/**
 * Data & Gaps — the proposal's second deliverable, given its own screen.
 *
 * "Identify key data gaps and recommend improved monitoring strategies" is a
 * stated objective, not a footnote, so coverage and provenance are a
 * destination here rather than a caption somewhere else. This screen also owns
 * the dataset sync, because the sync is the moment the portal's record and the
 * model's inputs are reconciled.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type PublicDistrictRisk, type SyncStatus } from "../api/client";
import { canSync, useAuth } from "../auth";
import { ErrorNote, Loading, Planned, Tile } from "../components/bits";

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

  return (
    <div className="page">
      <div className="page-head">
        <h1>Data & Gaps</h1>
        <p>
          Where the monitoring network is thin enough that a prediction should not be
          trusted — and the point at which approved field evidence reaches the model.
        </p>
      </div>

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
