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
  type Lifecycle, type LiveRun, type ObservationMap, type PinInfo, type PreviewRun,
  type PublicDistrictRisk, type SimRun, type DeletionImpact,
} from "../api/client";
import { canAdmin, canRunSim, useAuth } from "../auth";
import { ErrorNote, Loading, RiskBand, bandOf } from "../components/bits";
import { FloatingPanel, useResizableWidth } from "../components/panels";
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
import SiteEditForm from "../console/SiteEditForm";
import RunResult from "../console/RunResult";
import SweepChart, { type Sweep } from "../console/SweepChart";
import ProposeAdvisory from "../console/ProposeAdvisory";
import PublishFromPreview from "../console/PublishFromPreview";
import LifecycleChart, { LifecycleNarrative } from "../console/LifecycleChart";

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
  /** PUT /isr-points/{id} existed with no caller: a site could be created
   *  and deleted but never corrected, so fixing a typo meant a cascading
   *  delete of every run filed against it. */
  const [editingSite, setEditingSite] = useState(false);

  /**
   * WHAT A MAP CLICK MEANS — R10.
   *
   * This used to be implicit and got it wrong everywhere outside the ore belt.
   * The `districts` layer is on by default and its polygons tile the whole
   * state, and its click handler called `L.DomEvent.stop`, so the map's own
   * click handler — the one that drops an ISR pin — never fired. Inside the
   * belt the `ore` polygons happen to render on top and do NOT stop
   * propagation, so a pin dropped there and nowhere else. The symptom read as
   * "the engine only works in the belt"; the engine was never the limit.
   *
   * Now the meaning of a click is explicit and the user owns it. ISR is the
   * default, so any point in Jharkhand is usable as a hypothetical location,
   * belt or not. Exactly one drawer is ever open.
   */
  const [mapMode, setMapMode] = useState<"isr" | "district">("isr");
  // Leaflet handlers are bound once per layer build; a ref lets them read the
  // current mode without rebuilding every polygon on each toggle.
  const mapModeRef = useRef(mapMode);
  mapModeRef.current = mapMode;

  const [drawerHidden, setDrawerHidden] = useState(false);
  const rail = useResizableWidth("console.rail",
    { min: 240, max: 560, initial: 340, edge: "right" });
  // The drawer holds the lifecycle chart and the restoration sweep, and 720 px
  // was too narrow to read either properly — the sweep in particular is a curve
  // whose whole point is the shape and where it crosses the limit. The cap is
  // now most of a wide screen, so the plots can be pulled out to a size worth
  // looking at and dragged back when the map matters more.
  const drawer = useResizableWidth("console.drawer",
    { min: 320, max: 1100, initial: 420, edge: "left" });

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
  //
  // R5: a run is EPHEMERAL until somebody chooses to keep it. `preview` holds
  // the unstored result currently on screen; `runId` points at a stored one.
  // Exploring must not fill the run history with results nobody meant to save.
  const [preview, setPreview] = useState<PreviewRun | null>(null);
  const [showStored, setShowStored] = useState(false);

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

  const impact = useQuery({
    queryKey: ["deletion-impact", siteId],
    enabled: !!siteId && mode === "site" && canAdmin(me?.role),
    queryFn: () => api.get<DeletionImpact>(`/isr-points/${siteId}/deletion-impact`),
  });
  const delSite = useMutation({
    mutationFn: (id: string) =>
      api.del<{ message: string }>(`/isr-points/${id}?dry_run=false&confirm=DELETE`),
    onSuccess: () => {
      closeDrawer();
      qc.invalidateQueries({ queryKey: ["isr-points"] });
      qc.invalidateQueries({ queryKey: ["sites"] });
    },
  });

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
    if (!showStored) return null;
    const list = runs.data ?? [];
    return list.find((r) => r.id === runId) ?? list[0] ?? null;
  }, [runs.data, runId, showStored]);

  const predict = useMutation({
    mutationFn: () => api.post<LiveRun>("/ml/predict", {
      lon: pin!.lon, lat: pin!.lat, species,
      time_years: liveYears, mode: showBands ? "both" : "analytical",
    }),
    onSuccess: (r) => setLive(r),
  });

  /** Run it and look at it. Stores nothing — synchronous, because the engine
   *  solves in ~0.26 s and there is nothing worth queueing. */
  const runPreview = useMutation({
    mutationFn: () => api.post<PreviewRun>(`/simulations/${siteId}/preview`, {
      species, time_years: runYears, restoration_years: runRestoration,
    }),
    onSuccess: (r) => { setPreview(r); setShowStored(false); setRunId(null); },
  });

  /** The deliberate act of keeping one. This is where the model card, artifact
   *  bundle and code version get pinned — they only mean something for a result
   *  somebody chose to stand behind. */
  const saveRun = useMutation({
    mutationFn: () => api.post<SimRun>(`/simulations/${siteId}`, {
      species, time_years: runYears, restoration_years: runRestoration,
    }),
    onSuccess: (r) => {
      setRunId(r.id); setShowStored(true);
      qc.invalidateQueries({ queryKey: ["runs", siteId] });
    },
  });

  /** The whole-lifecycle trace: what happens over time at fixed inputs. */
  const lifecycle = useMutation({
    mutationFn: () => api.post<Lifecycle>(`/simulations/${siteId}/lifecycle`, {
      time_years: runYears, restoration_years: runRestoration, points: 12,
    }),
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
    mutationFn: (axis: "restoration") =>
      api.post<Sweep>(`/simulations/${siteId}/sweep`, {
        axis, species, points: 6, time_years: runYears,
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
      if (mapModeRef.current !== "isr") return;   // district mode: clicks mean districts
      const { lat, lng } = e.latlng;
      setPin({ lon: +lng.toFixed(5), lat: +lat.toFixed(5) });
      setMode("pin");
      setLive(null);
      setSiteId("");
      // One drawer at a time. A district selected earlier must not leave a
      // second column standing beside the pin.
      setSel(null);
      setDrawerHidden(false);
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
          // In ISR mode the click is DELIBERATELY allowed to bubble to the map,
          // which is what drops the pin. Swallowing it here unconditionally is
          // what made every point outside the ore belt unusable.
          if (mapModeRef.current !== "district") return;
          L.DomEvent.stop(ev as any);
          const d = districts.data?.find((x) => x.name === name);
          if (d) { setSel(d); setMode("none"); setDrawerHidden(false); }
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
        // Same contract as the district layer: in ISR mode the click belongs to
        // the map, so a block polygon must not swallow it either.
        layer.on("click", (ev) => {
          if (mapModeRef.current !== "district") return;
          L.DomEvent.stop(ev as any);
          const d = districts.data?.find((x) => x.name === p.district);
          if (d) { setSel(d); setMode("none"); setDrawerHidden(false); }
        });
      },
    }).addTo(g);
  }, [blocks.data, on.blocks, districts.data]);

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

  // ── field observations: only what is actually in the model ──
  //
  // R11. This drew three states: approved-and-synced (green), approved-but-not-
  // synced (amber), and pending review (red). The amber and red layers existed
  // to make the portal-vs-engine lag visible, which was the right instinct
  // applied in the wrong place — a marker on the map reads as "the engine knows
  // about this", and for those two states it did not. Someone reading a plume
  // beside an amber dot would reasonably assume the dot informed it.
  //
  // The map now shows **only what is in `Datasets/`**, so what is drawn is what
  // the engine used. The lag has not been hidden: it moved to where it can be
  // acted on — the sync pill in the header, Data & Gaps, and the Dataset
  // Manager, all of which report the count and offer the sync. That keeps the
  // "no data is a monitoring gap, never a clean result" rule intact, because the
  // gap is still reported; it is simply no longer reported as model input.
  useEffect(() => {
    if (!obs.data || !groups.current.green) return;
    const g = groups.current.green;
    g.clearLayers();
    for (const it of obs.data.approved_in_model ?? []) {
      if (it.lon == null || it.lat == null) continue;
      L.circleMarker([it.lat, it.lon], {
        radius: 7, color: "#37d39b", weight: 2, fillColor: "#37d39b",
        fillOpacity: 0.55,
      }).bindTooltip(`${it.name ?? "Observation"} — approved · in model`,
                     { direction: "top" }).addTo(g);
    }
    // The other two groups stay registered so the layer plumbing is unchanged,
    // but nothing is painted into them.
    groups.current.amber?.clearLayers();
    groups.current.red?.clearLayers();
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
  const previewPlume = useMemo(
    () => (preview ? storedRunToPlume(preview) : null), [preview]);

  useEffect(() => {
    const g = plumeGroup.current;
    if (!g) return;
    // One renderer, three sources: an unregistered pin, an unstored preview,
    // and a stored run. They must never look different from each other, because
    // a visual difference would read as a physics difference.
    const r = mode === "pin" ? live
      : mode === "site" ? (showStored ? storedPlume : previewPlume)
      : null;
    if (!r) { g.clearLayers(); return; }
    drawPlume(g, r, showBands);
  }, [mode, live, storedPlume, previewPlume, showStored, showBands]);

  // The direction the plume travels, drawn on the map. The engine has always
  // returned `azimuth_deg`; the portal showed it as a number for an
  // unregistered pin only, and never as the arrow the ml_pipeline dashboard
  // draws — so "which way does this go" was unanswerable from the map itself.
  useEffect(() => {
    const g = plumeGroup.current;
    const m = map.current;
    if (!g || !m) return;
    const shown: any = mode === "pin" ? live
      : mode === "site" ? (showStored ? storedPlume : preview) : null;
    const az = shown?.azimuth_deg;
    const coords = mode === "site"
      ? site?.location?.coordinates
      : pin ? [pin.lon, pin.lat] : null;
    if (az == null || !coords) return;
    // Scaled to the drawn extent so the arrow reads as "this way, this far"
    // rather than a fixed decoration.
    const reach = Math.max(Number(shown?.plume?.Xc_m ?? 0), 150);
    drawArrow(g, coords[1], coords[0], Number(az), "#2bb3ff",
              Math.min(0.03, Math.max(0.004, reach / 111_000 * 1.6)));
  }, [mode, live, storedPlume, preview, showStored, site, pin]);

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
    setDrawerHidden(false);
    setPin(null);
    setLive(null);
    pinMarker.current?.remove();
    pinMarker.current = null;
    // A site's own planned sweep is the sensible starting point for the run
    // control; the run can still test a different one without editing the site.
    setRunRestoration(s.restoration_years ?? 0);
    setPreview(null);
    setShowStored(false);
    lifecycle.reset();
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
    // Reaching district detail is a deliberate act: either this rail list, or
    // switching the map into district mode. It is never what a map click means
    // by default.
    setSel(d);
    setMode("none");
    setDrawerHidden(false);
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
      <aside className="rail" style={rail.style}>
        {rail.handle}
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
            : "Running the model is restricted to admin and analyst. "
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
              <RiskBand value={r?.max_uranium_ppb} samples={r?.samples} />
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

        {/* What a map click means. ISR is the default so that any point in
            Jharkhand is usable as a hypothetical location; district detail is
            a deliberate switch, not the thing that happens by accident. */}
        {mayRun && (
          <div className="map-ov modesw">
            <div className="seg seg-sm" role="group" aria-label="What a map click does">
              <button className={mapMode === "isr" ? "active" : ""}
                      onClick={() => setMapMode("isr")}>ISR pin</button>
              <button className={mapMode === "district" ? "active" : ""}
                      onClick={() => { setMapMode("district"); closeDrawer(); }}>
                District
              </button>
            </div>
            <div className="modesw-note">
              {mapMode === "isr"
                ? "Clicking anywhere resolves the hydrogeology there and runs the engine."
                : "Clicking a district or block opens its measured record."}
            </div>
          </div>
        )}

        {drawerHidden && (mode !== "none" || sel) && (
          <button className="drawer-peek" onClick={() => setDrawerHidden(false)}
                  title="Show the panel" aria-label="Show the panel">‹</button>
        )}

        <FloatingPanel storageKey="console.legend" title="Legend">
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
        </FloatingPanel>

        {mayRun && mode === "none" && !sel && mapMode === "isr" && (
          <div className="map-ov hint">
            <b>Click anywhere in Jharkhand</b> to resolve the hydrogeology and run the
            engine there — or click an amber diamond to open a registered site.
          </div>
        )}
      </div>

      {/* ── drawer: PIN mode ── */}
      {mayRun && mode === "pin" && pin && !drawerHidden && (
        <aside className="drawer wide" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">Unregistered pin</div>
              <div className="dh-sub mono">{pin.lat.toFixed(4)} °N, {pin.lon.toFixed(4)} °E</div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={closeDrawer}>Close</button>
            </div>
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
              {/* R1: outside an ore zone the engine refuses a URANIUM source
                  term — but not sulfate or TDS, which still produce a real
                  plume. Flagged before the run so a non-ore pin does not read
                  as a broken map. */}
              {pinInfo.data?.in_ore === false && (
                <div className="banner warn" style={{ marginBottom: 8 }}>
                  <strong>No uranium ore here.</strong> The engine will not invent a
                  uranium source term at this location — that refusal is correct, not a
                  failure. <b>Sulfate and TDS are still modelled</b>: an ISR operation
                  injects lixiviant regardless of what it dissolves, so pick one of
                  those to see how it would spread.
                  {pinInfo.data?.ore_name && (
                    <div className="muted small" style={{ marginTop: 4 }}>
                      Nearest deposit: {pinInfo.data.ore_name}.
                    </div>
                  )}
                </div>
              )}
              <div className="seg seg-sm">
                {SPECIES.map((sp) => {
                  const suppressed = pinInfo.data?.in_ore === false
                    && (sp === "uranium_ppb" || sp === "radium_226_mbq_l");
                  return (
                    <button key={sp} className={species === sp ? "active" : ""}
                            title={suppressed
                              ? "No source term here — the engine will return nothing "
                                + "for this contaminant outside an ore zone."
                              : undefined}
                            style={suppressed ? { opacity: 0.5 } : undefined}
                            onClick={() => setSpecies(sp)}>
                      {SPECIES_NAME[sp]}{suppressed ? " ·" : ""}
                    </button>
                  );
                })}
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
      {mode === "site" && site && !drawerHidden && (
        <aside className="drawer wide" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">{site.name}</div>
              <div className="dh-sub">
                Registered site · <span className="chip warn">Hypothetical</span>
              </div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={closeDrawer}>Close</button>
            </div>
          </div>

          {/* Deleting a site cascades to every stored run and advisory, so the
              impact is fetched and shown BEFORE the button is offered. A site
              with a published advisory is refused by the API outright — that is
              a public statement residents may have acted on, and erasing one by
              deleting its site is not a decision to reach by clicking through a
              dialog. */}
          {canAdmin(me?.role) && (
            <div className="danger-zone" style={{ margin: "8px 0" }}>
              {impact.data && (
                <p className="muted small">
                  Deleting this site would also destroy{" "}
                  <b>{impact.data.simulation_runs} stored run(s)</b> and{" "}
                  <b>{impact.data.advisories} advisory(ies)</b>, including their
                  provenance.
                  {impact.data.blocked_reason && (
                    <><br /><span className="warn-text">{impact.data.blocked_reason}</span></>
                  )}
                </p>
              )}
              <button className="btn ghost danger small"
                disabled={!impact.data?.deletable || delSite.isPending}
                title={impact.data?.deletable
                  ? "Delete this site and everything filed against it"
                  : impact.data?.blocked_reason ?? "Checking…"}
                onClick={() => {
                  const n = impact.data?.simulation_runs ?? 0;
                  if (window.prompt(
                    `Delete ${site.name}?

This also destroys ${n} stored run(s) `
                    + `and their provenance. It cannot be undone.

`
                    + `Type DELETE to confirm.`) === "DELETE") {
                    delSite.mutate(site.id);
                  }
                }}>
                Delete this site
              </button>
            </div>
          )}

          {mayRun && (editingSite ? (
            <SiteEditForm site={site} bounds={bounds.data}
                          onDone={() => setEditingSite(false)} />
          ) : (
            <button className="btn ghost small" style={{ margin: "6px 0" }}
                    onClick={() => setEditingSite(true)}>
              Edit the operation
            </button>
          ))}

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
            {SPECIES.map((sp) => (
              <button key={sp} className={species === sp ? "active" : ""}
                      onClick={() => { setSpecies(sp); setPreview(null); }}>
                {SPECIES_NAME[sp]}
              </button>
            ))}
          </div>
          <div className="muted small" style={{ marginTop: 6 }}>
            Uranium and radium need an ore zone; sulfate and TDS are modelled
            anywhere, because the operation injects lixiviant regardless of what it
            dissolves. The lifecycle trace below covers all four at once.
          </div>

          <div className="slider">
            <label>Evaluation horizon <span className="u">yr</span><b>{runYears}</b></label>
            <input type="range" min={0} max={horizonMax} step={1} value={runYears}
                   onChange={(e) => setRunYears(+e.target.value)} />
          </div>
          <div className="slider">
            <label>Restoration sweep <span className="u">yr</span><b>{runRestoration}</b></label>
            <input type="range" min={0} max={restMax} step={1} value={runRestoration}
                   onChange={(e) => { setRunRestoration(+e.target.value); setPreview(null); }} />
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
              {/* R5: running and KEEPING are different acts.
                  Running freely is how you explore; storing is how you commit
                  to a number. Conflating them filled the run history with
                  results nobody meant to save. */}
              <button className="btn primary block" disabled={runPreview.isPending}
                      onClick={() => runPreview.mutate()}>
                {runPreview.isPending ? "Solving…" : "Run"}
              </button>
              <div className="muted small" style={{ marginTop: 6 }}>
                Runs immediately and is <b>not stored</b>. Run as many as you like —
                nothing enters the record until you save one.
              </div>

              {preview && !showStored && (
                <>
                  <button className="btn block" disabled={saveRun.isPending}
                          onClick={() => saveRun.mutate()}>
                    {saveRun.isPending ? "Saving…" : "Save this run"}
                  </button>
                  <div className="muted small" style={{ marginTop: 6 }}>
                    Saving pins the model card, artifact bundle and code version that
                    produced it, so the number can be re-derived later. Use this to
                    keep a run you are <b>not</b> publishing — publishing saves it
                    for you.
                  </div>

                  {/* R11: publication no longer waits on a separate save.
                      The save still happens — it is done by the publish call —
                      so an advisory still cites a stored, re-derivable run. */}
                  <PublishFromPreview
                    siteId={siteId} species={species}
                    timeYears={runYears} restorationYears={runRestoration}
                    onSaved={(id) => { setRunId(id); setShowStored(true); }} />
                </>
              )}
            </>
          ) : (
            <div className="muted small">
              Your role can read stored results but not start runs.
            </div>
          )}
          <ErrorNote error={runPreview.error} />
          <ErrorNote error={saveRun.error} />

          {preview && !showStored && (
            <>
              <div className="banner" style={{ marginTop: 10 }}>
                <strong>Unsaved run.</strong> {preview.persistence_note}
              </div>
              <RunResult r={preview} extrapolation={preview.extrapolation ?? []} />
            </>
          )}

          {/* ── the lifecycle: what happens over the whole operation ── */}
          <div className="sec">Across the whole operation</div>
          <div className="muted small" style={{ marginBottom: 7 }}>
            Traces every contaminant through <b>{fmt(site.operation_years, 0)} yr</b> of
            injection, <b>{runRestoration} yr</b> of restoration and the remainder of
            the <b>{runYears} yr</b> horizon.
          </div>
          <button className="btn block" disabled={lifecycle.isPending}
                  onClick={() => lifecycle.mutate()}>
            {lifecycle.isPending ? "Tracing all four contaminants…" : "Plot the lifecycle"}
          </button>
          <ErrorNote error={lifecycle.error} />
          {lifecycle.data && (
            <div style={{ marginTop: 10 }}>
              <LifecycleChart data={lifecycle.data} />
              <LifecycleNarrative data={lifecycle.data} />
            </div>
          )}

          {/* ── how much restoration is enough? ──
              The evaluation axis this control used to offer is gone: the
              lifecycle trace above answers "how does it change over time"
              better, with the phases marked. What remains is the question a
              single run genuinely cannot answer — the shortest sweep that
              clears the screening limit. */}
          <div className="sec">How much restoration is enough?</div>
          <div className="muted small" style={{ margin: "7px 0" }}>
            Sweeps the restoration length from 0 to {restMax} yr, holding the
            evaluation horizon at <b>{runYears} yr</b>, and marks the shortest sweep
            at which nothing remains above the screening limit. The answer depends on
            when you look, which is why the horizon is stated rather than assumed.
          </div>
          <button className="btn block" disabled={sweep.isPending}
                  onClick={() => sweep.mutate("restoration")}>
            {sweep.isPending ? "Solving 6 points…" : "Plot the curve"}
          </button>
          <ErrorNote error={sweep.error} />
          {sweep.data && (
            <div style={{ marginTop: 10 }}>
              <SweepChart
                sweep={sweep.data}
                picked={runRestoration}
                onPick={(v) => {
                  // Clicking a point loads it into the run controls, so the
                  // curve is a way to CHOOSE the run worth keeping rather than
                  // a picture to look at and retype from.
                  setRunRestoration(v);
                  setPreview(null);
                }}
              />
            </div>
          )}

          {showStored && activeRun && activeRun.status !== "completed" && (
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
                  <tr key={r.id} style={{ cursor: "pointer" }}
                      onClick={() => { setRunId(r.id); setShowStored(true); }}>
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
      {mode === "none" && sel && !drawerHidden && (
        <aside className="drawer" style={drawer.style}>
          {drawer.handle}
          <div className="sheet-grip" />
          <div className="drawer-head">
            <div>
              <div className="dh-title">{sel.name}</div>
              <div className="dh-sub">District</div>
            </div>
            <div className="row">
              <button className="rail-btn" onClick={() => setDrawerHidden(true)}
                      title="Hide the panel" aria-label="Hide the panel">›</button>
              <button className="btn ghost" onClick={() => setSel(null)}>Close</button>
            </div>
          </div>
          <div className="sec">Measured groundwater</div>
          <dl className="kv">
            <dt>Wells sampled</dt><dd>{selRisk?.wells ?? "–"}</dd>
            <dt>Samples</dt><dd>{selRisk?.samples ?? "–"}</dd>
            <dt>Max uranium</dt>
            <dd>{selRisk?.max_uranium_ppb != null
                  ? `${selRisk.max_uranium_ppb} ppb` : "not analysed"}</dd>
            <dt>Band</dt>
            <dd><RiskBand value={selRisk?.max_uranium_ppb} samples={selRisk?.samples} /></dd>
          </dl>
          {selRisk?.max_uranium_ppb == null && (selRisk?.samples ?? 0) > 0 && (
            <div className="banner warn">
              {selRisk?.samples} sample(s) from this district are in the dataset, but
              none was analysed for uranium. That is a gap in <b>testing</b>, not a
              clean result — and a different gap from a district nobody has visited.
            </div>
          )}
          <div className="muted small" style={{ marginTop: 8 }}>
            Measurements from CGWB sampling. Not model output.
          </div>
        </aside>
      )}
    </div>
  );
}
