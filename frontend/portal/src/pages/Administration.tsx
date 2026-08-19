/**
 * Administration — accounts and roles.
 *
 * Deliberately thin. Account creation exists because the invitation flow the
 * design specifies does not, and an administrator otherwise has no way to
 * onboard anyone; it is labelled as the interim path rather than presented as
 * the intended one.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Role } from "../api/client";
import { ROLE_COLOUR, ROLE_LABEL } from "../auth";
import { ErrorNote, Loading, Planned , TableScroll } from "../components/bits";

interface U { id: string; username: string; email: string; role: Role }
// `regulator` is NOT offered. R7 retired it — every power it had, admin already
// had — and leaving it selectable let an operator assign a role the application
// no longer recognises, whose label ("Administrator (former regulator)") was
// itself an admission that it should not exist. The enum value survives in
// Postgres only because a value cannot be dropped transactionally.
const ROLES: Role[] = ["admin", "analyst", "field_officer", "citizen"];


/**
 * R9: the measured-alert scan, which had no trigger anywhere in the product.
 *
 * `POST /citizen/alerts/scan-measured` reads the CGWB water-quality table and
 * raises an alert for every well whose most recent sample exceeds the 30 ppb
 * uranium limit. Those are real laboratory results about water people drink
 * today — the truest thing this platform holds — and until now the only way to
 * fire it was to call the API by hand.
 *
 * Triggered rather than scheduled because this deployment has no scheduler, and
 * a cron job that silently stops is worse than a button nobody pressed: the
 * button's absence is at least visible.
 */
function MeasuredScan() {
  const scan = useMutation({
    mutationFn: () => api.post<{
      wells_over_limit: number; alerts_created: number; limit_ppb: number; note: string;
    }>("/citizen/alerts/scan-measured"),
  });

  return (
    <div className="card">
      <div className="card-title">Measured-exceedance alerts</div>
      <div className="prose muted" style={{ marginBottom: 10 }}>
        Scans government water-quality results and raises an alert for every
        monitoring well whose most recent sample is above the uranium safe limit.
        Residents following that block see it in their alerts. These are real
        laboratory results, not model output.
      </div>
      <button className="btn primary" disabled={scan.isPending}
              onClick={() => scan.mutate()}>
        {scan.isPending ? "Scanning…" : "Scan for exceedances now"}
      </button>
      <ErrorNote error={scan.error} />
      {scan.data && (
        <div className={`banner ${scan.data.alerts_created ? "warn" : "ok"}`}
             style={{ marginTop: 10 }}>
          <strong>
            {scan.data.wells_over_limit} well(s) above {scan.data.limit_ppb} ppb ·{" "}
            {scan.data.alerts_created} new alert(s).
          </strong>
          <div className="muted small" style={{ marginTop: 4 }}>{scan.data.note}</div>
        </div>
      )}
      <div className="muted small" style={{ marginTop: 8 }}>
        Safe to run repeatedly — an alert already raised for a well and sample date
        is not raised twice, so nobody is warned about the same reading again.
      </div>
    </div>
  );
}

/**
 * R9: the data-gap report, a NAMED PROPOSAL DELIVERABLE that was unreachable.
 *
 * `GET /ingest/data-quality-report` exists and nothing linked to it. "Identify
 * key data gaps in hydrogeological systems and recommend improved monitoring
 * strategies" is objective two of the funded proposal, and the portal was
 * computing the answer and showing it to nobody.
 */
function DataGapReport() {
  const report = useQuery({
    queryKey: ["data-quality"],
    queryFn: () => api.get<Record<string, any>>("/ingest/data-quality-report"),
    retry: false,
  });

  return (
    <div className="card">
      <div className="card-title">Data-gap report</div>
      <div className="prose muted" style={{ marginBottom: 10 }}>
        Where the monitoring network is thin. A gap is not a clean result — it is a
        place nobody has looked, and naming those is one of this project&apos;s stated
        objectives.
      </div>
      {report.isLoading && <Loading />}
      <ErrorNote error={report.error} />
      {report.data && (
        <TableScroll>
          <table className="grid">
            <tbody>
              {Object.entries(report.data).map(([k, v]) => (
                <tr key={k}>
                  <td>{k.replace(/_/g, " ")}</td>
                  <td className="mono">
                    {typeof v === "object" && v !== null
                      ? JSON.stringify(v).slice(0, 160)
                      : String(v)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}
    </div>
  );
}

export default function Administration() {
  const qc = useQueryClient();
  const [f, setF] = useState({ username: "", email: "", password: "", role: "citizen" as Role });

  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<U[]>("/users") });

  const create = useMutation({
    mutationFn: () => api.post<U>("/users", f),
    onSuccess: () => {
      setF({ username: "", email: "", password: "", role: "citizen" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.del(`/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const byRole = (r: Role) => (users.data ?? []).filter((u) => u.role === r).length;

  return (
    <div className="page">
      <MeasuredScan />
      <DataGapReport />
      <div className="page-head">
        <h1>Administration</h1>
        <p>Accounts and role assignment. Every action here is written to the audit trail.</p>
      </div>

      <div className="grid-4" style={{ marginBottom: 16 }}>
        {ROLES.slice(0, 4).map((r) => (
          <div className="tile" key={r}>
            <div className="tile-n" style={{ color: ROLE_COLOUR[r] }}>{byRole(r)}</div>
            <div className="tile-l">{ROLE_LABEL[r]}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Create an account</div>
        <div className="grid-4">
          <div className="field">
            <label>Username</label>
            <input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
          </div>
          <div className="field">
            <label>Email</label>
            <input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </div>
          <div className="field">
            <label>Password</label>
            <input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </div>
          <div className="field">
            <label>Role</label>
            <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </select>
          </div>
        </div>
        <button
          className="btn primary"
          disabled={!f.username || !f.email || !f.password || create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Creating…" : "Create account"}
        </button>
        <ErrorNote error={create.error} />
        <div className="muted small" style={{ marginTop: 8 }}>
          Interim path. The design replaces this with organisation invitations so a
          password is never handled by an administrator; that flow is not built. Note
          the API rejects <span className="mono">.local</span> addresses, so the seeded
          demo accounts cannot be recreated here.
        </div>
      </div>

      <div className="card" style={{ padding: 0 }}>
        {users.isLoading && <Loading />}
        <table className="grid">
          <thead><tr><th>User</th><th>Email</th><th>Role</th><th /></tr></thead>
          <tbody>
            {users.data?.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td className="mono">{u.email}</td>
                <td>
                  <span className="role-pill" style={{ color: ROLE_COLOUR[u.role] }}>
                    {ROLE_LABEL[u.role]}
                  </span>
                </td>
                <td style={{ textAlign: "right" }}>
                  <button className="btn ghost danger" onClick={() => remove.mutate(u.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ErrorNote error={remove.error} />

      <Planned
        label="Organisation invitations, API keys and rate-limit tiers"
        phase="P2 follow-up"
        why="Organisations exist in the schema and users are assigned to one, but there is no invitation or key-management endpoint."
      />
      <Planned
        label="Bulk data ingest (GeoJSON / CSV upload)"
        phase="admin tooling"
        why="The five ingest endpoints exist and are admin-only; the upload UI is not built."
      />
    </div>
  );
}
