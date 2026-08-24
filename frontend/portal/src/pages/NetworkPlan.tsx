/**
 * The proposed monitoring network, on one map.
 *
 * The per-block suggestion answers "where in THIS block". A monitoring
 * programme is planned across a district, so this shows the whole proposal at
 * once — every suggested well, over every block that needs one, **drawn on top
 * of the wells that already exist**. A proposal is only judgeable next to what
 * is already there: three new wells look generous until you see the 397 that
 * exist and the 55 of them that have never been analysed for uranium.
 *
 * Two marker vocabularies, deliberately different in shape and not only colour:
 *
 *   dashed + numbered   proposed — does not exist, is a suggestion
 *   solid dot           existing well, filled if it has a uranium result and
 *                       hollow if it has been sampled but never analysed
 *
 * The hollow ones are the point of the whole screen. They are not gaps in
 * coverage — the well is drilled, the round already happens — they are gaps in
 * *analysis*, and they are the cheapest thing on this map to fix.
 */
import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type NetworkPlan } from "../api/client";
import { ErrorNote, Loading, TableScroll } from "../components/bits";
import { canRunSim, useAuth } from "../auth";
import { attachBasemaps, BASEMAP_LABEL, type BasemapKey } from "../map/basemaps";

const CENTRE: [number, number] = [23.4, 85.6];

export default function NetworkPlanPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  //: Registering a well is placing a piece of the monitoring network, which is
  //: the same authority as placing an ISR site — analyst or admin.
  const mayRegister = canRunSim(me?.role);

  const register = useMutation({
    mutationFn: (body: {
      name: string; latitude: number; longitude: number; block_id: string;
    }) => api.post<{ id: string; name: string }>("/monitoring-wells", body),
    onSuccess: () => {
      // The plan ranks blocks by how badly they are OBSERVED, and a new well
      // changes that ranking, so the plan itself has to be refetched.
      qc.invalidateQueries({ queryKey: ["network-plan"] });
      qc.invalidateQueries({ queryKey: ["gap-recommendations"] });
    },
  });

  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const groups = useRef<{ blocks?: L.LayerGroup; proposed?: L.LayerGroup;
                          existing?: L.LayerGroup }>({});
  const basemapCtl = useRef<{ set: (k: BasemapKey) => void } | null>(null);

  const [top, setTop] = useState(10);
  const [perBlock, setPerBlock] = useState(2);
  const [basemap, setBasemap] = useState<BasemapKey>("light");
  const [showExisting, setShowExisting] = useState(true);
  const [onlyUntested, setOnlyUntested] = useState(false);

  const plan = useQuery({
    queryKey: ["network-plan", top, perBlock],
    queryFn: () => api.get<NetworkPlan>(
      `/data-gaps/network-plan?top=${top}&per_block=${perBlock}`),
  });

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, { center: CENTRE, zoom: 7, zoomControl: false });
    L.control.zoom({ position: "topright" }).addTo(m);
    basemapCtl.current = attachBasemaps(m, "light");
    groups.current.blocks = L.layerGroup().addTo(m);
    groups.current.existing = L.layerGroup().addTo(m);
    groups.current.proposed = L.layerGroup().addTo(m);   // on top
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []);

  useEffect(() => { basemapCtl.current?.set(basemap); }, [basemap]);

  useEffect(() => {
    const m = map.current, g = groups.current;
    if (!m || !g.blocks || !plan.data) return;
    g.blocks.clearLayers();
    g.proposed!.clearLayers();

    const all: L.Layer[] = [];
    plan.data.blocks.forEach((b) => {
      const poly = L.geoJSON(b.geometry as never, {
        style: { color: "#3D7EFF", weight: 1.6, fillOpacity: 0.07, dashArray: "5 4" },
      }).bindTooltip(
        `<b>${b.block}</b> · ${b.district}<br/>priority ${b.score} of 100<br/>`
        + `${b.wells} well(s), ${b.uranium_tests} uranium result(s)`,
        { sticky: true });
      poly.addTo(g.blocks!);
      all.push(poly);

      b.sites.forEach((s) => {
        L.marker([s.lat, s.lon], {
          icon: L.divIcon({
            className: "suggest-pin-wrap",
            html: `<div class="suggest-pin">${s.rank}</div>`,
            iconSize: [22, 22], iconAnchor: [11, 11],
          }),
        }).bindTooltip(
          `<b>Proposed well ${s.rank}</b> — ${b.block}<br/>${s.lat}, ${s.lon}<br/>`
          + `${s.km_to_tested_well} km from the nearest uranium result`,
          { direction: "top" }).addTo(g.proposed!);
      });
    });

    if (all.length) {
      try {
        const fg = L.featureGroup(all as L.Layer[]);
        m.fitBounds(fg.getBounds(), { padding: [30, 30] });
      } catch { /* nothing to fit */ }
    }
    setTimeout(() => m.invalidateSize(), 60);
  }, [plan.data]);

  // Existing wells are a separate effect so toggling them does not redraw the
  // proposal — 397 markers is enough to notice the difference.
  useEffect(() => {
    const g = groups.current.existing;
    if (!g || !plan.data) return;
    g.clearLayers();
    if (!showExisting) return;
    plan.data.existing_wells.forEach((w) => {
      const tested = (w.uranium_tests ?? 0) > 0;
      if (onlyUntested && tested) return;
      L.circleMarker([w.latitude, w.longitude], {
        radius: 4,
        color: tested ? "#8b919c" : "#f5a524",
        weight: tested ? 1 : 2,
        fillColor: tested ? "#8b919c" : "transparent",
        fillOpacity: tested ? 0.8 : 0,
      }).bindTooltip(
        `<b>${w.name}</b>${w.district ? ` · ${w.district}` : ""}<br/>`
        + (tested ? `${w.uranium_tests} uranium result(s)`
                  : `<b>sampled ${w.samples}×, never analysed for uranium</b>`),
        { direction: "top" }).addTo(g);
    });
  }, [plan.data, showExisting, onlyUntested]);

  const untested = (plan.data?.existing_total ?? 0) - (plan.data?.tested_total ?? 0);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Proposed monitoring network</h1>
        <p>
          Every suggested well, over every block that needs one, drawn on top of
          the wells that already exist. Sites maximise distance from the nearest
          existing uranium result — a geometric criterion, not a prediction of
          where contamination is.
        </p>
      </div>

      <div className="row gap wrap" style={{ marginBottom: 10 }}>
        <label className="field" style={{ margin: 0 }}>
          <span>Blocks to plan for</span>
          <select className="input" value={top}
            onChange={(e) => setTop(Number(e.target.value))}>
            {[5, 10, 20, 30].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="field" style={{ margin: 0 }}>
          <span>Wells per block</span>
          <select className="input" value={perBlock}
            onChange={(e) => setPerBlock(Number(e.target.value))}>
            {[1, 2, 3].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={showExisting}
            onChange={(e) => setShowExisting(e.target.checked)} />
          Show the {plan.data?.existing_total ?? 397} existing wells
        </label>
        <label className="check">
          <input type="checkbox" checked={onlyUntested}
            onChange={(e) => setOnlyUntested(e.target.checked)} />
          Only those never analysed for uranium
        </label>
      </div>

      {plan.isLoading && <Loading label="Planning the network…" />}
      {plan.error && <ErrorNote error={plan.error} />}

      <div className="row gap wrap" style={{ margin: "6px 0 10px" }}>
        {(["light", "dark", "satellite"] as BasemapKey[]).map((k) => (
          <button key={k} className={`btn ghost small ${basemap === k ? "sel" : ""}`}
            onClick={() => setBasemap(k)}>{BASEMAP_LABEL[k]}</button>
        ))}
      </div>

      <div ref={el} style={{ height: 520, borderRadius: 8, overflow: "hidden" }} />

      {/* Shape, not colour alone — the same accessibility rule the risk bands follow. */}
      <div className="row gap wrap" style={{ marginTop: 8 }}>
        <span className="muted small">
          <span className="suggest-pin" style={{ display: "inline-block",
            width: 16, height: 16, lineHeight: "12px", fontSize: 10 }}>1</span>
          {" "}proposed well
        </span>
        <span className="muted small">● existing, uranium measured</span>
        <span className="muted small" style={{ color: "#f5a524" }}>
          ○ existing, <b>never analysed for uranium</b>
        </span>
      </div>

      {plan.data && (
        <>
          <div className="grid-4" style={{ marginTop: 12 }}>
            <div className="tile"><b>{plan.data.proposed_total}</b>
              <span>wells proposed</span></div>
            <div className="tile"><b>{plan.data.blocks.length}</b>
              <span>blocks covered</span></div>
            <div className="tile"><b>{plan.data.existing_total}</b>
              <span>wells today</span></div>
            <div className="tile warn"><b>{untested}</b>
              <span>never analysed for uranium</span></div>
          </div>

          <section className="card">
            <h2>The proposal, block by block</h2>
            <TableScroll>
              <table className="grid">
                <thead>
                  <tr><th>Priority</th><th>Block</th><th>District</th>
                    <th>Wells today</th><th>Proposed</th><th>Coordinates</th>
                    {mayRegister && <th />}</tr>
                </thead>
                <tbody>
                  {plan.data.blocks.map((b) => (
                    <tr key={b.block_id}>
                      <td><b>{b.score.toFixed(0)}</b><span className="muted"> /100</span></td>
                      <td>{b.block}</td>
                      <td className="muted small">{b.district}</td>
                      <td className={b.wells === 0 ? "warn-text" : ""}>{b.wells}</td>
                      <td>{b.sites.length}</td>
                      <td className="mono small">
                        {b.sites.map((s) => `${s.lat}, ${s.lon}`).join(" · ")}
                      </td>
                      {/* `POST /monitoring-wells` was implemented and had no
                          caller: the plan could recommend a coordinate and
                          nobody could act on it without curl. This is the one
                          screen where the button belongs, because the
                          coordinate it registers is the one just recommended. */}
                      {mayRegister && (
                        <td>
                          {b.sites.map((s) => (
                            <button key={s.rank} className="btn ghost small"
                              disabled={register.isPending}
                              title={`Register a monitoring well at ${s.lat}, ${s.lon}`}
                              onClick={() => {
                                const name = window.prompt(
                                  `Register a monitoring well at ${s.lat}, ${s.lon} `
                                  + `(${b.block}, ${b.district})?

`
                                  + `This records the well in the portal. It does NOT `
                                  + `drill it, and it does not add any sample — the `
                                  + `block stays a monitoring gap until water is `
                                  + `actually analysed there.

Name for the well:`,
                                  `${b.block} proposed ${s.rank}`);
                                if (name && name.trim()) {
                                  register.mutate({
                                    name: name.trim(), latitude: s.lat,
                                    longitude: s.lon, block_id: b.block_id,
                                  });
                                }
                              }}>
                              Register #{s.rank}
                            </button>
                          ))}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
            <ErrorNote error={register.error} />
            {register.isSuccess && (
              <div className="banner" style={{ marginTop: 10 }}>
                Well registered. It appears on the Console map immediately, and
                this plan has been re-ranked — but the block is still a
                monitoring gap until a sample from it is actually analysed.
              </div>
            )}
            <div className="banner warn" style={{ marginTop: 10 }}>
              <b>Not a survey.</b> {plan.data.caveat}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
