/**
 * Scenarios — named, saved sets of run inputs.
 *
 * WHY THIS SCREEN EXISTS. The backend has carried the whole scenario feature
 * since migration `0014`: create, list, run, compare, archive — five endpoints,
 * `run_compare.diff` behind them, and tests. The 2026-08-24 audit found that
 * only `GET /scenarios` was ever called, by the Overview page, for a count. The
 * table had **zero rows**, because nothing in the portal could put one there.
 *
 * WHAT A SCENARIO IS, AND IS NOT. It names a question asked of a fixed site:
 * which contaminant, how far out to look, and how long a restoration sweep. It
 * does NOT carry the operation — injection rate, bleed, wellfield geometry all
 * belong to the registered site, and migration `0015` exists so that two people
 * running "Jaduguda" run the same thing. Changing the operation is a site edit,
 * which is audited; it is not a scenario parameter.
 *
 * WHY COMPARE IS THE POINT. Two runs of the same scenario can disagree because
 * the inputs changed or because the model did. `POST /scenarios/{id}/compare`
 * answers which, and that `cause` field is rendered more prominently than the
 * metric deltas — a delta nobody can attribute is a delta nobody can act on.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api, type IsrPoint, type RunDiff, type Scenario, type SimRun,
} from "../api/client";
import { ErrorNote, Loading, Empty, TableScroll } from "../components/bits";

const NUM: React.CSSProperties = {
  textAlign: "right", fontVariantNumeric: "tabular-nums",
};

const SPECIES = [
  ["uranium_ppb", "Uranium"],
  ["radium_226_mbq_l", "Radium-226"],
  ["sulfate_mg_l", "Sulfate"],
  ["tds_mg_l", "Total dissolved solids"],
];

export default function Scenarios() {
  const qc = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [siteId, setSiteId] = useState("");
  const [species, setSpecies] = useState("uranium_ppb");
  const [years, setYears] = useState(20);
  const [restoration, setRestoration] = useState(5);

  const [openId, setOpenId] = useState<string | null>(null);
  const [pick, setPick] = useState<string[]>([]);
  const [diff, setDiff] = useState<RunDiff | null>(null);

  const sites = useQuery({
    queryKey: ["isr-points"],
    queryFn: () => api.get<IsrPoint[]>("/isr-points"),
  });

  const scenarios = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.get<Scenario[]>("/scenarios"),
  });

  /** Runs for the opened scenario. Scenario runs are ordinary
   *  `simulation_run` rows tagged with the scenario, so they are read from the
   *  same endpoint the Console uses — one source of truth for a run. */
  const runs = useQuery({
    queryKey: ["scenario-runs", openId],
    queryFn: () => {
      const sc = (scenarios.data ?? []).find((s) => s.id === openId);
      return api.get<SimRun[]>(
        `/simulations/runs?isr_id=${sc!.isr_point_id}&limit=200`);
    },
    enabled: !!openId && !!scenarios.data,
  });

  const create = useMutation({
    mutationFn: () => api.post<Scenario>("/scenarios", {
      name, description: description || null, isr_point_id: siteId,
      params: { species, time_years: years, restoration_years: restoration },
    }),
    onSuccess: () => {
      setCreating(false); setName(""); setDescription("");
      qc.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });

  const run = useMutation({
    mutationFn: (id: string) =>
      api.post<{ run_id: string; status: string }>(`/scenarios/${id}/run`),
    onSuccess: () => {
      // A queued run completes in the background; the list is refetched rather
      // than optimistically marked complete.
      setTimeout(() => qc.invalidateQueries({ queryKey: ["scenario-runs"] }), 1500);
    },
  });

  const archive = useMutation({
    mutationFn: (id: string) => api.del<void>(`/scenarios/${id}`),
    onSuccess: () => {
      setOpenId(null);
      qc.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });

  const compare = useMutation({
    mutationFn: () => api.post<RunDiff>(`/scenarios/${openId}/compare`, {
      run_a: pick[0], run_b: pick[1],
    }),
    onSuccess: setDiff,
  });

  const siteName = (id: string) =>
    (sites.data ?? []).find((s) => s.id === id)?.name ?? id.slice(0, 8);

  const toggle = (id: string) =>
    setPick((p) => p.includes(id) ? p.filter((x) => x !== id)
      : [...p, id].slice(-2));

  return (
    <div className="page">
      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <h1>Scenarios</h1>
        <span className="spacer grow" />
        <button className="btn" onClick={() => setCreating((v) => !v)}>
          {creating ? "Cancel" : "New scenario"}
        </button>
      </div>

      <div className="banner" style={{ marginBottom: 14 }}>
        A scenario names a <strong>question asked of a fixed site</strong> — which
        contaminant, how far out to look, how long to sweep restoration. The
        operation itself (injection rate, bleed, wellfield geometry) belongs to
        the registered site, so that two people running the same site run the
        same thing. Change those by editing the site, which is audited.
      </div>

      {creating && (
        <div className="card" style={{ marginBottom: 14 }}>
          <h2 style={{ marginTop: 0 }}>New scenario</h2>
          <div className="grid-2">
            <label>
              <div className="muted small">Name</div>
              <input type="text" value={name} maxLength={160}
                     onChange={(e) => setName(e.target.value)}
                     placeholder="Jaduguda — 50-year outlook" />
            </label>
            <label>
              <div className="muted small">Site</div>
              <select value={siteId}
                      onChange={(e) => setSiteId(e.target.value)}>
                <option value="">Choose a registered site…</option>
                {(sites.data ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </label>
          </div>
          <label>
            <div className="muted small" style={{ marginTop: 8 }}>
              Description (optional)
            </div>
            <input type="text" value={description}
                   onChange={(e) => setDescription(e.target.value)}
                   placeholder="Why this scenario is worth keeping" />
          </label>
          <div className="grid-3" style={{ marginTop: 8 }}>
            <label>
              <div className="muted small">Contaminant</div>
              <select value={species}
                      onChange={(e) => setSpecies(e.target.value)}>
                {SPECIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label>
              <div className="muted small">Evaluate at (years)</div>
              <input type="number" min={1} max={200} value={years}
                     onChange={(e) => setYears(Number(e.target.value))} />
            </label>
            <label>
              <div className="muted small">Restoration sweep (years)</div>
              <input type="number" min={0} max={100}
                     value={restoration}
                     onChange={(e) => setRestoration(Number(e.target.value))} />
            </label>
          </div>
          <ErrorNote error={create.error} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn" disabled={!name.trim() || !siteId || create.isPending}
                    onClick={() => create.mutate()}>
              {create.isPending ? "Saving…" : "Save scenario"}
            </button>
          </div>
        </div>
      )}

      {scenarios.isLoading && <Loading />}
      <ErrorNote error={scenarios.error} />

      {scenarios.data?.length === 0 && !creating && (
        <Empty>
          No scenarios saved yet. A scenario is worth creating when you expect to
          ask the same question again — after a retrain, or against a revised
          site — and want the two answers to be comparable.
        </Empty>
      )}

      {!!scenarios.data?.length && (
        <TableScroll>
          <table className="grid">
            <thead>
              <tr>
                <th>Name</th><th>Site</th><th>Contaminant</th>
                <th style={NUM}>Years</th><th style={NUM}>Restoration</th>
                <th>Created</th><th />
              </tr>
            </thead>
            <tbody>
              {scenarios.data.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.name}
                    {s.description && (
                      <div className="muted small">{s.description}</div>
                    )}
                  </td>
                  <td className="muted small">{siteName(s.isr_point_id)}</td>
                  <td className="muted small">
                    {String(s.params.species ?? "—")}
                  </td>
                  <td style={NUM}>{String(s.params.time_years ?? "—")}</td>
                  <td style={NUM}>{String(s.params.restoration_years ?? "—")}</td>
                  <td className="muted small">
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn small" disabled={run.isPending}
                              onClick={() => run.mutate(s.id)}>
                        Run
                      </button>
                      <button className="btn ghost small"
                              onClick={() => {
                                setDiff(null); setPick([]);
                                setOpenId(openId === s.id ? null : s.id);
                              }}>
                        {openId === s.id ? "Hide runs" : "Runs"}
                      </button>
                      <button className="btn ghost small"
                              onClick={() => {
                                if (confirm(
                                  `Archive "${s.name}"? Runs that reference it are ` +
                                  `kept — archiving hides the scenario, it does not ` +
                                  `delete history.`)) archive.mutate(s.id);
                              }}>
                        Archive
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}

      <ErrorNote error={run.error} />
      <ErrorNote error={archive.error} />

      {openId && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row wrap" style={{ alignItems: "baseline" }}>
            <h2 style={{ margin: 0 }}>Runs at this site</h2>
            <span className="spacer grow" />
            <button className="btn" disabled={pick.length !== 2 || compare.isPending}
                    onClick={() => compare.mutate()}>
              {compare.isPending ? "Comparing…" : `Compare selected (${pick.length}/2)`}
            </button>
          </div>
          <div className="muted small" style={{ margin: "4px 0 10px" }}>
            Select two completed runs. Only completed runs can be compared — the
            API refuses the rest with a 409 rather than diffing a partial result.
          </div>

          {runs.isLoading && <Loading />}
          <ErrorNote error={runs.error} />
          {runs.data?.length === 0 && (
            <Empty>No runs stored at this site yet. Press <em>Run</em> above.</Empty>
          )}

          {!!runs.data?.length && (
            <TableScroll>
              <table className="grid">
                <thead>
                  <tr>
                    <th /><th>Started</th><th>Status</th><th>Contaminant</th>
                    <th>Engine</th><th>Model bundle</th><th style={NUM}>ms</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <input type="checkbox"
                               checked={pick.includes(r.id)}
                               disabled={r.status !== "completed"
                                 && !pick.includes(r.id)}
                               onChange={() => toggle(r.id)} />
                      </td>
                      <td className="muted small">
                        {new Date(r.created_at).toLocaleString()}
                      </td>
                      <td>
                        <span className={`chip ${r.status === "completed" ? "ok"
                          : r.status === "failed" ? "danger" : "warn"}`}>
                          {r.status}
                        </span>
                      </td>
                      <td className="muted small">{r.species}</td>
                      <td className="muted small">{r.engine}</td>
                      <td className="muted small">
                        {r.artifacts_sha ? r.artifacts_sha.slice(0, 10) : "—"}
                      </td>
                      <td style={NUM}>{r.runtime_ms ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}

          <ErrorNote error={compare.error} />

          {diff && (
            <div style={{ marginTop: 14 }}>
              {/* The cause leads. A metric delta nobody can attribute to either
                  the inputs or the model is a delta nobody can act on. */}
              <div className={`banner ${diff.same_engine ? "" : "warn"}`}>
                <strong>{diff.cause}</strong>
                <div className="muted small" style={{ marginTop: 4 }}>
                  Same model bundle: {diff.same_model ? "yes" : "no"} · same code
                  revision: {diff.same_code ? "yes" : "no"}
                  {!diff.same_engine && " — so this difference is NOT attributable "
                    + "to the inputs alone."}
                </div>
              </div>

              {Object.keys(diff.input_delta).length > 0 && (
                <>
                  <h3>Inputs that differ</h3>
                  <TableScroll>
                    <table className="grid">
                      <thead>
                        <tr><th>Field</th><th>Run A</th><th>Run B</th></tr>
                      </thead>
                      <tbody>
                        {Object.entries(diff.input_delta).map(([k, v]) => (
                          <tr key={k}>
                            <td>{k}</td>
                            <td className="muted small">{JSON.stringify(v.a)}</td>
                            <td className="muted small">{JSON.stringify(v.b)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableScroll>
                </>
              )}

              <h3>Metrics</h3>
              <TableScroll>
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th style={NUM}>Run A</th>
                      <th style={NUM}>Run B</th>
                      <th style={NUM}>Change</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(diff.metric_delta).map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td style={NUM}>{v.a ?? "—"}</td>
                        <td style={NUM}>{v.b ?? "—"}</td>
                        <td style={NUM}>
                          {v.change_pct === null ? "—"
                            : `${v.change_pct > 0 ? "+" : ""}${v.change_pct}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>

              <div className="muted small" style={{ marginTop: 8 }}>{diff.note}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
