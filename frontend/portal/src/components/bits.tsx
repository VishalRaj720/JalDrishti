/** Small shared pieces used across screens. */
import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="muted small" style={{ padding: 12 }}>
      <span className="spinner" /> {label}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="banner danger">{msg}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="card muted small">{children}</div>;
}

/**
 * A feature the backend does not implement yet.
 *
 * Rendered as a visibly disabled control with its delivery phase, so a reviewer
 * can see the intended shape of the product without being misled into thinking
 * it works. PRODUCT_DESIGN §4.7 lists what belongs here and why.
 */
export function Planned({ label, phase, why }: { label: string; phase: string; why?: string }) {
  return (
    <div
      className="card"
      style={{ opacity: 0.72, borderStyle: "dashed", marginBottom: 10 }}
      title={why}
    >
      <div className="row">
        <span style={{ fontSize: 12.5 }}>{label}</span>
        <span className="spacer grow" />
        <span className="chip planned">Planned · {phase}</span>
      </div>
      {why && <div className="muted small" style={{ marginTop: 5 }}>{why}</div>}
    </div>
  );
}

/** The tri-state used everywhere a field observation appears (§4.4b). */
export function StateChip({ state }: { state: "red" | "amber" | "green" }) {
  const map = {
    red: { cls: "danger", dot: "🔴", text: "Pending review" },
    amber: { cls: "warn", dot: "🟡", text: "Approved · not in model" },
    green: { cls: "ok", dot: "🟢", text: "In model" },
  }[state];
  return <span className={`chip ${map.cls}`}>{map.dot} {map.text}</span>;
}

export function Metric({
  label, value, unit, band, tone = "",
}: { label: string; value: ReactNode; unit?: string; band?: ReactNode; tone?: string }) {
  return (
    <div className={`metric ${tone}`}>
      <div className="m-label">{label}</div>
      <div className="m-value">
        {value} {unit && <span className="m-unit">{unit}</span>}
      </div>
      {band && <div className="m-band">{band}</div>}
    </div>
  );
}

export function Tile({
  n, label, sub, tone = "blue", onClick,
}: { n: ReactNode; label: string; sub?: string; tone?: string; onClick?: () => void }) {
  return (
    <div className={`tile ${tone} ${onClick ? "clickable" : ""}`} onClick={onClick}>
      <div className="tile-n">{n}</div>
      <div className="tile-l">{label}</div>
      {sub && <div className="tile-s">{sub}</div>}
    </div>
  );
}

/** Risk band from a measured uranium maximum, matching the public API's rule. */
export function bandOf(maxU: number | null | undefined) {
  if (maxU === null || maxU === undefined) return { label: "No data", cls: "neutral" };
  if (maxU >= 30) return { label: "High concern", cls: "danger" };
  if (maxU >= 15) return { label: "Moderate concern", cls: "warn" };
  return { label: "Low concern", cls: "ok" };
}
