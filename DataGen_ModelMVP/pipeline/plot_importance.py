"""plot_importance.py — plot SHAP feature-importance bar charts for every model.

Reads the shap_*.json files produced by shap_analysis.py and saves one PNG per
model into artifacts/plots/.

Run:
    python -m pipeline.plot_importance
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # headless — no display needed
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from pipeline import ARTIFACTS_DIR

PLOTS_DIR = ARTIFACTS_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# Human-readable titles for each model tag
MODEL_TITLES = {
    "uranium_regressor":     "Uranium (ppb) — SHAP Feature Importance\n(RandomForest Regressor, log1p target)",
    "risk_classifier":       "Contamination Risk Class — SHAP Feature Importance\n(RandomForest Classifier, mean |SHAP| over classes)",
    "cotarget_tds_mg_l":     "TDS (mg/L) — SHAP Feature Importance\n(RandomForest Regressor, co-target)",
    "cotarget_sulfate_mg_l": "Sulfate (mg/L) — SHAP Feature Importance\n(RandomForest Regressor, co-target)",
    "cotarget_ph":           "pH — SHAP Feature Importance\n(RandomForest Regressor, co-target)",
}

# Colour per model family
MODEL_COLOURS = {
    "uranium_regressor":     "#2166ac",
    "risk_classifier":       "#d6604d",
    "cotarget_tds_mg_l":     "#4dac26",
    "cotarget_sulfate_mg_l": "#8073ac",
    "cotarget_ph":           "#e08214",
}


def _short_name(feature: str) -> str:
    """Shorten OHE suffixes like 'aquifer_type_sandstone' -> 'type: sandstone'."""
    replacements = {
        "aquifer_type_": "type: ",
        "season_": "season: ",
        "aquifer_": "",
        "_m2day": " (m²/day)",
        "_mday": " (m/day)",
        "_km": " (km)",
        "_pct": " (%)",
        "_mg_l": " (mg/L)",
        "_ppb": " (ppb)",
        "_gpm": " (gpm)",
        "_mm": " (mm)",
        "_m": " (m)",
    }
    name = feature
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name.replace("_", " ").strip()


def plot_model(tag: str, json_path: Path) -> Path:
    data = json.loads(json_path.read_text())
    features = [_short_name(e["feature"]) for e in data["top_features"]]
    values   = [e["shap_mean_abs"] for e in data["top_features"]]
    method   = data.get("method", "")

    # Reverse so highest bar is at the top
    features = features[::-1]
    values   = values[::-1]

    colour = MODEL_COLOURS.get(tag, "#555555")
    title  = MODEL_TITLES.get(tag, tag)

    fig, ax = plt.subplots(figsize=(9, max(4, len(features) * 0.45 + 1.5)))
    bars = ax.barh(features, values, color=colour, alpha=0.82, edgecolor="white", linewidth=0.5)

    # Value labels at the end of each bar
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max(values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.4f}",
            va="center", ha="left", fontsize=8, color="#333333",
        )

    ax.set_xlabel("Mean |SHAP value|" if "shap" in method else "Feature importance", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=12)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.4f"))
    ax.tick_params(axis="y", labelsize=9)
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlim(right=max(values) * 1.18)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    fig.text(
        0.99, 0.01,
        f"method: {method}",
        ha="right", va="bottom", fontsize=7, color="#888888",
    )

    fig.tight_layout()
    out = PLOTS_DIR / f"shap_{tag}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    shap_files = sorted(ARTIFACTS_DIR.glob("shap_*.json"))
    if not shap_files:
        print(f"No shap_*.json files found in {ARTIFACTS_DIR}.")
        print("Run  python -m pipeline.shap_analysis  first.")
        return

    print(f"Plotting {len(shap_files)} model(s) -> {PLOTS_DIR}")
    for json_path in shap_files:
        tag = json_path.stem[len("shap_"):]   # strip leading "shap_"
        out = plot_model(tag, json_path)
        print(f"  {tag:30} -> {out.name}")

    print("Done.")


if __name__ == "__main__":
    main()
