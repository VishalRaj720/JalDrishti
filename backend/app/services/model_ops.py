"""What is stale, how to rebuild it, and how to put everything back.

THE PROBLEM THIS SOLVES. Syncing a row into `Datasets/` is not the same as the
engine using it. Two of the four writable files feed **derived** artifacts:

    cgwb_waterlevel_jharkhand.csv  ->  flow_field.npz    (gradient, azimuth)
    waterQuality_jharkhand.csv     ->  excursion baselines

Until those are rebuilt, an admin who synced a reading and watched nothing change
has no way to tell whether the sync failed or whether the rebuild is simply
outstanding. `status()` answers that by comparing each artifact's mtime against
its inputs', so "stale" is measured rather than remembered.

The ore files are different and deliberately absent from the staleness list:
`ore_zone_at()` and `grade_c0_factor()` read their CSV/XLSX at serve time behind
an lru_cache, so clearing the cache — which every sync and every row edit already
does — is the whole of the update.

FACTORY RESET is the emergency path: strip every `added` row from every dataset,
returning the files to exactly what shipped, and free the observations that
produced them. It deliberately does **not** delete the observations themselves.
A field officer's submitted work is not the admin's to destroy; the reset
un-applies it, and it can be re-synced.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import audit, datasets as ds

REPO_ROOT = ds.REPO_ROOT
FLOW_FIELD_NPZ = REPO_ROOT / "ml_pipeline" / "data_prep" / "artifacts" / "flow_field.npz"
DEM = ds.DATASETS / "jharkhand_glo30_dem.tif"


def _mtime(p: Path) -> Optional[float]:
    return p.stat().st_mtime if p.exists() else None


def _iso(ts: Optional[float]) -> Optional[str]:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


#: derived artifact -> (path, the dataset keys it is built from)
DERIVED: dict[str, tuple[Path, tuple[str, ...]]] = {
    "flow_field": (FLOW_FIELD_NPZ, ("groundwater_levels",)),
    # Baselines are computed in-process from the chemistry CSV rather than baked
    # to a file, so there is no artifact mtime to compare. Staleness is reported
    # from the cache-clear marker instead; see `_baselines_state`.
    "excursion_baselines": (Path(), ("water_quality",)),
}

#: Written whenever baselines are recomputed. A file, not memory, because the
#: question "is this stale" must survive a restart — an in-process flag would
#: report everything fresh after every deploy.
BASELINE_MARK = REPO_ROOT / "ml_pipeline" / "data_prep" / "artifacts" / ".baselines_built"


def status() -> dict[str, Any]:
    """Per derived artifact: built when, from what, and is it now stale."""
    out: list[dict[str, Any]] = []

    for name, (artifact, sources) in DERIVED.items():
        mark = BASELINE_MARK if name == "excursion_baselines" else artifact
        built = _mtime(mark)
        newest_input, newest_key = None, None
        for key in sources:
            t = _mtime(ds.get(key).path)
            if t and (newest_input is None or t > newest_input):
                newest_input, newest_key = t, key
        stale = bool(newest_input and (built is None or newest_input > built))
        entry = {
            "artifact": name,
            "built_at": _iso(built),
            "exists": built is not None,
            "sources": list(sources),
            "newest_input": newest_key,
            "newest_input_at": _iso(newest_input),
            "stale": stale,
        }
        if name == "flow_field":
            entry["requires_dem"] = True
            entry["dem_present"] = DEM.exists()
            if stale and not DEM.exists():
                entry["blocked"] = (
                    "The flow field is stale but jharkhand_glo30_dem.tif is missing. "
                    "It is built from CGWB stations where there are at least five "
                    "within 25 km and from smoothed DEM topography everywhere else, "
                    "so rebuilding without it would silently produce a station-only "
                    "field over most of the state.")
        out.append(entry)

    any_stale = any(e["stale"] for e in out)
    return {
        "artifacts": out,
        "any_stale": any_stale,
        "message": (
            "Some derived artifacts are stale — the datasets have changed since "
            "they were built, so the engine is not yet using the new rows."
            if any_stale else
            "Every derived artifact is current with its inputs."),
        "note": ("Ore zone and grade are not listed: they are read at serve time "
                 "behind a cache that every sync and edit already clears, so they "
                 "need no rebuild."),
    }


def mark_baselines_built() -> None:
    BASELINE_MARK.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_MARK.write_text(
        f"built {datetime.now(tz=timezone.utc).isoformat()}\n", encoding="utf-8")


def recompute_baselines() -> dict[str, Any]:
    """Drop the memoised chemistry reads and re-derive the ambient baselines.

    The baselines are computed from `waterQuality_jharkhand.csv` on demand, so
    "recompute" means invalidating the cache and forcing one read back through
    the real loader — which is also the cheapest honest way to prove the new rows
    parse before an admin is told the job succeeded.
    """
    ds.invalidate_caches()
    detail: dict[str, Any] = {}
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from ml_pipeline.data_prep import jharkhand_loader as jl

        frame = jl.load_jharkhand_water_quality()
        detail["rows"] = int(len(frame))
        detail["loader"] = "jharkhand_loader.load_jharkhand_water_quality"
    except Exception as exc:  # noqa: BLE001
        # Report rather than swallow: a loader that cannot read the file after a
        # sync is exactly the failure this endpoint exists to surface.
        raise ds.DatasetError(
            f"chemistry did not reload after sync: {exc}. The file may have a "
            f"column mismatch — restore the most recent backup and check the "
            f"appended rows.") from exc

    mark_baselines_built()
    return {"ok": True, "artifact": "excursion_baselines", **detail,
            "message": "Baselines recomputed from the current chemistry file."}


def rebuild_flow_field() -> dict[str, Any]:
    """Re-bake `flow_field.npz` from CGWB levels + the DEM.

    Loud, not silent, when the DEM is absent: a station-only field would still
    produce numbers, and they would be wrong over most of the state.
    """
    if not DEM.exists():
        raise ds.DatasetError(
            f"cannot rebuild the flow field: {DEM.name} is not on disk. The field "
            f"falls back to smoothed DEM topography wherever there are fewer than "
            f"five CGWB stations within 25 km, which is most of Jharkhand. "
            f"Rebuilding without it would quietly change what every pin resolves to.")

    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from ml_pipeline.data_prep import flow_field as ff

    logger.info("rebuilding flow field — this reads the DEM and may take a minute")
    ff.build_flow_field()
    ds.invalidate_caches()
    return {"ok": True, "artifact": "flow_field",
            "built_at": _iso(_mtime(FLOW_FIELD_NPZ)),
            "message": "Flow field rebuilt from CGWB levels and the GLO-30 DEM."}


async def factory_reset(db: AsyncSession, *, actor, dry_run: bool = False,
                        ip: Optional[str] = None) -> dict[str, Any]:
    """Strip every `added` row from every dataset and free its observation.

    The emergency path. Backs up each file first, so the reset is itself
    reversible from `GET /datasets/{key}/backups`.
    """
    per_file = {key: ds.strip_added(key, dry_run=True) for key in ds.REGISTRY}
    total = sum(p["would_remove"] for p in per_file.values())

    result: dict[str, Any] = {
        "dry_run": dry_run,
        "would_remove": total,
        "by_file": per_file,
        "note": ("Field observations are NOT deleted. They return to 'approved, "
                 "not yet in the model' and can be re-synced. Only the rows this "
                 "system wrote into Datasets/ are removed."),
    }
    if dry_run:
        result["message"] = (
            f"Would remove {total} added row(s) across "
            f"{sum(1 for p in per_file.values() if p['would_remove'])} file(s), "
            f"and return their observations to unsynced.")
        return result
    if not total:
        result["message"] = "Nothing to reset — no added rows in any dataset."
        result["observations_unsynced"] = 0
        return result

    applied = {key: ds.strip_added(key) for key in ds.REGISTRY}
    res = await db.execute(text("""
        UPDATE field_observations
        SET synced_to_dataset_at = NULL, dataset_sync_ref = NULL
        WHERE synced_to_dataset_at IS NOT NULL
        RETURNING id
    """))
    unsynced = len(res.fetchall())
    await db.commit()
    ds.invalidate_caches()

    result["by_file"] = applied
    result["removed"] = sum(p.get("removed", 0) for p in applied.values())
    result["observations_unsynced"] = unsynced
    result["backups"] = [p["backup"] for p in applied.values() if p.get("backup")]
    result["stale_marks"] = sorted(
        {m for k in ds.REGISTRY for m in ds.get(k).stale_marks})

    await audit.record(
        action="model_ops.factory_reset", entity_type="datasets",
        entity_id="ALL", actor_id=actor.id, actor_label=actor.email,
        ip_address=ip,
        detail={"removed": result["removed"], "observations_unsynced": unsynced,
                "backups": result["backups"], "by_file": {
                    k: v.get("removed", 0) for k, v in applied.items()}},
    )
    result["message"] = (
        f"Reset complete. Removed {result['removed']} added row(s); "
        f"{unsynced} observation(s) returned to unsynced. "
        f"Derived artifacts are now stale — rebuild them.")
    return result
