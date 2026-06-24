"""build.py — assemble the single unified dataset.

    texas_real      real Texas ISR chemistry (the uranium target signal)
  + jharkhand_real  real CGWB ambient uranium + chemistry (local baseline)
  + synthetic       ISR-in-Jharkhand counterfactual (mining/post only)
  -> artifacts/unified_dataset.csv   (one schema, uranium in ppb, provenance tagged)

Run:  python -m pipeline.build
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import ARTIFACTS_DIR, SEED
from pipeline import schema as S
from pipeline import sources as src
from pipeline import synth

# Texas ISR is hosted in Frio-Formation sandstone; use sandstone-typical
# hydrogeology for the Texas rows (ore porosity is overridden with the real
# AquiferExemptions value per mine where available).
_TX_SANDSTONE = {
    "aquifer_type": "sandstone",
    "aquifer_transmissivity_m2day": 150.0,
    "aquifer_hydraulic_conductivity_mday": 5.0,
    "aquifer_porosity": 0.18,
    "aquifer_specific_yield_pct": 15.0,
    "depth_to_water_m": 20.0,
    "aquifer_thickness_m": 30.0,
    "rainfall_mm": 720.0,
}
# Phase-imputed distance regime (km) for Texas wells (no per-well distance in
# the source); mirrors synth.dist_cfg so real and synthetic rows are comparable.
_TX_DIST = {"baseline": (np.log(9.0), 0.6, 0.5, 30.0),
            "mining":   (np.log(0.8), 0.6, 0.1, 6.0),
            "post":     (np.log(2.5), 0.7, 0.2, 15.0)}
_TX_DAYS = {"baseline": (0, 30), "mining": (120, 700), "post": (900, 2200)}


def _build_texas(rng: np.random.Generator) -> pd.DataFrame:
    ops = src.load_mine_ops()
    tx = src.attach_mine_ops(src.load_texas(), ops)
    n = len(tx)
    out = tx.copy()

    for col, val in _TX_SANDSTONE.items():
        out[col] = val
    # real ore porosity (%) -> fraction, where the mine matched the ops table
    op = tx["_ore_porosity_pct"] / 100.0
    out["aquifer_porosity"] = op.where(op.notna(), _TX_SANDSTONE["aquifer_porosity"])

    # phase-imputed distance + time
    dist = np.empty(n); days = np.empty(n)
    for ph, (mu, sig, lo, hi) in _TX_DIST.items():
        m = (tx["phase"] == ph).to_numpy()
        if m.any():
            dist[m] = np.clip(rng.lognormal(mu, sig, m.sum()), lo, hi)
            days[m] = rng.uniform(*_TX_DAYS[ph], m.sum())
    out["distance_from_isr_km"] = dist
    out["days_since_injection"] = days

    # injection rate: 0 at baseline (no operation yet), else matched or sampled
    inj = tx["injection_rate_gpm"].to_numpy(dtype=float)
    samp = np.clip(rng.normal(*ops.rate_dist, n), 200, 2500)
    inj = np.where(np.isnan(inj), samp, inj)
    inj[(tx["phase"] == "baseline").to_numpy()] = 0.0
    out["injection_rate_gpm"] = inj

    grade = tx["ore_grade_pct"].to_numpy(dtype=float)
    gsamp = np.clip(rng.normal(*ops.grade_dist, n), 0.03, 0.30)
    out["ore_grade_pct"] = np.where(np.isnan(grade), gsamp, grade)

    month = rng.integers(1, 13, n)
    out["season"] = [S.month_to_season(int(m)) for m in month]
    return out


def _build_jharkhand(rng: np.random.Generator) -> pd.DataFrame:
    aq = src.load_aquifers()
    jh = src.enrich_with_aquifer(src.load_jharkhand(), aq)
    n = len(jh)
    # ambient baseline: no ISR nearby -> far distance, no injection, no ore
    jh["distance_from_isr_km"] = np.clip(rng.normal(35, 10, n), 15, 60)
    jh["days_since_injection"] = 0.0
    jh["injection_rate_gpm"] = 0.0
    jh["ore_grade_pct"] = 0.0
    month = rng.integers(1, 13, n)
    jh["season"] = [S.month_to_season(int(m)) for m in month]
    return jh


def build(n_per_phase: int = 1500, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    texas = _build_texas(rng)
    jh = _build_jharkhand(rng)
    syn = synth.generate(n_per_phase=n_per_phase, seed=seed)

    full = pd.concat([texas, jh, syn], ignore_index=True)

    # guarantee every unified column exists, in order
    for col in S.UNIFIED_COLUMNS:
        if col not in full.columns:
            full[col] = np.nan
    full = S.assign_risk_column(full)
    full = full[full[S.CLASSIFICATION_TARGET].notna()].reset_index(drop=True)
    full = full[S.UNIFIED_COLUMNS]

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / "unified_dataset.csv"
    full.to_csv(out_path, index=False)

    # ---- report ----
    print(f"Saved -> {out_path}   shape={full.shape}")
    print("\nProvenance:")
    print(full["data_source"].value_counts().to_string())
    print("\nRisk class:")
    print(full["risk_class"].value_counts().reindex(S.RISK_CLASSES).to_string())
    print("\nRisk class x provenance:")
    print(pd.crosstab(full["data_source"], full["risk_class"]).to_string())
    print("\nUranium_ppb by phase (median):")
    print(full.groupby("phase")["uranium_ppb"].median().round(1).to_string())
    return full


if __name__ == "__main__":
    build()
