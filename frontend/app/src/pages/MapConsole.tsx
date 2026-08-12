import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useQuery } from "@tanstack/react-query";
import { api, type District, type IsrPoint, type ObservationMap } from "../api/client";
import { isStaff, useAuth } from "../auth";

/** Jharkhand, from the real district extent. */
const CENTRE: [number, number] = [23.6, 85.3];

type LayerKey =
  | "districts"
  | "isr"
  | "obsPending"
  | "obsAmber"
  | "obsGreen";

const LAYER_META: Array<{ key: LayerKey; label: string; colour: string }> = [
  { key: "districts", label: "Districts", colour: "#14a1a6" },
  { key: "isr", label: "ISR Sites (hypothetical) ◆", colour: "#F59E0B" },
  // The three states §4.4b requires. Listed separately, never merged.
  { key: "obsGreen", label: "Ore · in model", colour: "#16A34A" },
  { key: "obsAmber", label: "Ore · pending sync", colour: "#F59E0B" },
  { key: "obsPending", label: "Observations · pending review", colour: "#DC2626" },
];

function riskBand(v: number | null): { label: string; cls: string } {
  if (v === null || v === undefined) return { label: "no data", cls: "none" };
  if (v >= 0.75) return { label: "critical", cls: "critical" };
  if (v >= 0.5) return { label: "high", cls: "high" };
  if (v >= 0.25) return { label: "medium", cls: "medium" };
  return { label: "low", cls: "low" };
}

export default function MapConsole() {
  const { me } = useAuth();
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const groups = useRef<Record<LayerKey, L.LayerGroup>>({} as never);

  const [on, setOn] = useState<Record<LayerKey, boolean>>({
    districts: true,
    isr: true,
    obsGreen: true,
    obsAmber: true,
    obsPending: true,
  });
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<District | null>(null);
  const [zoom, setZoom] = useState(7);

  const districts = useQuery({
    queryKey: ["districts"],
    queryFn: () => api.get<District[]>("/districts"),
  });
  const geo = useQuery({
    queryKey: ["districts-geojson"],
    queryFn: () => api.get<GeoJSON.FeatureCollection>("/districts/geojson"),
  });
  const sites = useQuery({
    queryKey: ["isr-points"],
    queryFn: () => api.get<IsrPoint[]>("/isr-points"),
    enabled: isStaff(me?.role),
  });
  const obs = useQuery({
    queryKey: ["obs-map"],
    queryFn: () => api.get<ObservationMap>("/field-observations/map"),
    enabled: isStaff(me?.role),
  });

  // ── map init ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;
    const map = L.map(mapEl.current, { center: CENTRE, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(map);
    // Deliberately no raster basemap: the dark canvas from the established
    // design (--bg-map) is the backdrop, and a tile layer would fight the
    // green→amber→red risk ramp the whole console is read through.
    map.on("zoomend", () => setZoom(map.getZoom()));
    mapRef.current = map;
    (Object.keys(on) as LayerKey[]).forEach((k) => {
      groups.current[k] = L.layerGroup().addTo(map);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── districts ──────────────────────────────────────────────────────
  useEffect(() => {
    const g = groups.current.districts;
    if (!g || !geo.data) return;
    g.clearLayers();
    const byName = new Map(districts.data?.map((d) => [d.name, d]) ?? []);
    L.geoJSON(geo.data, {
      style: (f) => {
        const d = byName.get((f?.properties as { name?: string })?.name ?? "");
        const band = riskBand(d?.vulnerability_index ?? null);
        const stroke =
          { critical: "#DC2626", high: "#f97316", medium: "#F59E0B", low: "#16A34A", none: "#475569" }[
            band.cls
          ] ?? "#475569";
        return { color: stroke, weight: 1.4, fillColor: stroke, fillOpacity: 0.10 };
      },
      onEachFeature: (f, layer) => {
        const name = (f.properties as { name?: string })?.name ?? "District";
        const d = byName.get(name);
        const band = riskBand(d?.vulnerability_index ?? null);
        layer.bindTooltip(`${name} — ${band.label}`, { sticky: true });
        layer.on("click", () => d && setSelected(d));
      },
    }).addTo(g);
  }, [geo.data, districts.data]);

  // ── hypothetical ISR sites ─────────────────────────────────────────
  useEffect(() => {
    const g = groups.current.isr;
    if (!g || !sites.data) return;
    g.clearLayers();
    for (const s of sites.data) {
      const c = s.location?.coordinates;
      if (!c) continue;
      // A DIAMOND, not a circle. Amber is reserved for the "approved, pending
      // sync" observation state (§4.4b), and the original design already drew
      // ISR injection points as diamonds — so shape carries the distinction and
      // the two never read as the same thing on the map.
      L.marker([c[1], c[0]], {
        icon: L.divIcon({
          className: "isr-diamond-wrap",
          html: '<div class="isr-diamond"></div>',
          iconSize: [16, 16],
          iconAnchor: [8, 8],
        }),
      })
        .bindTooltip(`${s.name} — HYPOTHETICAL`, { direction: "top" })
        .addTo(g);
    }
  }, [sites.data]);

  // ── field observations, one layer per state ────────────────────────
  useEffect(() => {
    if (!obs.data || !groups.current.obsGreen) return;
    const paint = (
      key: LayerKey,
      items: Array<{ lon: number | null; lat: number | null; name?: string }>,
      colour: string,
      dashed: boolean,
      note: string,
    ) => {
      const g = groups.current[key];
      g.clearLayers();
      for (const it of items) {
        if (it.lon == null || it.lat == null) continue;
        L.circleMarker([it.lat, it.lon], {
          radius: 7,
          color: colour,
          weight: 2,
          // Pending review is hollow and dashed: it is not data yet.
          fillOpacity: dashed ? 0 : 0.6,
          dashArray: dashed ? "3 3" : undefined,
          fillColor: colour,
        })
          .bindTooltip(`${it.name ?? "Observation"} — ${note}`, { direction: "top" })
          .addTo(g);
      }
    };
    paint("obsGreen", obs.data.approved_in_model, "#16A34A", false, "approved, in model");
    paint(
      "obsAmber",
      obs.data.approved_pending_sync,
      "#F59E0B",
      false,
      "approved — NOT yet in the model",
    );
    paint("obsPending", obs.data.pending_review, "#DC2626", true, "pending review");
  }, [obs.data]);

  // ── layer toggles ──────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    (Object.keys(on) as LayerKey[]).forEach((k) => {
      const g = groups.current[k];
      if (!g) return;
      if (on[k]) g.addTo(map);
      else map.removeLayer(g);
    });
  }, [on]);

  const filtered = useMemo(() => {
    const list = districts.data ?? [];
    const q = search.trim().toLowerCase();
    return q ? list.filter((d) => d.name.toLowerCase().includes(q)) : list;
  }, [districts.data, search]);

  return (
    <>
      <aside className="rail">
        <div className="rail-search">
          <input
            placeholder="Search districts…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="rail-section-label">Layers</div>
        <div className="layers">
          {LAYER_META.map((l) => (
            <div className="layer-row" key={l.key}>
              <button
                className="toggle"
                data-on={on[l.key]}
                aria-label={`Toggle ${l.label}`}
                onClick={() => setOn((s) => ({ ...s, [l.key]: !s[l.key] }))}
              />
              <span className="swatch" style={{ background: l.colour }} />
              <span>{l.label}</span>
            </div>
          ))}
        </div>

        <div className="rail-section-label">
          Districts {districts.data ? `(${filtered.length})` : ""}
        </div>
        <div className="rail-list">
          {districts.isLoading && (
            <div style={{ padding: "var(--sp-4)" }} className="muted">
              <span className="spinner" /> Loading…
            </div>
          )}
          {filtered.map((d) => {
            const band = riskBand(d.vulnerability_index);
            return (
              <div
                key={d.id}
                className={`rail-item ${selected?.id === d.id ? "selected" : ""}`}
                onClick={() => setSelected(d)}
              >
                <div>
                  <div className="rail-item-name">{d.name}</div>
                  <div className="rail-item-meta">
                    {d.vulnerability_index === null
                      ? "no vulnerability index"
                      : `index ${d.vulnerability_index.toFixed(2)}`}
                  </div>
                </div>
                <span className={`badge ${band.cls}`}>{band.label}</span>
              </div>
            );
          })}
        </div>
      </aside>

      <div className="map-wrap">
        <div className="map" ref={mapEl} />

        {/* §4.5 rule 6 — the premise is never more than one glance away. */}
        <div className="hypothetical-ribbon">Hypothetical ISR scenarios</div>

        <div className="map-overlay legend">
          <h4>Legend</h4>
          {LAYER_META.map((l) => (
            <div className="legend-row" key={l.key}>
              <span className="swatch" style={{ background: l.colour }} />
              <span>{l.label}</span>
            </div>
          ))}
          <div className="legend-divider" />
          <div style={{ fontSize: "var(--text-xs)", color: "var(--slate-400)", lineHeight: 1.45 }}>
            🟡 approved but not yet in <span className="mono">Datasets/</span> — a
            simulation does not use it yet.
          </div>
        </div>

        <div className="map-overlay status-strip">
          Zoom {zoom} · Jharkhand, India
          {obs.data ? ` · ${obs.data.counts.pending_review} pending review` : ""}
        </div>
      </div>

      {selected && (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <h2 style={{ margin: 0, fontSize: "var(--text-xl)" }}>{selected.name}</h2>
              <div className="muted">District</div>
            </div>
            <button className="linkish" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          <div className="drawer-body">
            <dl className="kv">
              <dt>Vulnerability index</dt>
              <dd>
                {selected.vulnerability_index === null ? (
                  <span className="muted">not computed</span>
                ) : (
                  selected.vulnerability_index.toFixed(3)
                )}
              </dd>
              <dt>Risk band</dt>
              <dd>
                <span className={`badge ${riskBand(selected.vulnerability_index).cls}`}>
                  {riskBand(selected.vulnerability_index).label}
                </span>
              </dd>
              <dt>District id</dt>
              <dd className="mono">{selected.id}</dd>
            </dl>
          </div>
        </aside>
      )}
    </>
  );
}
