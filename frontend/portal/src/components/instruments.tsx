/**
 * Composed readouts shared across the screens that carry measurements.
 *
 * `bits.tsx` holds the small pieces — a chip, a tile, a loading row. This file
 * holds the ones with a rule inside them: a determinand against its published
 * limits, a set of counts as a proportion, a work queue, a coverage grid, an
 * age. Each exists because a screen was answering its question with a table and
 * the reader had to do the arithmetic.
 *
 * THE INVARIANT ACROSS ALL OF THEM. Nothing here defaults a missing value to
 * zero, hides it, or lets it inherit a passing colour. A gap is rendered as a
 * gap — hatched, dashed, grey, and named — because on this product the
 * difference between "measured and clean" and "never measured" is the whole
 * point. `styles/instruments.css` carries the visual half of that rule.
 */
import type { ReactNode } from "react";
import type { WqStatus } from "../api/client";
import { BAND_GLYPH, bandKey } from "./bits";

export type Tone = "ok" | "warn" | "danger" | "info" | "gap";

/**
 * Format a measurement for display.
 *
 * Determinands here span four orders of magnitude — pH 7.2, fluoride 1.42, TDS
 * 2,140 — so a fixed precision is wrong for most of them. Significant digits
 * scale with size, and an integer stays an integer rather than gaining a
 * decorative ".00".
 */
export function fmtVal(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (Number.isInteger(v) && a < 10000) return String(v);
  if (a >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

/** The five IS 10500 statuses, in one place.
 *
 *  This vocabulary used to live inside `WaterQuality.tsx`, which meant every
 *  other screen showing a determinand either imported nothing and invented its
 *  own wording, or showed a bare number. Two of these five are the reason it
 *  matters: `no_limit` and `not_tested` are NEUTRAL, never `ok`. A determinand
 *  nobody analysed and a determinand the standard sets no limit for are both
 *  the absence of a judgement, and colouring either of them green is the bug
 *  this table exists to prevent. */
export const WQ_STATUS: Record<WqStatus, { label: string; cls: string; glyph: string }> = {
  above_permissible: { label: "Above permissible", cls: "danger", glyph: "🔴" },
  above_acceptable: { label: "Above acceptable", cls: "warn", glyph: "🟠" },
  acceptable: { label: "Within limits", cls: "ok", glyph: "🟢" },
  no_limit: { label: "No BIS limit", cls: "neutral", glyph: "⚪" },
  not_tested: { label: "Not tested", cls: "neutral", glyph: "⚫" },
};

export function StatusChip({ status }: { status: WqStatus }) {
  const s = WQ_STATUS[status];
  return <span className={`chip ${s.cls}`}>{s.glyph} {s.label}</span>;
}

/** The limit column, spelled out rather than reduced to one number.
 *  "1.0 / 1.5" and "45 (no relaxation)" are different regimes, and a reader
 *  acting on the number needs to know which one they are in. */
export function limitText(p: {
  acceptable: number | null; permissible: number | null;
  range: [number | null, number | null] | null; relaxation: string;
}): string {
  if (p.range) return `${p.range[0]}–${p.range[1]}`;
  if (p.acceptable === null) return "—";
  if (p.permissible !== null) return `${p.acceptable} / ${p.permissible}`;
  return `${p.acceptable}${p.relaxation ? " (no relaxation)" : ""}`;
}

// ── the determinand scale ────────────────────────────────────────────

const pct = (v: number, lo: number, hi: number) =>
  Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100));

type Zone = { from: number; to: number; tone: "ok" | "warn" | "danger" };

/**
 * Work out the track for one determinand: its domain, its zones and its
 * thresholds. Exported separately from the component so the rule can be
 * reasoned about — and checked — without rendering anything.
 *
 * THE DOMAIN RULE, which is the only judgement call in here. An unbounded
 * concentration has no natural right-hand end, so the track ends at TWICE the
 * governing limit. That choice keeps the threshold markers in the middle third
 * of the track where they can be read, at the cost of putting extreme values
 * off the end — which is handled by drawing them off the end rather than by
 * clamping them silently. A track scaled to the observed maximum instead would
 * make a well at 1.1× the limit and a well at 9× look equally alarming, because
 * both would sit near the right edge of their own private scale.
 */
export function scaleGeometry(p: {
  acceptable: number | null;
  permissible: number | null;
  range: [number | null, number | null] | null;
}): { lo: number; hi: number; zones: Zone[]; thresholds: number[] } | null {
  // pH and anything else with a two-sided acceptable range: failure is in both
  // directions, so the safe zone sits in the middle with danger either side.
  if (p.range && p.range[0] !== null && p.range[1] !== null) {
    const [r0, r1] = p.range as [number, number];
    const pad = Math.max(r1 - r0, 1);
    const lo = r0 - pad;
    const hi = r1 + pad;
    return {
      lo, hi,
      zones: [
        { from: lo, to: r0, tone: "danger" },
        { from: r0, to: r1, tone: "ok" },
        { from: r1, to: hi, tone: "danger" },
      ],
      thresholds: [r0, r1],
    };
  }

  if (p.acceptable === null) return null;   // analysed, but no limit to draw

  const gov = p.permissible ?? p.acceptable;
  const hi = gov * 2;
  const zones: Zone[] = [{ from: 0, to: p.acceptable, tone: "ok" }];
  if (p.permissible !== null && p.permissible > p.acceptable) {
    zones.push({ from: p.acceptable, to: p.permissible, tone: "warn" });
    zones.push({ from: p.permissible, to: hi, tone: "danger" });
  } else {
    // No relaxation: past the acceptable limit there is no tolerated band, so
    // there is no amber to draw. Inventing one would misstate the standard.
    zones.push({ from: p.acceptable, to: hi, tone: "danger" });
  }
  return {
    lo: 0, hi, zones,
    thresholds: p.permissible !== null && p.permissible > p.acceptable
      ? [p.acceptable, p.permissible]
      : [p.acceptable],
  };
}

export interface ScaleProps {
  label: string;
  unit: string;
  value: number | null;
  status: WqStatus;
  acceptable: number | null;
  permissible: number | null;
  range: [number | null, number | null] | null;
  timesLimit?: number | null;
  relaxation?: string;
  health?: boolean;
  derived?: boolean;
  compact?: boolean;
  /** Overrides the default "no measurement exists" wording — the citizen
   *  surface says this differently from the staff one. */
  gapNote?: string;
  /**
   * Replaces the IS 10500 status chip.
   *
   * EXISTS BECAUSE TWO SURFACES JUDGE THE SAME NUMBER BY DIFFERENT RULES, and
   * showing both vocabularies at once reads as self-contradiction. The citizen
   * screen bands uranium at half the limit ("worth watching") and at the limit;
   * IS 10500 knows only pass and fail. Rendering "Within limits" directly under
   * a verdict of "Moderate concern" is technically true twice over and tells a
   * resident the screen cannot make up its mind. The caller passes the chip
   * that matches the words it has already used.
   */
  statusChip?: ReactNode;
  /** Extra explanation under the track — what the threshold marks mean, when
   *  they are not the standard's own acceptable/permissible pair. */
  footNote?: ReactNode;
}

/**
 * One measurement against its published limits.
 *
 * Every boundary drawn here comes from IS 10500:2012 as served by
 * `/water-quality/standard`. Nothing about the geometry is a design decision
 * about what looks concerning; it is the standard, drawn to scale.
 */
export function DeterminandScale({
  label, unit, value, status, acceptable, permissible, range,
  timesLimit, relaxation, health, derived, compact, gapNote,
  statusChip, footNote,
}: ScaleProps) {
  const geo = scaleGeometry({ acceptable, permissible, range });
  const untested = status === "not_tested" || value === null;
  const cls = `ds ${status}${compact ? " compact" : ""}`;

  return (
    <div className={cls}>
      <div className="ds-head">
        <span className="ds-label">{label}</span>
        {health && <span className="chip danger">health</span>}
        {derived && <span className="chip neutral">derived</span>}
        <span className="ds-value">
          {untested ? "—" : fmtVal(value)}
          {!untested && unit && <span className="u"> {unit}</span>}
        </span>
      </div>

      {untested ? (
        <>
          {/* An empty dashed channel, and no marker. A marker at zero would be
              a reading, and there is no reading — that misread is exactly what
              this branch exists to prevent. */}
          <div className="ds-track" />
          <div className="ds-gap-note">
            <span aria-hidden>⚫</span>
            {gapNote ?? "Not tested — no measurement exists for this determinand here. A monitoring gap, not a clean result."}
          </div>
        </>
      ) : geo === null ? (
        // Analysed, and the standard sets no drinking-water limit for it. Not a
        // pass, so there is nothing to draw and the note says why.
        <div className="ds-gap-note">
          <span aria-hidden>⚪</span>
          IS 10500 sets no drinking-water limit for this determinand. Measured, not judged.
        </div>
      ) : (
        <>
          <div className="ds-track">
            {geo.zones.map((z) => (
              <div
                key={`${z.from}-${z.tone}`}
                className={`ds-zone ${z.tone}`}
                style={{
                  left: `${pct(z.from, geo.lo, geo.hi)}%`,
                  width: `${pct(z.to, geo.lo, geo.hi) - pct(z.from, geo.lo, geo.hi)}%`,
                }}
              />
            ))}
            {geo.thresholds.map((t) => (
              <div key={`t${t}`} className="ds-thr" style={{ left: `${pct(t, geo.lo, geo.hi)}%` }} />
            ))}
            {geo.thresholds.map((t) => (
              <span key={`l${t}`} className="ds-thr-l" style={{ left: `${pct(t, geo.lo, geo.hi)}%` }}>
                {fmtVal(t)}
              </span>
            ))}
            <div
              className={`ds-mark${value! > geo.hi ? " off" : ""}`}
              style={{ left: `${pct(value!, geo.lo, geo.hi)}%` }}
            />
          </div>

          <div className="ds-foot">
            {statusChip ?? <StatusChip status={status} />}
            {timesLimit != null && (
              <span className={`x${timesLimit > 1 ? " over" : ""}`}>
                {timesLimit}× the limit
              </span>
            )}
            {value! > geo.hi && (
              <span className="x over">beyond the scale — value shown above</span>
            )}
            {relaxation && <span>{relaxation}</span>}
          </div>
          {footNote && (
            <div className="ds-gap-note" style={{ marginTop: "var(--s-2)" }}>
              {footNote}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── composition ──────────────────────────────────────────────────────

export interface Segment { key: string; label: string; n: number; tone: Tone }

/**
 * Counts that sum to a whole, as one bar.
 *
 * Four tiles reading 218 / 42 / 31 / 51 make the reader divide. One bar makes
 * the proportion the first thing they see and keeps the counts underneath for
 * anyone who needs the exact figure.
 *
 * A `gap` segment is hatched rather than merely grey, so an unmeasured share
 * reads as a different KIND of thing from a measured one. Zero-count segments
 * leave the bar — a 0px slice is a rendering artefact — but stay in the key,
 * because "0 wells above the permissible limit" is a result worth stating.
 */
export function Composition({
  segments, caption,
}: { segments: Segment[]; caption?: ReactNode }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.n), 0);
  return (
    <div className="comp">
      <div className="comp-bar" role="img"
           aria-label={segments.map((s) => `${s.n} ${s.label}`).join(", ")}>
        {total > 0 && segments.filter((s) => s.n > 0).map((s) => (
          <div key={s.key} className={`comp-seg ${s.tone}`}
               style={{ flex: `${s.n} 0 0` }} title={`${s.label}: ${s.n}`} />
        ))}
      </div>
      <div className="comp-key">
        {segments.map((s) => (
          <span key={s.key} className="comp-key-item">
            <span className={`comp-sw ${s.tone}`} aria-hidden />
            <b>{s.n.toLocaleString("en-US")}</b> {s.label}
          </span>
        ))}
      </div>
      {caption && <div className="muted small" style={{ marginTop: "var(--s-2)" }}>{caption}</div>}
    </div>
  );
}

/**
 * One row of a ranking: a label, a proportion, and the count.
 *
 * `of` is the denominator the share is taken against, and it is required
 * rather than optional on purpose — a bar with no stated denominator is a
 * picture of a number, and two such bars from different denominators would
 * invite a comparison that is not valid.
 */
export function RankBar({
  label, n, of, tone = "info", chip, note,
}: {
  label: ReactNode; n: number; of: number; tone?: "danger" | "warn" | "info";
  chip?: ReactNode; note?: string;
}) {
  const share = of > 0 ? (n / of) * 100 : 0;
  return (
    <div className="rank-row">
      <span className="rank-l">{label}{chip}</span>
      <span className="rank-track" role="img"
            aria-label={`${n} of ${of}, ${share.toFixed(1)} percent`}>
        <span className={`rank-fill ${tone}`} style={{ width: `${share}%` }} />
      </span>
      <span className="rank-n" title={note}>
        <b>{n.toLocaleString("en-US")}</b> · {share.toFixed(1)}%
      </span>
    </div>
  );
}

/** The composition bar reduced to fit a table cell. Same segments, same tones,
 *  no key — the key lives once above the table rather than in every row. */
export function CompositionMini({ segments }: { segments: Segment[] }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.n), 0);
  return (
    <span className="comp-mini" role="img"
          aria-label={segments.map((s) => `${s.n} ${s.label}`).join(", ")}
          title={segments.map((s) => `${s.n} ${s.label}`).join(" · ")}>
      {total > 0 && segments.filter((s) => s.n > 0).map((s) => (
        <span key={s.key} className={`comp-seg ${s.tone}`} style={{ flex: `${s.n} 0 0` }} />
      ))}
    </span>
  );
}

// ── statement + readouts ─────────────────────────────────────────────

export function Statement({
  eyebrow, line, sub, children,
}: { eyebrow: string; line: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <section className="stmt">
      <div className="stmt-eyebrow">{eyebrow}</div>
      <p className="stmt-line">{line}</p>
      {sub && <p className="stmt-sub">{sub}</p>}
      {children && <div className="stmt-readouts">{children}</div>}
    </section>
  );
}

export function Readout({
  label, value, unit, sub, tone,
}: {
  label: string; value: ReactNode; unit?: string; sub?: ReactNode; tone?: Tone;
}) {
  return (
    <div className={`readout ${tone ?? ""}`}>
      <div className="readout-l">{label}</div>
      <div className="readout-v">
        {value}{unit && <span className="u"> {unit}</span>}
      </div>
      {sub && <div className="readout-s">{sub}</div>}
    </div>
  );
}

// ── section head ─────────────────────────────────────────────────────

export function SectionHead({
  title, children, action, id,
}: { title: string; children?: ReactNode; action?: ReactNode; id?: string }) {
  return (
    <div className="sh">
      <div className="sh-main">
        <h2 id={id}>{title}</h2>
        {children && <p>{children}</p>}
      </div>
      {action && <div className="sh-act">{action}</div>}
    </div>
  );
}

// ── work queue ───────────────────────────────────────────────────────

export function Queue({ children }: { children: ReactNode }) {
  return <div className="queue">{children}</div>;
}

export function QueueItem({
  tone = "info", title, meta, side, onClick,
}: {
  tone?: Tone; title: ReactNode; meta?: ReactNode; side?: ReactNode; onClick?: () => void;
}) {
  const inner = (
    <>
      <div className="queue-main">
        <div className="queue-t">{title}</div>
        {meta && <div className="queue-m">{meta}</div>}
      </div>
      {side && <div className="queue-side">{side}</div>}
    </>
  );
  // A row that acts is a button, not a div with a handler — these are the
  // primary navigation on every landing screen and must be keyboard-reachable.
  if (!onClick) return <div className={`queue-item ${tone}`}>{inner}</div>;
  return (
    <button type="button" className={`queue-item ${tone}`} onClick={onClick}>
      {inner}
    </button>
  );
}

/** An empty queue states its result. "Nothing is waiting on you" is what a
 *  reviewer came to find out; a blank area leaves them wondering whether it
 *  loaded. */
export function QueueClear({ children }: { children: ReactNode }) {
  return <div className="queue-clear">{children}</div>;
}

// ── freshness ────────────────────────────────────────────────────────

const MS_YEAR = 365.25 * 24 * 3600 * 1000;

export function yearsSince(at: string | null | undefined): number | null {
  if (!at) return null;
  const t = Date.parse(at);
  if (!Number.isFinite(t)) return null;
  return (Date.now() - t) / MS_YEAR;
}

/**
 * How old the newest evidence is.
 *
 * This matters more here than in most products. The CGWB quality series ends
 * years before today, so for many blocks the most recent sample is the only
 * sample, and a screen that prints a date without saying how old it is invites
 * the reader to assume it is current. `staleYears` defaults to 5 but should be
 * passed the server's own `stale_years` wherever the API supplies it, so the UI
 * and the data-gap register cannot disagree about what "stale" means.
 */
export function Freshness({
  at, staleYears = 5, agingYears = 2, prefix = "last tested",
}: { at?: string | null; staleYears?: number; agingYears?: number; prefix?: string }) {
  const y = yearsSince(at);
  if (y === null) {
    return <span className="fresh never" title="No sample date recorded">never sampled</span>;
  }
  const cls = y >= staleYears ? "stale" : y >= agingYears ? "aging" : "recent";
  const age = y < 1
    ? `${Math.max(1, Math.round(y * 12))} month${Math.round(y * 12) === 1 ? "" : "s"} ago`
    : `${y.toFixed(y < 10 ? 1 : 0)} years ago`;
  return (
    <span className={`fresh ${cls}`} title={at ? new Date(at).toLocaleDateString() : undefined}>
      {prefix} {age}
    </span>
  );
}

// ── coverage cells ───────────────────────────────────────────────────

/**
 * Four steps, not a continuous ramp.
 *
 * A reader scanning a coverage grid is asking "is this district worse than that
 * one", and a 256-step ramp answers a question nobody has while making adjacent
 * districts indistinguishable. The count stays printed in the cell regardless,
 * so the step is an aid to scanning rather than the only carrier of the value.
 */
export function covClass(n: number, max: number): string {
  if (n <= 0) return "zero";
  if (max <= 0) return "s1";
  const r = n / max;
  if (r > 0.75) return "s4";
  if (r > 0.5) return "s3";
  if (r > 0.25) return "s2";
  return "s1";
}

// ── citizen verdict ──────────────────────────────────────────────────

/**
 * The answer to "is my water safe", for someone with no technical vocabulary.
 *
 * The band word is the largest thing on the screen because the alternative — a
 * chip in the corner of a card — makes a reader hunt for the verdict among the
 * evidence. The glyph beside it is the same one `.band` uses, so the two
 * renderings of the same fact cannot drift apart, and so the verdict survives
 * being read by someone who cannot separate the amber from the red.
 *
 * `band` is passed through from the server verbatim. It is not re-derived here,
 * and it is not shortened: "Not tested" and "No data" are different findings
 * and the citizen API distinguishes them on purpose.
 */
export function Verdict({
  band, place, district, say, children,
}: {
  band: string; place: string; district?: string | null;
  say?: ReactNode; children?: ReactNode;
}) {
  const k = bandKey(band);
  return (
    <section className={`verdict ${k}`}>
      <div className="verdict-place">
        <b>{place}</b>
        {district && <span>{district}</span>}
      </div>
      <div className="verdict-word">
        <span className="g" aria-hidden>{BAND_GLYPH[k]}</span>
        {band}
      </div>
      {say && <p className="verdict-say">{say}</p>}
      {children && <div className="verdict-evidence">{children}</div>}
    </section>
  );
}
