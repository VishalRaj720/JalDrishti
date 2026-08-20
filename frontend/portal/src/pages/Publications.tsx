/**
 * The publication queue — the one screen where something becomes public.
 *
 * This is the regulator's actual job, and before P4 the role did not really
 * have one: its only unique power was approving ore observations, a trickle.
 * Everything an analyst produced stopped at the analyst. Here a screening
 * either reaches residents or does not, and a named person owns that.
 *
 * DESIGNED AROUND THE DECISION, NOT THE RECORD. A reviewer needs three things
 * before they can honestly say yes: exactly what a citizen will read, how far
 * the footprint actually reaches, and which run stands behind it. All three are
 * on screen together, because a decision made from a list of headlines is a
 * decision made from headlines.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Advisory, type IsrPoint, type SimRun } from "../api/client";
import { canReview, useAuth } from "../auth";
import { Empty, ErrorNote, Field, Loading } from "../components/bits";
import { AffectedBlocks } from "../console/ProposeAdvisory";
import { fmt } from "../console/mapLayers";
import { SPECIES_NAME } from "../map/plume";

const STATUS_CLS: Record<string, string> = {
  published: "ok", proposed: "warn", withdrawn: "danger", rejected: "neutral",
};

function Card({ a, sites, reviewer }: {
  a: Advisory; sites: IsrPoint[]; reviewer: boolean;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState<"publish" | "withdraw" | null>(null);

  const site = sites.find((s) => s.id === a.isr_point_id);
  const run = useQuery({
    queryKey: ["run", a.run_id],
    queryFn: () => api.get<SimRun>(`/simulations/runs/${a.run_id}`),
  });

  const decide = useMutation({
    mutationFn: (decision: "publish" | "reject" | "withdraw") =>
      api.post<Advisory>(`/advisories/${a.id}/decision`,
                         { decision, note: note.trim() || null }),
    onSuccess: () => {
      setNote(""); setConfirming(null);
      qc.invalidateQueries({ queryKey: ["advisories"] });
    },
  });

  return (
    <div className="card">
      <div className="card-title">
        {site?.name ?? "Site"}
        <span className="spacer grow" />
        <button className="btn ghost" onClick={() => nav(`/report/${a.isr_point_id}`)}>
          Full report →
        </button>
        <span className={`chip ${STATUS_CLS[a.status] ?? "neutral"}`}>{a.status}</span>
      </div>

      <div className="banner" style={{ marginBottom: 10 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>{a.headline}</div>
        <div className="prose" style={{ whiteSpace: "pre-wrap", fontSize: "var(--fs-sm)" }}>
          {a.what_it_means}
        </div>
        {a.what_to_do && (
          <div className="prose" style={{ whiteSpace: "pre-wrap", marginTop: 8,
                                          fontSize: "var(--fs-sm)" }}>
            <strong>What to do:</strong> {a.what_to_do}
          </div>
        )}
      </div>
      <div className="muted small" style={{ marginBottom: 10 }}>
        Exactly as a resident would read it. Publishing does not edit this text.
      </div>

      <div className="grid-2">
        <div>
          <div className="sec" style={{ marginTop: 0 }}>How far it actually reaches</div>
          <AffectedBlocks advisory={a} />
        </div>

        <div>
          <div className="sec" style={{ marginTop: 0 }}>The run behind it</div>
          {run.isLoading && <Loading />}
          <dl className="kv">
            <dt>Contaminant</dt><dd>{SPECIES_NAME[a.species] ?? a.species}</dd>
            <dt>Evaluated at</dt><dd>{fmt(a.time_years, 0)} yr</dd>
            <dt>Restoration</dt><dd>{fmt(a.restoration_years, 0)} yr</dd>
            {run.data && (
              <>
                <dt>Footprint</dt>
                <dd>{fmt(run.data.metrics?.analytical?.area_ha, 2)} ha</dd>
                <dt>Migration</dt>
                <dd>{fmt(run.data.metrics?.analytical?.migration_m, 1)} m</dd>
                <dt>Excursion</dt>
                <dd>{run.data.excursion?.excursion_declared
                  ? <span className="chip danger">declared</span>
                  : <span className="chip ok">none</span>}</dd>
                <dt>Model card</dt>
                <dd className="mono">{run.data.model_card_sha?.slice(0, 14)}…</dd>
              </>
            )}
          </dl>
          {(run.data?.extrapolation?.length ?? 0) > 0 && (
            <div className="banner warn">
              This run is <b>outside the model's trained support</b> (
              <span className="mono">{run.data!.extrapolation!.join(", ")}</span>).
              The analytical engine served it, but the ML band carries no conformal
              guarantee. Consider whether that belongs in a public statement.
            </div>
          )}
        </div>
      </div>

      <div className="muted small" style={{ marginTop: 10 }}>
        Proposed {new Date(a.proposed_at).toLocaleString()}
        {a.published_at && ` · published ${new Date(a.published_at).toLocaleString()}`}
        {a.withdrawn_at && ` · withdrawn ${new Date(a.withdrawn_at).toLocaleString()}`}
        {a.decision_note && ` · “${a.decision_note}”`}
      </div>

      {reviewer && (a.status === "proposed" || a.status === "published") && (
        <>
          <Field label="Decision note — recorded in the audit trail" htmlFor={`n-${a.id}`}>
            <input id={`n-${a.id}`} value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="why you are publishing, rejecting or withdrawing" />
          </Field>

          {confirming ? (
            <div className="banner danger">
              <strong>
                {confirming === "publish"
                  ? "Publish to residents?"
                  : "Withdraw from public view?"}
              </strong>{" "}
              {confirming === "publish"
                ? `This becomes visible to citizens in ${a.affected_blocks?.length ?? 0} block(s) and appears in their alerts. It can be withdrawn later, but not un-seen.`
                : "Residents who have already read it will no longer see it."}
              <div className="row" style={{ marginTop: 8 }}>
                <button className="btn primary" disabled={decide.isPending}
                        onClick={() => decide.mutate(confirming)}>
                  {decide.isPending ? "Working…" : `Yes, ${confirming}`}
                </button>
                <button className="btn ghost" onClick={() => setConfirming(null)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="row wrap">
              {a.status === "proposed" && (
                <>
                  <button className="btn primary" onClick={() => setConfirming("publish")}>
                    Publish
                  </button>
                  <button className="btn danger" disabled={decide.isPending}
                          onClick={() => decide.mutate("reject")}>Reject</button>
                </>
              )}
              {a.status === "published" && (
                <button className="btn danger" onClick={() => setConfirming("withdraw")}>
                  Withdraw
                </button>
              )}
            </div>
          )}
          <ErrorNote error={decide.error} />
        </>
      )}
    </div>
  );
}

export default function Publications() {
  const { me } = useAuth();
  const reviewer = canReview(me?.role);
  const [filter, setFilter] = useState<string>("proposed");

  const advisories = useQuery({
    queryKey: ["advisories"],
    queryFn: () => api.get<Advisory[]>("/advisories?limit=200"),
  });
  const sites = useQuery({
    queryKey: ["isr-points"], queryFn: () => api.get<IsrPoint[]>("/isr-points"),
  });

  const all = advisories.data ?? [];
  const shown = filter === "all" ? all : all.filter((a) => a.status === filter);
  const count = (s: string) => all.filter((a) => a.status === s).length;

  return (
    <div className="page">
      <div className="page-head">
        <h1>Publications</h1>
        <p>
          {reviewer
            ? "Screenings proposed for the public. Publishing makes one visible to residents of the blocks its modelled footprint actually reaches — and puts your name on it."
            : "Screenings you and your colleagues have proposed, and what a regulator decided. Publishing is a regulator decision."}
        </p>
      </div>

      <div className="seg" style={{ marginBottom: 14, maxWidth: 620 }}>
        {[
          { v: "proposed", l: `Awaiting decision (${count("proposed")})` },
          { v: "published", l: `Published (${count("published")})` },
          { v: "withdrawn", l: `Withdrawn (${count("withdrawn")})` },
          { v: "rejected", l: `Rejected (${count("rejected")})` },
          { v: "all", l: `All (${all.length})` },
        ].map((t) => (
          <button key={t.v} className={filter === t.v ? "active" : ""}
                  onClick={() => setFilter(t.v)}>{t.l}</button>
        ))}
      </div>

      {advisories.isLoading && <Loading />}
      <ErrorNote error={advisories.error} />

      {!advisories.isLoading && shown.length === 0 && (
        <Empty>
          {filter === "proposed"
            ? "Nothing is waiting on a decision. Screenings appear here when an analyst proposes one from a completed run in the Console."
            : `No ${filter} advisories.`}
        </Empty>
      )}

      {shown.map((a) => (
        <Card key={a.id} a={a} sites={sites.data ?? []} reviewer={reviewer} />
      ))}
    </div>
  );
}
