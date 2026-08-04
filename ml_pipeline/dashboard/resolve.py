"""
ml_pipeline.dashboard.resolve
===========================
Bridge between the UI payload (pin + sliders) and predict.py's input contract.
Resolves the hydrogeology of the dropped pin from the real aquifer polygon and
the nearest water-quality baseline, then applies slider overrides.

Also owns the TRAINING-ENVELOPE check: inputs outside the envelope the deployed
model was trained on are flagged (`envelope_violations`) so the UI can warn
that the ML bands are extrapolating and the conformal guarantee is void there.
"""
from __future__ import annotations

import functools
import json
import numpy as np

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.jharkhand_loader import (
    load_jharkhand_aquifers, load_jharkhand_water_quality,
    aquifer_at_point, baseline_at_point,
)
from ml_pipeline.data_prep.texas_loader import texas_source_signature
from ml_pipeline.data_prep.ore_loader import ore_zone_at, deposit_ore_depth
from ml_pipeline.data_prep.flow_field import flow_at
from ml_pipeline.data_prep.strike_field import strike_at, anisotropy_from_variance
from ml_pipeline.ml.dataset import ARTIFACT_DIR

# Species + background defaults come from the config registry (remediation
# 2026-08-05, review.md finding #9). This module previously declared its OWN
# ML_SPECIES that nothing imported -- the server gates on ml.predict.ML_SPECIES --
# so the dead copy was free to drift from the live one indefinitely.
from ml_pipeline.config.parameters import SPECIES  # noqa: F401

# Data-confidence thresholds (Module 1). Beyond ~20 km the nearest water-quality
# well is a weak proxy; outside all mapped aquifer polygons the K/phi are borrowed.
_FAR_WELL_DEG = 0.18          # ~20 km at Jharkhand latitude
_DEG_TO_KM = 111.0


def _data_confidence(h: dict, b: dict) -> dict:
    """Telemetry on how well-supported a pin is by real data. `level: "low"`
    when the pin fell outside all mapped aquifer polygons OR the nearest
    water-quality well is far (the resolved hydrogeology/baseline is borrowed)."""
    reasons = []
    if h.get("_pip_fallback"):
        reasons.append("outside_mapped_aquifer")
    dd = b.get("dist_deg")
    if dd is not None and dd == dd and dd > _FAR_WELL_DEG:
        reasons.append("nearest_well_far")
    return {
        "level": "low" if reasons else "ok",
        "reasons": reasons,
        "nearest_well_km": (round(float(dd) * _DEG_TO_KM, 1)
                            if dd is not None and dd == dd else None),
    }


@functools.lru_cache(maxsize=1)
def _assets():
    return (load_jharkhand_aquifers(), load_jharkhand_water_quality(),
            texas_source_signature())


@functools.lru_cache(maxsize=1)
def _model_card() -> dict:
    try:
        return json.loads((ARTIFACT_DIR / "model_card.json").read_text())
    except (OSError, ValueError):
        return {}


def _training_envelope() -> dict:
    """The operational envelope the DEPLOYED model was trained on: read from
    the model card when artifacts exist (survives later config widening),
    else the current config ranges."""
    env = _model_card().get("training_envelope")
    if env:
        return {k: tuple(v) for k, v in env.items()}
    return dict(P.OPERATIONAL_RANGES)


def _hydro_support() -> dict:
    """Per-regime (phi_mobile, Rd, K) box the deployed model actually saw."""
    return _model_card().get("hydro_support", {})


def envelope_violations(inputs: dict) -> list[str]:
    """Names of inputs outside the training support (=> ML extrapolation, the
    conformal 80% guarantee is void; the ANALYTICAL engine is still valid).
    Covers both the operational sliders and the resolved HYDROGEOLOGY (P1) --
    a regime override or manual phi/K that lands where no training row exists."""
    env = _training_envelope()
    checks = {
        "injection_rate_m3_day": inputs["Q_in_m3_day"],
        "bleed_fraction": inputs["bleed_fraction"],
        "operation_years": inputs["operation_years"],
        "hydraulic_gradient": inputs["gradient_i"],
        "wellfield_width_m": inputs["wellfield_width_m"],
        "horizon_years": inputs["time_years"],
        # v2: Q_net was sampled as an independent knob -- high Q_in x high
        # bleed combos can exceed its sampled range even when both sliders
        # are individually in range.
        "net_extraction_m3_day": inputs["Q_in_m3_day"] * inputs["bleed_fraction"],
        "restoration_years": inputs.get("restoration_years", 0.0),
        "u_attenuation_k_per_yr": inputs.get("u_attenuation_k_per_yr", 0.0),
    }
    out = []
    for key, val in checks.items():
        lo, hi = env.get(key, (-np.inf, np.inf))
        tol = 1e-9 + 1e-6 * max(abs(lo), abs(hi))
        if val < lo - tol or val > hi + tol:
            out.append(key)

    # P1 hydro-OOD: check the resolved hydrogeology against the per-regime box.
    support = _hydro_support().get(inputs["regime"])
    if support:
        from ml_pipeline.data_prep.feature_engineering import retardation_factor
        Rd = retardation_factor(inputs["kd_L_kg"], inputs["n_total"],
                                inputs["grain_density"], inputs["regime"],
                                inputs["beta"])
        hydro_vals = {"phi_mobile": inputs["phi_mobile"],
                      "retardation_Rd": Rd, "K_m_day": inputs["K_m_day"]}
        for key, val in hydro_vals.items():
            lo, hi = support[key]
            span = max(hi - lo, 1e-9)
            if val < lo - 0.02 * span or val > hi + 0.02 * span:
                out.append(f"hydro:{key}")
    return out


def _belt_c0(base_c0: float, ore_zone: dict, env: tuple,
             apply_grade: bool = True) -> float:
    """Fix 3.6b: source strength for a BELT pin, ramped linearly from the
    NEAREST DEPOSIT's own C0 at its outline down to the flat belt value
    ORE_TAPER_KM away -- so the deposit/belt tier boundary is continuous
    instead of a ~3.3x step.

    The ceiling is the deposit's grade-scaled, envelope-clipped C0 (NOT the raw
    Texas envelope): clipping to the envelope instead let a belt pin 200 m from
    Jaduguda resolve to 21,088 ppb against the deposit's own 13,272 -- the halo
    out-sourcing the ore body. The floor is the unclipped belt fraction, because
    the belt tier is deliberately a WEAKER hypothetical source than the trained
    envelope's lower edge; clipping up to env_lo would erase that.
    """
    belt_flat = base_c0 * float(P.BELT_C0_FRACTION)
    d_km = ore_zone.get("nearest_deposit_km")
    taper = float(P.ORE_TAPER_KM)
    if d_km is None or taper <= 0:
        return belt_flat

    # what the nearest deposit itself would serve (same rule as the deposit tier)
    # apply_grade=False for radium: the UDEPO grade factor encodes URANIUM
    # leachability, not radium supply, so the radium deposit tier passes through
    # unscaled and its halo must ramp from that same unscaled value.
    ceiling = base_c0
    name = ore_zone.get("nearest_deposit")
    if name and apply_grade:
        from ml_pipeline.data_prep.ore_grades import grade_c0_factor
        factor, _ = grade_c0_factor(name)
        ceiling = float(np.clip(base_c0 * factor, env[0], env[1]))
    ceiling = max(ceiling, belt_flat)          # never ramp downward-inverted

    frac = min(max(float(d_km) / taper, 0.0), 1.0)
    return float(belt_flat + (ceiling - belt_flat) * (1.0 - frac))


def _deposit_ore_depth_at(lon: float, lat: float) -> float | None:
    """Representative ore-depth (m) if the pin is inside a surveyed deposit, else None."""
    oz = ore_zone_at(lon, lat)
    return deposit_ore_depth(oz.get("deposit_name")) if oz.get("zone") == "deposit" else None


def pin_info(lon: float, lat: float) -> dict:
    """Hydrogeology + baseline at a pin (for the UI to show + set defaults)."""
    aq, wq, _ = _assets()
    h = aquifer_at_point(lon, lat, aq)
    b = baseline_at_point(lon, lat, wq)
    return {
        "lon": lon, "lat": lat,
        "lithology": h["lithology"], "lithology_detail": h["lithology_detail"],
        "regime": h["regime"], "confinement": h["confinement"],
        "K_m_day": round(float(h["K_m_day"]), 4),
        "phi_mobile": round(float(h["eff_porosity"]), 4),
        "thickness_m": round(float(h["thickness_m"]), 1),
        "T_m2_day": round(float(h["T_m2_day"]), 1) if h["T_m2_day"] == h["T_m2_day"] else None,
        "district": b.get("district"),
        "hco3_mg_l": (None if b.get("hco3_mg_l") != b.get("hco3_mg_l")
                      else round(float(b["hco3_mg_l"]), 1)),
        "baseline": {k: (None if (b[k] != b[k]) else round(float(b[k]), 2))
                     for k in SPECIES if k in b},
        "data_confidence": _data_confidence(h, b),
        # D1 (Stage C): flow defaults so the UI can prefill azimuth/gradient at pin drop
        "flow": flow_at(lon, lat),
        # Polish #2: representative ore-depth for a deposit pin (seeds the slider)
        "ore_depth_suggestion_m": _deposit_ore_depth_at(lon, lat),
    }


def _override(payload: dict, key: str, fallback: float) -> float:
    """Slider override that is None-safe: Pydantic's model_dump() emits
    optional fields as None, which dict.get(key, fallback) would NOT catch."""
    v = payload.get(key)
    return float(v) if v is not None else float(fallback)


def resolve_inputs(payload: dict) -> tuple[dict, dict]:
    """(predict_inputs, hydro_display). Slider values override pin defaults."""
    aq, wq, source_sig = _assets()
    lon, lat = float(payload["lon"]), float(payload["lat"])
    species = payload.get("species", "uranium_ppb")
    h = aquifer_at_point(lon, lat, aq)
    b = baseline_at_point(lon, lat, wq)
    # D1 (Stage B/E2): data-derived flow -> default azimuth / gradient / seasonal
    # amplitude for the pin (overridden by explicit slider values below).
    flow = flow_at(lon, lat)
    # D2 / E1 (Stage H): fracture-strike dispersion -> transverse anisotropy of the
    # plume (fractured only) so the served alpha_T matches the E1-trained model.
    strike = strike_at(lon, lat)

    lithology = h["lithology"]
    natural_regime = h["regime"]
    regime = payload.get("regime") or natural_regime

    # P0-A (regime audit): a regime OVERRIDE that differs from the pin's natural
    # regime is a hypothetical "what if this rock were <regime>?". Transport
    # depends on the MATERIAL, so substitute regime-typical porosity / grain
    # density -- reusing crystalline materials under the porous branch built an
    # unphysical chimera (Rd ~ 635). K and thickness (measured T/b) stay.
    regime_overridden = bool(payload.get("regime")) and regime != natural_regime
    if regime_overridden:
        arch = P.REGIME_ARCHETYPE[regime]
        phi_default = arch["phi_mobile"]
        n_total = arch["n_total"]
        grain_density = arch["grain_density"]
    else:
        phi_default = h["eff_porosity"]
        n_total = P.TOTAL_POROSITY.get(lithology, P.DEFAULT_TOTAL_POROSITY)
        grain_density = float(h["grain_density"])

    # P0-B (regime audit): plume Kd = regime-central literature value, sampled
    # from the SAME KD_RANGES the training generator uses (train == serve). These
    # ranges already encode alkaline-ISR suppression; the ambient-alkalinity
    # helper is NOT applied to the near-field plume (the plume carries its own
    # lixiviant carbonate). Explicit slider overrides still win.
    # Radium sorbs orders of magnitude more strongly than alkaline uranium
    # (divalent Ra2+ across the whole pH range), so it carries its own Kd table.
    kd_lo, kd_central, kd_hi = P.kd_range_for(species, regime)
    kd = payload.get("kd_L_kg")
    if kd is None:
        kd = kd_central
    beta = payload.get("beta")
    if beta is None:
        beta = (sum(P.DUAL_POROSITY["beta_range"]) / 3.0
                if regime in P.DUAL_POROSITY["enabled_for"] else 0.0)

    # source signature (Texas-derived) midpoint; background from nearest well.
    # Radium has no Texas ISR series to transfer from and no radium column in
    # the CGWB water-quality file, so BOTH ends come from the measured Jaduguda
    # / BARC values instead (see parameters.py section 4b for citations).
    if species == "radium_226_mbq_l":
        c0 = float(P.RADIUM_SOURCE_MBQ_L[P.RADIUM_SOURCE_STATISTIC])
        cb = float(P.RADIUM_BACKGROUND_MBQ_L)
    else:
        c0 = float(np.mean(source_sig[species]))
        cb = b.get(species)
        if cb is None or cb != cb:
            cb = P.background_default_for(species)

    # Module 2: ore-body mask. ISR leaches uranium only where uranium ore exists.
    # Clamp the URANIUM source term by zone; sulfate/TDS (lixiviant reagents)
    # are unaffected. `u_suppressed` tells the server to bypass the ML surrogate
    # for uranium (the clamped C0 is far outside the model's training support).
    ore_zone = ore_zone_at(lon, lat)
    u_suppressed = False
    ore_grade_pct = None
    if species == "uranium_ppb":
        if ore_zone["zone"] == "deposit":
            # D4: scale the deposit's C0 by its real ore grade (IAEA UDEPO),
            # clipped to the trained uranium source-signature envelope.
            from ml_pipeline.data_prep.ore_grades import grade_c0_factor
            factor, ore_grade_pct = grade_c0_factor(ore_zone["deposit_name"])
            env_lo, env_hi = min(source_sig[species]), max(source_sig[species])
            c0 = float(np.clip(c0 * factor, env_lo, env_hi))
        elif ore_zone["zone"] == "belt":
            c0 = _belt_c0(c0, ore_zone,
                          (min(source_sig[species]), max(source_sig[species])))
        elif ore_zone["zone"] == "none":
            c0 = max(float(cb) * P.NON_ORE_U_TRACE_MULT, P.NON_ORE_U_TRACE_FLOOR_PPB)
            u_suppressed = True
    elif species == "radium_226_mbq_l":
        # Ra-226 is a decay product of the ore's uranium, so it is ore-zone
        # gated exactly like uranium: no ore body, no radium source. The
        # measured Jaduguda source term already represents a DEPOSIT, so the
        # deposit tier passes through unscaled (no UDEPO grade factor -- the
        # grade scaling encodes uranium leachability, not radium supply).
        if ore_zone["zone"] == "belt":
            # radium: ramp from its own measured (unscaled) deposit value
            c0 = _belt_c0(c0, ore_zone, (0.0, c0), apply_grade=False)
        elif ore_zone["zone"] == "none":
            c0 = float(cb)          # background only -- zero incremental source
            u_suppressed = True

    # D5: Singhbhum shear-zone transmissivity. At a fractured deposit/belt pin the
    # aquifer is far more transmissive than the generic schist polygon (NAQUIM T
    # 207-570 vs ~42) -> replace the served K + thickness with the measured
    # shear-zone values (T and b together so seepage velocity stays physical).
    # Explicit K override wins. K is a trained feature, so no retrain needed.
    k_default = float(h["K_m_day"])
    thickness_default = float(h["thickness_m"])
    shear_zone = None
    if (regime == "fractured" and ore_zone["zone"] in ("deposit", "belt")
            and payload.get("K_m_day") is None):
        k_default = P.SHEAR_ZONE_T_M2DAY / P.SHEAR_ZONE_THICKNESS_M
        thickness_default = P.SHEAR_ZONE_THICKNESS_M
        shear_zone = {"T_m2day": P.SHEAR_ZONE_T_M2DAY,
                      "thickness_m": P.SHEAR_ZONE_THICKNESS_M,
                      "K_m_day": round(k_default, 3),
                      "polygon_K_m_day": round(float(h["K_m_day"]), 3)}

    # Phase-1 fix 3.3: DEPTH-DEPENDENT K. The resolved K above characterises the
    # shallow drinking-water aquifer; the ISR target sits far below it, where
    # crystalline fractures close under load. Decay K from the shallow reference
    # depth to the ore depth using the district's OWN documented fracture-death
    # depth (NAQUIM), then clamp into the deployed model's trained K box so this
    # stays a serve-time correction with no retrain. An explicit K override from
    # the user wins outright (they are stating a measured value).
    k_depth = None
    if payload.get("K_m_day") is None and P.K_DEPTH_DECAY_ENABLED:
        from ml_pipeline.data_prep.naquim_vertical import vertical_params_at
        vp = vertical_params_at(lon, lat)
        ore_depth = _override(payload, "ore_depth_m", P.VERTICAL["ore_depth_default_m"])
        factor = P.depth_decay_factor(ore_depth, vp.get("fracture_max_m"))
        k_shallow = k_default
        k_dec = k_shallow * factor
        # keep the served K inside the trained support so no extrapolation flag
        # is raised by our own correction
        support = _hydro_support().get(regime, {})
        k_lo, k_hi = support.get("K_m_day", (None, None)) if support else (None, None)
        clamped = False
        if k_lo is not None and k_dec < k_lo:
            k_dec, clamped = float(k_lo), True
        k_default = k_dec
        k_depth = {
            "ore_depth_m": round(float(ore_depth), 1),
            "reference_depth_m": P.K_DEPTH_REF_M,
            "fracture_base_m": vp.get("fracture_max_m"),
            "fracture_base_source": ("NAQUIM district report"
                                     if vp.get("fracture_max_m") is not None
                                     else "statewide default"),
            "decay_factor": round(float(factor), 4),
            "K_shallow_m_day": round(float(k_shallow), 4),
            "K_at_depth_m_day": round(float(k_default), 4),
            "clamped_to_trained_min": clamped,
            "strength": P.K_DEPTH_DECAY_STRENGTH,
        }

    inputs = dict(
        regime=regime,
        K_m_day=_override(payload, "K_m_day", k_default),
        gradient_i=_override(payload, "gradient_i", flow["gradient_i"]),
        phi_mobile=_override(payload, "phi_mobile", phi_default),
        n_total=float(n_total),
        grain_density=float(grain_density),
        kd_L_kg=float(kd),
        beta=float(beta),
        Q_in_m3_day=_override(payload, "injection_rate_m3_day", 2500.0),
        bleed_fraction=_override(payload, "bleed_percent", 2.0) / 100.0,
        operation_years=_override(payload, "operation_years", 8.0),
        wellfield_width_m=_override(payload, "wellfield_width_m", 300.0),
        thickness_m=thickness_default,
        source_conc_C0=c0,
        background_conc_Cb=float(cb),
        species=species,
        time_years=_override(payload, "time_years", 10.0),
        restoration_years=_override(payload, "restoration_years", 0.0),
        downtime_fraction=_override(payload, "downtime_fraction", 0.0),
        # D1: effective seasonal amplitude folds in plane-fit / DEM-fallback
        # uncertainty -> wider ML bands on low-confidence cells.
        gradient_seasonal_amp=_override(payload, "gradient_seasonal_amp",
                                        flow["seasonal_amp_effective"]),
        # E1: V-derived transverse anisotropy (fractured); None -> regime default.
        aniso_ratio=(anisotropy_from_variance(strike["circular_variance"])
                     if regime == "fractured" else None),
        # real-ISR upgrade: U redox-trapping rate. Explicit expert override wins;
        # else the ORE-ZONE mineralogy mode (Phase-1 fix 3.5) for uranium /
        # 0 for the conservative species.
        u_attenuation_k_per_yr=_override(
            payload, "u_attenuation_k_per_yr",
            (P.U_ATTENUATION_MODE_BY_ZONE.get(ore_zone["zone"],
                                              P.U_ATTENUATION_K_PER_YR[1])
             if species == "uranium_ppb" else 0.0)),
    )
    # retardation (asymptotic) so the UI can SHOW why a plume is slow (P2)
    from ml_pipeline.data_prep.feature_engineering import retardation_factor
    Rd = retardation_factor(inputs["kd_L_kg"], inputs["n_total"],
                            inputs["grain_density"], regime, inputs["beta"])
    hydro = {
        "lithology": lithology, "regime": regime,
        "natural_regime": natural_regime,
        "regime_overridden": regime_overridden,
        "K_m_day": round(inputs["K_m_day"], 4),
        "phi_mobile": round(inputs["phi_mobile"], 4),
        "n_total": round(inputs["n_total"], 3),
        "thickness_m": round(inputs["thickness_m"], 1),
        "Kd_L_kg": round(inputs["kd_L_kg"], 3),
        "retardation_Rd": round(float(Rd), 1),
        "dual_porosity_beta": round(inputs["beta"], 2),
        "source_conc_C0": round(c0, 1),
        "background_conc_Cb": round(inputs["background_conc_Cb"], 2),
        "hco3_mg_l": (None if b.get("hco3_mg_l") != b.get("hco3_mg_l")
                      else round(float(b["hco3_mg_l"]), 1)),
        "district": b.get("district"),
        "data_confidence": _data_confidence(h, b),
        # Module 2: ore-body zone + whether the uranium source term was clamped
        "ore_zone": ore_zone,
        "u_suppressed": u_suppressed,
        # D4: deposit ore grade (%U) used to scale the uranium C0, if applicable
        "ore_grade_pct_u": ore_grade_pct,
        # D1 (Stage B): data-derived flow at the pin -- default azimuth/gradient,
        # divide flag, fit provenance, and depth-to-water for the map + screening.
        "flow": flow,
        # D2/E1 (Stage H): fracture strike + dispersion (for the display-only
        # tensor rotation of the plume azimuth toward strike).
        "strike": strike,
        # D5: Singhbhum shear-zone transmissivity correction applied (or None).
        "shear_zone": shear_zone,
        # Phase-1 fix 3.3: depth-decay of K from the shallow tested zone to the
        # ore depth (None when the user supplied an explicit K, or if disabled).
        "k_depth": k_depth,
        # Phase-1 fix 3.5: which ore-zone mineralogy set the attenuation mode.
        "u_attenuation_k_per_yr": inputs.get("u_attenuation_k_per_yr"),
        "u_attenuation_basis": (
            f"{ore_zone['zone']} zone mineralogy"
            if species == "uranium_ppb" and payload.get("u_attenuation_k_per_yr") is None
            else ("user override" if payload.get("u_attenuation_k_per_yr") is not None
                  else "n/a (conservative species)")),
        # Phase-1 fix 3.2: measured local source-term reality check. The served
        # C0 is Texas-ISR-derived (active lixiviant); this is what passive mine
        # water contacting the SAME ore body actually measures.
        "source_term_context": ({
            "model_C0_ppb": round(c0, 1),
            "jaduguda_mine_water_ppb": P.JADUGUDA_MINE_WATER_U_PPB,
            "ratio_model_to_measured_gm": round(
                c0 / P.JADUGUDA_MINE_WATER_U_PPB["gm"], 1),
            "note": ("Model C0 represents an engineered ISR lixiviant (Texas-derived, "
                     "the only real ISR source chemistry available). The Jaduguda "
                     "figures are MEASURED passive mine-water effluent from the same "
                     "ore body and act as a lower bound, not a substitute."),
            "citation": P.JADUGUDA_SOURCE_CITATION,
        } if species == "uranium_ppb" else None),
        # fix 3.9: radium provenance -- which measured statistic is being served,
        # the full observed distribution, and the WHO level it is judged against.
        "radium_context": ({
            "served_C0_mbq_l": round(c0, 1),
            "statistic_used": P.RADIUM_SOURCE_STATISTIC,
            "measured_source_mbq_l": P.RADIUM_SOURCE_MBQ_L,
            "background_mbq_l": P.RADIUM_BACKGROUND_MBQ_L,
            "who_guidance_mbq_l": P.EXCURSION_THRESHOLDS["radium_226_mbq_l"],
            "note": ("Source term is MEASURED Jaduguda mine water, not an ISR "
                     "lixiviant (no ISR radium data exists for this ore). The "
                     "geometric mean 371.3 mBq/L lies BELOW the WHO 1000 mBq/L "
                     "level, so the observed maximum is served as the screening "
                     "value; only <1% of ore radium leaches during processing, "
                     "so radium supply is genuinely limited."),
            "citation": P.JADUGUDA_SOURCE_CITATION,
            "kd_citation": ("EPA 402-R-04-002C Vol III Table 5.28 "
                            "(Thibault et al. 1990 compilation)"),
        } if species == "radium_226_mbq_l" else None),
    }
    return inputs, hydro
