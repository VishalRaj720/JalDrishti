"""
ml_pipeline.dashboard.isr_excursion  --  the REGULATORY excursion test
=====================================================================
Fix R-1 (2026-08-10). Until now the tool answered one question at the
monitoring ring: *"is the BIS/WHO health limit exceeded?"* That is a real and
useful question, but it is **not** how an in-situ-recovery operation detects an
excursion, and the difference changes which species matters and when the alarm
fires.

US NRC NUREG-1569, "Standard Review Plan for In Situ Leach Uranium Extraction
License Applications", Section 5.7.8.3:

  p.138  "An excursion is defined to occur whenever TWO OR MORE excursion
          indicators in a monitoring well exceed their upper control limits."
  p.137  "A minimum of three excursion indicators should be proposed."
          Indicators must be "strong indicators of the in situ leach process and
          ... NOT SIGNIFICANTLY ATTENUATED by geochemical reactions".
          "Conductivity, which is correlated to total dissolved solids, is also
           [used]."
  p.137  "URANIUM IS NOT CONSIDERED A GOOD EXCURSION INDICATOR because, although
          it is mobilized by in situ leaching, IT MAY BE RETARDED by reducing
          conditions in the aquifer."
  p.137  "The use of SULFATE may give FALSE ALARMS because of induced oxidation
          around a monitor well ... However, this should only be a problem if
          upper control limit values are set too conservatively."

The regulator's stated reason for rejecting uranium is exactly what this model
measures from first principles and independently: fractured uranium carries
beta_eff ~ 700 of dual-porosity retardation plus first-order redox trapping, so
its excursion probability collapses toward zero while the conservative species
retain meaningful values. The tool was leading with the one indicator the
regulator explicitly tells licensees not to lead with.

WHAT THIS MODULE DOES NOT CLAIM
-------------------------------
A licensed programme uses at least THREE indicators; this model transports two
of them (TDS as the conductivity proxy NUREG names, and sulfate). Chloride and
total alkalinity are not modelled species -- there is no ISR source term for
them in the Texas sheets in the form this engine needs. So the panel is short of
the regulatory minimum and the result is reported as `panel_shortfall`, never
silently as if a full programme had been simulated.
"""
from __future__ import annotations

from ml_pipeline.config import parameters as P


def _ring_concentration(payload: dict, species: str, ring_m: float) -> dict:
    """Deterministic plume-attributable concentration at the monitor ring.

    Uses the SAME resolve -> feature-row -> Domenico path the served analytical
    answer uses, so an indicator reading can never disagree with the plume the
    map is drawing. No Monte-Carlo: the indicator test is a threshold check on
    the central estimate, and the ML bands carry the uncertainty separately.
    """
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import features_from_inputs
    from ml_pipeline.physics.transport import (params_from_features,
                                               concentration_point)
    sp_payload = dict(payload)
    sp_payload["species"] = species
    inputs, _hydro = resolve_inputs(sp_payload)
    _X, feat, _Xc = features_from_inputs(**inputs)
    rest_days = float(inputs.get("restoration_years", 0.0) or 0.0) * 365.0
    params = params_from_features(
        feat, species_C0=inputs["source_conc_C0"],
        t_days=inputs["time_years"] * 365.0,
        operation_days=inputs["operation_years"] * 365.0,
        restoration_days=rest_days,
        residual_fraction=feat.get("_residual_endpoint", 1.0))
    plume = concentration_point(float(ring_m), 0.0, params)
    baseline = float(inputs["background_conc_Cb"])
    return {
        "species": species,
        "unit": P.SPECIES_UNITS[species],
        "baseline": baseline,
        "lixiviant_C0": float(inputs["source_conc_C0"]),
        # ABSOLUTE reading at the well, which is what a sampler measures
        "ring_conc": float(plume) + baseline,
        "plume_increment": float(plume),
    }


def isr_indicator_excursion(payload: dict,
                            ring_m: float | None = None,
                            ucl_increase: float | None = None) -> dict:
    """NUREG-1569 2-of-N indicator excursion test at the perimeter monitor ring.

    payload: the /api/predict request dict (species is overridden per indicator).
    ring_m:  distance down-gradient of the wellfield EDGE; defaults to the
             served compliance ring.
    """
    ring = float(P.COMPLIANCE_BUFFER_M if ring_m is None else ring_m)
    inc = P.ISR_UCL_BASELINE_INCREASE if ucl_increase is None else float(ucl_increase)

    indicators, n_over = [], 0
    for sp in P.ISR_EXCURSION_INDICATORS:
        try:
            r = _ring_concentration(payload, sp, ring)
        except Exception as e:                       # never break the main answer
            indicators.append({"species": sp, "status": f"unavailable: {e}"})
            continue
        ucl = P.isr_upper_control_limit(r["baseline"], r["lixiviant_C0"], inc)
        over = bool(r["ring_conc"] >= ucl) if ucl == ucl and ucl != float("inf") else False
        n_over += int(over)
        r.update({
            "upper_control_limit": (None if ucl == float("inf") else round(ucl, 3)),
            "over_ucl": over,
            # so a reader can re-apply their own UCL without re-running anything
            "ring_over_baseline_ratio": (round(r["ring_conc"] / r["baseline"], 4)
                                         if r["baseline"] > 0 else None),
            "baseline": round(r["baseline"], 3),
            "ring_conc": round(r["ring_conc"], 3),
            "plume_increment": round(r["plume_increment"], 4),
            "lixiviant_C0": round(r["lixiviant_C0"], 1),
        })
        indicators.append(r)

    n_available = sum(1 for i in indicators if "status" not in i)
    declared = n_over >= P.ISR_EXCURSION_MIN_INDICATORS
    shortfall = n_available < P.ISR_EXCURSION_REQUIRED_PANEL
    return {
        "excursion_declared": declared,
        "indicators_over_ucl": n_over,
        "indicators_required": P.ISR_EXCURSION_MIN_INDICATORS,
        "indicators_available": n_available,
        "rule": (f"{P.ISR_EXCURSION_MIN_INDICATORS}-of-{n_available}: an "
                 f"excursion is declared when {P.ISR_EXCURSION_MIN_INDICATORS} "
                 f"or more indicators exceed their upper control limits"),
        "indicators": indicators,
        "indicator_rationale": dict(P.ISR_INDICATOR_RATIONALE),
        "monitor_ring_m": round(ring, 1),
        "ucl_rule": (f"baseline x (1 + {inc:g}), bracketed to stay above baseline "
                     f"and below the lixiviant concentration (NUREG-1569 p.138)"),
        "ucl_rule_is_scenario_assumption": True,
        "panel_shortfall": shortfall,
        "panel_note": (
            f"NUREG-1569 p.137 asks for a minimum of "
            f"{P.ISR_EXCURSION_REQUIRED_PANEL} indicators; this model carries "
            f"{n_available}." if shortfall else None),
        # Candidate indicators left out ON PURPOSE, each with its measured reason
        # -- so an absent parameter reads as a decision, not an oversight.
        "indicators_excluded": dict(P.ISR_INDICATORS_EXCLUDED),
        "excluded_species": dict(P.ISR_NON_INDICATORS),
        "sampling_interval_days": P.MONITOR_SAMPLING_INTERVAL_DAYS,
        "citation": ("US NRC NUREG-1569 Sec. 5.7.8.3 pp.137-139 "
                     "(excursion definition, indicator selection, UCL bracket)"),
        # NON-NEGOTIABLE FRAMING. A full three-indicator panel makes this test
        # STRUCTURALLY like a licensed one; it does not make it a licensed one,
        # and the difference must not be allowed to blur as the panel fills out.
        "compliance_status": "NUREG-1569-INSPIRED SCREENING — NOT REGULATORY-COMPLIANT",
        "compliance_note": (
            "This implements the NUREG-1569 excursion CRITERION. It is not a "
            "licensed monitoring programme and must not be described as one. "
            "Missing: (1) per-well TEMPORAL baselines — the CGWB file holds 397 "
            "wells with one sample each from a single year, so NUREG's preferred "
            "statistical UCL rules (mean + 5sd, student's t, ASTM D6312) cannot "
            "be computed and the permitted percentage-over-baseline fallback is "
            "used instead, with the percentage itself a scenario assumption; "
            "(2) the verification-resampling protocol (NUREG p.140 requires a "
            "second and third confirming sample before declaring); (3) the "
            "60-day controllability demonstration; (4) an actual wellfield — no "
            "ISR operation has ever existed in Jharkhand."),
    }
