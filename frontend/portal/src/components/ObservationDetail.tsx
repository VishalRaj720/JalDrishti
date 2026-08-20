/**
 * What a field submission actually said — in words, not as a JSON dump.
 *
 * WHAT THIS REPLACES. Every submission rendered as `JSON.stringify(payload)`
 * in a monospace block. That is a readable format for the person who wrote the
 * schema and an unreadable one for the officer who took the measurement:
 * `uranium_ppb: 11.1` does not say that 11.1 is above the BIS drinking-water
 * limit of 30 µg/L or below it, and `radius_m: 400` does not say that 400 m was
 * the fallback nobody chose. A reviewer approving on that basis is approving a
 * shape, not a claim.
 *
 * THE ONE FACT THIS EXISTS TO SURFACE. "Approved" and "in the model" are
 * different states, and the gap between them is the whole reason the sync
 * button exists. The record used to stop at approved, so an approved
 * observation read as counted — and the honest answer for an unsynced one is
 * that the engine has never seen it. Every expanded entry says which of the two
 * it is, in those terms.
 *
 * Units and limits are stated because a number without them is not a
 * measurement. The BIS 10500 uranium limit (30 µg/L) is the one threshold shown
 * inline, since it is the only one a submitter is likely to be judging against
 * in the field.
 */
import { type Observation } from "../api/client";

/** Field label, unit, and how to read the value. Ordered as a person reads. */
const LABELS: Record<string, { label: string; unit?: string; hint?: string }> = {
  // ore presence
  name: { label: "Deposit name" },
  longitude: { label: "Longitude", unit: "°E" },
  latitude: { label: "Latitude", unit: "°N" },
  radius_m: {
    label: "Extent radius", unit: "m",
    hint: "How far the ore was judged to extend from that centre. Left empty, "
        + "the loader assumes 400 m.",
  },
  ore_zone: { label: "Zone type" },
  uranium_grade_pct: {
    label: "Uranium grade", unit: "% U₃O₈",
    hint: "Scales the modelled source concentration linearly.",
  },
  observed_at: { label: "Observed on" },
  notes: { label: "Field notes" },

  // water quality
  well_id: { label: "Well" },
  sampled_at: { label: "Sampled on" },
  uranium_ppb: {
    label: "Uranium", unit: "µg/L",
    hint: "BIS 10500 drinking-water limit is 30 µg/L.",
  },
  ph: { label: "pH" },
  ec_us_cm: { label: "Electrical conductivity", unit: "µS/cm" },
  tds_mg_l: {
    label: "Total dissolved solids", unit: "mg/L",
    hint: "One of the three excursion indicators, with chloride and sulphate.",
  },
  chloride_mg_l: { label: "Chloride", unit: "mg/L" },
  sulphate_mg_l: { label: "Sulphate", unit: "mg/L" },
  nitrate_mg_l: { label: "Nitrate", unit: "mg/L" },
  fluoride_mg_l: { label: "Fluoride", unit: "mg/L" },
  total_hardness: { label: "Total hardness", unit: "mg/L as CaCO₃" },
  iron_ppm: { label: "Iron", unit: "ppm" },
  arsenic_ppb: { label: "Arsenic", unit: "µg/L" },
  bicarbonate_mg_l: { label: "Bicarbonate", unit: "mg/L" },

  // groundwater level
  station_id: { label: "Station" },
  recorded_at: { label: "Recorded on" },
  groundwater_level: {
    label: "Depth to water", unit: "m below ground",
    hint: "Feeds the flow field — gradient and direction at every pin.",
  },
};

const TYPE_NAME: Record<string, string> = {
  ore_presence: "Uranium ore sighting",
  water_sample: "Water quality sample",
  groundwater_level: "Groundwater level reading",
};

/** What this submission governs once it reaches the datasets. */
const GOVERNS: Record<string, string> = {
  ore_presence:
    "Whether a uranium plume is possible at this location at all, and the "
    + "source concentration the engine starts from.",
  water_sample:
    "The excursion baselines every screening is compared against.",
  groundwater_level:
    "The flow field — which way a plume travels, and how fast.",
};

function pretty(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) {
    const d = new Date(v);
    if (!Number.isNaN(d.getTime())) return d.toLocaleString();
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Uranium against the BIS limit, when the payload carries one. */
function uraniumVerdict(p: Record<string, unknown>): string | null {
  const u = p.uranium_ppb;
  if (typeof u !== "number") return null;
  if (u > 30) return `${u} µg/L is above the BIS 10500 limit of 30 µg/L.`;
  return `${u} µg/L is within the BIS 10500 limit of 30 µg/L.`;
}

export default function ObservationDetail({ o }: { o: Observation }) {
  const proposed = (o.proposed ?? {}) as Record<string, unknown>;
  const previous = (o.previous ?? null) as Record<string, unknown> | null;

  // Known fields first, in the order declared above; anything the schema gains
  // later still appears, rather than silently vanishing from the review screen.
  const known = Object.keys(LABELS).filter((k) => k in proposed);
  const extra = Object.keys(proposed).filter((k) => !(k in LABELS));
  const keys = [...known, ...extra];

  const verdict = uraniumVerdict(proposed);
  const synced = !!o.synced_to_dataset_at;

  return (
    <div style={{ marginTop: 10 }}>
      <div className="muted small" style={{ marginBottom: 6 }}>
        <b>{TYPE_NAME[o.observation_type] ?? o.observation_type.replace(/_/g, " ")}</b>
        {GOVERNS[o.observation_type] ? <> — {GOVERNS[o.observation_type]}</> : null}
      </div>

      {keys.length === 0 ? (
        <div className="muted small">
          {o.operation === "delete"
            ? "A request to remove an existing record."
            : "No values were submitted with this entry."}
        </div>
      ) : (
        <div className="table-scroll">
          <table className="grid">
            <tbody>
              {keys.map((k) => {
                const meta = LABELS[k];
                const changed = previous && pretty(previous[k]) !== pretty(proposed[k]);
                return (
                  <tr key={k}>
                    <td style={{ width: "38%" }}>
                      {meta?.label ?? k.replace(/_/g, " ")}
                      {meta?.hint && (
                        <div className="muted small" style={{ lineHeight: "var(--lh-base)" }}>
                          {meta.hint}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="mono">{pretty(proposed[k])}</span>
                      {meta?.unit ? <span className="rv-u"> {meta.unit}</span> : null}
                      {changed && (
                        <div className="muted small">
                          was <span className="mono">{pretty(previous![k])}</span>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {verdict && (
        <div className={`banner ${(proposed.uranium_ppb as number) > 30 ? "warn" : "ok"}`}
             style={{ marginTop: 8 }}>
          {verdict}{" "}
          {(proposed.uranium_ppb as number) > 30
            ? "One sample is not a trend — this is a reading, not a determination."
            : ""}
        </div>
      )}

      {/* The state the record used to stop short of. */}
      {o.status === "approved" && (
        <div className={`banner ${synced ? "ok" : "warn"}`} style={{ marginTop: 8 }}>
          {synced ? (
            <>
              <strong>In the model.</strong> Written into the datasets on{" "}
              {new Date(o.synced_to_dataset_at!).toLocaleString()}
              {o.dataset_sync_ref
                ? <> as <span className="mono">{o.dataset_sync_ref}</span></> : null}
              , so the engine reads it.
            </>
          ) : (
            <>
              <strong>Approved, but not yet in the model.</strong> The engine reads
              the files in <span className="mono">Datasets/</span>, and this has not
              been written to them yet — every screening run so far was produced
              without it. An administrator closes the gap from Data &amp; Gaps.
            </>
          )}
        </div>
      )}

      <div className="muted small" style={{ marginTop: 8 }}>
        Submitted {new Date(o.submitted_at).toLocaleString()}
        {o.note ? <> · “{o.note}”</> : null}
        {o.reviewed_at
          ? <> · {o.status} {new Date(o.reviewed_at).toLocaleString()}</> : null}
        {o.review_note ? <> · reviewer said “{o.review_note}”</> : null}
      </div>
    </div>
  );
}
