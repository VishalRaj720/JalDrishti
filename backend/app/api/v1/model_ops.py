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

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_staff
from app.exceptions import AppException
from app.models.user import User
from app.services import audit, jobs, model_ops as mo

router = APIRouter(prefix="/model-ops", tags=["Model operations"])


@router.get("/status")
async def ops_status(_: User = Depends(require_staff)) -> dict[str, Any]:
    """Is each derived artifact current with the datasets it is built from?"""
    return mo.status()


@router.get("/jobs")
async def list_jobs(_: User = Depends(require_staff)) -> dict[str, Any]:
    """Work started from this screen, running or recently finished.

    Several of these actions take real time — the flow-field rebuild reads a
    671 MB raster — and the UI previously said nothing while they ran. A button
    that stays pressed for forty seconds with no feedback is indistinguishable
    from a button that did nothing.
    """
    return jobs.listing()


@router.post("/recompute-baselines")
async def recompute_baselines(
    request: Request,
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Re-derive excursion baselines from the current chemistry file.

    Also the cheapest real check that synced rows parse: if the loader cannot
    read the file, this fails loudly rather than leaving a broken CSV in place.
    """
    job_id = jobs.start("recompute_baselines",
                        label="Recomputing excursion baselines", actor=actor.email)
    try:
        out = mo.recompute_baselines()
        jobs.finish(job_id, message=out.get("message", ""))
    except AppException as e:
        jobs.fail(job_id, e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)
    await audit.record(
        action="model_ops.recompute_baselines", entity_type="artifacts",
        entity_id="excursion_baselines", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None, detail=out)
    return out


@router.post("/rebuild-flow-field")
async def rebuild_flow_field(
    request: Request,
    background: BackgroundTasks,
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Re-bake the flow field from CGWB levels + the GLO-30 DEM.

    Runs inline and takes a while — it reads a 671 MB raster. It refuses outright
    if the DEM is missing rather than producing a station-only field.
    """
    # Fail fast on the one condition checkable synchronously — a missing DEM
    # should be a 409 the user sees now, not a job that starts and then dies.
    if not mo.DEM.exists():
        raise HTTPException(
            status_code=409,
            detail=(f"cannot rebuild the flow field: {mo.DEM.name} is not on disk. "
                    f"Rebuilding without it would silently produce a station-only "
                    f"field over most of Jharkhand."))

    task = jobs.run(
        "rebuild_flow_field", label="Rebuilding the groundwater flow field",
        actor=actor.email, fn=mo.rebuild_flow_field,
        detail={"reads": "CGWB levels + GLO-30 DEM (671 MB)"})
    background.add_task(task)

    await audit.record(
        action="model_ops.rebuild_flow_field", entity_type="artifacts",
        entity_id="flow_field", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None,
        detail={"job_id": task.job_id, "started": True})
    return {
        "started": True, "job_id": task.job_id,
        "message": ("Rebuild started. It reads a 671 MB raster, so it takes a "
                    "minute or two — watch it under Activity."),
    }


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
    # A dry run writes nothing; logging it would fill Activity with rehearsals.
    job_id = None if dry_run else jobs.start(
        "factory_reset", label="Resetting datasets to what shipped",
        actor=actor.email)
    try:
        out = await mo.factory_reset(
            db, actor=actor, dry_run=dry_run,
            ip=request.client.host if request.client else None)
        if job_id:
            jobs.finish(job_id, message=out.get("message", ""))
        return out
    except AppException as e:
        if job_id:
            jobs.fail(job_id, e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/model")
async def model_state(_: User = Depends(require_staff)) -> dict[str, Any]:
    """What model is live, and whether anything exists to fall back to."""
    return mo.model_state()


@router.post("/model-backups")
async def create_model_backup(
    request: Request,
    label: str = Query("", description="Optional short label, slugified"),
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Snapshot the trained model.

    Worth doing before anything that touches `ml/artifacts/` — including running
    `python -m ml_pipeline.ml.train` by hand, which the README documents and which
    overwrites the directory in place.
    """
    job_id = jobs.start("backup_model", label="Backing up the trained model",
                        actor=actor.email)
    try:
        out = mo.backup_model(label)
        jobs.finish(job_id, message=out.get("message", ""))
    except AppException as e:
        jobs.fail(job_id, e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)
    await audit.record(
        action="model_ops.backup_model", entity_type="artifacts",
        entity_id=out["name"], actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None, detail=out)
    return out


@router.post("/model-backups/{name}/restore")
async def restore_model_backup(
    request: Request,
    name: str,
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Roll the model back to a bundle. The live version is snapshotted first."""
    job_id = jobs.start("restore_model", label=f"Restoring the model from {name}",
                        actor=actor.email)
    try:
        out = mo.restore_model(name)
        jobs.finish(job_id, message=out.get("message", ""))
    except AppException as e:
        jobs.fail(job_id, e.message)
        raise HTTPException(status_code=e.status_code, detail=e.message)
    await audit.record(
        action="model_ops.restore_model", entity_type="artifacts",
        entity_id=name, actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None, detail=out)
    return out
