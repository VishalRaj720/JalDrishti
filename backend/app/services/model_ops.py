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
from app.services.dataset_lock import with_dataset_lock

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


@with_dataset_lock("factory reset")
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


# ═══════════════════════════════════════════════════════════════════════
# Model artifact backup
#
# WHY THIS EXISTS. `ml_pipeline/ml/artifacts/` holds the trained surrogate: nine
# XGBoost quantile heads, the excursion regressor, the conformal calibration and
# the model card. Sixteen files, 12 MB — and **only five are tracked in git**
# (the JSON metadata). All ten `.joblib` weight files are untracked, so the
# trained model exists in exactly one copy, on one disk, with no version history
# behind it.
#
# `ml.train` overwrites that directory in place, and the project README documents
# running it from the command line. So the documented, ordinary workflow can
# destroy the only copy of a model whose conformal coverage was hand-verified,
# with nothing to restore from.
#
# This is not about retraining. Nothing here currently requires a retrain —
# ore zones, grades, the flow field and baselines are all *serve-time inputs* the
# surrogate was already trained across, which is why `dataset_sync` reports
# `retrain_required: False`. It is about a single unbacked-up copy of the most
# expensive artifact in the repo.
#
# Bundles live outside `artifacts/` so a restore cannot recurse into its own
# backups, and are gitignored: 12 MB per bundle does not belong in git history.
# ═══════════════════════════════════════════════════════════════════════

MODEL_ARTIFACTS = REPO_ROOT / "ml_pipeline" / "ml" / "artifacts"
MODEL_BUNDLES = REPO_ROOT / "ml_pipeline" / "ml" / "artifact_bundles"


def _bundle_meta(d: Path) -> dict[str, Any]:
    files = [f for f in d.iterdir() if f.is_file()]
    # The SAME hash `ml_pipeline_adapter` pins onto every stored run, so a bundle
    # can be matched against the runs that were computed with it. The card has no
    # `model_card_sha` field of its own — the sha IS of the file.
    card = d / "model_card.json"
    sha = None
    if card.exists():
        import hashlib
        sha = hashlib.sha256(card.read_bytes()).hexdigest()
    return {
        "name": d.name,
        "created_at": _iso(_mtime(d)),
        "files": len(files),
        "size_mb": round(sum(f.stat().st_size for f in files) / 1_048_576, 1),
        "model_card_sha": sha,
        # `relative_to` raises when the bundle dir is outside the repo, which
        # happens in tests and would happen for any operator who relocated it.
        "note_path": (str(d.relative_to(REPO_ROOT))
                      if d.is_relative_to(REPO_ROOT) else str(d)),
    }


def list_model_backups() -> list[dict[str, Any]]:
    if not MODEL_BUNDLES.exists():
        return []
    return [_bundle_meta(d) for d in
            sorted(MODEL_BUNDLES.iterdir(), key=lambda p: p.stat().st_mtime,
                   reverse=True) if d.is_dir()]


def backup_model(label: str = "") -> dict[str, Any]:
    """Copy the live artifacts into a timestamped bundle."""
    import re
    import shutil as sh

    if not MODEL_ARTIFACTS.exists():
        raise ds.DatasetError(
            f"nothing to back up: {MODEL_ARTIFACTS} does not exist", status_code=404)

    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # The label reaches a filesystem path, so it is reduced to a safe slug rather
    # than trusted.
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-")[:40]
    dest = MODEL_BUNDLES / (f"{stamp}_{slug}" if slug else stamp)
    if dest.exists():
        raise ds.DatasetError(f"bundle already exists: {dest.name}")

    MODEL_BUNDLES.mkdir(parents=True, exist_ok=True)
    sh.copytree(MODEL_ARTIFACTS, dest)
    meta = _bundle_meta(dest)
    logger.info(f"model artifacts backed up to {dest.name} "
                f"({meta['files']} files, {meta['size_mb']} MB)")
    return {"ok": True, **meta,
            "message": f"Backed up {meta['files']} artifact file(s) to {dest.name}."}


def restore_model(name: str) -> dict[str, Any]:
    """Put a bundle back, after backing up what is currently live.

    Restoring without first preserving the current state would make the restore
    itself the unrecoverable operation, which is the bug this module exists to
    prevent.
    """
    import shutil as sh

    # `name` arrives from the client, and this function calls rmtree() on the
    # live artifacts, so containment is checked before anything is destroyed.
    #
    # Comparing `(MODEL_BUNDLES / name).parent` against MODEL_BUNDLES is NOT
    # enough and was the first attempt: for name="..", that path is
    # `bundles/..`, whose `.parent` is literally `bundles` — so the check passed
    # and the restore copied the *parent* directory over the artifacts. Resolve
    # first, then require the result to be a direct child.
    root = MODEL_BUNDLES.resolve()
    src = (MODEL_BUNDLES / name).resolve()
    if ("/" in name or "\\" in name or name in {"", ".", ".."}
            or src.parent != root or src == root or not src.is_dir()):
        raise ds.DatasetError(f"not a model bundle: {name!r}", status_code=404)

    pre = backup_model("pre-restore")
    sh.rmtree(MODEL_ARTIFACTS)
    sh.copytree(src, MODEL_ARTIFACTS)
    ds.invalidate_caches()
    logger.info(f"model artifacts restored from {name}")
    return {"ok": True, "restored_from": name,
            "backup_of_previous": pre["name"],
            "message": (f"Restored the model from {name}. The version that was "
                        f"live is saved as {pre['name']}.")}


def model_state() -> dict[str, Any]:
    """What model is live, and is there anything to fall back to."""
    live = MODEL_ARTIFACTS.exists()
    files = ([f.name for f in MODEL_ARTIFACTS.iterdir() if f.is_file()]
             if live else [])
    weights = [f for f in files if f.endswith(".joblib")]
    bundles = list_model_backups()
    return {
        "live": live,
        "files": len(files),
        "weight_files": len(weights),
        "built_at": _iso(_mtime(MODEL_ARTIFACTS)),
        "backups": bundles,
        "unprotected": not bundles,
        "message": (
            "No backup exists. The trained model is a single copy — `ml.train` "
            "overwrites it in place and the weight files are not in git."
            if not bundles else
            f"{len(bundles)} backup(s) available; the newest is "
            f"{bundles[0]['name']}."),
    }


async def seed_database_from_datasets() -> dict[str, Any]:
    """Carry `Datasets/` INTO the database — the reverse of a dataset sync.

    `dataset_sync` moves approved observations DB -> Datasets/. This is the other
    direction, and it is what an admin needs after editing a dataset file
    directly through the Dataset Manager or replacing one via /ingest: until it
    runs, the portal's own record (wells, samples, district bands) is behind the
    files the engine reads.

    Only the GEODATA stages run — districts, sub-districts, aquifers,
    groundwater levels, water quality. Deliberately NOT the whole seed: that
    also creates demo users, organisations and ISR points, and re-creating weak
    demo logins from a button on a running system would be a security decision
    disguised as a refresh.

    Safe to run repeatedly. Districts and blocks upsert by name, wells by
    lat/lon, level readings by (station, timestamp), and water samples by
    (well, sampled_at) — the last of which was a blind insert until R11 and
    duplicated all 397 rows on any re-seed after an edit.

    The ore files are absent on purpose: `ore_zone_at()` and `grade_c0_factor()`
    read their CSV/XLSX straight off disk, so an ore edit needs no database
    round trip at all.
    """
    import sys

    from app.database import AsyncSessionLocal

    if str(REPO_ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "backend"))
    from scripts.seed import seed_geodata

    async with AsyncSessionLocal() as db:
        stages = await seed_geodata(db, ds.DATASETS)

    wq = stages.get("water_quality", {}) or {}
    gwl = stages.get("groundwater_levels", {}) or {}
    parts = []
    if wq.get("samples_inserted"):
        parts.append(f"{wq['samples_inserted']} new sample(s)")
    if wq.get("samples_updated"):
        parts.append(f"{wq['samples_updated']} updated")
    if gwl.get("readings_inserted"):
        parts.append(f"{gwl['readings_inserted']} new level reading(s)")

    return {
        "ok": True,
        "stages": stages,
        "message": ("Database updated from Datasets/: " + ", ".join(parts)
                    if parts else
                    "Database already matches Datasets/ — nothing to change."),
    }
