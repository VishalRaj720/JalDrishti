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
import { api, type DeliveryResult, type DeliveryStatus, type Role } from "../api/client";
import { ROLE_COLOUR, ROLE_LABEL } from "../auth";
import { ErrorNote, Loading, Planned , TableScroll } from "../components/bits";

interface U { id: string; username: string; email: string; role: Role }
/**
 * ASSIGNABLE roles. `admin` is deliberately absent.
 *
 * R12. There is exactly one administrator — the account that operates the
 * dataset pipeline, the factory reset and the model. A second is not a
 * convenience, it is a second person who can rewrite the evidence base. The
 * backend refuses to create or promote one (`UserService._refuse_second_admin`)
 * and a partial unique index in migration 0022 refuses it again below the
 * application, so leaving it in this dropdown would only offer an operator a
 * choice guaranteed to fail.
 *
 * `regulator` IS offered, and is the answer to "I need a second person who can
 * approve submissions". There may be as many as needed.
 *
 * `viewer` is absent because migration 0008 replaced it with `citizen`.
 */
const ROLES: Role[] = ["regulator", "analyst", "field_officer", "citizen"];

/** Counted on the summary tiles — includes `admin`, which exists and should be
 *  visible, even though it cannot be assigned from here. */
const COUNTED: Role[] = ["admin", "regulator", "analyst", "field_officer", "citizen"];


/**
 * R9: the measured-alert scan, which had no trigger anywhere in the product.
 * R16: it also runs on a schedule (`ALERT_SCAN_INTERVAL_HOURS`), and raising
 * is now half the job -- the panel below it shows whether what was raised
 * actually went out.
 *
 * `POST /citizen/alerts/scan-measured` reads the CGWB water-quality table and
 * raises an alert for every well whose most recent sample exceeds a health
 * limit (uranium, nitrate, fluoride, arsenic, iron). Those are real laboratory
 * results about water people drink today -- the truest thing this platform
 * holds.
 */
function MeasuredScan() {
  const qc = useQueryClient();
  const scan = useMutation({
    mutationFn: () => api.post<{
      wells_over_limit: number; alerts_created: number; note: string;
      delivery?: DeliveryResult;
    }>("/citizen/alerts/scan-measured"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["delivery-status"] }),
  });

  return (
    <div className="card">
      <div className="card-title">Measured-exceedance alerts</div>
      <div className="prose muted" style={{ marginBottom: 10 }}>
        Scans government water-quality results and raises an alert for every
        monitoring well whose most recent sample is above a drinking-water health
        limit. Residents following that block see it in their alerts and receive it
        by email. These are real laboratory results, not model output. Runs
        automatically on a schedule; this button runs it now.
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
            {scan.data.wells_over_limit} well(s) over a limit ·{" "}
            {scan.data.alerts_created} new alert(s)
            {scan.data.delivery && ` · ${scan.data.delivery.sent} emailed`}
            {scan.data.delivery && !scan.data.delivery.configured && " · email not configured"}.
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
 * R16: who was told, and whether the channel is even connected.
 *
 * `pending` is the number that matters. It counts alerts that exist, have a
 * subscriber with an address, and have not gone out. With no SMTP host it
 * grows and says so; a stopped scheduler shows the same way. "Configuration
 * that enforces nothing" is the failure this codebase has had three times,
 * and the cure each time was a visible number.
 */
function AlertDelivery() {
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["delivery-status"],
    queryFn: () => api.get<DeliveryStatus>("/citizen/alerts/delivery-status"),
    refetchInterval: 60_000,
  });
  const deliver = useMutation({
    mutationFn: () => api.post<DeliveryResult>("/citizen/alerts/deliver"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["delivery-status"] }),
  });
  const breach = useMutation({
    mutationFn: (dry: boolean) => api.post<{
      published_screenings: number; assessable: number; due_now: number;
      alerts_created: number; dry_run: boolean; considered: Array<Record<string, unknown>>;
      skipped: Array<Record<string, unknown>>;
    }>(`/citizen/alerts/scan-breach-due?dry_run=${dry}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["delivery-status"] }),
  });
  const d = status.data;

  return (
    <div className="card">
      <div className="card-title">
        Alert delivery
        <span className="spacer grow" />
        {d && (
          <span className={`chip ${d.configured ? "ok" : "warn"}`}>
            {d.configured ? `Email via ${d.provider_host}` : "Email not configured"}
          </span>
        )}
      </div>
      {status.isLoading && <Loading />}
      <ErrorNote error={status.error} />
      {d && (
        <>
          <div className="grid-5" style={{ marginBottom: 10 }}>
            <div className="tile"><div className="tile-n">{d.alerts_total}</div><div className="tile-l">alerts raised</div></div>
            <div className="tile"><div className="tile-n">{d.subscribers}</div><div className="tile-l">people following {d.blocks_followed} blocks</div></div>
            <div className="tile"><div className="tile-n" style={{ color: "var(--ok)" }}>{d.sent}</div><div className="tile-l">emails sent</div></div>
            <div className="tile"><div className="tile-n" style={{ color: d.pending ? "var(--warn)" : undefined }}>{d.pending}</div><div className="tile-l">waiting to go out</div></div>
            <div className="tile"><div className="tile-n" style={{ color: d.failed ? "var(--danger)" : undefined }}>{d.failed}</div><div className="tile-l">failed</div></div>
          </div>
          {!d.configured && (
            <div className="banner warn" style={{ marginBottom: 10 }}>
              <strong>No email relay is configured.</strong> Alerts still reach the
              portal inbox; {d.pending} are waiting for a relay. Set <code>SMTP_HOST</code>,{" "}
              <code>SMTP_USER</code>, <code>SMTP_PASSWORD</code> and <code>ALERT_FROM_EMAIL</code>{" "}
              on the API host — Brevo's free relay is 300 messages a day.
            </div>
          )}
          <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn primary" disabled={deliver.isPending || !d.configured}
                    onClick={() => deliver.mutate()}>
              {deliver.isPending ? "Sending…" : "Send waiting emails now"}
            </button>
            <button className="btn" disabled={breach.isPending}
                    onClick={() => breach.mutate(true)}>
              Check screening timetables (dry run)
            </button>
            {breach.data?.dry_run && breach.data.due_now > 0 && (
              <button className="btn danger" disabled={breach.isPending}
                      onClick={() => {
                        if (window.confirm(
                          `Raise ${breach.data!.due_now} timetable-passed alert(s) for real? ` +
                          "These go to residents and are the only alert that fires without " +
                          "anyone having acted.")) breach.mutate(false);
                      }}>
                Raise {breach.data.due_now} due alert(s)
              </button>
            )}
          </div>
          <ErrorNote error={deliver.error} />
          <ErrorNote error={breach.error} />
          {deliver.data && (
            <div className="banner ok" style={{ marginTop: 10 }}>
              Sent {deliver.data.sent}, failed {deliver.data.failed}, skipped{" "}
              {deliver.data.skipped} (demo addresses), still waiting {deliver.data.pending}.
            </div>
          )}
          {breach.data && (
            <div className={`banner ${breach.data.due_now ? "warn" : ""}`} style={{ marginTop: 10 }}>
              <strong>
                {breach.data.published_screenings} published screening(s) ·{" "}
                {breach.data.due_now} past their modelled timetable
                {breach.data.dry_run ? " (dry run — nothing raised)" : ` · ${breach.data.alerts_created} alert(s) raised`}.
              </strong>
              {breach.data.considered.length > 0 && (
                <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                  {breach.data.considered.map((c, i) => (
                    <li key={i}>
                      {String(c.site)}: {String(c.reason).replace(/_/g, " ")}
                      {c.due_in_years != null && ` — due in ${String(c.due_in_years)} yr`}
                      {c.elapsed_years != null && ` (${String(c.elapsed_years)} yr elapsed of ${String(c.years_to_breakthrough)})`}
                    </li>
                  ))}
                </ul>
              )}
              {breach.data.skipped.length > 0 && (
                <div className="muted small" style={{ marginTop: 4 }}>
                  Skipped {breach.data.skipped.length}:{" "}
                  {breach.data.skipped.map((k) => `${String(k.site)} (${String(k.reason).replace(/_/g, " ")})`).join("; ")}.
                </div>
              )}
            </div>
          )}
          <div className="muted small" style={{ marginTop: 8 }}>
            {d.note} Scheduler: every {d.scheduler_interval_hours} h
            {d.last_sent_at && ` · last email ${new Date(d.last_sent_at).toLocaleString()}`}.
          </div>
        </>
      )}
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

  /** `PUT /users/{id}` has always existed and nothing called it, so the only
   *  way to change somebody's role was to delete the account and recreate it —
   *  which loses the identity every audit entry is attributed to. Role is the
   *  one field worth editing in place; username and email are identity, and
   *  password resets belong in the invitation flow the design calls for. */
  const setRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) =>
      api.put(`/users/${id}`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  const byRole = (r: Role) => (users.data ?? []).filter((u) => u.role === r).length;

  return (
    <div className="page">
      <AlertDelivery />
      <MeasuredScan />
      <DataGapReport />
      <div className="page-head">
        <h1>Administration</h1>
        <p>Accounts and role assignment. Every action here is written to the audit trail.</p>
      </div>

      <div className="grid-5" style={{ marginBottom: 16 }}>
        {COUNTED.map((r) => (
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
            <input type="text" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
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
                  <div className="row">
                    <span className="role-pill" style={{ color: ROLE_COLOUR[u.role] }}>
                      {ROLE_LABEL[u.role]}
                    </span>
                    {/* NO role control for an administrator.
                        `ROLES` deliberately omits `admin` — migration 0022 pins
                        the account to exactly one, and it is created by
                        `scripts/bootstrap_admin`, not assigned from a dropdown.
                        Rendering the select anyway was a bug caught in
                        verification: with no matching <option>, the browser
                        falls back to the FIRST one, so the sole administrator's
                        row displayed "Regulator" and a stray change event would
                        have demoted them with no way back through this UI. */}
                    {u.role === "admin" ? (
                      <span className="muted small">
                        Set by <code>scripts/bootstrap_admin</code>; exactly one
                        account holds it.
                      </span>
                    ) : (
                    <select
                      value={u.role}
                      disabled={setRole.isPending}
                      aria-label={`Change role for ${u.username}`}
                      onChange={(e) => {
                        const role = e.target.value as Role;
                        if (role === u.role) return;
                        if (window.confirm(
                          `Change ${u.username} from ${ROLE_LABEL[u.role]} to `
                          + `${ROLE_LABEL[role]}?

The new role takes effect on `
                          + `their very next request — the role is re-read from the `
                          + `database rather than trusted from their token, so they `
                          + `do not need to sign in again.`)) {
                          setRole.mutate({ id: u.id, role });
                        } else {
                          e.target.value = u.role;   // revert the visible choice
                        }
                      }}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                      ))}
                    </select>
                    )}
                  </div>
                </td>
                <td style={{ textAlign: "right" }}>
                  {/* Was a one-click delete with no confirmation at all. */}
                  <button
                    className="btn ghost danger"
                    disabled={remove.isPending || u.role === "admin"}
                    title={u.role === "admin"
                      ? "The sole administrator cannot be removed here — you would lock yourself out of every admin surface."
                      : undefined}
                    onClick={() => {
                      if (window.prompt(
                        `Delete the account ${u.email}?

`
                        + `Their past actions stay in the audit trail, but the `
                        + `account itself is gone and cannot be restored.

`
                        + `Type DELETE to confirm.`) === "DELETE") {
                        remove.mutate(u.id);
                      }
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ErrorNote error={remove.error} />
      <ErrorNote error={setRole.error} />

      <Planned
        label="Organisation invitations, API keys and rate-limit tiers"
        phase="P2 follow-up"
        why="Organisations exist in the schema and users are assigned to one, but there is no invitation or key-management endpoint."
      />
      {/* Built 2026-08-24 — see pages/Ingest.tsx. The five endpoints had been
          admin-only and callable only by curl. */}
    </div>
  );
}
