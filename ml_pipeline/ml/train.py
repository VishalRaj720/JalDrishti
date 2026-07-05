"""
ml_pipeline.ml.train  (PHASE 3 v2 -- physics-guided training)
===========================================================
Trains the surrogate with the remediated guardrails (2026-07 plan):

  1. LEAKAGE CONTROL   -- GroupKFold(5) on scenario_id (primary skill number)
                          PLUS leave-aquifer-out GroupKFold on polygon_id (the
                          honest "new site" stress number, reported separately).
  2. PHYSICS CONTROL   -- PER-TARGET monotone maps (dataset.MONOTONE_MAPS);
                          verified post-fit ON-MANIFOLD: the raw operating
                          point is swept through the same feature builder used
                          at inference, so coupled features move together
                          (the old single-feature sweep could only ever pass).
  3. UNCERTAINTY       -- labels are MC P10/P50/P90 (parameter uncertainty);
                          one squared-error model per (target, band), then
                          CONFORMAL calibration done honestly:
                            * conformity scores from GroupKFold OOF predictions,
                            * aggregated per (Mondrian cell x scenario) by max,
                            * delta from a 50% calibration split of scenarios,
                            * coverage REPORTED on the untouched other 50%
                          (the old pipeline evaluated coverage on the same rows
                          that set the delta -- an identity, not a validation).

Artifacts -> ml/artifacts/ ; metrics -> ml/artifacts/metrics.json.
Run:  python -m ml_pipeline.ml.train
"""
from __future__ import annotations

import json
import math
import time
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import GroupKFold
from sklearn.metrics import r2_score, mean_absolute_error
import xgboost as xgb

from ml_pipeline.ml.dataset import (
    load_training_frame, censor_mask, MODEL_FEATURES, monotone_tuple,
    BAND_TARGETS, BANDS, POINT_TARGET, ALPHA, ARTIFACT_DIR,
    GROUP_COL, POLYGON_COL, mondrian_cells, Xy,
)

N_SPLITS = 5
CAL_SPLIT_SEED = 0
COMMON = dict(n_estimators=450, max_depth=5, learning_rate=0.05,
              subsample=0.85, colsample_bytree=0.85, reg_lambda=1.5,
              tree_method="hist", random_state=42)


def _model(target: str) -> xgb.XGBRegressor:
    return xgb.XGBRegressor(objective="reg:squarederror",
                            monotone_constraints=monotone_tuple(target), **COMMON)


def _subframe(df: pd.DataFrame, censor: bool) -> pd.DataFrame:
    return df[~censor_mask(df)] if censor else df


def _cal_eval_split(scenario_ids: np.ndarray) -> set:
    """Deterministic 50% calibration split of unique scenario ids."""
    uniq = np.unique(scenario_ids)
    rng = np.random.default_rng(CAL_SPLIT_SEED)
    rng.shuffle(uniq)
    return set(uniq[: len(uniq) // 2].tolist())


# --------------------------------------------------------------------------- #
def train_band_target(df: pd.DataFrame, target: str, cfg: dict):
    """OOF-CV the three band models, conformalize honestly, refit on all rows."""
    sub = _subframe(df, cfg["censor_offscale"])
    X = sub[MODEL_FEATURES].astype(float)
    groups = sub[GROUP_COL].to_numpy()
    cells = mondrian_cells(sub).to_numpy()
    yt = {b: np.log1p(sub[f"{target}_{b}"].to_numpy()) for b in BANDS}

    gkf = GroupKFold(n_splits=N_SPLITS)
    oof = {b: np.full(len(sub), np.nan) for b in BANDS}
    fold_r2 = []
    for tr, te in gkf.split(X, yt["p50"], groups):
        for b in BANDS:
            m = _model(target)
            m.fit(X.iloc[tr], yt[b][tr])
            oof[b][te] = m.predict(X.iloc[te])
        fold_r2.append(round(float(r2_score(
            np.expm1(yt["p50"][te]), np.expm1(oof["p50"][te]))), 4))

    # rearrange BEFORE any conformity computation (heads can cross per-row)
    lo = np.minimum(oof["p10"], oof["p50"])
    hi = np.maximum(oof["p90"], oof["p50"])

    band_metrics = {"r2": {}, "mae": {}}
    for b, pred in (("p10", lo), ("p50", oof["p50"]), ("p90", hi)):
        y_raw, p_raw = np.expm1(yt[b]), np.clip(np.expm1(pred), 0, None)
        band_metrics["r2"][b] = round(float(r2_score(y_raw, p_raw)), 4)
        band_metrics["mae"][b] = round(float(mean_absolute_error(y_raw, p_raw)), 4)

    # --- honest Mondrian split-conformal (log space, scenario-level scores) ---
    E = np.maximum(lo - yt["p10"], yt["p90"] - hi)   # band-containment score
    edf = pd.DataFrame({"E": E, "cell": cells, "scen": groups})
    scen_scores = edf.groupby(["cell", "scen"])["E"].max().reset_index()
    cal = _cal_eval_split(groups)
    is_cal = scen_scores["scen"].isin(cal)

    deltas = {}
    for cell, g in scen_scores[is_cal].groupby("cell"):
        s = np.sort(g["E"].to_numpy())
        k = min(int(math.ceil((len(s) + 1) * (1 - ALPHA))), len(s))
        deltas[cell] = round(float(s[k - 1]), 5)

    # coverage on the UNTOUCHED evaluation half
    row_eval = ~pd.Series(groups).isin(cal).to_numpy()
    d_row = pd.Series(cells).map(deltas).to_numpy()
    covered = (lo - d_row <= yt["p10"]) & (yt["p90"] <= hi + d_row)
    cov_rows = float(np.mean(covered[row_eval]))
    scen_eval = scen_scores[~is_cal]
    cov_scen = float(np.mean(scen_eval["E"].to_numpy()
                             <= scen_eval["cell"].map(deltas).to_numpy()))
    per_cell = {c: round(float(np.mean(covered[row_eval & (cells == c)])), 3)
                for c in np.unique(cells)}
    y90_raw = np.expm1(yt["p90"])
    tail = row_eval & (y90_raw >= np.quantile(y90_raw[row_eval], 0.95))
    cov_tail = float(np.mean(covered[tail])) if tail.any() else float("nan")

    metrics = {
        "n": int(len(sub)),
        "n_censored": int(len(df) - len(sub)),
        **band_metrics,
        "r2_p50_per_fold": fold_r2,
        "coverage": {"rows_eval": round(cov_rows, 4),
                     "scenarios_eval": round(cov_scen, 4),
                     "tail_top5_rows": round(cov_tail, 4),
                     "per_cell_rows": per_cell},
        "deltas": deltas,
    }

    final = {b: _model(target).fit(X, yt[b]) for b in BANDS}
    return final, metrics


def polygon_stress_cv(df: pd.DataFrame, target: str, cfg: dict) -> dict:
    """Leave-aquifer-out CV (P50 band only): honest 'new hydrogeology' skill."""
    sub = _subframe(df, cfg["censor_offscale"])
    X = sub[MODEL_FEATURES].astype(float)
    y = np.log1p(sub[f"{target}_p50"].to_numpy())
    polys = sub[POLYGON_COL].to_numpy()
    n_splits = min(N_SPLITS, len(np.unique(polys)))
    oof = np.full(len(sub), np.nan)
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, polys):
        m = _model(target)
        m.fit(X.iloc[tr], y[tr])
        oof[te] = m.predict(X.iloc[te])
    return {"r2_p50": round(float(r2_score(np.expm1(y), np.clip(np.expm1(oof), 0, None))), 4),
            "mae_p50": round(float(mean_absolute_error(np.expm1(y), np.clip(np.expm1(oof), 0, None))), 4),
            "n_polygons": int(len(np.unique(polys)))}


def train_point_regressor(df: pd.DataFrame):
    X, y, groups, _ = Xy(df, POINT_TARGET)
    gkf = GroupKFold(n_splits=N_SPLITS)
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(X, y, groups):
        m = _model(POINT_TARGET)
        m.fit(X.iloc[tr], y.iloc[tr])
        oof[te] = np.clip(m.predict(X.iloc[te]), 0, 1)
    metrics = {"n": int(len(y)),
               "r2": round(float(r2_score(y, oof)), 4),
               "mae": round(float(mean_absolute_error(y, oof)), 4)}
    final = _model(POINT_TARGET).fit(X, y)
    return final, metrics


# --------------------------------------------------------------------------- #
def verify_on_manifold(band_models: dict) -> dict:
    """Sweep the RAW OPERATING POINT through the inference feature builder so
    all coupled features move together, then check the trained P50 area:
      * higher Q_in at FIXED Q_net -> non-decreasing (the honest user law);
      * higher Q_net at fixed Q_in -> non-increasing (containment)."""
    from ml_pipeline.ml.predict import features_from_inputs
    base = dict(regime="fractured", K_m_day=1.12, gradient_i=0.006,
                phi_mobile=0.008, n_total=0.03, grain_density=2750.0,
                kd_L_kg=1.0, beta=8.0, Q_in_m3_day=2500.0, bleed_fraction=0.016,
                operation_years=8.0, wellfield_width_m=300.0, thickness_m=37.5,
                source_conc_C0=15000.0, background_conc_Cb=2.0,
                species="uranium_ppb", time_years=10.0)

    def p50_area(**over):
        X, _, _ = features_from_inputs(**{**base, **over})
        return float(np.clip(np.expm1(
            band_models["affected_area_ha"]["p50"].predict(X)[0]), 0, None))

    Q_net = 40.0
    qs = (500.0, 1500.0, 3000.0, 5000.0)
    area_q = [round(p50_area(Q_in_m3_day=q, bleed_fraction=Q_net / q), 2) for q in qs]
    bleeds = (0.0, 0.02, 0.05, 0.08)
    area_b = [round(p50_area(bleed_fraction=b), 2) for b in bleeds]
    tol_q = 0.02 * max(max(area_q) - min(area_q), 1.0)
    tol_b = 0.02 * max(max(area_b) - min(area_b), 1.0)
    return {
        "area_p50_vs_Q_in_at_fixed_Qnet": area_q,
        "area_p50_vs_bleed_at_fixed_Q_in": area_b,
        "qin_law_holds": bool(all(b >= a - tol_q for a, b in zip(area_q, area_q[1:]))),
        "bleed_law_holds": bool(all(b <= a + tol_b for a, b in zip(area_b, area_b[1:]))),
    }


# --------------------------------------------------------------------------- #
def train_all():
    t0 = time.time()
    ARTIFACT_DIR.mkdir(exist_ok=True)
    df = load_training_frame()
    print(f"Training v2 on {len(df)} rows / {df[GROUP_COL].nunique()} scenarios / "
          f"{df[POLYGON_COL].nunique()} polygons, {len(MODEL_FEATURES)} features, "
          f"GroupKFold({N_SPLITS}) + honest Mondrian split-CQR\n")

    band_models, metrics = {}, {"bands": {}, "stress_polygon_cv": {}, "config": {
        "n_splits": N_SPLITS, "alpha": ALPHA, "features": MODEL_FEATURES,
        "n_constrained_per_target": {t: sum(1 for s in monotone_tuple(t) if s)
                                     for t in list(BAND_TARGETS) + [POINT_TARGET]},
        "xgb_params": COMMON}}

    for target, cfg in BAND_TARGETS.items():
        models, mt = train_band_target(df, target, cfg)
        band_models[target] = models
        metrics["bands"][target] = mt
        for b, m in models.items():
            joblib.dump(m, ARTIFACT_DIR / f"band_{target}_{b}.joblib")
        cov = mt["coverage"]
        print(f"[bands] {target:26s} R2(P50)={mt['r2']['p50']:.3f}  "
              f"MAE(P50)={mt['mae']['p50']:.2f}  "
              f"coverage rows={cov['rows_eval']:.3f} scen={cov['scenarios_eval']:.3f} "
              f"tail={cov['tail_top5_rows']:.3f}")
        metrics["stress_polygon_cv"][target] = polygon_stress_cv(df, target, cfg)
        print(f"        leave-aquifer-out R2(P50)={metrics['stress_polygon_cv'][target]['r2_p50']:.3f}"
              f"  (vs scenario-CV {mt['r2']['p50']:.3f})")

    pex_model, metrics["pex"] = train_point_regressor(df)
    joblib.dump(pex_model, ARTIFACT_DIR / "pex_regressor.joblib")
    print(f"[point] excursion_probability     R2={metrics['pex']['r2']:.3f}  "
          f"MAE={metrics['pex']['mae']:.3f}")

    mono = verify_on_manifold(band_models)
    metrics["monotonicity_on_manifold"] = mono
    print("\n[on-manifold] area vs Q_in@fixed-Qnet:", mono["area_p50_vs_Q_in_at_fixed_Qnet"],
          "->", "OK" if mono["qin_law_holds"] else "VIOLATED")
    print("[on-manifold] area vs bleed@fixed-Qin: ", mono["area_p50_vs_bleed_at_fixed_Q_in"],
          "->", "OK" if mono["bleed_law_holds"] else "VIOLATED")

    from ml_pipeline.config import parameters as P
    from ml_pipeline.ml.dataset import MONOTONE_MAPS
    # Per-regime hydro support (P1 guard): the (phi_mobile, Rd, K) box the model
    # actually saw, so serving can flag out-of-distribution hydrogeology (e.g. a
    # regime override or manual phi/K that lands where no training row exists).
    hydro_support = {}
    for flag, name in ((1, "fractured"), (0, "porous")):
        sub = df[df["regime_is_fractured"] == flag]
        if len(sub):
            hydro_support[name] = {
                "phi_mobile": [float(sub["phi_mobile"].min()), float(sub["phi_mobile"].max())],
                "retardation_Rd": [float(sub["retardation_Rd"].min()), float(sub["retardation_Rd"].max())],
                "K_m_day": [float(sub["K_m_day"].min()), float(sub["K_m_day"].max())],
            }
    (ARTIFACT_DIR / "model_card.json").write_text(json.dumps({
        "version": 2,
        "features": MODEL_FEATURES,
        "band_targets": list(BAND_TARGETS),
        "bands": list(BANDS),
        "log_targets": [t for t, c in BAND_TARGETS.items() if c["log"]],
        "deltas": {t: metrics["bands"][t]["deltas"] for t in BAND_TARGETS},
        "monotone_maps": MONOTONE_MAPS,
        "point_target": POINT_TARGET,
        "band_semantics": ("P10/P90 = parameter-uncertainty quantiles "
                           "(Kd, local K, beta, gradient/seasonality, dispersivity, "
                           "bleed drift), conformally widened per regime x species "
                           f"to contain the true MC band at {int((1-ALPHA)*100)}%"),
        "training_envelope": {k: list(v) for k, v in P.OPERATIONAL_RANGES.items()},
        "hydro_support": hydro_support,
        "compliance_buffer_m": P.COMPLIANCE_BUFFER_M,
    }, indent=2))
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nDONE in {time.time()-t0:.1f}s -> artifacts in {ARTIFACT_DIR}")
    return band_models, metrics


if __name__ == "__main__":
    train_all()
