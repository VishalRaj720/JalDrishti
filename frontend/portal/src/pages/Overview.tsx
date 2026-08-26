/**
 * The landing screen — five different screens behind one route.
 *
 * A shared dashboard would serve nobody: a regulator needs a decision queue, a
 * field officer needs their own submission ledger, an analyst needs scenarios,
 * an admin needs system state, and a citizen needs plain language. What each
 * role sees here is "what needs *my* attention", not "all the data we have".
 *
 * ── R15 RESTRUCTURE ──
 *
 * Every role landed on the same shape: a `grid-4` of tiles over a `grid-2` of
 * cards. That made five different jobs look identical, and it made every number
 * equally important — which is the same as making none of them important. Each
 * role now opens with ONE SENTENCE naming what is waiting, and the work itself
 * is a full-width QUEUE rather than a list squeezed into half a card.
 *
 * TWO REAL DEFECTS WERE FIXED HERE, both invisible until the screen was pulled
 * apart:
 *
 * 1. `regulator` WAS RENDERING THE ADMIN SCREEN. Migration `0019` retired the
 *    role and the comment at the bottom of this file still said so; migration
 *    `0022` restored it with a narrower job — accept or reject what a data
 *    submitter files, and nothing else. Sending it to the admin screen meant a
 *    regulator issued `GET /users` on every sign-in (403, so the tile read "–"
 *    forever) and was offered a tile that navigated to `/admin`, which the
 *    route guard then refused. It now has its own screen: the review queue,
 *    the record it is deciding against, and the screening tool it may run.
 *
 * 2. THE `/health` CHIP COULD NEVER HAVE WORKED. It fetched a bare `/health`,
 *    but the API is same-origin only under `/api/*` — the Vite proxy in dev and
 *    `run_worker_first` in production both route that prefix and nothing else,
 *    so `/health` returned the SPA's own index.html and `.json()` threw on
 *    every render. The chip has always shown an amber "API unknown", which is
 *    worse than absent: it reported a fault that did not exist. Replaced with
 *    the trained-model state from `/model-ops/model`, which is a real endpoint,
 *    is genuinely an admin's business, and answers a question the old chip did
 *    not: is there a copy of the model anywhere but the running container.
 */
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  api, type Advisory, type AuditEntry, type IsrPoint, type ModelState,
  type Observation, type PublicDistrictRisk, type Scenario, type SimRun,
  type SyncStatus,
} from "../api/client";
import { ROLE_PURPOSE, useAuth } from "../auth";
import { HypotheticalNote, Loading, Planned, RiskBand } from "../components/bits";
import {
  Composition, Queue, QueueClear, QueueItem, Readout, SectionHead, Statement,
} from "../components/instruments";

function Head() {
  const { me } = useAuth();
  return (
    <div className="page-head">
      <h1>Good day, {me?.username}</h1>
      <p>{me ? ROLE_PURPOSE[me.role] : ""}</p>
    </div>
  );
}

const ago = (at: string) => {
  const d = Math.floor((Date.now() - Date.parse(at)) / 86_400_000);
  if (!Number.isFinite(d)) return "";
  return d <= 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`;
};

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
const useDistrictRisk = () =>
  useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[]; safe_limit: number; what_this_is: string }>(
      "/public/risk/districts"),
  });

/** Worst first. The two gap bands are excluded from the ranking entirely —
 *  see `MeasuredRecord`. */
const BAND_RANK: Record<string, number> = {
  "High concern": 0, "Moderate concern": 1, "Low concern": 2,
};

/** What actually set a district's band, in words. `band_driver` names the
 *  determinand; the matching maximum is what makes it quotable. */
function driverText(d: PublicDistrictRisk): string {
  switch (d.band_driver) {
    case "uranium": return `uranium ${d.max_uranium_ppb} ppb`;
    case "nitrate": return `nitrate ${d.max_nitrate_mg_l} mg/L`;
    case "fluoride": return `fluoride ${d.max_fluoride_mg_l} mg/L`;
    default: return "no health determinand above its limit";
  }
}

/**
 * Districts ranked by what has been MEASURED in them.
 *
 * Shared by the admin and regulator screens because both are deciding against
 * the same record.
 *
 * IT NOW RENDERS THE SERVER'S BAND RATHER THAN DERIVING ONE. This list used to
 * call `RiskBand` with the uranium maximum, which re-derives a band from
 * uranium alone — while the very same response carries a `band` computed from
 * uranium, nitrate AND fluoride. Two bands for one district, disagreeing, on
 * one screen: uranium exceeds its limit at no tested well in Jharkhand, so the
 * locally-derived version could never show anything but "Low concern" no matter
 * what was in the water. The server's band is the product's judgement, and this
 * screen now reports it and names what drove it.
 *
 * Districts in the two gap bands are excluded from the ranking rather than
 * sorted to the bottom — an unmeasured district is not "the safest", and a
 * ranking that implies otherwise is the error this product spends most of its
 * copy preventing. They are counted underneath instead.
 */
function MeasuredRecord() {
  const nav = useNavigate();
  const risk = useDistrictRisk();
  const all = risk.data?.districts ?? [];
  const ranked = all.filter((d) => d.band in BAND_RANK);
  const gaps = all.filter((d) => !(d.band in BAND_RANK));
  const worst = [...ranked]
    .sort((a, b) =>
      BAND_RANK[a.band] - BAND_RANK[b.band] ||
      (b.max_uranium_ppb ?? 0) - (a.max_uranium_ppb ?? 0))
    .slice(0, 6);

  return (
    <div className="card">
      <div className="card-title">
        Districts by measured health determinands
        <span className="spacer grow" />
        <button className="btn ghost" onClick={() => nav("/water-quality")}>
          All determinands →
        </button>
      </div>
      <div className="muted small" style={{ marginBottom: "var(--s-2)" }}>
        Real CGWB sampling — measurements, not model output. Banded on uranium,
        nitrate and fluoride.
      </div>
      {risk.isLoading && <Loading />}
      {worst.map((d) => (
        <div key={d.id} className="list-item">
          <div>
            <div className="nm">{d.name}</div>
            <div className="mt">{d.wells} wells · {driverText(d)}</div>
          </div>
          <RiskBand label={d.band} />
        </div>
      ))}
      {gaps.length > 0 && (
        <div className="muted small" style={{ marginTop: "var(--s-2)" }}>
          {gaps.length} further district{gaps.length === 1 ? "" : "s"} cannot be ranked
          here: {gaps.map((d) => d.name).join(", ")}. No health determinand has been
          analysed there. That is a monitoring gap, not a low reading.
        </div>
      )}
    </div>
  );
}

/** The pending-review queue, shared by the two roles that may decide on it. */
function ReviewQueue({ items, loading }: { items: Observation[]; loading: boolean }) {
  const nav = useNavigate();
  if (loading) return <Loading />;
  if (items.length === 0) {
    return (
      <QueueClear>
        Nothing is waiting for review. Submissions appear here the moment a data
        submitter files one.
      </QueueClear>
    );
  }
  return (
    <Queue>
      {items.slice(0, 6).map((o) => (
        <QueueItem
          key={o.id}
          tone="danger"
          title={`${o.operation} · ${o.observation_type.replace(/_/g, " ")}`}
          meta={<>submitted {ago(o.submitted_at)}{o.note ? ` · “${o.note}”` : ""}</>}
          side={<span className="chip danger">🔴 review</span>}
          onClick={() => nav("/field")}
        />
      ))}
      {items.length > 6 && (
        <button className="btn ghost" onClick={() => nav("/field")}>
          {items.length - 6} more →
        </button>
      )}
    </Queue>
  );
}

// ── ADMIN ────────────────────────────────────────────────────────────

/**
 * The admin landing screen.
 *
 * R7 folded the regulator's screen into this one, and R15 pulled it back out
 * (see the file header). What remains here is what only an admin can do:
 * decide what reaches residents, operate the sync, hold the accounts, and read
 * the trail. What an admin needs first is "what is waiting on me", not "how
 * many accounts exist".
 */
function AdminOverview() {
  const nav = useNavigate();
  const sync = useSync();
  const pending = usePending();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<any[]>("/users") });
  const audit = useQuery({ queryKey: ["audit", 8], queryFn: () => api.get<AuditEntry[]>("/audit?limit=8") });
  const model = useQuery({
    queryKey: ["model-state"],
    queryFn: () => api.get<ModelState>("/model-ops/model"),
  });
  const advisories = useQuery({
    queryKey: ["advisories"], queryFn: () => api.get<Advisory[]>("/advisories?limit=200"),
  });

  const proposed = (advisories.data ?? []).filter((a) => a.status === "proposed");
  const toReview = pending.data ?? [];
  const behind = sync.data?.approved_pending_sync ?? 0;

  // The opening sentence names the MOST BLOCKING thing, not a summary of
  // everything. A landing screen that lists four concerns equally is one the
  // reader has to triage themselves.
  const line = proposed.length > 0 ? (
    <>
      <span className="hl danger">{proposed.length}</span> screening
      {proposed.length === 1 ? "" : "s"} proposed for residents{" "}
      {proposed.length === 1 ? "is" : "are"} waiting on your decision.
    </>
  ) : toReview.length > 0 ? (
    <>
      <span className="hl warn">{toReview.length}</span> field submission
      {toReview.length === 1 ? "" : "s"} waiting for review.
    </>
  ) : behind > 0 ? (
    <>
      <span className="hl warn">{behind}</span> approved observation
      {behind === 1 ? "" : "s"} not yet in the model.
    </>
  ) : (
    <>Nothing is waiting on you.</>
  );

  return (
    <div className="page">
      <Head />

      <Statement eyebrow="Administrator · what needs you today" line={line}>
        <Readout label="Awaiting your decision" value={proposed.length}
                 tone={proposed.length ? "danger" : "ok"}
                 sub="screenings proposed for the public" />
        <Readout label="Field evidence to review" value={sync.data?.pending_review ?? "–"}
                 tone={(sync.data?.pending_review ?? 0) ? "warn" : "ok"} />
        <Readout label="Approved, not in model" value={behind}
                 tone={behind ? "warn" : "ok"} sub="needs a dataset sync" />
        <Readout label="Accounts" value={users.data?.length ?? "–"} tone="info"
                 sub="across the five roles" />
        <Readout
          label="Trained model"
          value={model.data ? (model.data.live ? "live" : "absent") : "–"}
          tone={!model.data ? undefined : model.data.unprotected ? "danger" : "ok"}
          sub={model.data?.unprotected
            ? "no bundle — the weights exist nowhere else"
            : model.data?.built_at
              ? `built ${new Date(model.data.built_at).toLocaleDateString()}`
              : undefined}
        />
      </Statement>

      <SectionHead
        title="Decisions waiting on you"
        action={<button className="btn ghost" onClick={() => nav("/publications")}>Open publications →</button>}
      >
        A screening reaches residents only when you publish it. Analysts propose;
        this is the only step that makes one public.
      </SectionHead>
      {advisories.isLoading ? <Loading /> : proposed.length === 0 ? (
        <QueueClear>
          Nothing is waiting on you. Screenings appear here when an analyst
          proposes one from a completed run.
        </QueueClear>
      ) : (
        <Queue>
          {proposed.slice(0, 6).map((a) => (
            <QueueItem
              key={a.id}
              tone="danger"
              title={a.headline}
              meta={
                <>
                  proposed {ago(a.proposed_at)}
                  {a.footprint_ha != null && ` · ${a.footprint_ha.toFixed(1)} ha`}
                </>
              }
              side={<span className="chip warn">decide</span>}
              onClick={() => nav("/publications")}
            />
          ))}
        </Queue>
      )}

      <SectionHead
        title="Field evidence awaiting review"
        action={<button className="btn ghost" onClick={() => nav("/field")}>Open field data →</button>}
      >
        Submissions change nothing until they are approved, and approving them
        changes the portal's record — not the model, which only moves at a sync.
      </SectionHead>
      <ReviewQueue items={toReview} loading={pending.isLoading} />

      <div className="grid-2" style={{ marginTop: "var(--s-5)" }}>
        <MeasuredRecord />

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
              <span className="mono" style={{ color: "var(--accent-text)" }}>{a.action}</span>
              <span className="muted small grow">{a.actor_label ?? "system"}</span>
              <span className="muted small">{new Date(a.occurred_at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      </div>

      <SectionHead title="Platform posture">
        Stated rather than measured — these are properties of how the system is
        built, and they do not change between page loads.
      </SectionHead>
      <div className="card">
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
  );
}

// ── REGULATOR ────────────────────────────────────────────────────────

/**
 * The regulator landing screen — restored in R15 to match migration `0022`.
 *
 * The job is narrow and this screen is narrow with it: accept or reject what a
 * data submitter files. A regulator may also run a screening (`canRunSim`,
 * added 2026-08-25 — a CGWB or SPCB officer asking "what would happen if" is
 * the primary real-world user of a screening tool) but may NOT publish one, so
 * the publication queue is deliberately absent rather than shown-and-refused.
 *
 * Nothing here calls `/users`, `/audit` or `/model-ops`. Those are operator
 * powers; the old shared screen requested all three and got a 403 for each.
 */
function RegulatorOverview() {
  const nav = useNavigate();
  const pending = usePending();
  const sync = useSync();
  const toReview = pending.data ?? [];

  return (
    <div className="page">
      <Head />

      <Statement
        eyebrow="Regulator · what needs you today"
        line={toReview.length > 0 ? (
          <>
            <span className="hl danger">{toReview.length}</span> submission
            {toReview.length === 1 ? "" : "s"} waiting on your decision.
          </>
        ) : (
          <>No submission is waiting on your decision.</>
        )}
        sub={
          "You decide whether a submitted finding is accepted into the record. " +
          "Approving one changes what this portal reports; it does not change the " +
          "model, which only moves when an administrator runs a dataset sync."
        }
      >
        <Readout label="Waiting on you" value={toReview.length}
                 tone={toReview.length ? "danger" : "ok"} />
        <Readout label="Approved, not in model" value={sync.data?.approved_pending_sync ?? "–"}
                 tone={(sync.data?.approved_pending_sync ?? 0) ? "warn" : "ok"}
                 sub="an administrator runs the sync" />
        <Readout label="In the model" value={sync.data?.approved_in_model ?? "–"} tone="ok" />
      </Statement>

      <SectionHead
        title="Submissions awaiting your decision"
        action={<button className="btn ghost" onClick={() => nav("/field")}>Open field data →</button>}
      >
        You cannot approve your own submission — that separation is a database
        constraint, not a rule this screen enforces.
      </SectionHead>
      <ReviewQueue items={toReview} loading={pending.isLoading} />

      <div className="grid-2" style={{ marginTop: "var(--s-5)" }}>
        <MeasuredRecord />

        <div className="card">
          <div className="card-title">
            Screening
            <span className="spacer grow" />
            <button className="btn primary" onClick={() => nav("/console")}>Open Console →</button>
          </div>
          <div className="muted small" style={{ lineHeight: "var(--lh-base)" }}>
            You may run the plume engine to ask what would happen if ISR-strength
            lixiviant entered an aquifer at a given point. Publishing a result to
            residents is a separate authority and rests with the administrator.
          </div>
          <div style={{ marginTop: "var(--s-3)" }}>
            <HypotheticalNote />
          </div>
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

      <Statement
        eyebrow="Analyst · state of your work"
        line={flagged.length > 0 ? (
          <>
            <span className="hl warn">{flagged.length}</span> recent run
            {flagged.length === 1 ? "" : "s"} sit outside trained support — the
            conformal band there is void.
          </>
        ) : (
          <>
            {sites.data?.length ?? "—"} hypothetical site
            {sites.data?.length === 1 ? "" : "s"} registered, and nothing recent
            falls outside trained support.
          </>
        )}
        sub={
          "A run outside trained support is not a wrong answer — it is an answer " +
          "the uncertainty model cannot vouch for, and it must not be quoted with a band."
        }
      >
        <Readout label="Hypothetical sites" value={sites.data?.length ?? "–"} tone="info" />
        <Readout label="Saved scenarios" value={scenarios.data?.length ?? "–"} tone="info" />
        <Readout label="Recent runs" value={runs.data?.length ?? "–"} tone="info" />
        <Readout label="Outside trained support" value={flagged.length}
                 tone={flagged.length ? "warn" : "ok"} sub="conformal band void" />
      </Statement>

      {flagged.length > 0 && (
        <>
          <SectionHead title="Runs outside trained support">
            Each names the input that left the envelope. Re-run inside it, or quote
            the result without a band and say why.
          </SectionHead>
          <Queue>
            {flagged.slice(0, 5).map((r) => (
              <QueueItem
                key={r.id}
                tone="warn"
                title={`${r.species} · ${new Date(r.created_at).toLocaleString()}`}
                meta={`extrapolating on ${r.extrapolation!.join(", ")}`}
                side={<span className="chip warn">no band</span>}
                onClick={() => nav("/console")}
              />
            ))}
          </Queue>
        </>
      )}

      <div className="grid-2" style={{ marginTop: "var(--s-5)" }}>
        <div className="card">
          <div className="card-title">
            Scenarios
            <span className="spacer grow" />
            <button className="btn primary" onClick={() => nav("/scenarios")}>Open →</button>
          </div>
          {scenarios.isLoading && <Loading />}
          {scenarios.data?.length === 0 && (
            <div className="muted small">
              No saved scenarios. A scenario names a set of inputs so a run can be
              repeated and compared later.
            </div>
          )}
          {scenarios.data?.slice(0, 6).map((s) => (
            <button key={s.id} className="list-item" onClick={() => nav("/scenarios")}>
              <div>
                <div className="nm">{s.name}</div>
                <div className="mt">{s.description ?? "no description"}</div>
              </div>
              <span className="chip info">open</span>
            </button>
          ))}
        </div>

        <div className="card">
          <div className="card-title">
            Latest runs
            <span className="spacer grow" />
            <button className="btn ghost" onClick={() => nav("/console")}>Console →</button>
          </div>
          {runs.isLoading && <Loading />}
          {runs.data?.length === 0 && <div className="muted small">No runs yet.</div>}
          {runs.data?.slice(0, 6).map((r) => (
            <button key={r.id} className="list-item" onClick={() => nav("/console")}>
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
            </button>
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

  const all = mine.data ?? [];
  const by = (s: string) => all.filter((o) => o.status === s);
  const pending = by("pending");
  const rejected = by("rejected");
  // The two states an approved submission can be in are genuinely different
  // facts, and the ledger exists to keep them apart: accepted into the record,
  // versus actually reaching the model at the next sync.
  const approved = all.filter((o) => o.status === "approved");
  const inModel = approved.filter((o) => o.synced_to_dataset_at !== null);
  const waitingSync = approved.length - inModel.length;

  return (
    <div className="page">
      <Head />

      <Statement
        eyebrow="Data submitter · your ledger"
        line={pending.length > 0 ? (
          <>
            <span className="hl warn">{pending.length}</span> of your submission
            {pending.length === 1 ? " is" : "s are"} still awaiting review.
          </>
        ) : all.length === 0 ? (
          <>You have not submitted anything yet.</>
        ) : (
          <>Everything you have submitted has been reviewed.</>
        )}
        sub={
          "Submissions enter a pending state and change nothing until a regulator " +
          "or administrator approves them. You cannot approve your own work — that " +
          "separation is enforced by a database constraint, not just by this screen."
        }
      >
        <Readout label="Awaiting review" value={pending.length}
                 tone={pending.length ? "warn" : "ok"} />
        <Readout label="Approved, not in model" value={waitingSync}
                 tone={waitingSync ? "warn" : "ok"} sub="until the next dataset sync" />
        <Readout label="In the model" value={inModel.length} tone="ok" />
        <Readout label="Rejected" value={rejected.length}
                 tone={rejected.length ? "danger" : "ok"} sub="with the reviewer's note" />
      </Statement>

      <SectionHead
        title="Record what you found"
        action={<button className="btn primary" onClick={() => nav("/field")}>New observation →</button>}
      >
        Ore occurrences, water samples and groundwater levels, filed against a
        named well or station.
      </SectionHead>

      <SectionHead title="My recent submissions" />
      {mine.isLoading ? <Loading /> : all.length === 0 ? (
        <QueueClear>
          Nothing submitted yet. Your submissions, and only yours, appear here.
        </QueueClear>
      ) : (
        <Queue>
          {all.slice(0, 8).map((o) => {
            const state = o.status === "approved"
              ? (o.synced_to_dataset_at ? "ok" : "warn")
              : o.status === "rejected" ? "danger"
              : o.status === "pending" ? "warn" : "info";
            const chip = o.status === "approved"
              ? (o.synced_to_dataset_at
                  ? <span className="chip ok">🟢 In model</span>
                  : <span className="chip warn">🟡 Approved · not in model</span>)
              : <span className={`chip ${o.status === "rejected" ? "danger" : "warn"}`}>
                  {o.status === "rejected" ? "🔴 Rejected" : "🔴 Pending review"}
                </span>;
            return (
              <QueueItem
                key={o.id}
                tone={state as "ok" | "warn" | "danger" | "info"}
                title={`${o.operation} · ${o.observation_type.replace(/_/g, " ")}`}
                meta={
                  <>
                    submitted {ago(o.submitted_at)}
                    {o.review_note ? ` · reviewer: “${o.review_note}”` : ""}
                  </>
                }
                side={chip}
                onClick={() => nav("/field")}
              />
            );
          })}
        </Queue>
      )}
    </div>
  );
}

// ── CITIZEN ──────────────────────────────────────────────────────────

function CitizenOverview() {
  const nav = useNavigate();
  const risk = useDistrictRisk();

  const all = risk.data?.districts ?? [];
  const limit = risk.data?.safe_limit ?? 30;
  const count = (b: string) => all.filter((d) => d.band === b).length;

  // Counted by the SERVER'S band, which reads uranium, nitrate and fluoride.
  // Counting `max_uranium_ppb >= 30` here instead — as this screen used to —
  // reports zero for the whole state, because uranium exceeds its limit at no
  // tested well in Jharkhand. That is a true sentence about uranium and a
  // false impression about the water.
  const high = count("High concern");
  const moderate = count("Moderate concern");
  const low = count("Low concern");
  // The two gaps stay separate: never sampled at all, versus sampled and never
  // analysed for any health determinand. Only one of them is fixed by sending
  // a sampling team.
  const noData = count("No data");
  const notTested = count("Not tested");
  const uraniumHigh = all.filter((d) => (d.max_uranium_ppb ?? 0) >= limit).length;

  return (
    <div className="page citizen">
      <Head />

      <div className="banner warn" style={{ marginBottom: "var(--s-5)" }}>
        {risk.data?.what_this_is ??
          "No uranium mine of the type this platform models operates in Jharkhand."}
      </div>

      <Statement
        eyebrow="Jharkhand · government test results"
        line={high > 0 ? (
          <>
            In <span className="hl danger">{high}</span> of {all.length} districts, at
            least one well tested above a health limit.
          </>
        ) : (
          <>
            No district has a well testing above a{" "}
            <span className="hl ok">health limit</span> in this dataset.
          </>
        )}
        sub={
          <>
            These are real laboratory measurements from government sampling — not
            predictions. Areas are judged on uranium, fluoride and nitrate together.
            {uraniumHigh === 0 && high > 0 && (
              <>
                {" "}Uranium itself is at or above the {limit} ppb limit in no district;
                the bands above come from fluoride and nitrate, which is exactly why
                one determinand alone is not enough.
              </>
            )}
            {" "}A district with no result has not been found safe — it has not been
            tested.
          </>
        }
      >
        <Readout label="Above a health limit" value={high}
                 tone={high ? "danger" : "ok"} />
        <Readout label="Worth watching" value={moderate}
                 tone={moderate ? "warn" : "ok"} />
        <Readout label="Never sampled" value={noData} tone="gap"
                 sub="a monitoring gap, not a clean result" />
        <Readout label="Sampled, never analysed" value={notTested} tone="gap"
                 sub="no health determinand tested there" />
      </Statement>

      <Composition
        segments={[
          { key: "low", label: "low concern", n: low, tone: "ok" },
          { key: "mod", label: "worth watching", n: moderate, tone: "warn" },
          { key: "high", label: "above a health limit", n: high, tone: "danger" },
          { key: "nt", label: "sampled, never analysed", n: notTested, tone: "gap" },
          { key: "nd", label: "never sampled", n: noData, tone: "gap" },
        ]}
        caption="The hatched shares are what nobody has measured. They are not safe areas — they are unknown ones."
      />

      <SectionHead
        title="Groundwater near you"
        action={<button className="btn primary lg" onClick={() => nav("/my-area")}>My area →</button>}
      >
        Follow the block you live in to see what was tested there, what it means,
        and who to contact.
      </SectionHead>

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
    // Restored in R15 to match migration `0022`, which brought the role back
    // with a narrower job. It previously fell through to the admin screen —
    // see the file header for what that cost.
    case "regulator": return <RegulatorOverview />;
    case "analyst": return <AnalystOverview />;
    case "field_officer": return <FieldOverview />;
    default: return <CitizenOverview />;
  }
}
