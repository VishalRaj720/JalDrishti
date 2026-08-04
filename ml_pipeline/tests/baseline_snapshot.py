"""
Baseline snapshot harness (remediation Phase 0) -- NOT a pytest test.
=====================================================================
Records the served answer at a fixed pin/species/time grid so a physics change
can be judged as "the intended shift" rather than "something moved". Run it
BEFORE the remediation and again AFTER; diff the two JSON files.

    myvenv/Scripts/python.exe -m ml_pipeline.tests.baseline_snapshot --out pre
    myvenv/Scripts/python.exe -m ml_pipeline.tests.baseline_snapshot --out post

Deliberately a script, not a test: it has no assertions and its numbers are
expected to change. The pinned regressions live in test_physics_laws.py.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from ml_pipeline.dashboard.resolve import resolve_inputs
from ml_pipeline.ml.dataset import ARTIFACT_DIR
from ml_pipeline.ml.predict import predict, predict_analytical

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"

# (label, lon, lat) -- chosen to span the tiers and to straddle the two seams
# measured in review.md section 2 (findings 5 and 6).
PINS = [
    ("jaduguda_deposit", 86.347, 22.652),
    ("mid_belt", 86.25, 22.63),
    ("ranchi_non_ore", 85.33, 23.36),
    ("dhanbad_non_ore", 86.43, 23.80),
    ("belt_edge_inside", 86.347, 22.6939),
    ("belt_edge_outside", 86.347, 22.6948),
]
SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")
TIMES_YEARS = (2.0, 10.0, 20.0)


def _one(lon: float, lat: float, species: str, t_years: float) -> dict:
    inputs, hydro = resolve_inputs({"lon": lon, "lat": lat, "species": species,
                                    "time_years": t_years})
    a = predict_analytical(**inputs)
    field = a.pop("_field")
    fm = field.metrics
    row = {
        # resolved inputs that drive everything downstream
        "regime": inputs["regime"],
        "K_m_day": round(float(inputs["K_m_day"]), 5),
        "thickness_m": round(float(inputs["thickness_m"]), 2),
        "Kd_L_kg": round(float(inputs["kd_L_kg"]), 4),
        "beta": round(float(inputs["beta"]), 3),
        "C0": round(float(inputs["source_conc_C0"]), 3),
        "Cb": round(float(inputs["background_conc_Cb"]), 3),
        "ore_zone": hydro["ore_zone"]["zone"],
        "u_suppressed": bool(hydro["u_suppressed"]),
        # analytical answer
        "area_ha": round(float(a["area_ha"]["p50"]), 4),
        "migration_m": round(float(a["migration_m"]["p50"]), 3),
        "max_downgradient_m": round(float(fm["max_downgradient_m"]), 3),
        "plume_halfwidth_m": round(float(fm["plume_halfwidth_m"]), 3),
        "Xc_m": round(float(a["Xc_m"]), 5),
        "compliance_conc": round(float(a["compliance_conc"]["p50"]), 4),
        "peak_conc": round(float(fm["peak_conc"]), 3),
        "excursion_probability": round(float(a["excursion_probability"]), 4),
        "off_scale": bool(fm["off_scale"]),
        "restoration": a.get("restoration"),
    }
    try:
        m = predict("ml", **inputs)
        row["ml"] = {
            k: {b: round(float(m[k][b]), 4) for b in ("p10", "p50", "p90")}
            for k in ("area_ha", "migration_m", "compliance_conc")
        }
        row["ml"]["excursion_probability"] = round(float(m["excursion_probability"]), 4)
    except Exception as e:                                   # artifacts absent
        row["ml"] = f"unavailable: {type(e).__name__}: {e}"
    return row


def snapshot() -> dict:
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        head = None

    def _read(name):
        try:
            return json.loads((ARTIFACT_DIR / name).read_text())
        except (OSError, ValueError):
            return None

    metrics = _read("metrics.json") or {}
    card = _read("model_card.json") or {}
    results = {}
    for label, lon, lat in PINS:
        for sp in SPECIES:
            for t in TIMES_YEARS:
                key = f"{label}|{sp}|t{t:g}"
                try:
                    results[key] = _one(lon, lat, sp, t)
                except Exception as e:
                    results[key] = {"error": f"{type(e).__name__}: {e}"}
                print(f"  {key}", flush=True)
    return {
        "git_head": head,
        "pins": [{"label": l, "lon": lo, "lat": la} for l, lo, la in PINS],
        "species": list(SPECIES),
        "times_years": list(TIMES_YEARS),
        "model_card": {k: card.get(k) for k in
                       ("version", "features", "band_targets", "training_envelope",
                        "hydro_support")},
        "metrics_summary": {
            t: {"r2_p50": b.get("r2", {}).get("p50"),
                "r2_log": b.get("r2_log"),
                "r2_log_by_species": b.get("r2_log_by_species"),
                "coverage_scenarios": b.get("coverage", {}).get("scenarios_eval")}
            for t, b in (metrics.get("bands") or {}).items()},
        "pex_metrics": metrics.get("pex"),
        "results": results,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="pre", choices=("pre", "post"),
                    help="writes outputs/baseline_{pre,post}_remediation.json")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"baseline_{args.out}_remediation.json"
    snap = snapshot()
    path.write_text(json.dumps(snap, indent=2))
    print(f"\nwrote {path}  ({len(snap['results'])} rows)")
    j = snap["results"]["jaduguda_deposit|uranium_ppb|t10"]
    print(f"GATE CHECK  Jaduguda U t=10:  migration_m={j['migration_m']}  "
          f"max_downgradient_m={j['max_downgradient_m']}  Xc_m={j['Xc_m']}")
