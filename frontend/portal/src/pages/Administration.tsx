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
import { ErrorNote, Loading, Planned } from "../components/bits";

interface U { id: string; username: string; email: string; role: Role }
const ROLES: Role[] = ["admin", "regulator", "analyst", "field_officer", "citizen"];

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
