/**
 * The operational map.
 *
 * Dark canvas with no raster basemap: the risk ramp is the information here, and
 * tiles would compete with it. Layout follows the ml_pipeline dashboard — a rail
 * of controls, a full-bleed map, overlays pinned to the corners — with the
 * prototype's entity list and detail drawer.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useQuery } from "@tanstack/react-query";
import {
  api, type District, type IsrPoint, type ObservationMap, type PublicDistrictRisk,
} from "../api/client";
import { Loading, bandOf } from "../components/bits";

const CENTRE: [number, number] = [23.6, 85.3];

type Key = "districts" | "isr" | "green" | "amber" | "red" | "wells";

const LAYERS: Array<{ key: Key; label: string; colour: string; shape?: "diamond" }> = [
  { key: "districts", label: "Districts", colour: "#3fb6ff" },
  { key: "isr", label: "ISR sites (hypothetical)", colour: "#ffb84d", shape: "diamond" },
  { key: "wells", label: "Monitoring wells", colour: "#8b97a7" },
  { key: "green", label: "Ore · in model", colour: "#37d39b" },
  { key: "amber", label: "Ore · approved, not in model", colour: "#ffb84d" },
  { key: "red", label: "Observations · pending review", colour: "#ff5a5a" },
];

const RAMP: Record<string, string> = {
  danger: "#ff5a5a", warn: "#ffb84d", ok: "#37d39b", neutral: "#3a465a",
};

export default function MapConsole() {
  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<Record<Key, L.LayerGroup>>({} as never);

  const [on, setOn] = useState<Record<Key, boolean>>({
    districts: true, isr: true, wells: false, green: true, amber: true, red: true,
  });
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<District | null>(null);
  const [zoom, setZoom] = useState(7);
  // The wells endpoint is viewport-scoped (bbox is required, there are thousands
  // of wells), so the query has to follow the map rather than fetch once.
  const [bbox, setBbox] = useState<string | null>(null);

  const districts = useQuery({ queryKey: ["districts"], queryFn: () => api.get<District[]>("/districts") });
  const geo = useQuery({ queryKey: ["districts-geojson"], queryFn: () => api.get<any>("/districts/geojson") });
  const sites = useQuery({ queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points") });
  const obs = useQuery({ queryKey: ["obs-map"], queryFn: () => api.get<ObservationMap>("/field-observations/map") });
  const wells = useQuery({
    queryKey: ["wells", bbox], enabled: on.wells && !!bbox,
    queryFn: () => api.get<any[]>(`/monitoring-wells?bbox=${bbox}&limit=2000`),
  });
  // Measured exceedance is what colours the choropleth — the public risk
  // aggregate, so officials and the public read the same underlying numbers.
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });

  const riskByName = useMemo(() => {
    const m = new Map<string, PublicDistrictRisk>();
    for (const d of risk.data?.districts ?? []) m.set(d.name, d);
    return m;
  }, [risk.data]);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { center: CENTRE, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(m);
    // Round the bbox to 4 dp so a one-pixel pan does not invalidate the query
    // key — the API caches on the same rounding.
    const syncBbox = () => {
      const b = m.getBounds();
      const r = (n: number) => n.toFixed(4);
      setBbox(`${r(b.getWest())},${r(b.getSouth())},${r(b.getEast())},${r(b.getNorth())}`);
    };
    m.on("zoomend", () => { setZoom(m.getZoom()); syncBbox(); });
    m.on("moveend", syncBbox);
    syncBbox();
    map.current = m;
    (Object.keys(on) as Key[]).forEach((k) => { groups.current[k] = L.layerGroup().addTo(m); });
    return () => { m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const g = groups.current.districts;
    if (!g || !geo.data) return;
    g.clearLayers();
    L.geoJSON(geo.data, {
      style: (f) => {
        const r = riskByName.get((f?.properties as any)?.name ?? "");
        const c = RAMP[bandOf(r?.max_uranium_ppb).cls];
        return { color: c, weight: 1.2, fillColor: c, fillOpacity: 0.12 };
      },
      onEachFeature: (f, layer) => {
        const name = (f.properties as any)?.name ?? "District";
        const r = riskByName.get(name);
        layer.bindTooltip(
          `<b>${name}</b><br/>${r ? `${r.wells} wells · max ${r.max_uranium_ppb ?? "–"} ppb` : "no data"}`,
          { sticky: true },
        );
        layer.on("click", () => {
          const d = districts.data?.find((x) => x.name === name);
          if (d) setSel(d);
        });
      },
    }).addTo(g);
  }, [geo.data, riskByName, districts.data]);

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
        icon: L.divIcon({
          className: "isr-pin-wrap", html: '<div class="isr-pin"></div>',
          iconSize: [14, 14], iconAnchor: [7, 7],
        }),
      }).bindTooltip(`${s.name} — HYPOTHETICAL`, { direction: "top" }).addTo(g);
    }
  }, [sites.data]);

  useEffect(() => {
    if (!obs.data || !groups.current.green) return;
    const paint = (k: Key, items: any[], colour: string, hollow: boolean, note: string) => {
      const g = groups.current[k];
      g.clearLayers();
      for (const it of items) {
        if (it.lon == null || it.lat == null) continue;
        L.circleMarker([it.lat, it.lon], {
          radius: 7, color: colour, weight: 2, fillColor: colour,
          fillOpacity: hollow ? 0 : 0.55,
          dashArray: hollow ? "3 3" : undefined,
        }).bindTooltip(`${it.name ?? "Observation"} — ${note}`, { direction: "top" }).addTo(g);
      }
    };
    paint("green", obs.data.approved_in_model, "#37d39b", false, "approved · in model");
    paint("amber", obs.data.approved_pending_sync, "#ffb84d", false, "approved · NOT yet in the model");
    paint("red", obs.data.pending_review, "#ff5a5a", true, "pending review");
  }, [obs.data]);

  useEffect(() => {
    const g = groups.current.wells;
    if (!g) return;
    g.clearLayers();
    if (!on.wells || !wells.data) return;
    for (const w of wells.data) {
      if (w.latitude == null || w.longitude == null) continue;
      L.circleMarker([w.latitude, w.longitude], {
        radius: 2.5, color: "#8b97a7", weight: 1, fillOpacity: 0.6,
      }).bindTooltip(w.name ?? "well", { direction: "top" }).addTo(g);
    }
  }, [wells.data, on.wells]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    (Object.keys(on) as Key[]).forEach((k) => {
      const g = groups.current[k];
      if (!g) return;
      on[k] ? g.addTo(m) : m.removeLayer(g);
    });
  }, [on]);

  const list = useMemo(() => {
    const l = districts.data ?? [];
    const s = q.trim().toLowerCase();
    return s ? l.filter((d) => d.name.toLowerCase().includes(s)) : l;
  }, [districts.data, q]);

  const selRisk = sel ? riskByName.get(sel.name) : undefined;

  return (
    <>
      <aside className="rail">
        <input placeholder="Search districts…" value={q} onChange={(e) => setQ(e.target.value)} />

        <div className="rail-head">Layers</div>
        {LAYERS.map((l) => (
          <div className="layer-row" key={l.key}>
            <button className="toggle" data-on={on[l.key]} aria-label={`Toggle ${l.label}`}
                    onClick={() => setOn((s) => ({ ...s, [l.key]: !s[l.key] }))} />
            <span className={`sw ${l.shape === "diamond" ? "diamond" : ""}`} style={{ background: l.colour }} />
            <span>{l.label}</span>
          </div>
        ))}

        <div className="rail-head">
          Districts {districts.data ? `(${list.length})` : ""}
        </div>
        {districts.isLoading && <Loading />}
        {list.map((d) => {
          const r = riskByName.get(d.name);
          const b = bandOf(r?.max_uranium_ppb);
          return (
            <div key={d.id} className={`list-item ${sel?.id === d.id ? "sel" : ""}`} onClick={() => setSel(d)}>
              <div>
                <div className="nm">{d.name}</div>
                <div className="mt">{r ? `${r.wells} wells · ${r.samples} samples` : "no data"}</div>
              </div>
              <span className={`chip ${b.cls}`}>{b.label.replace(" concern", "")}</span>
            </div>
          );
        })}
      </aside>

      <div className="map-wrap">
        <div className="map" ref={el} />
        <div className="ribbon">Hypothetical ISR scenarios</div>

        <div className="map-ov legend">
          <h5>Legend</h5>
          {LAYERS.map((l) => (
            <div className="legend-row" key={l.key}>
              <span className={`sw ${l.shape === "diamond" ? "diamond" : ""}`} style={{ background: l.colour }} />
              <span>{l.label}</span>
            </div>
          ))}
          <div className="legend-hr" />
          <div className="muted" style={{ fontSize: 10.5, lineHeight: 1.5 }}>
            District fill = highest measured uranium.<br />
            🟡 approved but not yet in <span className="mono">Datasets/</span> — a
            simulation does not use it yet.
          </div>
        </div>

        <div className="map-ov status">
          zoom {zoom} · Jharkhand
          {obs.data ? ` · ${obs.data.counts.pending_review} pending review` : ""}
        </div>
      </div>

      {sel && (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <h2>{sel.name}</h2>
              <div className="muted small">District</div>
            </div>
            <button className="btn ghost" onClick={() => setSel(null)}>Close</button>
          </div>
          <div className="drawer-body">
            <div className="card">
              <div className="card-title">Measured groundwater</div>
              <dl className="kv">
                <dt>Wells sampled</dt><dd>{selRisk?.wells ?? "–"}</dd>
                <dt>Samples</dt><dd>{selRisk?.samples ?? "–"}</dd>
                <dt>Max uranium</dt>
                <dd>{selRisk?.max_uranium_ppb ?? "–"} <span className="muted">ppb</span></dd>
                <dt>Band</dt>
                <dd>
                  <span className={`chip ${bandOf(selRisk?.max_uranium_ppb).cls}`}>
                    {bandOf(selRisk?.max_uranium_ppb).label}
                  </span>
                </dd>
              </dl>
              <div className="muted small" style={{ marginTop: 9 }}>
                Measurements from CGWB sampling. Not model output.
              </div>
            </div>

            <div className="card">
              <div className="card-title">Reference</div>
              <dl className="kv">
                <dt>Vulnerability index</dt>
                <dd>{sel.vulnerability_index ?? <span className="muted">not computed</span>}</dd>
                <dt>District id</dt><dd className="mono">{sel.id}</dd>
              </dl>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
