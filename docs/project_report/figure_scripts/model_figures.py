"""Confusion matrices and SHAP plots for each of the ten served surrogate models.

    python -m ml_pipeline.synthetic.generate --scenarios 900 --mc 48      # at commit 9d0fd67
    python docs/project_report/figure_scripts/model_figures.py --csv <synthetic_training.csv>

The served models (ml_pipeline/ml/artifacts, model card version 6) are regressors, so a
confusion matrix needs classes. Each one uses the threshold the product itself applies:

    excursion probability   >= 0.5 at the monitoring ring    (the `alert` tier, alert_tiers.py)
    ring concentration      above the IS 10500 limit of the chemical  (model card bis_thresholds)
    travel distance         inside the 100 m monitoring ring / 100-500 m / beyond 500 m
    footprint area          < 10 ha (about the leach zone) / 10-30 ha / >= 30 ha   (display bins)

HONESTY RULES
  * The CSV must be the v6 training file: its SHA-256 must match the model card, or (a re-bake
    on another machine) its bake metadata must match exactly AND the out-of-fold R² (log scale)
    must reproduce metrics.json within R2_TOL. Engine floats differ slightly across platforms,
    so a re-bake is the same dataset statistically, not byte for byte.
  * Confusion matrices use OUT-OF-FOLD predictions from the trainer's own GroupKFold(5) on
    scenario_id, with the trainer's own model constructor, so no row is scored by a model that
    saw its scenario. The reproduced P50 R² is checked against metrics.json before plotting.
  * P10/P90 heads are scored against the engine's own Monte Carlo P10/P90 labels, after the
    trainer's re-arrangement (lo = min(P10, P50), hi = max(P90, P50)) and before conformal
    widening, so they show what the heads learn, not the served (wider) band.
  * SHAP values come from the SERVED models (fitted on all rows), on every training row, computed
    with XGBoost's own exact TreeSHAP (pred_contribs).

Writes figures/cm_<target>.png, figures/shap_<target>.png and figures/model_evaluation.json.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import joblib                                                    # noqa: E402
import matplotlib                                                # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap            # noqa: E402
from sklearn.metrics import r2_score                             # noqa: E402
from sklearn.model_selection import GroupKFold                   # noqa: E402

from ml_pipeline.ml.dataset import (ARTIFACT_DIR, BAND_TARGETS, BANDS, GROUP_COL,   # noqa: E402
                                    MODEL_FEATURES, POINT_TARGET, censor_mask,
                                    load_training_frame)
from ml_pipeline.ml.train import N_SPLITS, _model                # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "figures"
# The re-baked file reproduces the model card's skill to within this (log-scale R², the
# card's headline metric; the pooled raw R² swings with a handful of very large plumes).
R2_TOL = 0.01
JOBS = 2      # XGBoost threads; set with --jobs. All cores at once can stall on a busy machine.


def model(target, band="p50"):
    """The trainer's own model constructor, with a thread count that cannot oversubscribe."""
    return _model(target, band).set_params(n_jobs=JOBS)

# palette: one-hue sequential ramp for magnitude; three validated categorical slots for the heads
SEQ = LinearSegmentedColormap.from_list("seq", ["#f4f8fd", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])
HEAD_COLOUR = {"p10": "#2a78d6", "p50": "#eb6834", "p90": "#1baf7a"}
INK, MUTED, GRID = "#1f1f1f", "#5f5f5f", "#d9d9d9"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.titlesize": 10, "axes.titleweight": "bold"})

TITLE = {"affected_area_ha": "Footprint area", "max_migration_distance_m": "Travel distance",
         "compliance_conc": "Ring concentration", POINT_TARGET: "Excursion probability"}
FILE = {"affected_area_ha": "area", "max_migration_distance_m": "migration",
        "compliance_conc": "ring", POINT_TARGET: "excursion"}


def classes_for(target, values, species, limits):
    """Class index and labels for a target, using the product's own thresholds."""
    v = np.asarray(values, dtype=float)
    if target == "affected_area_ha":
        return np.digitize(v, [10.0, 30.0]), ["< 10 ha", "10–30 ha", "≥ 30 ha"]
    if target == "max_migration_distance_m":
        return np.digitize(v, [100.0, 500.0]), ["< 100 m\n(inside ring)", "100–500 m", "≥ 500 m"]
    if target == "compliance_conc":
        lim = np.array([limits[s] for s in species])
        return (v > lim).astype(int), ["within\nIS 10500 limit", "above\nIS 10500 limit"]
    if target == POINT_TARGET:
        return (v >= 0.5).astype(int), ["< 0.5\n(notice)", "≥ 0.5\n(alert tier)"]
    raise ValueError(target)


def confusion(true_c, pred_c, k):
    m = np.zeros((k, k), dtype=int)
    np.add.at(m, (true_c, pred_c), 1)
    return m


def balanced(m):
    """Mean recall over the classes the engine actually produced; plain accuracy flatters a
    model when most rows fall in one class (most plumes stay inside the ring)."""
    rows = m.sum(axis=1)
    return float(np.mean([m[i, i] / rows[i] for i in range(len(rows)) if rows[i] > 0]))


def draw_matrix(ax, m, labels, title):
    rows = m.sum(axis=1, keepdims=True)
    share = np.divide(m, rows, out=np.zeros_like(m, dtype=float), where=rows > 0)
    ax.imshow(share, cmap=SEQ, vmin=0, vmax=1)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            dark = share[i, j] > 0.55
            ax.text(j, i, f"{m[i, j]:,}\n{100 * share[i, j]:.1f}%", ha="center", va="center",
                    fontsize=8, color="white" if dark else INK)
    k = len(labels)
    ax.set_xticks(range(k), labels, fontsize=7.5)
    ax.set_yticks(range(k), labels, fontsize=7.5)
    ax.set_xlabel("Surrogate (out-of-fold)")
    ax.set_ylabel("Physics engine")
    acc = np.trace(m) / m.sum()
    bal = balanced(m)
    ax.set_title(f"{title}\naccuracy {100 * acc:.1f}%  ·  balanced {100 * bal:.1f}%", fontsize=9)
    for s in ax.spines.values():
        s.set_visible(False)


def oof_bands(df, target, cfg):
    """Replicates train.train_band_target's cross-validation exactly."""
    sub = df[~censor_mask(df)] if cfg["censor_offscale"] else df
    X = sub[MODEL_FEATURES].astype(float)
    groups = sub[GROUP_COL].to_numpy()
    yt = {b: np.log1p(sub[f"{target}_{b}"].to_numpy()) for b in BANDS}
    oof = {b: np.full(len(sub), np.nan) for b in BANDS}
    for tr, te in GroupKFold(n_splits=N_SPLITS).split(X, yt["p50"], groups):
        for b in BANDS:
            oof[b][te] = model(target, b).fit(X.iloc[tr], yt[b][tr]).predict(X.iloc[te])
    lo, hi = np.minimum(oof["p10"], oof["p50"]), np.maximum(oof["p90"], oof["p50"])
    pred = {"p10": lo, "p50": oof["p50"], "p90": hi}
    r2_log = r2_score(yt["p50"], oof["p50"])
    truth = {b: np.expm1(yt[b]) for b in BANDS}
    pred = {b: np.clip(np.expm1(p), 0, None) for b, p in pred.items()}
    return sub, truth, pred, r2_log


def oof_point(df):
    X = df[MODEL_FEATURES].astype(float)
    y = df[POINT_TARGET].astype(float).to_numpy()
    groups = df[GROUP_COL].to_numpy()
    oof = np.full(len(y), np.nan)
    for tr, te in GroupKFold(n_splits=N_SPLITS).split(X, y, groups):
        oof[te] = np.clip(model(POINT_TARGET).fit(X.iloc[tr], y[tr]).predict(X.iloc[te]), 0, 1)
    return y, oof, r2_score(y, oof)


def shap_values(model, X):
    """Exact TreeSHAP from XGBoost itself (pred_contribs); the last column, the bias, is dropped.
    The shap package's own XGBoost loader cannot read xgboost 3.x's base_score format."""
    import xgboost as xgb
    booster = model.get_booster()
    booster.set_param({"nthread": JOBS})
    contribs = booster.predict(xgb.DMatrix(X, feature_names=list(X.columns)), pred_contribs=True)
    return np.asarray(contribs)[:, :-1]


def draw_beeswarm(ax, sv, X, top, title, xlabel):
    """Beeswarm by hand (one axis, sequential colour for the feature value)."""
    rng = np.random.default_rng(0)
    order = np.argsort(np.abs(sv).mean(axis=0))[::-1][:top]
    for row, f in enumerate(order[::-1]):
        vals = X.iloc[:, f].to_numpy(dtype=float)
        lo, hi = np.nanpercentile(vals, [5, 95])
        norm = np.clip((vals - lo) / (hi - lo if hi > lo else 1.0), 0, 1)
        x = sv[:, f]
        # vertical jitter scaled by local density so the swarm shows where the mass is
        hist, edges = np.histogram(x, bins=60)
        dens = hist[np.clip(np.digitize(x, edges) - 1, 0, 59)] / max(hist.max(), 1)
        y = row + (rng.random(len(x)) - 0.5) * 0.8 * np.sqrt(dens)
        ax.scatter(x, y, c=norm, cmap=SEQ, s=2.2, linewidths=0, rasterized=True)
    ax.set_yticks(range(top), [X.columns[f] for f in order[::-1]], fontsize=7.5)
    ax.axvline(0, color=GRID, lw=0.8, zorder=0)
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=9)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    return order


def draw_head_bars(ax, imp, top):
    """mean |SHAP| of the top features for the three heads of one target."""
    p50 = imp["p50"]
    order = np.argsort(p50)[::-1][:top]
    y = np.arange(top)[::-1]
    h = 0.26
    for k, b in enumerate(("p10", "p50", "p90")):
        ax.barh(y + (1 - k) * h, imp[b][order], height=h - 0.03, color=HEAD_COLOUR[b],
                label=b.upper(), edgecolor="white", linewidth=0.6)
    ax.set_yticks(y, [MODEL_FEATURES[i] for i in order], fontsize=7.5)
    ax.set_xlabel("mean |SHAP| (log-target units)")
    ax.set_title("Mean |SHAP| of the P10, P50 and P90 models", fontsize=9)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)


def colourbar(fig, ax):
    sm = plt.cm.ScalarMappable(cmap=SEQ)
    cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02, ticks=[0, 1])
    cb.ax.set_yticklabels(["low", "high"], fontsize=7)
    cb.set_label("feature value", fontsize=7.5)
    cb.outline.set_visible(False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--jobs", type=int, default=JOBS)
    args = ap.parse_args()
    globals()["JOBS"] = args.jobs

    card = json.loads((ARTIFACT_DIR / "model_card.json").read_text())
    metrics = json.loads((ARTIFACT_DIR / "metrics.json").read_text())
    sha = hashlib.sha256(args.csv.read_bytes()).hexdigest()
    want = card["reproducibility"]["training_csv_sha256"]
    identity = "sha256"
    if sha != want:
        # A re-bake on another machine changes the bytes (engine floats differ slightly across
        # platforms) without changing the dataset's design. Accept it only if every recorded property of the
        # bake (counts, regime mix, mean excursion probability per species, thresholds, ...)
        # equals the model card's; the out-of-fold R2 check below then has to reproduce
        # metrics.json within R2_TOL, or the script stops.
        meta_path = args.csv.with_name("synthetic_meta.json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        card_meta = card["reproducibility"]["bake_meta"]
        diff = [k for k in set(meta) | set(card_meta)
                if k != "git_sha" and meta.get(k) != card_meta.get(k)]
        if not meta or diff:
            raise SystemExit(f"{args.csv} is not the v{card['version']} training file "
                             f"(sha256 {sha[:12]}..., model card {want[:12]}...; meta differs: {diff})")
        identity = "bake metadata + reproduced cross-validation (bytes differ)"
        print(f"note: sha256 differs from the model card; {identity}")
    limits = card["reproducibility"]["bake_meta"]["bis_thresholds"]
    df = load_training_frame(args.csv)
    X_all = df[MODEL_FEATURES].astype(float)
    report = {"model_card_version": card["version"], "training_csv_sha256": sha,
              "model_card_csv_sha256": want, "training_data_identity": identity,
              "rows": int(len(df)), "folds": N_SPLITS, "targets": {}}

    # ---- band targets: three heads each -------------------------------------------------
    for target, cfg in BAND_TARGETS.items():
        sub, truth, pred, r2 = oof_bands(df, target, cfg)
        ref = metrics["bands"][target]["r2_log"]
        print(f"{target}: reproduced OOF R2(log, P50) {r2:.4f}  vs metrics.json {ref:.4f}")
        if abs(r2 - ref) > R2_TOL or len(sub) != metrics["bands"][target]["n"]:
            raise SystemExit("cross-validation does not reproduce the trainer; stop")
        species = sub["species"].to_numpy()
        fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.7), constrained_layout=True)
        entry = {"n": int(len(sub)), "r2_log_p50_reproduced": round(float(r2), 4),
                 "r2_log_p50_model_card": ref, "heads": {}}
        for ax, b in zip(axes, BANDS):
            t_c, labels = classes_for(target, truth[b], species, limits)
            p_c, _ = classes_for(target, pred[b], species, limits)
            m = confusion(t_c, p_c, len(labels))
            draw_matrix(ax, m, labels, f"{b.upper()} model")
            entry["heads"][b] = {"labels": [l.replace("\n", " ") for l in labels],
                                 "matrix": m.tolist(),
                                 "accuracy": round(float(np.trace(m) / m.sum()), 4),
                                 "balanced_accuracy": round(balanced(m), 4)}
        fig.savefig(OUT / f"cm_{FILE[target]}.png", dpi=220)
        plt.close(fig)

        # SHAP from the served models
        Xs = sub[MODEL_FEATURES].astype(float)
        imp, sv50 = {}, None
        for b in BANDS:
            sv = shap_values(joblib.load(ARTIFACT_DIR / f"band_{target}_{b}.joblib"), Xs)
            imp[b] = np.abs(sv).mean(axis=0)
            if b == "p50":
                sv50 = sv
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.6), constrained_layout=True,
                                     gridspec_kw={"width_ratios": [1.15, 1]})
        draw_beeswarm(a1, sv50, Xs, 12, f"{TITLE[target]}: SHAP values of the P50 model",
                      "SHAP value (effect on log-target)")
        colourbar(fig, a1)
        draw_head_bars(a2, imp, 10)
        fig.savefig(OUT / f"shap_{FILE[target]}.png", dpi=220)
        plt.close(fig)
        entry["shap_top5"] = {b: [MODEL_FEATURES[i] for i in np.argsort(imp[b])[::-1][:5]]
                              for b in BANDS}
        report["targets"][target] = entry

    # ---- excursion probability ------------------------------------------------------------
    y, oof, r2 = oof_point(df)
    ref = metrics["pex"]["r2"]
    print(f"{POINT_TARGET}: reproduced OOF R2 {r2:.4f}  vs metrics.json {ref:.4f}")
    if abs(r2 - ref) > R2_TOL:
        raise SystemExit("cross-validation does not reproduce the trainer; stop")
    t_c, labels = classes_for(POINT_TARGET, y, None, limits)
    p_c, _ = classes_for(POINT_TARGET, oof, None, limits)
    m = confusion(t_c, p_c, 2)
    tn, fp, fn, tp = m.ravel()
    sv = shap_values(joblib.load(ARTIFACT_DIR / "pex_regressor.joblib"), X_all)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.2), constrained_layout=True,
                                 gridspec_kw={"width_ratios": [0.8, 1.2]})
    draw_matrix(a1, m, labels, "Excursion-probability model")
    draw_beeswarm(a2, sv, X_all, 12, "SHAP values of the excursion-probability model",
                  "SHAP value (effect on probability)")
    colourbar(fig, a2)
    fig.savefig(OUT / "cm_shap_excursion.png", dpi=220)
    plt.close(fig)
    report["targets"][POINT_TARGET] = {
        "n": int(len(y)), "r2_reproduced": round(float(r2), 4), "r2_model_card": ref,
        "labels": [l.replace("\n", " ") for l in labels], "matrix": m.tolist(),
        "accuracy": round(float((tn + tp) / m.sum()), 4),
        "balanced_accuracy": round(balanced(m), 4),
        "recall_alert": round(float(tp / (tp + fn)), 4) if tp + fn else None,
        "precision_alert": round(float(tp / (tp + fp)), 4) if tp + fp else None,
        "shap_top5": [MODEL_FEATURES[i] for i in np.argsort(np.abs(sv).mean(axis=0))[::-1][:5]],
    }
    (OUT / "model_evaluation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({t: (e.get("accuracy") or {b: h["accuracy"] for b, h in e["heads"].items()})
                      for t, e in report["targets"].items()}, indent=1))


if __name__ == "__main__":
    main()
