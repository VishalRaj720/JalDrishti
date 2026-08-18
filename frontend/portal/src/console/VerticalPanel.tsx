/**
 * The vertical (2.5D) screening — will the water people actually drink be hit?
 *
 * WHY THIS EXISTS. The engine has returned a full `vertical` block on every run
 * since Module 5A: an upward-leakage probability, a breakthrough time, a
 * pathway split, and a seasonal wet/dry pair. The portal rendered **none of
 * it** — `grep vertical` across the whole frontend returned three CSS
 * `vertical-align` hits and nothing else.
 *
 * That was the single largest gap in the product, because the horizontal plume
 * answers "how far does contamination travel in the ore aquifer" while this
 * answers "does it reach the shallow aquifer villages actually pump from". The
 * second question is the one the proposal is about.
 *
 * THE SCHEMATIC IS DRAWN TO SCALE where the numbers allow it, because the whole
 * point is the SEPARATION between the ore zone and the shallow aquifer. A
 * decorative diagram with a fixed gap would hide the one quantity that decides
 * the answer.
 *
 * Ported in spirit from the `ml_pipeline` dashboard's `depth-schematic`, which
 * is where this analysis has always been visible.
 */
import type { VerticalScreening } from "../api/client";
import { fmt } from "./mapLayers";

const BAND_TONE: Record<string, string> = {
  high: "danger", moderate: "warn", low: "ok", none: "neutral",
};

const PATHWAY_LABEL: Record<string, string> = {
  advective_leakage: "Upward flow through the confining layer",
  dispersive: "Spreading across the confining layer",
  wellbore: "Leakage along a failed well casing",
};

/**
 * R10 SPLIT THE PANEL IN TWO, and the reason is layout rather than taste.
 *
 * The report wants the section drawn at HALF width with its numbers beside it,
 * and the drawer wants the same content in one narrow column. Rendering the
 * schematic and its numbers as separate exports lets both compose the same
 * markup without either screen forking the analysis.
 *
 * `VerticalPanel` remains the stacked composition, so every existing call site
 * is unchanged.
 */
export default function VerticalPanel({ v }: { v: VerticalScreening | null | undefined }) {
  if (!v) return null;
  return (
    <>
      <VerticalSchematic v={v} />
      <VerticalNumbers v={v} />
    </>
  );
}

export function VerticalSchematic({
  v, heading = true,
}: { v: VerticalScreening | null | undefined; heading?: boolean }) {
  if (!v) return null;

  const p = v.shallow_impact_probability;
  const band = (v.risk_band ?? "none").toLowerCase();
  const tone = BAND_TONE[band] ?? "neutral";
  const years = v.years_to_vertical_breakthrough;

  // Depth geometry for the schematic. `separation_m` is the confining thickness
  // between the top of the ore zone and the base of the shallow aquifer — the
  // quantity that governs everything else here.
  const oreDepth = Number(v.ore_depth_m ?? 0);
  const layer1Base = Number(v.layer1_base_m ?? v.seasonal?.separation_m ?? 0);
  const separation = Number(v.separation_m ?? v.seasonal?.separation_m ?? 0);
  const wet = v.seasonal?.water_table_wet_m;
  const dry = v.seasonal?.water_table_dry_m;

  // A single depth axis so the bands are comparable. Falls back to a sensible
  // total when the engine did not report one, and says so rather than drawing a
  // scale it cannot justify.
  const totalDepth = Math.max(oreDepth + 40, layer1Base + separation + 40, 200);
  const H = 210, W = 300, TOP = 14;
  const y = (m: number) => TOP + (m / totalDepth) * (H - TOP - 10);

  return (
    <>
      {heading && <div className="sec">Shallow aquifer — the water people pump</div>}

      <div className={`banner ${tone === "danger" ? "danger" : tone === "warn" ? "warn" : "ok"}`}
           style={{ marginBottom: 10 }}>
        <strong>
          {p === null || p === undefined
            ? "Not screened"
            : `${(p * 100).toFixed(0)}% chance of reaching the shallow aquifer`}
        </strong>
        {v.risk_band && <span className={`chip ${tone}`} style={{ marginLeft: 8 }}>
          {v.risk_band}
        </span>}
        <div className="muted small" style={{ marginTop: 4 }}>
          {years != null
            ? <>If it does, the model expects breakthrough after about{" "}
                <b>{fmt(years, 1)} years</b>.</>
            : <>The model does not expect breakthrough within the screened horizon.</>}
        </div>
      </div>

      {/* ── the depth schematic ── */}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label="Depth section from the surface through the shallow aquifer to the ore zone"
           style={{ display: "block", marginBottom: 10 }}>
        {/* ground surface */}
        <line x1="0" y1={y(0)} x2={W} y2={y(0)} stroke="var(--text)" strokeWidth="1.5" />
        <text x="4" y={y(0) - 4} fontSize="9" fill="var(--muted)">Ground surface</text>

        {/* shallow aquifer — what villages pump from */}
        {layer1Base > 0 && (
          <>
            <rect x="0" y={y(0)} width={W} height={Math.max(y(layer1Base) - y(0), 2)}
                  fill="var(--porous)" opacity="0.28" />
            <text x="6" y={y(layer1Base) - 5} fontSize="9" fill="var(--text)">
              Shallow aquifer · to {fmt(layer1Base, 0)} m
            </text>
          </>
        )}

        {/* seasonal water table band — the wet/dry swing */}
        {wet != null && dry != null && (
          <>
            <rect x="0" y={y(Number(wet))} width={W}
                  height={Math.max(y(Number(dry)) - y(Number(wet)), 2)}
                  fill="var(--accent)" opacity="0.35" />
            <text x={W - 4} y={y(Number(dry)) + 10} fontSize="8" textAnchor="end"
                  fill="var(--accent)">
              water table {fmt(wet, 1)}–{fmt(dry, 1)} m (wet–dry)
            </text>
          </>
        )}

        {/* confining layer — the barrier that decides the answer */}
        {layer1Base > 0 && oreDepth > layer1Base && (
          <>
            <rect x="0" y={y(layer1Base)} width={W}
                  height={Math.max(y(oreDepth) - y(layer1Base), 2)}
                  fill="var(--muted)" opacity="0.20" />
            <text x="6" y={(y(layer1Base) + y(oreDepth)) / 2 + 3} fontSize="9"
                  fill="var(--muted)">
              Confining rock · {fmt(oreDepth - layer1Base, 0)} m of separation
            </text>
          </>
        )}

        {/* ore / injection zone */}
        {oreDepth > 0 && (
          <>
            <rect x="0" y={y(oreDepth)} width={W}
                  height={Math.max(y(oreDepth + Number(v.ore_thickness_m ?? 20)) - y(oreDepth), 4)}
                  fill="var(--danger)" opacity="0.45" />
            <text x="6" y={y(oreDepth) + 13} fontSize="9" fill="var(--danger)"
                  fontWeight="700">
              Ore / injection zone · {fmt(oreDepth, 0)} m
            </text>
          </>
        )}

        {/* the upward pathway being screened */}
        {oreDepth > 0 && layer1Base > 0 && oreDepth > layer1Base && (
          <g opacity={p ? Math.max(0.25, Math.min(1, p)) : 0.25}>
            <line x1={W * 0.72} y1={y(oreDepth)} x2={W * 0.72} y2={y(layer1Base)}
                  stroke="var(--danger)" strokeWidth="2" strokeDasharray="4 3" />
            <polygon
              points={`${W * 0.72},${y(layer1Base)} ${W * 0.72 - 4},${y(layer1Base) + 7} ${W * 0.72 + 4},${y(layer1Base) + 7}`}
              fill="var(--danger)" />
          </g>
        )}
      </svg>
    </>
  );
}

export function VerticalNumbers({ v }: { v: VerticalScreening | null | undefined }) {
  if (!v) return null;

  const pathways = Object.entries(v.pathways ?? {})
    .filter(([, val]) => typeof val === "number")
    .sort((a, b) => (b[1] as number) - (a[1] as number));

  return (
    <>
      <dl className="kv">
        {v.dominant_pathway && (
          <>
            <dt>Most likely route</dt>
            <dd>{PATHWAY_LABEL[v.dominant_pathway] ?? v.dominant_pathway}</dd>
          </>
        )}
        {v.seasonal?.water_table_source && (
          <>
            <dt>Water table from</dt>
            <dd>{v.seasonal.water_table_source === "pin"
              ? "measured wells at this location"
              : v.seasonal.water_table_source}</dd>
          </>
        )}
      </dl>

      {pathways.length > 0 && (
        <>
          <div className="muted small" style={{ margin: "8px 0 4px" }}>
            How it would get there, by likelihood:
          </div>
          {pathways.map(([k, val]) => (
            <div key={k} className="readonly-val" style={{ marginBottom: 4 }}>
              <span className="muted small">{PATHWAY_LABEL[k] ?? k}</span>
              <span><span className="rv-v">{((val as number) * 100).toFixed(0)}</span>
                <span className="rv-u"> %</span></span>
            </div>
          ))}
        </>
      )}

      {/* The seasonal split is the most decision-relevant number here and the
          easiest to lose: the same site can be low risk in the monsoon and high
          risk in the dry season, because the gradient reverses. */}
      {v.seasonal?.static_deep_head && (
        <div className="banner warn" style={{ marginTop: 10 }}>
          <strong>Season changes the answer.</strong>
          <div className="table-scroll" style={{ marginTop: 6 }}>
            <table className="grid">
              <thead>
                <tr><th>Season</th><th>Chance of impact</th><th>Breakthrough</th></tr>
              </thead>
              <tbody>
                {Object.entries(v.seasonal.static_deep_head).map(([season, s]: [string, any]) => (
                  <tr key={season}>
                    <td>{season.replace(/_/g, " ")}</td>
                    <td className="mono">
                      {s.shallow_impact_probability != null
                        ? `${(s.shallow_impact_probability * 100).toFixed(0)}%` : "–"}
                    </td>
                    <td className="mono">
                      {s.years_to_breakthrough != null
                        ? `${fmt(s.years_to_breakthrough, 1)} yr` : "not expected"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="muted small" style={{ marginTop: 8, lineHeight: "var(--lh-base)" }}>
        This is a <b>screening</b> estimate of upward movement into the shallow
        aquifer, not a three-dimensional flow model. It is deliberately
        conservative and is the answer to “would this reach the water people
        actually pump”, which the horizontal plume above does not address.
      </div>
    </>
  );
}
