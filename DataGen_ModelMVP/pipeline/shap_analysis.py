"""shap_analysis.py — compute SHAP feature importance for every trained model.

Outputs one JSON per model in artifacts/:
    shap_uranium_regressor.json
    shap_risk_classifier.json
    shap_cotarget_tds_mg_l.json
    shap_cotarget_sulfate_mg_l.json
    shap_cotarget_ph.json

Each JSON is a list of {"feature": str, "shap_mean_abs": float} sorted descending.

Run:
    python -m pipeline.shap_analysis
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from pipeline import ARTIFACTS_DIR, SEED
from pipeline import schema as S

try:
    import shap
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False
    warnings.warn("shap not installed — falling back to sklearn feature_importances_", stacklevel=1)


# ── helpers ──────────────────────────────────────────────────────────────────

def _feature_names(pipeline) -> list[str]:
    pre = pipeline.named_steps["pre"]
    cat_names = list(
        pre.named_transformers_["cat"]
        .named_steps["oh"]
        .get_feature_names_out(S.CATEGORICAL_FEATURES)
    )
    return S.NUMERIC_FEATURES + cat_names


def _transform_X(pipeline, X: pd.DataFrame) -> np.ndarray:
    return pipeline.named_steps["pre"].transform(X)


def _shap_mean_abs_regressor(pipeline, X_raw: pd.DataFrame) -> np.ndarray:
    """Mean |SHAP| across samples for a regression pipeline."""
    X_t = _transform_X(pipeline, X_raw)
    estimator = pipeline.named_steps["model"]
    explainer = shap.TreeExplainer(estimator)
    vals = explainer.shap_values(X_t)          # shape (n_samples, n_features)
    return np.abs(vals).mean(axis=0)


def _shap_mean_abs_classifier(pipeline, X_raw: pd.DataFrame) -> np.ndarray:
    """Mean |SHAP| across samples AND classes for a classification pipeline."""
    X_t = _transform_X(pipeline, X_raw)
    estimator = pipeline.named_steps["model"]
    explainer = shap.TreeExplainer(estimator)
    vals = explainer.shap_values(X_t)          # list[n_classes] of (n_samples, n_features)
    # average absolute importance over all classes
    return np.mean([np.abs(v).mean(axis=0) for v in vals], axis=0)


def _sklearn_importances(pipeline) -> np.ndarray:
    return pipeline.named_steps["model"].feature_importances_


def _build_ranking(importances: np.ndarray, names: list[str], top: int = 15) -> list[dict]:
    pairs = sorted(zip(names, importances), key=lambda t: t[1], reverse=True)
    return [
        {"feature": n, "shap_mean_abs": round(float(v), 6)}
        for n, v in pairs[:top]
    ]


def _analyse(tag: str, path: Path, X: pd.DataFrame, is_classifier: bool) -> None:
    print(f"  {tag} ...", end=" ", flush=True)
    pipeline = joblib.load(path)
    names = _feature_names(pipeline)

    if _HAS_SHAP:
        try:
            if is_classifier:
                imps = _shap_mean_abs_classifier(pipeline, X)
            else:
                imps = _shap_mean_abs_regressor(pipeline, X)
            method = "shap_tree_explainer"
        except Exception as exc:
            warnings.warn(f"SHAP failed for {tag} ({exc}); using feature_importances_")
            imps = _sklearn_importances(pipeline)
            method = "sklearn_feature_importances"
    else:
        imps = _sklearn_importances(pipeline)
        method = "sklearn_feature_importances"

    ranking = _build_ranking(imps, names)
    out: dict[str, Any] = {"model": tag, "method": method, "top_features": ranking}
    dest = ARTIFACTS_DIR / f"shap_{tag}.json"
    dest.write_text(json.dumps(out, indent=2))
    print(f"saved ({method})")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    df = pd.read_csv(ARTIFACTS_DIR / "unified_dataset.csv")
    # Use a sample to keep SHAP tractable (TreeExplainer is fast but full dataset is 3k rows)
    rng = np.random.default_rng(SEED)
    sample_idx = rng.choice(len(df), size=min(500, len(df)), replace=False)
    X = df[S.ALL_FEATURES].iloc[sample_idx].reset_index(drop=True)

    print("Computing SHAP feature importances …")

    models: list[tuple[str, Path, bool]] = [
        ("uranium_regressor",       ARTIFACTS_DIR / "uranium_regressor.joblib",      False),
        ("risk_classifier",         ARTIFACTS_DIR / "risk_classifier.joblib",         True),
        ("cotarget_tds_mg_l",       ARTIFACTS_DIR / "cotarget_tds_mg_l.joblib",      False),
        ("cotarget_sulfate_mg_l",   ARTIFACTS_DIR / "cotarget_sulfate_mg_l.joblib",  False),
        ("cotarget_ph",             ARTIFACTS_DIR / "cotarget_ph.joblib",             False),
    ]

    for tag, path, is_clf in models:
        if not path.exists():
            print(f"  {tag} — artifact not found, skipping")
            continue
        _analyse(tag, path, X, is_clf)

    print(f"\nDone. SHAP JSONs written to {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
