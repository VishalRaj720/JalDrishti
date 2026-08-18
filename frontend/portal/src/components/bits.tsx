/** Small shared pieces used across screens. */
import type { CSSProperties, ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="muted small" style={{ padding: 12 }} role="status" aria-live="polite">
      <span className="spinner" /> {label}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return <div className="banner danger" role="alert">{msg}</div>;
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
      <div className="row wrap">
        <span style={{ fontSize: "var(--fs-sm)" }}>{label}</span>
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
  const cls = `tile ${tone} ${onClick ? "clickable" : ""}`;
  if (!onClick) {
    return (
      <div className={cls}>
        <div className="tile-n">{n}</div>
        <div className="tile-l">{label}</div>
        {sub && <div className="tile-s">{sub}</div>}
      </div>
    );
  }
  // A clickable tile is a button, not a div with a handler — otherwise it is
  // unreachable by keyboard, and these are the primary navigation on every
  // role's landing screen.
  return (
    <button type="button" className={cls} onClick={onClick}>
      <div className="tile-n">{n}</div>
      <div className="tile-l">{label}</div>
      {sub && <div className="tile-s">{sub}</div>}
    </button>
  );
}

/**
 * Risk band from a measured uranium maximum, matching the public API's rule.
 *
 * Returns FOUR encodings of the same fact, because colour alone is not an
 * accessible carrier and this ramp is the entire risk vocabulary of the
 * product:
 *
 *   `label`  the words
 *   `cls`    the legacy chip class (danger/warn/ok/neutral) — kept because the
 *            map's colour RAMP is keyed on it
 *   `band`   the `.band` class, which adds a glyph and a border treatment
 *   `dash` / `weight`  what Leaflet strokes a polygon with, so the four bands
 *            are separable on the map in greyscale as well as in colour
 */
export type BandInfo = {
  label: string;
  cls: "danger" | "warn" | "ok" | "neutral";
  band: "high" | "moderate" | "low" | "none";
  dash: string | undefined;
  weight: number;
};

export function bandOf(maxU: number | null | undefined): BandInfo {
  if (maxU === null || maxU === undefined)
    return { label: "No data", cls: "neutral", band: "none", dash: "3 4", weight: 1 };
  if (maxU >= 30)
    return { label: "High concern", cls: "danger", band: "high", dash: undefined, weight: 3 };
  if (maxU >= 15)
    return { label: "Moderate concern", cls: "warn", band: "moderate", dash: "8 3", weight: 2 };
  return { label: "Low concern", cls: "ok", band: "low", dash: undefined, weight: 1.2 };
}

/** The band as a badge. Always prefer this over a bare coloured chip. */
export function RiskBand({ value, label }: { value?: number | null; label?: string }) {
  const b = label
    ? { band: BAND_BY_LABEL[label] ?? "none", label }
    : bandOf(value);
  return <span className={`band ${b.band}`}>{b.label}</span>;
}

/** Maps the API's band strings onto the `.band` classes. */
export const BAND_BY_LABEL: Record<string, "high" | "moderate" | "low" | "none"> = {
  "High concern": "high",
  "Moderate concern": "moderate",
  "Low concern": "low",
  "No data": "none",
};

/** A labelled form control with an optional hint and error. */
export function Field({
  label, hint, error, htmlFor, children,
}: {
  label: string; hint?: ReactNode; error?: string | null;
  htmlFor?: string; children: ReactNode;
}) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <div className="err">{error}</div>
             : hint ? <div className="hint">{hint}</div> : null}
    </div>
  );
}

/**
 * A value the reader may see but not change.
 *
 * Used for the parameters pinned onto a registered ISR site. Deliberately not
 * a disabled `<input>`: a disabled control reads as "you could set this, but
 * not right now", and these are properties of the site itself — changing them
 * means editing the site, not the run.
 */
export function ReadOnly({
  label, value, unit, title,
}: { label: string; value: ReactNode; unit?: string; title?: string }) {
  return (
    <div className="readonly-val" title={title} style={{ marginBottom: 6 }}>
      <span className="muted small">{label}</span>
      <span>
        <span className="rv-v">{value}</span>
        {unit && <span className="rv-u"> {unit}</span>}
      </span>
    </div>
  );
}

export function Section({ children }: { children: ReactNode }) {
  return <div className="sec">{children}</div>;
}

/** Wraps a wide table so it scrolls itself instead of the page. */
export function TableScroll({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return <div className="table-scroll" style={style}>{children}</div>;
}

/**
 * The hypothetical premise, as a reusable block (§4.5 rule 6).
 *
 * It appears on every surface that shows model output, and having it in one
 * place is what stops the wording drifting between screens — a drift that
 * would read as one screen being more confident than another.
 */
export function HypotheticalNote({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <span className="chip warn" title="No ISR uranium mine operates in Jharkhand.">
        Hypothetical
      </span>
    );
  }
  return (
    <div className="banner warn">
      <strong>No ISR uranium mine operates in Jharkhand.</strong> Every site here is a
      hypothetical scenario used for screening and preparedness. Nothing on this screen
      reports an operation that has taken place.
    </div>
  );
}
