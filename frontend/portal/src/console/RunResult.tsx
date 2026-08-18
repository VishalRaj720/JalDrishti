/**
 * The result of an engine run — one renderer for both paths.
 *
 * A live pin run and a stored site run are read from the same component on
 * purpose. Before P2 they had separate presentations: the live path drew a
 * plume and three metric cards, the stored path drew a `Planned` card where the
 * map should have been. Two renderers for one physics is how a product ends up
 * with two different-looking answers to the same question, and a reader has no
 * way to tell which discrepancy is real.
 *
 * `storedRunToPlume` reshapes a persisted run into the live response's shape;
 * everything below this line is then identical for both.
 */
import { SPECIES_UNIT } from "../map/plume";
import { area, distance, fmt } from "./mapLayers";

export default function RunResult({
  r, extrapolation = [], compact = false,
}: { r: any; extrapolation?: string[]; compact?: boolean }) {
  const an = r?.metrics?.analytical;
  const ml = r?.metrics?.ml;
  const unit = SPECIES_UNIT[r?.species] ?? "";
  const exc = r?.isr_excursion;

  return (
    <>
      {/* §4.5 rule 2 — extrapolation is loud. */}
      {extrapolation.length > 0 && (
        <div className="banner warn" style={{ marginTop: 10 }}>
          <strong>Outside trained support:</strong>{" "}
          <span className="mono">{extrapolation.join(", ")}</span>. The analytical
          engine remains valid and is serving; the ML band's 80% conformal
          guarantee is <b>void</b> here — treat it as indicative only.
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
        </div>
      )}

      {r?.far_field_note && (
        <div className="banner" style={{ marginTop: 10 }}>{r.far_field_note}</div>
      )}

      <div className="sec">Result</div>
      <div className="metric-row">
        <div className="metric danger">
          <div className="m-label">Contaminated footprint</div>
          <div className="m-value">
            {area(an?.area_ha).text} <span className="m-unit">{area(an?.area_ha).unit}</span>
          </div>
          <div className="m-band">
            {ml?.area_ha
              ? `ML P10–P90 ${fmt(ml.area_ha.p10)} – ${fmt(ml.area_ha.p90)}`
              : r?.ml_status ?? "analytical only — no band"}
          </div>
        </div>
        <div className="metric">
          <div className="m-label">Max migration</div>
          <div className="m-value">
            {distance(an?.migration_m).text}{" "}
            <span className="m-unit">{distance(an?.migration_m).unit}</span>
          </div>
          <div className="m-band">
            {ml?.migration_m
              ? `ML P10–P90 ${fmt(ml.migration_m.p10)} – ${fmt(ml.migration_m.p90)}`
              : r?.ml_status ?? "analytical only — no band"}
          </div>
        </div>
        <div className="metric">
          <div className="m-label">At the monitoring ring</div>
          <div className="m-value">
            {fmt(an?.compliance_conc, 3)} <span className="m-unit">{unit}</span>
          </div>
          <div className="m-band">
            {ml?.compliance_conc
              ? `ML P10–P90 ${fmt(ml.compliance_conc.p10, 3)} – ${fmt(ml.compliance_conc.p90, 3)}`
              : r?.ml_status ?? "analytical only — no band"}
          </div>
        </div>
      </div>

      {/* The footprint is overwhelmingly the leach disc, not migrating plume.
          §4.5 rule 4 requires the split be shown rather than letting one number
          be read as "how far the contamination spread". */}
      {r?.plume?.source_zone?.area_ha != null && an?.area_ha > 0 && (
        <div className="muted small" style={{ marginTop: 6 }}>
          Of that footprint, <b>{fmt(r.plume.source_zone.area_ha)} ha</b> is the leach
          zone itself — ground the operation deliberately swept — and the remainder is
          migrating plume.
          {r.plume.radial_dominated && (
            <> The source disc dominates here, so “migration” reads as contaminated
               <b> extent</b>, not travel distance.</>
          )}
        </div>
      )}

      {exc && !compact && (
        <>
          <div className="sec">
            ISR excursion — NUREG-1569-inspired screening
          </div>
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
    </>
  );
}
