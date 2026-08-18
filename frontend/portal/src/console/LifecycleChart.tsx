/**
 * Concentration and extent across the operation's whole life.
 *
 * WHAT THIS PLOTS, AND WHY IT IS NOT ONE LINE. The intuitive expectation is a
 * single curve that rises while mining, falls during restoration, then decays.
 * The model says something more specific, measured before this was drawn:
 *
 *   · source strength is FLAT during injection — that is what injection is,
 *     the leach solution is held at strength
 *   · it falls only under a restoration sweep
 *   · afterwards it is HELD at the rebound floor (residual uranium can
 *     re-oxidise rather than keep cleaning up), while MIGRATION keeps growing,
 *     because hydraulic containment stops when the operation does
 *
 * A single "concentration" line would therefore be flat for a decade and read
 * as a broken chart. Three series are plotted against shared phase bands so the
 * story is visible: area grows, then source drops, then the front travels.
 *
 * The phase bands come from the engine's own boundaries, so a label can never
 * disagree with the physics it is describing.
 */
import { useMemo, useState } from "react";
import type { Lifecycle, LifecycleSeries } from "../api/client";
import { SPECIES_NAME } from "../map/plume";
import { fmt } from "./mapLayers";

type MetricKey = "source_conc" | "area_ha" | "migration_m" | "compliance_conc"
               | "shallow_impact_probability";

const METRICS: Array<{ k: MetricKey; label: string; unit: (s: LifecycleSeries) => string;
                       why: string }> = [
  { k: "source_conc", label: "Source strength", unit: (s) => s.unit,
    why: "Held constant while injecting; falls only under a restoration sweep; "
       + "then held at the stable endpoint rather than decaying away." },
  { k: "area_ha", label: "Affected area", unit: () => "ha",
    why: "This is what grows during injection — not the concentration." },
  { k: "migration_m", label: "Migration", unit: () => "m",
    why: "Grows after closure, when hydraulic containment stops holding the front." },
  { k: "compliance_conc", label: "At the ring", unit: (s) => s.unit,
    why: "Concentration at the perimeter monitoring ring, where an excursion "
       + "would actually be detected." },
  { k: "shallow_impact_probability", label: "Shallow-aquifer risk", unit: () => "",
    why: "Chance the contamination reaches the shallow aquifer people pump from." },
];

const PHASE_FILL: Record<string, string> = {
  operation: "rgba(255,90,90,.10)",
  restoration: "rgba(63,182,255,.12)",
  post_closure: "rgba(139,151,167,.09)",
};

const W = 460, H = 200, PAD_L = 52, PAD_B = 34, PAD_T = 18, PAD_R = 12;

export default function LifecycleChart({ data }: { data: Lifecycle }) {
  const [metric, setMetric] = useState<MetricKey>("source_conc");
  const [speciesIdx, setSpeciesIdx] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  const series = data.series[speciesIdx];
  const meta = METRICS.find((m) => m.k === metric)!;

  const usable = useMemo(
    () => (series?.points ?? []).filter((p) => p.error === null && p[metric] != null),
    [series, metric]);

  const maxX = data.time_years || 1;
  // Zero-based always: a truncated axis on a contamination chart exaggerates
  // whatever decline it shows.
  const maxY = Math.max(...usable.map((p) => Number(p[metric])), 1e-9);

  const px = (v: number) => PAD_L + (v / maxX) * (W - PAD_L - PAD_R);
  const py = (v: number) => H - PAD_B - (v / maxY) * (H - PAD_T - PAD_B);

  const path = usable
    .map((p, i) => `${i ? "L" : "M"}${px(p.year).toFixed(1)},${py(Number(p[metric])).toFixed(1)}`)
    .join(" ");

  const hovered = hover !== null ? usable.find((p) => p.year === hover) ?? null : null;
  const failed = (series?.points ?? []).filter((p) => p.error !== null);

  if (!series) return null;

  return (
    <>
      <div className="seg seg-sm" style={{ marginBottom: 6 }}>
        {data.series.map((s, i) => (
          <button key={s.species} className={i === speciesIdx ? "active" : ""}
                  onClick={() => setSpeciesIdx(i)}>
            {SPECIES_NAME[s.species] ?? s.species}
          </button>
        ))}
      </div>
      <div className="seg seg-sm" style={{ marginBottom: 8 }}>
        {METRICS.map((m) => (
          <button key={m.k} className={metric === m.k ? "active" : ""}
                  onClick={() => setMetric(m.k)}>{m.label}</button>
        ))}
      </div>

      {series.suppressed && (
        <div className="banner warn" style={{ marginBottom: 8 }}>
          <strong>No source term for this contaminant here.</strong> {series.suppressed}
        </div>
      )}

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label={`${meta.label} for ${SPECIES_NAME[series.species] ?? series.species} across the operation lifecycle`}
           style={{ display: "block", overflow: "visible" }}>
        {/* phase bands, from the engine's own boundaries */}
        {data.phases.filter((ph) => ph.to > ph.from).map((ph) => (
          <g key={ph.phase}>
            <rect x={px(ph.from)} y={PAD_T} width={Math.max(px(ph.to) - px(ph.from), 0)}
                  height={H - PAD_T - PAD_B} fill={PHASE_FILL[ph.phase] ?? "none"} />
            <text x={(px(ph.from) + px(ph.to)) / 2} y={PAD_T - 6} textAnchor="middle"
                  fontSize="8.5" fill="var(--muted)">
              {ph.phase === "operation" ? "Operating"
                : ph.phase === "restoration" ? "Restoration" : "Post-closure"}
            </text>
            <line x1={px(ph.to)} y1={PAD_T} x2={px(ph.to)} y2={H - PAD_B}
                  stroke="var(--line)" strokeWidth="1" strokeDasharray="3 3" />
          </g>
        ))}

        {/* axes */}
        <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B}
              stroke="var(--line)" />
        <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="var(--line)" />

        {[0, maxY / 2, maxY].map((v, i) => (
          <g key={i}>
            <line x1={PAD_L - 3} y1={py(v)} x2={PAD_L} y2={py(v)} stroke="var(--line)" />
            <text x={PAD_L - 6} y={py(v) + 3} textAnchor="end" fontSize="8.5"
                  fill="var(--muted)">
              {metric === "shallow_impact_probability"
                ? `${(v * 100).toFixed(0)}%`
                : fmt(v, v < 10 ? 2 : 0)}
            </text>
          </g>
        ))}
        <text x={PAD_L - 6} y={PAD_T - 6} textAnchor="end" fontSize="8"
              fill="var(--muted)">{meta.unit(series)}</text>

        {[0, maxX / 4, maxX / 2, (maxX * 3) / 4, maxX].map((v, i) => (
          <text key={i} x={px(v)} y={H - PAD_B + 12} textAnchor="middle" fontSize="8.5"
                fill="var(--muted)">{fmt(v, 0)}</text>
        ))}
        <text x={(W + PAD_L) / 2} y={H - 4} textAnchor="middle" fontSize="9"
              fill="var(--muted)">Years from start</text>

        {/* the screening limit, where one applies */}
        {series.threshold != null && metric !== "shallow_impact_probability"
          && metric !== "area_ha" && metric !== "migration_m"
          && series.threshold <= maxY && (
          <g>
            <line x1={PAD_L} y1={py(series.threshold)} x2={W - PAD_R}
                  y2={py(series.threshold)} stroke="var(--danger)" strokeWidth="1.2"
                  strokeDasharray="5 3" />
            <text x={W - PAD_R} y={py(series.threshold) - 3} textAnchor="end"
                  fontSize="8" fill="var(--danger)">
              safe limit {fmt(series.threshold, 0)}
            </text>
          </g>
        )}

        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />

        {usable.map((p) => (
          <g key={p.year}>
            <circle cx={px(p.year)} cy={py(Number(p[metric]))}
                    r={hover === p.year ? 4.5 : 2.8}
                    fill={p.extrapolating ? "var(--bg)" : "var(--accent)"}
                    stroke={p.excursion_declared ? "var(--danger)" : "var(--accent)"}
                    strokeWidth={p.excursion_declared ? 2.2 : 1.3} />
            <circle cx={px(p.year)} cy={py(Number(p[metric]))} r="11" fill="transparent"
                    onMouseEnter={() => setHover(p.year)}
                    onMouseLeave={() => setHover(null)} />
          </g>
        ))}
      </svg>

      {hovered && (
        <div className="readonly-val" style={{ marginTop: 4 }}>
          <span className="muted small">
            Year {fmt(hovered.year, 1)} · {hovered.phase.replace(/_/g, "-")}
          </span>
          <span>
            <span className="rv-v">
              {metric === "shallow_impact_probability"
                ? `${((hovered[metric] as number) * 100).toFixed(0)}%`
                : fmt(hovered[metric], 2)}
            </span>
            <span className="rv-u"> {meta.unit(series)}</span>
          </span>
        </div>
      )}

      <div className="muted small" style={{ marginTop: 8, lineHeight: "var(--lh-base)" }}>
        {meta.why}
      </div>

      {failed.length > 0 && (
        <div className="banner warn" style={{ marginTop: 8 }}>
          {failed.length} point(s) failed to solve and are left as gaps rather than
          interpolated over.
        </div>
      )}
    </>
  );
}

/** The three-phase narrative, spelled out. Used under the chart and in the
 *  published report, so both explain the shape the same way. */
export function LifecycleNarrative({ data }: { data: Lifecycle }) {
  return (
    <div className="card" style={{ background: "var(--card2)" }}>
      <div className="card-title">How to read this</div>
      {data.phases.filter((p) => p.to > p.from).map((p) => (
        <div key={p.phase} style={{ marginBottom: 8 }}>
          <div className="row wrap">
            <span className={`chip ${p.phase === "operation" ? "danger"
              : p.phase === "restoration" ? "info" : "neutral"}`}>
              {p.label}
            </span>
            <span className="muted small">
              year {fmt(p.from, 0)} – {fmt(p.to, 0)}
            </span>
          </div>
          <div className="muted small" style={{ marginTop: 4, lineHeight: "var(--lh-base)" }}>
            {p.note}
          </div>
        </div>
      ))}
      <div className="muted small" style={{ marginTop: 6 }}>{data.reading_note}</div>
    </div>
  );
}
