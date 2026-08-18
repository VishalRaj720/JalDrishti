"""Model operations: what is stale, rebuild it, or put everything back.

Status is staff-readable — an analyst reading a number should be able to see
whether the engine is current with its inputs. Everything that writes is
`require_admin`.

`POST /factory-reset` is the destructive one, and it is deliberately awkward:
it requires `confirm=RESET` in the query string, defaults `dry_run` to true, and
audits into a log that has no UPDATE or DELETE path. An admin cannot reach it by
mis-clicking, and cannot quietly un-record having reached it.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_staff
from app.exceptions import AppException
from app.models.user import User
from app.services import audit, model_ops as mo

router = APIRouter(prefix="/model-ops", tags=["Model operations"])


@router.get("/status")
async def ops_status(_: User = Depends(require_staff)) -> dict[str, Any]:
    """Is each derived artifact current with the datasets it is built from?"""
    return mo.status()


@router.post("/recompute-baselines")
async def recompute_baselines(
    request: Request,
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Re-derive excursion baselines from the current chemistry file.

    Also the cheapest real check that synced rows parse: if the loader cannot
    read the file, this fails loudly rather than leaving a broken CSV in place.
    """
    try:
        out = mo.recompute_baselines()
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    await audit.record(
        action="model_ops.recompute_baselines", entity_type="artifacts",
        entity_id="excursion_baselines", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None, detail=out)
    return out


@router.post("/rebuild-flow-field")
async def rebuild_flow_field(
    request: Request,
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Re-bake the flow field from CGWB levels + the GLO-30 DEM.

    Runs inline and takes a while — it reads a 671 MB raster. It refuses outright
    if the DEM is missing rather than producing a station-only field.
    """
    try:
        out = mo.rebuild_flow_field()
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    await audit.record(
        action="model_ops.rebuild_flow_field", entity_type="artifacts",
        entity_id="flow_field", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None, detail=out)
    return out


@router.post("/factory-reset")
async def factory_reset(
    request: Request,
    dry_run: bool = Query(True, description="Defaults to TRUE. Pass false to apply."),
    confirm: str = Query("", description="Must be exactly RESET to apply"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Remove every `added` row from every dataset, restoring what shipped.

    Field observations are **kept** — they return to "approved, not yet in the
    model" and can be re-synced. Each file is backed up first, so the reset is
    itself reversible from `GET /datasets/{key}/backups`.
    """
    if not dry_run and confirm != "RESET":
        raise HTTPException(
            status_code=400,
            detail=("Refusing to reset without confirmation. Re-send with "
                    "confirm=RESET. Run with dry_run=true first to see exactly "
                    "which rows would be removed."))
    try:
        return await mo.factory_reset(
            db, actor=actor, dry_run=dry_run,
            ip=request.client.host if request.client else None)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
