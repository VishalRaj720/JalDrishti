/**
 * The full ISR report — every parameter, every contaminant, one document.
 *
 * R6. The Publications screen used to show a headline, some prose, a block
 * overlap and six numbers about uranium. That is a summary of a decision, not a
 * description of what was assessed, and it left the reader unable to answer the
 * obvious follow-ups: what were the operating parameters? what about sulfate?
 * does it reach the shallow aquifer? what happens after year 20?
 *
 * This is that document. Two inputs are deliberately left live —
 * **evaluation horizon** (default 50 yr) and **restoration sweep** (default 0
 * yr) — because those are the two questions a reader legitimately re-asks of a
 * published site, and re-asking them must not require an analyst. Everything
 * else is fixed by the site, as it is everywhere else in this product.
 *
 * Nothing here is stored. A reader exploring "what if they swept for five
 * years" is asking a question, not creating a record.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import {
  api, type Advisory, type IsrPoint, type Lifecycle, type PreviewRun, type SimRun,
} from "../api/client";
import { canRunSim, useAuth } from "../auth";
import { ErrorNote, Loading, TableScroll } from "../components/bits";
import LifecycleChart, { LifecycleNarrative } from "../console/LifecycleChart";
import RunResult from "../console/RunResult";
import VerticalPanel from "../console/VerticalPanel";
import { fmt } from "../console/mapLayers";
import { SPECIES_NAME } from "../map/plume";
import { AffectedBlocks } from "../console/ProposeAdvisory";

/** The report's own defaults, as specified: look a long way out, assume nothing
 *  was cleaned up. Both are the conservative reading — a short horizon hides
 *  post-closure migration, and assuming a sweep credits remediation nobody has
 *  committed to. */
const DEFAULT_HORIZON = 50;
const DEFAULT_RESTORATION = 0;

export default function IsrReport() {
  const { siteId } = useParams<{ siteId: string }>();
  const nav = useNavigate();
  const { me } = useAuth();
  const mayRun = canRunSim(me?.role);

  const [horizon, setHorizon] = useState(DEFAULT_HORIZON);
  const [restoration, setRestoration] = useState(DEFAULT_RESTORATION);

  const site = useQuery({
    queryKey: ["isr-point", siteId], enabled: !!siteId,
    queryFn: () => api.get<IsrPoint>(`/isr-points/${siteId}`),
  });
  const advisories = useQuery({
    queryKey: ["advisories", siteId], enabled: !!siteId,
    queryFn: () => api.get<Advisory[]>(`/advisories?isr_point_id=${siteId}`),
  });
  const runs = useQuery({
    queryKey: ["runs", siteId], enabled: !!siteId,
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${siteId}&limit=10`),
  });

  const lifecycle = useMutation({
    mutationFn: () => api.post<Lifecycle>(`/simulations/${siteId}/lifecycle`, {
      time_years: horizon, restoration_years: restoration, points: 12,
    }),
  });
  const detail = useMutation({
    mutationFn: () => api.post<PreviewRun>(`/simulations/${siteId}/preview`, {
      species: "uranium_ppb", time_years: horizon, restoration_years: restoration,
    }),
  });

  // Build the report on open, and again whenever the two live inputs change —
  // the reader should not have to press a button to see the defaults.
  useEffect(() => {
    if (!siteId || !mayRun) return;
    lifecycle.mutate();
    detail.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, horizon, restoration, mayRun]);

  const s = site.data;
  const published = (advisories.data ?? []).find((a) => a.status === "published")
    ?? (advisories.data ?? [])[0];

  if (site.isLoading) return <div className="page"><Loading label="Loading the site…" /></div>;
  if (site.error) return <div className="page"><ErrorNote error={site.error} /></div>;
  if (!s) return null;

  return (
    <div className="page">
      <div className="page-head">
        <div className="row wrap">
          <button className="btn ghost" onClick={() => nav("/publications")}>← Publications</button>
        </div>
        <h1 style={{ marginTop: 10 }}>{s.name}</h1>
        <p>
          Full assessment record for this hypothetical ISR site — every operating
          parameter, all four contaminants, the shallow-aquifer screening, and how
          each changes across the operation&apos;s life.
        </p>
      </div>

      <div className="banner warn" style={{ marginBottom: 16 }}>
        <strong>No ISR uranium mine operates in Jharkhand.</strong> This describes a
        modelled scenario at this location, used for screening and preparedness. It is
        not a record of anything that has happened, and not a permitting document.
      </div>

      {/* ── the two live inputs ── */}
      <div className="card">
        <div className="card-title">Set the two questions</div>
        <div className="grid-2">
          <div className="slider">
            <label>Evaluation horizon <span className="u">yr</span><b>{horizon}</b></label>
            <input type="range" min={1} max={50} step={1} value={horizon}
                   onChange={(e) => setHorizon(+e.target.value)} />
          </div>
          <div className="slider">
            <label>Restoration sweep <span className="u">yr</span><b>{restoration}</b></label>
            <input type="range" min={0} max={30} step={1} value={restoration}
                   onChange={(e) => setRestoration(+e.target.value)} />
          </div>
        </div>
        <div className="muted small">
          These two are yours to change; everything else is a property of the site and
          is fixed, so that two people reading this report read the same operation.
          Defaults are deliberately conservative — look a long way out
          ({DEFAULT_HORIZON} yr), and assume no remediation ({DEFAULT_RESTORATION} yr).
          Nothing you do here is stored.
        </div>
      </div>

      {/* ── the operation ── */}
      <div className="card">
        <div className="card-title">The operation — fixed for this site</div>
        <TableScroll>
          <table className="grid">
            <tbody>
              <tr><td>Injection rate</td>
                  <td className="mono">{fmt(s.injection_rate_m3_day, 0)} m³/day</td>
                  <td className="muted small">lixiviant delivered to the wellfield</td></tr>
              <tr><td>Bleed</td><td className="mono">{fmt(s.bleed_percent, 2)} %</td>
                  <td className="muted small">net over-extraction that holds the plume in</td></tr>
              <tr><td>Operation duration</td><td className="mono">{fmt(s.operation_years, 0)} yr</td>
                  <td className="muted small">how long injection continues</td></tr>
              <tr><td>Well-pattern footprint ⌀</td>
                  <td className="mono">{fmt(s.wellfield_width_m, 0)} m</td>
                  <td className="muted small">full transverse extent of the wellfield — not a borehole width</td></tr>
              <tr><td>Monitor ring</td><td className="mono">{fmt(s.monitor_ring_m, 0)} m</td>
                  <td className="muted small">perimeter distance where an excursion is detected</td></tr>
              <tr><td>Ore zone depth</td><td className="mono">{fmt(s.ore_depth_m, 0)} m</td>
                  <td className="muted small">depth to the injection target</td></tr>
              <tr><td>Ore zone thickness</td><td className="mono">{fmt(s.ore_thickness_m, 0)} m</td>
                  <td className="muted small">vertical extent of the target</td></tr>
              <tr><td>Planned restoration</td>
                  <td className="mono">{fmt(s.restoration_years, 0)} yr</td>
                  <td className="muted small">the site&apos;s own figure; this report uses {restoration} yr</td></tr>
              <tr><td>Aquifer regime</td>
                  <td className="mono">{s.regime_override ?? "resolved from the location"}</td>
                  <td className="muted small">left to the engine unless overridden</td></tr>
              <tr><td>Hydraulic gradient</td>
                  <td className="mono">{s.gradient_i ?? "resolved from the location"}</td>
                  <td className="muted small">from the measured flow field</td></tr>
              <tr><td>Flow direction</td>
                  <td className="mono">{s.azimuth_deg ?? "resolved from the location"}</td>
                  <td className="muted small">down-gradient bearing</td></tr>
            </tbody>
          </table>
        </TableScroll>
      </div>

      {!mayRun && (
        <div className="banner">
          Your role can read this record but not re-run the model, so the charts below
          are unavailable. The published summary and the affected area are shown.
        </div>
      )}

      {/* ── every contaminant, across the whole life ── */}
      {mayRun && (
        <div className="card">
          <div className="card-title">All four contaminants, across the operation</div>
          {lifecycle.isPending && <Loading label="Tracing four contaminants…" />}
          <ErrorNote error={lifecycle.error} />
          {lifecycle.data && (
            <>
              <LifecycleChart data={lifecycle.data} />
              <LifecycleNarrative data={lifecycle.data} />
            </>
          )}
        </div>
      )}

      {/* ── the shallow aquifer ── */}
      {mayRun && detail.data && (
        <div className="card">
          <VerticalPanel v={detail.data.vertical} />
        </div>
      )}

      {/* ── the detailed uranium run at these settings ── */}
      {mayRun && (
        <div className="card">
          <div className="card-title">
            Detail at {horizon} yr, {restoration} yr sweep
          </div>
          {detail.isPending && <Loading label="Solving…" />}
          <ErrorNote error={detail.error} />
          {detail.data && (
            <RunResult r={detail.data} extrapolation={detail.data.extrapolation ?? []} />
          )}
        </div>
      )}

      {/* ── what was published, and where it reaches ── */}
      {published && (
        <div className="card">
          <div className="card-title">
            Published to residents
            <span className="spacer grow" />
            <span className={`chip ${published.status === "published" ? "ok" : "warn"}`}>
              {published.status}
            </span>
          </div>
          <div className="banner" style={{ marginBottom: 10 }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>{published.headline}</div>
            <div className="prose" style={{ whiteSpace: "pre-wrap", fontSize: "var(--fs-sm)" }}>
              {published.what_it_means}
            </div>
          </div>
          <AffectedBlocks advisory={published} />
          <div className="muted small" style={{ marginTop: 8 }}>
            Published for {SPECIES_NAME[published.species] ?? published.species} at{" "}
            {fmt(published.time_years, 0)} yr with a {fmt(published.restoration_years, 0)} yr
            sweep. Changing the sliders above does not change what was published — that
            record is fixed to the run behind it.
          </div>
        </div>
      )}

      {/* ── provenance ── */}
      <div className="card">
        <div className="card-title">Provenance — how to re-derive this</div>
        {runs.isLoading && <Loading />}
        {(runs.data ?? []).length === 0 && (
          <div className="muted small">
            No stored run for this site yet. The charts above are live and unstored;
            a saved run is what carries a re-derivable provenance triple.
          </div>
        )}
        <TableScroll>
          <table className="grid">
            <thead>
              <tr><th>Run</th><th>Contaminant</th><th>Model card</th><th>Code</th><th>When</th></tr>
            </thead>
            <tbody>
              {(runs.data ?? []).filter((r) => r.status === "completed").map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.id.slice(0, 8)}</td>
                  <td>{SPECIES_NAME[r.species] ?? r.species}</td>
                  <td className="mono">{r.model_card_sha?.slice(0, 12)}…</td>
                  <td className="mono">{r.code_version?.slice(0, 10)}</td>
                  <td className="muted small">
                    {r.completed_at ? new Date(r.completed_at).toLocaleString() : "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
        <div className="muted small" style={{ marginTop: 8 }}>
          Every stored run is pinned to the model card, artifact bundle and git commit
          that produced it, so any number in this report can be reproduced exactly as
          it stood — not merely recomputed with whatever the model looks like today.
        </div>
      </div>
    </div>
  );
}
