/**
 * The result of an engine run — one renderer for the live pin, the preview and
 * the stored run alike.
 *
 * R3: EVERY NUMBER NOW SAYS WHICH ENGINE PRODUCED IT.
 *
 * The portal used to show a bare figure with "ML P10–P90 …" underneath, which
 * invited exactly the wrong reading — that the number was the model's and the
 * band was a refinement of it. It is the other way round:
 *
 *   **The analytical engine is the authority.** It solves Domenico transport
 *   directly and is benchmarked against exact solutions.
 *
 *   **The ML surrogate is trained on that engine's own output.** It was fitted
 *   to synthetic scenarios the analytical engine generated, so it cannot be
 *   more accurate than its own teacher. What it adds is a calibrated
 *   *uncertainty band*, fast — not a better estimate.
 *
 * So the headline value is always analytical, labelled, and the ML band sits
 * beside it labelled as a band. `PRODUCT_DESIGN §4.6` rule 1 has said this from
 * the start; the UI simply never said it out loud.
 */
import type { ReactNode } from "react";
import { SPECIES_UNIT } from "../map/plume";
import { area, distance, fmt } from "./mapLayers";
import VerticalPanel from "./VerticalPanel";

/** One metric, with its provenance made explicit. */
function Metric({
  label, value, unit, mlBand, mlStatus, tone = "",
}: {
  label: string; value: ReactNode; unit?: string;
  mlBand?: { p10: number; p90: number } | null;
  mlStatus?: string | null; tone?: string;
}) {
  return (
    <div className={`metric ${tone}`}>
      <div className="m-label">{label}</div>
      <div className="m-value">
        {value} {unit && <span className="m-unit">{unit}</span>}
      </div>
      <div className="m-band">
        <span className="chip ok" style={{ fontSize: 9, padding: "1px 6px" }}>
          analytical
        </span>{" "}
        <span className="muted">authoritative value</span>
      </div>
      <div className="m-band" style={{ marginTop: 2 }}>
        {mlBand ? (
          <>
            <span className="chip info" style={{ fontSize: 9, padding: "1px 6px" }}>
              ML band
            </span>{" "}
            {fmt(mlBand.p10)} – {fmt(mlBand.p90)}
          </>
        ) : (
          <span className="muted">{mlStatus ?? "no ML band for this run"}</span>
        )}
      </div>
    </div>
  );
}

const band = (m: any) =>
  m && typeof m === "object" && m.p10 != null && m.p90 != null
    ? { p10: m.p10, p90: m.p90 } : null;

export default function RunResult({
  r, extrapolation = [], compact = false, showVertical = true,
}: { r: any; extrapolation?: string[]; compact?: boolean; showVertical?: boolean }) {
  const an = r?.metrics?.analytical;
  const ml = r?.metrics?.ml;
  const unit = SPECIES_UNIT[r?.species] ?? "";
  const exc = r?.isr_excursion ?? r?.excursion;

  return (
    <>
      {/* §4.5 rule 2 — extrapolation is loud. */}
      {extrapolation.length > 0 && (
        <div className="banner warn" style={{ marginTop: 10 }}>
          <strong>Outside trained support:</strong>{" "}
          <span className="mono">{extrapolation.join(", ")}</span>. The analytical
          engine remains valid and is what you are reading; the ML band&apos;s 80%
          conformal guarantee is <b>void</b> here.
        </div>
      )}

      {/* The engine's OWN words about why it refused a source term. Without
          this a non-ore pin renders as "0 ha", which reads as a measurement
          showing safety rather than the model declining to invent
          contamination (§4.6 rule 3). */}
      {r?.notice && (
        <div className="banner warn" style={{ marginTop: 10 }}>
          <strong>{r.ore_zone?.zone === "none" ? "Non-ore zone." : "Note."}</strong>{" "}
          {r.notice}
          {r.ore_zone?.nearest_deposit && (
            <div className="muted small" style={{ marginTop: 4 }}>
              Nearest deposit: {r.ore_zone.nearest_deposit} ·{" "}
              {fmt(r.ore_zone.nearest_deposit_km, 1)} km away.
            </div>
          )}
          <div className="muted small" style={{ marginTop: 4 }}>
            Sulfate and TDS are <b>not</b> suppressed here — switch contaminant to
            see how they would spread at this location.
          </div>
        </div>
      )}

      {r?.far_field_note && (
        <div className="banner" style={{ marginTop: 10 }}>{r.far_field_note}</div>
      )}

      <div className="sec">Result</div>
      <div className="metric-row">
        <Metric tone="danger" label="Contaminated footprint"
                value={area(an?.area_ha).text} unit={area(an?.area_ha).unit}
                mlBand={band(ml?.area_ha)} mlStatus={r?.ml_status} />
        <Metric label="Max migration"
                value={distance(an?.migration_m).text} unit={distance(an?.migration_m).unit}
                mlBand={band(ml?.migration_m)} mlStatus={r?.ml_status} />
        <Metric label="At the monitoring ring"
                value={fmt(an?.compliance_conc, 3)} unit={unit}
                mlBand={band(ml?.compliance_conc)} mlStatus={r?.ml_status} />
      </div>

      {/* Which engine is which — stated once, next to the numbers it governs. */}
      <div className="banner" style={{ marginTop: 8 }}>
        <strong>Analytical is the authority.</strong> Those values come from the
        physics engine, which solves contaminant transport directly and is
        benchmarked against exact solutions. The <b>ML band</b> beside each one is
        a fast uncertainty estimate from a surrogate <b>trained on this engine&apos;s
        own output</b> — it cannot be more accurate than the engine it learned
        from, and it is shown for spread, never as a better answer.
      </div>

      {r?.disagreement != null && typeof r.disagreement === "object"
        && Object.keys(r.disagreement).length > 0 && !compact && (
        <div className="muted small" style={{ marginTop: 6 }}>
          Surrogate-vs-engine disagreement on this request:{" "}
          <span className="mono">
            {Object.entries(r.disagreement)
              .filter(([, v]) => typeof v === "number")
              .map(([k, v]) => `${k} ${(Number(v) * 100).toFixed(0)}%`)
              .join(" · ") || "within tolerance"}
          </span>
        </div>
      )}

      {/* Extra engine output the portal used to drop entirely. */}
      {!compact && (
        <div className="grid-2" style={{ marginTop: 10 }}>
          {r?.plume?.peak_conc != null && (
            <div className="readonly-val">
              <span className="muted small">Peak concentration</span>
              <span><span className="rv-v">{fmt(r.plume.peak_conc, 1)}</span>
                <span className="rv-u"> {unit}</span></span>
            </div>
          )}
          {an?.excursion_probability != null && (
            <div className="readonly-val">
              <span className="muted small">Excursion probability</span>
              <span><span className="rv-v">
                {(Number(an.excursion_probability) * 100).toFixed(0)}</span>
                <span className="rv-u"> %</span></span>
            </div>
          )}
          {r?.azimuth_deg != null && (
            <div className="readonly-val">
              <span className="muted small">Plume heads</span>
              <span>
                <span className="rv-v">{fmt(r.azimuth_deg, 0)}°</span>
                <span className="rv-u"> {compass(r.azimuth_deg)}</span>
              </span>
            </div>
          )}
          {r?.nearest_river_km != null && (
            <div className="readonly-val">
              <span className="muted small">Nearest river</span>
              <span><span className="rv-v">{fmt(r.nearest_river_km, 1)}</span>
                <span className="rv-u"> km</span></span>
            </div>
          )}
        </div>
      )}

      {r?.azimuth_source && !compact && (
        <div className="muted small" style={{ marginTop: 6 }}>
          Direction is {
            r.azimuth_source === "user" ? "the value you set"
            : r.azimuth_source === "flow_field" ? "derived from the measured groundwater flow field"
            : r.azimuth_source === "flow_field+strike" ? "the measured flow field, rotated toward the dominant fracture strike"
            : "indeterminate here — the site sits near a groundwater divide with no preferred direction, so the plume is drawn radially"
          }.
        </div>
      )}

      {/* The footprint is overwhelmingly the leach disc, not migrating plume.
          §4.5 rule 4 requires the split be shown rather than letting one number
          be read as "how far the contamination spread". */}
      {r?.plume?.source_zone?.area_ha != null && an?.area_ha > 0 && (
        <div className="muted small" style={{ marginTop: 8 }}>
          Of that footprint, <b>{fmt(r.plume.source_zone.area_ha)} ha</b> is the leach
          zone itself — ground the operation deliberately swept — and the remainder is
          migrating plume.
          {r.plume.radial_dominated && (
            <> The source disc dominates here, so “migration” reads as contaminated
               <b> extent</b>, not travel distance.</>
          )}
        </div>
      )}

      {/* R2: the shallow-aquifer screening, which the portal never showed.
          R10: `showVertical` exists because the REPORT rendered this twice —
          once directly and once through here — producing two copies of the
          same depth section. The report now places it itself, at half width
          with its numbers beside it, and switches this copy off. */}
      {!compact && showVertical && <VerticalPanel v={r?.vertical} />}

      {exc && !compact && (
        <>
          <div className="sec">ISR excursion — NUREG-1569-inspired screening</div>
          <div className="row" style={{ marginBottom: 8 }}>
            <span className={`chip ${exc.excursion_declared ? "danger" : "ok"}`}>
              {exc.excursion_declared ? "DECLARED" : "none"}
            </span>
            <span className="muted small">{exc.rule}</span>
          </div>
          <div className="table-scroll">
            <table className="grid">
              <thead>
                <tr>
                  <th>Indicator</th><th>At ring</th><th>Baseline</th>
                  <th>UCL</th><th>Over</th>
                </tr>
              </thead>
              <tbody>
                {(exc.indicators ?? []).map((i: any) => (
                  <tr key={i.species ?? i.name}>
                    <td>
                      {(i.species ?? i.name ?? "").replace(/_mg_l$/, "").replace(/_/g, " ")}
                      {i.unit && <span className="muted small"> {i.unit}</span>}
                    </td>
                    <td className="mono">{fmt(i.ring_conc, 2)}</td>
                    <td className="mono">{fmt(i.baseline, 2)}</td>
                    <td className="mono">{fmt(i.upper_control_limit, 2)}</td>
                    <td>
                      {i.over_ucl ? <span className="chip danger">yes</span>
                                  : <span className="chip neutral">no</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {exc.ucl_rule && (
            <div className="muted small" style={{ marginTop: 8 }}>
              <strong>UCL</strong> — {exc.ucl_rule}
            </div>
          )}
          {(exc.compliance_status || exc.compliance_note) && (
            <div className="banner warn" style={{ marginTop: 10 }}>
              {exc.compliance_status}. {exc.compliance_note}
            </div>
          )}
        </>
      )}

      {/* Containment saturates, and the UI must say so rather than looking
          unresponsive when raising the bleed stops changing the answer. */}
      {r?.containment && !compact && (
        <div className="muted small" style={{ marginTop: 10 }}>
          Containment efficiency <b>{fmt(r.containment.eta, 3)}</b>
          {r.containment.saturated && " — saturated: more bleed cannot capture more"}.
          Holds only while operating ({fmt(r.containment.operating_years, 0)} yr);
          {" "}{fmt(r.containment.post_closure_years, 0)} yr of this run are post-closure,
          when it no longer applies.
        </div>
      )}

      {r?.restoration?.rebound_floor_note && !compact && (
        <div className="banner" style={{ marginTop: 8 }}>
          <strong>After restoration.</strong> {r.restoration.rebound_floor_note}
        </div>
      )}
    </>
  );
}

/** Bearing to a compass point, for readers who do not think in degrees. */
function compass(deg: number): string {
  const pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return pts[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}
