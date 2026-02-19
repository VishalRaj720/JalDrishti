"""Simulations router – trigger async simulation, poll status."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.simulation import SimulationResponse
from app.schemas.common import JobResponse
from app.services.simulation import SimulationService
from app.dependencies import require_analyst_or_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/simulations", tags=["Simulations"])


@router.post("/{isr_id}", response_model=JobResponse, status_code=202)
async def trigger_simulation(
    isr_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """
    Trigger a new simulation for an ISR point.
    Runs asynchronously via Celery (falls back to BackgroundTasks).
    Returns a job_id to poll.
    """
    try:
        svc = SimulationService(db)
        sim = await svc.create_pending(isr_id)

        # Try Celery first; fall back to FastAPI BackgroundTasks
        try:
            from app.tasks.simulation import run_simulation_task
            task = run_simulation_task.delay(str(sim.id))
            await svc.sim_repo.update(sim, {"task_id": task.id})
            return JobResponse(
                job_id=str(sim.id),
                status="queued",
                message=f"Simulation queued. Poll GET /api/v1/simulations/{sim.id}",
            )
        except Exception:
            # Celery unavailable: run in BackgroundTask
            background_tasks.add_task(_run_simulation_bg, sim.id)
            return JobResponse(
                job_id=str(sim.id),
                status="queued",
                message=f"Simulation started in background. Poll GET /api/v1/simulations/{sim.id}",
            )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


async def _run_simulation_bg(sim_id: uuid.UUID):
    """Background task wrapper for when Celery is unavailable."""
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        svc = SimulationService(db)
        await svc.run(sim_id)


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
