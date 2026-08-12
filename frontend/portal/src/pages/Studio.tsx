/**
 * Simulation Studio — the ISR plume engine, inside the portal.
 *
 * The side panel follows the ml_pipeline dashboard: numbered steps, segmented
 * contaminant selector, operational sliders, then metric cards with the P10–P90
 * band always visible.
 *
 * It drives the BACKEND run API, never the pipeline directly (PRODUCT_DESIGN §6:
 * the engine is an internal service). That buys a persisted, audited, provenance-
 * pinned result — and costs live interactivity: a run takes 5–15 s and is queued
 * and polled, so this is "configure then run", not drag-to-update. The UI says so
 * rather than pretending otherwise.
 */
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type IsrPoint, type Scenario, type SimRun } from "../api/client";
import { canRunSim, useAuth } from "../auth";
import { Empty, ErrorNote, Loading, Metric, Planned } from "../components/bits";

const SPECIES = [
  { v: "uranium_ppb", label: "Uranium", unit: "ppb" },
  { v: "sulfate_mg_l", label: "Sulfate", unit: "mg/L" },
  { v: "tds_mg_l", label: "TDS", unit: "mg/L" },
  { v: "radium_226_mbq_l", label: "Radium-226", unit: "mBq/L" },
];
// A concentration without its unit is not a number a regulator can act on, and
// the unit changes with the species being run.
const unitOf = (species?: string) =>
  SPECIES.find((s) => s.v === species)?.unit ?? "";

interface Params {
  species: string; operation_years: number; time_years: number;
  injection_rate_m3_day: number; wellfield_width_m: number;
  bleed_percent: number; restoration_years: number; monitor_ring_m: number;
}
const DEFAULTS: Params = {
  species: "uranium_ppb", operation_years: 8, time_years: 20,
  injection_rate_m3_day: 2500, wellfield_width_m: 300,
  bleed_percent: 2, restoration_years: 0, monitor_ring_m: 100,
};

function band(m: any) {
  if (!m || typeof m !== "object") return null;
  const { p10, p50, p90 } = m;
  if (p50 === undefined) return null;
  return { p10, p50, p90 };
}
const fmt = (n: any, d = 1) =>
  typeof n === "number" ? n.toLocaleString(undefined, { maximumFractionDigits: d }) : "–";

export default function Studio() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [siteId, setSiteId] = useState<string>("");
  const [p, setP] = useState<Params>(DEFAULTS);
  const [runId, setRunId] = useState<string | null>(null);
  const [scenarioName, setScenarioName] = useState("");

  const sites = useQuery({ queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points") });
  useEffect(() => {
    if (!siteId && sites.data?.length) setSiteId(sites.data[0].id);
  }, [sites.data, siteId]);

  const runs = useQuery({
    queryKey: ["runs", siteId], enabled: !!siteId,
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${siteId}&limit=25`),
    // Poll while the Studio is open: a run finishes in a background task, so
    // without this a completed result would sit on "running" indefinitely.
    // `InBackground` matters — the client disables window-focus refetching, and
    // a plain interval is paused while the tab is hidden, so switching away
    // mid-run and back would otherwise strand the row on "running" forever.
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
  });

  const scenarios = useQuery({
    queryKey: ["scenarios", siteId], enabled: !!siteId,
    queryFn: () => api.get<Scenario[]>(`/scenarios?isr_point_id=${siteId}`),
  });

  const active = runs.data?.find((r) => r.id === runId) ?? runs.data?.[0];

  const run = useMutation({
    mutationFn: () =>
      api.post<SimRun>(`/simulations/${siteId}`, {
        species: p.species,
        operation_years: p.operation_years,
        time_years: p.time_years,
        injection_rate_m3_day: p.injection_rate_m3_day,
        wellfield_width_m: p.wellfield_width_m,
        bleed_percent: p.bleed_percent,
        restoration_years: p.restoration_years,
        monitor_ring_m: p.monitor_ring_m,
      }),
    onSuccess: (r) => { setRunId(r.id); qc.invalidateQueries({ queryKey: ["runs", siteId] }); },
  });

  const save = useMutation({
    mutationFn: () =>
      api.post<Scenario>("/scenarios", {
        name: scenarioName, isr_point_id: siteId,
        params: { ...p },
      }),
    onSuccess: () => { setScenarioName(""); qc.invalidateQueries({ queryKey: ["scenarios", siteId] }); },
  });

  const S = (k: keyof Params, label: string, unit: string, min: number, max: number, step: number) => (
    <div className="slider" key={k}>
      <label>{label} <span className="u">{unit}</span><b>{p[k] as number}</b></label>
      <input type="range" min={min} max={max} step={step} value={p[k] as number}
             onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} />
    </div>
  );

  const metrics = active?.metrics ?? null;
  const an = metrics?.analytical ?? null;
  const ml = metrics?.ml ?? null;
  const exc = active?.excursion ?? null;
  const extrap = active?.extrapolation ?? [];

  return (
    <>
      <aside className="rail">
        <div className="card">
          <div className="card-title">① Site</div>
          {sites.isLoading && <Loading />}
          <select value={siteId} onChange={(e) => { setSiteId(e.target.value); setRunId(null); }}>
            {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <div className="muted small" style={{ marginTop: 7 }}>
            Hydrogeology, flow direction and baselines are resolved by the engine from
            its own datasets at these coordinates.
          </div>
        </div>

        <div className="card">
          <div className="card-title">② Contaminant</div>
          <div className="seg">
            {SPECIES.map((s) => (
              <button key={s.v} className={p.species === s.v ? "active" : ""}
                      onClick={() => setP({ ...p, species: s.v })}>{s.label}</button>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-title">③ Operational parameters</div>
          {S("injection_rate_m3_day", "Injection rate", "m³/day", 200, 8000, 50)}
          {S("bleed_percent", "Bleed", "%", 0, 10, 0.1)}
          {S("operation_years", "Operation duration", "yr", 1, 20, 1)}
          {S("time_years", "Evaluation horizon", "yr", 0, 50, 1)}
          {S("wellfield_width_m", "Well-pattern footprint ⌀", "m", 100, 800, 10)}
          {S("restoration_years", "Restoration sweep", "yr", 0, 30, 1)}
          {S("monitor_ring_m", "Monitor ring", "m", 75, 180, 5)}
          <div className="muted small">
            Sliders extend beyond the model's trained range on purpose — the analytical
            engine still serves there and the result is flagged, not refused.
          </div>
        </div>

        <div className="card">
          <div className="card-title">④ Run</div>
          {canRunSim(me?.role) ? (
            <>
              <button className="btn primary" style={{ width: "100%" }}
                      disabled={!siteId || run.isPending} onClick={() => run.mutate()}>
                {run.isPending ? "Queueing…" : "Run simulation"}
              </button>
              <div className="muted small" style={{ marginTop: 7 }}>
                Queued and executed server-side (5–15 s), then persisted with the model
                and code version that produced it.
              </div>
            </>
          ) : (
            <div className="muted small">
              Your role can read results but not start runs. Runs are limited to
              analysts and administrators.
            </div>
          )}
          <ErrorNote error={run.error} />
        </div>

        {canRunSim(me?.role) && (
          <div className="card">
            <div className="card-title">⑤ Save as scenario</div>
            <input placeholder="e.g. Baseline 8yr" value={scenarioName}
                   onChange={(e) => setScenarioName(e.target.value)} />
            <button className="btn" style={{ width: "100%", marginTop: 7 }}
                    disabled={!scenarioName || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save current inputs"}
            </button>
            <ErrorNote error={save.error} />
            {scenarios.data?.map((s) => (
              <div key={s.id} className="list-item" style={{ marginTop: 4 }}
                   onClick={() => setP({ ...p, ...(s.params as any) })}>
                <div><div className="nm">{s.name}</div><div className="mt">load inputs</div></div>
              </div>
            ))}
          </div>
        )}
      </aside>

      <div className="page">
        <div className="page-head">
          <h1>Simulation Studio</h1>
          <p>
            Physics-informed ISR plume surrogate. The analytical engine is the authority;
            the ML surrogate contributes calibrated P10–P90 uncertainty bands.
          </p>
        </div>

        {!active && <Empty>No run yet for this site. Configure the inputs and press Run.</Empty>}

        {active && (
          <>
            {active.status !== "completed" && (
              <div className="banner" style={{ marginBottom: 13 }}>
                <span className="spinner" /> Run is <strong>{active.status}</strong> — the
                engine is solving transport on a 200² grid.
              </div>
            )}
            {active.error_message && <div className="banner danger">{active.error_message}</div>}

            {/* §4.5 rule 2 — extrapolation is loud. */}
            {extrap.length > 0 && (
              <div className="banner warn" style={{ marginBottom: 13 }}>
                <strong>Outside trained support:</strong>{" "}
                <span className="mono">{extrap.join(", ")}</span>
                <div style={{ marginTop: 4 }}>
                  The analytical engine remains valid. The ML band here is <b>not</b>
                  conformally guaranteed — treat it as indicative only.
                </div>
              </div>
            )}
            {active.sync_note && (
              <div className="banner warn" style={{ marginBottom: 13 }}>{active.sync_note}</div>
            )}

            {active.status === "completed" && (
              <>
                <div className="grid-3" style={{ marginBottom: 13 }}>
                  <Metric tone="danger" label="Contaminated footprint" unit="ha"
                          value={fmt(an?.area_ha ?? an?.affected_area_ha)}
                          band={(() => {
                            const b = band(ml?.area_ha);
                            return b ? `ML P10–P90  ${fmt(b.p10)} – ${fmt(b.p90)}` : "analytical only";
                          })()} />
                  <Metric label="Max migration distance" unit="m"
                          value={fmt(an?.migration_m ?? an?.max_migration_distance_m)}
                          band={(() => {
                            const b = band(ml?.migration_m);
                            return b ? `ML P10–P90  ${fmt(b.p10)} – ${fmt(b.p90)}` : "analytical only";
                          })()} />
                  <Metric label="Concentration at compliance ring"
                          unit={unitOf(active.species)}
                          value={fmt(an?.compliance_conc, 3)}
                          band={(() => {
                            const b = band(ml?.compliance_conc);
                            return b ? `ML P10–P90  ${fmt(b.p10, 3)} – ${fmt(b.p90, 3)}` : "analytical only";
                          })()} />
                </div>

                {exc && (
                  <div className="card">
                    <div className="card-title">
                      ISR excursion — NUREG-1569-inspired screening
                      <span className="spacer grow" />
                      <span className={`chip ${exc.excursion_declared ? "danger" : "ok"}`}>
                        {exc.excursion_declared ? "DECLARED" : "none"}
                      </span>
                    </div>
                    <div className="muted small" style={{ marginBottom: 9 }}>{exc.rule}</div>
                    <table className="grid">
                      <thead>
                        <tr><th>Indicator</th><th>Ring conc.</th><th>Baseline</th><th>UCL</th><th>Over</th></tr>
                      </thead>
                      <tbody>
                        {(exc.indicators ?? []).map((i: any) => (
                          <tr key={i.species ?? i.name}>
                            <td>
                              {(i.species ?? i.name ?? "").replace(/_mg_l$/, "").replace(/_/g, " ")}
                              {i.unit && <span className="muted small"> {i.unit}</span>}
                            </td>
                            <td className="mono">{fmt(i.ring_conc, 2)}</td>
                            <td className="mono">{fmt(i.baseline, 2)}</td>
                            <td className="mono">{fmt(i.upper_control_limit, 2)}</td>
                            <td>{i.over_ucl ? <span className="chip danger">yes</span>
                                             : <span className="chip neutral">no</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {exc.ucl_rule && (
                      <div className="muted small" style={{ marginTop: 8 }}>
                        <strong>UCL</strong> — {exc.ucl_rule}
                      </div>
                    )}
                    <div className="banner warn" style={{ marginTop: 10 }}>
                      {exc.compliance_status}. {exc.compliance_note}
                    </div>
                  </div>
                )}

                <Planned label="Plume contour map and P10/P90 migration envelope" phase="P5"
                         why="The run API persists metrics, excursion state and hydrogeology — not plume geometry. Rendering contours needs the geometry to be stored, which is a backend change, so nothing is drawn here rather than drawing something invented." />

                <div className="card">
                  <div className="card-title">Provenance — how to re-derive this number</div>
                  <dl className="kv">
                    <dt>Run id</dt><dd className="mono">{active.id}</dd>
                    <dt>Model card</dt><dd className="mono">{active.model_card_sha?.slice(0, 24)}…</dd>
                    <dt>Artifact bundle</dt><dd className="mono">{active.artifacts_sha?.slice(0, 24)}…</dd>
                    <dt>Code version</dt><dd className="mono">{active.code_version?.slice(0, 12)}</dd>
                    <dt>Runtime</dt><dd>{active.runtime_ms ? `${(active.runtime_ms / 1000).toFixed(1)}s` : "–"}</dd>
                    <dt>Completed</dt>
                    <dd>{active.completed_at ? new Date(active.completed_at).toLocaleString() : "–"}</dd>
                  </dl>
                </div>
              </>
            )}
          </>
        )}

        <div className="card">
          <div className="card-title">Run history</div>
          {runs.isLoading && <Loading />}
          {runs.data?.length === 0 && <div className="muted small">No runs for this site.</div>}
          <table className="grid">
            <tbody>
              {runs.data?.map((r) => (
                <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => setRunId(r.id)}>
                  <td>{r.species.replace(/_/g, " ")}</td>
                  <td className="muted">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="mono">{r.runtime_ms ? `${(r.runtime_ms / 1000).toFixed(1)}s` : "–"}</td>
                  <td>{(r.extrapolation?.length ?? 0) > 0 && <span className="chip warn">extrapolating</span>}</td>
                  <td>
                    <span className={`chip ${r.status === "completed" ? "ok" : r.status === "failed" ? "danger" : "warn"}`}>
                      {r.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
