"""Named scenarios, and comparing their runs.

PRODUCT_DESIGN.md §3.3, the last outstanding slice of P3. A scenario names a set
of inputs; running it queues a normal `simulation_run` tagged with the scenario,
so every result stays immutable and pinned to the artifacts that produced it.

`POST /scenarios/{id}/compare` diffs two runs rather than re-deriving anything.
It reports **why** they differ — different inputs, or the same inputs against a
different model — because "the number changed" is only actionable once you know
which of those happened.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request, status)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_simulation_roles, require_staff
from app.exceptions import AppException, ResourceNotFoundError
from app.models.scenario import Scenario
from app.models.simulation_run import SimulationRun
from app.models.user import User
from app.services import audit
from app.services import run_compare as rc
from app.services.simulation_run import SimulationRunService

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


class ScenarioCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    isr_point_id: uuid.UUID
    description: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    isr_point_id: uuid.UUID
    params: dict[str, Any]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    archived_at: Optional[datetime]


class CompareRequest(BaseModel):
    run_a: uuid.UUID
    run_b: uuid.UUID


def _ip(r: Request) -> Optional[str]:
    return r.client.host if r.client else None


@router.post("", response_model=ScenarioResponse,
             status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_simulation_roles),
):
    # P2: narrowed from CLIENT_TUNABLE to RUN_VARIABLE. A scenario is a named
    # set of RUN inputs against a fixed site, and a run may vary exactly three
    # things. Validating against the wider interactive-map allowlist let a
    # scenario carry `operation_years` or `injection_rate_m3_day` and override
    # the registered site's own operation at run time — the same defeat of
    # migration 0015 that cutting `RunRequest` was meant to end, reached through
    # a different door.
    from app.services.ml_pipeline_adapter import RUN_VARIABLE
    unknown = set(payload.params) - RUN_VARIABLE
    if unknown:
        # Validated at save time, not at run time: a scenario that cannot run is
        # worse than one that is refused, because it looks saved.
        raise HTTPException(
            status_code=422,
            detail=f"A scenario may vary only {sorted(RUN_VARIABLE)}. "
                   f"Rejected: {sorted(unknown)}. Everything else is a property "
                   f"of the ISR site — edit the site to change it, so that two "
                   f"people running the same site run the same operation.")

    sc = Scenario(name=payload.name, description=payload.description,
                  isr_point_id=payload.isr_point_id, params=payload.params,
                  created_by=actor.id, org_id=actor.org_id)
    db.add(sc)
    try:
        await db.flush()
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        if "uq_scenario_site_name" in str(exc):
            raise HTTPException(
                status_code=409,
                detail=f"A scenario named '{payload.name}' already exists for "
                       f"this site.")
        raise
    await audit.record(action="scenario.create", entity_type="scenarios",
                       entity_id=str(sc.id), actor_id=actor.id,
                       actor_label=actor.email, ip_address=_ip(request),
                       detail={"name": sc.name, "params": sc.params})
    return sc


@router.get("", response_model=list[ScenarioResponse])
async def list_scenarios(
    isr_point_id: Optional[uuid.UUID] = Query(None),
    include_archived: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    stmt = select(Scenario).order_by(Scenario.created_at.desc())
    if isr_point_id:
        stmt = stmt.where(Scenario.isr_point_id == isr_point_id)
    if not include_archived:
        stmt = stmt.where(Scenario.archived_at.is_(None))
    return list((await db.execute(stmt)).scalars().all())


async def _get(db: AsyncSession, sid: uuid.UUID) -> Scenario:
    sc = (await db.execute(
        select(Scenario).where(Scenario.id == sid))).scalar_one_or_none()
    if sc is None:
        raise ResourceNotFoundError("Scenario", str(sid))
    return sc


@router.get("/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(
    scenario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    try:
        return await _get(db, scenario_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{scenario_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_scenario(
    scenario_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_simulation_roles),
):
    """Queue a run of this scenario's saved inputs."""
    from app.api.v1.simulations import _run_in_background
    try:
        sc = await _get(db, scenario_id)
        run = await SimulationRunService(db).create(
            actor=actor, isr_id=sc.isr_point_id, params=dict(sc.params),
            ip=_ip(request), scenario_id=sc.id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # No second write here. Assigning `run.scenario_id` after `create()` and
    # committing again raised StaleDataError every time -- the RLS context is
    # discarded at COMMIT, so the follow-up UPDATE matched no rows. The link is
    # now written by the INSERT itself; see SimulationRunService.create.
    background_tasks.add_task(_run_in_background, run.id)
    return {"run_id": str(run.id), "scenario_id": str(sc.id), "status": run.status}


@router.post("/{scenario_id}/compare")
async def compare_runs(
    scenario_id: uuid.UUID,
    payload: CompareRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Diff two runs and say **why** they differ.

    Two runs can disagree for two very different reasons: the inputs changed, or
    the model did. Reporting the delta without saying which would leave a
    reviewer unable to act on it.
    """
    svc = SimulationRunService(db)
    try:
        a = await svc.get(payload.run_a)
        b = await svc.get(payload.run_b)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    for r in (a, b):
        if r.status != "completed":
            raise HTTPException(
                status_code=409,
                detail=f"Run {r.id} is '{r.status}'; only completed runs can be "
                       f"compared.")

    out = rc.diff(a, b)
    out["scenario_id"] = str(scenario_id)
    return out


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_scenario(
    scenario_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_simulation_roles),
):
    """Archive, never delete: runs reference the scenario that produced them."""
    try:
        sc = await _get(db, scenario_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    sc.archived_at = datetime.now(tz=sc.created_at.tzinfo)
    await db.commit()
    await audit.record(action="scenario.archive", entity_type="scenarios",
                       entity_id=str(sc.id), actor_id=actor.id,
                       actor_label=actor.email, ip_address=_ip(request),
                       detail={"name": sc.name})
