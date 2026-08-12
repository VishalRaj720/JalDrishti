/**
 * Audit — who did what, when.
 *
 * Read-only by construction: there is no write or delete endpoint, and the
 * database has no UPDATE or DELETE policy on `audit_log`, so the trail cannot be
 * edited even by an administrator. Restricted to admin and regulator; analysts
 * and field officers appear IN the log and cannot read it.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type AuditEntry } from "../api/client";
import { Loading } from "../components/bits";

const ACTIONS = [
  "", "login", "login_failed", "access_denied",
  "field_observation.submit", "field_observation.approve", "field_observation.reject",
  "dataset.sync_ore", "simulation.queue", "simulation.completed", "scenario.create",
];

export default function Audit() {
  const [action, setAction] = useState("");
  const q = useQuery({
    queryKey: ["audit", action],
    queryFn: () => api.get<AuditEntry[]>(`/audit?limit=200${action ? `&action=${action}` : ""}`),
  });

  const tone = (a: string) =>
    a.includes("denied") || a.includes("failed") ? "danger"
      : a.includes("approve") || a.includes("sync") ? "ok"
      : a.includes("reject") ? "warn"
      : "info";

  return (
    <div className="page">
      <div className="page-head">
        <h1>Audit trail</h1>
        <p>
          Every decision, refusal and dataset change, with the old and new values
          involved. Append-only: no endpoint can modify or delete an entry.
        </p>
      </div>

      <div className="card">
        <div className="card-title">
          Filter
          <span className="spacer grow" />
          <span className="muted small">{q.data?.length ?? 0} entries</span>
        </div>
        <select value={action} onChange={(e) => setAction(e.target.value)}>
          {ACTIONS.map((a) => <option key={a} value={a}>{a || "all actions"}</option>)}
        </select>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {q.isLoading && <Loading />}
        {q.data?.length === 0 && (
          <div className="muted small" style={{ padding: 14 }}>No entries.</div>
        )}
        <table className="grid">
          <thead>
            <tr><th>When</th><th>Actor</th><th>Action</th><th>Entity</th><th>Detail</th></tr>
          </thead>
          <tbody>
            {q.data?.map((a) => (
              <tr key={a.id}>
                <td className="muted small" style={{ whiteSpace: "nowrap" }}>
                  {new Date(a.occurred_at).toLocaleString()}
                </td>
                <td className="small">{a.actor_label ?? <span className="muted">system</span>}</td>
                <td><span className={`chip ${tone(a.action)}`}>{a.action}</span></td>
                <td className="mono">{a.entity_type}</td>
                <td
                  className="mono"
                  style={{ maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  title={JSON.stringify(a.detail)}
                >
                  {a.detail ? JSON.stringify(a.detail) : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
