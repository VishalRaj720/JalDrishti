import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Role, type SyncStatus } from "../api/client";
import {
  ROLE_COLOUR, ROLE_LABEL, canAdmin, canAudit, canPublish, canReview, canRunSim,
  canSubmit, isStaff, useAuth,
} from "../auth";

/**
 * The nav, grouped.
 *
 * An admin sees eleven destinations. As a flat row of links they overflowed the
 * header and collided with the sync pill and the account controls — horizontal
 * space is the one thing a top bar cannot buy more of, and every section added
 * since P4 made it worse.
 *
 * Grouping trades one click for a header that fits: five stable top-level items
 * whose width does not change as sections are added. The grouping is by QUESTION
 * being asked, not by permission — "where is the data" and "what has been
 * decided" are different jobs, and a menu that mirrors the role matrix would
 * just be the permission model leaking into the furniture.
 *
 * Overview stays a plain link because it is the landing page, and a dropdown
 * containing one thing is a worse button.
 */
type NavItem = { to: string; label: string };
type NavGroup = { label: string; items: NavItem[] };

function sectionsFor(role: Role | undefined): NavGroup[] {
  const groups: NavGroup[] = [];
  const add = (label: string, items: (NavItem | false)[]) => {
    const kept = items.filter(Boolean) as NavItem[];
    if (kept.length) groups.push({ label, items: kept });
  };

  add("Overview", [{ to: "/overview", label: "Overview" }]);

  add("Map", [
    isStaff(role) && { to: "/console", label: "Console" },
    canRunSim(role) && { to: "/compare", label: "Compare sites" },
  ]);

  add("Data", [
    (canSubmit(role) || canReview(role)) && { to: "/field", label: "Field data" },
    isStaff(role) && { to: "/data", label: "Data & gaps" },
    isStaff(role) && { to: "/network-plan", label: "Monitoring plan" },
    canAdmin(role) && { to: "/datasets", label: "Dataset manager" },
  ]);

  add("Decisions", [
    // Analysts propose, admins decide — both need the queue. A field officer
    // does not run the model, so nothing here is theirs to propose or judge.
    (canRunSim(role) || canPublish(role)) && { to: "/publications", label: "Publications" },
    canAudit(role) && { to: "/audit", label: "Audit log" },
    canAdmin(role) && { to: "/admin", label: "Administration" },
  ]);

  add("Public", [
    { to: "/my-area", label: isStaff(role) ? "Public view" : "My area" },
    { to: "/public", label: isStaff(role) ? "Public map" : "Map near me" },
    !isStaff(role) && { to: "/alerts", label: "Alerts" },
    { to: "/methods", label: "Data & methods" },
  ]);

  return groups;
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
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const loc = useLocation();
  const here = loc.pathname;
  const colour = me ? ROLE_COLOUR[me.role] : "var(--muted)";
  const sections = sectionsFor(me?.role);

  // Navigating closes every menu. Without this the sheet stays open over the
  // screen it just navigated to, which reads as a stuck overlay.
  useEffect(() => { setNav(false); setMenu(false); setOpenGroup(null); }, [here]);

  // A dropdown must close on a click elsewhere and on Escape, or it behaves
  // like a panel that will not go away.
  useEffect(() => {
    if (!openGroup) return;
    const away = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".nav-group")) setOpenGroup(null);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenGroup(null); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [openGroup]);

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
          {sections.map((g) => (
            g.items.length === 1 ? (
              <NavLink key={g.label} to={g.items[0].to}
                       className={({ isActive }) => (isActive ? "active" : "")}>
                {g.items[0].label}
              </NavLink>
            ) : (
              <div key={g.label} className="nav-group">
                <button
                  className={`nav-group-btn ${
                    g.items.some((i) => here.startsWith(i.to)) ? "active" : ""}`}
                  onClick={() => setOpenGroup(openGroup === g.label ? null : g.label)}
                  aria-expanded={openGroup === g.label}
                  aria-haspopup="true"
                >
                  {g.label}<span className="caret" aria-hidden>▾</span>
                </button>
                {openGroup === g.label && (
                  <div className="nav-drop" role="menu">
                    {g.items.map((i) => (
                      <NavLink key={i.to} to={i.to} role="menuitem"
                               className={({ isActive }) => (isActive ? "active" : "")}>
                        {i.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            )
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
            {sections.map((g) => (
              <div key={g.label}>
                {g.items.length > 1 && <div className="nav-sheet-head">{g.label}</div>}
                {g.items.map((i) => (
                  <NavLink key={i.to} to={i.to}
                           className={({ isActive }) => (isActive ? "active" : "")}>
                    {i.label}
                  </NavLink>
                ))}
              </div>
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
