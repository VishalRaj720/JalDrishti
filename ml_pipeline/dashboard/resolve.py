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
from ml_pipeline.data_prep.ore_loader import ore_zone_at
from ml_pipeline.data_prep.flow_field import flow_at
from ml_pipeline.data_prep.strike_field import strike_at, anisotropy_from_variance
from ml_pipeline.ml.dataset import ARTIFACT_DIR

SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
_BG_DEFAULT = {"uranium_ppb": 1.0, "sulfate_mg_l": 20.0, "tds_mg_l": 300.0}

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
    kd_lo, kd_central, kd_hi = P.KD_RANGES[species][regime]
    kd = payload.get("kd_L_kg")
    if kd is None:
        kd = kd_central
    beta = payload.get("beta")
    if beta is None:
        beta = (sum(P.DUAL_POROSITY["beta_range"]) / 3.0
                if regime in P.DUAL_POROSITY["enabled_for"] else 0.0)

    # source signature (Texas-derived) midpoint; background from nearest well
    c0 = float(np.mean(source_sig[species]))
    cb = b.get(species)
    if cb is None or cb != cb:
        cb = _BG_DEFAULT[species]

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
            c0 = c0 * P.BELT_C0_FRACTION
        elif ore_zone["zone"] == "none":
            c0 = max(float(cb) * P.NON_ORE_U_TRACE_MULT, P.NON_ORE_U_TRACE_FLOOR_PPB)
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
    }
    return inputs, hydro
