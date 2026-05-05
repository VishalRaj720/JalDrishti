"""Train + evaluate Month 4 baseline models.

Models:
  TDS regressor:    RandomForestRegressor + Ridge (best by 5-fold R^2)
  Contamination:    RandomForestClassifier + LogisticRegression (best by weighted F1)

Outputs:
    backend/ml/artifacts/tds_regressor.joblib
    backend/ml/artifacts/contamination_classifier.joblib
    backend/ml/artifacts/training_metrics.json
    backend/ml/artifacts/feature_metadata.json   (regenerated for runtime use)
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer, SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    f1_score, mean_absolute_error, mean_squared_error, r2_score, roc_auc_score,
)
from sklearn.model_selection import (
    KFold, StratifiedKFold, cross_val_score, train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler

from ml import ARTIFACTS_DIR
from ml.feature_pipeline import build_feature_matrix
from ml.features import (
    ALL_FEATURES, AQUIFER_TYPE_VOCAB, CATEGORICAL_FEATURES, CONTAMINATION_CLASSES,
    NUMERIC_FEATURES, SEASON_VOCAB, feature_schema,
)


def _build_preprocessor() -> ColumnTransformer:
    numeric_pipe = Pipeline([
        ("impute", IterativeImputer(max_iter=10, random_state=42)),
        ("scale", StandardScaler()),
    ])
    cat_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("encode", OrdinalEncoder(
            categories=[AQUIFER_TYPE_VOCAB, SEASON_VOCAB],
            handle_unknown="use_encoded_value",
            unknown_value=-1,
        )),
    ])
    return ColumnTransformer([
        ("num", numeric_pipe, NUMERIC_FEATURES),
        ("cat", cat_pipe, CATEGORICAL_FEATURES),
    ])


def _train_regressor(X: pd.DataFrame, y: pd.Series) -> Tuple[Pipeline, Dict[str, Any]]:
    candidates = {
        "random_forest": RandomForestRegressor(
            n_estimators=300, max_depth=12, min_samples_leaf=2,
            random_state=42, n_jobs=-1,
        ),
        "ridge": Ridge(alpha=1.0, random_state=42),
    }

    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    best_name, best_pipe, best_metrics = None, None, None

    for name, est in candidates.items():
        pipe = Pipeline([("pre", _build_preprocessor()), ("model", est)])
        try:
            r2_scores = cross_val_score(pipe, X, y, cv=cv, scoring="r2", n_jobs=1)
        except Exception as exc:
            logger.warning(f"Regressor {name} failed CV: {exc}")
            continue
        rmse_scores = -cross_val_score(
            pipe, X, y, cv=cv, scoring="neg_root_mean_squared_error", n_jobs=1
        )
        mae_scores = -cross_val_score(
            pipe, X, y, cv=cv, scoring="neg_mean_absolute_error", n_jobs=1
        )
        metrics = {
            "model": name,
            "cv_r2_mean": float(np.mean(r2_scores)),
            "cv_r2_std": float(np.std(r2_scores)),
            "cv_rmse_mean": float(np.mean(rmse_scores)),
            "cv_mae_mean": float(np.mean(mae_scores)),
        }
        logger.info(f"[regressor] {name}: R2={metrics['cv_r2_mean']:.3f}  "
                    f"RMSE={metrics['cv_rmse_mean']:.1f}  MAE={metrics['cv_mae_mean']:.1f}")
        if best_metrics is None or metrics["cv_r2_mean"] > best_metrics["cv_r2_mean"]:
            best_name, best_pipe, best_metrics = name, pipe, metrics

    if best_pipe is None:
        raise RuntimeError("Regressor training failed for all candidates")

    # final fit on full data + held-out evaluation
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
    best_pipe.fit(X_tr, y_tr)
    y_pred = best_pipe.predict(X_te)
    best_metrics["holdout_r2"] = float(r2_score(y_te, y_pred))
    best_metrics["holdout_rmse"] = float(np.sqrt(mean_squared_error(y_te, y_pred)))
    best_metrics["holdout_mae"] = float(mean_absolute_error(y_te, y_pred))

    # refit on all data for production
    best_pipe.fit(X, y)
    best_metrics["selected"] = best_name
    best_metrics["acceptance_threshold_r2"] = 0.55
    best_metrics["passes_threshold"] = best_metrics["cv_r2_mean"] > 0.55
    return best_pipe, best_metrics


def _train_classifier(X: pd.DataFrame, y: pd.Series) -> Tuple[Pipeline, Dict[str, Any]]:
    candidates = {
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=2,
            class_weight="balanced", random_state=42, n_jobs=-1,
        ),
        "logistic": LogisticRegression(
            multi_class="multinomial", solver="lbfgs", max_iter=2000,
            class_weight="balanced", random_state=42,
        ),
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    best_name, best_pipe, best_metrics = None, None, None
    for name, est in candidates.items():
        pipe = Pipeline([("pre", _build_preprocessor()), ("model", est)])
        try:
            f1_scores = cross_val_score(pipe, X, y, cv=cv, scoring="f1_weighted", n_jobs=1)
        except Exception as exc:
            logger.warning(f"Classifier {name} failed CV: {exc}")
            continue
        metrics = {
            "model": name,
            "cv_f1_weighted_mean": float(np.mean(f1_scores)),
            "cv_f1_weighted_std": float(np.std(f1_scores)),
        }
        logger.info(f"[classifier] {name}: weighted F1={metrics['cv_f1_weighted_mean']:.3f}")
        if best_metrics is None or metrics["cv_f1_weighted_mean"] > best_metrics["cv_f1_weighted_mean"]:
            best_name, best_pipe, best_metrics = name, pipe, metrics

    if best_pipe is None:
        raise RuntimeError("Classifier training failed for all candidates")

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    best_pipe.fit(X_tr, y_tr)
    y_pred = best_pipe.predict(X_te)
    best_metrics["holdout_f1_weighted"] = float(f1_score(y_te, y_pred, average="weighted"))

    # one-vs-rest AUC if at least 2 classes appear in test
    try:
        proba = best_pipe.predict_proba(X_te)
        classes = best_pipe.named_steps["model"].classes_
        # binarise y_te
        y_te_bin = pd.get_dummies(y_te).reindex(columns=classes, fill_value=0)
        auc = roc_auc_score(y_te_bin.values, proba, multi_class="ovr", average="weighted")
        best_metrics["holdout_auc_ovr_weighted"] = float(auc)
    except Exception as exc:
        logger.warning(f"AUC computation failed: {exc}")
        best_metrics["holdout_auc_ovr_weighted"] = None

    # refit on all data
    best_pipe.fit(X, y)
    best_metrics["selected"] = best_name
    best_metrics["acceptance_threshold_f1"] = 0.65
    best_metrics["passes_threshold"] = best_metrics["cv_f1_weighted_mean"] > 0.65
    best_metrics["classes"] = list(best_pipe.named_steps["model"].classes_)
    return best_pipe, best_metrics


async def main(use_existing_csv: bool = False, exclude_synthetic: bool = False) -> Dict[str, Any]:
    csv_path = ARTIFACTS_DIR / "feature_matrix.csv"

    if use_existing_csv and csv_path.exists():
        logger.info(f"Reusing existing feature matrix at {csv_path}")
        matrix = pd.read_csv(csv_path)
    else:
        matrix = await build_feature_matrix(include_synthetic=not exclude_synthetic)

    target_cols = ["__target_tds__", "__target_class__", "__sample_id__",
                   "__well_id__", "__sampled_at__", "__synthetic__"]
    X = matrix[ALL_FEATURES].copy()
    y_reg = matrix["__target_tds__"].astype(float)
    y_clf = matrix["__target_class__"].astype(str)

    logger.info(f"Training set: {len(X)} rows × {X.shape[1]} features")
    logger.info(f"Class distribution: {y_clf.value_counts().to_dict()}")

    reg_pipe, reg_metrics = _train_regressor(X, y_reg)
    clf_pipe, clf_metrics = _train_classifier(X, y_clf)

    reg_path = ARTIFACTS_DIR / "tds_regressor.joblib"
    clf_path = ARTIFACTS_DIR / "contamination_classifier.joblib"
    joblib.dump(reg_pipe, reg_path)
    joblib.dump(clf_pipe, clf_path)

    # rewrite feature metadata so MLPredictionService picks up exact schema
    meta = feature_schema()
    meta["row_count"] = int(len(X))
    meta["regressor_path"] = str(reg_path.name)
    meta["classifier_path"] = str(clf_path.name)
    (ARTIFACTS_DIR / "feature_metadata.json").write_text(json.dumps(meta, indent=2))

    metrics = {
        "regressor": reg_metrics,
        "classifier": clf_metrics,
        "n_samples": int(len(X)),
        "feature_count": len(ALL_FEATURES),
    }
    (ARTIFACTS_DIR / "training_metrics.json").write_text(
        json.dumps(metrics, indent=2, default=str)
    )

    logger.info(f"TDS regressor saved -> {reg_path}")
    logger.info(f"Classifier saved    -> {clf_path}")
    logger.info(f"Metrics saved       -> {ARTIFACTS_DIR / 'training_metrics.json'}")
    return metrics


def _cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-existing-csv", action="store_true",
                        help="Skip DB query, reuse feature_matrix.csv")
    parser.add_argument("--exclude-synthetic", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(use_existing_csv=args.use_existing_csv,
                     exclude_synthetic=args.exclude_synthetic))


if __name__ == "__main__":
    _cli()
