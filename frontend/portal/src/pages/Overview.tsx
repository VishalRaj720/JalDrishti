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
  api, type AuditEntry, type IsrPoint, type Observation,
  type PublicDistrictRisk, type Scenario, type SimRun, type SyncStatus,
} from "../api/client";
import { ROLE_PURPOSE, useAuth } from "../auth";
import { Loading, Planned, Tile, bandOf } from "../components/bits";

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

function AdminOverview() {
  const nav = useNavigate();
  const sync = useSync();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const audit = useQuery({ queryKey: ["audit", 8], queryFn: () => api.get<AuditEntry[]>("/audit?limit=8") });
  const health = useQuery({ queryKey: ["health"], queryFn: async () => (await fetch("/health")).json() });

  return (
    <div className="page">
      <Head />
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={users.data?.length ?? "–"} label="User accounts" tone="blue"
              sub="across five roles" onClick={() => nav("/admin")} />
        <Tile n={sync.data?.pending_review ?? "–"} label="Awaiting review" tone="red"
              sub="field observations" onClick={() => nav("/field")} />
        <Tile n={sync.data?.approved_pending_sync ?? "–"} label="Approved, not in model" tone="amber"
              sub="needs a dataset sync" onClick={() => nav("/data")} />
        <Tile n={health.data?.status === "ok" ? "OK" : "?"} label="API health" tone="green"
              sub={health.data?.version ? `v${health.data.version}` : ""} />
      </div>

      <div className="grid-2">
        <div>
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

// ── REGULATOR ────────────────────────────────────────────────────────

function RegulatorOverview() {
  const nav = useNavigate();
  const sync = useSync();
  const pending = usePending();
  const sites = useSites();
  const runs = useRuns(sites.data?.[0]?.id);
  const districts = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });

  const excursions = (runs.data ?? []).filter((r) => r.excursion?.excursion_declared);
  const extrapolating = (runs.data ?? []).filter((r) => (r.extrapolation?.length ?? 0) > 0);
  const worst = [...(districts.data?.districts ?? [])]
    .filter((d) => d.max_uranium_ppb !== null)
    .sort((a, b) => (b.max_uranium_ppb ?? 0) - (a.max_uranium_ppb ?? 0))
    .slice(0, 6);

  return (
    <div className="page">
      <Head />
      <div className="grid-4" style={{ marginBottom: 16 }}>
        <Tile n={pending.data?.length ?? "–"} label="Awaiting your decision" tone="red"
              sub="field observations" onClick={() => nav("/field")} />
        <Tile n={excursions.length} label="Runs declaring excursion" tone="amber"
              sub="NUREG-1569 2-of-3" onClick={() => nav("/studio")} />
        <Tile n={extrapolating.length} label="Runs outside trained support" tone="amber"
              sub="ML band not guaranteed" onClick={() => nav("/studio")} />
        <Tile n={sync.data?.approved_pending_sync ?? "–"} label="Approved, not in model" tone="amber"
              sub="awaiting admin sync" onClick={() => nav("/data")} />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            Decision queue
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/field")}>Open →</button>
          </div>
          {pending.isLoading && <Loading />}
          {pending.data?.length === 0 && (
            <div className="muted small">Nothing is waiting on you.</div>
          )}
          {pending.data?.slice(0, 6).map((o) => (
            <div key={o.id} className="list-item" onClick={() => nav("/field")}>
              <div>
                <div className="nm">{o.operation} · {o.observation_type}</div>
                <div className="mt">submitted {new Date(o.submitted_at).toLocaleString()}</div>
              </div>
              <span className="chip danger">🔴 review</span>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title">Districts by measured uranium</div>
          <div className="muted small" style={{ marginBottom: 8 }}>
            Real CGWB sampling — measurements, not model output.
          </div>
          {districts.isLoading && <Loading />}
          {worst.map((d) => {
            const b = bandOf(d.max_uranium_ppb);
            return (
              <div key={d.id} className="list-item">
                <div>
                  <div className="nm">{d.name}</div>
                  <div className="mt">{d.wells} wells · max {d.max_uranium_ppb} ppb</div>
                </div>
                <span className={`chip ${b.cls}`}>{b.label}</span>
              </div>
            );
          })}
        </div>
      </div>

      <Planned label="Publish / archive a site, and export a signed regulator report"
               phase="P5 / P8"
               why="The site status workflow and PDF export endpoints are not implemented." />
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
        <Tile n={sites.data?.length ?? "–"} label="Hypothetical sites" tone="blue" onClick={() => nav("/map")} />
        <Tile n={scenarios.data?.length ?? "–"} label="Saved scenarios" tone="blue" onClick={() => nav("/studio")} />
        <Tile n={runs.data?.length ?? "–"} label="Recent runs" tone="green" onClick={() => nav("/studio")} />
        <Tile n={flagged.length} label="Outside trained support" tone="amber"
              sub="conformal band void" onClick={() => nav("/studio")} />
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            Scenarios
            <span className="spacer grow" />
            <button className="btn primary" onClick={() => nav("/studio")}>Open Studio →</button>
          </div>
          {scenarios.isLoading && <Loading />}
          {scenarios.data?.length === 0 && (
            <div className="muted small">
              No saved scenarios. A scenario names a set of inputs so a run can be
              repeated and compared later.
            </div>
          )}
          {scenarios.data?.slice(0, 6).map((s) => (
            <div key={s.id} className="list-item" onClick={() => nav("/studio")}>
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
            <div key={r.id} className="list-item" onClick={() => nav("/studio")}>
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
          <button className="btn primary" onClick={() => nav("/public")}>Find my area →</button>
        </div>
        <div className="muted small" style={{ lineHeight: 1.6 }}>
          These are real measurements from government groundwater sampling — not
          predictions. Choose your district to see the reading for each block, what it
          means, and who to contact.
        </div>
      </div>

      <Planned label="Get an alert when water near me changes" phase="P7"
               why="Alert subscriptions are designed but not built — there is no notification service yet." />
    </div>
  );
}

export default function Overview() {
  const { me } = useAuth();
  switch (me?.role) {
    case "admin": return <AdminOverview />;
    case "regulator": return <RegulatorOverview />;
    case "analyst": return <AnalystOverview />;
    case "field_officer": return <FieldOverview />;
    default: return <CitizenOverview />;
  }
}
