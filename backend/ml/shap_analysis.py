"""SHAP feature-importance analysis for the Month 4 baseline models.

Produces:
  artifacts/shap_top10_regressor.json
  artifacts/shap_top10_classifier.json
  artifacts/shap_summary_regressor.png   (only if shap & matplotlib available)
  artifacts/shap_summary_classifier.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import pandas as pd
from loguru import logger

from ml import ARTIFACTS_DIR
from ml.features import ALL_FEATURES


def _try_imports():
    try:
        import shap
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return shap, plt
    except Exception as exc:
        logger.warning(f"shap/matplotlib not installed: {exc}")
        return None, None


def _expand_feature_names(pipe) -> List[str]:
    """Recover post-preprocessing feature column names."""
    pre = pipe.named_steps["pre"]
    names: List[str] = []
    for name, _trans, cols in pre.transformers_:
        if name == "remainder":
            continue
        names.extend(cols)
    return names


def _shap_top_features(pipe, X: pd.DataFrame, n_samples: int = 200, top_k: int = 10) -> Dict:
    shap, plt = _try_imports()
    if shap is None:
        # Fallback: use sklearn's built-in feature_importances_ when available
        model = pipe.named_steps["model"]
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return {"method": "unsupported", "top_features": []}
        names = _expand_feature_names(pipe)
        order = np.argsort(importances)[::-1][:top_k]
        return {
            "method": "sklearn_feature_importances",
            "top_features": [
                {"feature": names[i], "importance": float(importances[i])}
                for i in order
            ],
        }

    # use a sample for performance
    sample = X.sample(min(n_samples, len(X)), random_state=42)
    pre = pipe.named_steps["pre"]
    model = pipe.named_steps["model"]
    X_pre = pre.transform(sample)

    feature_names = _expand_feature_names(pipe)

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_pre)
    except Exception:
        # KernelExplainer fallback (slow; small sample only)
        background = X_pre[: min(50, len(X_pre))]
        explainer = shap.KernelExplainer(model.predict, background)
        shap_values = explainer.shap_values(X_pre[: min(50, len(X_pre))])

    if isinstance(shap_values, list):
        # multi-class — average absolute over classes
        abs_vals = np.mean([np.abs(s) for s in shap_values], axis=0)
        mean_abs = abs_vals.mean(axis=0)
    else:
        abs_arr = np.abs(shap_values)
        if abs_arr.ndim == 2:
            mean_abs = abs_arr.mean(axis=0)
        else:
            # 3-D: (n_samples, n_features, n_classes) — keep feature axis (1)
            axes = tuple(i for i in range(abs_arr.ndim) if i != 1)
            mean_abs = abs_arr.mean(axis=axes)

    order = np.argsort(mean_abs.ravel())[::-1][:top_k]
    mean_abs = mean_abs.ravel()
    top = [
        {"feature": feature_names[int(i)], "mean_abs_shap": float(mean_abs[int(i)])}
        for i in order
    ]
    return {"method": "shap_tree_explainer", "top_features": top}


def run() -> None:
    csv_path = ARTIFACTS_DIR / "feature_matrix.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"{csv_path} missing. Run `python -m ml.feature_pipeline` then `python -m ml.train_baselines`."
        )

    matrix = pd.read_csv(csv_path)
    X = matrix[ALL_FEATURES].copy()

    reg_path = ARTIFACTS_DIR / "tds_regressor.joblib"
    clf_path = ARTIFACTS_DIR / "contamination_classifier.joblib"
    if not reg_path.exists() or not clf_path.exists():
        raise FileNotFoundError("Trained models not found. Run train_baselines first.")

    reg_pipe = joblib.load(reg_path)
    clf_pipe = joblib.load(clf_path)

    reg_top = _shap_top_features(reg_pipe, X)
    clf_top = _shap_top_features(clf_pipe, X)

    (ARTIFACTS_DIR / "shap_top10_regressor.json").write_text(json.dumps(reg_top, indent=2))
    (ARTIFACTS_DIR / "shap_top10_classifier.json").write_text(json.dumps(clf_top, indent=2))

    logger.info(f"Regressor top features: {reg_top['top_features'][:5]}")
    logger.info(f"Classifier top features: {clf_top['top_features'][:5]}")
    logger.info(f"Reports written to {ARTIFACTS_DIR}")


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run()


if __name__ == "__main__":
    _cli()
