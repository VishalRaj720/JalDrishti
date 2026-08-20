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
 * Delivery is in-portal only. There is no notification service, so the screen
 * says that plainly rather than implying an SMS is on its way.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type CitizenAlert } from "../api/client";
import { Empty, ErrorNote, Loading } from "../components/bits";

type Filter = "all" | "measured_exceedance" | "published_screening"
  | "aquifer_pathway";

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
    queryFn: () => api.get<{ alerts: CitizenAlert[]; unread: number; limit_ppb: number }>(
      `/citizen/alerts${filter === "all" ? "" : `?kind=${filter}`}`),
  });

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

  const alerts = inbox.data?.alerts ?? [];
  const measured = alerts.filter((a) => a.kind === "measured_exceedance").length;

  return (
    <div className="page citizen">
      <div className="page-head">
        <h1>Your alerts</h1>
        <p>
          For the areas you follow. Alerts appear here only — this portal does not
          send SMS or email.
        </p>
      </div>

      {measured > 0 && filter !== "published_screening" && (
        <div className="banner danger" style={{ marginBottom: 14 }}>
          <strong>
            {measured} well{measured === 1 ? "" : "s"} near you tested above the safe
            limit for uranium.
          </strong>{" "}
          These are real laboratory results from government sampling, not predictions.
        </div>
      )}

      <div className="seg" style={{ marginBottom: 14 }}>
        {([
          ["all", "Everything"],
          ["measured_exceedance", "Measured results"],
          ["published_screening", "Assessments"],
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
        const isOpen = open === a.id;
        return (
          <div className="card" key={a.id}
               style={{ borderLeft: `3px solid var(--${
                 a.kind === "measured_exceedance" ? "danger" : "warn"})`,
                 opacity: a.is_read ? 0.82 : 1 }}>
            <div className="row wrap" style={{ marginBottom: 6 }}>
              <span className={`chip ${k.chip}`}>{k.label}</span>
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
                  <span className="rv-u"> (limit {inbox.data?.limit_ppb ?? 30})</span>
                </span>
              </div>
            )}

            {isOpen ? (
              <div className="prose" style={{ marginTop: 10, whiteSpace: "pre-wrap" }}>
                {a.body}
              </div>
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
          operates in Jharkhand.
        </div>
      )}
    </div>
  );
}
