"""
ml_pipeline.ml.predict  (PHASE 3 -- inference API for the dashboard)
==================================================================
One module, two engines, identical output schema -- so the Phase-4 "Analytical
vs ML Surrogate" toggle is a one-line switch:

    out = predict(mode, **inputs)          # mode in {"analytical","ml"}
    out = {
       "area_ha":          {"p10","p50","p90"},
       "migration_m":      {"p10","p50","p90"},
       "compliance_conc":  {"p10","p50","p90"},
       "excursion_probability": float,
       "breach_probability":    float,
    }

ML path: XGBoost quantile heads + conformal calibration (fast, gives bands).
Analytical path: the Domenico engine + Monte-Carlo excursion (ground truth).

`inputs` are the same raw operating point the dashboard sliders produce:
  regime, K_m_day, gradient_i, phi_mobile, n_total, grain_density,
  kd_L_kg, beta, Q_in_m3_day, bleed_fraction, operation_years,
  wellfield_width_m, thickness_m, source_conc_C0, background_conc_Cb,
  species, time_years.
"""
from __future__ import annotations

import json
import functools
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from ml_pipeline.data_prep.feature_engineering import build_feature_row, FEATURE_COLUMNS
from ml_pipeline.physics.transport import simulate_plume, effective_travel_distance
from ml_pipeline.ml.dataset import MODEL_FEATURES, ARTIFACT_DIR, SPECIES_ONEHOT
from ml_pipeline.config import parameters as P

SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
COMPLIANCE_BUFFER_M = 100.0


# --------------------------------------------------------------------------- #
# Shared: raw inputs -> the model feature row (mirrors generate.label_row)
# --------------------------------------------------------------------------- #
def features_from_inputs(*, regime, K_m_day, gradient_i, phi_mobile, n_total,
                         grain_density, kd_L_kg, beta, Q_in_m3_day, bleed_fraction,
                         operation_years, wellfield_width_m, thickness_m,
                         source_conc_C0, background_conc_Cb, species,
                         time_years) -> tuple[pd.DataFrame, dict, float]:
    op_days = operation_years * 365.0
    t_days = time_years * 365.0
    feat = build_feature_row(
        regime=regime, domain_is_texas=False, K_m_day=K_m_day, gradient_i=gradient_i,
        phi_mobile=phi_mobile, n_total=n_total, grain_density=grain_density,
        kd_L_kg=kd_L_kg, beta=beta, Q_in_m3_day=Q_in_m3_day,
        bleed_fraction=bleed_fraction, operation_days=op_days,
        wellfield_width_m=wellfield_width_m, thickness_m=thickness_m,
        source_conc_C0=source_conc_C0, background_conc_Cb=background_conc_Cb)
    Xc = effective_travel_distance(feat["contaminant_velocity_vc"],
                                   feat["containment_eta"], t_days, op_days)
    row = {k: feat[k] for k in FEATURE_COLUMNS}
    row["Xc_m"] = Xc
    row["time_years"] = time_years
    row["is_post_closure"] = int(t_days > op_days)
    for sp in SPECIES:
        row[f"is_{sp}"] = int(species == sp)
    X = pd.DataFrame([row])[MODEL_FEATURES].astype(float)
    return X, feat, Xc


# --------------------------------------------------------------------------- #
# ML surrogate
# --------------------------------------------------------------------------- #
class MLSurrogate:
    def __init__(self, artifact_dir: Path = ARTIFACT_DIR):
        self.dir = Path(artifact_dir)
        self.card = json.loads((self.dir / "model_card.json").read_text())
        self.q_models = {t: joblib.load(self.dir / f"quantile_{t}.joblib")
                         for t in self.card["quantile_targets"]}
        self.pex = joblib.load(self.dir / "pex_regressor.joblib")
        self.breach = joblib.load(self.dir / "breach_classifier.joblib")
        self.log_targets = set(self.card["log_targets"])
        self.deltas = self.card["conformal_deltas"]

    def _quantiles(self, target, X):
        raw = np.asarray(self.q_models[target].predict(X))[0]   # [P10,P50,P90] transformed
        d = self.deltas[target]
        lo, mid, hi = raw[0] - d, raw[1], raw[2] + d            # conformal widen
        if target in self.log_targets:
            lo, mid, hi = np.expm1(lo), np.expm1(mid), np.expm1(hi)
        lo, mid, hi = (float(max(v, 0.0)) for v in (lo, mid, hi))
        # Multi-quantile heads can cross per-row; rearrange so P10<=P50<=P90
        # while keeping the median head as P50 (Chernozhukov et al. rearrangement).
        lo, hi = min(lo, mid), max(hi, mid)
        return {"p10": lo, "p50": mid, "p90": hi}

    def predict(self, **inputs) -> dict:
        X, _, _ = features_from_inputs(**inputs)
        return {
            "area_ha": self._quantiles("affected_area_ha", X),
            "migration_m": self._quantiles("max_migration_distance_m", X),
            "compliance_conc": self._quantiles("compliance_conc", X),
            "excursion_probability": float(np.clip(self.pex.predict(X)[0], 0, 1)),
            "breach_probability": float(self.breach.predict_proba(X)[0, 1]),
        }


@functools.lru_cache(maxsize=1)
def _surrogate() -> MLSurrogate:
    return MLSurrogate()


# --------------------------------------------------------------------------- #
# Analytical engine (same schema; deterministic central + MC excursion)
# --------------------------------------------------------------------------- #
def predict_analytical(*, n_mc: int = 24, seed: int = 0, **inputs) -> dict:
    species = inputs["species"]
    threshold = P.EXCURSION_THRESHOLDS[species]
    X, feat, Xc = features_from_inputs(**inputs)
    op_days = inputs["operation_years"] * 365.0
    t_days = inputs["time_years"] * 365.0
    x_comp = inputs["wellfield_width_m"] / 2.0 + COMPLIANCE_BUFFER_M

    res = simulate_plume(feat, species_C0=inputs["source_conc_C0"],
                         background=inputs["background_conc_Cb"], threshold=threshold,
                         t_days=t_days, operation_days=op_days, grid_n=200,
                         compliance_x=x_comp)
    m = res.metrics

    # excursion probability via the same parameter-uncertainty MC as Phase 2
    from ml_pipeline.synthetic.generate import excursion_probability
    scn = dict(width=inputs["wellfield_width_m"], regime=inputs["regime"],
               K=inputs["K_m_day"], phi_mobile=inputs["phi_mobile"],
               n_total=inputs["n_total"], grain_density=inputs["grain_density"],
               beta=inputs["beta"], gradient=inputs["gradient_i"],
               Q_in=inputs["Q_in_m3_day"], bleed=inputs["bleed_fraction"],
               thickness=inputs["thickness_m"],
               C0={species: inputs["source_conc_C0"]},
               Cb={species: inputs["background_conc_Cb"]})
    rng = np.random.default_rng(seed)
    p_ex = excursion_probability(scn, species, t_days, op_days, rng, n_mc)

    def pt(v):  # analytical is a point estimate -> degenerate band
        return {"p10": float(v), "p50": float(v), "p90": float(v)}
    return {
        "area_ha": pt(m["affected_area_ha"]),
        "migration_m": pt(m["max_migration_distance_m"]),
        "compliance_conc": pt(m["compliance_conc"]),
        "excursion_probability": float(p_ex),
        "breach_probability": float(m["breaches_at_compliance"]),
        "_field": res,   # full plume grid for the heatmap
    }


def predict(mode: str, **inputs) -> dict:
    if mode == "ml":
        return _surrogate().predict(**inputs)
    if mode == "analytical":
        return predict_analytical(**inputs)
    raise ValueError("mode must be 'analytical' or 'ml'")


if __name__ == "__main__":
    demo = dict(regime="fractured", K_m_day=1.12, gradient_i=0.006, phi_mobile=0.008,
                n_total=0.03, grain_density=2750, kd_L_kg=1.0, beta=8.0,
                Q_in_m3_day=2500, bleed_fraction=0.02, operation_years=8,
                wellfield_width_m=300, thickness_m=37.5, source_conc_C0=15000,
                background_conc_Cb=2.0, species="uranium_ppb", time_years=10)
    a = predict("analytical", **demo)
    m = predict("ml", **demo)
    print("ANALYTICAL  area=%.1f ha  migration=%.0f m  P_ex=%.2f  breach=%.0f"
          % (a["area_ha"]["p50"], a["migration_m"]["p50"], a["excursion_probability"],
             a["breach_probability"]))
    print("ML P50      area=%.1f ha  migration=%.0f m  P_ex=%.2f  breach=%.2f"
          % (m["area_ha"]["p50"], m["migration_m"]["p50"], m["excursion_probability"],
             m["breach_probability"]))
    print("ML bands    area[P10,P90]=[%.1f, %.1f]  migration[P10,P90]=[%.0f, %.0f]"
          % (m["area_ha"]["p10"], m["area_ha"]["p90"],
             m["migration_m"]["p10"], m["migration_m"]["p90"]))
