/**
 * The citizen's map.
 *
 * A citizen previously got a dropdown and a table. That is a fine way to read a
 * number and a poor way to answer the question people actually have, which is
 * spatial: *is anyone testing near me, and what did they find?* So they get a
 * real map with real place names, the same three basemaps as staff, and every
 * layer toggleable.
 *
 * WHAT IS DELIBERATELY ABSENT, and why it is not an oversight:
 *
 * * **No ISR sites.** Design §2 forbids the public a precise coordinate for a
 *   *hypothetical* uranium mine. A speculative point beside a named village
 *   gets read as a plan.
 * * **No ore deposits, no plume, no flow or fracture field.** These are model
 *   inputs and model output. This surface reports what was measured.
 * * **No uncertainty bands, no species jargon.** Bands are plain language.
 *
 * What remains is public government reference data: administrative boundaries,
 * CGWB monitoring-well positions, and the measured uranium result at each. A
 * "no data" block is drawn as a monitoring gap, never as a clean result — that
 * distinction is the whole reason this map is worth drawing.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { useQuery } from "@tanstack/react-query";
import { api, type FeatureCollection } from "../api/client";
import { isStaff, useAuth } from "../auth";
import { Loading } from "../components/bits";
import { attachBasemaps, BASEMAP_LABEL, type BasemapKey } from "../map/basemaps";

const CENTRE: [number, number] = [23.6, 85.3];

/** The four public bands, and the one colour vocabulary used for all of them.
 *  Grey for "No data" on purpose: it must not read as green. */
const BAND_COLOUR: Record<string, string> = {
  "High concern": "#e5484d",
  "Moderate concern": "#f5a524",
  "Low concern": "#30a46c",
  "No data": "#8b97a7",
};
const BANDS = ["High concern", "Moderate concern", "Low concern", "No data"];

type Key = "districts" | "blocks" | "wells";

export default function CitizenMap() {
  const { me } = useAuth();
  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<Record<Key, L.LayerGroup>>({} as never);
  const basemapCtl = useRef<{ set: (k: BasemapKey) => void } | null>(null);

  const [on, setOn] = useState<Record<Key, boolean>>({
    districts: true, blocks: false, wells: true,
  });
  const [basemap, setBasemap] = useState<BasemapKey>("light");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Record<string, any> | null>(null);
  const [q, setQ] = useState("");

  const districts = useQuery({
    queryKey: ["pub-geo", "districts"], staleTime: 3_600_000,
    queryFn: () => api.get<FeatureCollection>("/public/risk/geojson/districts"),
  });
  const blocks = useQuery({
    queryKey: ["pub-geo", "blocks"], enabled: on.blocks, staleTime: 3_600_000,
    queryFn: () => api.get<FeatureCollection>("/public/risk/geojson/blocks"),
  });
  const wells = useQuery({
    queryKey: ["pub-geo", "wells"], enabled: on.wells, staleTime: 3_600_000,
    queryFn: () => api.get<FeatureCollection>("/public/risk/geojson/wells"),
  });

  const visible = (band: string) => !hidden.has(band);
  const toggleBand = (b: string) =>
    setHidden((s) => {
      const n = new Set(s);
      n.has(b) ? n.delete(b) : n.add(b);
      return n;
    });

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { center: CENTRE, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(m);
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(m);
    basemapCtl.current = attachBasemaps(m, "light");
    for (const k of ["districts", "blocks", "wells"] as Key[]) {
      groups.current[k] = L.layerGroup().addTo(m);
    }
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => { basemapCtl.current?.set(basemap); }, [basemap]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const k of ["districts", "blocks", "wells"] as Key[]) {
      const g = groups.current[k];
      if (!g) continue;
      if (on[k]) { if (!m.hasLayer(g)) g.addTo(m); }
      else if (m.hasLayer(g)) m.removeLayer(g);
    }
  }, [on]);

  // ── districts ──
  useEffect(() => {
    const g = groups.current.districts;
    if (!g || !districts.data) return;
    g.clearLayers();
    L.geoJSON(districts.data as any, {
      filter: (f) => visible((f.properties as any).band),
      style: (f) => {
        const c = BAND_COLOUR[(f?.properties as any).band] ?? "#8b97a7";
        return { color: c, weight: 1.4, fillColor: c, fillOpacity: 0.22 };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name}</b><br/>${p.wells} well(s) tested · ${p.band}`,
          { sticky: true });
        layer.on("click", () => setSel({ ...p, kind: "District" }));
      },
    }).addTo(g);
  }, [districts.data, hidden]);

  // ── blocks ──
  useEffect(() => {
    const g = groups.current.blocks;
    if (!g) return;
    g.clearLayers();
    if (!on.blocks || !blocks.data) return;
    L.geoJSON(blocks.data as any, {
      filter: (f) => visible((f.properties as any).band),
      style: (f) => {
        const c = BAND_COLOUR[(f?.properties as any).band] ?? "#8b97a7";
        return { color: c, weight: 0.8, fillColor: c, fillOpacity: 0.28 };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name}</b> <span class="muted">${p.district}</span><br/>`
          + `${p.wells} well(s) tested · ${p.band}`, { sticky: true });
        layer.on("click", () => setSel({ ...p, kind: "Block" }));
      },
    }).addTo(g);
  }, [blocks.data, on.blocks, hidden]);

  // ── wells ──
  useEffect(() => {
    const g = groups.current.wells;
    if (!g) return;
    g.clearLayers();
    if (!on.wells || !wells.data) return;
    for (const f of wells.data.features) {
      const p = f.properties as any;
      if (!visible(p.band)) continue;
      const [lon, lat] = f.geometry.coordinates;
      L.circleMarker([lat, lon], {
        radius: 4.5, color: "#ffffff", weight: 1,
        fillColor: BAND_COLOUR[p.band] ?? "#8b97a7", fillOpacity: 0.95,
      }).bindTooltip(
        `<b>${p.name}</b><br/>${p.block ?? "–"}, ${p.district ?? "–"}<br/>`
        + (p.max_uranium_ppb !== null
            ? `highest reading ${p.max_uranium_ppb} ppb — ${p.band}`
            : "no result recorded"),
        { direction: "top" })
       .on("click", () => setSel({ ...p, kind: "Monitoring well" }))
       .addTo(g);
    }
  }, [wells.data, on.wells, hidden]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of districts.data?.features ?? []) {
      const b = (f.properties as any).band;
      c[b] = (c[b] ?? 0) + 1;
    }
    return c;
  }, [districts.data]);

  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    const out: Array<{ name: string; sub: string; band: string; f: any }> = [];
    for (const f of districts.data?.features ?? []) {
      const p = f.properties as any;
      if (p.name.toLowerCase().includes(t)) out.push({ name: p.name, sub: "District", band: p.band, f });
    }
    for (const f of blocks.data?.features ?? []) {
      const p = f.properties as any;
      if (p.name.toLowerCase().includes(t)) out.push({ name: p.name, sub: p.district, band: p.band, f });
    }
    return out.slice(0, 12);
  }, [q, districts.data, blocks.data]);

  const flyTo = (f: any) => {
    if (!map.current) return;
    map.current.fitBounds(L.geoJSON(f).getBounds(), { maxZoom: 11 });
    setSel({ ...(f.properties as any), kind: f.properties.district ? "Block" : "District" });
  };

  return (
    <div className="map-shell">
      <aside className="rail">
        <div className="rail-head">Find your area</div>
        <input placeholder="District or block…" value={q}
               onChange={(e) => {
                 setQ(e.target.value);
                 // Searching a block name is useless if the block layer is off.
                 if (e.target.value.trim() && !on.blocks) setOn((s) => ({ ...s, blocks: true }));
               }} />
        {results.map((r, i) => (
          <div key={i} className="list-item" onClick={() => flyTo(r.f)}>
            <div>
              <div className="nm">{r.name}</div>
              <div className="mt">{r.sub}</div>
            </div>
            <span className="dot" style={{ background: BAND_COLOUR[r.band] }} />
          </div>
        ))}

        <div className="rail-head">Basemap</div>
        <div className="seg seg-sm">
          {(["light", "dark", "satellite"] as BasemapKey[]).map((b) => (
            <button key={b} className={basemap === b ? "active" : ""}
                    onClick={() => setBasemap(b)}>{BASEMAP_LABEL[b]}</button>
          ))}
        </div>

        <div className="rail-head">Show on the map</div>
        {([["districts", "Districts"], ["blocks", "Blocks"], ["wells", "Monitoring wells"]] as const)
          .map(([k, label]) => (
            <div className="layer-row" key={k}>
              <button className="toggle" data-on={on[k]} aria-label={`Toggle ${label}`}
                      onClick={() => setOn((s) => ({ ...s, [k]: !s[k] }))} />
              <span>{label}</span>
            </div>
          ))}

        <div className="rail-head">Result — tap to filter</div>
        {BANDS.map((b) => (
          <div className="layer-row" key={b}>
            <button className="toggle" data-on={!hidden.has(b)} aria-label={`Toggle ${b}`}
                    onClick={() => toggleBand(b)} />
            <span className="sw" style={{ background: BAND_COLOUR[b] }} />
            <span>{b}</span>
            {counts[b] !== undefined && <span className="muted small"> · {counts[b]}</span>}
          </div>
        ))}

        <div className="muted small" style={{ padding: "10px 2px" }}>
          The safe limit for uranium in drinking water is <b>30 ppb</b>. A grey
          area has never been sampled — that is a gap in monitoring, not a clean
          result.
        </div>
      </aside>

      <div className="map-area">
        <div ref={el} className="map-canvas" />
        {districts.isLoading && (
          <div className="map-ov hint"><Loading label="Loading your area…" /></div>
        )}
        <div className="map-ov legend">
          <div className="ov-title">What the colours mean</div>
          {BANDS.filter((b) => !hidden.has(b)).map((b) => (
            <div className="legend-row" key={b}>
              <span className="sw" style={{ background: BAND_COLOUR[b] }} />{b}
            </div>
          ))}
          <div className="muted small" style={{ marginTop: 6 }}>
            Real measurements from government groundwater sampling — not
            predictions from any simulation.
          </div>
        </div>
      </div>

      {sel && (
        <aside className="drawer">
          <div className="drawer-head">
            <div>
              <div className="dh-title">{sel.name}</div>
              <div className="dh-sub">{sel.kind}{sel.district ? ` · ${sel.district}` : ""}</div>
            </div>
            <button className="btn ghost" onClick={() => setSel(null)}>Close</button>
          </div>

          <div className="banner" style={{ background: `${BAND_COLOUR[sel.band]}22`,
                                           borderColor: BAND_COLOUR[sel.band] }}>
            <strong>{sel.band}</strong>
          </div>

          {sel.what_it_means && (
            <div className="muted" style={{ lineHeight: 1.65, marginTop: 8 }}>
              {sel.what_it_means}
            </div>
          )}

          <div className="sec">What was measured</div>
          <dl className="kv">
            {sel.kind !== "Monitoring well" && <><dt>Wells tested</dt><dd>{sel.wells}</dd></>}
            <dt>Samples</dt><dd>{sel.samples}</dd>
            <dt>Highest reading</dt>
            <dd>{sel.max_uranium_ppb !== null && sel.max_uranium_ppb !== undefined
                  ? `${sel.max_uranium_ppb} ppb` : "no result"}</dd>
            {sel.last_sampled && (
              <><dt>Last sampled</dt><dd>{new Date(sel.last_sampled).toLocaleDateString()}</dd></>
            )}
          </dl>

          {sel.band === "High concern" && (
            <div className="banner danger">
              Contact your block water office about testing your own supply.
            </div>
          )}

          <div className="muted small" style={{ marginTop: 10 }}>
            No uranium mine of the type this platform models operates in
            Jharkhand. These are real test results, not predictions.
          </div>
        </aside>
      )}

      {isStaff(me?.role) && (
        <div className="ribbon">
          You are viewing the <b>public map</b> — no ISR sites, ore, plume or model
          output appear here.
        </div>
      )}
    </div>
  );
}
