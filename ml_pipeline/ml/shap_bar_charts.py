"""
ml_pipeline.ml.shap_bar_charts  (interpretability -- all 10 trained models)
============================================================================
Computes mean(|SHAP|) feature importance for every deployed model --
3 band targets (affected_area_ha, max_migration_distance_m, compliance_conc)
x 3 quantiles (p10/p50/p90) + the excursion_probability point regressor --
and saves one horizontal bar chart per model to ml_pipeline/outputs/shap_charts/.

Run:  python -m ml_pipeline.ml.shap_bar_charts
Out:  outputs/shap_charts/shap_<target>_<band>.png  (10 PNGs)
      outputs/shap_charts/shap_top_features.json    (raw top-15 per model)
"""
from __future__ import annotations

import json
import joblib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap

from ml_pipeline.ml.dataset import (
    load_training_frame, MODEL_FEATURES, BAND_TARGETS, BANDS, POINT_TARGET,
    ARTIFACT_DIR,
)

SAMPLE_N = 1200
TOP_N = 15
OUT_DIR = ARTIFACT_DIR.parents[1] / "outputs" / "shap_charts"

BAR_COLOR = "#1B6E8C"       # teal, matches the dashboard palette
POINT_COLOR = "#C0392B"     # rust, for the excursion-probability model


def mean_abs_shap(model, X) -> np.ndarray:
    """mean(|SHAP|) per feature for a single-output XGBRegressor."""
    expl = shap.TreeExplainer(model)
    sv = np.asarray(expl.shap_values(X))
    if sv.ndim == 3:            # defensive: some SHAP/XGBoost combos add a
        sv = sv[:, :, 0]        # trailing singleton output axis
    return np.abs(sv).mean(axis=0)


def bar_chart(top, title, path, color):
    top = top[::-1]             # largest importance at the top of the barh
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.barh([r["feature"] for r in top], [r["importance"] for r in top], color=color)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("mean(|SHAP value|)")
    ax.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_training_frame()
    X = df[MODEL_FEATURES].astype(float).sample(min(SAMPLE_N, len(df)), random_state=0)

    all_results = {}

    for target in BAND_TARGETS:
        for band in BANDS:
            name = f"{target}_{band}"
            model_path = ARTIFACT_DIR / f"band_{target}_{band}.joblib"
            model = joblib.load(model_path)
            imp = mean_abs_shap(model, X)
            order = np.argsort(imp)[::-1]
            top = [{"feature": MODEL_FEATURES[i], "importance": round(float(imp[i]), 5)}
                   for i in order[:TOP_N]]
            all_results[name] = top

            title = f"SHAP drivers -- {target} ({band.upper()})"
            out_path = OUT_DIR / f"shap_{name}.png"
            bar_chart(top, title, out_path, BAR_COLOR)
            print(f"[{name}] -> {out_path.name}")
            for r in top[:6]:
                print(f"    {r['feature']:26s} {r['importance']:.4f}")

    # point model: excursion_probability
    model = joblib.load(ARTIFACT_DIR / "pex_regressor.joblib")
    imp = mean_abs_shap(model, X)
    order = np.argsort(imp)[::-1]
    top = [{"feature": MODEL_FEATURES[i], "importance": round(float(imp[i]), 5)}
           for i in order[:TOP_N]]
    all_results[POINT_TARGET] = top
    out_path = OUT_DIR / f"shap_{POINT_TARGET}.png"
    bar_chart(top, f"SHAP drivers -- {POINT_TARGET}", out_path, POINT_COLOR)
    print(f"[{POINT_TARGET}] -> {out_path.name}")
    for r in top[:6]:
        print(f"    {r['feature']:26s} {r['importance']:.4f}")

    (OUT_DIR / "shap_top_features.json").write_text(json.dumps(all_results, indent=2))
    print(f"\nDONE -> {OUT_DIR}  ({len(all_results)} models, {TOP_N} features each)")


if __name__ == "__main__":
    run()
