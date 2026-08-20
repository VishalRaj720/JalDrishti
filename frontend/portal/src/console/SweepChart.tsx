/**
 * The sweep curve — "how many years of restoration is enough?" as a shape.
 *
 * A single slider answers that question with one number and nothing to compare
 * it against, so the honest answer is a curve and the year it crosses the
 * screening limit. The engine solves in ~0.26 s warm (measured, not assumed),
 * which is what makes a 6–12 point sweep affordable inside one request.
 *
 * Inline SVG rather than a charting library: this is one series with a marked
 * crossing, and adding Recharts for it would be ~50 kB to draw eleven line
 * segments. The axes are drawn honestly — y starts at zero, because a truncated
 * axis on a contamination chart exaggerates a decline, which is precisely the
 * over-claiming §4.5 exists to stop.
 */
import { useMemo, useState } from "react";
import { fmt } from "./mapLayers";

export interface SweepPoint {
  value: number;
  area_ha: number | null;
  migration_m: number | null;
  compliance_conc: number | null;
  excursion_declared: boolean | null;
  source_zone_above_threshold: boolean | null;
  residual_fraction: number | null;
  extrapolating: boolean;
  error: string | null;
}

export interface Sweep {
  persisted: false;
  persistence_note: string;
  axis: "restoration" | "evaluation";
  species: string;
  unit: string;
  held: Record<string, number>;
  points: SweepPoint[];
  crossing_value: number | null;
  crossing_note: string;
}

type MetricKey = "area_ha" | "migration_m" | "compliance_conc";

const METRICS: Array<{ k: MetricKey; label: string; unitOf: (s: Sweep) => string }> = [
  { k: "area_ha", label: "Footprint", unitOf: () => "ha" },
  { k: "migration_m", label: "Migration", unitOf: () => "m" },
  { k: "compliance_conc", label: "At ring", unitOf: (s) => s.unit },
];

const W = 320, H = 150, PAD_L = 40, PAD_B = 26, PAD_T = 12, PAD_R = 10;

export default function SweepChart({
  sweep, onPick, picked,
}: { sweep: Sweep; onPick?: (value: number) => void; picked?: number }) {
  const [metric, setMetric] = useState<MetricKey>("area_ha");
  const [hover, setHover] = useState<number | null>(null);

  const usable = useMemo(
    () => sweep.points.filter((p) => p.error === null && p[metric] != null),
    [sweep.points, metric]);

  const failed = sweep.points.filter((p) => p.error !== null);

  const { xs, maxY, maxX } = useMemo(() => {
    const xv = usable.map((p) => p.value);
    const yv = usable.map((p) => Number(p[metric]));
    return {
      xs: xv,
      maxX: Math.max(...xv, 1),
      // Zero-based, always. A contamination curve on a truncated axis reads as
      // a steeper decline than the numbers support.
      maxY: Math.max(...yv, 1e-9),
    };
  }, [usable, metric]);

  if (usable.length < 2) {
    return (
      <div className="banner warn">
        Not enough points solved to draw a curve.
        {failed.length > 0 && ` ${failed.length} of ${sweep.points.length} failed.`}
      </div>
    );
  }

  const px = (v: number) => PAD_L + (v / maxX) * (W - PAD_L - PAD_R);
  const py = (v: number) => H - PAD_B - (v / maxY) * (H - PAD_T - PAD_B);

  const path = usable
    .map((p, i) => `${i ? "L" : "M"}${px(p.value).toFixed(1)},${py(Number(p[metric])).toFixed(1)}`)
    .join(" ");

  const axisLabel = sweep.axis === "restoration"
    ? "Restoration sweep (yr)" : "Evaluation horizon (yr)";
  const unit = METRICS.find((m) => m.k === metric)!.unitOf(sweep);
  const active = hover ?? picked ?? null;
  const activePoint = active !== null
    ? usable.find((p) => p.value === active) ?? null : null;

  return (
    <>
      <div className="seg seg-sm" style={{ marginBottom: 8 }}>
        {METRICS.map((m) => (
          <button key={m.k} className={metric === m.k ? "active" : ""}
                  onClick={() => setMetric(m.k)}>{m.label}</button>
        ))}
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label={`${METRICS.find((m) => m.k === metric)!.label} against ${axisLabel}`}
           style={{ display: "block", overflow: "visible" }}>
        {/* axes */}
        <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B}
              stroke="var(--line)" strokeWidth="1" />
        <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B}
              stroke="var(--line)" strokeWidth="1" />

        {/* y ticks — zero and max only; more would crowd a 320px box */}
        {[0, maxY].map((v, i) => (
          <g key={i}>
            <line x1={PAD_L - 3} y1={py(v)} x2={PAD_L} y2={py(v)} stroke="var(--line)" />
            <text x={PAD_L - 6} y={py(v) + 3} textAnchor="end"
                  fill="var(--muted)" fontSize="9">{fmt(v, v < 10 ? 2 : 0)}</text>
          </g>
        ))}
        <text x={PAD_L - 6} y={PAD_T - 3} textAnchor="end" fill="var(--muted)" fontSize="8">
          {unit}
        </text>

        {/* x ticks at each sampled value */}
        {xs.map((v) => (
          <g key={v}>
            <line x1={px(v)} y1={H - PAD_B} x2={px(v)} y2={H - PAD_B + 3} stroke="var(--line)" />
            <text x={px(v)} y={H - PAD_B + 13} textAnchor="middle"
                  fill="var(--muted)" fontSize="9">{fmt(v, 0)}</text>
          </g>
        ))}
        <text x={(W + PAD_L) / 2} y={H - 2} textAnchor="middle"
              fill="var(--muted)" fontSize="9">{axisLabel}</text>

        {/* the crossing — where the curve reaches the screening limit */}
        {sweep.crossing_value !== null && (
          <g>
            <line x1={px(sweep.crossing_value)} y1={PAD_T}
                  x2={px(sweep.crossing_value)} y2={H - PAD_B}
                  stroke="var(--ok)" strokeWidth="1.5" strokeDasharray="4 3" />
            <text x={px(sweep.crossing_value)} y={PAD_T - 2} textAnchor="middle"
                  fill="var(--ok)" fontSize="9" fontWeight="700">
              {fmt(sweep.crossing_value, 0)} yr
            </text>
          </g>
        )}

        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />

        {/* points — hollow where the model is extrapolating, so the reader can
            see which part of the curve carries no conformal guarantee */}
        {usable.map((p) => {
          const isActive = active === p.value;
          return (
            <g key={p.value}>
              <circle cx={px(p.value)} cy={py(Number(p[metric]))}
                      r={isActive ? 5 : 3.2}
                      fill={p.extrapolating ? "var(--bg)" : "var(--accent)"}
                      stroke={p.excursion_declared ? "var(--danger)" : "var(--accent)"}
                      strokeWidth={p.excursion_declared ? 2.4 : 1.4} />
              {/* a generous invisible target: a 3px dot is not hoverable */}
              <circle cx={px(p.value)} cy={py(Number(p[metric]))} r="12"
                      fill="transparent" style={{ cursor: onPick ? "pointer" : "default" }}
                      onMouseEnter={() => setHover(p.value)}
                      onMouseLeave={() => setHover(null)}
                      onClick={() => onPick?.(p.value)} />
            </g>
          );
        })}
      </svg>

      {activePoint && (
        <div className="readonly-val" style={{ marginTop: 6 }}>
          <span className="muted small">
            {sweep.axis === "restoration" ? "Sweep" : "Horizon"} {fmt(activePoint.value, 0)} yr
          </span>
          <span>
            <span className="rv-v">{fmt(activePoint[metric], 2)}</span>
            <span className="rv-u"> {unit}</span>
            {activePoint.excursion_declared && (
              <span className="chip danger" style={{ marginLeft: 6 }}>excursion</span>
            )}
          </span>
        </div>
      )}

      <div className="muted small" style={{ marginTop: 8, lineHeight: "var(--lh-base)" }}>
        <b>Hollow points</b> are outside the model's trained range — the analytical
        engine still serves there, but the ML band's conformal guarantee is void.
        <b> Red-ringed points</b> declare a NUREG-1569-inspired excursion.
      </div>

      <div className={`banner ${sweep.crossing_value !== null ? "ok" : "warn"}`}
           style={{ marginTop: 8 }}>
        {sweep.crossing_value !== null
          ? <><strong>{fmt(sweep.crossing_value, 0)} yr.</strong> {sweep.crossing_note}</>
          : sweep.crossing_note}
      </div>

      {failed.length > 0 && (
        <div className="banner warn" style={{ marginTop: 8 }}>
          {failed.length} of {sweep.points.length} points failed to solve and are
          missing from the curve, rather than being interpolated over:{" "}
          <span className="mono">{failed[0].error}</span>
        </div>
      )}

      <div className="muted small" style={{ marginTop: 8 }}>{sweep.persistence_note}</div>
    </>
  );
}
