/**
 * The alert inbox — two channels, kept visibly apart.
 *
 * THE ONE THING THIS SCREEN MUST NOT DO is present a measured exceedance and a
 * published screening as the same kind of thing.
 *
 *   MEASURED   a well near you was tested and came back over the safe limit.
 *              True, dated, laboratory-confirmed. It gets the red treatment and
 *              no hedging whatsoever — hedging a real exceedance is how a
 *              warning stops being read.
 *   SCREENING  a regulator published a model of what a hypothetical uranium
 *              operation would do. No such mine exists in Jharkhand. It gets a
 *              distinct colour, a distinct label, and the premise in its body.
 *
 * A resident who cannot tell them apart will either panic at the second or
 * ignore the first, and both failures would be ours.
 *
 * R16: alerts are ALSO emailed to the address on the account (services/
 * notify.py), and this screen says so -- and says where to turn that off.
 *
 * R17: every alert carries a TIER on the IS 10500 acceptable/permissible
 * ladder (notice / warning / alert / critical) and a structured explanation
 * answering the seven questions a reader has -- what happened, which
 * substance, where, how serious, measured or modelled, how sure, what next.
 * The card renders those fields as a record, not as prose, and a row written
 * before R17 (no explanation yet) says "not recorded" rather than pretending.
 */
import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  api, citizen, type AlertExplanation, type AlertTier, type AlertTiersLegend,
  type CitizenAlert,
} from "../api/client";
import { Empty, ErrorNote, Loading } from "../components/bits";

type Filter = "all" | "measured_exceedance" | "published_screening"
  | "aquifer_pathway" | "possible_reach";

/** Tier -> chip tone. `critical` and `alert` are red because they are the
 *  rungs that call for action; `warning` amber; `notice` neutral. */
const TIER: Record<AlertTier, { label: string; chip: string; border: string }> = {
  critical: { label: "Critical", chip: "danger", border: "danger" },
  alert:    { label: "Alert",    chip: "danger", border: "danger" },
  warning:  { label: "Warning",  chip: "warn",   border: "warn" },
  notice:   { label: "Notice",   chip: "neutral", border: "border" },
};

function fmtBand(b?: { p10?: number; p50?: number; p90?: number } | null, unit = "") {
  if (!b || b.p50 === undefined) return null;
  const f = (v?: number) => (v === undefined ? "–" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }));
  return `${f(b.p10)} / ${f(b.p50)} / ${f(b.p90)}${unit ? ` ${unit}` : ""}`;
}

/** The seven questions, answered from the structured fields. Read
 *  defensively: shapes differ by basis, and older rows have no explanation. */
function Explanation({ x, tier }: { x: AlertExplanation | null; tier: AlertTier }) {
  if (!x) {
    return (
      <div className="muted small" style={{ marginTop: 10 }}>
        Structured explanation not recorded for this alert (written before the
        record format existed). The full text above is the alert as issued.
      </div>
    );
  }
  const d = x.driver ?? {};
  const c = x.confidence ?? {};
  const observed = x.basis === "observed";
  const rows: Array<[string, ReactNode]> = [
    ["What happened", x.what_happened],
    ["Driven by", d.determinand
      ? <>
          <b>{d.determinand}</b> {d.value} {d.unit} against a limit of {d.limit} {d.unit}
          {d.limit_kind ? ` (${d.limit_kind})` : ""}{d.times_limit ? ` — ${d.times_limit}×` : ""}
          {(d.all_breaches?.length ?? 0) > 1 && (
            <div className="muted small">
              also {d.all_breaches!.slice(1).map((b) =>
                `${b.determinand} ${b.value} ${b.unit} (limit ${b.limit} ${b.unit})`).join("; ")}
            </div>
          )}
        </>
      : <>{d.quantity ?? "—"}{d.species ? <span className="muted"> · {d.species}</span> : null}</>],
    ["Where", <>{x.where?.block}{x.where?.district ? `, ${x.where.district}` : ""}
      {x.where?.well_name ? <> — {x.where.well_name}</> : null}
      {x.where?.scope ? <span className="muted small"> ({x.where.scope})</span> : null}</>],
    ["How serious", <><span className={`chip ${TIER[tier].chip}`}>{TIER[tier].label}</span>{" "}
      <span className="muted small">{x.tier?.rule}</span></>],
    ["Basis", observed
      ? <><b>Observed</b> — a laboratory measurement, not a prediction.</>
      : <><b>Modelled</b> — a screening of a hypothetical scenario. No ISR uranium
          mine operates in Jharkhand; nothing has been measured.</>],
    ["Confidence", observed
      ? <>{c.source ?? "Laboratory result"}{c.sampled_at ? `, sampled ${String(c.sampled_at).slice(0, 10)}` : ""}
          {c.single_sample ? " · a single sample, so a reading rather than a trend" : ""}
          {c.note ? <div className="muted small">{c.note}</div> : null}</>
      : <>
          {fmtBand(c.migration_m, "m")
            ? <>Migration P10 / P50 / P90: <b>{fmtBand(c.migration_m, "m")}</b>
                {c.band_source ? <span className="muted small"> ({c.band_source} band)</span> : null}</>
            : <>Band not recorded on this run</>}
          {c.excursion_probability !== undefined && c.excursion_probability !== null &&
            <div>Excursion probability at the monitoring ring: <b>{c.excursion_probability}</b></div>}
          {c.breakthrough_years ? <div>Modelled shallow-aquifer breakthrough: <b>{c.breakthrough_years} yr</b>
            {c.breakthrough_probability !== undefined && c.breakthrough_probability !== null
              ? ` (probability ${Math.round(Number(c.breakthrough_probability) * 100)}%)` : ""}</div> : null}
          <div className={c.in_trained_support === false ? "" : "muted small"}>
            {c.in_trained_support === false
              ? <><span className="chip warn">extrapolating</span> outside the trained
                  support on {c.extrapolation?.join(", ")} — the band's guarantee does not hold there</>
              : "Inside the model's trained support."}
          </div>
          {c.beta_band && <div className="muted small">
            Matrix-storage ratio β sampled over {c.beta_band[0]}–{c.beta_band[1]} in this band.</div>}
          {c.note ? <div className="muted small">{c.note}</div> : null}
        </>],
    ["What next", (x.next_action?.length ?? 0) > 0
      ? <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
          {x.next_action.map((a, i) => <li key={i}>{a}</li>)}
        </ul>
      : "—"],
  ];
  return (
    <dl style={{ marginTop: 12 }}>
      {rows.map(([k, v]) => (
        <div key={k} style={{ display: "grid", gridTemplateColumns: "minmax(110px, 140px) 1fr", gap: 8, padding: "6px 0", borderTop: "1px solid var(--border)" }}>
          <dt className="muted small" style={{ margin: 0 }}>{k}</dt>
          <dd style={{ margin: 0 }}>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

const KIND = {
  measured_exceedance: {
    label: "Measured result",
    chip: "danger",
    lead: "A real laboratory test",
  },
  published_screening: {
    label: "Assessment",
    chip: "warn",
    lead: "A modelled scenario",
  },
  // R11. Deliberately worded as sharing a water body rather than as a result:
  // this alert goes to blocks the modelled plume never touches, and reading it
  // as "your water is affected" would be exactly the over-claim it is bounded
  // to avoid.
  aquifer_pathway: {
    label: "Shared aquifer",
    chip: "warn",
    lead: "A modelled pathway into water this area shares",
  },
  // R14. The only alert that fires because time passed rather than because
  // somebody acted. Labelled "Timetable passed" rather than anything resembling
  // "breach" or "detected": no mine exists, nothing has been measured, and the
  // finding is that a published assessment's own schedule has run out.
  aquifer_breach_due: {
    label: "Timetable passed",
    chip: "warn",
    lead: "A published screening's modelled schedule has been reached",
  },
  // R17. Blocks inside the model's UPPER (P90) estimate that the central
  // footprint never touches. Worded as the width of the uncertainty band: the
  // model cannot rule the block out, and that is all it says.
  possible_reach: {
    label: "Uncertainty band",
    chip: "warn",
    lead: "Inside the upper estimate of a modelled screening, outside its central one",
  },
} as const;

/** Never index `KIND` blind: an unknown kind from a newer backend must not
 *  white-screen the page a resident opens to check their water. */
const UNKNOWN = { label: "Notice", chip: "neutral", lead: "" } as const;

export default function Alerts() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string | null>(null);

  const inbox = useQuery({
    queryKey: ["citizen-alerts", filter],
    queryFn: () => api.get<{ alerts: CitizenAlert[]; unread: number; limit_ppb: number;
                             tiers?: AlertTiersLegend }>(
      `/citizen/alerts${filter === "all" ? "" : `?kind=${filter}`}`),
  });
  const [showLadder, setShowLadder] = useState(false);

  const read = useMutation({
    mutationFn: (id: string) => api.post(`/citizen/alerts/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["citizen-alerts"] }),
  });
  const readAll = useMutation({
    mutationFn: () => api.post("/citizen/alerts/read-all"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["citizen-alerts"] });
      qc.invalidateQueries({ queryKey: ["unread"] });
    },
  });

  const profile = useQuery({ queryKey: ["citizen-me"], queryFn: citizen.me, retry: false });

  const alerts = inbox.data?.alerts ?? [];
  const measured = alerts.filter((a) => a.kind === "measured_exceedance").length;

  return (
    <div className="page citizen">
      <div className="page-head">
        <h1>Your alerts</h1>
        <p>
          For the areas you follow.{" "}
          {profile.data?.alert_email_opt_in === false
            ? "Email delivery is turned off for your account; alerts appear here only."
            : profile.data?.email
              ? `New alerts are also emailed to ${profile.data.email}.`
              : "New alerts are also emailed to the address on your account."}{" "}
          Change that, or the areas you follow, from <a href="/my-area">My area</a>.
        </p>
      </div>

      {measured > 0 && filter !== "published_screening" && (
        <div className="banner danger" style={{ marginBottom: 14 }}>
          <strong>
            {measured} well{measured === 1 ? "" : "s"} near you tested above a
            drinking-water limit.
          </strong>{" "}
          These are real laboratory results from government sampling, not predictions.
        </div>
      )}

      <div className="seg" style={{ marginBottom: 14 }}>
        {([
          ["all", "Everything"],
          ["measured_exceedance", "Measured results"],
          ["published_screening", "Assessments"],
          ["possible_reach", "Uncertainty band"],
          ["aquifer_pathway", "Shared aquifer"],
        ] as Array<[Filter, string]>).map(([v, l]) => (
          <button key={v} className={filter === v ? "active" : ""}
                  onClick={() => setFilter(v)}>{l}</button>
        ))}
      </div>

      {(inbox.data?.unread ?? 0) > 0 && (
        <button className="btn" style={{ marginBottom: 12 }}
                disabled={readAll.isPending} onClick={() => readAll.mutate()}>
          Mark all as read ({inbox.data!.unread})
        </button>
      )}

      {inbox.isLoading && <Loading />}
      <ErrorNote error={inbox.error} />

      {!inbox.isLoading && alerts.length === 0 && (
        <Empty>
          No alerts for the areas you follow.{" "}
          <button className="link-btn" onClick={() => nav("/my-area")}>
            Follow an area
          </button>{" "}
          to start receiving them.
        </Empty>
      )}

      {alerts.map((a) => {
        const k = KIND[a.kind as keyof typeof KIND] ?? UNKNOWN;
        const t = TIER[(a.tier ?? "notice") as AlertTier] ?? TIER.notice;
        const isOpen = open === a.id;
        return (
          <div className="card" key={a.id}
               style={{ borderLeft: `3px solid var(--${t.border})`,
                 opacity: a.is_read ? 0.82 : 1 }}>
            <div className="row wrap" style={{ marginBottom: 6 }}>
              <span className={`chip ${t.chip}`} title={a.explanation?.tier?.rule ?? ""}>
                {t.label}
              </span>
              <span className={`chip ${k.chip}`}>{k.label}</span>
              <span className={`chip ${a.basis === "observed" ? "danger" : "neutral"}`}>
                {a.basis === "observed" ? "Measured" : "Modelled"}
              </span>
              <span className="muted small">{k.lead}</span>
              <span className="spacer grow" />
              {!a.is_read && <span className="chip info">New</span>}
            </div>

            <div style={{ fontWeight: 700, fontSize: "var(--fs-md)" }}>{a.headline}</div>
            <div className="muted small" style={{ marginTop: 3 }}>
              {a.block_name}{a.district_name ? `, ${a.district_name}` : ""}
              {" · "}{new Date(a.created_at).toLocaleDateString()}
            </div>

            {a.kind === "measured_exceedance" && a.measured_value !== null && (
              <div className="readonly-val" style={{ marginTop: 10 }}>
                <span className="muted small">
                  {a.well_name ?? "Monitoring well"}
                  {a.sampled_at &&
                    ` · tested ${new Date(a.sampled_at).toLocaleDateString()}`}
                </span>
                <span>
                  <span className="rv-v" style={{ color: "var(--danger)" }}>
                    {a.measured_value.toFixed(1)}
                  </span>
                  <span className="rv-u"> {a.measured_unit}</span>
                  {/* R17: the limit of the DRIVING determinand from the record.
                      This used to print the uranium limit (30) under every
                      reading, nitrate and fluoride included. Falls back to the
                      uranium limit only when the row has no record and is a
                      uranium reading. */}
                  {(() => {
                    const d = a.explanation?.driver;
                    const lim = d?.limit ?? (a.measured_unit === "ppb" ? inbox.data?.limit_ppb : undefined);
                    return lim !== undefined && lim !== null
                      ? <span className="rv-u"> (limit {lim}{d?.limit_kind ? `, ${d.limit_kind}` : ""})</span>
                      : null;
                  })()}
                </span>
              </div>
            )}

            {isOpen ? (
              <>
                <div className="prose" style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
                  {a.body}
                </div>
                <Explanation x={a.explanation} tier={(a.tier ?? "notice") as AlertTier} />
              </>
            ) : (
              <div className="prose muted" style={{ marginTop: 10 }}>
                {a.body.split("\n")[0].slice(0, 160)}
                {a.body.length > 160 ? "…" : ""}
              </div>
            )}

            <div className="row wrap" style={{ marginTop: 10 }}>
              <button className="btn ghost" onClick={() => {
                setOpen(isOpen ? null : a.id);
                if (!a.is_read) read.mutate(a.id);
              }}>
                {isOpen ? "Show less" : "Read the full alert"}
              </button>
              {!a.is_read && !isOpen && (
                <button className="btn ghost" onClick={() => read.mutate(a.id)}>
                  Mark as read
                </button>
              )}
            </div>
          </div>
        );
      })}

      {alerts.length > 0 && (
        <div className="muted small" style={{ marginTop: "var(--s-4)", lineHeight: "var(--lh-loose)" }}>
          <strong>Measured results</strong> come from government laboratory testing of
          groundwater and describe water as it was on the date shown.{" "}
          <strong>Assessments</strong> are computer models of what would happen if a
          uranium in-situ recovery operation were built at a location — no such mine
          operates in Jharkhand.{" "}
          <button className="link-btn" onClick={() => setShowLadder((v) => !v)}>
            {showLadder ? "Hide" : "How the levels are decided"}
          </button>
          {showLadder && inbox.data?.tiers && (
            <div className="card" style={{ marginTop: 8 }}>
              <div><b>Levels</b> follow {inbox.data.tiers.standard}: its <i>acceptable</i> limit
                and its <i>permissible limit in the absence of an alternate source</i>.</div>
              <dl style={{ margin: "8px 0 0" }}>
                {inbox.data.tiers.order.map((lvl) => (
                  <div key={lvl} style={{ display: "grid", gridTemplateColumns: "90px 1fr", gap: 8, padding: "3px 0" }}>
                    <dt><span className={`chip ${TIER[lvl].chip}`}>{TIER[lvl].label}</span></dt>
                    <dd style={{ margin: 0 }}>
                      <div><span className="muted">measured:</span> {inbox.data!.tiers!.observed[lvl] ?? "—"}</div>
                      <div><span className="muted">modelled:</span> {inbox.data!.tiers!.modelled[lvl] ?? "—"}</div>
                    </dd>
                  </div>
                ))}
              </dl>
              <div className="muted small" style={{ marginTop: 6 }}>
                Project-defined, not from the standard: {inbox.data.tiers.project_defined.join("; ")}.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
