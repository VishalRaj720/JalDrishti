"""synth.py — the "ISR-in-Jharkhand" counterfactual generator.

There is NO operating ISR mine in Jharkhand, so local ISR ground truth cannot
exist. These rows answer the project's actual question — *what if* a uranium ISR
field operated in Jharkhand — by combining:

  * REAL Jharkhand spatial context + aquifer hydrogeology   (sources.load_aquifers)
  * REAL Texas ISR per-phase contaminant levels             (sources.load_texas)
  * REAL Texas mine-operation ranges (flow rate, ore grade) (sources.load_mine_ops)
  * a transparent advection/decay coupling                  (this file)

Every row produced here is tagged `data_source == "synthetic"`. The physics is
deliberately simple and auditable (exponential distance decay, K-amplified plume
length, seasonal dilution) rather than a black-box solver.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from pipeline import SEED
from pipeline import schema as S
from pipeline import sources as src


# Sampling regions: bias toward the East Singhbhum uranium belt (Jaduguda),
# the only place a uranium ISR field would plausibly be sited in Jharkhand,
# while still covering the wider state so the model sees varied hydrogeology.
_BELT = {"lat": (22.45, 22.95), "lon": (86.05, 86.65)}          # E. Singhbhum
_STATE = {"lat": (22.0, 25.3), "lon": (83.4, 87.9)}            # all Jharkhand
_BELT_FRACTION = 0.6


def _phase_logparams(tx: pd.DataFrame, col: str) -> Dict[str, Tuple[float, float]]:
    """Per-phase (log-mean, log-std) for a positive contaminant column."""
    out = {}
    for phase, g in tx.groupby("phase"):
        v = pd.to_numeric(g[col], errors="coerce").dropna()
        v = v[v > 0]
        if len(v) >= 3:
            lv = np.log(v)
            out[phase] = (float(lv.mean()), float(max(lv.std(), 0.3)))
    return out


def _sample_locations(n: int, rng: np.random.Generator) -> np.ndarray:
    belt = rng.random(n) < _BELT_FRACTION
    lat = np.where(belt, rng.uniform(*_BELT["lat"], n), rng.uniform(*_STATE["lat"], n))
    lon = np.where(belt, rng.uniform(*_BELT["lon"], n), rng.uniform(*_STATE["lon"], n))
    return np.column_stack([lon, lat])


def generate(n_per_phase: int = 1000, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    tx = src.load_texas()
    ops = src.load_mine_ops()
    aq = src.load_aquifers()
    jh = src.load_jharkhand()
    ambient_u = jh["uranium_ppb"].dropna().to_numpy()        # real ambient pool
    ambient_tds = jh["tds_mg_l"].dropna().to_numpy()
    ambient_so4 = jh["sulfate_mg_l"].dropna().to_numpy()

    u_p = _phase_logparams(tx, "uranium_ppb")
    tds_p = _phase_logparams(tx, "tds_mg_l")
    so4_p = _phase_logparams(tx, "sulfate_mg_l")
    ph_by_phase = tx.groupby("phase")["ph"].median().to_dict()

    rate_med = ops.rate_dist[0]
    grade_med = ops.grade_dist[0]

    # Only the ISR-perturbation states are synthesised. The "baseline" class is
    # covered by REAL data (Jharkhand ambient + Texas pre-mining), so we never
    # fabricate a baseline — that would be inventing observable data.
    synth_phases = ["mining", "post"]
    # Distance regime per phase (km). We sample distance UNIFORMLY across the
    # plume's reach (not clustered at the source) so the model learns the full
    # uranium-vs-distance decay curve — the core thing the project must predict.
    dist_cfg = {"mining": (0.1, 20.0), "post": (0.2, 30.0)}
    # Coarse time stamp per phase (days since injection start)
    days_cfg = {"mining": (120, 700), "post": (900, 2200)}

    frames = []
    for phase in synth_phases:
        n = n_per_phase
        xy = _sample_locations(n, rng)
        recs = [aq.lookup(lon, lat) for lon, lat in xy]
        ar = pd.DataFrame(recs)

        # ISR scenario from REAL Texas operation ranges (lognormal-ish, clipped)
        inj = np.clip(rng.normal(*ops.rate_dist, n), 200, 2500)
        grade = np.clip(rng.normal(*ops.grade_dist, n), 0.03, 0.30)

        dlo, dhi = dist_cfg[phase]
        dist = rng.uniform(dlo, dhi, n)
        days = rng.uniform(*days_cfg[phase], n)
        month = rng.integers(1, 13, n)
        season = np.array([S.month_to_season(int(m)) for m in month])

        K = pd.to_numeric(ar["aquifer_hydraulic_conductivity_mday"], errors="coerce") \
            .fillna(2.0).to_numpy()
        K_med = np.nanmedian(K) if np.isfinite(np.nanmedian(K)) else 2.0

        # --- source strength at the injection point (distance 0) ---
        def _src(params, fallback_pool):
            if phase in params:
                m, s = params[phase]
                return np.exp(rng.normal(m, s, n))
            return rng.choice(fallback_pool, n)

        u_src = _src(u_p, ambient_u)
        tds_src = _src(tds_p, ambient_tds)
        so4_src = _src(so4_p, ambient_so4)

        # ore grade & injection rate amplify the uranium source term
        u_src = u_src * (grade / grade_med) ** 0.5 * (inj / rate_med) ** 0.3

        # --- ambient (clean) background to decay toward ---
        u_amb = rng.choice(ambient_u, n)
        tds_amb = rng.choice(ambient_tds, n)
        so4_amb = rng.choice(ambient_so4, n)

        # --- exponential distance decay; plume length scales with sqrt(K) ---
        L = 3.0 * np.sqrt(np.maximum(K, 0.1) / K_med)        # km e-folding length
        decay = np.exp(-dist / L)

        def _mix(src_arr, amb_arr):
            return amb_arr + (src_arr - amb_arr) * decay

        uranium = _mix(u_src, u_amb)
        tds = _mix(tds_src, tds_amb)
        sulfate = _mix(so4_src, so4_amb)

        # seasonal dilution/concentration
        sf = np.where(season == "monsoon", 0.85,
                      np.where(np.isin(season, ["pre_monsoon", "winter"]), 1.12, 1.0))
        uranium *= sf; tds *= sf; sulfate *= sf

        # pH drifts from neutral ambient toward the phase pH near the source
        ph_src = ph_by_phase.get(phase, 7.5)
        ph = 7.5 + (ph_src - 7.5) * decay + rng.normal(0, 0.2, n)

        df = pd.DataFrame({
            "data_source": "synthetic",
            "phase": phase,
            "latitude": xy[:, 1],
            "longitude": xy[:, 0],
            "mine": "",
            "distance_from_isr_km": dist,
            "days_since_injection": days,
            "injection_rate_gpm": inj,
            "ore_grade_pct": grade,
            "aquifer_type": ar["aquifer_type"].values,
            "aquifer_transmissivity_m2day": ar["aquifer_transmissivity_m2day"].values,
            "aquifer_hydraulic_conductivity_mday": ar["aquifer_hydraulic_conductivity_mday"].values,
            "aquifer_porosity": ar["aquifer_porosity"].values,
            "aquifer_specific_yield_pct": ar["aquifer_specific_yield_pct"].values,
            "depth_to_water_m": ar["depth_to_water_m"].values,
            "aquifer_thickness_m": ar["aquifer_thickness_m"].values,
            "rainfall_mm": ar["rainfall_mm"].values,
            "season": season,
            "uranium_ppb": np.clip(uranium, 0, None),
            "tds_mg_l": np.clip(tds, 0, None),
            "sulfate_mg_l": np.clip(sulfate, 0, None),
            "ph": np.clip(ph, 5.5, 9.5),
            "iron_mg_l": np.nan,        # not modelled in the synthetic counterfactual
            "arsenic_ppb": np.nan,
        })
        frames.append(df)

    return pd.concat(frames, ignore_index=True)
