/**
 * The Console — one map, one engine surface.
 *
 * P2 MERGED the Map Console and the Simulation Studio, which were two screens
 * running the same engine with different parameters and producing different
 * answers for the same site. The split had a worse consequence than confusion:
 * the *live* path (map click, explicitly unpersisted) drew contours, the leach
 * zone, the compliance ring and the ML envelope, while the *auditable* path
 * (registered site, stored run, provenance-pinned) rendered a "Planned" card
 * where the map should have been. The product's best evidence was on its
 * throwaway route and its official route was three numbers and a table.
 *
 * Now there is one canvas and two modes on it:
 *
 *   PIN mode    click anywhere → resolve the hydrogeology → run live → see the
 *               plume → register the location as a site. The run is NOT stored,
 *               and says so.
 *   SITE mode   select a registered site → its operating parameters are shown
 *               READ-ONLY, because the site *is* the operation (migration 0015)
 *               → choose species, evaluation horizon and restoration sweep →
 *               run and store → the stored run redraws its own plume.
 *
 * Both modes draw through `drawPlume`, so a live and a stored result cannot
 * diverge in appearance without diverging in fact.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api, type District, type EngineBounds, type FeatureCollection, type IsrPoint,
  type LiveRun, type ObservationMap, type PinInfo, type PublicDistrictRisk,
  type SimRun,
} from "../api/client";
import { canRunSim, useAuth } from "../auth";
import { ErrorNote, Loading, RiskBand, bandOf } from "../components/bits";
import { attachBasemaps, BASEMAP_LABEL, type BasemapKey } from "../map/basemaps";
import { lineOpacity, maskOpacity, OVERLAY, tune } from "../map/palette";
import {
  createPlumePanes, drawPlume, SPECIES_NAME, storedRunToPlume,
} from "../map/plume";
import { addScaleControl } from "../map/scale";
import { useRail } from "../map/useRail";
import {
  DEFAULT_ON, LAYERS, RAMP, SPECIES, type Key,
  drawArrow, drawTick, fmt, ringsOf,
} from "../console/mapLayers";
import RegisterForm from "../console/RegisterForm";
import RunResult from "../console/RunResult";
import SweepChart, { type Sweep } from "../console/SweepChart";
import ProposeAdvisory from "../console/ProposeAdvisory";

const CENTRE: [number, number] = [23.6, 85.3];

export default function Console() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const mayRun = canRunSim(me?.role);

  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<Record<Key, L.LayerGroup>>({} as never);
  const plumeGroup = useRef<L.LayerGroup | null>(null);
  const pinMarker = useRef<L.Marker | null>(null);
  const basemapCtl = useRef<{ set: (k: BasemapKey) => void } | null>(null);

  const { collapsed, toggle: toggleRail } = useRail(map);
  const [on, setOn] = useState<Record<Key, boolean>>(DEFAULT_ON);
  const [basemap, setBasemap] = useState<BasemapKey>("light");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<District | null>(null);
  const [bbox, setBbox] = useState<string | null>(null);

  /** The drawer is one of three things at a time. */
  const [mode, setMode] = useState<"none" | "pin" | "site">("none");
  const [pin, setPin] = useState<{ lon: number; lat: number } | null>(null);
  const [siteId, setSiteId] = useState<string>("");

  // Live-run controls (pin mode only).
  const [species, setSpecies] = useState("uranium_ppb");
  const [liveYears, setLiveYears] = useState(10);
  const [showBands, setShowBands] = useState(true);
  const [live, setLive] = useState<LiveRun | null>(null);

  // Stored-run controls (site mode). These two, and only these two, are what a
  // run may vary against a fixed site.
  const [runYears, setRunYears] = useState(20);
  const [runRestoration, setRunRestoration] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const [sweepAxis, setSweepAxis] = useState<"restoration" | "evaluation">("restoration");

  // ── data ──
  const districts = useQuery({ queryKey: ["districts"], queryFn: () => api.get<District[]>("/districts") });
  const geo = useQuery({ queryKey: ["districts-geojson"], queryFn: () => api.get<any>("/districts/geojson") });
  const sites = useQuery({ queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points") });
  const obs = useQuery({ queryKey: ["obs-map"], queryFn: () => api.get<ObservationMap>("/field-observations/map") });
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });
  const bounds = useQuery({
    queryKey: ["ml", "bounds"], staleTime: 3_600_000, enabled: mayRun,
    queryFn: () => api.get<EngineBounds>("/ml/bounds"),
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
  // map people stop opening.
  const REF = { staleTime: 3_600_000 } as const;
  const boundary = useQuery({ queryKey: ["ml", "boundary"], enabled: on.boundary, ...REF,
    queryFn: () => api.get<any>("/ml/boundary") });
  const ore = useQuery({ queryKey: ["ml", "ore"], enabled: on.ore, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/ore") });
  const aquifers = useQuery({ queryKey: ["ml", "aquifers"], enabled: on.aquifers, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/aquifers") });
  const rivers = useQuery({ queryKey: ["ml", "rivers"], enabled: on.rivers, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/rivers") });
  const flow = useQuery({ queryKey: ["ml", "flow"], enabled: on.flow, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/flow-field?step=3") });
  const strike = useQuery({ queryKey: ["ml", "strike"], enabled: on.strike, ...REF,
    queryFn: () => api.get<FeatureCollection>("/ml/strike-field?step=3") });

  const pinInfo = useQuery({
    queryKey: ["ml-pin", pin?.lon, pin?.lat], enabled: !!pin && mayRun && mode === "pin",
    queryFn: () => api.get<PinInfo>(`/ml/pin?lon=${pin!.lon}&lat=${pin!.lat}`),
    retry: false,
  });

  const site = useMemo(
    () => sites.data?.find((s) => s.id === siteId) ?? null, [sites.data, siteId]);

  const runs = useQuery({
    queryKey: ["runs", siteId], enabled: !!siteId && mode === "site",
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${siteId}&limit=25`),
    // A run finishes in a background task. `InBackground` matters: the client
    // disables window-focus refetching, and a plain interval is paused while
    // the tab is hidden, so switching away mid-run and back would otherwise
    // strand the row on "running" forever.
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
  });

  const activeRun = useMemo(() => {
    const list = runs.data ?? [];
    return list.find((r) => r.id === runId) ?? list[0] ?? null;
  }, [runs.data, runId]);

  const predict = useMutation({
    mutationFn: () => api.post<LiveRun>("/ml/predict", {
      lon: pin!.lon, lat: pin!.lat, species,
      time_years: liveYears, mode: showBands ? "both" : "analytical",
    }),
    onSuccess: (r) => setLive(r),
  });

  const startRun = useMutation({
    mutationFn: () => api.post<SimRun>(`/simulations/${siteId}`, {
      species, time_years: runYears, restoration_years: runRestoration,
    }),
    onSuccess: (r) => { setRunId(r.id); qc.invalidateQueries({ queryKey: ["runs", siteId] }); },
  });

  /**
   * The sweep — "how many years of restoration is enough", answered as a curve.
   *
   * Synchronous and unstored. The engine solves in ~0.26 s warm, so six points
   * cost ~1.6 s; the "5–15 s" a stored run takes is queueing and provenance
   * overhead, not physics. Each axis holds the other fixed, and the held value
   * is sent explicitly because restoration adequacy is conditional on when you
   * look — a sweep that suffices at 20 yr need not at 50.
   */
  const sweep = useMutation({
    mutationFn: (axis: "restoration" | "evaluation") =>
      api.post<Sweep>(`/simulations/${siteId}/sweep`, {
        axis, species, points: 6,
        ...(axis === "restoration"
          ? { time_years: runYears }
          : { restoration_years: runRestoration }),
      }),
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
    addScaleControl(m);
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

  // Clicking the map drops a pin. Registered separately so it can depend on
  // `mayRun` without tearing down the map.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const handler = (e: L.LeafletMouseEvent) => {
      if (!mayRun) return;
      const { lat, lng } = e.latlng;
      setPin({ lon: +lng.toFixed(5), lat: +lat.toFixed(5) });
      setMode("pin");
      setLive(null);
      setSiteId("");
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
        const b = bandOf(r?.max_uranium_ppb);
        const c = RAMP[b.cls];
        // Weight and dash carry the band as well as hue, so the choropleth is
        // separable without colour vision (see `bandOf`).
        return { color: c, weight: b.weight, dashArray: b.dash, fillColor: c, fillOpacity: 0.14 };
      },
      onEachFeature: (f, layer) => {
        const name = (f.properties as any)?.name ?? "District";
        const r = riskByName.get(name);
        layer.bindTooltip(
          `<b>${name}</b><br/>${r ? `${r.wells} wells · max ${r.max_uranium_ppb ?? "–"} ppb · ${bandOf(r.max_uranium_ppb).label}` : "no data"}`,
          { sticky: true });
        layer.on("click", (ev) => {
          L.DomEvent.stop(ev as any);   // a district click must not also drop a pin
          const d = districts.data?.find((x) => x.name === name);
          if (d) { setSel(d); setMode("none"); }
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
        const b = bandOf((f?.properties as any)?.max_uranium_ppb);
        const c = RAMP[b.cls];
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

  // ── ISR sites — now CLICKABLE, which is what makes the merge work ──
  useEffect(() => {
    const g = groups.current.isr;
    if (!g || !sites.data) return;
    g.clearLayers();
    for (const s of sites.data) {
      const c = s.location?.coordinates;
      if (!c) continue;
      // A diamond, not a circle: amber is reserved for the "approved, pending
      // sync" observation state, so ISR sites are told apart by SHAPE.
      const mk = L.marker([c[1], c[0]], {
        icon: L.divIcon({ className: "isr-pin-wrap", html: '<div class="isr-pin"></div>',
                          iconSize: [14, 14], iconAnchor: [7, 7] }),
      }).bindTooltip(`${s.name} — HYPOTHETICAL · click to open`, { direction: "top" });
      mk.on("click", (ev) => {
        L.DomEvent.stop(ev as any);
        openSite(s);
      });
      mk.addTo(g);
    }
  }, [sites.data]); // eslint-disable-line react-hooks/exhaustive-deps

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
        radius: 2.6, color: OVERLAY.well, weight: 1, fillOpacity: 0.65,
      }).bindTooltip(w.name ?? "well", { direction: "top" }).addTo(g);
    }
  }, [wells.data, on.wells]);

  // ── boundary + the inverse mask that dims everything outside the state ──
  useEffect(() => {
    const g = groups.current.boundary;
    if (!g) return;
    g.clearLayers();
    if (!on.boundary || !boundary.data) return;
    const rings = ringsOf(boundary.data);
    if (rings.length) {
      const world: L.LatLngExpression[] = [[-85, -179], [-85, 179], [85, 179], [85, -179]];
      L.polygon([world, ...rings], {
        pane: "paneMask", stroke: false, fillColor: "#000",
        fillOpacity: maskOpacity(basemap), interactive: false,
      }).addTo(g);
      for (const r of rings) {
        L.polygon(r, {
          pane: "paneMask", color: OVERLAY.boundary, weight: 1.6, fill: false,
          opacity: lineOpacity(basemap), interactive: false,
        }).addTo(g);
      }
    }
  }, [boundary.data, on.boundary, basemap]);

  useEffect(() => {
    const g = groups.current.ore;
    if (!g) return;
    g.clearLayers();
    if (!on.ore || !ore.data) return;
    L.geoJSON(ore.data as any, {
      style: (f) => {
        const belt = (f?.properties as any)?.tier !== "deposit";
        return tune(basemap, {
          color: belt ? OVERLAY.oreBelt : OVERLAY.oreDeposit,
          weight: belt ? 1.2 : 1.4,
          fillColor: belt ? OVERLAY.oreBelt : OVERLAY.oreDeposit,
          fillOpacity: belt ? 0.05 : 0.22,
          dashArray: belt ? "5 5" : undefined,
        } as any, belt ? 0.06 : 0.24) as any;
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `${p.tier === "deposit" ? "Uranium deposit" : "Prospective belt"}: `
          + `<b>${p.name ?? "unnamed"}</b>`
          + (p.origin ? ` <span class="muted">(${p.origin})</span>` : ""),
          { sticky: true });
      },
    }).addTo(g);
  }, [ore.data, on.ore, basemap]);

  useEffect(() => {
    const g = groups.current.aquifers;
    if (!g) return;
    g.clearLayers();
    if (!on.aquifers || !aquifers.data) return;
    L.geoJSON(aquifers.data as any, {
      style: (f) => {
        const fr = (f?.properties as any)?.regime === "fractured";
        const c = fr ? OVERLAY.aquiferFractured : OVERLAY.aquiferPorous;
        return tune(basemap, { color: c, weight: 0.6, fillColor: c, fillOpacity: 0.12 } as any,
                    0.14) as any;
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
  }, [aquifers.data, on.aquifers, basemap]);

  useEffect(() => {
    const g = groups.current.rivers;
    if (!g) return;
    g.clearLayers();
    if (!on.rivers || !rivers.data) return;
    L.geoJSON(rivers.data as any, {
      style: { color: OVERLAY.river, weight: 1.1, opacity: lineOpacity(basemap) },
      onEachFeature: (f, l) => l.bindTooltip(
        `perennial river · ${fmt((f.properties as any)?.DIS_AV_CMS, 1)} m³/s`,
        { className: "aq-tip", sticky: true }),
    }).addTo(g);
  }, [rivers.data, on.rivers, basemap]);

  useEffect(() => {
    const g = groups.current.flow;
    if (!g) return;
    g.clearLayers();
    if (!on.flow || !flow.data) return;
    for (const f of flow.data.features) {
      const [lon, lat] = f.geometry.coordinates;
      drawArrow(g, lat, lon, f.properties.azimuth_deg,
                f.properties.source === "stations" ? OVERLAY.flowStations : OVERLAY.flowDem,
                0.02);
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
               V < 0.4 ? OVERLAY.strikeTight
                 : V > 0.65 ? OVERLAY.strikeSpread : OVERLAY.strikeMid, 0.017);
    }
  }, [strike.data, on.strike]);

  // ── the plume — one renderer, both modes ──
  const storedPlume = useMemo(
    () => (activeRun ? storedRunToPlume(activeRun) : null), [activeRun]);

  useEffect(() => {
    const g = plumeGroup.current;
    if (!g) return;
    const r = mode === "site" ? storedPlume : mode === "pin" ? live : null;
    if (!r) { g.clearLayers(); return; }
    drawPlume(g, r, showBands);
  }, [mode, live, storedPlume, showBands]);

  const toggle = useCallback((k: Key) => setOn((s) => ({ ...s, [k]: !s[k] })), []);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    const list = districts.data ?? [];
    return t ? list.filter((d) => d.name.toLowerCase().includes(t)) : list;
  }, [districts.data, q]);

  const filteredSites = useMemo(() => {
    const t = q.trim().toLowerCase();
    const list = sites.data ?? [];
    return t ? list.filter((s) => s.name.toLowerCase().includes(t)) : list;
  }, [sites.data, q]);

  function openSite(s: IsrPoint) {
    setSiteId(s.id);
    setMode("site");
    setRunId(null);
    setSel(null);
    setPin(null);
    setLive(null);
    pinMarker.current?.remove();
    pinMarker.current = null;
    // A site's own planned sweep is the sensible starting point for the run
    // control; the run can still test a different one without editing the site.
    setRunRestoration(s.restoration_years ?? 0);
    const c = s.location?.coordinates;
    if (c && map.current) map.current.setView([c[1], c[0]], Math.max(map.current.getZoom(), 11));
  }

  function closeDrawer() {
    setMode("none");
    setPin(null);
    setSiteId("");
    setLive(null);
    pinMarker.current?.remove();
    pinMarker.current = null;
  }

  const flyTo = (d: District) => {
    setSel(d);
    setMode("none");
    const f = (geo.data?.features ?? []).find((x: any) => x.properties?.name === d.name);
    if (f && map.current) map.current.fitBounds(L.geoJSON(f).getBounds(), { maxZoom: 10 });
  };

  const loadingRef =
    (on.rivers && rivers.isLoading) || (on.aquifers && aquifers.isLoading) ||
    (on.flow && flow.isLoading) || (on.strike && strike.isLoading) ||
    (on.blocks && blocks.isLoading);

  const selRisk = sel ? riskByName.get(sel.name) : undefined;
  const B = bounds.data;
  const horizonMax = B?.horizon_ui_max ?? 50;
  const restMax = B?.restoration_ui_max ?? 30;
  const horizonTrained = B?.horizon_trained_max;
  const restTrained = B?.restoration_trained_max;

  return (
    <div className="map-shell">
      {/* ── left rail ── */}
      {!collapsed && (
      <aside className="rail">
        <div className="rail-top">
          <span className="t">Sites, layers &amp; districts</span>
          <button className="rail-btn" onClick={toggleRail}
                  title="Collapse the panel" aria-label="Collapse the panel">‹</button>
        </div>
        <input placeholder="Search sites and districts…" value={q}
               onChange={(e) => setQ(e.target.value)} aria-label="Search" />

        <div className="rail-head">Basemap</div>
        <div className="seg seg-sm">
          {(["light", "dark", "satellite"] as BasemapKey[]).map((b) => (
            <button key={b} className={basemap === b ? "active" : ""}
                    onClick={() => setBasemap(b)}>{BASEMAP_LABEL[b]}</button>
          ))}
        </div>

        <div className="rail-head">Registered sites ({filteredSites.length})</div>
        {sites.isLoading && <Loading />}
        {sites.data?.length === 0 && (
          <div className="muted small" style={{ padding: "2px 2px 8px" }}>
            No sites yet. Click anywhere in Jharkhand to resolve the hydrogeology
            there and register one.
          </div>
        )}
        {filteredSites.map((s) => (
          <button key={s.id} className={`list-item ${s.id === siteId ? "sel" : ""}`}
                  onClick={() => openSite(s)}>
            <div>
              <div className="nm">{s.name}</div>
              <div className="mt">
                {fmt(s.injection_rate_m3_day, 0)} m³/day · {fmt(s.operation_years, 0)} yr
              </div>
            </div>
            <span className="chip warn">Hypothetical</span>
          </button>
        ))}

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

        <div className="muted small" style={{ padding: "8px 2px 2px" }}>
          {mayRun
            ? "Click the map to place a pin, or a diamond to open a registered site."
            : "Running the model is restricted to admin, regulator and analyst. "
              + "You can read every layer here."}
        </div>

        <div className="rail-head">Districts ({filtered.length})</div>
        {districts.isLoading && <Loading />}
        {filtered.map((d) => {
          const r = riskByName.get(d.name);
          return (
            <button key={d.id} className="list-item" onClick={() => flyTo(d)}>
              <div>
                <div className="nm">{d.name}</div>
                <div className="mt">{r ? `${r.wells} wells · ${r.samples} samples` : "no data"}</div>
              </div>
              <RiskBand value={r?.max_uranium_ppb} />
            </button>
          );
        })}
      </aside>
      )}

      {/* ── map ── */}
      <div className="map-area">
        <div ref={el} className="map-canvas" />

        {collapsed && (
          <button className="rail-peek" onClick={toggleRail}
                  title="Show the panel" aria-label="Show the panel">›</button>
        )}

        <div className="map-ov legend">
          <div className="ov-title">Legend</div>
          {LAYERS.filter((l) => on[l.key]).map((l) => (
            <div className="legend-row" key={l.key}>
              <span className={`sw ${l.shape ?? ""}`} style={{ background: l.colour }} />
              {l.label}
            </div>
          ))}
          {(live || storedPlume) && (
            <>
              <div className="legend-hr" />
              <div className="legend-row"><span className="sw" style={{ background: "#b71c1c" }} />
                Concentration — <b>darker = higher</b></div>
              <div className="legend-row"><span className="sw line" style={{ background: "#2bb3ff" }} />
                Monitoring ring (dotted)</div>
              {showBands && (
                <div className="legend-row"><span className="sw line" style={{ background: "#5b21b6" }} />
                  ML migration envelope</div>
              )}
            </>
          )}
          <div className="muted small" style={{ marginTop: 6 }}>
            District fill = highest <b>measured</b> uranium, never model output. Band is
            also carried by outline weight, so the ramp does not depend on colour vision.
          </div>
        </div>

        {mayRun && mode === "none" && (
          <div className="map-ov hint">
            <b>Click anywhere in Jharkhand</b> to resolve the hydrogeology and run the
            engine there — or click an amber diamond to open a registered site.
          </div>
        )}
      </div>

      {/* ── drawer: PIN mode ── */}
      {mayRun && mode === "pin" && pin && (
        <aside className="drawer wide">
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">Unregistered pin</div>
              <div className="dh-sub mono">{pin.lat.toFixed(4)} °N, {pin.lon.toFixed(4)} °E</div>
            </div>
            <button className="btn ghost" onClick={closeDrawer}>Close</button>
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
                Resolved by the engine from its own datasets — not from this portal's
                database.
              </div>

              <div className="sec">Try a run here</div>
              <div className="seg seg-sm">
                {SPECIES.map((s) => (
                  <button key={s} className={species === s ? "active" : ""}
                          onClick={() => setSpecies(s)}>{SPECIES_NAME[s]}</button>
                ))}
              </div>
              <div className="seg seg-sm" style={{ marginTop: 6 }}>
                <button className={showBands ? "active" : ""} onClick={() => setShowBands(true)}>
                  ML + bands</button>
                <button className={!showBands ? "active" : ""} onClick={() => setShowBands(false)}>
                  Analytical only</button>
              </div>

              <div className="slider">
                <label>Evaluation horizon <span className="u">yr</span><b>{liveYears}</b></label>
                <input type="range" min={0} max={horizonMax} step={1} value={liveYears}
                       onChange={(e) => setLiveYears(+e.target.value)} />
              </div>

              <div className="banner" style={{ marginTop: 8 }}>
                This is an <b>exploratory</b> run at default operating parameters. It is
                <b> not stored</b> and carries no provenance. Register the location below
                to choose the operation and produce an auditable, reproducible run.
              </div>

              <button className="btn primary block" disabled={predict.isPending}
                      onClick={() => predict.mutate()}>
                {predict.isPending ? "Solving transport…" : "Run on this pin"}
              </button>
              <ErrorNote error={predict.error} />
            </>
          )}

          {live && (
            <RunResult r={live} extrapolation={live.extrapolation ?? []} compact />
          )}

          {pinInfo.data && (
            <RegisterForm lon={pin.lon} lat={pin.lat}
                          onRegistered={(s) => openSite(s)} />
          )}
        </aside>
      )}

      {/* ── drawer: SITE mode ── */}
      {mode === "site" && site && (
        <aside className="drawer wide">
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">{site.name}</div>
              <div className="dh-sub">
                Registered site · <span className="chip warn">Hypothetical</span>
              </div>
            </div>
            <button className="btn ghost" onClick={closeDrawer}>Close</button>
          </div>

          <div className="sec">The operation — fixed for this site</div>
          <dl className="kv">
            <dt>Injection rate</dt><dd>{fmt(site.injection_rate_m3_day, 0)} m³/day</dd>
            <dt>Bleed</dt><dd>{fmt(site.bleed_percent, 2)} %</dd>
            <dt>Operation</dt><dd>{fmt(site.operation_years, 0)} yr</dd>
            <dt>Footprint ⌀</dt><dd>{fmt(site.wellfield_width_m, 0)} m</dd>
            <dt>Monitor ring</dt><dd>{fmt(site.monitor_ring_m, 0)} m</dd>
            <dt>Ore depth</dt><dd>{fmt(site.ore_depth_m, 0)} m</dd>
            <dt>Ore thickness</dt><dd>{fmt(site.ore_thickness_m, 0)} m</dd>
          </dl>
          <div className="muted small">
            These are properties of the site, not of a run. Changing them means editing
            the site — an audited write — so that two people opening it are always
            running the same operation.
          </div>

          <div className="sec">What this run varies</div>
          <div className="seg seg-sm">
            {SPECIES.map((s) => (
              <button key={s} className={species === s ? "active" : ""}
                      onClick={() => setSpecies(s)}>{SPECIES_NAME[s]}</button>
            ))}
          </div>

          <div className="slider">
            <label>Evaluation horizon <span className="u">yr</span><b>{runYears}</b></label>
            <input type="range" min={0} max={horizonMax} step={1} value={runYears}
                   onChange={(e) => setRunYears(+e.target.value)} />
          </div>
          <div className="slider">
            <label>Restoration sweep <span className="u">yr</span><b>{runRestoration}</b></label>
            <input type="range" min={0} max={restMax} step={1} value={runRestoration}
                   onChange={(e) => setRunRestoration(+e.target.value)} />
          </div>
          {(horizonTrained !== undefined && runYears > horizonTrained) ||
           (restTrained !== undefined && runRestoration > restTrained) ? (
            <div className="banner warn">
              Past the model's trained range. The analytical engine still serves here and
              the result is <b>flagged, not refused</b> — the ML band's conformal
              guarantee does not hold beyond it.
            </div>
          ) : null}

          {canRunSim(me?.role) ? (
            <>
              <button className="btn primary block" disabled={startRun.isPending}
                      onClick={() => startRun.mutate()}>
                {startRun.isPending ? "Queueing…" : "Run and store"}
              </button>
              <div className="muted small" style={{ marginTop: 6 }}>
                Queued and executed server-side (5–15 s), then pinned to the model card,
                artifact bundle and code version that produced it.
              </div>
            </>
          ) : (
            <div className="muted small">
              Your role can read stored results but not start runs.
            </div>
          )}
          <ErrorNote error={startRun.error} />

          {/* ── the sweep: a shape question, not a point question ── */}
          <div className="sec">Answer a shape question</div>
          <div className="seg seg-sm">
            <button className={sweepAxis === "restoration" ? "active" : ""}
                    onClick={() => { setSweepAxis("restoration"); sweep.reset(); }}>
              How much restoration?</button>
            <button className={sweepAxis === "evaluation" ? "active" : ""}
                    onClick={() => { setSweepAxis("evaluation"); sweep.reset(); }}>
              How does it change over time?</button>
          </div>
          <div className="muted small" style={{ margin: "7px 0" }}>
            {sweepAxis === "restoration"
              ? <>Sweeps the restoration length from 0 to {restMax} yr, holding the
                  evaluation horizon at <b>{runYears} yr</b>, and marks the shortest
                  sweep at which nothing remains above the screening limit.</>
              : <>Sweeps the evaluation horizon from 0 to {horizonMax} yr, holding the
                  restoration sweep at <b>{runRestoration} yr</b>, so you can see how
                  the footprint develops rather than reading one year of it.</>}
          </div>
          <button className="btn block" disabled={sweep.isPending}
                  onClick={() => sweep.mutate(sweepAxis)}>
            {sweep.isPending ? "Solving 6 points…" : "Plot the curve"}
          </button>
          <ErrorNote error={sweep.error} />
          {sweep.data && sweep.data.axis === sweepAxis && (
            <div style={{ marginTop: 10 }}>
              <SweepChart
                sweep={sweep.data}
                picked={sweepAxis === "restoration" ? runRestoration : runYears}
                onPick={(v) => {
                  // Clicking a point loads it into the run controls, so the
                  // curve is a way to CHOOSE the run worth storing rather than
                  // a picture to look at and retype from.
                  if (sweepAxis === "restoration") setRunRestoration(v);
                  else setRunYears(v);
                }}
              />
            </div>
          )}

          {activeRun && activeRun.status !== "completed" && (
            <div className="banner" style={{ marginTop: 10 }}>
              <span className="spinner" /> Run is <strong>{activeRun.status}</strong> — the
              engine is solving transport on a 200² grid.
            </div>
          )}
          {activeRun?.error_message && (
            <div className="banner danger" style={{ marginTop: 10 }}>{activeRun.error_message}</div>
          )}
          {activeRun?.sync_note && (
            <div className="banner warn" style={{ marginTop: 10 }}>{activeRun.sync_note}</div>
          )}

          {activeRun?.status === "completed" && storedPlume && (
            <>
              <RunResult r={storedPlume} extrapolation={activeRun.extrapolation ?? []} />
              <div className="sec">Provenance — how to re-derive this number</div>
              <dl className="kv">
                <dt>Run id</dt><dd className="mono">{activeRun.id.slice(0, 18)}…</dd>
                <dt>Model card</dt><dd className="mono">{activeRun.model_card_sha?.slice(0, 18)}…</dd>
                <dt>Artifacts</dt><dd className="mono">{activeRun.artifacts_sha?.slice(0, 18)}…</dd>
                <dt>Code version</dt><dd className="mono">{activeRun.code_version?.slice(0, 12)}</dd>
                <dt>Runtime</dt>
                <dd>{activeRun.runtime_ms ? `${(activeRun.runtime_ms / 1000).toFixed(1)} s` : "–"}</dd>
                <dt>Completed</dt>
                <dd>{activeRun.completed_at ? new Date(activeRun.completed_at).toLocaleString() : "–"}</dd>
              </dl>
              <ProposeAdvisory run={activeRun} />
            </>
          )}

          {/* A completed run with no geometry has two distinct causes and the
              reader is entitled to know which. */}
          {activeRun?.status === "completed" && !storedPlume && (
            <div className="banner warn" style={{ marginTop: 10 }}>
              <strong>No plume drawn for this run.</strong> Either it completed before
              geometry was stored with runs, or the engine produced no extent at all —
              which outside an ore zone is the correct answer, not a failure. Re-run to
              get a drawable result.
            </div>
          )}

          <div className="sec">Run history</div>
          {runs.isLoading && <Loading />}
          {runs.data?.length === 0 && <div className="muted small">No runs for this site yet.</div>}
          <div className="table-scroll">
            <table className="grid">
              <tbody>
                {runs.data?.map((r) => (
                  <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => setRunId(r.id)}>
                    <td>{SPECIES_NAME[r.species] ?? r.species.replace(/_/g, " ")}</td>
                    <td className="muted small">{new Date(r.created_at).toLocaleString()}</td>
                    <td>
                      {(r.extrapolation?.length ?? 0) > 0 &&
                        <span className="chip warn">extrapolating</span>}
                    </td>
                    <td>
                      <span className={`chip ${r.status === "completed" ? "ok"
                        : r.status === "failed" ? "danger" : "warn"}`}>{r.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </aside>
      )}

      {/* ── drawer: district ── */}
      {mode === "none" && sel && (
        <aside className="drawer">
          <div className="sheet-grip" />
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
            <dt>Band</dt><dd><RiskBand value={selRisk?.max_uranium_ppb} /></dd>
          </dl>
          <div className="muted small">Measurements from CGWB sampling. Not model output.</div>
        </aside>
      )}
    </div>
  );
}
