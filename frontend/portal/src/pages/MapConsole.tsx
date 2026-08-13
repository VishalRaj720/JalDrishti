/**
 * The operational map — the portal's primary working surface.
 *
 * Built on the ml_pipeline dashboard's map rather than a fresh one: that map
 * already knows how to draw a plume honestly, and its layer set (aquifer
 * regime, ore, rivers, flow, fracture strike) is the context that makes a
 * result interpretable. What this adds is the portal's own data — districts,
 * blocks, wells, ISR sites, field observations in their three states — the
 * role model, and a real basemap so places have names.
 *
 * **Clicking the map is the main interaction.** For admin, regulator and
 * analyst it drops a pin, resolves what the engine knows there, and offers a
 * run. That run is interactive and unpersisted; registering the pin as an ISR
 * point is the separate, deliberate act that makes it a site the Simulation
 * Studio can produce an auditable record against.
 *
 * Field officers get the same map without the engine: they read context and
 * submit evidence, they do not model.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api, type District, type FeatureCollection, type IsrPoint, type LiveRun,
  type ObservationMap, type PinInfo, type PublicDistrictRisk,
} from "../api/client";
import { canRunSim, useAuth } from "../auth";
import { ErrorNote, Loading, bandOf } from "../components/bits";
import { attachBasemaps, BASEMAP_LABEL, type BasemapKey } from "../map/basemaps";
import { createPlumePanes, drawPlume, SPECIES_NAME, SPECIES_UNIT } from "../map/plume";

const CENTRE: [number, number] = [23.6, 85.3];

type Key =
  | "districts" | "blocks" | "wells" | "isr" | "green" | "amber" | "red"
  | "aquifers" | "ore" | "rivers" | "flow" | "strike" | "boundary";

interface LayerDef {
  key: Key; label: string; colour: string; shape?: "diamond" | "line" | "hollow";
  group: "Portal data" | "Reference geography";
  note?: string;
  /** Heavy payloads stay off until asked for. */
  lazy?: boolean;
}

const LAYERS: LayerDef[] = [
  { key: "districts", label: "Districts", colour: "#3fb6ff", group: "Portal data",
    note: "Filled by highest measured uranium" },
  { key: "blocks", label: "Blocks", colour: "#6ea8d8", group: "Portal data",
    note: "Finer administrative units", lazy: true },
  { key: "wells", label: "Monitoring wells", colour: "#8b97a7", group: "Portal data",
    note: "397 CGWB wells" },
  { key: "isr", label: "ISR sites (hypothetical)", colour: "#ffb84d", shape: "diamond",
    group: "Portal data" },
  { key: "green", label: "Ore · in model", colour: "#37d39b", group: "Portal data" },
  { key: "amber", label: "Ore · approved, not in model", colour: "#ffb84d", group: "Portal data" },
  { key: "red", label: "Observations · pending review", colour: "#ff5a5a", shape: "hollow",
    group: "Portal data" },
  { key: "boundary", label: "Jharkhand outline", colour: "#c9d4e2", shape: "line",
    group: "Reference geography" },
  { key: "ore", label: "Uranium deposits", colour: "#ffd166", group: "Reference geography",
    note: "Where the engine will produce a uranium plume at all" },
  { key: "aquifers", label: "Aquifer regime", colour: "#7fd1ae", group: "Reference geography",
    lazy: true, note: "Fractured vs weathered/porous" },
  { key: "rivers", label: "Perennial rivers", colour: "#3aa0ff", shape: "line",
    group: "Reference geography", lazy: true, note: "Where a plume would surface" },
  { key: "flow", label: "Groundwater flow →", colour: "#37d39b", shape: "line",
    group: "Reference geography", lazy: true, note: "Direction a plume travels" },
  { key: "strike", label: "Fracture strike ⇔", colour: "#c79bff", shape: "line",
    group: "Reference geography", lazy: true, note: "What elongates a plume" },
];

const RAMP: Record<string, string> = {
  danger: "#ff5a5a", warn: "#ffb84d", ok: "#37d39b", neutral: "#8390a3",
};

const SPECIES = ["uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l"];

const DEFAULT_ON: Record<Key, boolean> = {
  districts: true, blocks: false, wells: true, isr: true,
  green: true, amber: true, red: true,
  boundary: true, ore: true, aquifers: false, rivers: false, flow: false, strike: false,
};

// ── small helpers ────────────────────────────────────────────────────

/** Point at `lenDeg` from (lat,lon) along a bearing measured from north. */
function destPoint(lat: number, lon: number, azDeg: number, lenDeg: number): [number, number] {
  const a = (azDeg * Math.PI) / 180;
  return [lat + lenDeg * Math.cos(a),
          lon + (lenDeg * Math.sin(a)) / Math.cos((lat * Math.PI) / 180)];
}
function drawArrow(g: L.LayerGroup, lat: number, lon: number, az: number,
                   colour: string, len: number) {
  const tip = destPoint(lat, lon, az, len);
  const b1 = destPoint(tip[0], tip[1], az + 150, len * 0.42);
  const b2 = destPoint(tip[0], tip[1], az - 150, len * 0.42);
  L.polyline([[lat, lon], tip], { color: colour, weight: 1.3, opacity: 0.85 }).addTo(g);
  L.polyline([b1, tip, b2], { color: colour, weight: 1.3, opacity: 0.85 }).addTo(g);
}
function drawTick(g: L.LayerGroup, lat: number, lon: number, strike: number,
                  colour: string, len: number) {
  L.polyline([destPoint(lat, lon, strike, len), destPoint(lat, lon, strike + 180, len)],
             { color: colour, weight: 1.4, opacity: 0.8 }).addTo(g);
}

const fmt = (v: unknown, d = 2) =>
  typeof v === "number" && isFinite(v)
    ? v.toLocaleString(undefined, { maximumFractionDigits: d })
    : "–";

/**
 * Design §4.5 rule 5: below map resolution the answer is "no measurable
 * migration", never a bare `0`. A zero reads as a measurement showing nothing;
 * the truth is that the extent is smaller than this model can resolve.
 */
const distance = (v: unknown) =>
  typeof v === "number" && isFinite(v) && v < 1
    ? { text: "no measurable", unit: "migration" }
    : { text: fmt(v, 1), unit: "m" };

const area = (v: unknown) =>
  typeof v === "number" && isFinite(v) && v <= 0
    ? { text: "none", unit: "above the limit" }
    : { text: fmt(v), unit: "ha" };

// ── component ────────────────────────────────────────────────────────

export default function MapConsole() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const mayRun = canRunSim(me?.role);

  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<Record<Key, L.LayerGroup>>({} as never);
  const plumeGroup = useRef<L.LayerGroup | null>(null);
  const pinMarker = useRef<L.Marker | null>(null);
  const basemapCtl = useRef<{ set: (k: BasemapKey) => void } | null>(null);

  const [on, setOn] = useState<Record<Key, boolean>>(DEFAULT_ON);
  const [basemap, setBasemap] = useState<BasemapKey>("light");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<District | null>(null);
  const [bbox, setBbox] = useState<string | null>(null);
  const [pin, setPin] = useState<{ lon: number; lat: number } | null>(null);

  // engine controls
  const [species, setSpecies] = useState("uranium_ppb");
  const [years, setYears] = useState(10);
  const [inj, setInj] = useState(2500);
  const [width, setWidth] = useState(300);
  const [mode, setMode] = useState<"ml" | "analytical">("ml");
  const [run, setRun] = useState<LiveRun | null>(null);
  const [siteName, setSiteName] = useState("");

  // ── data ──
  const districts = useQuery({ queryKey: ["districts"], queryFn: () => api.get<District[]>("/districts") });
  const geo = useQuery({ queryKey: ["districts-geojson"], queryFn: () => api.get<any>("/districts/geojson") });
  const sites = useQuery({ queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points") });
  const obs = useQuery({ queryKey: ["obs-map"], queryFn: () => api.get<ObservationMap>("/field-observations/map") });
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });
  const wells = useQuery({
    queryKey: ["wells", bbox], enabled: on.wells && !!bbox,
    queryFn: () => api.get<any[]>(`/monitoring-wells?bbox=${bbox}&limit=2000`),
  });
  const blocks = useQuery({
    queryKey: ["blocks-geojson"], enabled: on.blocks,
    queryFn: () => api.get<FeatureCollection>("/public/risk/geojson/blocks"),
  });

  // Reference geography from the engine. Each is fetched only once its layer is
  // switched on — rivers alone is ~1.9 MB, and a map that stalls on load is a
  // map people stop opening. `staleTime` is an hour because these change only
  // when `Datasets/` does, which is a deliberate admin action.
  const REF = { staleTime: 3_600_000 } as const;
  const boundary = useQuery({
    queryKey: ["ml", "boundary"], enabled: on.boundary, ...REF,
    queryFn: () => api.get<any>("/ml/boundary"),
  });
  const ore = useQuery({
    queryKey: ["ml", "ore"], enabled: on.ore, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/ore"),
  });
  const aquifers = useQuery({
    queryKey: ["ml", "aquifers"], enabled: on.aquifers, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/aquifers"),
  });
  const rivers = useQuery({
    queryKey: ["ml", "rivers"], enabled: on.rivers, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/rivers"),
  });
  const flow = useQuery({
    queryKey: ["ml", "flow"], enabled: on.flow, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/flow-field?step=3"),
  });
  const strike = useQuery({
    queryKey: ["ml", "strike"], enabled: on.strike, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/strike-field?step=3"),
  });

  const pinInfo = useQuery({
    queryKey: ["ml-pin", pin?.lon, pin?.lat], enabled: !!pin && mayRun,
    queryFn: () => api.get<PinInfo>(`/ml/pin?lon=${pin!.lon}&lat=${pin!.lat}`),
    retry: false,
  });

  const predict = useMutation({
    mutationFn: () => api.post<LiveRun>("/ml/predict", {
      lon: pin!.lon, lat: pin!.lat, species,
      time_years: years, injection_rate_m3_day: inj,
      wellfield_width_m: width, mode: mode === "ml" ? "both" : "analytical",
    }),
    onSuccess: (r) => setRun(r),
  });

  const register = useMutation({
    mutationFn: () => api.post<IsrPoint>("/isr-points", {
      name: siteName.trim(),
      location: { type: "Point", coordinates: [pin!.lon, pin!.lat] },
      injection_rate: inj,
    }),
    onSuccess: () => {
      setSiteName("");
      qc.invalidateQueries({ queryKey: ["isr-points"] });
    },
  });

  const riskByName = useMemo(() => {
    const m = new Map<string, PublicDistrictRisk>();
    for (const d of risk.data?.districts ?? []) m.set(d.name, d);
    return m;
  }, [risk.data]);

  // ── map init ──
  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { center: CENTRE, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(m);
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(m);
    createPlumePanes(m);
    basemapCtl.current = attachBasemaps(m, "light");

    const syncBbox = () => {
      const b = m.getBounds();
      const r = (n: number) => n.toFixed(4);
      setBbox(`${r(b.getWest())},${r(b.getSouth())},${r(b.getEast())},${r(b.getNorth())}`);
    };
    m.on("moveend zoomend", syncBbox);
    syncBbox();

    for (const l of LAYERS) groups.current[l.key] = L.layerGroup().addTo(m);
    plumeGroup.current = L.layerGroup().addTo(m);

    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { basemapCtl.current?.set(basemap); }, [basemap]);

  // Clicking the map. Registered separately so it can depend on `mayRun`
  // without tearing down the map.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const handler = (e: L.LeafletMouseEvent) => {
      if (!mayRun) return;
      const { lat, lng } = e.latlng;
      setPin({ lon: +lng.toFixed(5), lat: +lat.toFixed(5) });
      setRun(null);
      pinMarker.current?.remove();
      pinMarker.current = L.marker([lat, lng], {
        icon: L.divIcon({ className: "pin-wrap", html: '<div class="map-pin"></div>',
                          iconSize: [18, 18], iconAnchor: [9, 9] }),
      }).addTo(m);
    };
    m.on("click", handler);
    return () => { m.off("click", handler); };
  }, [mayRun]);

  // ── layer visibility ──
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const l of LAYERS) {
      const g = groups.current[l.key];
      if (!g) continue;
      if (on[l.key]) { if (!m.hasLayer(g)) g.addTo(m); }
      else if (m.hasLayer(g)) m.removeLayer(g);
    }
  }, [on]);

  // ── districts ──
  useEffect(() => {
    const g = groups.current.districts;
    if (!g || !geo.data) return;
    g.clearLayers();
    L.geoJSON(geo.data, {
      style: (f) => {
        const r = riskByName.get((f?.properties as any)?.name ?? "");
        const c = RAMP[bandOf(r?.max_uranium_ppb).cls];
        return { color: c, weight: 1.3, fillColor: c, fillOpacity: 0.14 };
      },
      onEachFeature: (f, layer) => {
        const name = (f.properties as any)?.name ?? "District";
        const r = riskByName.get(name);
        layer.bindTooltip(
          `<b>${name}</b><br/>${r ? `${r.wells} wells · max ${r.max_uranium_ppb ?? "–"} ppb` : "no data"}`,
          { sticky: true });
        layer.on("click", (ev) => {
          L.DomEvent.stop(ev as any);   // a district click must not also drop a pin
          const d = districts.data?.find((x) => x.name === name);
          if (d) setSel(d);
        });
      },
    }).addTo(g);
  }, [geo.data, riskByName, districts.data]);

  // ── blocks ──
  useEffect(() => {
    const g = groups.current.blocks;
    if (!g) return;
    g.clearLayers();
    if (!on.blocks || !blocks.data) return;
    L.geoJSON(blocks.data as any, {
      style: (f) => {
        const c = RAMP[bandOf((f?.properties as any)?.max_uranium_ppb).cls];
        return { color: c, weight: 0.7, fillColor: c, fillOpacity: 0.10, dashArray: "3 3" };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name}</b> <span class="muted">${p.district}</span><br/>`
          + `${p.wells} well(s) · max ${p.max_uranium_ppb ?? "–"} ppb · ${p.band}`,
          { sticky: true });
      },
    }).addTo(g);
  }, [blocks.data, on.blocks]);

  // ── ISR sites ──
  useEffect(() => {
    const g = groups.current.isr;
    if (!g || !sites.data) return;
    g.clearLayers();
    for (const s of sites.data) {
      const c = s.location?.coordinates;
      if (!c) continue;
      // A diamond, not a circle: amber is reserved for the "approved, pending
      // sync" observation state, so ISR sites are told apart by SHAPE.
      L.marker([c[1], c[0]], {
        icon: L.divIcon({ className: "isr-pin-wrap", html: '<div class="isr-pin"></div>',
                          iconSize: [14, 14], iconAnchor: [7, 7] }),
      }).bindTooltip(`${s.name} — HYPOTHETICAL`, { direction: "top" }).addTo(g);
    }
  }, [sites.data]);

  // ── field observations, three states ──
  useEffect(() => {
    if (!obs.data || !groups.current.green) return;
    const paint = (k: Key, items: any[], colour: string, hollow: boolean, note: string) => {
      const g = groups.current[k];
      g.clearLayers();
      for (const it of items) {
        if (it.lon == null || it.lat == null) continue;
        L.circleMarker([it.lat, it.lon], {
          radius: 7, color: colour, weight: 2, fillColor: colour,
          fillOpacity: hollow ? 0 : 0.55, dashArray: hollow ? "3 3" : undefined,
        }).bindTooltip(`${it.name ?? "Observation"} — ${note}`, { direction: "top" }).addTo(g);
      }
    };
    paint("green", obs.data.approved_in_model, "#37d39b", false, "approved · in model");
    paint("amber", obs.data.approved_pending_sync, "#ffb84d", false, "approved · NOT yet in the model");
    paint("red", obs.data.pending_review, "#ff5a5a", true, "pending review");
  }, [obs.data]);

  // ── wells ──
  useEffect(() => {
    const g = groups.current.wells;
    if (!g) return;
    g.clearLayers();
    if (!on.wells || !wells.data) return;
    for (const w of wells.data) {
      if (w.latitude == null || w.longitude == null) continue;
      L.circleMarker([w.latitude, w.longitude], {
        radius: 2.6, color: "#8b97a7", weight: 1, fillOpacity: 0.65,
      }).bindTooltip(w.name ?? "well", { direction: "top" }).addTo(g);
    }
  }, [wells.data, on.wells]);

  // ── engine reference geography ──
  useEffect(() => {
    const g = groups.current.boundary;
    if (!g) return;
    g.clearLayers();
    if (!on.boundary || !boundary.data) return;
    L.geoJSON(boundary.data, {
      style: { color: "#c9d4e2", weight: 2, fill: false, dashArray: "6 4" },
      interactive: false,
    } as any).addTo(g);
  }, [boundary.data, on.boundary]);

  useEffect(() => {
    const g = groups.current.ore;
    if (!g) return;
    g.clearLayers();
    if (!on.ore || !ore.data) return;
    L.geoJSON(ore.data as any, {
      style: (f) => {
        const belt = /belt|envelope/i.test((f?.properties as any)?.name ?? "");
        return { color: belt ? "#b08d3a" : "#ffd166", weight: belt ? 1 : 1.6,
                 fillColor: "#ffd166", fillOpacity: belt ? 0.05 : 0.18,
                 dashArray: belt ? "5 5" : undefined };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name ?? "Uranium deposit"}</b>`
          + (p.origin ? ` <span class="muted">(${p.origin})</span>` : ""),
          { sticky: true });
      },
    }).addTo(g);
  }, [ore.data, on.ore]);

  useEffect(() => {
    const g = groups.current.aquifers;
    if (!g) return;
    g.clearLayers();
    if (!on.aquifers || !aquifers.data) return;
    L.geoJSON(aquifers.data as any, {
      style: (f) => {
        const fr = (f?.properties as any)?.regime === "fractured";
        return { color: fr ? "#7fd1ae" : "#d8b46a", weight: 0.6,
                 fillColor: fr ? "#7fd1ae" : "#d8b46a", fillOpacity: 0.12 };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.lithology ?? "aquifer"}</b> · ${p.regime}<br/>`
          + `K ${fmt(p.K_m_day, 3)} m/day · porosity ${fmt(p.eff_porosity, 3)}`
          + ` · ${fmt(p.thickness_m, 0)} m thick`,
          { className: "aq-tip", sticky: true });
      },
    }).addTo(g);
  }, [aquifers.data, on.aquifers]);

  useEffect(() => {
    const g = groups.current.rivers;
    if (!g) return;
    g.clearLayers();
    if (!on.rivers || !rivers.data) return;
    L.geoJSON(rivers.data as any, {
      style: { color: "#3aa0ff", weight: 1.1, opacity: 0.7 },
      onEachFeature: (f, l) => l.bindTooltip(
        `perennial river · ${fmt((f.properties as any)?.DIS_AV_CMS, 1)} m³/s`,
        { className: "aq-tip", sticky: true }),
    }).addTo(g);
  }, [rivers.data, on.rivers]);

  useEffect(() => {
    const g = groups.current.flow;
    if (!g) return;
    g.clearLayers();
    if (!on.flow || !flow.data) return;
    for (const f of flow.data.features) {
      const [lon, lat] = f.geometry.coordinates;
      drawArrow(g, lat, lon, f.properties.azimuth_deg,
                f.properties.source === "stations" ? "#37d39b" : "#7f8a99", 0.02);
    }
  }, [flow.data, on.flow]);

  useEffect(() => {
    const g = groups.current.strike;
    if (!g) return;
    g.clearLayers();
    if (!on.strike || !strike.data) return;
    for (const f of strike.data.features) {
      const [lon, lat] = f.geometry.coordinates;
      const V = f.properties.circular_variance;
      drawTick(g, lat, lon, f.properties.strike_deg,
               V < 0.4 ? "#ffcf6f" : V > 0.65 ? "#9b7bff" : "#c79bff", 0.017);
    }
  }, [strike.data, on.strike]);

  // ── plume ──
  useEffect(() => {
    if (!plumeGroup.current) return;
    if (!run) { plumeGroup.current.clearLayers(); return; }
    drawPlume(plumeGroup.current, run, mode === "ml");
  }, [run, mode]);

  const toggle = useCallback((k: Key) => setOn((s) => ({ ...s, [k]: !s[k] })), []);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    const list = districts.data ?? [];
    return t ? list.filter((d) => d.name.toLowerCase().includes(t)) : list;
  }, [districts.data, q]);

  const selRisk = sel ? riskByName.get(sel.name) : undefined;
  const an = run?.metrics?.analytical;
  const mlm = run?.metrics?.ml as any;
  const unit = SPECIES_UNIT[species] ?? "";

  const flyTo = (d: District) => {
    setSel(d);
    const f = (geo.data?.features ?? []).find((x: any) => x.properties?.name === d.name);
    if (f && map.current) map.current.fitBounds(L.geoJSON(f).getBounds(), { maxZoom: 10 });
  };

  const loadingRef =
    (on.rivers && rivers.isLoading) || (on.aquifers && aquifers.isLoading) ||
    (on.flow && flow.isLoading) || (on.strike && strike.isLoading) ||
    (on.blocks && blocks.isLoading);

  return (
    <div className="map-shell">
      {/* ── left rail ── */}
      <aside className="rail">
        <input placeholder="Search districts…" value={q} onChange={(e) => setQ(e.target.value)} />

        <div className="rail-head">Basemap</div>
        <div className="seg seg-sm">
          {(["light", "dark", "satellite"] as BasemapKey[]).map((b) => (
            <button key={b} className={basemap === b ? "active" : ""}
                    onClick={() => setBasemap(b)}>{BASEMAP_LABEL[b]}</button>
          ))}
        </div>

        {(["Portal data", "Reference geography"] as const).map((grp) => (
          <div key={grp}>
            <div className="rail-head">
              {grp}
              {grp === "Reference geography" && loadingRef && <span className="spinner sm" />}
            </div>
            {LAYERS.filter((l) => l.group === grp).map((l) => (
              <div className="layer-row" key={l.key} title={l.note ?? ""}>
                <button className="toggle" data-on={on[l.key]}
                        aria-label={`Toggle ${l.label}`} onClick={() => toggle(l.key)} />
                <span className={`sw ${l.shape ?? ""}`} style={{ background: l.colour }} />
                <span>{l.label}</span>
              </div>
            ))}
          </div>
        ))}

        {grpNote(mayRun)}

        <div className="rail-head">Districts ({filtered.length})</div>
        {districts.isLoading && <Loading />}
        {filtered.map((d) => {
          const r = riskByName.get(d.name);
          const b = bandOf(r?.max_uranium_ppb);
          return (
            <div key={d.id} className="list-item" onClick={() => flyTo(d)}>
              <div>
                <div className="nm">{d.name}</div>
                <div className="mt">{r ? `${r.wells} wells · ${r.samples} samples` : "no data"}</div>
              </div>
              <span className={`chip ${b.cls}`}>{b.label}</span>
            </div>
          );
        })}
      </aside>

      {/* ── map ── */}
      <div className="map-area">
        <div ref={el} className="map-canvas" />

        <div className="map-ov legend">
          <div className="ov-title">Legend</div>
          {LAYERS.filter((l) => on[l.key]).map((l) => (
            <div className="legend-row" key={l.key}>
              <span className={`sw ${l.shape ?? ""}`} style={{ background: l.colour }} />
              {l.label}
            </div>
          ))}
          {run && (
            <>
              <div className="legend-row"><span className="sw" style={{ background: "#b71c1c" }} />
                Concentration — <b>darker = higher</b></div>
              <div className="legend-row"><span className="sw line" style={{ background: "#2bb3ff" }} />
                Monitoring ring (dotted)</div>
              {mode === "ml" && (
                <div className="legend-row"><span className="sw line" style={{ background: "#5b21b6" }} />
                  ML migration envelope</div>
              )}
            </>
          )}
          <div className="muted small" style={{ marginTop: 6 }}>
            District fill = highest measured uranium. 🟡 approved but not yet in
            <span className="mono"> Datasets/</span> — a simulation does not use it yet.
          </div>
        </div>

        {mayRun && !pin && (
          <div className="map-ov hint">
            <b>Click anywhere in Jharkhand</b> to resolve the hydrogeology there and
            run the engine.
          </div>
        )}
      </div>

      {/* ── right drawer: engine ── */}
      {mayRun && pin && (
        <aside className="drawer wide">
          <div className="drawer-head">
            <div>
              <div className="dh-title">Pin</div>
              <div className="dh-sub mono">{pin.lat.toFixed(4)} °N, {pin.lon.toFixed(4)} °E</div>
            </div>
            <button className="btn ghost" onClick={() => {
              setPin(null); setRun(null); pinMarker.current?.remove(); pinMarker.current = null;
            }}>Close</button>
          </div>

          {pinInfo.isLoading && <Loading label="Resolving hydrogeology…" />}
          {pinInfo.error && <ErrorNote error={pinInfo.error} />}

          {pinInfo.data && (
            <>
              <div className="sec">What the engine resolves here</div>
              <dl className="kv">
                <dt>District</dt><dd>{pinInfo.data.district ?? "–"}</dd>
                <dt>Lithology</dt><dd>{pinInfo.data.lithology ?? "–"}
                  {pinInfo.data.lithology_detail ? ` · ${pinInfo.data.lithology_detail}` : ""}</dd>
                <dt>Regime</dt><dd>{pinInfo.data.regime ?? "–"}</dd>
                <dt>K</dt><dd>{fmt(pinInfo.data.K_m_day, 3)} m/day</dd>
                <dt>Thickness</dt><dd>{fmt(pinInfo.data.thickness_m, 1)} m</dd>
                <dt>Flow azimuth</dt><dd>{fmt(pinInfo.data.flow?.azimuth_deg, 1)}°</dd>
                <dt>Gradient</dt><dd>{fmt(pinInfo.data.flow?.gradient_i, 5)}</dd>
                <dt>Nearest well</dt><dd>{fmt(pinInfo.data.data_confidence?.nearest_well_km, 1)} km</dd>
              </dl>
              <div className="muted small">
                Resolved by the engine from its own datasets — not from this
                portal's database.
              </div>

              <div className="sec">Run</div>
              <div className="seg seg-sm">
                {SPECIES.map((s) => (
                  <button key={s} className={species === s ? "active" : ""}
                          onClick={() => setSpecies(s)}>{SPECIES_NAME[s]}</button>
                ))}
              </div>
              <div className="seg seg-sm" style={{ marginTop: 6 }}>
                <button className={mode === "ml" ? "active" : ""} onClick={() => setMode("ml")}>
                  ML + bands</button>
                <button className={mode === "analytical" ? "active" : ""} onClick={() => setMode("analytical")}>
                  Analytical only</button>
              </div>

              <div className="slider"><label>Evaluation time <span className="u">yr</span><b>{years}</b></label>
                <input type="range" min={0} max={50} step={1} value={years}
                       onChange={(e) => setYears(+e.target.value)} /></div>
              <div className="slider"><label>Injection rate <span className="u">m³/day</span><b>{inj}</b></label>
                <input type="range" min={200} max={8000} step={50} value={inj}
                       onChange={(e) => setInj(+e.target.value)} /></div>
              <div className="slider"><label>Well-pattern footprint ⌀ <span className="u">m</span><b>{width}</b></label>
                <input type="range" min={100} max={800} step={10} value={width}
                       onChange={(e) => setWidth(+e.target.value)} /></div>

              <button className="btn primary block" disabled={predict.isPending}
                      onClick={() => predict.mutate()}>
                {predict.isPending ? "Solving transport…" : "Run on this pin"}
              </button>
              <ErrorNote error={predict.error} />
              <div className="muted small" style={{ marginTop: 6 }}>
                Interactive and <b>not stored</b>. Register the pin below to produce
                an auditable run from the Simulation Studio. Uranium returns nothing
                outside an ore zone — the engine will not invent a source term.
              </div>
            </>
          )}

          {run && (
            <>
              {(run.extrapolation?.length ?? 0) > 0 && (
                <div className="banner warn" style={{ marginTop: 10 }}>
                  <strong>Outside trained support:</strong>{" "}
                  <span className="mono">{run.extrapolation!.join(", ")}</span>. The
                  analytical engine is serving; the ML band's 80% guarantee is void here.
                </div>
              )}
              {/* The engine's OWN words about why it refused a source term.
                  Without this a non-ore pin renders as "0 ha", which reads as a
                  measurement showing safety rather than as the model declining
                  to invent contamination (design §4.6 rule 3). */}
              {run.notice && (
                <div className="banner warn" style={{ marginTop: 10 }}>
                  <strong>{run.ore_zone?.zone === "none" ? "Non-ore zone." : "Note."}</strong>{" "}
                  {run.notice}
                  {run.ore_zone?.nearest_deposit && (
                    <div className="muted small" style={{ marginTop: 4 }}>
                      Nearest deposit: {run.ore_zone.nearest_deposit} ·{" "}
                      {fmt(run.ore_zone.nearest_deposit_km, 1)} km away.
                    </div>
                  )}
                </div>
              )}

              <div className="sec">Result</div>
              <div className="metric-row">
                <div className="metric danger">
                  <div className="m-label">Contaminated footprint</div>
                  <div className="m-value">{area(an?.area_ha).text}{" "}
                    <span className="m-unit">{area(an?.area_ha).unit}</span></div>
                  <div className="m-band">{mlm?.area_ha
                    ? `ML P10–P90 ${fmt(mlm.area_ha.p10)} – ${fmt(mlm.area_ha.p90)}`
                    : run.ml_status ?? "analytical only"}</div>
                </div>
                <div className="metric">
                  <div className="m-label">Max migration</div>
                  <div className="m-value">{distance(an?.migration_m).text}{" "}
                    <span className="m-unit">{distance(an?.migration_m).unit}</span></div>
                  <div className="m-band">{mlm?.migration_m
                    ? `ML P10–P90 ${fmt(mlm.migration_m.p10)} – ${fmt(mlm.migration_m.p90)}`
                    : run.ml_status ?? "analytical only"}</div>
                </div>
                <div className="metric">
                  <div className="m-label">At compliance ring</div>
                  <div className="m-value">{fmt(an?.compliance_conc, 3)} <span className="m-unit">{unit}</span></div>
                  <div className="m-band">{mlm?.compliance_conc
                    ? `ML P10–P90 ${fmt(mlm.compliance_conc.p10, 3)} – ${fmt(mlm.compliance_conc.p90, 3)}`
                    : run.ml_status ?? "analytical only"}</div>
                </div>
              </div>

              {run.isr_excursion && (
                <div className="banner" style={{ marginTop: 8 }}>
                  <strong>ISR excursion (NUREG-1569-inspired):</strong>{" "}
                  {run.isr_excursion.excursion_declared
                    ? <span className="chip danger">declared</span>
                    : <span className="chip ok">none</span>}
                  <div className="muted small" style={{ marginTop: 4 }}>
                    {run.isr_excursion.rule}
                  </div>
                </div>
              )}

              <div className="sec">Register this location</div>
              <div className="field">
                <label>Site name</label>
                <input value={siteName} placeholder="e.g. Bagjata North (hypothetical)"
                       onChange={(e) => setSiteName(e.target.value)} />
              </div>
              <button className="btn block" disabled={!siteName.trim() || register.isPending}
                      onClick={() => register.mutate()}>
                {register.isPending ? "Registering…" : "Register as an ISR point"}
              </button>
              <ErrorNote error={register.error} />
              {register.isSuccess && (
                <div className="banner ok" style={{ marginTop: 8 }}>
                  Registered. It is now selectable in the Simulation Studio, where a
                  run is stored with its model card, artifact bundle and code version.
                </div>
              )}
              <div className="muted small" style={{ marginTop: 6 }}>
                Every site in this system is hypothetical. Registering one records a
                location to screen, not a proposal to mine it.
              </div>
            </>
          )}
        </aside>
      )}

      {/* ── right drawer: district ── */}
      {!pin && sel && (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <div className="dh-title">{sel.name}</div>
              <div className="dh-sub">District</div>
            </div>
            <button className="btn ghost" onClick={() => setSel(null)}>Close</button>
          </div>
          <div className="sec">Measured groundwater</div>
          <dl className="kv">
            <dt>Wells sampled</dt><dd>{selRisk?.wells ?? "–"}</dd>
            <dt>Samples</dt><dd>{selRisk?.samples ?? "–"}</dd>
            <dt>Max uranium</dt><dd>{selRisk?.max_uranium_ppb ?? "–"} ppb</dd>
            <dt>Band</dt><dd>{bandOf(selRisk?.max_uranium_ppb).label}</dd>
          </dl>
          <div className="muted small">Measurements from CGWB sampling. Not model output.</div>
        </aside>
      )}
    </div>
  );
}

function grpNote(mayRun: boolean) {
  return (
    <div className="muted small" style={{ padding: "8px 2px 2px" }}>
      {mayRun
        ? "Click the map to place a pin and run the engine there."
        : "Running the model is restricted to admin, regulator and analyst. "
          + "You can read every layer here."}
    </div>
  );
}
