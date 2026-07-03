"""
ml_pipeline.ml.dataset  (PHASE 3 -- data contract for training)
=============================================================
Defines exactly what the surrogate sees, the physically-mandated monotone
constraints, the target transforms, and the leakage-safe grouping.

Two guardrails live here:
  * MODEL_FEATURES        -- the ONLY columns the model may use (no targets,
                             no metadata, no leakage).
  * MONOTONE_MAP          -- sign of each feature's allowed effect on every
                             "more-contamination" target, encoding hydrogeology
                             law (higher injection -> larger plume = +1;
                             higher bleed/retardation -> smaller plume = -1).
Grouping is by `scenario_id` so GroupKFold never splits a scenario's
(time x species) rows across train/test.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
TRAINING_CSV = OUT_DIR / "synthetic_training.csv"
GROUP_COL = "scenario_id"

SPECIES_ONEHOT = ["is_uranium_ppb", "is_sulfate_mg_l", "is_tds_mg_l"]

# Ordered feature list. ORDER IS LOAD-BEARING: monotone_constraints is a tuple
# aligned to this order. `domain_is_texas` is dropped (constant 0 in synthetic).
MODEL_FEATURES = [
    # --- intrinsic hydrogeology ---
    "regime_is_fractured",
    "K_m_day", "gradient_i", "phi_mobile", "phi_total",
    "darcy_flux_q", "seepage_velocity_v",
    # --- chemistry / retardation ---
    "Kd_L_kg", "retardation_Rd", "contaminant_velocity_vc",
    # --- dispersion / anisotropy ---
    "alpha_L", "alpha_T", "anisotropy_ratio", "D_L", "D_T",
    # --- dimensionless groups ---
    "peclet_L", "pore_volumes_PV", "dimensionless_time_tau", "dual_porosity_beta",
    # --- operations ---
    "Q_in_m3_day", "Q_out_m3_day", "bleed_fraction", "Q_net_m3_day",
    "containment_eta", "operation_days", "wellfield_width_m",
    # --- source / background ---
    "source_conc_C0", "background_conc_Cb",
    # --- evaluation-time (cheap, time-informative; Xc is the analytic front pos) ---
    "Xc_m", "time_years", "is_post_closure",
    # --- species one-hot ---
    *SPECIES_ONEHOT,
]

# Sign of each feature's permitted monotone effect on a "MORE contamination"
# target (area, migration distance, boundary concentration, excursion prob /
# breach). Features not listed are left UNCONSTRAINED (0) because their effect
# is ambiguous or target-dependent (e.g. dispersivity raises area but lowers
# peak). Each sign is a hydrogeology law:
MONOTONE_MAP = {
    "K_m_day": +1,                 # more conductive -> faster, farther
    "gradient_i": +1,              # steeper gradient -> faster
    "darcy_flux_q": +1,
    "seepage_velocity_v": +1,
    "contaminant_velocity_vc": +1,
    "Xc_m": +1,                    # farther advective front -> larger footprint
    "time_years": +1,              # later time -> larger plume
    "is_post_closure": +1,         # drift phase -> migrates farther
    "dimensionless_time_tau": +1,
    "Q_in_m3_day": +1,             # USER LAW: higher injection -> larger plume
    "source_conc_C0": +1,          # stronger source -> larger above-threshold area
    "background_conc_Cb": +1,      # higher background -> easier breach
    "wellfield_width_m": +1,       # wider source -> wider plume
    "phi_mobile": -1,              # more porosity -> slower velocity -> less reach
    "retardation_Rd": -1,          # more sorption -> slower, smaller
    "Kd_L_kg": -1,                 # higher partitioning -> more retardation
    "bleed_fraction": -1,          # USER LAW: higher bleed -> stronger capture -> smaller
    "containment_eta": -1,         # more hydraulic capture -> smaller
    "Q_net_m3_day": -1,            # more net extraction -> more containment
}


def monotone_tuple() -> tuple[int, ...]:
    """Build the XGBoost monotone_constraints tuple aligned to MODEL_FEATURES."""
    return tuple(MONOTONE_MAP.get(f, 0) for f in MODEL_FEATURES)


# Targets and how to model them.
QUANTILE_TARGETS = {           # log1p-transformed, modelled with quantile loss
    "affected_area_ha": dict(log=True, censor_offscale=True),
    "max_migration_distance_m": dict(log=True, censor_offscale=True),
    "compliance_conc": dict(log=True, censor_offscale=False),
}
POINT_TARGET = "excursion_probability"     # regression in [0,1]
CLASS_TARGET = "breaches_bis"              # binary classification
QUANTILES = (0.10, 0.50, 0.90)


def load_training_frame(csv: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(csv or TRAINING_CSV)
    for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l"):
        df[f"is_{sp}"] = (df["species"] == sp).astype(int)
    missing = [c for c in MODEL_FEATURES if c not in df.columns]
    if missing:
        raise KeyError(f"training CSV missing model features: {missing}")
    return df


def Xy(df: pd.DataFrame, target: str, *, censor_offscale: bool = False):
    """Return (X, y, groups) for a target, optionally dropping off-scale-censored
    rows (whose gridded area/distance are only lower bounds)."""
    sub = df
    if censor_offscale and "off_scale" in df.columns:
        sub = df[df["off_scale"] == 0]
    X = sub[MODEL_FEATURES].astype(float)
    y = sub[target].astype(float)
    groups = sub[GROUP_COL].astype(int)
    return X, y, groups


if __name__ == "__main__":
    df = load_training_frame()
    print("rows:", len(df), "| scenarios:", df[GROUP_COL].nunique())
    print("n model features:", len(MODEL_FEATURES))
    mt = monotone_tuple()
    constrained = [(f, s) for f, s in zip(MODEL_FEATURES, mt) if s != 0]
    print("constrained features:", len(constrained))
    for f, s in constrained:
        print(f"   {'+' if s > 0 else '-'}  {f}")
    print("\nquantile targets:", list(QUANTILE_TARGETS))
    print("off_scale rows (censored for area/dist):", int(df.get("off_scale", pd.Series([0])).sum()))
