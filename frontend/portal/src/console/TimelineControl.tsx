/**
 * The plume over time — frames the engine actually evaluated (R17).
 *
 * A stored run is evaluated at one horizon. When it completes, the backend
 * also evaluates the same inputs at a fixed set of horizons (0, 1, 2, 3, 5, 8,
 * 10, 15, 20 … up to the run's own, plus the two phase boundaries) and stores
 * each frame: the screening-limit contour, the source zone, the footprint,
 * the migration, the concentration at the monitoring ring, the phase and the
 * calendar date. This control scrubs and plays through those frames.
 *
 * THE RULE THIS COMPONENT KEEPS. Nothing shown here is interpolated. Each
 * frame is a real engine result at that year; the scrubber snaps to frames;
 * the strip chart draws the evaluated points and joins them with a line only
 * as a reading aid, with the first evaluated frame over the limit marked —
 * the true crossing lies between it and the frame before, and the caption
 * says so. The ML band is NOT drawn at intermediate frames: the band stored
 * on a frame is the surrogate's own evaluation there, but the console's band
 * ellipses belong to the run's horizon, and drawing a band at year 3 that
 * was calibrated for year 20 would read as something the model did not say.
 *
 * A run stored before frames existed reports "not recorded" and this control
 * says exactly that rather than showing an empty animation.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type RecordedTimeline, type RunTimeline, type TimelineFrame } from "../api/client";
import { SPECIES_NAME, SPECIES_UNIT } from "../map/plume";

const PHASE_LABEL: Record<string, string> = {
  operation: "Operation (injection + capture)",
  restoration: "Restoration sweep (front held)",
  drift: "Post-closure drift",
  post_closure: "Post-closure drift",
};

function fmt(v: number | null | undefined, d = 1) {
  if (v === null || v === undefined || !isFinite(Number(v))) return "–";
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: d });
}

/** Loads the frames for a stored run (staff) or a published advisory (public). */
export function useRunTimeline(opts: { runId?: string | null; advisoryId?: string | null }) {
  const key = opts.runId ? `/simulations/runs/${opts.runId}/timeline`
    : opts.advisoryId ? `/public/risk/advisories/${opts.advisoryId}/timeline` : null;
  return useQuery({
    queryKey: ["run-timeline", key],
    enabled: !!key,
    queryFn: () => api.get<RunTimeline>(key!),
    staleTime: 5 * 60 * 1000,
  });
}

/** Ring concentration against time, with the threshold and the first-exceedance frame. */
export function TimelineStrip({ tl, current, onPick }: {
  tl: RecordedTimeline; current?: number; onPick?: (i: number) => void;
}) {
  const frames = tl.frames.filter((f) => !f.error);
  const W = 640, H = 170, PL = 46, PR = 12, PT = 14, PB = 30;
  const xs = frames.map((f) => f.year);
  const ys = frames.map((f) => Number(f.compliance_conc ?? 0));
  const xMax = Math.max(tl.horizon_years, ...xs, 1);
  const thr = tl.threshold ?? null;
  const yMax = Math.max(...ys, thr ?? 0, 1e-9) * 1.15;
  const px = (x: number) => PL + (x / xMax) * (W - PL - PR);
  const py = (y: number) => PT + (1 - y / yMax) * (H - PT - PB);
  const unit = SPECIES_UNIT[tl.species] ?? "";
  const op = tl.operation_years, rest = tl.restoration_years;
  const bands = [
    { from: 0, to: Math.min(op, xMax), label: "operation", fill: "rgba(43,179,255,.10)" },
    { from: Math.min(op, xMax), to: Math.min(op + rest, xMax), label: "restoration", fill: "rgba(245,165,36,.12)" },
    { from: Math.min(op + rest, xMax), to: xMax, label: "post-closure", fill: "rgba(122,134,153,.10)" },
  ].filter((b) => b.to > b.from);
  const path = frames.map((f, i) => `${i ? "L" : "M"}${px(f.year)},${py(Number(f.compliance_conc ?? 0))}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" style={{ display: "block", overflow: "visible" }}
         aria-label={`Concentration at the monitoring ring over time for ${SPECIES_NAME[tl.species] ?? tl.species}`}>
      {bands.map((b) => (
        <g key={b.label}>
          <rect x={px(b.from)} y={PT} width={Math.max(px(b.to) - px(b.from), 0)} height={H - PT - PB} fill={b.fill} />
          <text x={px(b.from) + 4} y={PT + 11} fontSize="9.5" fill="var(--muted)">{b.label}</text>
        </g>
      ))}
      <line x1={PL} y1={py(0)} x2={W - PR} y2={py(0)} stroke="var(--border)" />
      <line x1={PL} y1={PT} x2={PL} y2={py(0)} stroke="var(--border)" />
      {thr !== null && (
        <g>
          <line x1={PL} y1={py(thr)} x2={W - PR} y2={py(thr)} stroke="var(--danger)" strokeDasharray="5 4" strokeWidth="1.2" />
          <text x={W - PR} y={py(thr) - 3} fontSize="9.5" textAnchor="end" fill="var(--danger)">screening limit {fmt(thr, 2)} {unit}</text>
        </g>
      )}
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.6" strokeOpacity="0.7" />
      {frames.map((f, i) => {
        const over = thr !== null && Number(f.compliance_conc ?? 0) > thr;
        const first = tl.first_exceedance_year !== null && f.year === tl.first_exceedance_year;
        const isCur = current !== undefined && frames[current]?.year === f.year;
        return (
          <g key={f.year} style={{ cursor: onPick ? "pointer" : "default" }} onClick={() => onPick?.(i)}>
            <circle cx={px(f.year)} cy={py(Number(f.compliance_conc ?? 0))} r={isCur ? 5.5 : 3.6}
                    fill={over ? "var(--danger)" : "var(--accent)"} stroke={first ? "var(--danger)" : "var(--bg)"} strokeWidth={first ? 2.4 : 1.2}>
              <title>{`${f.year} yr · ${fmt(f.compliance_conc, 3)} ${unit} at the ring · ${f.phase}`}</title>
            </circle>
            {first && <text x={px(f.year)} y={py(Number(f.compliance_conc ?? 0)) - 9} fontSize="9.5" textAnchor="middle" fill="var(--danger)">first over limit</text>}
          </g>
        );
      })}
      {[0, xMax / 2, xMax].map((x) => (
        <text key={x} x={px(x)} y={H - 10} fontSize="9.5" textAnchor="middle" fill="var(--muted)">{fmt(x, 0)} yr</text>
      ))}
      <text x={4} y={PT + 4} fontSize="9.5" fill="var(--muted)">{unit}</text>
      <text x={4} y={py(0)} fontSize="9.5" fill="var(--muted)">0</text>
    </svg>
  );
}

export default function TimelineControl({ tl, onFrame, compact = false }: {
  tl: RunTimeline | null | undefined;
  /** The frame currently shown; `null` when the control is released back to
   *  the run's own horizon. */
  onFrame?: (f: TimelineFrame | null) => void;
  compact?: boolean;
}) {
  const frames = useMemo(() => (tl?.recorded ? tl.frames.filter((f) => !f.error) : []), [tl]);
  const [idx, setIdx] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<number | null>(null);

  // playback: advance one frame every 900 ms, stop at the last frame
  useEffect(() => {
    if (!playing) { if (timer.current) window.clearInterval(timer.current); timer.current = null; return; }
    timer.current = window.setInterval(() => {
      setIdx((i) => {
        const n = i === null ? 0 : i + 1;
        if (n >= frames.length - 1) { setPlaying(false); return frames.length - 1; }
        return n;
      });
    }, 900);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [playing, frames.length]);

  useEffect(() => {
    if (!onFrame) return;
    if (idx === null || idx >= frames.length - 1) onFrame(null);   // the run's own horizon
    else onFrame(frames[idx]);
  }, [idx, frames, onFrame]);

  if (!tl) return null;
  if (!tl.recorded) {
    return (
      <div className="muted small" style={{ marginTop: 8 }}>
        <b>Timeline not recorded.</b> {tl.reason}
      </div>
    );
  }
  if (frames.length < 2) return null;

  const cur = idx === null ? frames.length - 1 : idx;
  const f = frames[cur];
  const unit = SPECIES_UNIT[tl.species] ?? "";
  const over = tl.threshold !== null && Number(f.compliance_conc ?? 0) > (tl.threshold ?? Infinity);

  return (
    <div className="timeline-control" style={{ marginTop: 10 }}>
      <div className="row wrap" style={{ alignItems: "center", gap: 8 }}>
        <button className="btn ghost" onClick={() => { if (cur >= frames.length - 1) setIdx(0); setPlaying((p) => !p); }}
                aria-label={playing ? "Pause" : "Play"}>
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <input type="range" min={0} max={frames.length - 1} step={1} value={cur}
               style={{ flex: "1 1 160px" }}
               onChange={(e) => { setPlaying(false); setIdx(Number(e.target.value)); }}
               aria-label="Scrub through evaluated horizons" />
        <b style={{ minWidth: 64 }}>{fmt(f.year, 1)} yr</b>
        {f.calendar_date && <span className="muted small">{f.calendar_date}</span>}
        <span className="chip neutral">{PHASE_LABEL[f.phase] ?? f.phase}</span>
        {f.extrapolating && <span className="chip warn" title={(f.extrapolation ?? []).join(", ")}>extrapolating</span>}
      </div>
      <dl className="kv" style={{ marginTop: 8, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 6 }}>
        <div><dt className="muted small">Footprint</dt><dd style={{ margin: 0 }}><b>{fmt(f.area_ha, 2)}</b> ha</dd></div>
        <div><dt className="muted small">Migration</dt><dd style={{ margin: 0 }}><b>{fmt(f.migration_m, 1)}</b> m</dd></div>
        <div><dt className="muted small">At the ring ({fmt(tl.monitor_ring_m, 0)} m beyond the wellfield)</dt>
          <dd style={{ margin: 0, color: over ? "var(--danger)" : undefined }}>
            <b>{fmt(f.compliance_conc, 3)}</b> {unit}
            {tl.threshold !== null && <span className="muted small"> / limit {fmt(tl.threshold, 2)}</span>}
          </dd></div>
        <div><dt className="muted small">Source zone</dt><dd style={{ margin: 0 }}><b>{fmt(f.source_conc, 0)}</b> {unit}</dd></div>
      </dl>
      {!compact && <TimelineStrip tl={tl} current={cur} onPick={(i) => { setPlaying(false); setIdx(i); }} />}
      <div className="muted small" style={{ marginTop: 6 }}>
        {tl.first_exceedance_year !== null
          ? <>First evaluated frame with the ring above the screening limit: <b>{tl.first_exceedance_year} yr</b>
              {" "}— the true crossing lies between that frame and the one before it.</>
          : <>No evaluated frame puts the ring above the screening limit within {fmt(tl.horizon_years, 0)} years.</>}
        {tl.first_excursion_year !== null && <> Indicator excursion first declared at <b>{tl.first_excursion_year} yr</b>.</>}
        {" "}{frames.length} frames, each a separate engine evaluation; nothing between them is interpolated.
      </div>
    </div>
  );
}
