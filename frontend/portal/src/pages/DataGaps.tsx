/**
 * Data & Gaps — the proposal's second deliverable, given its own screen.
 *
 * "Identify key data gaps and recommend improved monitoring strategies" is a
 * stated objective, not a footnote, so coverage and provenance are a
 * destination here rather than a caption somewhere else. This screen also owns
 * the dataset sync, because the sync is the moment the portal's record and the
 * model's inputs are reconciled.
 *
 * ── R15 RESTRUCTURE ──
 *
 * The deficiency matrix — the single most distinctive thing this project has to
 * show — was a numeric table twenty-four rows deep. "Where is the network
 * blind" is a question about pattern, and a grid of bare integers makes the
 * reader compute the pattern themselves. It is now a coverage grid: the same
 * numbers, still printed in full, with a four-step intensity behind them so the
 * holes are visible from across a room. Nothing was aggregated away.
 *
 * A STALE `Planned` CARD WAS REMOVED. It sat at the foot of this screen
 * claiming that ranking candidate monitoring locations "needs an optimisation
 * the backend does not implement" — directly below the section that does
 * exactly that, from `/data-gaps/recommendations`, with a per-block suggestion
 * map. Understating the product is a smaller sin than overstating it, but it is
 * still a false statement on a screen whose entire subject is what this project
 * does and does not know.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api, type GapMatrix, type Recommendations, type PublicDistrictRisk,
  type SyncStatus,
} from "../api/client";
import { canSync, useAuth } from "../auth";
import { ErrorNote, Loading, TableScroll, useRevealOnOpen } from "../components/bits";
import {
  Composition, Readout, SectionHead, Statement, covClass,
} from "../components/instruments";
import SiteSuggestionMap from "../console/SiteSuggestionMap";

interface PendingItem {
  id: string; observation_type: string; operation: string;
  target_table: string; reviewed_at: string | null;
  submitted_by_email: string | null; reviewed_by_email: string | null;
}

const NUM: React.CSSProperties = {
  textAlign: "right", fontVariantNumeric: "tabular-nums",
};

/**
 * The deficiency matrix, drawn.
 *
 * One row per district, one column per KIND of gap. The intensity is scaled
 * PER COLUMN, not globally: the columns count different things — untested
 * blocks, wells with no uranium result, stale samples — and a shared scale
 * would make the column with the largest natural magnitude the only one
 * visible. Each column's darkest cell is the worst district for that gap,
 * which is the comparison a reader actually makes.
 *
 * The count stays printed in every cell. A heat map whose values live only in a
 * tooltip is a picture of data rather than data, and this table is cited.
 */
function CoverageGrid({ m }: { m: GapMatrix }) {
  const maxByDim: Record<string, number> = {};
  for (const d of m.dimensions) {
    maxByDim[d.key] = m.districts.reduce(
      (mx, r) => Math.max(mx, Number(r[d.key] ?? 0)), 0);
  }

  return (
    <TableScroll>
      <table className="cov">
        <thead>
          <tr>
            <th className="name">District</th>
            <th style={NUM}>Blocks</th>
            <th style={NUM}>Wells</th>
            {m.dimensions.map((d) => (
              <th key={d.key} title={`${d.label} — ${d.means}`}>{d.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {m.districts.map((r) => (
            <tr key={String(r.district)}>
              <td className="name" title={String(r.district)}>{r.district}</td>
              <td className="num">{r.blocks ?? 0}</td>
              <td className="num">{r.wells ?? 0}</td>
              {m.dimensions.map((d) => {
                const n = Number(r[d.key] ?? 0);
                return (
                  <td key={d.key}>
                    <span className={`cov-cell ${covClass(n, maxByDim[d.key])}`}
                          title={`${r.district} · ${d.label}: ${n}`}>
                      {n}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
          <tr className="total">
            <td className="name">All Jharkhand</td>
            <td className="num">{m.totals.blocks}</td>
            <td className="num">{m.totals.wells}</td>
            {m.dimensions.map((d) => (
              <td key={d.key}>
                <span className={`cov-cell ${m.totals[d.key] > 0 ? "s3" : "zero"}`}>
                  {m.totals[d.key]}
                </span>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </TableScroll>
  );
}

export default function DataGaps() {
  const { me } = useAuth();
  const qc = useQueryClient();

  const sync = useQuery({ queryKey: ["sync-status"], queryFn: () => api.get<SyncStatus>("/dataset-sync/status") });
  const pending = useQuery({
    queryKey: ["sync-pending"],
    queryFn: () => api.get<{ count: number; items: PendingItem[]; syncable_types: string[] }>("/dataset-sync/pending"),
  });
  const risk = useQuery({
    queryKey: ["public-risk"],
    queryFn: () => api.get<{ districts: PublicDistrictRisk[] }>("/public/risk/districts"),
  });
  const dq = useQuery({
    queryKey: ["dq-report"],
    queryFn: () => api.get<any>("/ingest/data-quality-report"),
    retry: false,
  });

  const runSync = useMutation({
    mutationFn: () => api.post<{ message: string; synced: number; retrain_required: boolean }>("/dataset-sync/ore"),
    onSuccess: () => ["sync-status", "sync-pending", "obs-map", "obs"].forEach(
      (k) => qc.invalidateQueries({ queryKey: [k] })),
  });

  const districts = risk.data?.districts ?? [];
  const noData = districts.filter((d) => d.samples === 0);
  const thin = districts.filter((d) => d.samples > 0 && d.wells < 10);
  const covered = districts.filter((d) => d.wells >= 10);

  const [siteFor, setSiteFor] = useState<{ id: string; name: string } | null>(null);
  //: The suggestion map renders below a 20-row table; without this the
  //: button appears to do nothing.
  const siteRef = useRevealOnOpen(siteFor?.id ?? null);

  /** One column per KIND of gap. Each carries the capability it denies and the
   *  limitation it forces, so LIMITATIONS.md can be read off the data instead of
   *  maintained by hand. */
  const matrix = useQuery({
    queryKey: ["gap-matrix"],
    queryFn: () => api.get<GapMatrix>("/data-gaps/matrix"),
  });

  const recs = useQuery({
    queryKey: ["gap-recommendations"],
    queryFn: () => api.get<Recommendations>("/data-gaps/recommendations?limit=20"),
  });

  const maxScore = (recs.data?.recommendations ?? []).reduce(
    (mx, r) => Math.max(mx, r.score), 0);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Data &amp; Gaps</h1>
        <p>
          Where the monitoring network is thin enough that a prediction should not be
          trusted — and the point at which approved field evidence reaches the model.
        </p>
      </div>

      <Statement
        eyebrow="Coverage · Jharkhand"
        line={noData.length > 0 ? (
          <>
            <span className="hl gap">{noData.length}</span> of {districts.length} districts
            have no groundwater sample in this dataset at all.
          </>
        ) : (
          <>
            Every district has at least one groundwater sample, though{" "}
            <span className="hl warn">{thin.length}</span> rest on fewer than ten wells.
          </>
        )}
        sub={
          "A district with no sample has not been found clean — it has not been " +
          "looked at. Everything on this screen is an observation about the network, " +
          "never a prediction about the water."
        }
      >
        <Readout label="No samples at all" value={noData.length} tone="gap"
                 sub="a gap, not a clean result" />
        <Readout label="Fewer than ten wells" value={thin.length}
                 tone={thin.length ? "warn" : "ok"} sub="sparse coverage" />
        <Readout label="Adequately sampled" value={covered.length} tone="ok" />
        <Readout label="Approved, not in model" value={sync.data?.approved_pending_sync ?? "–"}
                 tone={(sync.data?.approved_pending_sync ?? 0) ? "warn" : "ok"}
                 sub="awaiting a dataset sync" />
      </Statement>

      <Composition
        segments={[
          { key: "cov", label: "districts adequately sampled", n: covered.length, tone: "ok" },
          { key: "thin", label: "sparse (fewer than ten wells)", n: thin.length, tone: "warn" },
          { key: "none", label: "never sampled", n: noData.length, tone: "gap" },
        ]}
        caption="The hatched share is the part of the state this platform cannot speak for."
      />

      {/* ── the deficiency matrix ──
          Counts alone are a statistic. Each column carries what it denies and
          what it forces the project to admit, which is what turns a gap into a
          limitation. */}
      {matrix.isLoading && <Loading label="Reading the coverage matrix…" />}
      <ErrorNote error={matrix.error} />
      {matrix.data && (
        <>
          <SectionHead title="Where the network is blind">
            {matrix.data.what_this_is} Intensity is scaled within each column, so the
            darkest cell in a column is the worst district for that particular gap.
          </SectionHead>
          <CoverageGrid m={matrix.data} />

          <SectionHead title="What each column limits">
            This is the register in <code>docs/LIMITATIONS.md</code>, derived from the
            data rather than maintained by hand. A gap nobody can name the effect of is
            a statistic; a gap with its effect beside it is a limitation.
          </SectionHead>
          {matrix.data.dimensions.map((d) => (
            <div key={d.key} className="banner" style={{ marginBottom: 8 }}>
              <b>{d.label} — {matrix.data!.totals[d.key]}</b>
              <div className="muted small" style={{ marginTop: 4 }}>{d.means}</div>
              <div className="small" style={{ marginTop: 4 }}>
                <b>Prevents:</b> {d.blocks}
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                <b>So the project must say:</b> {d.implies}
              </div>
            </div>
          ))}
        </>
      )}

      {/* ── where to sample next: the proposal's recommendation half ── */}
      <SectionHead
        title="Where to sample next"
        action={<Link className="btn" to="/network-plan">Open the full map →</Link>}
      >
        {recs.data?.what_this_is}
      </SectionHead>

      {recs.isLoading && <Loading />}
      <ErrorNote error={recs.error} />
      {recs.data && (
        <>
          <TableScroll>
            <table className="grid">
              <thead>
                <tr>
                  <th>#</th><th>Priority</th><th>Block</th><th>District</th>
                  <th style={NUM}>Area</th>
                  <th style={NUM}>Wells</th>
                  <th style={NUM}>U tests</th>
                  <th>Why</th><th />
                </tr>
              </thead>
              <tbody>
                {recs.data.recommendations.map((r, i) => (
                  <tr key={r.id}>
                    <td className="muted">{i + 1}</td>
                    <td>
                      {/* The score and its share of the top score. A bare "88"
                          tells a reader nothing until they have read the whole
                          column; the bar makes the ranking legible in one pass. */}
                      <div className="row" style={{ gap: "var(--s-2)" }}>
                        <b style={{ fontVariantNumeric: "tabular-nums" }}>
                          {r.score.toFixed(0)}
                        </b>
                        <span className="rank-track" style={{ width: 54 }}>
                          <span className="rank-fill warn"
                                style={{ width: `${maxScore ? (r.score / maxScore) * 100 : 0}%` }} />
                        </span>
                      </div>
                    </td>
                    <td>{r.name}</td>
                    <td className="muted small">{r.district}</td>
                    <td style={NUM} className="small">{r.area_km2?.toFixed(0)} km²</td>
                    <td style={NUM} className={r.wells === 0 ? "warn-text" : ""}>{r.wells}</td>
                    <td style={NUM} className={r.uranium_tests === 0 ? "warn-text" : ""}>
                      {r.uranium_tests}
                    </td>
                    <td className="small muted">{r.reason}</td>
                    <td>
                      <button className="btn ghost"
                        onClick={() => setSiteFor(
                          siteFor?.id === r.id ? null : { id: r.id, name: r.name })}>
                        {siteFor?.id === r.id ? "Hide" : "Where exactly?"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>

          {siteFor && (
            <div ref={siteRef} className="card" style={{ marginTop: 12 }}>
              <div className="row between">
                <div className="sec" style={{ margin: 0 }}>
                  Where to put a well in {siteFor.name}
                </div>
                <button className="btn ghost" onClick={() => setSiteFor(null)}>Close</button>
              </div>
              <SiteSuggestionMap blockId={siteFor.id} />
            </div>
          )}

          <details style={{ marginTop: 10 }}>
            <summary className="muted small">
              How this is scored — these weights are a policy judgement, not a
              measurement
            </summary>
            <dl className="kv" style={{ marginTop: 8 }}>
              {Object.entries(recs.data.weights).map(([k, w]) => (
                <div key={k}>
                  <dt>{k.replace(/_/g, " ")} · {w.weight}</dt>
                  <dd className="small muted">{w.why}</dd>
                </div>
              ))}
            </dl>
            <p className="muted small">{recs.data.tie_break}</p>
          </details>
        </>
      )}

      {/* The sync — where the portal's record and the model's inputs reconcile. */}
      <SectionHead title="Dataset sync">
        The moment approved field evidence stops being a portal record and becomes a
        model input.
      </SectionHead>
      <div className="card">
        <div className="card-title">
          Status
          <span className="spacer grow" />
          {sync.data && (
            <span className={`chip ${sync.data.approved_pending_sync ? "warn" : "ok"}`}>
              {sync.data.approved_pending_sync ? "🟡 behind" : "🟢 in sync"}
            </span>
          )}
        </div>

        {sync.isLoading && <Loading />}
        {sync.data && (
          <>
            <div className="row wrap" style={{ gap: 14, marginBottom: 10 }}>
              <span className="chip danger">🔴 {sync.data.pending_review} pending review</span>
              <span className="chip warn">🟡 {sync.data.approved_pending_sync} approved, not in model</span>
              <span className="chip ok">🟢 {sync.data.approved_in_model} in model</span>
            </div>
            <div className="muted small" style={{ lineHeight: 1.6, marginBottom: 11 }}>
              {sync.data.note}
            </div>

            {canSync(me?.role) ? (
              <>
                <button className="btn primary" disabled={runSync.isPending || !sync.data.approved_pending_sync}
                        onClick={() => runSync.mutate()}>
                  {runSync.isPending ? "Syncing…" : "Sync approved ore observations → Datasets/"}
                </button>
                <div className="muted small" style={{ marginTop: 7 }}>
                  Appends to the deposit CSV and the grade workbook, tagging each new row
                  <span className="mono"> origin=added</span>. Both files are backed up
                  first. This changes a <em>resolved input</em>, not the trained model —
                  no retrain is triggered.
                </div>
              </>
            ) : (
              <div className="muted small">
                Only an administrator can run the sync. Ask one to reconcile the
                {" "}{sync.data.approved_pending_sync} outstanding item(s).
              </div>
            )}
            {runSync.data && (
              <div className="banner ok" style={{ marginTop: 10 }}>
                ✅ {runSync.data.message} · retrain required:{" "}
                <strong>{String(runSync.data.retrain_required)}</strong>
              </div>
            )}
            <ErrorNote error={runSync.error} />
          </>
        )}
      </div>

      {(pending.data?.count ?? 0) > 0 && (
        <div className="card">
          <div className="card-title">
            Approved but not yet in the model
            <span className="spacer grow" />
            <span className="muted small">
              only {pending.data?.syncable_types.join(", ")} syncs automatically
            </span>
          </div>
          <TableScroll>
            <table className="grid">
              <thead>
                <tr><th>Type</th><th>Operation</th><th>Target</th><th>Approved</th><th>By</th></tr>
              </thead>
              <tbody>
                {pending.data?.items.map((i) => (
                  <tr key={i.id}>
                    <td>{i.observation_type.replace(/_/g, " ")}</td>
                    <td>{i.operation}</td>
                    <td className="mono">{i.target_table}</td>
                    <td className="muted">{i.reviewed_at ? new Date(i.reviewed_at).toLocaleDateString() : "–"}</td>
                    <td className="muted small">{i.reviewed_by_email ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
          <div className="muted small" style={{ marginTop: 8 }}>
            Anything outside the syncable types is applied by hand from the audit trail —
            those changes move a value the model was already trained across, so they are
            rare and deliberate.
          </div>
        </div>
      )}

      <SectionHead title="Monitoring coverage by district">
        Thinnest first. The last column names the health determinands that have never
        been analysed there — arsenic and iron appear for every district because they
        are 0 % populated statewide, so no block in Jharkhand has been cleared for
        either.
      </SectionHead>
      {risk.isLoading && <Loading />}
      <TableScroll>
        <table className="grid">
          <thead>
            <tr>
              <th>District</th>
              <th style={NUM}>Wells</th>
              <th style={NUM}>Samples</th>
              <th style={NUM}>Max uranium (ppb)</th>
              <th>Coverage</th>
              <th>Never analysed here</th>
            </tr>
          </thead>
          <tbody>
            {[...districts].sort((a, b) => a.wells - b.wells).map((d) => (
              <tr key={d.id}>
                <td>{d.name}</td>
                <td className="mono">{d.wells}</td>
                <td className="mono">{d.samples}</td>
                <td className="mono">{d.max_uranium_ppb ?? "–"}</td>
                <td>
                  {d.samples === 0 ? <span className="chip danger">no data</span>
                    : d.wells < 10 ? <span className="chip warn">sparse</span>
                    : <span className="chip ok">adequate</span>}
                </td>
                <td className="muted small">
                  {(d.untested_health ?? []).length > 0
                    ? d.untested_health!.join(", ")
                    : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>

      {dq.data && (
        <div className="card" style={{ marginTop: "var(--s-4)" }}>
          <div className="card-title">Data-quality report</div>
          <div className="muted small" style={{ marginBottom: 8 }}>
            Generated by the seed/ingest pipeline.
          </div>
          <pre className="mono" style={{ maxHeight: 260, overflow: "auto", margin: 0 }}>
            {JSON.stringify(dq.data.row_counts ?? dq.data, null, 1)}
          </pre>
        </div>
      )}
    </div>
  );
}
