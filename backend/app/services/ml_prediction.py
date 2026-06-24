"""ml_prediction — backend predictor used by the simulation service.

Month 1 status
--------------
The canonical, trained ML lives in `DataGen_ModelMVP/pipeline/` (uranium
regressor + risk classifier, grounded in real Texas ISR + Jharkhand data).
Wiring those trained artifacts into this backend endpoint — and folding the
spread projection into the ML layer — is the Month-2 task.

Until then this module returns a **transparent, deterministic** estimate (NOT
random): uranium scales with injection rate and decays with aquifer count /
porosity. It keeps the simulation API functional and reproducible, and is
clearly tagged `model: "month1_placeholder"` so nothing is mistaken for a real
prediction.

The previous version depended on `backend/ml/` (the Gaussian-copula pipeline,
now deleted) and an external `ML_SERVICE_URL` microservice (never built). Both
dependencies are gone.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aquifer import Aquifer
from app.models.isr_point import IsrPoint

WHO_URANIUM_MGL = 0.03   # 30 ppb
WHO_TDS_MGL = 1000.0


def _deterministic_estimate(
    injection_rate: float, aquifer_count: int, avg_porosity: float
) -> Dict[str, Any]:
    """A monotone, reproducible placeholder — not a trained model."""
    rate = max(injection_rate or 100.0, 1.0)
    poro = avg_porosity if avg_porosity and avg_porosity > 0 else 0.1
    # higher injection -> more uranium; higher porosity dilutes the peak
    uranium = round(min(0.005 + (rate / 1000.0) * 0.04 / poro, 0.40), 4)
    tds = round(400.0 + rate * 0.6, 2)
    if uranium > WHO_URANIUM_MGL or tds > WHO_TDS_MGL:
        risk = "high"
    elif uranium > WHO_URANIUM_MGL * 0.5:
        risk = "medium"
    else:
        risk = "low"
    return {
        "concentration": {
            "uranium": {
                "max": uranium,
                "unit": "mg/L",
                "who_limit": WHO_URANIUM_MGL,
                "exceeds_limit": uranium > WHO_URANIUM_MGL,
                "estimated_from": "month1_placeholder",
            },
            "tds": {
                "predicted": tds,
                "unit": "mg/L",
                "who_limit": WHO_TDS_MGL,
                "exceeds_limit": tds > WHO_TDS_MGL,
            },
        },
        "vulnerability": {
            "risk_level": risk,
            "probability": round(min(uranium / WHO_URANIUM_MGL, 1.0), 3),
            "model": "month1_placeholder",
        },
        "model_loaded": False,
        "impacted_aquifer_count": aquifer_count,
    }


async def predict_for_simulation(
    db: AsyncSession,
    isr: IsrPoint,
    impacted_aquifers: List[Aquifer],
    sample_date: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return a contamination/vulnerability estimate for the simulation service.

    Wire-compatible with `SimulationService.run()` (expects
    `result["concentration"]["uranium"]["max"]` and `result["vulnerability"]`).
    """
    porosities = [a.porosity for a in impacted_aquifers if a.porosity]
    avg_porosity = sum(porosities) / len(porosities) if porosities else 0.1
    return _deterministic_estimate(
        injection_rate=isr.injection_rate or 100.0,
        aquifer_count=len(impacted_aquifers),
        avg_porosity=avg_porosity,
    )
