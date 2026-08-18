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
import { ErrorNote, Loading } from "../components/bits";
import { FloatingPanel, useResizableWidth } from "../components/panels";
import { attachBasemaps, BASEMAP_LABEL, type BasemapKey } from "../map/basemaps";
import { addScaleControl } from "../map/scale";
import { useRail } from "../map/useRail";

const CENTRE: [number, number] = [23.6, 85.3];

/** The four public bands, and the one colour vocabulary used for all of them.
 *  Grey for "No data" on purpose: it must not read as green. */
const BAND_COLOUR: Record<string, string> = {
  "High concern": "#f2555a",
  "Moderate concern": "#f5a524",
  "Low concern": "#3ecf8e",
  "No data": "#8b919c",
};
const BANDS = ["High concern", "Moderate concern", "Low concern", "No data"];

type Key = "districts" | "blocks" | "wells" | "screenings";

export default function CitizenMap() {
  const { me } = useAuth();
  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<Record<Key, L.LayerGroup>>({} as never);
  const basemapCtl = useRef<{ set: (k: BasemapKey) => void } | null>(null);

  const { collapsed, toggle: toggleRail } = useRail(map);
  const [on, setOn] = useState<Record<Key, boolean>>({
    districts: true, blocks: false, wells: true, screenings: true,
  });
  const [screening, setScreening] = useState<Record<string, any> | null>(null);
  const [basemap, setBasemap] = useState<BasemapKey>("light");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [sel, setSel] = useState<Record<string, any> | null>(null);
  const [pin, setPin] = useState<{ lon: number; lat: number } | null>(null);
  const pinMarker = useRef<any>(null);
  const [q, setQ] = useState("");

  /**
   * WHAT A MAP CLICK MEANS, on the citizen surface — R10.
   *
   * Two things live on this map and they answer different questions: *what was
   * measured near me* (districts, blocks, wells) and *what has been assessed
   * near me* (published screening footprints). They were both clickable at
   * once, into two independent pieces of state, and both drawers rendered as
   * flex items — so selecting one of each really did put TWO COLUMNS on
   * screen, which is the reported defect.
   *
   * The mode makes it one question at a time. `area` is the default because
   * this screen exists to answer "is anyone testing near me", and a measured
   * result is the thing a resident can act on. The footprint layer is switched
   * to non-interactive in that mode so a click passes THROUGH it to the block
   * underneath, rather than being silently swallowed by an overlay.
   */
  const [citizenMode, setCitizenMode] = useState<"area" | "assessments">("area");
  const modeRef = useRef(citizenMode);
  modeRef.current = citizenMode;

  const [drawerHidden, setDrawerHidden] = useState(false);
  const rail = useResizableWidth("citizen.rail",
    { min: 240, max: 520, initial: 340, edge: "right" });
  const drawer = useResizableWidth("citizen.drawer",
    { min: 300, max: 640, initial: 460, edge: "left" });

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
  //
  // R8: the footprints of screenings a reviewer has PUBLISHED. Residents could
  // read that an assessment covered their block but had no way to see where —
  // and telling somebody they are in an assessed area while withholding where
  // creates rumour without recourse.
  //
  // The ISR point itself is still absent: design §2 keeps a precise coordinate
  // for a hypothetical mine off the public map, and the footprint already
  // answers "does this reach me?" without planting a pin beside a village.
  const screenings = useQuery({
    queryKey: ["pub-geo", "screenings"], enabled: on.screenings,
    queryFn: () => api.get<FeatureCollection>("/citizen/advisories/geojson"),
  });

  /** What is measured at the tapped point. Measurements only — never a model. */
  const at = useQuery({
    queryKey: ["risk-at", pin?.lon, pin?.lat],
    enabled: !!pin,
    queryFn: () => api.get<any>(
      `/public/risk/at?lon=${pin!.lon.toFixed(5)}&lat=${pin!.lat.toFixed(5)}`),
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
    addScaleControl(m);
    basemapCtl.current = attachBasemaps(m, "light");
    for (const k of ["districts", "blocks", "wells", "screenings"] as Key[]) {
      groups.current[k] = L.layerGroup().addTo(m);
    }
    // ── tap anywhere ──
    //
    // Before this, only a *feature* was clickable: land on open ground, or on a
    // gap between polygons, and nothing happened at all, which reads as a broken
    // map rather than as "no data here". A map-level handler answers the
    // question the resident is actually asking — "what is known about *this
    // spot*" — from measurements only. `GET /public/risk/at` runs no model and
    // returns no site geometry, so tapping cannot be used to discover where a
    // hypothetical operation was placed.
    //
    // Leaflet fires `click` for taps too, and only when no interactive layer
    // consumed the event, so a district click still wins over the pin.
    m.on("click", (e: any) => {
      if (modeRef.current !== "area") return;
      const { lat, lng } = e.latlng;
      setScreening(null);
      setSel(null);
      setDrawerHidden(false);
      setPin({ lon: lng, lat });
    });

    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  // The marker for the tapped point, kept out of the layer groups so a layer
  // toggle cannot orphan it.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    pinMarker.current?.remove();
    pinMarker.current = null;
    if (!pin) return;
    pinMarker.current = L.circleMarker([pin.lat, pin.lon], {
      radius: 7, weight: 2, color: "#3D7EFF", fillColor: "#3D7EFF",
      fillOpacity: 0.55, interactive: false,
    }).addTo(m);
  }, [pin]);

  useEffect(() => { basemapCtl.current?.set(basemap); }, [basemap]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const k of ["districts", "blocks", "wells", "screenings"] as Key[]) {
      const g = groups.current[k];
      if (!g) continue;
      if (on[k]) { if (!m.hasLayer(g)) g.addTo(m); }
      else if (m.hasLayer(g)) m.removeLayer(g);
    }
  }, [on]);

  // ── published screenings ──
  //
  // Drawn ABOVE the choropleths and in a distinct hatched violet, because a
  // resident must never confuse "an assessment was modelled here" with "this
  // area tested badly". Those are the two channels the whole citizen surface
  // keeps apart, and the map is the easiest place to blur them.
  useEffect(() => {
    const g = groups.current.screenings;
    if (!g) return;
    g.clearLayers();
    if (!on.screenings || !screenings.data) return;
    L.geoJSON(screenings.data as any, {
      // Non-interactive in area mode so the block underneath still answers a
      // click. Rebuilt on mode change because `interactive` is fixed at
      // construction — the layer is small enough that this is free.
      interactive: citizenMode === "assessments",
      style: {
        color: "#a78bfa", weight: 2.4, fillColor: "#a78bfa",
        fillOpacity: 0.30, dashArray: "6 4",
      },
      onEachFeature: (f, layer) => {
        const p: any = f.properties ?? {};
        layer.bindTooltip(
          `<b>${p.headline ?? "Published screening"}</b><br/>`
          + `modelled area ${Number(p.footprint_ha ?? 0).toFixed(1)} ha`
          + `<br/><span class="muted">a modelled scenario, not a measurement</span>`,
          { className: "plume-tip", sticky: true });
        layer.on("click", () => { setSel(null); setPin(null); setScreening(p); setDrawerHidden(false); });
      },
    }).addTo(g);
  }, [screenings.data, on.screenings, citizenMode]);

  // ── districts ──
  useEffect(() => {
    const g = groups.current.districts;
    if (!g || !districts.data) return;
    g.clearLayers();
    L.geoJSON(districts.data as any, {
      filter: (f) => visible((f.properties as any).band),
      style: (f) => {
        const c = BAND_COLOUR[(f?.properties as any).band] ?? "#8b919c";
        return { color: c, weight: 1.4, fillColor: c, fillOpacity: 0.22 };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name}</b><br/>${p.wells} well(s) tested · ${p.band}`,
          { sticky: true });
        layer.on("click", () => {
          if (modeRef.current !== "area") return;
          setScreening(null); setPin(null); setSel({ ...p, kind: "District" }); setDrawerHidden(false);
        });
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
        const c = BAND_COLOUR[(f?.properties as any).band] ?? "#8b919c";
        return { color: c, weight: 0.8, fillColor: c, fillOpacity: 0.28 };
      },
      onEachFeature: (f, layer) => {
        const p = f.properties as any;
        layer.bindTooltip(
          `<b>${p.name}</b> <span class="muted">${p.district}</span><br/>`
          + `${p.wells} well(s) tested · ${p.band}`, { sticky: true });
        layer.on("click", () => {
          if (modeRef.current !== "area") return;
          setScreening(null); setSel({ ...p, kind: "Block" }); setDrawerHidden(false);
        });
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
        fillColor: BAND_COLOUR[p.band] ?? "#8b919c", fillOpacity: 0.95,
      }).bindTooltip(
        `<b>${p.name}</b><br/>${p.block ?? "–"}, ${p.district ?? "–"}<br/>`
        + (p.max_uranium_ppb !== null
            ? `highest reading ${p.max_uranium_ppb} ppb — ${p.band}`
            : "no result recorded"),
        { direction: "top" })
       .on("click", () => {
         if (modeRef.current !== "area") return;
         setScreening(null); setSel({ ...p, kind: "Monitoring well" }); setDrawerHidden(false);
       })
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
      {!collapsed && (
      <aside className="rail" style={rail.style}>
        {rail.handle}
        <div className="rail-top">
          <span className="t">Your area</span>
          <button className="rail-btn" onClick={toggleRail}
                  title="Collapse the panel" aria-label="Collapse the panel">‹</button>
        </div>
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
        {([["districts", "Districts"], ["blocks", "Blocks"], ["wells", "Monitoring wells"],
           ["screenings", "Published assessments"]] as const)
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
      )}

      <div className="map-area">
        <div ref={el} className="map-canvas" />

        {collapsed && (
          <button className="rail-peek" onClick={toggleRail}
                  title="Show the panel" aria-label="Show the panel">›</button>
        )}
        {districts.isLoading && (
          <div className="map-ov hint"><Loading label="Loading your area…" /></div>
        )}

        {/* One question at a time. Switching mode closes whatever was open, so
            the two channels can never be on screen together. */}
        <div className="map-ov modesw">
          <div className="seg seg-sm" role="group" aria-label="What a map click shows">
            <button className={citizenMode === "area" ? "active" : ""}
                    onClick={() => { setCitizenMode("area"); setScreening(null); }}>
              Test results
            </button>
            <button className={citizenMode === "assessments" ? "active" : ""}
                    onClick={() => { setCitizenMode("assessments"); setSel(null);
                                     setOn((o) => ({ ...o, screenings: true })); }}>
              Assessments
            </button>
          </div>
          <div className="modesw-note">
            {citizenMode === "area"
              ? "Tap an area or a well to see what was actually measured there."
              : "Tap a shaded area to see the published assessment behind it."}
          </div>
        </div>

        {drawerHidden && (sel || screening || pin) && (
          <button className="drawer-peek" onClick={() => setDrawerHidden(false)}
                  title="Show the panel" aria-label="Show the panel">‹</button>
        )}

        <FloatingPanel storageKey="citizen.legend" title="What the colours mean">
          {on.screenings && (
            <div className="legend-row">
              <span className="sw" style={{ background: "#a78bfa" }} />
              Published assessment (modelled)
            </div>
          )}
          {BANDS.filter((b) => !hidden.has(b)).map((b) => (
            <div className="legend-row" key={b}>
              <span className="sw" style={{ background: BAND_COLOUR[b] }} />{b}
            </div>
          ))}
          <div className="muted small" style={{ marginTop: 6 }}>
            Real measurements from government groundwater sampling — not
            predictions from any simulation.
          </div>
        </FloatingPanel>
      </div>

      {/* EXACTLY ONE DRAWER. `screening` and `sel` are cleared against each
          other at every call site; the ternary is the belt-and-braces so a
          future call site cannot reintroduce the two-column defect. */}
      {screening && !drawerHidden ? (
        <aside className="drawer" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">Published assessment</div>
              <div className="dh-sub">a modelled scenario, not a measurement</div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={() => setScreening(null)}>Close</button>
            </div>
          </div>

          <div className="banner warn" style={{ marginTop: 10 }}>
            {screening.what_this_is}
          </div>

          <div className="sec">What was assessed</div>
          <div className="prose" style={{ fontWeight: 600 }}>{screening.headline}</div>

          <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Modelled area</dt>
            <dd>{Number(screening.footprint_ha ?? 0).toFixed(1)} hectares</dd>
            <dt>Looked ahead</dt>
            <dd>{screening.time_years ?? "–"} years</dd>
            <dt>Clean-up assumed</dt>
            <dd>{screening.restoration_years
              ? `${screening.restoration_years} years`
              : "none"}</dd>
            {screening.published_at && (
              <>
                <dt>Published</dt>
                <dd>{new Date(screening.published_at).toLocaleDateString()}</dd>
              </>
            )}
          </dl>

          <div className="muted small prose" style={{ marginTop: 10 }}>
            The shaded area is how far the model expects contamination to reach if an
            operation of this kind ran here. It is drawn from the assessment a
            reviewer published — not from anything measured in the ground, and not
            from anything that has happened.
          </div>

          <div className="muted small prose" style={{ marginTop: 10 }}>
            The grey dots on this map are different: those are <b>real government
            monitoring wells</b>, and their colour is what was actually tested there.
          </div>
        </aside>
      ) : sel && !drawerHidden ? (
        <aside className="drawer" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">{sel.name}</div>
              <div className="dh-sub">{sel.kind}{sel.district ? ` · ${sel.district}` : ""}</div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={() => setSel(null)}>Close</button>
            </div>
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
      ) : pin && !drawerHidden ? (
        <aside className="drawer" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">
                {at.data?.inside_jharkhand ? at.data.block : "This spot"}
              </div>
              <div className="dh-sub">
                {at.data?.inside_jharkhand
                  ? `${at.data.district} · tapped location`
                  : `${pin.lat.toFixed(4)}, ${pin.lon.toFixed(4)}`}
              </div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={() => setPin(null)}>Close</button>
            </div>
          </div>

          {at.isLoading && <Loading label="Looking up this location…" />}
          {at.error && <ErrorNote error={at.error} />}

          {at.data && !at.data.inside_jharkhand && (
            <div className="muted" style={{ lineHeight: 1.65 }}>{at.data.message}</div>
          )}

          {at.data?.inside_jharkhand && (
            <>
              <div className="banner"
                   style={{ background: `${BAND_COLOUR[at.data.band] ?? "#8b919c"}22`,
                            borderColor: BAND_COLOUR[at.data.band] ?? "#8b919c" }}>
                <strong>{at.data.band}</strong>
              </div>

              <div className="muted" style={{ lineHeight: 1.65, marginTop: 8 }}>
                {at.data.what_it_means}
              </div>

              <div className="sec">What was measured here</div>
              <dl className="kv">
                <dt>Wells</dt><dd>{at.data.wells}</dd>
                <dt>Samples</dt><dd>{at.data.samples}</dd>
                <dt>Tested for uranium</dt><dd>{at.data.uranium_tests}</dd>
                <dt>Highest reading</dt>
                <dd>{at.data.max_uranium_ppb != null
                      ? `${at.data.max_uranium_ppb} ppb` : "no result"}</dd>
                <dt>Safe limit</dt><dd>{at.data.safe_limit} ppb</dd>
              </dl>

              {at.data.nearest_wells?.length > 0 && (
                <>
                  <div className="sec">Nearest monitoring wells</div>
                  <ul className="plain">
                    {at.data.nearest_wells.map((w: any, i: number) => (
                      <li key={i}>
                        <b>{w.name}</b>
                        <span className="muted small">
                          {" "}· {(Number(w.metres) / 1000).toFixed(1)} km
                          {w.uranium_tests > 0
                            ? ` · highest ${w.max_uranium_ppb} ppb`
                            : " · not tested for uranium"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {at.data.advisories?.length > 0 && (
                <>
                  <div className="sec">Published advisories covering this spot</div>
                  <ul className="plain">
                    {at.data.advisories.map((a: any, i: number) => (
                      <li key={i}>{a.headline}</li>
                    ))}
                  </ul>
                </>
              )}

              {at.data.band === "High concern" && (
                <div className="banner danger">
                  Contact your block water office about testing your own supply.
                </div>
              )}
            </>
          )}

          <div className="muted small" style={{ marginTop: 10 }}>
            {at.data?.what_this_is ?? (
              "No uranium mine of the type this platform models operates in "
              + "Jharkhand. These are real test results, not predictions.")}
          </div>
        </aside>
      ) : null}

      {isStaff(me?.role) && (
        <div className="ribbon">
          You are viewing the <b>public map</b> — no ISR sites, ore, plume or model
          output appear here.
        </div>
      )}
    </div>
  );
}
