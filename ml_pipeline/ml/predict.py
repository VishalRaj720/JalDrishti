"""
ml_pipeline.ml.predict  (PHASE 3 v2 -- inference API for the dashboard)
=====================================================================
One module, two engines, identical output schema -- so the "Analytical vs ML
Surrogate" toggle is a one-line switch:

    out = predict(mode, **inputs)          # mode in {"analytical","ml"}
    out = {
       "area_ha":          {"p10","p50","p90"},
       "migration_m":      {"p10","p50","p90"},
       "compliance_conc":  {"p10","p50","p90"},
       "excursion_probability": float,
       "breach_probability":    float,   # == excursion_probability (v2: the
                                         # separate breach classifier is retired)
       "off_scale": bool, "Xc_m": float,
    }

v2 band semantics: P10/P90 are PARAMETER-UNCERTAINTY quantiles (Kd, local K
heterogeneity, beta, gradient/seasonality, dispersivity, bleed drift) learned
from MC-labelled physics, conformally widened per regime x species (Mondrian
split-CQR) to contain the true MC band at 80%.

`inputs` are the raw operating point the dashboard produces:
  regime, K_m_day, gradient_i, phi_mobile, n_total, grain_density,
  kd_L_kg, beta, Q_in_m3_day, bleed_fraction, operation_years,
  wellfield_width_m, thickness_m, source_conc_C0, background_conc_Cb,
  species, time_years, restoration_years (opt), downtime_fraction (opt),
  gradient_seasonal_amp (opt).
"""
from __future__ import annotations

import json
import functools
from pathlib import Path
import numpy as np
import pandas as pd
import joblib

from ml_pipeline.data_prep.feature_engineering import build_feature_row, FEATURE_COLUMNS
from ml_pipeline.physics.transport import simulate_plume, MAX_GRID_REACH_M
from ml_pipeline.ml.dataset import MODEL_FEATURES, ARTIFACT_DIR, BANDS, cell_key
from ml_pipeline.config import parameters as P

SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")


@functools.lru_cache(maxsize=1)
def _restoration_residual() -> dict:
    """Per-species residual source fraction (Texas post-restoration data)."""
    try:
        from ml_pipeline.data_prep.texas_loader import texas_restoration_residual
        return texas_restoration_residual()
    except Exception:
        return dict(P.RESTORATION_FALLBACK_RESIDUAL)


# --------------------------------------------------------------------------- #
# Shared: raw inputs -> the model feature row (mirrors generate.label_row)
# --------------------------------------------------------------------------- #
def features_from_inputs(*, regime, K_m_day, gradient_i, phi_mobile, n_total,
                         grain_density, kd_L_kg, beta, Q_in_m3_day, bleed_fraction,
                         operation_years, wellfield_width_m, thickness_m,
                         source_conc_C0, background_conc_Cb, species,
                         time_years, restoration_years: float = 0.0,
                         downtime_fraction: float = 0.0,
                         gradient_seasonal_amp: float = 0.0,
                         aniso_ratio: float | None = None
                         ) -> tuple[pd.DataFrame, dict, float]:
    op_days = operation_years * 365.0
    t_days = time_years * 365.0
    rest_days = max(float(restoration_years), 0.0) * 365.0
    residual = _restoration_residual().get(species, 1.0) if rest_days > 0 else 1.0
    feat = build_feature_row(
        regime=regime, domain_is_texas=False, K_m_day=K_m_day, gradient_i=gradient_i,
        phi_mobile=phi_mobile, n_total=n_total, grain_density=grain_density,
        kd_L_kg=kd_L_kg, beta=beta, Q_in_m3_day=Q_in_m3_day,
        bleed_fraction=bleed_fraction, operation_days=op_days,
        wellfield_width_m=wellfield_width_m, thickness_m=thickness_m,
        source_conc_C0=source_conc_C0, background_conc_Cb=background_conc_Cb,
        eval_time_days=t_days, restoration_days=rest_days,
        downtime_fraction=downtime_fraction,
        gradient_seasonal_amp=gradient_seasonal_amp,
        residual_fraction=residual, aniso_ratio=aniso_ratio)
    Xc = feat["_Xc_eval_m"]                     # same kinematics as the labels
    row = {k: feat[k] for k in FEATURE_COLUMNS}
    row["Xc_m"] = Xc
    row["Xc_clean_m"] = feat["_Xc_clean_m"]
    row["time_years"] = time_years
    row["is_post_closure"] = int(t_days > op_days)
    for sp in SPECIES:
        row[f"is_{sp}"] = int(species == sp)
    X = pd.DataFrame([row])[MODEL_FEATURES].astype(float)
    return X, feat, Xc


# --------------------------------------------------------------------------- #
# ML surrogate (v2: per-band models + Mondrian conformal deltas)
# --------------------------------------------------------------------------- #
class MLSurrogate:
    def __init__(self, artifact_dir: Path = ARTIFACT_DIR):
        self.dir = Path(artifact_dir)
        self.card = json.loads((self.dir / "model_card.json").read_text())
        if self.card.get("version", 1) < 2:
            raise RuntimeError("model_card.json is v1 -- retrain with "
                               "`python -m ml_pipeline.ml.train` on v2 data")
        self.models = {t: {b: joblib.load(self.dir / f"band_{t}_{b}.joblib")
                           for b in self.card["bands"]}
                       for t in self.card["band_targets"]}
        self.pex = joblib.load(self.dir / "pex_regressor.joblib")
        self.log_targets = set(self.card["log_targets"])
        self.deltas = self.card["deltas"]

    def _bands(self, target: str, X: pd.DataFrame, cell: str) -> dict:
        lo = float(self.models[target]["p10"].predict(X)[0])
        mid = float(self.models[target]["p50"].predict(X)[0])
        hi = float(self.models[target]["p90"].predict(X)[0])
        # rearrange (heads can cross), then Mondrian conformal widening
        lo, hi = min(lo, mid), max(hi, mid)
        d = self.deltas[target].get(cell, 0.0)
        lo, hi = lo - d, hi + d
        if target in self.log_targets:
            lo, mid, hi = np.expm1(lo), np.expm1(mid), np.expm1(hi)
        lo, mid, hi = (float(max(v, 0.0)) for v in (lo, mid, hi))
        lo, hi = min(lo, mid), max(hi, mid)
        return {"p10": lo, "p50": mid, "p90": hi}

    def predict(self, **inputs) -> dict:
        X, _, Xc = features_from_inputs(**inputs)
        cell = cell_key(inputs["regime"], inputs["species"])
        p_ex = float(np.clip(self.pex.predict(X)[0], 0, 1))
        return {
            "area_ha": self._bands("affected_area_ha", X, cell),
            "migration_m": self._bands("max_migration_distance_m", X, cell),
            "compliance_conc": self._bands("compliance_conc", X, cell),
            "excursion_probability": p_ex,
            # v2: single coherent risk number (breach classifier retired)
            "breach_probability": p_ex,
            # area/migration models were trained with off-scale rows censored:
            # beyond MAX_GRID_REACH the surrogate extrapolates -- flag it.
            "off_scale": bool(Xc > MAX_GRID_REACH_M),
            "Xc_m": float(Xc),
        }


@functools.lru_cache(maxsize=1)
def _surrogate() -> MLSurrogate:
    return MLSurrogate()


# --------------------------------------------------------------------------- #
# Analytical engine (same schema; deterministic central + MC bands/excursion)
# --------------------------------------------------------------------------- #
def predict_analytical(*, n_mc: int = 48, seed: int = 0, **inputs) -> dict:
    species = inputs["species"]
    threshold = P.EXCURSION_THRESHOLDS[species]
    rest_years = float(inputs.get("restoration_years", 0.0) or 0.0)
    X, feat, Xc = features_from_inputs(**inputs)
    # QA F-2: feat["residual_fraction"] is now the REALIZED fraction (the ML
    # feature); the physics needs the raw Texas endpoint ref -- passing the
    # realized value into the drawdown law would double-apply it.
    residual = feat.get("_residual_endpoint", feat["residual_fraction"])
    op_days = inputs["operation_years"] * 365.0
    t_days = inputs["time_years"] * 365.0

    res = simulate_plume(feat, species_C0=inputs["source_conc_C0"],
                         background=inputs["background_conc_Cb"], threshold=threshold,
                         t_days=t_days, operation_days=op_days,
                         restoration_days=rest_years * 365.0,
                         residual_fraction=residual, grid_n=200,
                         compliance_x=P.COMPLIANCE_BUFFER_M)
    m = res.metrics

    # excursion probability via the same parameter-uncertainty MC as Phase 2
    from ml_pipeline.synthetic.generate import excursion_probability, mc_draws
    scn = dict(width=inputs["wellfield_width_m"], regime=inputs["regime"],
               K=inputs["K_m_day"], phi_mobile=inputs["phi_mobile"],
               n_total=inputs["n_total"], grain_density=inputs["grain_density"],
               beta=inputs["beta"], gradient=inputs["gradient_i"],
               Q_in=inputs["Q_in_m3_day"],
               Q_net=inputs["Q_in_m3_day"] * inputs["bleed_fraction"],
               bleed=inputs["bleed_fraction"],
               thickness=inputs["thickness_m"],
               downtime=float(inputs.get("downtime_fraction", 0.0) or 0.0),
               seasonal_amp=float(inputs.get("gradient_seasonal_amp", 0.0) or 0.0),
               aniso_ratio=inputs.get("aniso_ratio"),   # E1: V-derived (fractured)
               C0={species: inputs["source_conc_C0"]},
               Cb={species: inputs["background_conc_Cb"]})
    draws = mc_draws(n_mc, seed)
    p_ex = excursion_probability(scn, species, t_days, op_days, draws,
                                 rest_days=rest_years * 365.0,
                                 residual_fraction=residual)

    def pt(v):  # analytical central run is a point estimate -> degenerate band
        return {"p10": float(v), "p50": float(v), "p90": float(v)}
    # restoration diagnostic (QA F-3 fix): credit the ELAPSED sweep, not the
    # planned one -- mid-sweep the old diagnostic claimed the full-sweep clean-up
    # while the served field showed none, contradicting itself.
    from ml_pipeline.physics.transport import restoration_source_fraction
    restoration = None
    if rest_years > 0.0:
        rest_days = rest_years * 365.0
        elapsed_days = min(max(t_days - op_days, 0.0), rest_days)
        f_now = restoration_source_fraction(residual, t_days, op_days, rest_days)
        restoration = {
            "restoration_years": round(rest_years, 2),
            "sweep_elapsed_years": round(elapsed_days / 365.0, 2),
            "sweep_complete": bool(t_days >= op_days + rest_days),
            "residual_endpoint_fraction": round(float(residual), 4),  # Texas @ ref yr
            "residual_realized_fraction": round(float(f_now), 4),     # after ELAPSED sweep
            "source_conc_after_restoration": round(f_now * inputs["source_conc_C0"], 1),
            "ref_years": P.RESTORATION_REF_YEARS,
        }
    return {
        "area_ha": pt(m["affected_area_ha"]),
        "migration_m": pt(m["max_migration_distance_m"]),
        "compliance_conc": pt(m["compliance_conc"]),
        "excursion_probability": float(p_ex),
        "breach_probability": float(m["breaches_at_compliance"]),
        "off_scale": bool(m["off_scale"]),
        "Xc_m": float(m["Xc_m"]),
        "restoration": restoration,
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
    print("ANALYTICAL  area=%.1f ha  migration=%.0f m  P_ex=%.2f  breach=%.0f"
          % (a["area_ha"]["p50"], a["migration_m"]["p50"], a["excursion_probability"],
             a["breach_probability"]))
    try:
        m = predict("ml", **demo)
        print("ML P50      area=%.1f ha  migration=%.0f m  P_ex=%.2f"
              % (m["area_ha"]["p50"], m["migration_m"]["p50"], m["excursion_probability"]))
        print("ML bands    area[P10,P90]=[%.1f, %.1f]  migration[P10,P90]=[%.0f, %.0f]"
              % (m["area_ha"]["p10"], m["area_ha"]["p90"],
                 m["migration_m"]["p10"], m["migration_m"]["p90"]))
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ML surrogate unavailable ({e}) -- run "
              "`python -m ml_pipeline.ml.train` after regenerating v2 data.")
