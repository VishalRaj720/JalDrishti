"""Row-level control over the files the engine reads. Admin only.

Reading the registry is staff-readable — an analyst should be able to see what
the engine is standing on, and which rows were added rather than shipped.
Writing is `require_admin`, because these files *are* the model's inputs: an edit
here changes what every subsequent run computes, for everyone.

The one rule worth restating at the route layer, because it is the reason this
router can exist safely at all: **`record_source=original` rows cannot be edited
or deleted.** That is enforced in `services/datasets.py`, not here, so the CLI,
the factory reset and any future caller hit it too. A 409 with the reason is what
comes back.
"""
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_staff
from app.models.user import User
from app.services import audit, datasets as ds

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("")
async def list_datasets(_: User = Depends(require_staff)) -> dict[str, Any]:
    """Every writable dataset: row counts, original/added split, what it governs."""
    return {
        "source_column": ds.SOURCE_COL,
        "values": {"original": ds.SOURCE_ORIGINAL, "added": ds.SOURCE_ADDED},
        "note": (
            f"'{ds.SOURCE_ORIGINAL}' marks rows that shipped with the project "
            f"(CGWB, UDEPO, GSI, NAQUIM) — immutable. '{ds.SOURCE_ADDED}' marks "
            f"rows this system wrote from approved field observations — editable "
            f"and removable by an admin."),
        "datasets": ds.summary(),
    }


@router.get("/{key}/rows")
async def dataset_rows(
    key: str,
    source: Optional[str] = Query(None, description="original | added"),
    q: Optional[str] = Query(None, description="free-text row filter"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Paged rows. `added` rows sort first — they are what an admin came for."""
    return ds.rows(key, source=source, q=q, offset=offset, limit=limit)


@router.get("/{key}/backups")
async def dataset_backups(key: str, _: User = Depends(require_admin)):
    """Every restore point for this file, newest first."""
    return {"key": key, "backups": ds.list_backups(key)}


@router.patch("/{key}/rows/{row_id}")
async def patch_row(
    request: Request,
    key: str,
    row_id: str,
    patch: dict[str, Any] = Body(..., description="column -> new value"),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Edit one `added` row. 409 if it is `original`."""
    out = ds.update_row(key, row_id, patch)
    await audit.record(
        action="dataset.row_update", entity_type="datasets",
        entity_id=f"{key}:{row_id}", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None,
        detail={"dataset": key, "row_id": row_id, "before": out["before"],
                "after": out["after"], "backup": out["backup"],
                "stale_marks": out["stale_marks"]},
    )
    out["message"] = f"Updated {row_id} in {key}."
    return out


@router.delete("/{key}/rows/{row_id}")
async def remove_row(
    request: Request,
    key: str,
    row_id: str,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Delete one `added` row, and un-sync the observation that produced it.

    Clearing `synced_to_dataset_at` matters: without it the portal would keep
    reporting the observation as "in the model" after its row had been removed
    from the file the model reads, which is exactly the split-brain the sync
    status exists to expose.
    """
    out = ds.delete_row(key, row_id)

    unsynced = 0
    ref = out.get("record_ref")
    if ref:
        res = await db.execute(text("""
            UPDATE field_observations
            SET synced_to_dataset_at = NULL, dataset_sync_ref = NULL
            WHERE dataset_sync_ref = :ref
            RETURNING id
        """), {"ref": ref})
        unsynced = len(res.fetchall())
        await db.commit()
    out["observations_unsynced"] = unsynced

    await audit.record(
        action="dataset.row_delete", entity_type="datasets",
        entity_id=f"{key}:{row_id}", actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None,
        detail={"dataset": key, "row_id": row_id, "removed": out["removed"],
                "backup": out["backup"], "observations_unsynced": unsynced,
                "stale_marks": out["stale_marks"]},
    )
    out["message"] = (f"Deleted {row_id} from {key}."
                      + (f" {unsynced} observation(s) returned to unsynced."
                         if unsynced else ""))
    return out


@router.post("/{key}/restore")
async def restore_dataset(
    request: Request,
    key: str,
    backup_name: str = Query(..., description="a name from GET /{key}/backups"),
    actor: User = Depends(require_admin),
) -> dict[str, Any]:
    """Roll a file back to a restore point. The current file is backed up first."""
    out = ds.restore(key, backup_name)
    await audit.record(
        action="dataset.restore", entity_type="datasets", entity_id=key,
        actor_id=actor.id, actor_label=actor.email,
        ip_address=request.client.host if request.client else None,
        detail={"dataset": key, **out},
    )
    out["message"] = f"Restored {key} from {backup_name}."
    return out


# The link back to `field_observations` is the row's own `record_ref` column,
# written at sync time. A whole sync batch shares one ref, so deleting any row
# from a batch frees every observation in it — correct for the single-row batches
# this actually sees, and the response reports the count either way rather than
# claiming a number it did not verify.
