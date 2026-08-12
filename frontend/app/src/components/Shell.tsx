import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type SyncStatus } from "../api/client";
import { canReview, useAuth } from "../auth";

/**
 * The §4.4b split-brain counter.
 *
 * Approved field data is authoritative in the portal the moment a reviewer
 * accepts it, but the physics engine reads `Datasets/` and only sees it after a
 * deliberate admin sync. That lag is shown, never hidden — a header the user
 * passes on every screen is the right place for it.
 */
function SyncBadge() {
  const { data } = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => api.get<SyncStatus>("/dataset-sync/status"),
    refetchInterval: 60_000,
  });
  if (!data) return null;

  const pending = data.approved_pending_sync;
  return (
    <span
      className={`sync-badge ${pending ? "amber" : "clean"}`}
      title={pending ? `${data.message} ${data.note}` : data.message}
    >
      <span>{pending ? "🟡" : "🟢"}</span>
      {pending ? `${pending} not yet in model` : "Model in sync"}
    </span>
  );
}

export default function Shell() {
  const { me, signOut } = useAuth();

  return (
    <div className="shell">
      <header className="header">
        <div className="brand">
          <div className="brand-mark">💧</div>
          <div>
            <div className="brand-name">JalDrishti</div>
            <div className="brand-sub">Groundwater Assessment</div>
          </div>
        </div>

        <nav className="nav">
          <NavLink to="/map" className={({ isActive }) => (isActive ? "active" : "")}>
            Map
          </NavLink>
          <NavLink to="/sites" className={({ isActive }) => (isActive ? "active" : "")}>
            Site Registry
          </NavLink>
          {canReview(me?.role) && (
            <NavLink
              to="/review"
              className={({ isActive }) => (isActive ? "active" : "")}
            >
              Review
            </NavLink>
          )}
        </nav>

        <div className="header-right">
          <SyncBadge />
          <span className="role-chip">{me?.role ?? "—"}</span>
          <div className="avatar">{(me?.username ?? "?")[0]?.toUpperCase()}</div>
          <button className="linkish" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="body">
        <Outlet />
      </div>
    </div>
  );
}
