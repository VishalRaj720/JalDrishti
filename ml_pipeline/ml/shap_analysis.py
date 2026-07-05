"""
ml_pipeline.ml.shap_analysis  (PHASE 3 -- interpretability)
=========================================================
SHAP feature attribution for the trained surrogate: which physics drivers move
plume area and excursion risk. Robust to XGBoost multi-quantile output (takes
the P50 head) and falls back to gain importance if SHAP can't run.

Run:  python -m ml_pipeline.ml.shap_analysis
Out:  ml/artifacts/shap_top_<model>.json  (+ optional PNG if matplotlib present)
"""
from __future__ import annotations

import json
import numpy as np
import pandas as pd
import joblib

from ml_pipeline.ml.dataset import load_training_frame, MODEL_FEATURES, ARTIFACT_DIR

SAMPLE_N = 1200


def _mean_abs_shap(model, X: pd.DataFrame, p50_index: int | None = None) -> np.ndarray:
    """mean(|SHAP|) per feature; handles 2D/3D shap output and classifiers."""
    import shap
    expl = shap.TreeExplainer(model)
    sv = expl.shap_values(X)
    arr = np.asarray(sv)
    if arr.ndim == 3:                      # (n, features, outputs) multi-quantile
        idx = p50_index if p50_index is not None else arr.shape[2] // 2
        arr = arr[:, :, idx]
    return np.abs(arr).mean(axis=0)


def importance_for(model, X, name, p50_index=None) -> dict:
    try:
        imp = _mean_abs_shap(model, X, p50_index)
        method = "shap_mean_abs"
    except Exception as e:                  # graceful fallback
        imp = np.asarray(model.feature_importances_, dtype=float)
        method = f"gain_fallback ({type(e).__name__})"
    order = np.argsort(imp)[::-1]
    top = [{"feature": MODEL_FEATURES[i], "importance": round(float(imp[i]), 5)}
           for i in order[:10]]
    return {"model": name, "method": method, "top10": top}


def run():
    df = load_training_frame()
    X = df[MODEL_FEATURES].astype(float).sample(min(SAMPLE_N, len(df)), random_state=0)

    jobs = {
        "area_p50": (joblib.load(ARTIFACT_DIR / "band_affected_area_ha_p50.joblib"), None),
        "migration_p50": (joblib.load(ARTIFACT_DIR / "band_max_migration_distance_m_p50.joblib"), None),
        "excursion_probability": (joblib.load(ARTIFACT_DIR / "pex_regressor.joblib"), None),
    }
    results = {}
    for name, (model, p50) in jobs.items():
        res = importance_for(model, X, name, p50)
        results[name] = res
        (ARTIFACT_DIR / f"shap_top_{name}.json").write_text(json.dumps(res, indent=2))
        print(f"\n[{name}] ({res['method']})")
        for r in res["top10"][:8]:
            print(f"   {r['feature']:26s} {r['importance']:.4f}")

    # optional bar chart of the excursion drivers
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        res = results["excursion_probability"]["top10"][::-1]
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.barh([r["feature"] for r in res], [r["importance"] for r in res], color="#c0392b")
        ax.set_title("SHAP drivers of excursion probability")
        ax.set_xlabel("mean(|SHAP|)")
        fig.tight_layout()
        fig.savefig(ARTIFACT_DIR / "shap_excursion_probability.png", dpi=130)
        print(f"\nplot -> {ARTIFACT_DIR / 'shap_excursion_probability.png'}")
    except Exception as e:
        print(f"\n(plot skipped: {type(e).__name__})")


if __name__ == "__main__":
    run()
