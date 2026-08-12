import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Role, type SyncStatus } from "../api/client";
import {
  ROLE_COLOUR, ROLE_LABEL, canAdmin, canAudit, canReview, canRunSim,
  canSubmit, isStaff, useAuth,
} from "../auth";

/** Section list, filtered by role — the `roleReq` pattern from the prototype. */
function sectionsFor(role: Role | undefined) {
  const s: Array<{ to: string; label: string }> = [{ to: "/overview", label: "Overview" }];
  if (isStaff(role)) s.push({ to: "/map", label: "Map Console" });
  if (canRunSim(role) || canReview(role)) s.push({ to: "/studio", label: "Simulation Studio" });
  if (canSubmit(role) || canReview(role)) s.push({ to: "/field", label: "Field Data" });
  if (isStaff(role)) s.push({ to: "/data", label: "Data & Gaps" });
  if (canAudit(role)) s.push({ to: "/audit", label: "Audit" });
  if (canAdmin(role)) s.push({ to: "/admin", label: "Administration" });
  s.push({ to: "/public", label: isStaff(role) ? "Public View" : "My Area" });
  return s;
}

/**
 * The portal-vs-model lag, in the header on every screen.
 *
 * Approved field data is authoritative here the moment a reviewer accepts it,
 * but the physics engine reads `Datasets/` and only sees it after a deliberate
 * admin sync. Every screen that shows a number is affected, so the indicator
 * belongs somewhere the user passes constantly (PRODUCT_DESIGN §4.4b).
 */
function SyncPill() {
  const nav = useNavigate();
  const { data } = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => api.get<SyncStatus>("/dataset-sync/status"),
    refetchInterval: 60_000,
    retry: false,
  });
  if (!data) return null;
  const n = data.approved_pending_sync;
  return (
    <button
      className={`sync-pill ${n ? "amber" : "clean"}`}
      title={`${data.message} ${data.note}`}
      onClick={() => nav("/data")}
    >
      <span>{n ? "🟡" : "🟢"}</span>
      {n ? `${n} not in model` : "Model in sync"}
    </button>
  );
}

export default function Shell() {
  const { me, signOut } = useAuth();
  const [menu, setMenu] = useState(false);
  const colour = me ? ROLE_COLOUR[me.role] : "var(--muted)";

  return (
    <div className="shell">
      <header className="hdr">
        <div className="hdr-brand">
          <div className="hdr-mark">💧</div>
          <div>
            <div className="hdr-name">JalDrishti</div>
            <div className="hdr-sub">ISR Groundwater Portal</div>
          </div>
        </div>

        <nav className="hdr-nav">
          {sectionsFor(me?.role).map((s) => (
            <NavLink key={s.to} to={s.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {s.label}
            </NavLink>
          ))}
        </nav>

        <div className="hdr-right">
          {isStaff(me?.role) && <SyncPill />}
          <span className="role-pill" style={{ color: colour }}>
            {me ? ROLE_LABEL[me.role] : "—"}
          </span>
          <button
            className="avatar"
            style={{ background: colour }}
            onClick={() => setMenu((v) => !v)}
            aria-label="Account menu"
          >
            {(me?.username ?? "?")[0]?.toUpperCase()}
          </button>
        </div>

        {menu && (
          <div className="acct-menu" onMouseLeave={() => setMenu(false)}>
            <div className="who">
              <div style={{ fontWeight: 600 }}>{me?.username}</div>
              <div className="muted small">{me?.email}</div>
              <div className="small" style={{ color: colour, marginTop: 4, fontWeight: 700 }}>
                {me ? ROLE_LABEL[me.role] : ""}
              </div>
            </div>
            <button onClick={signOut}>Sign out</button>
          </div>
        )}
      </header>

      <div className="body">
        <Outlet />
      </div>
    </div>
  );
}
