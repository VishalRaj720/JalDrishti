"""train.py — train the JalDrishti models on the unified dataset.

Objective 1 deliverables:
  * uranium_regressor   : predict uranium_ppb (log-target RandomForest)
  * risk_classifier     : predict safe / marginal / unsafe
  * cotarget regressors : TDS, sulfate, pH (the other ISR-altered parameters)

Honest evaluation
-----------------
Synthetic rows dominate the data, so a single accuracy number would mostly
measure how well the model fits its own generator. We therefore report metrics
BOTH overall and on the held-out REAL rows only (texas_real + jharkhand_real) —
the latter is the number that actually reflects real-world signal.

Run:  python -m pipeline.train
"""
from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, classification_report, f1_score,
                             mean_absolute_error, r2_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from pipeline import ARTIFACTS_DIR, SEED
from pipeline import schema as S


def _preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), S.NUMERIC_FEATURES),
        ("cat", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore")),
        ]), S.CATEGORICAL_FEATURES),
    ])


def _feature_names(pre: ColumnTransformer) -> list:
    cat = list(pre.named_transformers_["cat"]
               .named_steps["oh"].get_feature_names_out(S.CATEGORICAL_FEATURES))
    return S.NUMERIC_FEATURES + cat


def _importances(model: Pipeline, top: int = 12) -> list:
    pre = model.named_steps["pre"]
    est = model.named_steps["model"]
    names = _feature_names(pre)
    pairs = sorted(zip(names, est.feature_importances_),
                   key=lambda t: t[1], reverse=True)
    return [{"feature": n, "importance": round(float(v), 4)} for n, v in pairs[:top]]


def main() -> None:
    df = pd.read_csv(ARTIFACTS_DIR / "unified_dataset.csv")
    X = df[S.ALL_FEATURES]
    src_all = df["data_source"]
    metrics: dict = {"n_rows": len(df),
                     "provenance": df["data_source"].value_counts().to_dict()}

    # shared stratified split (on risk class) reused for every target
    idx_tr, idx_te = train_test_split(
        df.index, test_size=0.20, random_state=SEED, stratify=df["risk_class"])
    real_te = idx_te[src_all.loc[idx_te].isin(["texas_real", "jharkhand_real"])]

    # ================= 1. Uranium regressor (log target) =================
    print("=" * 64, "\nURANIUM REGRESSOR (uranium_ppb, log1p target)")
    y = np.log1p(df[S.PRIMARY_TARGET].clip(lower=0))
    u_mask = df[S.PRIMARY_TARGET].notna()
    u_tr = idx_tr[u_mask.loc[idx_tr].values]
    u_te = idx_te[u_mask.loc[idx_te].values]
    u_real_te = real_te[u_mask.loc[real_te].values]
    reg = Pipeline([("pre", _preprocessor()),
                    ("model", RandomForestRegressor(
                        n_estimators=400, min_samples_leaf=2,
                        n_jobs=-1, random_state=SEED))])
    reg.fit(X.loc[u_tr], y.loc[u_tr])

    def _reg_report(idx, label):
        if len(idx) == 0:
            return {}
        pred_log = reg.predict(X.loc[idx])
        yt_log = y.loc[idx]
        yt = np.expm1(yt_log); yp = np.expm1(pred_log)
        r = {"n": int(len(idx)),
             "r2_log": round(float(r2_score(yt_log, pred_log)), 4),
             "mae_log": round(float(mean_absolute_error(yt_log, pred_log)), 4),
             "median_abs_err_ppb": round(float(np.median(np.abs(yt - yp))), 3)}
        print(f"  [{label:14}] n={r['n']:5}  R2(log)={r['r2_log']:.3f}  "
              f"MAE(log)={r['mae_log']:.3f}  medAbsErr={r['median_abs_err_ppb']} ppb")
        return r

    metrics["uranium_regressor"] = {
        "overall": _reg_report(u_te, "all test"),
        "real_only": _reg_report(u_real_te, "real test"),
        "feature_importances": _importances(reg),
    }
    joblib.dump(reg, ARTIFACTS_DIR / "uranium_regressor.joblib")

    # ================= 2. Risk classifier =================
    print("=" * 64, "\nRISK CLASSIFIER (safe / marginal / unsafe)")
    yc = df["risk_class"]
    clf = Pipeline([("pre", _preprocessor()),
                    ("model", RandomForestClassifier(
                        n_estimators=400, min_samples_leaf=2,
                        class_weight="balanced", n_jobs=-1, random_state=SEED))])
    clf.fit(X.loc[idx_tr], yc.loc[idx_tr])

    def _clf_report(idx, label):
        if len(idx) == 0:
            return {}
        pred = clf.predict(X.loc[idx])
        r = {"n": int(len(idx)),
             "accuracy": round(float(accuracy_score(yc.loc[idx], pred)), 4),
             "macro_f1": round(float(f1_score(yc.loc[idx], pred, average="macro",
                                              labels=S.RISK_CLASSES, zero_division=0)), 4)}
        print(f"  [{label:14}] n={r['n']:5}  acc={r['accuracy']:.3f}  "
              f"macroF1={r['macro_f1']:.3f}")
        return r

    metrics["risk_classifier"] = {
        "overall": _clf_report(idx_te, "all test"),
        "real_only": _clf_report(real_te, "real test"),
        "feature_importances": _importances(clf),
    }
    print("\n  Real-only test classification report:")
    if len(real_te):
        print(classification_report(yc.loc[real_te], clf.predict(X.loc[real_te]),
                                    labels=S.RISK_CLASSES, zero_division=0))
    joblib.dump(clf, ARTIFACTS_DIR / "risk_classifier.joblib")

    # ================= 3. Co-target regressors (TDS, sulfate, pH) ========
    print("=" * 64, "\nCO-TARGET REGRESSORS")
    metrics["cotargets"] = {}
    for tgt in S.CO_TARGETS:
        yt = df[tgt]
        m = yt.notna()
        tr = idx_tr[m.loc[idx_tr].values]; te = idx_te[m.loc[idx_te].values]
        co = Pipeline([("pre", _preprocessor()),
                       ("model", RandomForestRegressor(
                           n_estimators=300, min_samples_leaf=2,
                           n_jobs=-1, random_state=SEED))])
        co.fit(X.loc[tr], yt.loc[tr])
        pred = co.predict(X.loc[te])
        r2 = round(float(r2_score(yt.loc[te], pred)), 4)
        mae = round(float(mean_absolute_error(yt.loc[te], pred)), 3)
        metrics["cotargets"][tgt] = {"n_test": int(len(te)), "r2": r2, "mae": mae}
        print(f"  {tgt:14} R2={r2:.3f}  MAE={mae}")
        joblib.dump(co, ARTIFACTS_DIR / f"cotarget_{tgt}.joblib")

    # ================= persist schema + metrics =========================
    schema_blob = {
        "numeric_features": S.NUMERIC_FEATURES,
        "categorical_features": S.CATEGORICAL_FEATURES,
        "regression_targets": S.REGRESSION_TARGETS,
        "classification_target": S.CLASSIFICATION_TARGET,
        "risk_classes": S.RISK_CLASSES,
        "uranium_target_transform": "log1p",
        "thresholds": {
            "uranium_unsafe_ppb": S.URANIUM_UNSAFE_PPB,
            "uranium_marginal_ppb": S.URANIUM_MARGINAL_PPB,
            "tds_unsafe_mgl": S.TDS_UNSAFE_MGL,
            "sulfate_unsafe_mgl": S.SULFATE_UNSAFE_MGL,
        },
    }
    (ARTIFACTS_DIR / "feature_schema.json").write_text(json.dumps(schema_blob, indent=2))
    (ARTIFACTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print("=" * 64, f"\nArtifacts + metrics saved -> {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
