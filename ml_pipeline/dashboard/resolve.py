"""
ml_pipeline.dashboard.resolve
===========================
Bridge between the UI payload (pin + sliders) and predict.py's input contract.
Resolves the hydrogeology of the dropped pin from the real aquifer polygon and
the nearest water-quality baseline, then applies slider overrides.
"""
from __future__ import annotations

import functools
import numpy as np

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.jharkhand_loader import (
    load_jharkhand_aquifers, load_jharkhand_water_quality,
    aquifer_at_point, baseline_at_point,
)
from ml_pipeline.data_prep.texas_loader import texas_source_signature

SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
_BG_DEFAULT = {"uranium_ppb": 1.0, "sulfate_mg_l": 20.0, "tds_mg_l": 300.0}


@functools.lru_cache(maxsize=1)
def _assets():
    return (load_jharkhand_aquifers(), load_jharkhand_water_quality(),
            texas_source_signature())


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
        "baseline": {k: (None if (b[k] != b[k]) else round(float(b[k]), 2))
                     for k in SPECIES if k in b},
    }


def resolve_inputs(payload: dict) -> tuple[dict, dict]:
    """(predict_inputs, hydro_display). Slider values override pin defaults."""
    aq, wq, source_sig = _assets()
    lon, lat = float(payload["lon"]), float(payload["lat"])
    species = payload.get("species", "uranium_ppb")
    h = aquifer_at_point(lon, lat, aq)
    b = baseline_at_point(lon, lat, wq)

    regime = payload.get("regime") or h["regime"]
    lithology = h["lithology"]
    n_total = P.TOTAL_POROSITY.get(lithology, P.DEFAULT_TOTAL_POROSITY)

    # Kd / beta: slider override, else regime-central literature value
    kd = payload.get("kd_L_kg")
    if kd is None:
        kd = P.KD_RANGES[species][regime][1]
    beta = payload.get("beta")
    if beta is None:
        beta = (sum(P.DUAL_POROSITY["beta_range"]) / 3.0
                if regime in P.DUAL_POROSITY["enabled_for"] else 0.0)

    # source signature (Texas-derived) midpoint; background from nearest well
    c0 = float(np.mean(source_sig[species]))
    cb = b.get(species)
    if cb is None or cb != cb:
        cb = _BG_DEFAULT[species]

    inputs = dict(
        regime=regime,
        K_m_day=float(payload.get("K_m_day", h["K_m_day"])),
        gradient_i=float(payload.get("gradient_i", 0.005)),
        phi_mobile=float(payload.get("phi_mobile", h["eff_porosity"])),
        n_total=float(n_total),
        grain_density=float(h["grain_density"]),
        kd_L_kg=float(kd),
        beta=float(beta),
        Q_in_m3_day=float(payload.get("injection_rate_m3_day", 2500.0)),
        bleed_fraction=float(payload.get("bleed_percent", 2.0)) / 100.0,
        operation_years=float(payload.get("operation_years", 8.0)),
        wellfield_width_m=float(payload.get("wellfield_width_m", 300.0)),
        thickness_m=float(h["thickness_m"]),
        source_conc_C0=c0,
        background_conc_Cb=float(cb),
        species=species,
        time_years=float(payload.get("time_years", 10.0)),
    )
    hydro = {
        "lithology": lithology, "regime": regime,
        "K_m_day": round(inputs["K_m_day"], 4),
        "phi_mobile": round(inputs["phi_mobile"], 4),
        "thickness_m": round(inputs["thickness_m"], 1),
        "Kd_L_kg": round(inputs["kd_L_kg"], 3),
        "dual_porosity_beta": round(inputs["beta"], 2),
        "source_conc_C0": round(c0, 1),
        "background_conc_Cb": round(inputs["background_conc_Cb"], 2),
        "district": b.get("district"),
    }
    return inputs, hydro
