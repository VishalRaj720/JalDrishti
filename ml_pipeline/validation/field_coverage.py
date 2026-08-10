"""
ml_pipeline.validation.field_coverage  --  the gate review2.md V-5 found missing
==============================================================================
Split-conformal prediction guarantees coverage only under EXCHANGEABILITY between
the calibration data and the data actually queried. This surrogate calibrates on
a random half of the GENERATOR's scenarios, and the generator does not sample the
distribution users query: measured 2026-08-05, its median hydraulic gradient ran
1.35x the real Jharkhand flow-field median and its p90 ran 2.02x.

`E1_geometry_design.md` Section 6, gate 5 anticipated exactly this and mandated a
"FIELD-RESAMPLED coverage batch: ~100 scenarios pinned to real grid cells with
real V/gradient/amp; scenario coverage must hold >= 0.80 THERE". No artifact,
test or metrics field ever recorded that gate being run against a deployed model
(review2.md V-5), while the UI stated "parameter uncertainty - 80% conformal"
without qualification.

This module runs it. `--field-mix 1.0` pins EVERY scenario's gradient, seasonal
amplitude and fracture-dispersion V to the real field at its own jittered pin, so
the batch is drawn from the serving distribution. The batch is baked fresh and is
therefore a genuine hold-out: no row of it was seen in training or calibration.

Reported the same way the training gate is: scenario-level coverage (max score
over a scenario's rows) per Mondrian cell, against the deltas stored in the
deployed model card. If it fails, the honest fix is to widen the deltas -- NOT to
lower the gate.

Run:
    python -m ml_pipeline.synthetic.generate --scenarios 120 --mc 48 \
        --field-mix 1.0 --out ml_pipeline/outputs/field_batch.csv
    python -m ml_pipeline.validation.field_coverage
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib

from ml_pipeline.ml.dataset import (MODEL_FEATURES, ARTIFACT_DIR, BANDS,
                                    BAND_TARGETS, censor_mask, mondrian_cells,
                                    GROUP_COL, load_training_frame)

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
DEFAULT_BATCH = OUT_DIR / "field_batch.csv"
COVERAGE_GATE = 0.80


def _load_models(target: str, artifact_dir: Path) -> dict:
    return {b: joblib.load(artifact_dir / f"band_{target}_{b}.joblib") for b in BANDS}


def evaluate(batch_csv: Path = DEFAULT_BATCH,
             artifact_dir: Path = ARTIFACT_DIR) -> dict:
    # load_training_frame, NOT read_csv: the generator writes a `species` column
    # but not the per-species one-hot columns MODEL_FEATURES expects -- the
    # loader derives them. Reading the CSV raw silently loses four features.
    df = load_training_frame(batch_csv)
    card = json.loads((artifact_dir / "model_card.json").read_text())
    # field_mix must be 1.0 for this to be the serving-distribution gate; read it
    # from the batch's own meta rather than assuming, so a batch baked at the
    # default 0.60 cannot be mistaken for the gate.
    meta_path = batch_csv.with_name(batch_csv.stem + "_meta.json")
    field_mix = (json.loads(meta_path.read_text()).get("field_mix_frac")
                 if meta_path.exists() else None)
    out = {"batch": str(batch_csv.name), "n_rows": int(len(df)),
           "n_scenarios": int(df[GROUP_COL].nunique()),
           "field_mix": field_mix, "is_serving_distribution": field_mix == 1.0,
           "gate": COVERAGE_GATE, "targets": {}}

    for target, cfg in BAND_TARGETS.items():
        sub = df[~censor_mask(df)] if cfg["censor_offscale"] else df
        X = sub[MODEL_FEATURES].astype(float)
        cells = mondrian_cells(sub).to_numpy()
        groups = sub[GROUP_COL].to_numpy()
        models = _load_models(target, artifact_dir)

        yt = {b: np.log1p(sub[f"{target}_{b}"].to_numpy()) for b in BANDS}
        pred = {b: models[b].predict(X) for b in BANDS}
        # SAME order of operations as serving: rearrange, then widen by the
        # stored Mondrian delta. Any other order would be measuring a model the
        # user never receives.
        lo = np.minimum(pred["p10"], pred["p50"])
        hi = np.maximum(pred["p90"], pred["p50"])
        deltas = card["deltas"][target]
        d_row = pd.Series(cells).map(deltas).fillna(0.0).to_numpy()

        covered = (lo - d_row <= yt["p10"]) & (yt["p90"] <= hi + d_row)
        E = np.maximum(lo - yt["p10"], yt["p90"] - hi)
        sc = (pd.DataFrame({"E": E, "cell": cells, "scen": groups})
              .groupby(["cell", "scen"])["E"].max().reset_index())
        cov_scen = float(np.mean(sc["E"].to_numpy()
                                 <= sc["cell"].map(deltas).fillna(0.0).to_numpy()))
        per_cell = {c: round(float(np.mean(covered[cells == c])), 3)
                    for c in np.unique(cells)}
        out["targets"][target] = {
            "rows": round(float(np.mean(covered)), 4),
            "scenarios": round(cov_scen, 4),
            "per_cell_rows": per_cell,
            "passes_gate": bool(cov_scen >= COVERAGE_GATE),
        }
    out["all_targets_pass"] = all(t["passes_gate"] for t in out["targets"].values())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=str, default=str(DEFAULT_BATCH))
    ap.add_argument("--write-metrics", action="store_true",
                    help="record the result in ml/artifacts/metrics.json")
    args = ap.parse_args()

    res = evaluate(Path(args.batch))
    print(f"FIELD-RESAMPLED COVERAGE  ({res['n_scenarios']} scenarios / "
          f"{res['n_rows']} rows, field_mix={res['field_mix']})")
    if res["field_mix"] != 1.0:
        print("  !! WARNING: field_mix != 1.0 -- this batch is NOT drawn from "
              "the serving distribution, so it does not satisfy the V-5 gate.")
    print(f"gate: scenario coverage >= {COVERAGE_GATE}\n")
    for target, t in res["targets"].items():
        flag = "PASS" if t["passes_gate"] else "**FAIL**"
        print(f"  {target:28s} rows={t['rows']:.4f}  scenarios={t['scenarios']:.4f}  {flag}")
        worst = min(t["per_cell_rows"].items(), key=lambda kv: kv[1])
        print(f"     weakest Mondrian cell: {worst[0]} = {worst[1]:.3f}")
    print(f"\nALL TARGETS PASS: {res['all_targets_pass']}")

    if args.write_metrics:
        mp = ARTIFACT_DIR / "metrics.json"
        m = json.loads(mp.read_text())
        m["field_resampled_coverage"] = res
        mp.write_text(json.dumps(m, indent=2))
        print(f"recorded in {mp}")
    return 0 if res["all_targets_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
