/**
 * Data & Gaps — the proposal's second deliverable, given its own screen.
 *
 * "Identify key data gaps and recommend improved monitoring strategies" is a
 * stated objective, not a footnote, so coverage and provenance are a
 * destination here rather than a caption somewhere else. This screen also owns
 * the dataset sync, because the sync is the moment the portal's record and the
 * model's inputs are reconciled.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type GapMatrix, type Recommendations, type PublicDistrictRisk, type SyncStatus } from "../api/client";
import { canSync, useAuth } from "../auth";
import { ErrorNote, Loading, Planned, TableScroll, Tile } from "../components/bits";
import SiteSuggestionMap from "../console/SiteSuggestionMap";

interface PendingItem {
  id: string; observation_type: string; operation: string;
  target_table: string; reviewed_at: string | null;
  submitted_by_email: string | null; reviewed_by_email: string | null;
}

export default function DataGaps() {
  const { me } = useAuth();
  const qc = useQueryClient();

  const sync = useQuery({ queryKey: ["sync-status"], queryFn: () => api.get<SyncStatus>("/dataset-sync/status") });
  const pending = useQuery({
    queryKey: ["sync-pending"],
    queryFn: () => api.get<{ count: number; items: PendingItem[]; syncable_types: string[] }>("/dataset-sync/pending"),
  });
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });
  const dq = useQuery({
    queryKey: ["dq-report"],
    queryFn: () => api.get<any>("/ingest/data-quality-report"),
    retry: false,
  });

  const runSync = useMutation({
    mutationFn: () => api.post<{ message: string; synced: number; retrain_required: boolean }>("/dataset-sync/ore"),
    onSuccess: () => ["sync-status", "sync-pending", "obs-map", "obs"].forEach(
      (k) => qc.invalidateQueries({ queryKey: [k] })),
  });

  const districts = risk.data?.districts ?? [];
  const noData = districts.filter((d) => d.samples === 0);
  const thin = districts.filter((d) => d.samples > 0 && d.wells < 10);
  const covered = districts.filter((d) => d.wells >= 10);

  const [siteFor, setSiteFor] = useState<{ id: string; name: string } | null>(null);

  /** One column per KIND of gap. Each carries the capability it denies and the
   *  limitation it forces, so LIMITATIONS.md can be read off the data instead of
   *  maintained by hand. */
  const matrix = useQuery({
    queryKey: ["gap-matrix"],
    queryFn: () => api.get<GapMatrix>("/data-gaps/matrix"),
  });

  const recs = useQuery({
    queryKey: ["gap-recommendations"],
    queryFn: () => api.get<Recommendations>("/data-gaps/recommendations?limit=20"),
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Data & Gaps</h1>
        <p>
          Where the monitoring network is thin enough that a prediction should not be
          trusted — and the point at which approved field evidence reaches the model.
        </p>
      </div>

      {/* ── the deficiency matrix ──
          Counts alone are a statistic. Each column here carries what it denies
          and what it forces the project to admit, which is what turns a gap into
          a limitation. */}
      {matrix.data && (
        <section className="card">
          <h2>Data deficiencies, by kind</h2>
          <p className="muted small">{matrix.data.what_this_is}</p>

          <TableScroll>
            <table className="grid">
              <thead>
                <tr>
                  <th>District</th>
                  <th>Blocks</th>
                  <th>Wells</th>
                  {matrix.data.dimensions.map((d) => (
                    <th key={d.key} title={d.means}>{d.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr style={{ fontWeight: 600 }}>
                  <td>ALL JHARKHAND</td>
                  <td>{matrix.data.totals.blocks}</td>
                  <td>{matrix.data.totals.wells}</td>
                  {matrix.data.dimensions.map((d) => (
                    <td key={d.key} className={matrix.data!.totals[d.key] > 0 ? "warn-text" : ""}>
                      {matrix.data!.totals[d.key]}
                    </td>
                  ))}
                </tr>
                {matrix.data.districts.map((r) => (
                  <tr key={r.district}>
                    <td>{r.district}</td>
                    <td className="muted">{r.blocks}</td>
                    <td className="muted">{r.wells}</td>
                    {matrix.data!.dimensions.map((d) => (
                      <td key={d.key}
                          className={Number(r[d.key] ?? 0) > 0 ? "warn-text" : "muted"}>
                        {r[d.key] ?? 0}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>

          <div className="sec">What each column limits</div>
          <p className="muted small">
            This is the register in <code>docs/LIMITATIONS.md</code>, derived from
            the data rather than maintained by hand. A gap nobody can name the
            effect of is a statistic; a gap with its effect beside it is a
            limitation.
          </p>
          {matrix.data.dimensions.map((d) => (
            <div key={d.key} className="banner" style={{ marginBottom: 8 }}>
              <b>{d.label} — {matrix.data!.totals[d.key]}</b>
              <div className="muted small" style={{ marginTop: 4 }}>{d.means}</div>
              <div className="small" style={{ marginTop: 4 }}>
                <b>Prevents:</b> {d.blocks}
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                <b>So the project must say:</b> {d.implies}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* ── where to sample next: the proposal's recommendation half ── */}
      <section className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Where to sample next</h2>
          <Link className="btn" to="/network-plan">Open the full map →</Link>
        </div>
        <p className="muted small">
          {recs.data?.what_this_is}
        </p>
        {recs.isLoading && <Loading />}
        {recs.error && <ErrorNote error={recs.error} />}
        {recs.data && (
          <>
            <TableScroll>
              <table className="grid">
                <thead>
                  <tr>
                    <th>#</th><th>Priority</th><th>Block</th><th>District</th>
                    <th>Area</th><th>Wells</th><th>U tests</th><th>Why</th><th />
                  </tr>
                </thead>
                <tbody>
                  {recs.data.recommendations.map((r, i) => (
                    <tr key={r.id}>
                      <td className="muted">{i + 1}</td>
                      <td><b>{r.score.toFixed(0)}</b></td>
                      <td>{r.name}</td>
                      <td className="muted small">{r.district}</td>
                      <td className="small">{r.area_km2?.toFixed(0)} km²</td>
                      <td className={r.wells === 0 ? "warn-text" : ""}>{r.wells}</td>
                      <td className={r.uranium_tests === 0 ? "warn-text" : ""}>
                        {r.uranium_tests}
                      </td>
                      <td className="small muted">{r.reason}</td>
                      <td>
                        <button className="btn ghost small"
                          onClick={() => setSiteFor(
                            siteFor?.id === r.id ? null : { id: r.id, name: r.name })}>
                          {siteFor?.id === r.id ? "Hide" : "Where exactly?"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>

            {siteFor && (
              <div className="card" style={{ marginTop: 12 }}>
                <div className="row between">
                  <div className="sec" style={{ margin: 0 }}>
                    Where to put a well in {siteFor.name}
                  </div>
                  <button className="btn ghost" onClick={() => setSiteFor(null)}>Close</button>
                </div>
                <SiteSuggestionMap blockId={siteFor.id} />
              </div>
            )}

            <details style={{ marginTop: 10 }}>
              <summary className="muted small">
                How this is scored — these weights are a policy judgement, not a
                measurement
              </summary>
              <dl className="kv" style={{ marginTop: 8 }}>
                {Object.entries(recs.data.weights).map(([k, w]) => (
                  <div key={k}>
                    <dt>{k.replace(/_/g, " ")} · {w.weight}</dt>
                    <dd className="small muted">{w.why}</dd>
                  </div>
                ))}
              </dl>
              <p className="muted small">{recs.data.tie_break}</p>
            </details>
          </>
        )}
      </section>

      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={noData.length} label="Districts with no samples" tone="red"
              sub="a gap, not a clean result" />
        <Tile n={thin.length} label="Districts with fewer than 10 wells" tone="amber"
              sub="sparse coverage" />
        <Tile n={covered.length} label="Districts adequately sampled" tone="green" />
        <Tile n={sync.data?.approved_pending_sync ?? "–"} label="Approved, not in model" tone="amber"
              sub="awaiting dataset sync" />
      </div>

      {/* The sync — where the portal's record and the model's inputs reconcile. */}
      <div className="card">
        <div className="card-title">
          Dataset sync
          <span className="spacer grow" />
          {sync.data && (
            <span className={`chip ${sync.data.approved_pending_sync ? "warn" : "ok"}`}>
              {sync.data.approved_pending_sync ? "🟡 behind" : "🟢 in sync"}
            </span>
          )}
        </div>

        {sync.isLoading && <Loading />}
        {sync.data && (
          <>
            <div className="row wrap" style={{ gap: 14, marginBottom: 10 }}>
              <span className="chip danger">🔴 {sync.data.pending_review} pending review</span>
              <span className="chip warn">🟡 {sync.data.approved_pending_sync} approved, not in model</span>
              <span className="chip ok">🟢 {sync.data.approved_in_model} in model</span>
            </div>
            <div className="muted small" style={{ lineHeight: 1.6, marginBottom: 11 }}>
              {sync.data.note}
            </div>

            {canSync(me?.role) ? (
              <>
                <button className="btn primary" disabled={runSync.isPending || !sync.data.approved_pending_sync}
                        onClick={() => runSync.mutate()}>
                  {runSync.isPending ? "Syncing…" : "Sync approved ore observations → Datasets/"}
                </button>
                <div className="muted small" style={{ marginTop: 7 }}>
                  Appends to the deposit CSV and the grade workbook, tagging each new row
                  <span className="mono"> origin=added</span>. Both files are backed up
                  first. This changes a <em>resolved input</em>, not the trained model —
                  no retrain is triggered.
                </div>
              </>
            ) : (
              <div className="muted small">
                Only an administrator can run the sync. Ask one to reconcile the
                {" "}{sync.data.approved_pending_sync} outstanding item(s).
              </div>
            )}
            {runSync.data && (
              <div className="banner ok" style={{ marginTop: 10 }}>
                ✅ {runSync.data.message} · retrain required:{" "}
                <strong>{String(runSync.data.retrain_required)}</strong>
              </div>
            )}
            <ErrorNote error={runSync.error} />
          </>
        )}
      </div>

      {(pending.data?.count ?? 0) > 0 && (
        <div className="card">
          <div className="card-title">
            Approved but not yet in the model
            <span className="spacer grow" />
            <span className="muted small">
              only {pending.data?.syncable_types.join(", ")} syncs automatically
            </span>
          </div>
          <table className="grid">
            <thead>
              <tr><th>Type</th><th>Operation</th><th>Target</th><th>Approved</th><th>By</th></tr>
            </thead>
            <tbody>
              {pending.data?.items.map((i) => (
                <tr key={i.id}>
                  <td>{i.observation_type.replace(/_/g, " ")}</td>
                  <td>{i.operation}</td>
                  <td className="mono">{i.target_table}</td>
                  <td className="muted">{i.reviewed_at ? new Date(i.reviewed_at).toLocaleDateString() : "–"}</td>
                  <td className="muted small">{i.reviewed_by_email ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted small" style={{ marginTop: 8 }}>
            Anything outside the syncable types is applied by hand from the audit trail —
            those changes move a value the model was already trained across, so they are
            rare and deliberate.
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-title">Monitoring coverage by district</div>
        {risk.isLoading && <Loading />}
        <table className="grid">
          <thead>
            <tr><th>District</th><th>Wells</th><th>Samples</th><th>Max uranium (ppb)</th><th>Coverage</th></tr>
          </thead>
          <tbody>
            {[...districts].sort((a, b) => a.wells - b.wells).map((d) => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td className="mono">{d.wells}</td>
                <td className="mono">{d.samples}</td>
                <td className="mono">{d.max_uranium_ppb ?? "–"}</td>
                <td>
                  {d.samples === 0 ? <span className="chip danger">no data</span>
                    : d.wells < 10 ? <span className="chip warn">sparse</span>
                    : <span className="chip ok">adequate</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dq.data && (
        <div className="card">
          <div className="card-title">Data-quality report</div>
          <div className="muted small" style={{ marginBottom: 8 }}>
            Generated by the seed/ingest pipeline.
          </div>
          <pre className="mono" style={{ maxHeight: 260, overflow: "auto", margin: 0 }}>
            {JSON.stringify(dq.data.row_counts ?? dq.data, null, 1)}
          </pre>
        </div>
      )}

      <Planned label="Recommended monitoring plan — where to place the next well"
               phase="objective 2"
               why="Coverage is reported above, but ranking candidate locations needs an optimisation the backend does not implement." />
    </div>
  );
}
