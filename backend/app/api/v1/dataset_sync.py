"""Dataset sync: see the gap, and close it deliberately.

`GET /dataset-sync/status` is readable by all staff — it is what the UI polls to
render the amber badge and the "N approved observations are not yet in the
model" line. `POST /dataset-sync/ore` is admin-only, because it writes tracked
data files that the physics engine reads.

There is no scheduler. A weekly rebake on a frozen, gate-validated model buys
nothing and risks silently replacing artifacts whose coverage was hand-verified,
so syncing is something a person decides to do.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_staff
from app.exceptions import AppException
from app.models.user import User
from app.services import dataset_sync as ds

router = APIRouter(prefix="/dataset-sync", tags=["Dataset sync"])


@router.get("/status")
async def sync_status(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Counts behind the three UI states."""
    return await ds.pending_summary(db)


@router.get("/pending")
async def pending_items(
    observation_type: Optional[str] = Query(None),
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """The amber list: approved, not yet in `Datasets/`.

    This is the working list an admin takes to the audit log for the types that
    have no automated sync (chemistry, groundwater levels).
    """
    sql = """
        SELECT f.id::text, f.observation_type, f.operation, f.target_table,
               f.target_id::text, f.previous, f.proposed, f.reviewed_at,
               u.email AS reviewed_by_email,
               s.email AS submitted_by_email
        FROM field_observations f
        LEFT JOIN users u ON u.id = f.reviewed_by
        LEFT JOIN users s ON s.id = f.submitted_by
        WHERE f.status = 'approved' AND f.synced_to_dataset_at IS NULL
    """
    params: dict[str, Any] = {"lim": limit}
    if observation_type:
        sql += " AND f.observation_type = :t"
        params["t"] = observation_type
    sql += " ORDER BY f.reviewed_at LIMIT :lim"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return {"count": len(rows), "items": [dict(r) for r in rows],
            "syncable_types": list(ds.SYNCABLE_TYPES)}


@router.post("/ore")
async def sync_ore(
    request: Request,
    dry_run: bool = Query(False, description="Report what would change, write nothing"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Append approved ore observations to the two ore dataset files.

    Backs both files up first, tags new rows `origin=added`, marks the
    observations synced, clears the pipeline's dataset caches, and audits the
    batch. Does **not** retrain — the response says so explicitly.
    """
    try:
        return await ds.sync_ore(
            db, actor=actor, dry_run=dry_run,
            ip=(request.client.host if request.client else None))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


def _ip(request: Request):
    return request.client.host if request.client else None


@router.post("/water-quality")
async def sync_water_quality(
    request: Request,
    dry_run: bool = Query(False, description="Report what would change, write nothing"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Append approved chemistry to `waterQuality_jharkhand.csv`.

    Returns `stale_marks: ["excursion_baselines"]` — the rows are in the file but
    the baselines derived from them are not recomputed until
    `POST /model-ops/recompute-baselines` runs. Reporting that is the difference
    between a sync that took effect and one that only looks like it did.
    """
    try:
        return await ds.sync_water_quality(
            db, actor=actor, dry_run=dry_run, ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/groundwater-levels")
async def sync_groundwater_levels(
    request: Request,
    dry_run: bool = Query(False, description="Report what would change, write nothing"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Append approved level readings to `cgwb_waterlevel_jharkhand.csv`.

    Returns `stale_marks: ["flow_field"]`. The flow field is baked from these
    readings plus the GLO-30 DEM, so a rebuild is required before any pin sees a
    different gradient or azimuth.
    """
    try:
        return await ds.sync_groundwater_levels(
            db, actor=actor, dry_run=dry_run, ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/all")
async def sync_all(
    request: Request,
    dry_run: bool = Query(False, description="Report what would change, write nothing"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Run every syncable type in one action, and report the union of stale marks."""
    try:
        return await ds.sync_all(db, actor=actor, dry_run=dry_run, ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
