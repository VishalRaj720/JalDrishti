"""Simulations router — read simulation runs; triggering is disabled until P3.

P0 (2026-08-11): the stub engine behind `POST /simulations/{isr_id}` was
deleted (see `app/services/simulation.py` for what it fabricated). Rather than
keep serving invented numbers, the trigger reports **501 Not Implemented** and
names the engine that does work. P3 rewires it to `ml_pipeline`.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.simulation import SimulationResponse
from app.services.simulation import SimulationService
from app.dependencies import require_analyst_or_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/simulations", tags=["Simulations"])

_NOT_WIRED = (
    "Simulation execution is not available. The previous in-backend engine "
    "produced fabricated results (a random flow direction and a constant "
    "0.5733 km2 affected area) and was removed in P0. The validated engine is "
    "ml_pipeline; until it is wired in (P3), run scenarios against the "
    "ml_pipeline dashboard at POST /api/predict. See PRODUCT_DESIGN.md 1.3."
)


@router.post("/{isr_id}", status_code=501)
async def trigger_simulation(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Trigger a simulation for an ISR point. Disabled — see module docstring.

    The ISR point is still validated first, so an unknown site reports 404
    rather than a misleading 501.
    """
    try:
        await SimulationService(db).assert_isr_exists(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    raise HTTPException(status_code=501, detail=_NOT_WIRED)


@router.get("/{sim_id}", response_model=SimulationResponse)
async def get_simulation(
    sim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await SimulationService(db).get(sim_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
