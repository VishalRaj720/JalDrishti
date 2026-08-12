import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type SyncStatus } from "../api/client";
import { canSync, useAuth } from "../auth";

interface Observation {
  id: string;
  observation_type: string;
  operation: string;
  target_table: string;
  previous: Record<string, unknown> | null;
  proposed: Record<string, unknown> | null;
  status: string;
  submitted_by: string;
  submitted_at: string;
}

/**
 * The reviewer's screen: the red queue, and the amber backlog beneath it.
 *
 * Both are shown together on purpose. Approving something moves it from red to
 * amber, not to done, and a reviewer who cannot see the amber pile has no way
 * to know the model is drifting behind the record.
 */
export default function ReviewQueue() {
  const { me } = useAuth();
  const qc = useQueryClient();

  const pending = useQuery({
    queryKey: ["obs", "pending"],
    queryFn: () => api.get<Observation[]>("/field-observations?status=pending"),
  });
  const sync = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => api.get<SyncStatus>("/dataset-sync/status"),
  });

  const decide = useMutation({
    mutationFn: ({ id, verb }: { id: string; verb: "approve" | "reject" }) =>
      api.post(`/field-observations/${id}/${verb}`, { review_note: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["obs", "pending"] });
      qc.invalidateQueries({ queryKey: ["sync-status"] });
      qc.invalidateQueries({ queryKey: ["obs-map"] });
    },
  });

  const runSync = useMutation({
    mutationFn: () => api.post<{ message: string }>("/dataset-sync/ore"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sync-status"] });
      qc.invalidateQueries({ queryKey: ["obs-map"] });
    },
  });

  return (
    <div className="page">
      <h1>Review queue</h1>
      <p className="lede">
        Field observations become authoritative only once a reviewer accepts them —
        and reach the model only after a dataset sync.
      </p>

      {sync.data && (
        <div
          className={sync.data.approved_pending_sync ? "notice" : "card"}
          style={{ marginBottom: "var(--sp-6)" }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <div>
              <strong>
                🔴 {sync.data.pending_review} pending · 🟡{" "}
                {sync.data.approved_pending_sync} approved, not in model · 🟢{" "}
                {sync.data.approved_in_model} in model
              </strong>
              <div style={{ marginTop: 4 }}>{sync.data.note}</div>
            </div>
            {canSync(me?.role) && sync.data.approved_pending_sync > 0 && (
              <button
                className="primary"
                style={{ whiteSpace: "nowrap", height: "fit-content" }}
                disabled={runSync.isPending}
                onClick={() => runSync.mutate()}
              >
                {runSync.isPending ? "Syncing…" : "Sync ore → Datasets/"}
              </button>
            )}
          </div>
          {runSync.data && (
            <div style={{ marginTop: "var(--sp-3)" }}>✅ {runSync.data.message}</div>
          )}
        </div>
      )}

      <div className="rail-section-label" style={{ padding: "0 0 var(--sp-2)" }}>
        🔴 Awaiting review
      </div>

      {pending.isLoading && <div className="muted"><span className="spinner" /> Loading…</div>}
      {pending.data?.length === 0 && (
        <div className="card muted">Nothing awaiting review.</div>
      )}

      {pending.data?.map((o) => (
        <div className="card" key={o.id} style={{ marginBottom: "var(--sp-4)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <div>
              <strong>
                {o.operation} · {o.observation_type}
              </strong>
              <div className="muted">
                into <span className="mono">{o.target_table}</span> ·{" "}
                {new Date(o.submitted_at).toLocaleString()}
              </div>
            </div>
            <div style={{ display: "flex", gap: "var(--sp-2)", height: "fit-content" }}>
              <button
                className="primary"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, verb: "approve" })}
              >
                Approve
              </button>
              <button
                className="linkish"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: o.id, verb: "reject" })}
              >
                Reject
              </button>
            </div>
          </div>

          {/* Old vs new, straight from the proposal row — the reviewer decides
              on the actual diff, not on a summary of it. */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "var(--sp-4)",
              marginTop: "var(--sp-4)",
            }}
          >
            <div>
              <div className="muted" style={{ marginBottom: 4 }}>Current</div>
              <pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {o.previous ? JSON.stringify(o.previous, null, 1) : "— new record —"}
              </pre>
            </div>
            <div>
              <div className="muted" style={{ marginBottom: 4 }}>Proposed</div>
              <pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                {o.proposed ? JSON.stringify(o.proposed, null, 1) : "— deletion —"}
              </pre>
            </div>
          </div>
        </div>
      ))}

      {decide.isError && (
        <div className="error">{(decide.error as Error).message}</div>
      )}
    </div>
  );
}
