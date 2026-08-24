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
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api, type WqBlock, type WqDistrict, type WqStandard, type WqStatus,
  type WqWell,
} from "../api/client";
import { ErrorNote, Loading, TableScroll, Tile } from "../components/bits";

/** One vocabulary for the five statuses, used by every table on this screen. */
const STATUS: Record<WqStatus, { label: string; cls: string; glyph: string }> = {
  above_permissible: { label: "Above permissible", cls: "danger", glyph: "🔴" },
  above_acceptable: { label: "Above acceptable", cls: "warn", glyph: "🟠" },
  acceptable: { label: "Within limits", cls: "ok", glyph: "🟢" },
  // Deliberately NOT green: the determinand was analysed and the standard sets
  // no drinking-water limit for it. That is not a pass.
  no_limit: { label: "No BIS limit", cls: "neutral", glyph: "⚪" },
  // Deliberately NOT green either. Absence of evidence is a monitoring gap.
  not_tested: { label: "Not tested", cls: "neutral", glyph: "⚫" },
};

const NUM: React.CSSProperties = {
  textAlign: "right", fontVariantNumeric: "tabular-nums",
};

function StatusChip({ status }: { status: WqStatus }) {
  const s = STATUS[status];
  return <span className={`chip ${s.cls}`}>{s.glyph} {s.label}</span>;
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(digits);
}

/** The limit column, spelled out rather than reduced to one number.
 *  "1.0 / 1.5" and "45 (no relaxation)" are different regimes, and a reader
 *  acting on the number needs to know which one they are in. */
function limitText(p: {
  acceptable: number | null; permissible: number | null;
  range: [number | null, number | null] | null; relaxation: string;
}): string {
  if (p.range) return `${p.range[0]}–${p.range[1]}`;
  if (p.acceptable === null) return "—";
  if (p.permissible !== null) return `${p.acceptable} / ${p.permissible}`;
  return `${p.acceptable}${p.relaxation ? " (no relaxation)" : ""}`;
}

export default function WaterQuality() {
  const [districtId, setDistrictId] = useState<string | null>(null);
  const [openWell, setOpenWell] = useState<WqWell | null>(null);
  const [showStandard, setShowStandard] = useState(false);
  /** Block, not district, is the unit a monitoring decision is actually made
   *  in — it is what advisories and citizen alerts are scoped to — so the
   *  roll-up has to be available at that level too. */
  const [byBlock, setByBlock] = useState(false);

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

  return (
    <div className="page">
      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <h1>Water quality</h1>
        <span className="spacer grow" />
        <button className="btn ghost" onClick={() => setShowStandard((v) => !v)}>
          {showStandard ? "Hide the standard" : "What are the limits?"}
        </button>
      </div>

      <div className="banner" style={{ marginBottom: 16 }}>
        <strong>Measurements, not predictions.</strong>{" "}
        {districts.data?.what_this_is ??
          "Real laboratory results from government (CGWB) groundwater sampling, " +
          "judged against IS 10500:2012."}
      </div>

      {districts.isLoading && <Loading label="Assessing every well…" />}
      <ErrorNote error={districts.error} />

      {sw && (
        <>
          {/* Health first, always. "283 wells exceed a limit" at the top would
              be true and would misinform every reader of it. */}
          <h2>Health-significant findings</h2>
          <div className="grid-4" style={{ marginBottom: 12 }}>
            <Tile
              n={sw.health_exceedance_wells}
              label="wells over a health limit"
              sub={`of ${sw.wells} sampled`}
              tone={sw.health_exceedance_wells ? "red" : "green"}
            />
            {sw.health_exceedances.map((h) => (
              <Tile key={h.key} n={h.wells} label={`over the ${h.label} limit`}
                    tone="amber" />
            ))}
            {sw.health_exceedances.length === 0 && (
              <Tile n={0} label="health exceedances" tone="green" />
            )}
          </div>

          <h2>General and aesthetic</h2>
          <div className="grid-4" style={{ marginBottom: 12 }}>
            <Tile n={sw.aesthetic_only_wells} label="wells over a general limit only"
                  sub="hardness, TDS, alkalinity, Ca, Mg" tone="blue" />
            <Tile n={sw.acceptable} label="wells within every limit" tone="green" />
            <Tile n={sw.median_wqi ?? "—"} label="median WQI"
                  sub={`over ${sw.wqi_wells} wells · secondary figure`} tone="blue" />
            <Tile n={sw.above_permissible} label="wells above a permissible limit"
                  tone={sw.above_permissible ? "red" : "green"} />
          </div>

          <div className="banner" style={{ marginBottom: 16 }}>{sw.interpretation}</div>

          <h2>Most common exceedances</h2>
          <TableScroll style={{ marginBottom: 18 }}>
            <table className="grid">
              <thead>
                <tr>
                  <th>Determinand</th>
                  <th style={NUM}>Wells</th>
                  <th style={NUM}>% of sampled</th>
                </tr>
              </thead>
              <tbody>
                {sw.top_exceedances.map((t) => (
                  <tr key={t.key}>
                    <td>{t.label}</td>
                    <td style={NUM}>{t.wells}</td>
                    <td style={NUM}>{t.pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>
        </>
      )}

      {showStandard && (
        <>
          <h2>The standard</h2>
          {standard.isLoading && <Loading />}
          <ErrorNote error={standard.error} />
          {standard.data && (
            <>
              <div className="muted small" style={{ marginBottom: 8 }}>
                {standard.data.standard}. {standard.data.not_tested_rule}
              </div>
              <TableScroll style={{ marginBottom: 18 }}>
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
                          {d.range ? `${d.range[0]}–${d.range[1]}` : fmt(d.acceptable)}
                        </td>
                        <td style={NUM}>
                          {d.permissible === null
                            ? <span className="muted small">{d.relaxation || "—"}</span>
                            : fmt(d.permissible)}
                        </td>
                        <td className="muted small">{d.source}</td>
                        <td className="muted small">{d.note}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScroll>
            </>
          )}
        </>
      )}

      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <h2 style={{ margin: 0 }}>{byBlock ? "By block" : "By district"}</h2>
        <button className={`btn ${byBlock ? "" : "ghost"} small`}
                style={{ marginLeft: 8 }}
                onClick={() => { setByBlock((v) => !v); setDistrictId(null); setOpenWell(null); }}>
          {byBlock ? "Show districts" : "Group by block"}
        </button>
      </div>
      <div className="muted small" style={{ margin: "6px 0" }}>
        Worst first.{byBlock
          ? " Blocks are what advisories and citizen alerts are scoped to."
          : " Choose a district to list its wells."}
      </div>
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
                  <th style={NUM}>Health</th>
                  <th style={NUM}>Above perm.</th>
                  <th style={NUM}>Within limits</th>
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
                    <td style={NUM}>
                      {b.health_exceedance_wells
                        ? <strong style={{ color: "var(--danger)" }}>
                            {b.health_exceedance_wells}
                          </strong>
                        : <span className="muted">0</span>}
                    </td>
                    <td style={NUM}>{b.above_permissible}</td>
                    <td style={NUM}>{b.acceptable}</td>
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
              <th style={NUM}>Health</th>
              <th style={NUM}>Above perm.</th>
              <th style={NUM}>Above acc.</th>
              <th style={NUM}>Within limits</th>
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
                <td style={NUM}>{d.median_wqi ?? "—"}</td>
                <td className="muted small">
                  {d.top_exceedances[0]
                    ? `${d.top_exceedances[0].label} (${d.top_exceedances[0].wells})`
                    : "—"}
                </td>
                <td>
                  <button
                    className="btn ghost small"
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
        <>
          <h2>Wells{wells.data ? ` — ${wells.data.count}` : ""}</h2>
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
                                {fmt(w.summary.driver.value)} {w.summary.driver.unit}
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
                      <td>
                        <button
                          className="btn ghost small"
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
        </>
      )}

      {/* Inline rather than a modal: this project has no dialog primitive, and
          the full determinand table is the reason someone came to this screen —
          it should be linkable, scrollable and printable with everything else. */}
      {openWell && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row wrap" style={{ alignItems: "baseline" }}>
            <h2 style={{ margin: 0 }}>{openWell.well_name}</h2>
            <span className="spacer grow" />
            <button className="btn ghost small" onClick={() => setOpenWell(null)}>
              Close
            </button>
          </div>
          <div className="muted small" style={{ margin: "4px 0 10px" }}>
            {openWell.block ?? "—"}, {openWell.district ?? "—"}
            {openWell.sampled_at &&
              ` · sampled ${new Date(openWell.sampled_at).toLocaleDateString()}`}
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

          <TableScroll>
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
                {openWell.parameters.map((p) => (
                  <tr key={p.key}>
                    <td>
                      {p.label}{" "}
                      {p.health && <span className="chip danger">health</span>}
                      {p.derived && <span className="chip neutral">derived</span>}
                    </td>
                    <td style={NUM}>{fmt(p.value)}</td>
                    <td className="muted small">{p.unit}</td>
                    <td style={NUM}>{limitText(p)}</td>
                    <td style={NUM}>{p.times_limit ?? "—"}</td>
                    <td><StatusChip status={p.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableScroll>

          <div className="muted small" style={{ marginTop: 10 }}>
            “Not tested” means no measurement exists for that determinand at this
            well. It is a gap in monitoring, never a clean result.
          </div>
        </div>
      )}
    </div>
  );
}
