/**
 * Dataset Manager — what the engine actually reads, and control over it.
 *
 * This is the surface for the `record_source` column. Every writable dataset
 * shows its `original` / `added` split, and only `added` rows carry edit and
 * delete controls. The disabled state here is a courtesy: the API returns 409
 * for an `original` row regardless of what the browser sends, and that is the
 * real boundary.
 *
 * Three things live together on this page because they are one workflow:
 *
 *   1. **Sync** — carry approved field observations into the files.
 *   2. **Rebuild** — recompute what those files derive (flow field, baselines).
 *      Syncing without rebuilding leaves the engine on the old numbers, which is
 *      the failure mode the staleness banner exists to make impossible to miss.
 *   3. **Reset** — strip every added row and go back to what shipped.
 *
 * Splitting them across screens would let someone do (1), see "synced", and
 * reasonably believe the model had changed when it had not.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api, type DatasetRows, type DatasetSummary, type MlDrift, type ModelState, type OpsStatus,
} from "../api/client";
import { Empty, ErrorNote, Loading, TableScroll } from "../components/bits";

const PAGE = 50;

export default function Datasets() {
  const qc = useQueryClient();
  const [key, setKey] = useState<string | null>(null);
  const [filter, setFilter] = useState<"" | "original" | "added">("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [banner, setBanner] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api.get<{ datasets: DatasetSummary[]; note: string }>("/datasets"),
  });
  const ops = useQuery({
    queryKey: ["ops-status"],
    queryFn: () => api.get<OpsStatus>("/model-ops/status"),
  });
  const model = useQuery({
    queryKey: ["model-state"],
    queryFn: () => api.get<ModelState>("/model-ops/model"),
  });
  // The two endpoints that existed since P4 and were never once called by the
  // UI. Drift is the honest answer to "does this model still agree with the
  // engine it was trained on", which is the only question that would justify a
  // retrain — so it belongs beside the model, not in a debug console.
  const drift = useQuery({
    queryKey: ["ml-drift"],
    queryFn: () => api.get<MlDrift>("/ml/drift"),
  });
  const rows = useQuery({
    queryKey: ["dataset-rows", key, filter, q, offset],
    enabled: !!key,
    queryFn: () => api.get<DatasetRows>(
      `/datasets/${key}/rows?offset=${offset}&limit=${PAGE}`
      + (filter ? `&source=${filter}` : "")
      + (q ? `&q=${encodeURIComponent(q)}` : "")),
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["datasets"] });
    qc.invalidateQueries({ queryKey: ["dataset-rows"] });
    qc.invalidateQueries({ queryKey: ["ops-status"] });
    qc.invalidateQueries({ queryKey: ["model-state"] });
    qc.invalidateQueries({ queryKey: ["ml-drift"] });
    qc.invalidateQueries({ queryKey: ["sync-status"] });
  };
  const sync = useMutation({
    mutationFn: (what: string) =>
      api.post<{ message: string }>(`/dataset-sync/${what}?dry_run=false`),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const rebuild = useMutation({
    mutationFn: (what: string) => api.post<{ message: string }>(`/model-ops/${what}`),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const del = useMutation({
    mutationFn: (rowId: string) =>
      api.del<{ message: string }>(`/datasets/${key}/rows/${encodeURIComponent(rowId)}`),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const patch = useMutation({
    mutationFn: (v: { rowId: string; body: Record<string, unknown> }) =>
      api.patch<{ message: string }>(
        `/datasets/${key}/rows/${encodeURIComponent(v.rowId)}`, v.body),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const backup = useMutation({
    mutationFn: (label: string) =>
      api.post<{ message: string }>(
        `/model-ops/model-backups?label=${encodeURIComponent(label)}`),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const restoreModel = useMutation({
    mutationFn: (name: string) => api.post<{ message: string }>(
      `/model-ops/model-backups/${encodeURIComponent(name)}/restore`),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });
  const reset = useMutation({
    mutationFn: (dry: boolean) => api.post<{ message: string }>(
      `/model-ops/factory-reset?dry_run=${dry}` + (dry ? "" : "&confirm=RESET")),
    onSuccess: (r) => { setProblem(null); setBanner(r.message); refresh(); },
    onError: (e: Error) => setProblem(e.message),
  });

  const sel = list.data?.datasets.find((d) => d.key === key) ?? null;
  const busy = sync.isPending || rebuild.isPending || reset.isPending
    || del.isPending || patch.isPending || backup.isPending
    || restoreModel.isPending;

  return (
    <div className="page">
      <header className="page-head">
        <h1>Dataset manager</h1>
        <p className="muted">
          The files the physics engine reads. <b>Rows marked “original” shipped with
          the project</b> — CGWB, UDEPO, GSI, NAQUIM — and cannot be edited or
          deleted. Rows marked “added” were written from approved field
          observations, and can.
        </p>
      </header>

      {banner && <div className="note ok" role="status">{banner}</div>}
      {problem && <ErrorNote error={problem} />}

      {/* ── staleness: the thing most likely to be missed ── */}
      {ops.data && (
        <section className={`card ${ops.data.any_stale ? "warn" : ""}`}>
          <h2>Engine currency</h2>
          <p>{ops.data.message}</p>
          <table className="tbl">
            <thead>
              <tr><th>Derived artifact</th><th>Built from</th><th>Built</th><th>State</th></tr>
            </thead>
            <tbody>
              {ops.data.artifacts.map((a) => (
                <tr key={a.artifact}>
                  <td className="mono">{a.artifact}</td>
                  <td className="muted small">{a.sources.join(", ")}</td>
                  <td className="muted small">
                    {a.built_at ? new Date(a.built_at).toLocaleString() : "never"}
                  </td>
                  <td>
                    {a.stale
                      ? <span className="pill amber">⚠ stale</span>
                      : <span className="pill green">✓ current</span>}
                    {a.blocked && <div className="small warn-text">{a.blocked}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">{ops.data.note}</p>
          <div className="row gap">
            <button className="btn" disabled={busy}
              onClick={() => rebuild.mutate("recompute-baselines")}>
              Recompute baselines
            </button>
            <button className="btn" disabled={busy}
              onClick={() => rebuild.mutate("rebuild-flow-field")}>
              Rebuild flow field
            </button>
          </div>
        </section>
      )}

      {/* ── sync ── */}
      <section className="card">
        <h2>Bring approved observations in</h2>
        <p className="muted small">
          Each sync backs the file up first, tags new rows <code>added</code>, and
          records the batch in the audit log. Chemistry and level syncs leave a
          derived artifact stale — rebuild it above afterwards.
        </p>
        <div className="row gap">
          <button className="btn" disabled={busy} onClick={() => sync.mutate("ore")}>
            Sync ore
          </button>
          <button className="btn" disabled={busy}
            onClick={() => sync.mutate("water-quality")}>Sync chemistry</button>
          <button className="btn" disabled={busy}
            onClick={() => sync.mutate("groundwater-levels")}>Sync levels</button>
          <button className="btn primary" disabled={busy}
            onClick={() => sync.mutate("all")}>Sync everything</button>
        </div>
      </section>

      {/* ── the files ── */}
      <section className="card">
        <h2>Files</h2>
        {list.isLoading && <Loading />}
        {list.error && <ErrorNote error={list.error} />}
        <table className="tbl">
          <thead>
            <tr>
              <th>Dataset</th><th>Rows</th><th>Original</th><th>Added</th>
              <th>Governs</th><th />
            </tr>
          </thead>
          <tbody>
            {list.data?.datasets.map((d) => (
              <tr key={d.key} className={d.key === key ? "sel" : ""}>
                <td>
                  <div>{d.label}</div>
                  <div className="mono small muted">{d.path}</div>
                </td>
                <td>{d.available ? d.rows : <span className="warn-text">missing</span>}</td>
                <td>{d.original ?? "—"}</td>
                <td>{d.added ? <b>{d.added}</b> : 0}</td>
                <td className="small muted">{d.governs}</td>
                <td>
                  <button className="btn ghost" disabled={!d.available}
                    onClick={() => { setKey(d.key); setOffset(0); setQ(""); setFilter(""); }}>
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* ── rows ── */}
      {key && sel && (
        <section className="card">
          <div className="row between">
            <h2>{sel.label}</h2>
            <button className="btn ghost" onClick={() => setKey(null)}>Close</button>
          </div>
          <p className="muted small">{rows.data?.editable_note}</p>

          <div className="row gap wrap">
            <input className="input" placeholder="Filter rows…" value={q}
              onChange={(e) => { setQ(e.target.value); setOffset(0); }} />
            <select className="input" value={filter}
              onChange={(e) => {
                setFilter(e.target.value as "" | "original" | "added");
                setOffset(0);
              }}>
              <option value="">All rows</option>
              <option value="added">Added only</option>
              <option value="original">Original only</option>
            </select>
          </div>

          {rows.isLoading && <Loading />}
          {rows.data && rows.data.rows.length === 0 && <Empty>No matching rows.</Empty>}
          {rows.data && rows.data.rows.length > 0 && (
            <>
              <TableScroll>
                <table className="tbl compact">
                  <thead>
                    <tr>
                      <th>Source</th>
                      {rows.data.columns
                        .filter((c) => c !== "record_source" && c !== "record_ref")
                        .slice(0, 8)
                        .map((c) => <th key={c}>{c}</th>)}
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.data.rows.map((r, i) => {
                      const added = r.record_source === "added";
                      const id = String(r[rows.data!.id_column] ?? "");
                      return (
                        <tr key={`${id}-${i}`}>
                          <td>
                            <span className={`pill ${added ? "amber" : "grey"}`}>
                              {added ? "added" : "original"}
                            </span>
                          </td>
                          {rows.data!.columns
                            .filter((c) => c !== "record_source" && c !== "record_ref")
                            .slice(0, 8)
                            .map((c) => (
                              <td key={c} className="small">{fmt(r[c])}</td>
                            ))}
                          <td className="nowrap">
                            <button className="btn ghost small" disabled={!added || busy}
                              title={added ? "Edit this row"
                                : "Original rows are immutable"}
                              onClick={() => {
                                const col = window.prompt(
                                  `Which column of ${id}?\n\n`
                                  + rows.data!.columns
                                    .filter((c) => c !== rows.data!.id_column
                                      && c !== "record_source" && c !== "record_ref")
                                    .join(", "));
                                if (!col) return;
                                const val = window.prompt(`New value for ${col}:`,
                                  String(r[col] ?? ""));
                                if (val === null) return;
                                patch.mutate({ rowId: id, body: { [col]: val } });
                              }}>Edit</button>
                            <button className="btn ghost small danger"
                              disabled={!added || busy}
                              title={added ? "Delete this row"
                                : "Original rows cannot be deleted"}
                              onClick={() => {
                                if (window.confirm(
                                  `Delete ${id} from ${sel.label}?\n\n`
                                  + "The file is backed up first, and the observation "
                                  + "that produced this row returns to unsynced.")) {
                                  del.mutate(id);
                                }
                              }}>Delete</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </TableScroll>
              <div className="row between">
                <span className="muted small">
                  {offset + 1}–{Math.min(offset + PAGE, rows.data.total)} of {rows.data.total}
                </span>
                <span className="row gap">
                  <button className="btn ghost" disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
                  <button className="btn ghost"
                    disabled={offset + PAGE >= rows.data.total}
                    onClick={() => setOffset(offset + PAGE)}>Next</button>
                </span>
              </div>
            </>
          )}
        </section>
      )}

      {/* ── the trained model ── */}
      {model.data && (
        <section className={`card ${model.data.unprotected ? "warn" : ""}`}>
          <h2>Trained model</h2>
          <p>{model.data.message}</p>
          <p className="muted small">
            {model.data.weight_files} weight file(s) are live. <b>They are not in
            git</b> — <code>ml.train</code> overwrites this directory in place, so a
            snapshot is the only way back. Nothing here currently needs retraining:
            ore zones, grades, the flow field and baselines are inputs the surrogate
            was already trained across.
          </p>
          <div className="row gap">
            <button className="btn primary" disabled={busy}
              onClick={() => backup.mutate("manual")}>Back up the model now</button>
          </div>

          {drift.data && (
            <>
              <div className="sec">Agreement with the analytical engine</div>
              <p className="muted small">
                The surrogate was trained on the engine's own output, so the engine
                is the reference. This compares the two on predictions served since
                this process started — <b>{drift.data.n_requests} so far</b>. It is
                in-process only, so it resets on restart and says nothing about
                runs served earlier.
              </p>
              <TableScroll>
                <table className="tbl compact">
                  <thead>
                    <tr><th>Metric</th><th>n</th><th>Median rel. diff</th>
                      <th>P90</th><th>State</th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(drift.data.per_metric).map(([k, m]) => (
                      <tr key={k}>
                        <td className="mono small">{k}</td>
                        <td>{m.n}</td>
                        <td>{(m.median_rel * 100).toFixed(1)}%</td>
                        <td>{(m.p90_rel * 100).toFixed(1)}%</td>
                        <td>
                          {m.n < drift.data!.min_samples
                            ? <span className="muted small">too few to judge</span>
                            : m.drifting
                              ? <span className="pill amber">⚠ drifting</span>
                              : <span className="pill green">✓ agrees</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
              <dl className="kv">
                <dt>Drift threshold</dt>
                <dd>{(drift.data.threshold_rel * 100).toFixed(0)}% relative,
                    after {drift.data.min_samples} samples</dd>
                <dt>Extrapolation rate</dt>
                <dd>{(drift.data.extrapolation_rate * 100).toFixed(1)}% — pins
                    outside trained support, where the conformal guarantee is void</dd>
                <dt>Off-scale rate</dt>
                <dd>{(drift.data.off_scale_rate * 100).toFixed(1)}%</dd>
              </dl>
              <p className="muted small">
                Sustained drift is the <b>only</b> signal here that would justify
                retraining. Syncing rows does not: ore zone, grade, flow field and
                baselines are inputs the surrogate was already trained across.
              </p>
            </>
          )}
          {model.data.backups.length > 0 && (
            <TableScroll>
              <table className="tbl compact">
                <thead>
                  <tr><th>Bundle</th><th>Created</th><th>Files</th><th>Size</th>
                    <th>Model card</th><th /></tr>
                </thead>
                <tbody>
                  {model.data.backups.map((b) => (
                    <tr key={b.name}>
                      <td className="mono small">{b.name}</td>
                      <td className="muted small">
                        {b.created_at ? new Date(b.created_at).toLocaleString() : "—"}
                      </td>
                      <td>{b.files}</td>
                      <td>{b.size_mb} MB</td>
                      <td className="mono small"
                          title="The same hash pinned onto every run computed with it">
                        {b.model_card_sha ? `${b.model_card_sha.slice(0, 12)}…` : "—"}
                      </td>
                      <td>
                        <button className="btn ghost small" disabled={busy}
                          onClick={() => {
                            if (window.confirm(
                              `Restore the model from ${b.name}?\n\n`
                              + "The version that is live now will be snapshotted "
                              + "first, so this is reversible.")) {
                              restoreModel.mutate(b.name);
                            }
                          }}>Restore</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </section>
      )}

      {/* ── the emergency path ── */}
      <section className="card danger-zone">
        <h2>Reset to the shipped datasets</h2>
        <p className="muted small">
          Removes <b>every</b> row marked “added” from every dataset, returning the
          files to exactly what shipped. Each file is backed up first, so this is
          reversible. <b>Field observations are kept</b> — they return to “approved,
          not yet in the model” and can be re-synced. Always dry-run first.
        </p>
        <div className="row gap">
          <button className="btn" disabled={busy} onClick={() => reset.mutate(true)}>
            Dry run — show me what would go
          </button>
          <button className="btn danger" disabled={busy}
            onClick={() => {
              if (window.prompt(
                "This removes every added row from every dataset.\n\n"
                + "Type RESET to confirm.") === "RESET") reset.mutate(false);
            }}>
            Reset datasets
          </button>
        </div>
      </section>
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  const s = String(v);
  return s.length > 40 ? `${s.slice(0, 38)}…` : s;
}
