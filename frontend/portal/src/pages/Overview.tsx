/**
 * The landing screen — five different screens behind one route.
 *
 * A shared dashboard would serve nobody: a regulator needs a decision queue, a
 * field officer needs their own submission ledger, an analyst needs scenarios,
 * an admin needs system state, and a citizen needs plain language. What each
 * role sees here is "what needs *my* attention", not "all the data we have".
 */
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  api, type Advisory, type AuditEntry, type IsrPoint, type Observation,
  type PublicDistrictRisk, type Scenario, type SimRun, type SyncStatus,
} from "../api/client";
import { ROLE_PURPOSE, useAuth } from "../auth";
import { Loading, Planned, RiskBand, Tile } from "../components/bits";

function Head() {
  const { me } = useAuth();
  return (
    <div className="page-head">
      <h1>Good day, {me?.username}</h1>
      <p>{me ? ROLE_PURPOSE[me.role] : ""}</p>
    </div>
  );
}

// ── shared queries ───────────────────────────────────────────────────
const useSync = () =>
  useQuery({ queryKey: ["sync-status"], queryFn: () => api.get<SyncStatus>("/dataset-sync/status") });
const usePending = () =>
  useQuery({ queryKey: ["obs", "pending"], queryFn: () => api.get<Observation[]>("/field-observations?status=pending") });
const useRuns = (isr?: string) =>
  useQuery({
    queryKey: ["runs", isr], enabled: !!isr,
    queryFn: () => api.get<SimRun[]>(`/simulations/runs?isr_id=${isr}&limit=25`),
  });
const useSites = () =>
  useQuery({ queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points") });

// ── ADMIN ────────────────────────────────────────────────────────────

/**
 * The admin landing screen.
 *
 * R7 folded the regulator's screen into this one. That was not a deletion: an
 * admin now carries the DOMAIN decisions the regulator used to — approving
 * field evidence and deciding what reaches residents — so the decision queue
 * and the publication queue belong here, above platform housekeeping. What an
 * admin needs first is "what is waiting on me", not "how many accounts exist".
 */
function AdminOverview() {
  const nav = useNavigate();
  const sync = useSync();
  const pending = usePending();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const audit = useQuery({ queryKey: ["audit", 8], queryFn: () => api.get<AuditEntry[]>("/audit?limit=8") });
  const health = useQuery({ queryKey: ["health"], queryFn: async () => (await fetch("/health")).json() });
  const advisories = useQuery({
    queryKey: ["advisories"], queryFn: () => api.get<Advisory[]>("/advisories?limit=200"),
  });
  const districts = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });

  const proposed = (advisories.data ?? []).filter((a) => a.status === "proposed");
  const worst = [...(districts.data?.districts ?? [])]
    .filter((d) => d.max_uranium_ppb !== null)
    .sort((a, b) => (b.max_uranium_ppb ?? 0) - (a.max_uranium_ppb ?? 0))
    .slice(0, 6);

  return (
    <div className="page">
      <Head />
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={proposed.length} label="Awaiting your decision" tone="red"
              sub="screenings proposed for the public" onClick={() => nav("/publications")} />
        <Tile n={sync.data?.pending_review ?? "–"} label="Field evidence to review" tone="amber"
              sub="ore observations" onClick={() => nav("/field")} />
        <Tile n={sync.data?.approved_pending_sync ?? "–"} label="Approved, not in model" tone="amber"
              sub="needs a dataset sync" onClick={() => nav("/data")} />
        <Tile n={users.data?.length ?? "–"} label="User accounts" tone="blue"
              sub="across four roles" onClick={() => nav("/admin")} />
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">
            Decision queue
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/publications")}>Open →</button>
          </div>
          {advisories.isLoading && <Loading />}
          {proposed.length === 0 && (
            <div className="muted small">
              Nothing is waiting on you. Screenings appear here when an analyst
              proposes one from a completed run.
            </div>
          )}
          {proposed.slice(0, 5).map((a) => (
            <button key={a.id} className="list-item" onClick={() => nav("/publications")}>
              <div>
                <div className="nm">{a.headline}</div>
                <div className="mt">
                  proposed {new Date(a.proposed_at).toLocaleDateString()}
                  {a.footprint_ha != null && ` · ${a.footprint_ha.toFixed(1)} ha`}
                </div>
              </div>
              <span className="chip warn">decide</span>
            </button>
          ))}
          {pending.data && pending.data.length > 0 && (
            <div className="muted small" style={{ marginTop: 8 }}>
              Also {pending.data.length} field observation(s) awaiting review.
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">Districts by measured uranium</div>
          <div className="muted small" style={{ marginBottom: 8 }}>
            Real CGWB sampling — measurements, not model output.
          </div>
          {districts.isLoading && <Loading />}
          {worst.map((d) => (
            <div key={d.id} className="list-item">
              <div>
                <div className="nm">{d.name}</div>
                <div className="mt">{d.wells} wells · max {d.max_uranium_ppb} ppb</div>
              </div>
              <RiskBand value={d.max_uranium_ppb} />
            </div>
          ))}
        </div>
      </div>

      <div className="grid-2">
        <div>
          <div className="card">
            <div className="card-title">System</div>
            <div className="row wrap" style={{ marginBottom: 8 }}>
              <span className={`chip ${health.data?.status === "ok" ? "ok" : "warn"}`}>
                API {health.data?.status === "ok" ? "healthy" : "unknown"}
              </span>
              {health.data?.version && (
                <span className="muted small">v{health.data.version}</span>
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-title">Platform posture</div>
            <div className="banner ok" style={{ marginBottom: 9 }}>
              Row-level security is enforced in Postgres, and the API connects as a
              role that cannot bypass it. Access control is not application-only.
            </div>
            <div className="muted small">
              Simulation results are pinned to the model card, artifact bundle and git
              SHA that produced them, so any number can be re-derived later.
            </div>
          </div>
          <Planned label="Ingest new reference geography (GeoJSON / CSV)" phase="admin tooling"
                   why="The ingest endpoints exist and are admin-only, but the upload UI is not built. Use the API directly for now." />
        </div>

        <div className="card">
          <div className="card-title">
            Recent activity
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/audit")}>Full audit →</button>
          </div>
          {audit.isLoading && <Loading />}
          {audit.data?.length === 0 && <div className="muted small">No activity recorded yet.</div>}
          {audit.data?.slice(0, 8).map((a) => (
            <div key={a.id} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <span className="mono" style={{ color: "var(--accent)" }}>{a.action}</span>
              <span className="muted small grow">{a.actor_label ?? "system"}</span>
              <span className="muted small">{new Date(a.occurred_at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── ANALYST ──────────────────────────────────────────────────────────

function AnalystOverview() {
  const nav = useNavigate();
  const sites = useSites();
  const scenarios = useQuery({ queryKey: ["scenarios"], queryFn: () => api.get<Scenario[]>("/scenarios") });
  const runs = useRuns(sites.data?.[0]?.id);
  const flagged = (runs.data ?? []).filter((r) => (r.extrapolation?.length ?? 0) > 0);

  return (
    <div className="page">
      <Head />
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={sites.data?.length ?? "–"} label="Hypothetical sites" tone="blue" onClick={() => nav("/console")} />
        <Tile n={scenarios.data?.length ?? "–"} label="Saved scenarios" tone="blue" onClick={() => nav("/console")} />
        <Tile n={runs.data?.length ?? "–"} label="Recent runs" tone="green" onClick={() => nav("/console")} />
        <Tile n={flagged.length} label="Outside trained support" tone="amber"
              sub="conformal band void" onClick={() => nav("/console")} />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            Scenarios
            <span className="spacer grow" />
            <button className="btn primary" onClick={() => nav("/console")}>Open Console →</button>
          </div>
          {scenarios.isLoading && <Loading />}
          {scenarios.data?.length === 0 && (
            <div className="muted small">
              No saved scenarios. A scenario names a set of inputs so a run can be
              repeated and compared later.
            </div>
          )}
          {scenarios.data?.slice(0, 6).map((s) => (
            <div key={s.id} className="list-item" onClick={() => nav("/console")}>
              <div>
                <div className="nm">{s.name}</div>
                <div className="mt">{s.description ?? "no description"}</div>
              </div>
              <span className="chip info">open</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">Latest runs</div>
          {runs.isLoading && <Loading />}
          {runs.data?.length === 0 && <div className="muted small">No runs yet.</div>}
          {runs.data?.slice(0, 6).map((r) => (
            <div key={r.id} className="list-item" onClick={() => nav("/console")}>
              <div>
                <div className="nm">{r.species}</div>
                <div className="mt">
                  {new Date(r.created_at).toLocaleString()}
                  {r.runtime_ms ? ` · ${(r.runtime_ms / 1000).toFixed(1)}s` : ""}
                </div>
              </div>
              <span className={`chip ${r.status === "completed" ? "ok" : r.status === "failed" ? "danger" : "warn"}`}>
                {r.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── FIELD OFFICER ────────────────────────────────────────────────────

function FieldOverview() {
  const nav = useNavigate();
  // RLS scopes this to the officer's OWN submissions — no client-side filter.
  const mine = useQuery({ queryKey: ["obs", "mine"], queryFn: () => api.get<Observation[]>("/field-observations?limit=200") });

  const by = (s: string) => (mine.data ?? []).filter((o) => o.status === s);
  const pending = by("pending");
  const approved = (mine.data ?? []).filter((o) => o.status === "approved");
  const rejected = by("rejected");

  return (
    <div className="page">
      <Head />
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={pending.length} label="Awaiting review" tone="red" onClick={() => nav("/field")} />
        <Tile n={approved.length} label="Approved" tone="green" onClick={() => nav("/field")} />
        <Tile n={rejected.length} label="Rejected" tone="amber" onClick={() => nav("/field")} />
        <Tile n={mine.data?.length ?? "–"} label="Total submitted" tone="blue" />
      </div>

      <div className="card">
        <div className="card-title">
          Record what you found
          <span className="spacer grow" />
          <button className="btn primary" onClick={() => nav("/field")}>New observation →</button>
        </div>
        <div className="muted small" style={{ lineHeight: 1.6 }}>
          Submissions enter a <strong>pending</strong> state and change nothing until a
          regulator or administrator approves them. You cannot approve your own work —
          that separation is enforced by a database constraint, not just by this screen.
        </div>
      </div>

      <div className="card">
        <div className="card-title">My recent submissions</div>
        {mine.isLoading && <Loading />}
        {mine.data?.length === 0 && (
          <div className="muted small">
            Nothing submitted yet. Your submissions, and only yours, appear here.
          </div>
        )}
        {mine.data?.slice(0, 8).map((o) => (
          <div key={o.id} className="list-item" onClick={() => nav("/field")}>
            <div>
              <div className="nm">{o.operation} · {o.observation_type}</div>
              <div className="mt">
                {new Date(o.submitted_at).toLocaleString()}
                {o.review_note ? ` · reviewer: ${o.review_note}` : ""}
              </div>
            </div>
            <span className={`chip ${o.status === "approved" ? "ok" : o.status === "rejected" ? "danger" : "warn"}`}>
              {o.status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── CITIZEN ──────────────────────────────────────────────────────────

function CitizenOverview() {
  const nav = useNavigate();
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[]; safe_limit: number; what_this_is: string }>("/public/risk/districts"),
  });

  const withData = (risk.data?.districts ?? []).filter((d) => d.samples > 0);
  const high = withData.filter((d) => (d.max_uranium_ppb ?? 0) >= 30).length;
  const gaps = (risk.data?.districts ?? []).filter((d) => d.samples === 0).length;

  return (
    <div className="page">
      <Head />

      <div className="banner warn" style={{ marginBottom: 16 }}>
        {risk.data?.what_this_is ??
          "No uranium mine of the type this platform models operates in Jharkhand."}
      </div>

      <div className="grid-3" style={{ marginBottom: 16 }}>
        <Tile n={withData.length} label="Districts with test results" tone="green" />
        <Tile n={high} label="Districts at or above the safe limit" tone="red"
              sub={`${risk.data?.safe_limit ?? 30} ppb uranium`} />
        <Tile n={gaps} label="Districts with no data yet" tone="amber"
              sub="a monitoring gap, not a clean result" />
      </div>

      <div className="card">
        <div className="card-title">
          Groundwater near you
          <span className="spacer grow" />
          <button className="btn primary" onClick={() => nav("/my-area")}>My area →</button>
        </div>
        <div className="prose muted">
          These are real measurements from government groundwater sampling — not
          predictions. Follow your block to see what was tested there, what it means,
          and who to contact.
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            Alerts
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/alerts")}>Open →</button>
          </div>
          <div className="prose muted">
            You are told when a well near you tests above the safe limit, and when an
            assessment is published for your area. Alerts appear in this portal only —
            no SMS, no email.
          </div>
        </div>
        <div className="card">
          <div className="card-title">
            Data &amp; methods
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/methods")}>Read →</button>
          </div>
          <div className="prose muted">
            Where these numbers come from, what the safe limit is, and what this
            platform does not know.
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Overview() {
  const { me } = useAuth();
  switch (me?.role) {
    case "admin": return <AdminOverview />;
    // R7 retired `regulator`; migration 0019 merged those accounts into admin.
    // Any token minted before that still decodes to the old role, so it maps to
    // the admin screen rather than falling through to the citizen one — a stale
    // token must not silently downgrade someone into the public surface.
    case "regulator": return <AdminOverview />;
    case "analyst": return <AnalystOverview />;
    case "field_officer": return <FieldOverview />;
    default: return <CitizenOverview />;
  }
}
