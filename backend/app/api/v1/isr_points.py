"""ISR Points router."""
import uuid
from typing import List
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.simulation import IsrPointCreate, IsrPointUpdate, IsrPointResponse, SimulationResponse
from app.services.isr_point import IsrPointService
from app.services.simulation import SimulationService
from app.dependencies import (
    require_admin, require_analyst_or_admin, require_any_role,
    require_simulation_roles,
)
from app.exceptions import AppException
from app.services import audit
from app.schemas.common import JobResponse

router = APIRouter(prefix="/isr-points", tags=["ISR Points"])


@router.get("", response_model=List[IsrPointResponse])
async def list_isr_points(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await IsrPointService(db).list(skip=skip, limit=limit)


@router.get("/{isr_id}", response_model=IsrPointResponse)
async def get_isr_point(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await IsrPointService(db).get(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=IsrPointResponse, status_code=201)
async def create_isr_point(
    payload: IsrPointCreate,
    db: AsyncSession = Depends(get_db),
    # Regulators too: placing a hypothetical site is how a reviewer tests a
    # scenario for themselves instead of accepting an analyst's chosen location.
    current_user=Depends(require_simulation_roles),
):
    try:
        return await IsrPointService(db).create(
            payload, owner_org_id=current_user.org_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{isr_id}", response_model=IsrPointResponse)
async def update_isr_point(
    isr_id: uuid.UUID,
    payload: IsrPointUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_simulation_roles),
):
    try:
        return await IsrPointService(db).update(isr_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/{isr_id}/deletion-impact")
async def deletion_impact(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """What deleting this site would destroy. Always check before deleting.

    `simulation_runs.isr_point_id` and `advisories.isr_point_id` are both
    `ON DELETE CASCADE`, so removing a site takes its entire filed history with
    it — silently, and with no 409 to warn anyone.
    """
    return await _impact(db, isr_id)


async def _impact(db: AsyncSession, isr_id: uuid.UUID) -> dict:
    row = (await db.execute(text("""
        SELECT
          (SELECT count(*) FROM simulation_runs WHERE isr_point_id = :id) AS runs,
          (SELECT count(*) FROM advisories
            WHERE isr_point_id = :id) AS advisories,
          (SELECT count(*) FROM advisories
            WHERE isr_point_id = :id AND status = 'published') AS published
    """), {"id": isr_id})).mappings().one()
    runs, advisories, published = (int(row["runs"]), int(row["advisories"]),
                                   int(row["published"]))
    return {
        "isr_point_id": str(isr_id),
        "simulation_runs": runs,
        "advisories": advisories,
        "published_advisories": published,
        "deletable": published == 0,
        "cascade_warning": (
            "Both simulation_runs and advisories cascade on delete. Removing this "
            "site would permanently destroy every stored run's provenance triple "
            "(model card, artifact bundle, git SHA) — the record that makes a "
            "filed number defensible."),
        "blocked_reason": (
            f"{published} PUBLISHED advisory(ies) reference this site. A published "
            f"advisory is a public statement residents may have acted on; deleting "
            f"the site would erase it and leave their alerts pointing at nothing. "
            f"Withdraw the advisories first, deliberately, so the withdrawal is "
            f"itself recorded."
            if published else None),
    }


@router.delete("/{isr_id}", status_code=200)
async def delete_isr_point(
    request: Request,
    isr_id: uuid.UUID,
    dry_run: bool = Query(True, description="Defaults to TRUE. Pass false to apply."),
    confirm: str = Query("", description="Must be exactly DELETE to apply"),
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_admin),
):
    """Delete a registered site — and everything that cascades from it.

    Deliberately awkward, because the cascade is invisible from the call site:
    `dry_run` defaults to true, `confirm=DELETE` is required to apply, and a site
    with **published** advisories is refused outright rather than confirmed away.
    A published advisory is a public health statement; erasing one by deleting
    its site is not a decision that should be reachable by clicking through a
    dialog.
    """
    impact = await _impact(db, isr_id)

    if dry_run:
        impact["dry_run"] = True
        impact["message"] = (
            f"Would delete this site, {impact['simulation_runs']} stored run(s) "
            f"and {impact['advisories']} advisory(ies)."
            if impact["deletable"] else impact["blocked_reason"])
        return impact

    if not impact["deletable"]:
        raise HTTPException(status_code=409, detail=impact["blocked_reason"])
    if confirm != "DELETE":
        raise HTTPException(
            status_code=400,
            detail=("Refusing to delete without confirmation. Re-send with "
                    "confirm=DELETE. Run with dry_run=true first to see what "
                    "would be destroyed."))

    try:
        await IsrPointService(db).delete(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    await audit.record(
        action="isr_point.delete", entity_type="isr_points",
        entity_id=str(isr_id), actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None,
        detail={k: impact[k] for k in
                ("simulation_runs", "advisories", "published_advisories")},
    )
    return {**impact, "deleted": True,
            "message": (f"Deleted the site, {impact['simulation_runs']} run(s) "
                        f"and {impact['advisories']} advisory(ies).")}


@router.get("/{isr_id}/simulations", response_model=List[SimulationResponse])
async def list_simulations_for_isr(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await SimulationService(db).list_by_isr(isr_id)
