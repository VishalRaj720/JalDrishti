"""Carry approved field observations into `Datasets/`, deliberately and by hand.

WHY THIS IS MANUAL. Three architectures were considered (PRODUCT_DESIGN.md
§3.6): auto-feeding the database into the engine, a continuous DB→dataset sync,
or an admin-triggered export. The first breaks reproducibility — the same pin
and sliders would return different answers over time with nothing recorded, and
a regulator cannot defend a number that moves. The second is the right end state
if this ever ingests sensor streams, and is heavy machinery for the handful of
ore sightings actually expected. So: **admin-triggered, audited, reversible.**

WHY ONLY ORE IS AUTOMATED HERE. An ore observation is the one field input that
currently does nothing at all: `ore_zone_at()` reads the deposit CSV, and a pin
in `zone == "none"` suppresses the uranium plume entirely (frozen rule #3, "the
tool cannot invent contamination"). So an approved *"uranium ore found here"*
leaves the simulation still reporting no plume — the exact case the field-officer
role exists for. Chemistry and groundwater-level corrections stay manual: they
move a feature *value* the model was already trained across, they are rare, and
the audit log gives an admin the old/new values to apply by hand.

WHAT A SYNC TOUCHES

    Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv
        Drives `ore_zone_at()` — whether a pin is deposit / belt / none, and
        therefore whether a uranium plume is possible at all.
    Datasets/udepo_uranium_deposits.xlsx  (header row 8)
        Drives `grade_c0_factor()` — scales the source concentration C0.

Both gain an `origin` column, `original` for the rows that shipped with the
project and `added` for anything a regulator approved, so a map can render the
two differently and a reader can always tell which is which. Existing rows are
backfilled as `original` on first sync.

THIS DOES NOT RETRAIN ANYTHING. Adding a deposit changes a *resolved input*, not
the model: C0 and the ore zone are read at serve time, and the surrogate was
trained across the full Texas C0 envelope. Retraining is only required when the
generator's assumptions change (§4.6 rule 9). The caller is told so explicitly.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger
from sqlalchemy import bindparam as sa_bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppException
from app.services import audit

REPO_ROOT = Path(__file__).resolve().parents[3]
ORE_CSV = REPO_ROOT / "Datasets" / "Jharkhand Ore" / "jharkhand_uranium_deposits.csv"
UDEPO_XLSX = REPO_ROOT / "Datasets" / "udepo_uranium_deposits.xlsx"
UDEPO_HEADER_ROW = 8          # matches ml_pipeline/data_prep/ore_grades.py

ORIGIN_COL = "origin"
ORIGIN_ORIGINAL = "original"
ORIGIN_ADDED = "added"

#: Only ore observations have an automated path. Everything else is reported as
#: pending and applied by an admin from the audit log.
SYNCABLE_TYPES = ("ore_presence",)


class DatasetSyncError(AppException):
    def __init__(self, message: str):
        super().__init__(message, status_code=409)


def _radius_polygon_wkt(lon: float, lat: float, radius_m: float = 400.0,
                        n: int = 24) -> str:
    """A small circular outline around the sighting.

    A field observation is a point; `ore_zone_at()` needs an outline to test
    containment against. 400 m is the order of the existing deposit outlines and
    is recorded in the row's notes so nobody mistakes it for a surveyed boundary.
    """
    import math
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 1e-6))
    pts = []
    for i in range(n + 1):
        th = 2.0 * math.pi * i / n
        pts.append(f"{lon + dlon * math.cos(th):.6f} {lat + dlat * math.sin(th):.6f}")
    return f"POLYGON(({', '.join(pts)}))"


async def pending_summary(db: AsyncSession) -> dict[str, Any]:
    """Counts for the three UI states, plus the amber backlog by type."""
    rows = (await db.execute(text("""
        SELECT observation_type,
               count(*) FILTER (WHERE status = 'pending')                       AS pending_review,
               count(*) FILTER (WHERE status = 'approved'
                                  AND synced_to_dataset_at IS NULL)             AS approved_unsynced,
               count(*) FILTER (WHERE status = 'approved'
                                  AND synced_to_dataset_at IS NOT NULL)         AS in_model
        FROM field_observations
        GROUP BY observation_type
    """))).mappings().all()

    by_type = {r["observation_type"]: dict(r) for r in rows}
    total_unsynced = sum(r["approved_unsynced"] for r in rows)
    total_pending = sum(r["pending_review"] for r in rows)
    total_in_model = sum(r["in_model"] for r in rows)

    return {
        "pending_review": total_pending,
        "approved_pending_sync": total_unsynced,
        "approved_in_model": total_in_model,
        "by_type": by_type,
        "syncable_types": list(SYNCABLE_TYPES),
        # The sentence the UI shows verbatim.
        "message": (
            f"{total_unsynced} approved observation(s) are not yet in the model."
            if total_unsynced else
            "All approved observations are reflected in the model."),
        "note": ("Approved observations are authoritative in the portal "
                 "immediately, but the physics engine and surrogate read only "
                 "Datasets/. A sync is a deliberate admin action; it changes "
                 "resolved inputs, not the trained model."),
    }


async def _unsynced_ore(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(text("""
        SELECT f.id::text            AS obs_id,
               o.id::text            AS ore_id,
               o.name, o.ore_zone, o.uranium_grade_pct, o.depth_m,
               o.notes, o.observed_at,
               ST_X(o.location::geometry) AS lon,
               ST_Y(o.location::geometry) AS lat
        FROM field_observations f
        JOIN ore_observations o ON o.origin_observation_id = f.id
        WHERE f.observation_type = 'ore_presence'
          AND f.status = 'approved'
          AND f.synced_to_dataset_at IS NULL
        ORDER BY f.reviewed_at
    """))).mappings().all()
    return [dict(r) for r in rows]


def _ensure_origin_column_csv(df, path: Path) -> None:
    if ORIGIN_COL not in df.columns:
        df[ORIGIN_COL] = ORIGIN_ORIGINAL
        logger.info(f"{path.name}: added '{ORIGIN_COL}' column, "
                    f"backfilled {len(df)} row(s) as '{ORIGIN_ORIGINAL}'")
    else:
        df[ORIGIN_COL] = df[ORIGIN_COL].fillna(ORIGIN_ORIGINAL)


def _backup(path: Path, ref: str) -> Path:
    """Copy beside the original before rewriting. These files are tracked data;
    an admin action that appends to them should be trivially undoable."""
    bak = path.with_suffix(path.suffix + f".{ref}.bak")
    shutil.copy2(path, bak)
    return bak


async def sync_ore(db: AsyncSession, *, actor, dry_run: bool = False,
                   ip: Optional[str] = None) -> dict[str, Any]:
    """Append approved ore observations to both dataset files."""
    import pandas as pd

    items = await _unsynced_ore(db)
    ref = uuid.uuid4().hex[:12]
    result: dict[str, Any] = {
        "sync_ref": ref, "dry_run": dry_run, "count": len(items),
        "deposits": [i["name"] for i in items],
        "files": [], "backups": [],
        "retrain_required": False,
        "note": ("Adding a deposit changes a RESOLVED INPUT (ore zone and C0), "
                 "not the trained model. No retrain or re-bake is required; the "
                 "surrogate was trained across the full source envelope. See "
                 "PRODUCT_DESIGN.md section 4.6 rule 9 for what does require one."),
    }
    if not items:
        result["message"] = "Nothing to sync."
        return result

    for p in (ORE_CSV, UDEPO_XLSX):
        if not p.exists():
            raise DatasetSyncError(f"dataset file missing: {p}")

    # ── the deposit outline CSV — drives ore_zone_at() ───────────────
    csv_df = pd.read_csv(ORE_CSV)
    _ensure_origin_column_csv(csv_df, ORE_CSV)
    existing = {str(n).strip().lower() for n in csv_df["name"].fillna("")}

    new_csv_rows, skipped = [], []
    for it in items:
        if str(it["name"]).strip().lower() in existing:
            # Name collision: ore_zone_at and grade lookup both key on name, so
            # a duplicate would make the grade ambiguous. Refuse the row rather
            # than shadow an existing deposit.
            skipped.append(it["name"])
            continue
        new_csv_rows.append({
            "name": it["name"],
            "district": "", "state": "Jharkhand",
            "center_lat": round(float(it["lat"]), 6),
            "center_lon": round(float(it["lon"]), 6),
            "status": "Field-observed",
            "geometry_wkt": _radius_polygon_wkt(float(it["lon"]), float(it["lat"])),
            "notes": (f"Field observation approved {it['observed_at']}. "
                      f"Outline is a 400 m radius around the sighting, NOT a "
                      f"surveyed boundary. "
                      f"{(it['notes'] or '').strip()}").strip(),
            ORIGIN_COL: ORIGIN_ADDED,
        })
    result["skipped_duplicate_name"] = skipped

    # ── the grade workbook — drives grade_c0_factor() ────────────────
    xl_df = pd.read_excel(UDEPO_XLSX, header=UDEPO_HEADER_ROW).dropna(how="all")
    if ORIGIN_COL not in xl_df.columns:
        xl_df[ORIGIN_COL] = ORIGIN_ORIGINAL
    else:
        xl_df[ORIGIN_COL] = xl_df[ORIGIN_COL].fillna(ORIGIN_ORIGINAL)

    new_xl_rows = []
    for it in items:
        if it["name"] in skipped:
            continue
        grade = it["uranium_grade_pct"]
        new_xl_rows.append({
            "Country": "India",
            "Deposit ID": f"FIELD-{it['ore_id'][:8]}",
            "Deposit Name": it["name"],
            "Main Commodity": "Uranium",
            "Deposit Type": "Field observation",
            "Deposit Subtype": it["ore_zone"],
            "Resource Range": "",
            # `_parse_grade` reads a range string; a single value is valid input.
            "Grade Range": (f"{float(grade):g}" if grade is not None else ""),
            ORIGIN_COL: ORIGIN_ADDED,
        })

    if dry_run:
        result["message"] = (f"Would append {len(new_csv_rows)} deposit row(s) "
                             f"and {len(new_xl_rows)} grade row(s).")
        return result

    if new_csv_rows:
        result["backups"].append(str(_backup(ORE_CSV, ref)))
        out = pd.concat([csv_df, pd.DataFrame(new_csv_rows)], ignore_index=True)
        out.to_csv(ORE_CSV, index=False)
        result["files"].append(str(ORE_CSV.relative_to(REPO_ROOT)))

    if new_xl_rows:
        result["backups"].append(str(_backup(UDEPO_XLSX, ref)))
        out = pd.concat([xl_df, pd.DataFrame(new_xl_rows)], ignore_index=True)
        # Preserve the 8-row preamble so ore_grades.py's `header=8` still lands
        # on the real header row.
        import openpyxl
        wb = openpyxl.load_workbook(UDEPO_XLSX)
        ws = wb[wb.sheetnames[0]]
        header = [c.value for c in ws[UDEPO_HEADER_ROW + 1]]
        if ORIGIN_COL not in [str(h) for h in header]:
            ws.cell(row=UDEPO_HEADER_ROW + 1, column=len(header) + 1,
                    value=ORIGIN_COL)
            for r in range(UDEPO_HEADER_ROW + 2, ws.max_row + 1):
                ws.cell(row=r, column=len(header) + 1, value=ORIGIN_ORIGINAL)
            header = header + [ORIGIN_COL]
        for row in new_xl_rows:
            ws.append([row.get(str(h), "") for h in header])
        wb.save(UDEPO_XLSX)
        result["files"].append(str(UDEPO_XLSX.relative_to(REPO_ROOT)))

    synced_ids = [it["obs_id"] for it in items if it["name"] not in skipped]
    if synced_ids:
        # `expanding=True` rather than a Postgres array literal: asyncpg binds
        # by Python type and rejects the '{a,b}' string form outright.
        stmt = text("""
            UPDATE field_observations
            SET synced_to_dataset_at = now(), dataset_sync_ref = :ref
            WHERE id IN :ids
        """).bindparams(sa_bindparam("ids", expanding=True))
        await db.execute(stmt, {"ref": ref,
                                "ids": [uuid.UUID(i) for i in synced_ids]})
        await db.commit()

    invalidate_ml_caches()

    await audit.record(
        action="dataset.sync_ore", entity_type="datasets", entity_id=ref,
        actor_id=actor.id, actor_label=actor.email, ip_address=ip,
        detail={"sync_ref": ref, "synced": len(synced_ids),
                "deposits": result["deposits"], "skipped": skipped,
                "files": result["files"], "backups": result["backups"],
                "retrain_required": False},
    )
    result["synced"] = len(synced_ids)
    result["message"] = (f"Synced {len(synced_ids)} ore observation(s) into "
                         f"{len(result['files'])} dataset file(s).")
    return result


def invalidate_ml_caches() -> None:
    """Drop the pipeline's dataset caches so a sync takes effect immediately.

    `ore_loader` and `ore_grades` memoise their parsed files with
    `functools.lru_cache`, so without this a running process keeps serving the
    pre-sync ore map until it restarts — and the sync would look like it had
    done nothing.
    """
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    cleared = []
    for mod_name in ("ml_pipeline.data_prep.ore_loader",
                     "ml_pipeline.data_prep.ore_grades"):
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"could not reach {mod_name} to clear its cache: {exc}")
            continue
        for attr in dir(mod):
            fn = getattr(mod, attr)
            if hasattr(fn, "cache_clear"):
                fn.cache_clear()
                cleared.append(f"{mod_name}.{attr}")
    logger.info(f"cleared {len(cleared)} ml_pipeline dataset cache(s)")
    return None
