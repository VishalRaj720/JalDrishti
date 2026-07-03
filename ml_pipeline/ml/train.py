"""
ml_pipeline.ml.train  (PHASE 3 -- physics-guided training)
========================================================
Trains the surrogate with three hard guardrails:

  1. LEAKAGE CONTROL  -- GroupKFold(5) on scenario_id; a scenario's 15
     (time x species) rows are never split across train/test.
  2. PHYSICS CONTROL  -- XGBoost monotone_constraints from dataset.MONOTONE_MAP
     (higher injection -> larger plume; higher bleed/retardation -> smaller).
  3. UNCERTAINTY      -- quantile loss gives P10/P50/P90 (non-crossing) for the
     map-able predictive bands; a breach classifier + P_ex regressor for risk.

Artifacts -> ml/artifacts/ ; CV metrics -> ml/artifacts/metrics.json.
Run:  python -m ml_pipeline.ml.train
"""
from __future__ import annotations

import json
import time
import numpy as np
import pandas as pd
import joblib
from sklearn.model_selection import GroupKFold
from sklearn.metrics import (
    r2_score, mean_absolute_error, roc_auc_score, brier_score_loss,
    accuracy_score,
)
import xgboost as xgb

from ml_pipeline.ml.dataset import (
    load_training_frame, Xy, MODEL_FEATURES, monotone_tuple, QUANTILE_TARGETS,
    POINT_TARGET, CLASS_TARGET, QUANTILES, ARTIFACT_DIR,
)

N_SPLITS = 5
COMMON = dict(n_estimators=450, max_depth=5, learning_rate=0.05,
              subsample=0.85, colsample_bytree=0.85, reg_lambda=1.5,
              tree_method="hist", random_state=42)
MONO = monotone_tuple()


# --------------------------------------------------------------------------- #
def pinball(y, q_pred, alpha):
    d = y - q_pred
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def _quantile_model():
    return xgb.XGBRegressor(objective="reg:quantileerror",
                            quantile_alpha=np.array(QUANTILES),
                            monotone_constraints=MONO, **COMMON)


# --------------------------------------------------------------------------- #
def train_quantile_target(df, target, cfg) -> tuple[xgb.XGBRegressor, dict]:
    """GroupKFold-CV a multi-quantile regressor, then fit on all rows."""
    X, y, groups = Xy(df, target, censor_offscale=cfg["censor_offscale"])
    y = y.to_numpy()
    yt = np.log1p(y) if cfg["log"] else y.copy()
    gkf = GroupKFold(n_splits=N_SPLITS)

    oof = np.full((len(y), len(QUANTILES)), np.nan)
    for tr, te in gkf.split(X, yt, groups):
        m = _quantile_model()
        m.fit(X.iloc[tr], yt[tr])
        oof[te] = m.predict(X.iloc[te])
    # --- Conformalized Quantile Regression (Romano et al. 2019) -------------
    # The synthetic physics is near-deterministic given X, so raw quantile heads
    # under-cover out-of-fold. Calibrate in the (transformed) model space using
    # the OOF conformity score E = max(qlo - y, y - qhi); widen by its (1-alpha)
    # empirical quantile so the P10-P90 band achieves ~80% coverage.
    qlo, qhi = oof[:, 0], oof[:, 2]                 # transformed space
    E = np.maximum(qlo - yt, yt - qhi)
    alpha = 0.20
    n = len(yt)
    k = min(int(np.ceil((n + 1) * (1 - alpha))), n)
    delta = float(np.sort(E)[k - 1])               # conformal half-correction
    lo_cal_t, hi_cal_t = qlo - delta, qhi + delta

    # back-transform (raw and calibrated)
    inv = (lambda a: np.clip(np.expm1(a), 0, None)) if cfg["log"] else (lambda a: np.clip(a, 0, None))
    p10, p50, p90 = inv(oof[:, 0]), inv(oof[:, 1]), inv(oof[:, 2])
    p10c, p90c = inv(lo_cal_t), inv(hi_cal_t)

    metrics = {
        "n": int(len(y)),
        "r2_p50": round(float(r2_score(y, p50)), 4),
        "mae_p50": round(float(mean_absolute_error(y, p50)), 4),
        "coverage_raw": round(float(np.mean((y >= p10) & (y <= p90))), 4),
        "coverage_calibrated": round(float(np.mean((y >= p10c) & (y <= p90c))), 4),
        "mean_width_calibrated": round(float(np.mean(p90c - p10c)), 4),
        "conformal_delta": round(delta, 5),
        "pinball_p10": round(pinball(yt, oof[:, 0], 0.10), 5),
        "pinball_p90": round(pinball(yt, oof[:, 2], 0.90), 5),
    }
    final = _quantile_model().fit(X, yt)
    return final, metrics


def train_point_regressor(df) -> tuple[xgb.XGBRegressor, dict]:
    X, y, groups = Xy(df, POINT_TARGET)
    gkf = GroupKFold(n_splits=N_SPLITS)
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(X, y, groups):
        m = xgb.XGBRegressor(objective="reg:squarederror",
                             monotone_constraints=MONO, **COMMON)
        m.fit(X.iloc[tr], y.iloc[tr])
        oof[te] = np.clip(m.predict(X.iloc[te]), 0, 1)
    metrics = {"n": int(len(y)),
               "r2": round(float(r2_score(y, oof)), 4),
               "mae": round(float(mean_absolute_error(y, oof)), 4)}
    final = xgb.XGBRegressor(objective="reg:squarederror",
                             monotone_constraints=MONO, **COMMON).fit(X, y)
    return final, metrics


def train_classifier(df) -> tuple[xgb.XGBClassifier, dict]:
    X, y, groups = Xy(df, CLASS_TARGET)
    gkf = GroupKFold(n_splits=N_SPLITS)
    oof = np.full(len(y), np.nan)
    for tr, te in gkf.split(X, y, groups):
        m = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss",
                              monotone_constraints=MONO, **COMMON)
        m.fit(X.iloc[tr], y.iloc[tr])
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    metrics = {"n": int(len(y)),
               "auc": round(float(roc_auc_score(y, oof)), 4),
               "brier": round(float(brier_score_loss(y, oof)), 4),
               "accuracy@0.5": round(float(accuracy_score(y, (oof >= 0.5))), 4)}
    final = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss",
                              monotone_constraints=MONO, **COMMON).fit(X, y)
    return final, metrics


# --------------------------------------------------------------------------- #
def verify_monotonicity(models: dict, df, tol_ha: float = 1e-2) -> dict:
    """Empirically confirm the constraints bind: sweep one feature (others held
    at a REAL in-distribution baseline -- uranium species), check the predicted
    area moves the physically-correct direction. `tol_ha` ignores sub-1e-2 ha
    tree-boundary / expm1 round-off (constraints are exact only in log space)."""
    X = df[MODEL_FEATURES].astype(float)
    base = X.median()
    base["is_uranium_ppb"], base["is_sulfate_mg_l"], base["is_tds_mg_l"] = 1.0, 0.0, 0.0
    qm = models["quantile"]["affected_area_ha"]

    def sweep(feature, n=30):
        lo, hi = X[feature].quantile(0.02), X[feature].quantile(0.98)
        Xs = pd.DataFrame([base.copy() for _ in range(n)])
        Xs[feature] = np.linspace(lo, hi, n)
        return np.expm1(qm.predict(Xs[MODEL_FEATURES])[:, 1])   # P50, ha

    q, b = sweep("Q_in_m3_day"), sweep("bleed_fraction")
    return {
        "area_increases_with_Q_in": bool(q[-1] >= q[0] and np.min(np.diff(q)) > -tol_ha),
        "area_decreases_with_bleed": bool(b[-1] <= b[0] and np.max(np.diff(b)) < tol_ha),
        "area_Q_in_lo_hi_ha": [round(float(q[0]), 2), round(float(q[-1]), 2)],
        "area_bleed_lo_hi_ha": [round(float(b[0]), 2), round(float(b[-1]), 2)],
        "max_violation_ha": round(float(max(max(-np.min(np.diff(q)), 0.0),
                                            max(np.max(np.diff(b)), 0.0))), 6),
    }


def train_all():
    t0 = time.time()
    ARTIFACT_DIR.mkdir(exist_ok=True)
    df = load_training_frame()
    print(f"Training on {len(df)} rows / {df['scenario_id'].nunique()} scenarios, "
          f"{len(MODEL_FEATURES)} features, GroupKFold({N_SPLITS})\n")

    models = {"quantile": {}}
    metrics = {"quantile": {}, "config": {
        "n_splits": N_SPLITS, "quantiles": list(QUANTILES),
        "features": MODEL_FEATURES, "monotone": list(MONO),
        "xgb_params": COMMON}}

    for target, cfg in QUANTILE_TARGETS.items():
        m, mt = train_quantile_target(df, target, cfg)
        models["quantile"][target] = m
        metrics["quantile"][target] = mt
        joblib.dump(m, ARTIFACT_DIR / f"quantile_{target}.joblib")
        print(f"[quantile] {target:26s} R2(P50)={mt['r2_p50']:.3f}  "
              f"MAE={mt['mae_p50']:.2f}  coverage raw={mt['coverage_raw']:.2f}"
              f" -> calib={mt['coverage_calibrated']:.2f}")

    models["pex"], metrics["pex"] = train_point_regressor(df)
    joblib.dump(models["pex"], ARTIFACT_DIR / "pex_regressor.joblib")
    print(f"[regress]  excursion_probability    R2={metrics['pex']['r2']:.3f}  "
          f"MAE={metrics['pex']['mae']:.3f}")

    models["breach"], metrics["breach"] = train_classifier(df)
    joblib.dump(models["breach"], ARTIFACT_DIR / "breach_classifier.joblib")
    print(f"[classify] breaches_bis             AUC={metrics['breach']['auc']:.3f}  "
          f"Brier={metrics['breach']['brier']:.3f}  acc={metrics['breach']['accuracy@0.5']:.3f}")

    mono = verify_monotonicity(models, df)
    metrics["monotonicity_check"] = mono
    print("\n[monotonicity] area INCREASES with Q_in:", mono["area_increases_with_Q_in"],
          "| area DECREASES with bleed:", mono["area_decreases_with_bleed"])
    print("   area Q_in[lo->hi]:", mono["area_Q_in_lo_hi_ha"],
          "ha | area bleed[lo->hi]:", mono["area_bleed_lo_hi_ha"],
          "ha | max numerical violation:", mono["max_violation_ha"], "ha")

    # model card for the dashboard / predict.py
    (ARTIFACT_DIR / "model_card.json").write_text(json.dumps({
        "features": MODEL_FEATURES, "monotone_constraints": list(MONO),
        "quantiles": list(QUANTILES), "quantile_targets": list(QUANTILE_TARGETS),
        "log_targets": [t for t, c in QUANTILE_TARGETS.items() if c["log"]],
        "conformal_deltas": {t: metrics["quantile"][t]["conformal_delta"]
                             for t in QUANTILE_TARGETS},
        "point_target": POINT_TARGET, "class_target": CLASS_TARGET,
    }, indent=2))
    (ARTIFACT_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"\nDONE in {time.time()-t0:.1f}s -> artifacts in {ARTIFACT_DIR}")
    return models, metrics


if __name__ == "__main__":
    train_all()
