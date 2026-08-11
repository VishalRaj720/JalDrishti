"""Simulations, backed by the real ml_pipeline engine.

P0 deleted the stub that fabricated results (a `random.uniform(30, 90)` flow
direction and a constant 0.5733 km² affected area) and left this endpoint
returning 501. P3 wires it to `ml_pipeline` — the engine with 307 tests, an
exact-solution-benchmarked transport kernel and conformally calibrated bands.

A run is queued, executed in the background (~6 s), and polled. Every completed
run records the model card, artifact bundle and git SHA that produced it, so the
number can be re-derived later; `ck_sim_runs_completed_is_pinned` refuses a
completed run that cannot name them.

**What does NOT cross into the engine:** anything from the database. Only the
pin coordinates and the operational sliders. See
`app/services/ml_pipeline_adapter.py` — approved field observations must never
move a contamination model without a deliberate retrain.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request, status)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_analyst_or_admin, require_staff
from app.exceptions import AppException
from app.models.user import User
from app.schemas.simulation import SimulationResponse
from app.services.simulation import SimulationService
from app.services.simulation_run import SimulationRunService

router = APIRouter(prefix="/simulations", tags=["Simulations"])


class RunRequest(BaseModel):
    """Operational sliders. The site location comes from the ISR point, never
    from the body — a caller must not be able to run a scenario at a pin the
    registry does not hold."""
    species: str = Field("uranium_ppb")
    operation_years: Optional[float] = Field(None, ge=0, le=20)
    time_years: Optional[float] = Field(None, ge=0, le=50)
    injection_rate_m3_day: Optional[float] = Field(None, gt=0)
    wellfield_width_m: Optional[float] = Field(None, ge=100, le=800)
    bleed_percent: Optional[float] = Field(None, ge=0, le=10)
    restoration_years: Optional[float] = Field(None, ge=0, le=30)
    gradient: Optional[float] = Field(None, gt=0)
    azimuth_deg: Optional[float] = Field(None, ge=0, le=360)
    monitor_ring_m: Optional[float] = Field(None, ge=75, le=180)


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    isr_point_id: uuid.UUID
    status: str
    engine: str
    species: str
    model_card_sha: Optional[str]
    artifacts_sha: Optional[str]
    code_version: Optional[str]
    request: dict[str, Any]
    metrics: Optional[dict[str, Any]]
    excursion: Optional[dict[str, Any]]
    extrapolation: Optional[list[str]]
    hydro: Optional[dict[str, Any]]
    error_message: Optional[str]
    runtime_ms: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]


async def _run_in_background(run_id: uuid.UUID) -> None:
    from app.database import AsyncSessionLocal, set_rls_context
    async with AsyncSessionLocal() as db:
        # The background task has no request identity, so it runs as the system.
        # It is executing work a permitted caller already authorised at queue
        # time; the audit row records that caller as the actor.
        await set_rls_context(db, bypass=True)
        await SimulationRunService(db, system=True).execute(run_id)


@router.post("/{isr_id}", response_model=RunResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def trigger_simulation(
    isr_id: uuid.UUID,
    payload: RunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_analyst_or_admin),
):
    """Queue a run against a registered ISR point. Poll `GET /simulations/runs/{id}`."""
    try:
        run = await SimulationRunService(db).create(
            actor=actor, isr_id=isr_id,
            params=payload.model_dump(exclude_none=True),
            ip=(request.client.host if request.client else None))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    background_tasks.add_task(_run_in_background, run.id)
    return run


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    try:
        return await SimulationRunService(db).get(run_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(
    isr_id: uuid.UUID = Query(...),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    return await SimulationRunService(db).list_for_isr(isr_id, limit=limit)


@router.get("/{sim_id}", response_model=SimulationResponse)
async def get_legacy_simulation(
    sim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Rows written by the pre-P0 engine. Retained so historical ids still
    resolve; nothing writes here any more."""
    try:
        return await SimulationService(db).get(sim_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
