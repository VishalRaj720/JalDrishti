"""MLPredictionService — Month 4 in-process predictor.

Replaces the random-stub `_call_ml_service` in `services.simulation`. Loads the
trained baseline models from `backend/ml/artifacts/` once at import time and
exposes an async `predict()` that:

  1. Builds a single-row feature dataframe using the same FeatureBuilder used
     during training (guarantees column parity).
  2. Runs the TDS regressor and contamination classifier.
  3. Returns a dict shaped to match the existing `_call_ml_service` contract,
     so `SimulationService.run()` does not need to know which backend is alive.

If artifacts are missing (fresh checkout, models not trained yet) the service
exposes `models_loaded == False` and the caller falls back to the legacy stub
or the HTTP microservice (`ML_SERVICE_URL`).
"""
from __future__ import annotations

import asyncio
import json
import math
import random
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import pandas as pd
from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.aquifer import Aquifer
from app.models.isr_point import IsrPoint


# Path to artifacts produced by `python -m ml.train_baselines`
_ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "ml" / "artifacts"


_MODEL_LOCK = threading.Lock()
_LOADED: Dict[str, Any] = {
    "regressor": None,
    "classifier": None,
    "metadata": None,
    "version": None,
    "loaded_at": None,
    "error": None,
}


def _load_artifacts() -> Dict[str, Any]:
    """Lazy-load joblib artifacts. Idempotent; safe to call from any task."""
    with _MODEL_LOCK:
        if _LOADED["regressor"] is not None and _LOADED["classifier"] is not None:
            return _LOADED
        try:
            import joblib
        except ImportError as exc:
            _LOADED["error"] = f"joblib not installed: {exc}"
            return _LOADED

        reg_path = _ARTIFACTS_DIR / "tds_regressor.joblib"
        clf_path = _ARTIFACTS_DIR / "contamination_classifier.joblib"
        meta_path = _ARTIFACTS_DIR / "feature_metadata.json"

        if not reg_path.exists() or not clf_path.exists():
            _LOADED["error"] = (
                f"Artifacts missing in {_ARTIFACTS_DIR}. "
                f"Run `python -m ml.train_baselines` from backend/."
            )
            return _LOADED

        try:
            _LOADED["regressor"] = joblib.load(reg_path)
            _LOADED["classifier"] = joblib.load(clf_path)
            _LOADED["metadata"] = (
                json.loads(meta_path.read_text()) if meta_path.exists() else {}
            )
            _LOADED["version"] = "baseline_v1"
            _LOADED["loaded_at"] = datetime.now(timezone.utc).isoformat()
            _LOADED["error"] = None
            logger.info(f"MLPredictionService loaded artifacts from {_ARTIFACTS_DIR}")
        except Exception as exc:
            _LOADED["error"] = f"Failed to load artifacts: {exc}"
            logger.warning(_LOADED["error"])
        return _LOADED


# SQL pulls everything needed to build one feature row at predict time.
_FEATURE_SQL = """
SELECT
    :sample_date::timestamp                                              AS sampled_at,
    a.type::text                                                          AS aquifer_type,
    a.porosity                                                            AS porosity,
    a.hydraulic_conductivity                                              AS hydraulic_conductivity,
    a.transmissivity                                                      AS transmissivity,
    a.specific_yield                                                      AS specific_yield,
    a.storage_coefficient                                                 AS storage_coefficient,
    a.dtw_decadal_avg                                                     AS dtw_decadal_avg,
    a.min_depth                                                           AS aquifer_min_depth,
    a.max_depth                                                           AS aquifer_max_depth,
    ip.injection_rate                                                     AS nearest_isr_injection_rate,
    ST_Distance(a.geometry::geography, ip.location::geography) / 1000.0   AS distance_to_nearest_isr_km,
    NULL::float                                                           AS well_depth,
    NULL::float                                                           AS tds_mg_l,
    NULL::float                                                           AS ec_us_cm,
    NULL::float                                                           AS uranium_ppb
FROM aquifers a
JOIN isr_points ip ON ip.id = :isr_id
WHERE a.id = :aquifer_id;
"""


class MLPredictionService:
    """Stateless wrapper around the loaded sklearn pipelines."""

    def __init__(self, db: AsyncSession):
        self.db = db
        artifacts = _load_artifacts()
        self.regressor = artifacts["regressor"]
        self.classifier = artifacts["classifier"]
        self.metadata = artifacts.get("metadata") or {}
        self.version = artifacts.get("version")
        self.error = artifacts.get("error")

    @property
    def models_loaded(self) -> bool:
        return self.regressor is not None and self.classifier is not None

    async def _build_feature_row(
        self,
        isr: IsrPoint,
        aquifer: Aquifer,
        sample_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Pull the single-row feature frame from PostGIS."""
        from ml.features import FeatureBuilder, ALL_FEATURES  # local import: ml is sibling to app

        sample_date = sample_date or datetime.now(timezone.utc)
        result = await self.db.execute(
            text(_FEATURE_SQL),
            {
                "isr_id": isr.id,
                "aquifer_id": aquifer.id,
                "sample_date": sample_date,
            },
        )
        row = result.mappings().first()
        if row is None:
            # build a degraded row from in-memory ORM objects
            row = {
                "sampled_at": sample_date,
                "aquifer_type": getattr(aquifer.type, "value", str(aquifer.type)) if aquifer.type else None,
                "porosity": aquifer.porosity,
                "hydraulic_conductivity": aquifer.hydraulic_conductivity,
                "transmissivity": aquifer.transmissivity,
                "specific_yield": aquifer.specific_yield,
                "storage_coefficient": aquifer.storage_coefficient,
                "dtw_decadal_avg": aquifer.dtw_decadal_avg,
                "aquifer_min_depth": aquifer.min_depth,
                "aquifer_max_depth": aquifer.max_depth,
                "nearest_isr_injection_rate": isr.injection_rate,
                "distance_to_nearest_isr_km": None,
                "well_depth": None,
                "tds_mg_l": None,
                "ec_us_cm": None,
                "uranium_ppb": None,
            }

        df = pd.DataFrame([dict(row)])
        # FeatureBuilder.split_xy drops rows lacking targets, so call
        # derive_features directly to preserve the inference row.
        derived = FeatureBuilder.derive_features(df)
        for col in ALL_FEATURES:
            if col not in derived.columns:
                derived[col] = None
        return derived[ALL_FEATURES]

    def _classifier_proba(self, X: pd.DataFrame) -> Dict[str, float]:
        proba = self.classifier.predict_proba(X)[0]
        classes = list(self.classifier.named_steps["model"].classes_)
        return {cls: float(p) for cls, p in zip(classes, proba)}

    async def predict(
        self,
        isr: IsrPoint,
        aquifer: Aquifer,
        sample_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Return a dict matching the legacy `_call_ml_service` shape."""
        if not self.models_loaded:
            return self._stub_payload(reason=self.error or "models_not_loaded")

        try:
            X = await self._build_feature_row(isr, aquifer, sample_date)
            tds_pred = float(self.regressor.predict(X)[0])
            class_proba = self._classifier_proba(X)
            top_class = max(class_proba, key=class_proba.get)
            risk_level = {"safe": "low", "marginal": "medium", "unsafe": "high"}.get(top_class, "medium")

            # Map TDS prediction onto a uranium proxy (no direct uranium model in baseline):
            # use the WHO-classifier probability of "unsafe" as a soft contamination indicator.
            unsafe_prob = class_proba.get("unsafe", 0.0)
            uranium_proxy = 0.005 + unsafe_prob * 0.10  # 0.005–0.105 mg/L band

            return {
                "concentration": {
                    "uranium": {
                        "max": round(uranium_proxy, 4),
                        "unit": "mg/L",
                        "who_limit": 0.03,
                        "exceeds_limit": uranium_proxy > 0.03,
                        "estimated_from": "classifier_proba",
                    },
                    "tds": {
                        "predicted": round(tds_pred, 2),
                        "unit": "mg/L",
                        "who_limit": 1000.0,
                        "exceeds_limit": tds_pred > 1000.0,
                    },
                },
                "vulnerability": {
                    "risk_level": risk_level,
                    "predicted_class": top_class,
                    "class_probabilities": {k: round(v, 4) for k, v in class_proba.items()},
                    "probability": round(float(class_proba.get("unsafe", 0.0) +
                                                0.5 * class_proba.get("marginal", 0.0)), 4),
                    "model": f"baseline_{self.version}",
                },
                "model_loaded": True,
            }
        except Exception as exc:
            logger.warning(f"MLPredictionService.predict failed: {exc}; falling back to stub")
            return self._stub_payload(reason=str(exc))

    @staticmethod
    def _stub_payload(reason: str = "stub") -> Dict[str, Any]:
        uranium = round(random.uniform(0.01, 0.12), 4)
        return {
            "concentration": {
                "uranium": {
                    "max": uranium,
                    "unit": "mg/L",
                    "who_limit": 0.03,
                    "exceeds_limit": uranium > 0.03,
                    "estimated_from": "stub",
                },
                "tds": {
                    "predicted": round(random.uniform(200, 1500), 2),
                    "unit": "mg/L",
                    "who_limit": 1000.0,
                    "exceeds_limit": False,
                },
            },
            "vulnerability": {
                "risk_level": random.choice(["low", "medium", "high"]),
                "probability": round(random.uniform(0.4, 0.95), 2),
                "model": f"stub_v0 ({reason})",
            },
            "model_loaded": False,
        }


# ---------------------------------------------------------------------------
# Aggregator that simulation.py calls in place of the old _call_ml_service.
# Keeps the HTTP microservice fallback for Month 9 deployments.
# ---------------------------------------------------------------------------

async def predict_for_simulation(
    db: AsyncSession,
    isr: IsrPoint,
    impacted_aquifers: list,
    sample_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Aggregate predictions across all impacted aquifers and return a
    single payload compatible with the legacy stub contract.

    Tries (in order): in-process `MLPredictionService`, HTTP microservice,
    legacy stub.
    """
    svc = MLPredictionService(db)

    if svc.models_loaded and impacted_aquifers:
        per_aquifer = []
        for aquifer in impacted_aquifers:
            per_aquifer.append(await svc.predict(isr, aquifer, sample_date))
        # collapse: take worst-case per metric
        worst_uranium = max(p["concentration"]["uranium"]["max"] for p in per_aquifer)
        max_tds = max(p["concentration"]["tds"]["predicted"] for p in per_aquifer)
        unsafe_prob = max(p["vulnerability"]["probability"] for p in per_aquifer)
        risk_levels = [p["vulnerability"]["risk_level"] for p in per_aquifer]
        worst_level = "high" if "high" in risk_levels else "medium" if "medium" in risk_levels else "low"

        return {
            "concentration": {
                "uranium": {
                    "max": round(worst_uranium, 4),
                    "unit": "mg/L",
                    "who_limit": 0.03,
                    "exceeds_limit": worst_uranium > 0.03,
                },
                "tds": {
                    "predicted": round(max_tds, 2),
                    "unit": "mg/L",
                    "who_limit": 1000.0,
                    "exceeds_limit": max_tds > 1000.0,
                },
            },
            "vulnerability": {
                "risk_level": worst_level,
                "probability": round(unsafe_prob, 4),
                "model": f"baseline_{svc.version}",
                "per_aquifer_count": len(per_aquifer),
            },
            "model_loaded": True,
            "per_aquifer": per_aquifer,
        }

    # No impacted aquifers OR models not loaded: try HTTP microservice fallback
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ML_SERVICE_URL}/predict",
                json={
                    "isr_id": str(isr.id),
                    "injection_rate": isr.injection_rate or 100.0,
                    "aquifer_count": len(impacted_aquifers),
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning(f"ML HTTP fallback unreachable: {exc}; using stub")
        return MLPredictionService._stub_payload(reason="all_fallbacks_failed")
