/**
 * Water quality — every measured determinand against IS 10500:2012.
 *
 * WHY THIS SCREEN EXISTS. Until 2026-08-24 this platform measured twenty
 * determinands and reported one. `water_samples` carries pH, EC, TDS, hardness,
 * nitrate, fluoride, chloride, sulphate, calcium and magnesium at 99-100 %
 * coverage, and every surface in the product banded a district on uranium
 * alone. That was not a small omission: uranium exceeds its limit at ZERO of
 * 342 tested wells, while nitrate exceeds at 22 and fluoride at 32. The single
 * indicator on screen was the one indicator that never fired.
 *
 * THE FRAMING THIS SCREEN HAS TO GET RIGHT. About 71 % of sampled wells exceed
 * some IS 10500 limit, and on its own that number misinforms: most of it is
 * hardness, alkalinity and TDS — hard-rock aquifer chemistry, not
 * contamination, and no mine caused it. So the health-significant count leads
 * and the general count follows, never the reverse, and the API's own
 * `interpretation` sentence is rendered rather than paraphrased.
 *
 * Nothing here is a prediction. No band, no interval, no extrapolation warning,
 * because there is no model — these are laboratory results and a published
 * standard.
 *
 * ── R15 RESTRUCTURE ──
 *
 * The screen was correct and hard to read: two `grid-4` tile walls, then five
 * tables. Three changes, no data added and none removed:
 *
 *   · the two tile walls become ONE STATEMENT — the sentence the screen exists
 *     to say — with the figures beneath it as a reading rather than as eight
 *     equally-weighted boxes;
 *   · the exceedance tables become RANKED BARS, because "which determinand
 *     fails most often" is a comparison and a table makes the reader do it;
 *   · the per-well determinand table becomes DETERMINAND SCALES, which draw the
 *     acceptable and permissible limits the numbers are being judged against.
 *     A reader should not need to already know that fluoride's limits are
 *     1.0/1.5 to understand that 1.42 is inside the relaxation band.
 *
 * The comparative district and block tables STAY tables. Twenty-four rows
 * compared across seven columns is a table's job, and turning it into cards
 * would be decoration at the cost of the comparison.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api, type WqBlock, type WqDistrict, type WqParameter, type WqRollup,
  type WqStandard, type WqStatus, type WqWell,
} from "../api/client";
import { ErrorNote, Loading, TableScroll, useRevealOnOpen } from "../components/bits";
import {
  Composition, CompositionMini, DeterminandScale, Freshness, RankBar, Readout,
  SectionHead, Statement, StatusChip, fmtVal, limitText, type Segment,
} from "../components/instruments";

const NUM: React.CSSProperties = {
  textAlign: "right", fontVariantNumeric: "tabular-nums",
};

/**
 * The four well classes, as a composition.
 *
 * `_rollup` in the API counts each well ONCE by its worst determinand, so these
 * four partition the sampled wells. The residual guard below exists anyway: if
 * the server ever adds a sixth status, a silently short bar would understate
 * the total rather than announce a gap, and understating is the failure mode
 * this whole screen is written against.
 */
function wellSegments(r: WqRollup): Segment[] {
  const segs: Segment[] = [
    { key: "perm", label: "above a permissible limit", n: r.above_permissible, tone: "danger" },
    { key: "acc", label: "above an acceptable limit", n: r.above_acceptable, tone: "warn" },
    { key: "ok", label: "within every limit", n: r.acceptable, tone: "ok" },
    { key: "gap", label: "never analysed", n: r.not_tested, tone: "gap" },
  ];
  const residual = r.wells - segs.reduce((s, x) => s + x.n, 0);
  if (residual > 0) {
    segs.push({ key: "other", label: "not classified", n: residual, tone: "gap" });
  }
  return segs;
}

/**
 * Order determinands for reading, not alphabetically.
 *
 * NOT TESTED SORTS ABOVE WITHIN-LIMITS, deliberately. A determinand nobody
 * analysed is more actionable than one that passed — it is the thing a sampling
 * round would fix — and burying it under the passes is how "we never looked for
 * uranium here" ends up below the fold.
 */
const READ_ORDER: Record<WqStatus, number> = {
  above_permissible: 0, above_acceptable: 1, not_tested: 2, no_limit: 3, acceptable: 4,
};
const forReading = (ps: WqParameter[]) =>
  [...ps].sort((a, b) =>
    READ_ORDER[a.status] - READ_ORDER[b.status] || a.label.localeCompare(b.label));

export default function WaterQuality() {
  const [districtId, setDistrictId] = useState<string | null>(null);
  const [openWell, setOpenWell] = useState<WqWell | null>(null);
  const [showStandard, setShowStandard] = useState(false);
  /** Block, not district, is the unit a monitoring decision is actually made
   *  in — it is what advisories and citizen alerts are scoped to — so the
   *  roll-up has to be available at that level too. */
  const [byBlock, setByBlock] = useState(false);

  //: Two panels on this screen open from a table row and render below it. The
  //: wells list sits under a 24-row district table; the parameter panel sits
  //: under a wells list that can run to hundreds of rows. Both were far enough
  //: below the fold that the button read as broken.
  const wellsRef = useRevealOnOpen(districtId);
  const detailRef = useRevealOnOpen(openWell?.well_id ?? null);

  const districts = useQuery({
    queryKey: ["wq-districts"],
    queryFn: () => api.get<{
      districts: WqDistrict[]; statewide: WqDistrict; standard: string;
      what_this_is: string;
    }>("/water-quality/districts"),
  });

  const wells = useQuery({
    queryKey: ["wq-wells", districtId],
    queryFn: () => api.get<{ count: number; wells: WqWell[]; rollup: WqDistrict }>(
      `/water-quality/wells?limit=2000${districtId ? `&district_id=${districtId}` : ""}`),
    enabled: districtId !== null,
  });

  const blocks = useQuery({
    queryKey: ["wq-blocks"],
    enabled: byBlock,
    queryFn: () => api.get<{ blocks: WqBlock[] }>("/water-quality/blocks"),
  });

  const standard = useQuery({
    queryKey: ["wq-standard"],
    queryFn: () => api.get<WqStandard>("/water-quality/standard"),
    enabled: showStandard,
  });

  const sw = districts.data?.statewide;
  const healthKeys = new Set((sw?.health_exceedances ?? []).map((h) => h.key));
  const leadHealth = sw?.health_exceedances[0];

  return (
    <div className="page">
      <div className="page-head">
        <h1>Water quality</h1>
        <p>
          Real laboratory results from government (CGWB) groundwater sampling,
          judged against IS 10500:2012. Measurements, not predictions — there is
          no model on this screen, no interval and no extrapolation flag.
        </p>
      </div>

      {districts.isLoading && <Loading label="Assessing every well…" />}
      <ErrorNote error={districts.error} />

      {sw && (
        <>
          {/* HEALTH FIRST, ALWAYS. "283 wells exceed a limit" as the opening
              line would be true and would misinform every reader of it. */}
          <Statement
            eyebrow="Statewide · IS 10500:2012"
            line={
              sw.health_exceedance_wells > 0 ? (
                <>
                  <span className="hl danger">{sw.health_exceedance_wells}</span> of{" "}
                  {sw.wells.toLocaleString("en-US")} sampled wells exceed a
                  health-significant limit
                  {leadHealth && <>, most often <span className="hl danger">{leadHealth.label.toLowerCase()}</span></>}.
                </>
              ) : (
                <>
                  No sampled well exceeds a{" "}
                  <span className="hl ok">health-significant</span> limit.
                </>
              )
            }
            sub={sw.interpretation}
          >
            <Readout label="Health exceedances" value={sw.health_exceedance_wells}
                     tone={sw.health_exceedance_wells ? "danger" : "ok"}
                     sub="uranium, fluoride, nitrate, arsenic, iron" />
            <Readout label="Above a permissible limit" value={sw.above_permissible}
                     tone={sw.above_permissible ? "danger" : "ok"}
                     sub="tolerated only with no alternate source" />
            <Readout label="General exceedance only" value={sw.aesthetic_only_wells}
                     tone="info" sub="hardness, TDS, alkalinity, Ca, Mg" />
            <Readout label="Within every limit" value={sw.acceptable} tone="ok" />
            {/* Never green, and never omitted for being awkward. */}
            <Readout label="Never analysed" value={sw.not_tested} tone="gap"
                     sub="a monitoring gap, not a clean result" />
            <Readout label="Median WQI" value={sw.median_wqi ?? "—"} tone="info"
                     sub={`over ${sw.wqi_wells} wells · secondary figure`} />
          </Statement>

          <SectionHead title="Every sampled well, by its worst determinand">
            Each well is counted once, in the most severe class any of its
            determinands falls into.
          </SectionHead>
          <Composition segments={wellSegments(sw)} />

          <SectionHead
            title="What exceeds, and how often"
            action={
              <button className="btn ghost" onClick={() => setShowStandard((v) => !v)}>
                {showStandard ? "Hide the limits" : "What are the limits?"}
              </button>
            }
          >
            Health-significant determinands first. The rest follow, and are the
            larger number — which is the point of separating them.
          </SectionHead>

          <div className="card">
            <div className="card-title">Health-significant</div>
            <div className="rank">
              {sw.health_exceedances.map((h) => (
                <RankBar key={h.key} label={h.label} n={h.wells} of={sw.wells}
                         tone="danger" chip={<span className="chip danger">health</span>}
                         note="share of all sampled wells" />
              ))}
              {sw.health_exceedances.length === 0 && (
                <div className="muted small">
                  No health-significant determinand exceeds its limit at any sampled
                  well. That is a result about the wells that were analysed — it says
                  nothing about the {sw.not_tested} that were not.
                </div>
              )}
            </div>

            <div className="card-title" style={{ marginTop: "var(--s-5)" }}>
              Most common overall
            </div>
            <div className="rank">
              {sw.top_exceedances.map((t) => (
                <RankBar key={t.key} label={t.label} n={t.wells} of={sw.wells}
                         tone={healthKeys.has(t.key) ? "danger" : "info"}
                         chip={healthKeys.has(t.key)
                           ? <span className="chip danger">health</span> : undefined} />
              ))}
            </div>
          </div>
        </>
      )}

      {showStandard && (
        <>
          <SectionHead title="The standard">
            {standard.data?.standard}{" "}
            {standard.data?.not_tested_rule}
          </SectionHead>
          {standard.isLoading && <Loading />}
          <ErrorNote error={standard.error} />
          {standard.data && (
            <TableScroll style={{ marginBottom: "var(--s-4)" }}>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Determinand</th><th>Unit</th>
                    <th style={NUM}>Acceptable</th>
                    <th style={NUM}>Permissible</th>
                    <th>Source</th><th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {standard.data.determinands.map((d) => (
                    <tr key={d.key}>
                      <td>
                        {d.label}{" "}
                        {d.health && <span className="chip danger">health</span>}
                        {d.derived && <span className="chip neutral">derived</span>}
                      </td>
                      <td className="muted small">{d.unit}</td>
                      <td style={NUM}>
                        {d.range ? `${d.range[0]}–${d.range[1]}` : fmtVal(d.acceptable)}
                      </td>
                      <td style={NUM}>
                        {d.permissible === null
                          ? <span className="muted small">{d.relaxation || "—"}</span>
                          : fmtVal(d.permissible)}
                      </td>
                      <td className="muted small">{d.source}</td>
                      <td className="muted small">{d.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </>
      )}

      <SectionHead
        title={byBlock ? "By block" : "By district"}
        action={
          <button className="btn ghost"
                  onClick={() => { setByBlock((v) => !v); setDistrictId(null); setOpenWell(null); }}>
            {byBlock ? "Show districts" : "Group by block"}
          </button>
        }
      >
        Worst first.{byBlock
          ? " Blocks are what advisories and citizen alerts are scoped to."
          : " Choose a district to list its wells."}{" "}
        The bar in each row is the same composition as above, for that row's wells.
      </SectionHead>

      {byBlock ? (
        <>
          {blocks.isLoading && <Loading />}
          <ErrorNote error={blocks.error} />
          <TableScroll>
            <table className="grid">
              <thead>
                <tr>
                  <th>Block</th><th>District</th>
                  <th style={NUM}>Wells</th>
                  <th>Composition</th>
                  <th style={NUM}>Health</th>
                  <th style={NUM}>Above perm.</th>
                  <th style={NUM}>Never analysed</th>
                  <th style={NUM}>Median WQI</th>
                  <th>Leading exceedance</th>
                </tr>
              </thead>
              <tbody>
                {(blocks.data?.blocks ?? []).map((b) => (
                  <tr key={b.id}>
                    <td>{b.name}</td>
                    <td className="muted small">{b.district ?? "—"}</td>
                    <td style={NUM}>{b.wells}</td>
                    <td><CompositionMini segments={wellSegments(b)} /></td>
                    <td style={NUM}>
                      {b.health_exceedance_wells
                        ? <strong style={{ color: "var(--danger)" }}>
                            {b.health_exceedance_wells}
                          </strong>
                        : <span className="muted">0</span>}
                    </td>
                    <td style={NUM}>{b.above_permissible}</td>
                    <td style={NUM} className={b.not_tested ? "" : "muted"}>{b.not_tested}</td>
                    <td style={NUM}>{b.median_wqi ?? "—"}</td>
                    <td className="muted small">
                      {b.top_exceedances[0]
                        ? `${b.top_exceedances[0].label} (${b.top_exceedances[0].wells})`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </>
      ) : (
        <TableScroll>
          <table className="grid">
            <thead>
              <tr>
                <th>District</th>
                <th style={NUM}>Wells</th>
                <th>Composition</th>
                <th style={NUM}>Health</th>
                <th style={NUM}>Above perm.</th>
                <th style={NUM}>Above acc.</th>
                <th style={NUM}>Within limits</th>
                <th style={NUM}>Never analysed</th>
                <th style={NUM}>Median WQI</th>
                <th>Leading exceedance</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(districts.data?.districts ?? []).map((d) => (
                <tr key={d.id}>
                  <td>{d.name}</td>
                  <td style={NUM}>{d.wells}</td>
                  <td><CompositionMini segments={wellSegments(d)} /></td>
                  <td style={NUM}>
                    {d.health_exceedance_wells
                      ? <strong style={{ color: "var(--danger)" }}>
                          {d.health_exceedance_wells}
                        </strong>
                      : <span className="muted">0</span>}
                  </td>
                  <td style={NUM}>{d.above_permissible}</td>
                  <td style={NUM}>{d.above_acceptable}</td>
                  <td style={NUM}>{d.acceptable}</td>
                  <td style={NUM} className={d.not_tested ? "" : "muted"}>{d.not_tested}</td>
                  <td style={NUM}>{d.median_wqi ?? "—"}</td>
                  <td className="muted small">
                    {d.top_exceedances[0]
                      ? `${d.top_exceedances[0].label} (${d.top_exceedances[0].wells})`
                      : "—"}
                  </td>
                  <td>
                    <button
                      className="btn ghost"
                      onClick={() => {
                        setOpenWell(null);
                        setDistrictId(districtId === d.id ? null : d.id);
                      }}
                    >
                      {districtId === d.id ? "Hide wells" : "Wells"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableScroll>
      )}

      {districtId && (
        <div ref={wellsRef}>
          <SectionHead title={`Wells${wells.data ? ` — ${wells.data.count}` : ""}`}>
            The age of each result is shown because for many of these wells the
            sample listed is the only one ever taken.
          </SectionHead>
          {wells.isLoading && <Loading />}
          <ErrorNote error={wells.error} />
          {wells.data && (
            <TableScroll>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Well</th><th>Block</th><th>Status</th>
                    <th>Driving determinand</th>
                    <th style={NUM}>× limit</th>
                    <th style={NUM}>Tested</th>
                    <th style={NUM}>WQI</th>
                    <th>Sampled</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {wells.data.wells.map((w) => (
                    <tr key={w.well_id}>
                      <td>{w.well_name}</td>
                      <td className="muted small">{w.block ?? "—"}</td>
                      <td><StatusChip status={w.summary.status} /></td>
                      <td>
                        {w.summary.driver
                          ? <>
                              {w.summary.driver.label}{" "}
                              <span className="muted small">
                                {fmtVal(w.summary.driver.value)} {w.summary.driver.unit}
                              </span>
                            </>
                          : <span className="muted">—</span>}
                      </td>
                      <td style={NUM}>{w.summary.driver?.times_limit ?? "—"}</td>
                      <td style={NUM}>
                        {w.summary.tested}
                        <span className="muted small"> / {w.parameters.length}</span>
                      </td>
                      <td style={NUM}>{w.wqi?.score ?? "—"}</td>
                      <td><Freshness at={w.sampled_at} prefix="" /></td>
                      <td>
                        <button
                          className="btn ghost"
                          onClick={() => setOpenWell(
                            openWell?.well_id === w.well_id ? null : w)}
                        >
                          {openWell?.well_id === w.well_id ? "Hide" : "All parameters"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          )}
        </div>
      )}

      {/* Inline rather than a modal: this project has no dialog primitive, and
          the full determinand readout is the reason someone came to this screen —
          it should be linkable, scrollable and printable with everything else. */}
      {openWell && (
        <div ref={detailRef} className="card" style={{ marginTop: "var(--s-4)" }}>
          <div className="row wrap" style={{ alignItems: "baseline" }}>
            <h2 style={{ margin: 0, fontSize: "var(--fs-lg)" }}>{openWell.well_name}</h2>
            <span className="spacer grow" />
            <Freshness at={openWell.sampled_at} />
            <button className="btn ghost" onClick={() => setOpenWell(null)}>
              Close
            </button>
          </div>
          <div className="muted small" style={{ margin: "4px 0 10px" }}>
            {openWell.block ?? "—"}, {openWell.district ?? "—"} ·{" "}
            {openWell.summary.tested} of {openWell.parameters.length} determinands
            analysed
          </div>

          {openWell.wqi && (
            <div className="banner" style={{ marginBottom: 10 }}>
              <strong>WQI {openWell.wqi.score} — {openWell.wqi.band}.</strong>
              {openWell.wqi.dominated_by && openWell.wqi.dominated_by.share !== null && (
                <>
                  {" "}
                  <strong>
                    {Math.round(openWell.wqi.dominated_by.share * 100)}% of this
                    score is {openWell.wqi.dominated_by.label.toLowerCase()}
                  </strong>{" "}
                  — {openWell.wqi.dominated_by.why}.
                </>
              )}{" "}
              {openWell.wqi.caveat}
            </div>
          )}

          {/* Health-significant determinands get their own block, above the
              rest, for the same reason the statement at the top of the screen
              does: order is a claim about importance whether or not it is
              meant to be. */}
          {(["health", "general"] as const).map((grp) => {
            const ps = forReading(
              openWell.parameters.filter((p) => (grp === "health" ? p.health : !p.health)));
            if (ps.length === 0) return null;
            return (
              <div key={grp}>
                <div className="card-title" style={{ marginTop: "var(--s-4)" }}>
                  {grp === "health"
                    ? "Health-significant determinands"
                    : "General and aesthetic determinands"}
                  <span className="spacer grow" />
                  <span className="muted" style={{ textTransform: "none", letterSpacing: 0 }}>
                    limits shown are IS 10500 acceptable / permissible
                  </span>
                </div>
                {ps.map((p) => (
                  <DeterminandScale
                    key={p.key}
                    label={p.label}
                    unit={p.unit}
                    value={p.value}
                    status={p.status}
                    acceptable={p.acceptable}
                    permissible={p.permissible}
                    range={p.range}
                    timesLimit={p.times_limit}
                    relaxation={p.relaxation}
                    health={p.health}
                    derived={p.derived}
                  />
                ))}
              </div>
            );
          })}

          {/* The exact figures, for anyone quoting them. The scales above are
              the reading; this is the record, and removing it would cost the
              screen its citability. */}
          <details style={{ marginTop: "var(--s-4)" }}>
            <summary className="muted small">
              The same values as a table, for quoting
            </summary>
            <TableScroll style={{ marginTop: "var(--s-2)" }}>
              <table className="grid">
                <thead>
                  <tr>
                    <th>Determinand</th>
                    <th style={NUM}>Value</th>
                    <th>Unit</th>
                    <th style={NUM}>Limit (acc. / perm.)</th>
                    <th style={NUM}>× limit</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {forReading(openWell.parameters).map((p) => (
                    <tr key={p.key}>
                      <td>
                        {p.label}{" "}
                        {p.health && <span className="chip danger">health</span>}
                        {p.derived && <span className="chip neutral">derived</span>}
                      </td>
                      <td style={NUM}>{fmtVal(p.value)}</td>
                      <td className="muted small">{p.unit}</td>
                      <td style={NUM}>{limitText(p)}</td>
                      <td style={NUM}>{p.times_limit ?? "—"}</td>
                      <td><StatusChip status={p.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScroll>
          </details>

          <div className="muted small" style={{ marginTop: 10 }}>
            “Not tested” means no measurement exists for that determinand at this
            well. It is a gap in monitoring, never a clean result.
          </div>
        </div>
      )}
    </div>
  );
}
