import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Role, type SyncStatus } from "../api/client";
import {
  ROLE_COLOUR, ROLE_LABEL, canAdmin, canAudit, canReview, canRunSim,
  canSubmit, isStaff, useAuth,
} from "../auth";

/** Section list, filtered by role — the `roleReq` pattern from the prototype. */
function sectionsFor(role: Role | undefined) {
  const s: Array<{ to: string; label: string }> = [{ to: "/overview", label: "Overview" }];
  if (isStaff(role)) s.push({ to: "/console", label: "Console" });
  // Analysts propose, regulators decide — both need the queue. A field officer
  // does not run the model, so nothing here is theirs to propose or judge.
  if (canRunSim(role) || canReview(role)) s.push({ to: "/publications", label: "Publications" });
  if (canSubmit(role) || canReview(role)) s.push({ to: "/field", label: "Field Data" });
  if (isStaff(role)) s.push({ to: "/data", label: "Data & Gaps" });
  if (canAudit(role)) s.push({ to: "/audit", label: "Audit" });
  if (canAdmin(role)) s.push({ to: "/admin", label: "Administration" });
  // The citizen's own sections. Staff get "Public View" so an official can see
  // exactly what a resident sees — the same screen, not a preview of it.
  s.push({ to: "/my-area", label: isStaff(role) ? "Public View" : "My area" });
  if (!isStaff(role)) s.push({ to: "/alerts", label: "Alerts" });
  s.push({ to: "/methods", label: "Data & methods" });
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
/**
 * Unread alerts, on every screen.
 *
 * Delivery is in-portal only — no SMS, no email — so this bell is the entire
 * notification channel. If it is not visible everywhere, an alert about a well
 * over the safe limit reaches nobody.
 */
function AlertBell() {
  const nav = useNavigate();
  const { data } = useQuery({
    queryKey: ["unread"],
    queryFn: () => api.get<{ unread: number }>("/citizen/alerts/unread-count"),
    refetchInterval: 120_000,
    retry: false,
  });
  const n = data?.unread ?? 0;
  return (
    <button className="bell" onClick={() => nav("/alerts")}
            aria-label={n ? `${n} unread alerts` : "Alerts"}>
      <span aria-hidden>🔔</span>
      {n > 0 && <span className="count">{n > 99 ? "99+" : n}</span>}
    </button>
  );
}

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
      <span aria-hidden>{n ? "🟡" : "🟢"}</span>
      <span>{n ? `${n} not in model` : "Model in sync"}</span>
    </button>
  );
}

export default function Shell() {
  const { me, signOut } = useAuth();
  const [menu, setMenu] = useState(false);
  const [nav, setNav] = useState(false);
  const loc = useLocation();
  const colour = me ? ROLE_COLOUR[me.role] : "var(--muted)";
  const sections = sectionsFor(me?.role);

  // Navigating closes the mobile menu. Without this the sheet stays open over
  // the screen it just navigated to, which reads as a stuck overlay.
  useEffect(() => { setNav(false); setMenu(false); }, [loc.pathname]);

  return (
    <div className="shell">
      <header className="hdr">
        <button className="nav-btn" onClick={() => setNav((v) => !v)}
                aria-label="Sections" aria-expanded={nav}>☰</button>

        <div className="hdr-brand">
          <div className="hdr-mark" aria-hidden>💧</div>
          <div>
            <div className="hdr-name">JalDrishti</div>
            <div className="hdr-sub">ISR Groundwater Portal</div>
          </div>
        </div>

        <nav className="hdr-nav">
          {sections.map((s) => (
            <NavLink key={s.to} to={s.to} className={({ isActive }) => (isActive ? "active" : "")}>
              {s.label}
            </NavLink>
          ))}
        </nav>

        <div className="hdr-right">
          {isStaff(me?.role) && <SyncPill />}
          <AlertBell />
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

        {nav && (
          <nav className="nav-sheet">
            {sections.map((s) => (
              <NavLink key={s.to} to={s.to} className={({ isActive }) => (isActive ? "active" : "")}>
                {s.label}
              </NavLink>
            ))}
          </nav>
        )}

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
