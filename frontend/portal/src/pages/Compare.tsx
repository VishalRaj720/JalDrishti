/**
 * Compare two ISR sites, side by side.
 *
 * A registered site *is* the operation — only species, evaluation time and the
 * restoration sweep vary per run — so two sites are two distinct hypothetical
 * operations, and the interesting question is which of their fixed parameters
 * drove the difference in outcome. That is what this screen answers, and why it
 * leads with `cause` rather than with the numbers: a delta nobody can attribute
 * is a delta nobody can act on.
 *
 * Comparing a site against ITSELF is supported and useful — the same site at two
 * evaluation times, or before and after a model change. The endpoint reports
 * `same_site` so the page can say which kind of comparison this is.
 *
 * Only **saved** runs appear. A Console preview stores nothing by design (rule
 * 7), so there is nothing to compare until someone deliberately keeps a run.
 */
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api, type IsrPoint, type RunDiff, type SimRun } from "../api/client";
import { Empty, ErrorNote, HypotheticalNote, Loading, TableScroll } from "../components/bits";

/** One side of the comparison: pick a site, then one of its saved runs. */
function SidePicker({
  label, sites, siteId, onSite, runId, onRun,
}: {
  label: string;
  sites: IsrPoint[] | undefined;
  siteId: string; onSite: (v: string) => void;
  runId: string; onRun: (v: string) => void;
}) {
  const runs = useQuery({
    queryKey: ["runs", siteId],
    enabled: !!siteId,
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${siteId}&limit=50`),
  });
  const done = (runs.data ?? []).filter((r) => r.status === "completed");

  return (
    <div className="card">
      <div className="sec">{label}</div>
      <label className="field">
        <span>Site</span>
        <select className="input" value={siteId}
          onChange={(e) => { onSite(e.target.value); onRun(""); }}>
          <option value="">Choose a site…</option>
          {(sites ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </label>

      <label className="field">
        <span>Saved run</span>
        <select className="input" value={runId} disabled={!siteId || runs.isLoading}
          onChange={(e) => onRun(e.target.value)}>
          <option value="">
            {!siteId ? "Choose a site first"
              : runs.isLoading ? "Loading…"
                : done.length === 0 ? "No saved runs for this site"
                  : "Choose a run…"}
          </option>
          {done.map((r) => (
            <option key={r.id} value={r.id}>
              {r.species} · {new Date(r.created_at).toLocaleString()}
            </option>
          ))}
        </select>
      </label>

      {siteId && !runs.isLoading && done.length === 0 && (
        <p className="muted small">
          Nothing saved here yet. A Console run is ephemeral until you keep it —
          open the site in the <Link to="/console">Console</Link> and save one.
        </p>
      )}
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return String(v);
    return Math.abs(v) < 0.01 ? v.toExponential(2) : v.toFixed(3);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

export default function Compare() {
  const [aSite, setASite] = useState(""); const [aRun, setARun] = useState("");
  const [bSite, setBSite] = useState(""); const [bRun, setBRun] = useState("");

  const sites = useQuery({
    queryKey: ["isr-points"],
    queryFn: () => api.get<IsrPoint[]>("/isr-points"),
  });

  const cmp = useMutation({
    mutationFn: () => api.post<RunDiff>("/simulations/compare",
      { run_a: aRun, run_b: bRun }),
  });

  const ready = !!aRun && !!bRun && aRun !== bRun;
  const nameOf = (id: string) => sites.data?.find((s) => s.id === id)?.name ?? id;

  return (
    <div className="page">
      <div className="page-head">
        <h1>Compare two sites</h1>
        <p>
          Diff two saved runs and attribute the difference — did the inputs change,
          or did the model? A delta nobody can attribute is a delta nobody can act on.
        </p>
      </div>

      <HypotheticalNote />

      <div className="grid-2">
        <SidePicker label="Site A" sites={sites.data} siteId={aSite}
          onSite={setASite} runId={aRun} onRun={setARun} />
        <SidePicker label="Site B" sites={sites.data} siteId={bSite}
          onSite={setBSite} runId={bRun} onRun={setBRun} />
      </div>

      <div className="row gap" style={{ margin: "12px 0" }}>
        <button className="btn primary" disabled={!ready || cmp.isPending}
          onClick={() => cmp.mutate()}>
          {cmp.isPending ? "Comparing…" : "Compare"}
        </button>
        {aRun && bRun && aRun === bRun && (
          <span className="muted small">Pick two different runs.</span>
        )}
      </div>

      {cmp.error && <ErrorNote error={cmp.error} />}

      {cmp.data && (
        <>
          {/* Why they differ comes first — the numbers are meaningless without it. */}
          <section className={`card ${cmp.data.same_engine ? "" : "warn"}`}>
            <h2>Why these differ</h2>
            <p><b>{cmp.data.cause}</b></p>
            <dl className="kv">
              <dt>Comparison</dt>
              <dd>{cmp.data.same_site
                ? "The same site, twice — so any difference is time, species or the model."
                : `${nameOf(cmp.data.isr_point_a)} vs ${nameOf(cmp.data.isr_point_b)}`}</dd>
              <dt>Species</dt>
              <dd>{cmp.data.species.a}
                {cmp.data.species.a !== cmp.data.species.b && ` vs ${cmp.data.species.b}`}</dd>
              <dt>Same model artifacts</dt>
              <dd>{cmp.data.same_model
                ? "Yes — identical artifact bundle and model card."
                : "No — the trained surrogate differs between these runs."}</dd>
              <dt>Same engine code</dt>
              <dd>{cmp.data.same_code
                ? "Yes — the same git revision computed both."
                : "No — a different revision computed each. The analytical engine "
                  + "is code, not a pickled model, so this moves every analytical "
                  + "number even with an identical artifact bundle."}</dd>
            </dl>
            {(cmp.data.extrapolation.a?.length || cmp.data.extrapolation.b?.length) ? (
              <div className="banner danger">
                <b>Outside trained support.</b>{" "}
                {cmp.data.extrapolation.a?.length ? `A: ${cmp.data.extrapolation.a.join(", ")}. ` : ""}
                {cmp.data.extrapolation.b?.length ? `B: ${cmp.data.extrapolation.b.join(", ")}. ` : ""}
                The conformal guarantee is void where that is flagged; the
                analytical engine still serves a value.
              </div>
            ) : null}
            <p className="muted small">{cmp.data.note}</p>
          </section>

          <section className="card">
            <h2>Inputs that differ</h2>
            {Object.keys(cmp.data.input_delta).length === 0 ? (
              <Empty>Identical inputs.</Empty>
            ) : (
              <TableScroll>
                <table className="grid">
                  <thead><tr><th>Parameter</th><th>A</th><th>B</th></tr></thead>
                  <tbody>
                    {Object.entries(cmp.data.input_delta).map(([k, v]) => (
                      <tr key={k}>
                        <td className="mono small">{k}</td>
                        <td>{fmt(v.a)}</td>
                        <td>{fmt(v.b)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
          </section>

          <section className="card">
            <h2>What changed in the result</h2>
            <p className="muted small">
              Metrics are prefixed by the engine that produced them.{" "}
              <b>The analytical engine is the authority</b> — the surrogate was
              trained on its output and contributes calibrated bands, so where the
              two disagree the analytical value is the one to quote.
            </p>
            {Object.keys(cmp.data.metric_delta).length === 0 ? (
              <Empty>No metric changed.</Empty>
            ) : (
              <TableScroll>
                <table className="grid">
                  <thead>
                    <tr><th>Metric</th><th>A</th><th>B</th><th>Change</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(cmp.data.metric_delta).map(([k, v]) => (
                      <tr key={k}>
                        <td className="mono small">{k}</td>
                        <td>{fmt(v.a)}</td>
                        <td>{fmt(v.b)}</td>
                        <td className={
                          v.change_pct == null ? "muted"
                            : v.change_pct > 0 ? "warn-text" : ""}>
                          {v.change_pct == null
                            // A rise from zero has no meaningful percentage: a
                            // plume that did not exist and now does is not
                            // "infinitely larger".
                            ? (v.a === 0 ? "from zero" : "—")
                            : `${v.change_pct > 0 ? "+" : ""}${v.change_pct}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            )}
          </section>

          <section className="card">
            <h2>Provenance</h2>
            <TableScroll>
              <table className="grid">
                <thead><tr><th /><th>Run A</th><th>Run B</th></tr></thead>
                <tbody>
                  <tr>
                    <td>Artifact bundle</td>
                    <td className="mono small">{cmp.data.model.a.artifacts_sha?.slice(0, 16) ?? "—"}</td>
                    <td className="mono small">{cmp.data.model.b.artifacts_sha?.slice(0, 16) ?? "—"}</td>
                  </tr>
                  <tr>
                    <td>Model card</td>
                    <td className="mono small">{cmp.data.model.a.model_card_sha?.slice(0, 16) ?? "—"}</td>
                    <td className="mono small">{cmp.data.model.b.model_card_sha?.slice(0, 16) ?? "—"}</td>
                  </tr>
                  <tr>
                    <td>Code version</td>
                    <td className="mono small">{cmp.data.model.a.code_version ?? "—"}</td>
                    <td className="mono small">{cmp.data.model.b.code_version ?? "—"}</td>
                  </tr>
                  <tr>
                    <td>Run id</td>
                    <td className="mono small">{cmp.data.run_a.slice(0, 8)}…</td>
                    <td className="mono small">{cmp.data.run_b.slice(0, 8)}…</td>
                  </tr>
                </tbody>
              </table>
            </TableScroll>
          </section>
        </>
      )}

      {sites.isLoading && <Loading />}
      {sites.data?.length === 0 && (
        <Empty>No ISR sites are registered yet.</Empty>
      )}
    </div>
  );
}
