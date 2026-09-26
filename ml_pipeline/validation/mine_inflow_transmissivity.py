"""
ml_pipeline.validation.mine_inflow_transmissivity
=================================================
What bulk transmissivity do the Singhbhum mines' own pumping records allow, and
where does the engine's served hydrogeology sit against it?
[grounding pass 2026-09-26, LIMITATIONS.md 1k]

A dewatered underground mine is a pumping test at the scale of a square
kilometre, run for decades. UCIL's 2017 pre-feasibility reports (public, on
environmentclearance.nic.in; copies in Datasets/ucil_reference/) give:

  Narwapahar  "2700 m3/d of water is discharged from the mine"; developed to
              380 m (6th level).
  Turamdih    "3170 m3/day will be met by mine discharge water" -- so the mine
              discharges at least that; working levels 60-230 m bgl, shaft
              bottom 260 m.

Steady Thiem flow to an equivalent large well gives

    T = Q ln(R / r_e) / (2 pi s)

swept over every plausible geometry: ln(R/r_e) from 0.7 to 2.3 (R = 2x to 10x
the workings' equivalent radius) and drawdown s from half to all of the drained
column (water table ~5 m bgl; Kudada's static level is 2.4 m). The pumped water
also carries stowing, drilling and rain water, so the natural inflow -- and every
T below -- is an UPPER bound.

Against that the script puts:
  * the shear-zone baseline T (Kudada EW, P.SHEAR_ZONE_T_M2DAY),
  * the engine's own K(z) column at each mine, integrated over the drained
    depth -- the bulk T the served hydrogeology implies there,
  * the discharge a given T would force, for the old 370 m2/day value.

    python -m ml_pipeline.validation.mine_inflow_transmissivity
writes validation/mine_inflow_transmissivity.json;
tests/test_grounded_baselines.py re-derives it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ml_pipeline.config import parameters as P

OUT_JSON = Path(__file__).with_suffix(".json")

WATER_TABLE_M = 5.0
LN_R_OVER_RE = (0.7, 1.4, 2.3)

MINES = {
    "Turamdih": {
        "discharge_m3_day": 3170.0, "discharge_is_lower_bound": True,
        "deepest_drained_m": 260.0,
        "quote": ("Water requirement will be 3430 m3/day out of which 3170 m3/day "
                  "will be met by mine discharge water"),
        "source": ("UCIL, Pre-Feasibility Report, Turamdih Mine augmentation to "
                   "0.75 MTPA (2017), secs. 1.0 and 3.8.1; levels 60-230 m bgl, "
                   "main shaft bottom 260 m (sec. 3.5.3)"),
    },
    "Narwapahar": {
        "discharge_m3_day": 2700.0, "discharge_is_lower_bound": False,
        "deepest_drained_m": 380.0,
        "quote": "2700 m3/d of water is discharged from the mine",
        "source": ("UCIL, Pre-Feasibility Report, Narwapahar Mine expansion to 0.6 "
                   "MTPA (2017), sec. 3.7; developed to 380 m (sec. 1.0)"),
    },
}


def thiem_T(q: float, ln_ratio: float, s: float) -> float:
    return q * ln_ratio / (2.0 * math.pi * s)


def mine_bounds(m: dict) -> dict:
    s_full = m["deepest_drained_m"] - WATER_TABLE_M
    s_half = 0.5 * s_full
    lo = thiem_T(m["discharge_m3_day"], LN_R_OVER_RE[0], s_full)
    mid = thiem_T(m["discharge_m3_day"], LN_R_OVER_RE[1], 0.75 * s_full)
    hi = thiem_T(m["discharge_m3_day"], LN_R_OVER_RE[2], s_half)
    return {"bulk_T_m2day": [round(lo, 2), round(mid, 2), round(hi, 2)],
            "drawdown_m": [round(s_half, 1), round(s_full, 1)]}


def model_column_T(deposit: str, deepest_m: float) -> dict:
    """Bulk T of the engine's served K(z) at a deposit, integrated from the water
    table down the drained column (the shear-zone reference K, decayed with the
    deposit's own fracture base -- what a run there serves)."""
    from ml_pipeline.dashboard.resolve import shear_zone_reference
    from ml_pipeline.data_prep.groundwater_baselines import _deposit_centres
    from ml_pipeline.data_prep.naquim_vertical import fracture_base_at
    lon, lat = _deposit_centres()[deposit]
    fb = float(fracture_base_at(lon, lat)["fracture_base_m"])
    k_ref = shear_zone_reference()["K_reference_m_day"]
    zs = np.linspace(WATER_TABLE_M, deepest_m, 2001)
    fz = np.array([P.depth_decay_factor(z, fb) for z in zs])
    integral = float(np.sum(0.5 * (fz[1:] + fz[:-1]) * np.diff(zs)))
    return {"K_reference_m_day": round(k_ref, 4), "fracture_base_m": round(fb, 1),
            "column_T_m2day": round(k_ref * integral, 2)}


def forced_discharge(T: float, drawdown_m: float = 55.0,
                     ln_ratio: float = LN_R_OVER_RE[-1]) -> float:
    """Discharge a bulk T would force at Turamdih in the GENEROUS case: only the
    first working level (60 m) drained, the widest cone (ln R/r_e = 2.3)."""
    return 2.0 * math.pi * T * drawdown_m / ln_ratio


def run() -> dict:
    out = {"method": ("Thiem, T = Q ln(R/r_e) / (2 pi s), swept over ln(R/r_e) "
                      f"{LN_R_OVER_RE[0]}-{LN_R_OVER_RE[-1]} and drawdown from half "
                      f"to all of the drained column below a {WATER_TABLE_M:g} m "
                      "water table; every T is an upper bound"),
           "mines": {}}
    for name, m in MINES.items():
        b = mine_bounds(m)
        col = model_column_T(name, m["deepest_drained_m"])
        out["mines"][name] = {**m, **b, "engine_column": col,
                              "engine_column_over_mine_upper_bound": round(
                                  col["column_T_m2day"] / b["bulk_T_m2day"][2], 2)}
    q_turamdih = MINES["Turamdih"]["discharge_m3_day"]
    out["forced_discharge_turamdih"] = {
        f"{T:g}": {"m3_day": round(forced_discharge(T)),
                   "times_reported": round(forced_discharge(T) / q_turamdih, 1)}
        for T in (P.SHEAR_ZONE_T_M2DAY, 101.0, 370.0)}
    out["baseline_T_m2day"] = P.SHEAR_ZONE_T_M2DAY
    out["reading"] = (
        "The mines bound the bulk transmissivity of the shear zone around the ore "
        "at single digits of m2/day. The served baseline (Kudada, 19) sits above "
        "that bound -- the measured maximum is the conservative side of the mine "
        "data -- and the retired 370 would have forced ~17x the discharge UCIL "
        "reports even in the most generous geometry.")
    return out


def main() -> None:
    res = run()
    OUT_JSON.write_text(json.dumps(res, indent=2))
    for name, m in res["mines"].items():
        print(f"{name:11s} Q={m['discharge_m3_day']:6.0f}  bulk T (upper bound) "
              f"{m['bulk_T_m2day']}  engine column T {m['engine_column']['column_T_m2day']}"
              f"  ({m['engine_column_over_mine_upper_bound']}x the bound)")
    for T, v in res["forced_discharge_turamdih"].items():
        print(f"  T={T:>5s} would force {v['m3_day']:>7d} m3/day = {v['times_reported']}x reported")
    print(f"-> {OUT_JSON}")


if __name__ == "__main__":
    main()
