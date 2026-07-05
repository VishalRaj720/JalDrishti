"""
ml_pipeline.ml.dataset  (PHASE 3 v2 -- data contract for training)
=================================================================
Defines exactly what the surrogate sees, the physically-mandated monotone
constraints PER TARGET, the target transforms, and the leakage-safe grouping.

v2 (2026-07 remediation plan, Phase 3):
  * PER-TARGET MONOTONE MAPS -- one shared sign tuple forced physically wrong
    signs (review finding #1): time/tau are unsafe for the ring concentration
    (Tang sqrt(t) attenuation + clean-front timing at fixed front features),
    so `compliance_conc` gets its own map.
  * Q_out_m3_day DROPPED -- pure collinearity with Q_in x bleed; it existed
    only as an unconstrained back-door that laundered constraint violations.
  * DISTRIBUTIONAL TARGETS -- the labels are MC P10/P50/P90 (parameter
    uncertainty), one squared-error model per (target, band); quantile loss is
    no longer appropriate because each band label is (near-)deterministic in X.
  * TWO GROUPINGS -- `scenario_id` (primary leakage-safe CV) and `polygon_id`
    (leave-aquifer-out stress CV: does the model generalize to hydrogeology it
    has never seen?).
  * MONDRIAN CELLS -- conformal deltas are calibrated per regime x species so
    the risk-critical slices (fractured / uranium) get honest coverage.
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
TRAINING_CSV = OUT_DIR / "synthetic_training.csv"
GROUP_COL = "scenario_id"
POLYGON_COL = "polygon_id"

SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
SPECIES_ONEHOT = ["is_uranium_ppb", "is_sulfate_mg_l", "is_tds_mg_l"]

# Ordered feature list. ORDER IS LOAD-BEARING: monotone tuples align to it.
# `domain_is_texas` (constant 0) and `Q_out_m3_day` (collinear back-door) are
# excluded. `Xc_m` / `Xc_clean_m` are the analytic front positions --
# deterministic functions of the raw operating point, recomputed at inference.
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
    "Q_in_m3_day", "bleed_fraction", "Q_net_m3_day",
    "containment_eta", "operation_days", "wellfield_width_m",
    # --- source / background ---
    "source_conc_C0", "background_conc_Cb",
    # --- irregularities & restoration (Phase-2 v2) ---
    "downtime_fraction", "gradient_seasonal_amp",
    "restoration_years", "residual_fraction",
    # --- evaluation-time (analytic fronts + time) ---
    "Xc_m", "Xc_clean_m", "time_years", "is_post_closure",
    # --- species one-hot ---
    *SPECIES_ONEHOT,
]

# Base sign map for "more contamination" FOOTPRINT targets (area, migration,
# excursion probability). Each sign is a hydrogeology law, verified on the
# physics LABELS in ml_pipeline/tests/test_physics_laws.py (raw-operating-point
# sweeps, all coupled quantities moving together):
_FOOTPRINT_MAP = {
    "K_m_day": +1,                 # more conductive -> faster, farther
    "gradient_i": +1,              # steeper gradient -> faster
    "darcy_flux_q": +1,
    "seepage_velocity_v": +1,
    "contaminant_velocity_vc": +1,
    "Xc_m": +1,                    # farther front -> larger footprint
    "Xc_clean_m": -1,              # farther clean-up front -> smaller footprint
    "time_years": +1,              # later time -> larger plume (no-restoration)
    "is_post_closure": +1,         # drift phase -> migrates farther
    "dimensionless_time_tau": +1,
    "Q_in_m3_day": +1,             # more throughput -> wider source (at fixed Q_net;
                                   #   verified label-level in the tests)
    "pore_volumes_PV": +1,         # time-consistent throughput -> wider source
    "source_conc_C0": +1,
    "background_conc_Cb": +1,      # higher ambient -> lower incremental threshold
    "wellfield_width_m": +1,       # ring is FIXED 100 m beyond the edge (v2 geometry)
    "downtime_fraction": +1,       # capture outages -> more escape
    "residual_fraction": +1,       # dirtier restoration -> more contamination
    "phi_mobile": -1,              # more mobile porosity -> slower velocity
    "retardation_Rd": -1,
    "Kd_L_kg": -1,                 # porous: sorption; fractured: matrix uptake (sigma)
    "bleed_fraction": -1,          # containment knobs
    "Q_net_m3_day": -1,
    "containment_eta": -1,
    "restoration_years": -1,       # longer sweep -> front held longer + cleaner source
}

# Ring concentration: time signs are UNSAFE at fixed front features (Tang
# sqrt(t) attenuation shrinks the early-arrival channel; the clean front's
# timing is only partially captured by Xc_clean_m) -> unconstrained.
_COMPLIANCE_MAP = {**_FOOTPRINT_MAP,
                   "time_years": 0, "is_post_closure": 0,
                   "dimensionless_time_tau": 0}

MONOTONE_MAPS = {
    "affected_area_ha": _FOOTPRINT_MAP,
    "max_migration_distance_m": _FOOTPRINT_MAP,
    "compliance_conc": _COMPLIANCE_MAP,
    "excursion_probability": _FOOTPRINT_MAP,
}


# Phase 3.5 (2026-07): the monotone constraints are applied ONLY to the P50
# central estimate. The P10/P90 uncertainty band edges are left FREE. A quantile
# band of a switch-like target (esp. compliance_conc at the fixed compliance
# ring) is not monotone in every driver, and forcing it cost ~0.7 R^2 on the
# compliance P90 and ~0.16 on the migration P10 -- the conformal delta then had
# to absorb that fit error as blunt, over-wide bands. Freeing the edges keeps
# P50 physical (on-manifold check unaffected), holds 80% coverage, and shrinks
# the bands 27-33%. Verified empirically before adoption.
CONSTRAIN_BANDS = ("p50",)


def monotone_tuple(target: str, band: str = "p50") -> tuple[int, ...]:
    """XGBoost monotone_constraints tuple for a (target, band), aligned to
    MODEL_FEATURES. Only the P50 central estimate is constrained; the P10/P90
    band edges are unconstrained (see CONSTRAIN_BANDS)."""
    if band not in CONSTRAIN_BANDS:
        return tuple(0 for _ in MODEL_FEATURES)
    m = MONOTONE_MAPS[target]
    return tuple(m.get(f, 0) for f in MODEL_FEATURES)


# Distributional band targets: label columns are f"{target}_{band}" (MC
# quantiles over the parameter-uncertainty draws). log1p-transformed,
# squared-error per band. Off-scale rows are censored for the gridded targets.
BANDS = ("p10", "p50", "p90")
BAND_TARGETS = {
    "affected_area_ha": dict(log=True, censor_offscale=True),
    "max_migration_distance_m": dict(log=True, censor_offscale=True),
    "compliance_conc": dict(log=True, censor_offscale=False),
}
POINT_TARGET = "excursion_probability"     # breach fraction of the same draws
ALPHA = 0.20                               # 1 - target band coverage


def load_training_frame(csv: Path | None = None) -> pd.DataFrame:
    df = pd.read_csv(csv or TRAINING_CSV)
    for sp in SPECIES:
        df[f"is_{sp}"] = (df["species"] == sp).astype(int)
    missing = [c for c in MODEL_FEATURES if c not in df.columns]
    if missing:
        raise KeyError(f"training CSV missing model features: {missing} "
                       f"-- regenerate with ml_pipeline.synthetic.generate (v2)")
    band_cols = [f"{t}_{b}" for t in BAND_TARGETS for b in BANDS]
    missing_y = [c for c in band_cols if c not in df.columns]
    if missing_y:
        raise KeyError(f"training CSV missing v2 band labels: {missing_y}")
    return df


def censor_mask(df: pd.DataFrame) -> pd.Series:
    """Rows whose gridded area/distance labels are censored lower bounds."""
    off = df.get("off_scale", 0).astype(float)
    off_frac = df.get("off_scale_frac", 0.0).astype(float)
    return (off > 0) | (off_frac > 0.10)


def Xy(df: pd.DataFrame, column: str, *, censor_offscale: bool = False):
    """(X, y, groups, polygons) for one label column."""
    sub = df[~censor_mask(df)] if censor_offscale else df
    X = sub[MODEL_FEATURES].astype(float)
    y = sub[column].astype(float)
    groups = sub[GROUP_COL].astype(int)
    polys = sub[POLYGON_COL].astype(int) if POLYGON_COL in sub else groups
    return X, y, groups, polys


def mondrian_cells(df: pd.DataFrame) -> pd.Series:
    """Conformal calibration cell per row: '{regime}|{species}' (6 cells)."""
    regime = np.where(df["regime_is_fractured"].astype(int) == 1,
                      "fractured", "porous")
    return pd.Series(regime, index=df.index).str.cat(df["species"], sep="|")


def cell_key(regime: str, species: str) -> str:
    """Serving-side cell key (must mirror mondrian_cells)."""
    return f"{regime}|{species}"


if __name__ == "__main__":
    df = load_training_frame()
    print("rows:", len(df), "| scenarios:", df[GROUP_COL].nunique(),
          "| polygons:", df[POLYGON_COL].nunique())
    print("n model features:", len(MODEL_FEATURES))
    for t in MONOTONE_MAPS:
        mt = monotone_tuple(t)
        print(f"  {t:28s} constrained: {sum(1 for s in mt if s != 0)}")
    print("censored rows (off-scale):", int(censor_mask(df).sum()))
    print("cells:", mondrian_cells(df).value_counts().to_dict())
