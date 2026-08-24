/**
 * Groundwater levels — trend and seasonal behaviour, 2013-2021.
 *
 * WHY THIS SCREEN EXISTS. `groundwater_level_readings` holds 8,345 CGWB
 * measurements from 415 stations over nine years — the only genuinely temporal
 * data this project has. Before 2026-08-24 it was read once, to bake a single
 * static flow field for the transport engine, and the time axis was averaged
 * away. The proposal names "groundwater level fluctuations" and "seasonal /
 * monsoon variation" among its inputs; both were already on disk.
 *
 * THE SIGN CONVENTION, WHICH THIS SCREEN MUST NOT GET WRONG. The measurement is
 * DEPTH BELOW GROUND. A rising number means a FALLING water table. Every label
 * here says "falling"/"rising" in words rather than showing a bare signed slope,
 * because a reader who infers the sign backwards reads a depleting aquifer as a
 * recovering one.
 *
 * WHAT IT REFUSES TO SAY. 84 of 415 stations have too short a record to test.
 * They are shown as "not enough record", never as "stable" — that distinction
 * is the whole reason the monitoring-gap work exists elsewhere in this product.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api, type GwStation, type GwStationDetail, type GwSummary, type GwTrends,
} from "../api/client";
import { ErrorNote, Loading, TableScroll, Tile } from "../components/bits";

const NUM: React.CSSProperties = {
  textAlign: "right", fontVariantNumeric: "tabular-nums",
};

function TrendChip({ s }: { s: GwStation }) {
  if (!s.trend) return <span className="chip neutral">⚫ Not enough record</span>;
  if (s.trend === "declining")
    return <span className="chip danger">🔻 Water table falling</span>;
  if (s.trend === "recovering")
    return <span className="chip ok">🔺 Water table rising</span>;
  return <span className="chip neutral">▪ No significant change</span>;
}

/**
 * The measured series, drawn as a sparkline with the trend line over it.
 *
 * The points are drawn, not just the fit. A trend line with nothing underneath
 * it cannot be challenged by the person reading it, and these records are short
 * enough that the scatter is the honest part of the picture.
 *
 * Y is INVERTED relative to the stored value: depth increases downward, so a
 * deepening water table draws downward, which is what a reader expects to see.
 */
function Series({ detail }: { detail: GwStationDetail }) {
  const pts = detail.series;
  if (pts.length < 2) return <div className="muted small">Too few readings to plot.</div>;

  const W = 640, H = 170, PAD = 34;
  const ts = pts.map((p) => new Date(p.at).getTime());
  const ds = pts.map((p) => p.depth_m);
  const t0 = Math.min(...ts), t1 = Math.max(...ts);
  const d0 = Math.min(...ds), d1 = Math.max(...ds);
  const span = Math.max(1, t1 - t0);
  const range = Math.max(0.5, d1 - d0);

  const x = (t: number) => PAD + ((t - t0) / span) * (W - PAD - 10);
  // Inverted: larger depth -> lower on screen.
  const y = (d: number) => PAD / 2 + ((d - d0) / range) * (H - PAD - 10);

  const path = pts
    .map((p, i) => `${i ? "L" : "M"}${x(new Date(p.at).getTime()).toFixed(1)},${y(p.depth_m).toFixed(1)}`)
    .join(" ");

  // The Theil-Sen line, anchored at the median point so it sits in the data
  // rather than at an arbitrary intercept.
  let trendPath: string | null = null;
  if (detail.slope_m_per_year !== null) {
    const midT = (t0 + t1) / 2;
    const midD = ds.slice().sort((a, b) => a - b)[Math.floor(ds.length / 2)];
    const yrs = (t: number) => (t - midT) / (365.2425 * 86400_000);
    const at = (t: number) => midD + detail.slope_m_per_year! * yrs(t);
    trendPath = `M${x(t0).toFixed(1)},${y(at(t0)).toFixed(1)} L${x(t1).toFixed(1)},${y(at(t1)).toFixed(1)}`;
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
         aria-label={`Depth to water at ${detail.station}, ${pts.length} readings`}
         style={{ maxWidth: W }}>
      <text x={4} y={PAD / 2} fontSize="10" fill="var(--muted)">{d0.toFixed(1)} m</text>
      <text x={4} y={H - 14} fontSize="10" fill="var(--muted)">{d1.toFixed(1)} m</text>
      <text x={PAD} y={H - 2} fontSize="10" fill="var(--muted)">
        {new Date(t0).getFullYear()}
      </text>
      <text x={W - 34} y={H - 2} fontSize="10" fill="var(--muted)">
        {new Date(t1).getFullYear()}
      </text>
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.2"
            opacity="0.85" />
      {pts.map((p, i) => (
        <circle key={i} cx={x(new Date(p.at).getTime())} cy={y(p.depth_m)} r="1.6"
                fill="var(--accent)" opacity="0.9" />
      ))}
      {trendPath && (
        <path d={trendPath} fill="none" strokeWidth="1.8" strokeDasharray="5 4"
              stroke={detail.trend === "declining" ? "var(--danger)"
                : detail.trend === "recovering" ? "var(--ok)" : "var(--muted)"} />
      )}
    </svg>
  );
}

export default function GroundwaterTrends() {
  const [openId, setOpenId] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("");
  const [showMethod, setShowMethod] = useState(false);
  /** The district roll-up answers a different question from the station list:
   *  "where should a hydrogeologist look", not "which station is worst". */
  const [byDistrict, setByDistrict] = useState(false);

  const trends = useQuery({
    queryKey: ["gw-trends"],
    queryFn: () => api.get<GwTrends>("/groundwater/trends?limit=2000"),
  });

  const districts = useQuery({
    queryKey: ["gw-districts"],
    enabled: byDistrict,
    queryFn: () => api.get<{
      districts: Array<{ district: string } & GwSummary>;
      statewide: GwSummary;
    }>("/groundwater/districts"),
  });

  const detail = useQuery({
    queryKey: ["gw-station", openId],
    queryFn: () => api.get<GwStationDetail>(`/groundwater/stations/${openId}`),
    enabled: !!openId,
  });

  const s = trends.data?.summary;
  const stations = (trends.data?.stations ?? []).filter(
    (st) => !filter || st.trend === filter
      || (filter === "none" && !st.trend));

  return (
    <div className="page">
      <div className="row wrap" style={{ alignItems: "baseline" }}>
        <h1>Groundwater levels</h1>
        <span className="spacer grow" />
        <button className="btn ghost" onClick={() => setShowMethod((v) => !v)}>
          {showMethod ? "Hide method" : "How is this computed?"}
        </button>
      </div>

      <div className="banner" style={{ marginBottom: 16 }}>
        <strong>Depth below ground, so a rising number is a falling water
        table.</strong>{" "}
        CGWB station records, 2013–2021. This describes what the measurements
        did; nothing here is extrapolated forward, and it is unrelated to the
        ISR transport model.
      </div>

      {trends.isLoading && <Loading label="Fitting trends…" />}
      <ErrorNote error={trends.error} />

      {s && (
        <>
          <div className="grid-4" style={{ marginBottom: 12 }}>
            <Tile n={s.declining} label="stations with a falling water table"
                  sub={`of ${s.analysed} testable`}
                  tone={s.declining ? "red" : "green"} />
            <Tile n={s.by_trend.recovering ?? 0} label="rising" tone="green" />
            <Tile n={s.by_trend.stable ?? 0} label="no significant change"
                  tone="blue" />
            <Tile n={s.insufficient_data} label="not enough record to test"
                  sub={`of ${s.stations} stations`} tone="amber" />
          </div>

          <div className="grid-2" style={{ marginBottom: 12 }}>
            <div className="card">
              <div className="muted small">Fastest decline</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                {s.fastest_decline_m_per_year ?? "—"}{" "}
                <span className="muted small">m/year deeper</span>
              </div>
            </div>
            <div className="card">
              <div className="muted small">Median seasonal swing</div>
              <div style={{ fontSize: 22, fontWeight: 700 }}>
                {s.median_seasonal_swing_m ?? "—"}{" "}
                <span className="muted small">m, pre- to post-monsoon</span>
              </div>
            </div>
          </div>

          <div className="banner" style={{ marginBottom: 16 }}>{s.coverage_note}</div>
        </>
      )}

      {showMethod && trends.data && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ marginTop: 0 }}>Method</h2>
          <table className="grid">
            <tbody>
              {Object.entries(trends.data.method).map(([k, v]) => (
                <tr key={k}>
                  <td style={{ width: 150, textTransform: "capitalize" }}>
                    {k.replace(/_/g, " ")}
                  </td>
                  <td className="muted small">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="row wrap" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>{byDistrict ? "By district" : "Stations"}</h2>
        <button className={`btn ${byDistrict ? "" : "ghost"} small`}
                style={{ marginLeft: 8 }}
                onClick={() => setByDistrict((v) => !v)}>
          {byDistrict ? "Show stations" : "Group by district"}
        </button>
        <span className="spacer grow" />
        {[["", "All"], ["declining", "Falling"], ["recovering", "Rising"],
          ["stable", "Stable"], ["none", "Not enough record"]].map(([v, label]) => (
          <button key={v}
                  className={`btn ${filter === v ? "" : "ghost"} small`}
                  onClick={() => setFilter(v)}>
            {label}
          </button>
        ))}
      </div>

      {byDistrict ? (
        <>
          {districts.isLoading && <Loading />}
          <ErrorNote error={districts.error} />
          <TableScroll>
            <table className="grid">
              <thead>
                <tr>
                  <th>District</th>
                  <th style={NUM}>Stations</th>
                  <th style={NUM}>Testable</th>
                  <th style={NUM}>Falling</th>
                  <th style={NUM}>Rising</th>
                  <th style={NUM}>Stable</th>
                  <th style={NUM}>Not enough record</th>
                  <th style={NUM}>Fastest decline</th>
                </tr>
              </thead>
              <tbody>
                {(districts.data?.districts ?? []).map((d) => (
                  <tr key={d.district}>
                    <td>{d.district}</td>
                    <td style={NUM}>{d.stations}</td>
                    <td style={NUM}>{d.analysed}</td>
                    <td style={NUM}>
                      {d.declining
                        ? <strong style={{ color: "var(--danger)" }}>{d.declining}</strong>
                        : <span className="muted">0</span>}
                    </td>
                    <td style={NUM}>{d.by_trend.recovering ?? 0}</td>
                    <td style={NUM}>{d.by_trend.stable ?? 0}</td>
                    <td style={NUM}>{d.insufficient_data}</td>
                    <td style={NUM}>
                      {d.fastest_decline_m_per_year ?? "—"}
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
              <th>Station</th><th>District</th><th>Trend</th>
              <th style={NUM}>m/year</th>
              <th style={NUM}>p</th>
              <th style={NUM}>Readings</th>
              <th style={NUM}>Span (yr)</th>
              <th style={NUM}>Seasonal swing</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {stations.map((st) => (
              <tr key={st.station_id}>
                <td>{st.station}</td>
                <td className="muted small">{st.district ?? "—"}</td>
                <td><TrendChip s={st} /></td>
                <td style={NUM}>
                  {st.slope_m_per_year === null
                    ? "—"
                    : (st.slope_m_per_year > 0 ? "+" : "") + st.slope_m_per_year.toFixed(3)}
                </td>
                <td style={NUM}>{st.p_value ?? "—"}</td>
                <td style={NUM}>{st.readings}</td>
                <td style={NUM}>{st.span_years ?? "—"}</td>
                <td style={NUM}>{st.seasonal?.swing_m ?? "—"}</td>
                <td>
                  <button className="btn ghost small"
                          onClick={() => setOpenId(openId === st.station_id
                            ? null : st.station_id)}>
                    {openId === st.station_id ? "Hide" : "Series"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
      )}

      {openId && !byDistrict && (
        <div className="card" style={{ marginTop: 14 }}>
          {detail.isLoading && <Loading />}
          <ErrorNote error={detail.error} />
          {detail.data && (
            <>
              <div className="row wrap" style={{ alignItems: "baseline" }}>
                <h2 style={{ margin: 0 }}>{detail.data.station}</h2>
                <span className="spacer grow" />
                <button className="btn ghost small" onClick={() => setOpenId(null)}>
                  Close
                </button>
              </div>
              <div className="muted small" style={{ margin: "4px 0 10px" }}>
                {detail.data.village ? `${detail.data.village} · ` : ""}
                {detail.data.block ?? "—"}, {detail.data.district ?? "—"} ·{" "}
                {detail.data.readings} readings
              </div>

              {detail.data.insufficient_data
                ? <div className="banner warn">{detail.data.insufficient_data}</div>
                : (
                  <div className="banner">
                    <strong>{detail.data.direction}</strong> at{" "}
                    {Math.abs(detail.data.slope_m_per_year ?? 0).toFixed(3)} m/year
                    {" "}(p = {detail.data.p_value}).
                  </div>
                )}

              <Series detail={detail.data} />

              {detail.data.seasonal && (
                <div className="muted small" style={{ marginTop: 8 }}>
                  Pre-monsoon mean depth {detail.data.seasonal.pre_monsoon_depth_m} m
                  ({detail.data.seasonal.pre_n} readings) · post-monsoon{" "}
                  {detail.data.seasonal.post_monsoon_depth_m} m
                  ({detail.data.seasonal.post_n}) · swing{" "}
                  {detail.data.seasonal.swing_m} m. {detail.data.seasonal.note}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
