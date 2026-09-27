"""
ml_pipeline.physics.injectivity  --  can the requested rate be injected at all?
==============================================================================
2026-09-27 (P.INJECTIVITY; docs/GEMINI_REVIEW_ASSESSMENT.md Issue 4).

The engine takes the injection rate as an operating input independent of the
rock. In the measured rock at the deposits (ore-zone K 0.03-0.06 m/day) a
production rate may need more pressure than the rock can take before it
fractures -- and US Class III rules forbid injection that initiates or
propagates fractures (40 CFR 146.33(a)(1)). This module says which, and never
changes a modelled number: it is a feasibility read-out beside the answer.

Head rise at an injector of a repeated five-spot pattern (Muskat 1937):
    dh = Q_w / (pi K b) * [ln(d / r_w) - 0.619]
with d the injector-producer distance, N = pi (W/2)^2 / (2 d^2) injectors over
the pattern footprint, Q_w = Q / N. Headroom before fracture initiation: the
minimum principal stress k * sigma_v, less the hydrostatic pore pressure,
in metres of water. The stress regime is not measured at any deposit, so k is
a range (P.INJECTIVITY) and the verdict is feasible / marginal / infeasible.
"""
from __future__ import annotations

import math

from ml_pipeline.config import parameters as P


def _head_rise(Q_w: float, K: float, b: float, d: float, r_w: float) -> float:
    return Q_w / (math.pi * max(K, 1e-12) * max(b, 1e-6)) * (math.log(d / r_w) - 0.619)


def injectivity_check(*, K_ore_m_day: float, ore_thickness_m: float,
                      Q_in_m3_day: float, wellfield_width_m: float,
                      ore_depth_m: float, water_table_m: float | None = None) -> dict:
    cfg = P.INJECTIVITY
    r_w = float(cfg["well_radius_m"])
    wt = float(water_table_m) if water_table_m is not None else 5.0
    area = math.pi * (float(wellfield_width_m) / 2.0) ** 2
    patterns = []
    for d in cfg["pattern_spacing_m"]:
        n = max(1, int(round(area / (2.0 * d * d))))
        q_w = float(Q_in_m3_day) / n
        patterns.append({"spacing_m": d, "injectors": n,
                         "rate_per_injector_m3_day": round(q_w, 1),
                         "head_rise_m": round(_head_rise(q_w, K_ore_m_day,
                                                         ore_thickness_m, d, r_w), 1)})
    rise_lo = min(p["head_rise_m"] for p in patterns)
    rise_hi = max(p["head_rise_m"] for p in patterns)

    z = float(ore_depth_m)
    sigma_v_head = cfg["rock_density_kg_m3"] / 1000.0 * z   # m of water
    hydro_head = max(z - wt, 0.0)
    k_lo, k_hi = cfg["sigma_min_over_sigma_v"]
    room_lo = max(k_lo * sigma_v_head - hydro_head, 0.0)
    room_hi = max(k_hi * sigma_v_head - hydro_head, 0.0)

    if rise_hi <= room_lo:
        verdict = "feasible"
    elif rise_lo > room_hi:
        verdict = "infeasible"
    else:
        verdict = "marginal"
    # the largest total rate the densest pattern could take without reaching
    # the LOW end of the fracture headroom (the precautionary limit)
    d0 = min(cfg["pattern_spacing_m"])
    n0 = max(1, int(round(area / (2.0 * d0 * d0))))
    per_unit = _head_rise(1.0, K_ore_m_day, ore_thickness_m, d0, r_w)
    q_max = n0 * room_lo / per_unit if per_unit > 0 else float("inf")
    msg = {
        "feasible": "the requested rate can be injected below fracture pressure",
        "marginal": ("the requested rate is near the fracture pressure: it may be "
                     "injectable with many closely spaced wells, or may need "
                     "pressures that fracture the rock"),
        "infeasible": ("the requested rate cannot be injected without fracturing "
                       "the rock -- the measured-rock answer then describes "
                       "lixiviant in place, not a production wellfield"),
    }[verdict]
    return {
        "verdict": verdict,
        "message": msg,
        "requested_rate_m3_day": round(float(Q_in_m3_day), 1),
        "max_rate_below_fracture_m3_day": round(q_max, 1),
        "head_rise_range_m": [rise_lo, rise_hi],
        "fracture_headroom_range_m": [round(room_lo, 1), round(room_hi, 1)],
        "patterns": patterns,
        "K_ore_m_day": round(float(K_ore_m_day), 4),
        "ore_thickness_m": round(float(ore_thickness_m), 1),
        "basis": ("Muskat five-spot head rise against fracture-initiation headroom "
                  f"(sigma_min = {k_lo:g}-{k_hi:g} x sigma_v; not measured at any "
                  "deposit)"),
        "display_only": True,
        "citation": cfg["citation"],
    }
