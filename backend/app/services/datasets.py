"""Row-level control over the files the physics engine actually reads.

WHY THIS EXISTS. `dataset_sync.py` carries approved field observations *into*
`Datasets/`. It is append-only, so until now a row that landed there was
permanent: a typo in a field officer's grade estimate, or a sighting later shown
to be something else, could be approved into the engine's inputs and never taken
back out. This module is the other half — list, edit, delete, restore — and the
provenance column that makes any of it safe.

THE `record_source` COLUMN. Every writable dataset gains one, values `original`
or `added`, backfilled to `original` the first time the file is touched.

    original   shipped with the project — CGWB, UDEPO, GSI, NAQUIM
    added      written by this system from an approved field observation

**`original` rows are immutable.** Not editable, not deletable, enforced here in
the service layer with a 409 so every caller hits it rather than in the UI where
only a browser would. A screening tool whose operator can quietly rewrite its own
evidence base cannot defend a number, and the whole point of the column is that
the distinction is mechanical rather than a matter of remembering.

WHY NOT JUST `source`. The obvious name was taken, twice, meaning something else:
`cgwb_waterlevel_jharkhand.csv` has `source` = the collecting agency (`CGWB`),
and `naquim_reference/naquim_vertical.csv` has `source` = the citation a row was
extracted from. Overloading either would destroy real data and mislead anyone
reading the file directly, so the provenance marker gets its own unambiguous
name and uses it in every file.

ROW IDENTITY is the file's own natural key, never a positional index — indices
shift under deletion, and an admin acting on a stale list would hit the wrong
row. Each registry entry names its id column.

EVERY MUTATION: back up first, write, clear the pipeline's caches, audit. The
backup is what makes this reversible, and `restore()` is the way back.
"""
from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.exceptions import AppException

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS = REPO_ROOT / "Datasets"

#: The provenance column. See the module docstring for why it is not `source`.
SOURCE_COL = "record_source"
SOURCE_ORIGINAL = "original"
SOURCE_ADDED = "added"

#: The sync batch that wrote an `added` row; empty on `original` rows.
#:
#: Without it, deleting a row could not free the observation that produced it —
#: nothing else links a line in a CSV back to a `field_observations` id — and the
#: portal would go on reporting an observation as "in the model" after its row had
#: been removed from the file the model reads. Encoding the link in a free-text
#: `notes` field was tried first and is not sound: two of these files have no
#: notes column, and a human editing notes would silently break provenance.
REF_COL = "record_ref"


class DatasetError(AppException):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message, status_code=status_code)


@dataclass(frozen=True)
class DatasetFile:
    """One file the engine reads and this system may write."""

    key: str            #: URL-safe identifier used by the API
    relpath: str        #: path under Datasets/
    kind: str           #: "csv" | "xlsx"
    id_column: str      #: the file's own natural key
    label: str
    governs: str        #: what changes in the model when this file changes
    stale_marks: tuple[str, ...] = ()   #: derived artifacts invalidated by a write
    header_row: int = 0                 #: xlsx only — rows of preamble above the header

    @property
    def path(self) -> Path:
        return DATASETS / self.relpath


#: Everything the application may write. Reference geography (district, aquifer
#: and river GeoJSON) is deliberately absent: it is replaced wholesale through
#: `/ingest/*`, which checksums the source file and writes a `dataset_versions`
#: row, not edited row by row.
REGISTRY: dict[str, DatasetFile] = {
    "water_quality": DatasetFile(
        key="water_quality",
        relpath="waterQuality_jharkhand.csv",
        kind="csv",
        id_column="S. No.",
        label="Groundwater chemistry (CGWB)",
        governs="Excursion baselines, and the measured uranium a district's band is "
                "computed from.",
        stale_marks=("excursion_baselines",),
    ),
    "groundwater_levels": DatasetFile(
        key="groundwater_levels",
        relpath="cgwb_waterlevel_jharkhand.csv",
        kind="csv",
        id_column="id",
        label="Groundwater levels (CGWB)",
        governs="The groundwater flow field — hydraulic gradient and flow azimuth at "
                "every pin. Requires a flow-field rebuild to take effect.",
        stale_marks=("flow_field",),
    ),
    "ore_deposits": DatasetFile(
        key="ore_deposits",
        relpath="Jharkhand Ore/jharkhand_uranium_deposits.csv",
        kind="csv",
        id_column="name",
        label="Uranium deposit outlines",
        governs="Whether a pin resolves to deposit / belt / none — and therefore "
                "whether a uranium plume is possible there at all.",
    ),
    "ore_grades": DatasetFile(
        key="ore_grades",
        relpath="udepo_uranium_deposits.xlsx",
        kind="xlsx",
        id_column="Deposit ID",
        label="Uranium deposit grades (UDEPO)",
        governs="The grade factor scaling source concentration C0.",
        header_row=8,
    ),
    "naquim_vertical": DatasetFile(
        key="naquim_vertical",
        relpath="naquim_reference/naquim_vertical.csv",
        kind="csv",
        id_column="district",
        label="NAQUIM vertical structure",
        governs="Per-district aquifer layer bases and fracture depth ranges.",
    ),
}


def get(key: str) -> DatasetFile:
    try:
        return REGISTRY[key]
    except KeyError:
        raise DatasetError(f"unknown dataset '{key}'", status_code=404) from None


# ── reading ──────────────────────────────────────────────────────────

def _read(df_file: DatasetFile):
    """Load a dataset into a DataFrame with `record_source` guaranteed present."""
    import pandas as pd

    p = df_file.path
    if not p.exists():
        raise DatasetError(f"dataset file missing: {p}", status_code=404)

    if df_file.kind == "xlsx":
        df = pd.read_excel(p, header=df_file.header_row).dropna(how="all")
    else:
        # utf-8-sig: waterQuality_jharkhand.csv carries a BOM, which would
        # otherwise become part of the first column's name ("﻿S. No.")
        # and break every lookup against `id_column`.
        df = pd.read_csv(p, encoding="utf-8-sig")

    if SOURCE_COL not in df.columns:
        df[SOURCE_COL] = SOURCE_ORIGINAL
    else:
        df[SOURCE_COL] = df[SOURCE_COL].fillna(SOURCE_ORIGINAL)
    if REF_COL not in df.columns:
        df[REF_COL] = ""
    else:
        df[REF_COL] = df[REF_COL].fillna("")
    return df


def _write_csv(df_file: DatasetFile, df) -> None:
    """Persist a DataFrame back over a CSV. Verified round-trip-clean."""
    df.to_csv(df_file.path, index=False, encoding="utf-8-sig")


# ── xlsx: mutate the sheet in place, never re-dump it ─────────────────
#
# The obvious implementation — read with pandas, write the frame back — was
# built first and silently corrupted the file: `grade_c0_factor("Jaduguda")`
# went from (0.6, 0.03) to (1.0, None) after a *no-op* round trip, with the row
# count unchanged. `pd.read_excel(header=8)` renames blank and duplicate header
# cells ("Unnamed: 5"), so writing back by matching the Excel header text against
# frame column names blanks every column whose name pandas altered.
#
# Nothing here reconstructs the sheet. It finds a row, changes or removes it, and
# leaves every other cell — and the 8-row preamble `ore_grades.py` relies on —
# exactly as it was.

def _xlsx_open(f: DatasetFile):
    import openpyxl

    wb = openpyxl.load_workbook(f.path)
    ws = wb[wb.sheetnames[0]]
    hrow = f.header_row + 1                      # openpyxl is 1-indexed
    header = [c.value for c in ws[hrow]]
    return wb, ws, hrow, header


def _xlsx_ensure_source(f: DatasetFile) -> None:
    """Add `record_source` to the sheet and backfill it, once."""
    wb, ws, hrow, header = _xlsx_open(f)
    present = [str(h) for h in header if h is not None]
    if SOURCE_COL in present and REF_COL in present:
        return
    # `max_column + 1`, NOT `len(non-empty headers) + 1`. This sheet's used range
    # starts at column B, so counting names put the new header straight on top of
    # `Grade Range` — which silently turned grade_c0_factor("Jaduguda") from
    # (0.6, 0.03) into (1.0, None) with no error and no row-count change.
    filled = 0
    for name, default in ((SOURCE_COL, SOURCE_ORIGINAL), (REF_COL, "")):
        # Re-read: adding a cell above moves `max_column`, and the second
        # column must land after the first, not on top of it.
        header = [c.value for c in ws[hrow]]
        if name in [str(h) for h in header if h is not None]:
            continue
        col = ws.max_column + 1
        ws.cell(row=hrow, column=col, value=name)
        for r in range(hrow + 1, ws.max_row + 1):
            if any(ws.cell(row=r, column=c).value is not None
                   for c in range(1, col)):
                ws.cell(row=r, column=col, value=default)
                filled += 1
    wb.save(f.path)
    logger.info(f"{f.relpath}: added '{SOURCE_COL}', backfilled {filled} row(s) "
                f"as '{SOURCE_ORIGINAL}'")


def _xlsx_col_index(header: list, name: str) -> int:
    for i, h in enumerate(header, start=1):
        if h is not None and str(h).strip() == name:
            return i
    raise DatasetError(f"column {name!r} not found in sheet header")


def _xlsx_locate(ws, hrow: int, header: list, f: DatasetFile, row_id: str) -> int:
    """Excel row number for one natural-key value."""
    idc = _xlsx_col_index(header, f.id_column)
    hits = [r for r in range(hrow + 1, ws.max_row + 1)
            if str(ws.cell(row=r, column=idc).value or "").strip() == str(row_id).strip()]
    if not hits:
        raise DatasetError(
            f"no row with {f.id_column}={row_id!r} in {f.relpath}", status_code=404)
    if len(hits) > 1:
        raise DatasetError(
            f"{f.id_column}={row_id!r} matches {len(hits)} rows in {f.relpath}; "
            f"refusing to act on an ambiguous key")
    return hits[0]


def _xlsx_row_source(ws, excel_row: int, header: list) -> str:
    try:
        sc = _xlsx_col_index(header, SOURCE_COL)
    except DatasetError:
        return SOURCE_ORIGINAL
    return str(ws.cell(row=excel_row, column=sc).value or SOURCE_ORIGINAL)


def summary() -> list[dict[str, Any]]:
    """One row per writable dataset: counts, split, and what it governs."""
    out = []
    for key, f in REGISTRY.items():
        entry: dict[str, Any] = {
            "key": key, "label": f.label, "path": f.relpath,
            "kind": f.kind, "id_column": f.id_column, "governs": f.governs,
        }
        try:
            df = _read(f)
            counts = df[SOURCE_COL].value_counts().to_dict()
            entry.update({
                "rows": int(len(df)),
                "original": int(counts.get(SOURCE_ORIGINAL, 0)),
                "added": int(counts.get(SOURCE_ADDED, 0)),
                "modified_at": datetime.fromtimestamp(
                    f.path.stat().st_mtime, tz=timezone.utc).isoformat(),
                "available": True,
            })
        except Exception as exc:  # noqa: BLE001
            entry.update({"available": False, "error": str(exc)})
        out.append(entry)
    return out


def rows(key: str, *, source: Optional[str] = None, q: Optional[str] = None,
         offset: int = 0, limit: int = 100) -> dict[str, Any]:
    """Paged rows, newest-added first so a just-synced row is visible."""
    f = get(key)
    df = _read(f)
    df = df.reset_index(drop=True)

    if source in (SOURCE_ORIGINAL, SOURCE_ADDED):
        df = df[df[SOURCE_COL] == source]
    if q:
        needle = str(q).strip().lower()
        mask = df.apply(
            lambda r: needle in " ".join(str(v).lower() for v in r.values), axis=1)
        df = df[mask]

    # `added` rows first: they are the ones an admin came here to act on.
    df = df.assign(_added=(df[SOURCE_COL] == SOURCE_ADDED).astype(int))
    df = df.sort_values("_added", ascending=False, kind="stable").drop(columns="_added")

    total = int(len(df))
    page = df.iloc[offset:offset + limit]
    import pandas as pd
    recs = [
        {k: (None if pd.isna(v) else v) for k, v in rec.items()}
        for rec in page.to_dict(orient="records")
    ]
    return {
        "key": key, "label": f.label, "id_column": f.id_column,
        "columns": [c for c in df.columns],
        "total": total, "offset": offset, "limit": limit,
        "editable_note": (
            f"Rows marked '{SOURCE_ORIGINAL}' are the shipped evidence base and "
            f"cannot be edited or deleted. Only '{SOURCE_ADDED}' rows — written by "
            f"this system from approved field observations — may be changed."),
        "rows": recs,
    }


# ── writing ──────────────────────────────────────────────────────────

def backup(path: Path, ref: str) -> Path:
    """Copy beside the original before rewriting.

    These are tracked data files. Any admin action that changes one should be
    trivially undoable without reaching for git, because the person undoing it
    may be doing so at speed.
    """
    bak = path.with_suffix(path.suffix + f".{ref}.bak")
    shutil.copy2(path, bak)
    return bak


def _locate(df, f: DatasetFile, row_id: str):
    """Find exactly one row by the file's natural key."""
    ids = df[f.id_column].astype(str).str.strip()
    match = df[ids == str(row_id).strip()]
    if match.empty:
        raise DatasetError(
            f"no row with {f.id_column}={row_id!r} in {f.relpath}", status_code=404)
    if len(match) > 1:
        raise DatasetError(
            f"{f.id_column}={row_id!r} matches {len(match)} rows in {f.relpath}; "
            f"refusing to act on an ambiguous key")
    return match.index[0], match.iloc[0]


def _raise_original(f: DatasetFile, row_id: str, verb: str) -> None:
    raise DatasetError(
        f"cannot {verb} {f.id_column}={row_id!r}: it is a '{SOURCE_ORIGINAL}' row. "
        f"The shipped evidence base (CGWB, UDEPO, GSI, NAQUIM) is immutable — only "
        f"rows this system added from approved field observations can be changed. To "
        f"correct source data, replace the file through /ingest, which records a "
        f"versioned, checksummed dataset.")


def _guard_original(row, f: DatasetFile, row_id: str, verb: str) -> None:
    if str(row.get(SOURCE_COL, SOURCE_ORIGINAL)) != SOURCE_ADDED:
        _raise_original(f, row_id, verb)


def _validate_patch(f: DatasetFile, columns, patch: dict[str, Any]) -> None:
    unknown = [k for k in patch if k not in columns]
    if unknown:
        raise DatasetError(f"unknown column(s) for {f.relpath}: {unknown}")
    if not patch:
        raise DatasetError("empty patch — nothing to change")
    if SOURCE_COL in patch:
        raise DatasetError(
            f"{SOURCE_COL} is provenance, not data — it cannot be edited. A row "
            f"cannot be relabelled as shipped evidence.")
    if f.id_column in patch:
        raise DatasetError(
            f"{f.id_column} is this file's row identity and cannot be edited; "
            f"delete the row and re-sync instead.")


def update_row(key: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Edit one `added` row. Returns before/after for the audit entry."""
    f = get(key)
    ref = uuid.uuid4().hex[:12]

    if f.kind == "xlsx":
        _xlsx_ensure_source(f)
        wb, ws, hrow, header = _xlsx_open(f)
        _validate_patch(f, [str(h) for h in header if h is not None], patch)
        r = _xlsx_locate(ws, hrow, header, f, row_id)
        if _xlsx_row_source(ws, r, header) != SOURCE_ADDED:
            _raise_original(f, row_id, "edit")
        bak = backup(f.path, ref)
        before, after = {}, {}
        for col, val in patch.items():
            c = _xlsx_col_index(header, col)
            before[col] = ws.cell(row=r, column=c).value
            ws.cell(row=r, column=c, value=val)
            after[col] = val
        wb.save(f.path)
    else:
        df = _read(f)
        _validate_patch(f, df.columns, patch)
        idx, row = _locate(df, f, row_id)
        _guard_original(row, f, row_id, "edit")
        before = {k: (None if _isna(row[k]) else row[k]) for k in patch}
        for k, v in patch.items():
            df.at[idx, k] = v
        after = {k: (None if _isna(df.at[idx, k]) else df.at[idx, k]) for k in patch}
        bak = backup(f.path, ref)
        _write_csv(f, df)

    invalidate_caches()
    logger.info(f"{f.relpath}: edited {f.id_column}={row_id} ({len(patch)} field(s))")
    return {"ref": ref, "backup": str(bak.relative_to(REPO_ROOT)),
            "before": _jsonable(before), "after": _jsonable(after),
            "stale_marks": list(f.stale_marks)}


def delete_row(key: str, row_id: str) -> dict[str, Any]:
    """Remove one `added` row. Returns the removed row for the audit entry."""
    f = get(key)
    ref = uuid.uuid4().hex[:12]

    if f.kind == "xlsx":
        _xlsx_ensure_source(f)
        wb, ws, hrow, header = _xlsx_open(f)
        r = _xlsx_locate(ws, hrow, header, f, row_id)
        if _xlsx_row_source(ws, r, header) != SOURCE_ADDED:
            _raise_original(f, row_id, "delete")
        removed = {str(h): ws.cell(row=r, column=i).value
                   for i, h in enumerate(header, start=1) if h is not None}
        bak = backup(f.path, ref)
        ws.delete_rows(r)
        wb.save(f.path)
    else:
        df = _read(f)
        idx, row = _locate(df, f, row_id)
        _guard_original(row, f, row_id, "delete")
        removed = {k: (None if _isna(v) else v) for k, v in row.items()}
        bak = backup(f.path, ref)
        _write_csv(f, df.drop(index=idx))

    invalidate_caches()
    logger.info(f"{f.relpath}: deleted {f.id_column}={row_id}")
    return {"ref": ref, "backup": str(bak.relative_to(REPO_ROOT)),
            "removed": _jsonable(removed),
            "record_ref": (str(removed.get(REF_COL) or "").strip() or None),
            "stale_marks": list(f.stale_marks)}


def strip_added(key: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove every `added` row — the per-file primitive behind the reset."""
    f = get(key)
    df = _read(f)
    added = df[df[SOURCE_COL] == SOURCE_ADDED]
    result: dict[str, Any] = {
        "key": key, "path": f.relpath, "would_remove": int(len(added)),
        "ids": [str(v) for v in added[f.id_column].tolist()],
        "record_refs": sorted({str(v).strip() for v in added[REF_COL].tolist()
                               if str(v).strip()}),
    }
    if dry_run or added.empty:
        return result

    ref = uuid.uuid4().hex[:12]
    result["backup"] = str(backup(f.path, ref).relative_to(REPO_ROOT))
    if f.kind == "xlsx":
        wb, ws, hrow, header = _xlsx_open(f)
        # Bottom-up: deleting a row shifts every row beneath it.
        for r in sorted(
            (rr for rr in range(hrow + 1, ws.max_row + 1)
             if _xlsx_row_source(ws, rr, header) == SOURCE_ADDED), reverse=True):
            ws.delete_rows(r)
        wb.save(f.path)
    else:
        _write_csv(f, df[df[SOURCE_COL] != SOURCE_ADDED])
    invalidate_caches()
    result["removed"] = int(len(added))
    logger.info(f"{f.relpath}: stripped {len(added)} added row(s)")
    return result


def list_backups(key: str) -> list[dict[str, Any]]:
    f = get(key)
    out = []
    for b in sorted(f.path.parent.glob(f"{f.path.name}.*.bak"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        out.append({
            "name": b.name,
            "ref": b.name.rsplit(".", 2)[-2],
            "size_bytes": b.stat().st_size,
            "created_at": datetime.fromtimestamp(
                b.stat().st_mtime, tz=timezone.utc).isoformat(),
        })
    return out


def restore(key: str, backup_name: str) -> dict[str, Any]:
    """Put a backup back. The current file is itself backed up first."""
    f = get(key)
    src = f.path.parent / backup_name
    # Contain the path: `backup_name` arrives from the client.
    if src.parent.resolve() != f.path.parent.resolve() or not src.name.endswith(".bak"):
        raise DatasetError(f"not a backup of {f.relpath}: {backup_name!r}")
    if not src.exists():
        raise DatasetError(f"no such backup: {backup_name}", status_code=404)

    ref = uuid.uuid4().hex[:12]
    pre = backup(f.path, ref)
    shutil.copy2(src, f.path)
    invalidate_caches()
    logger.info(f"{f.relpath}: restored from {backup_name}")
    return {"restored_from": backup_name, "ref": ref,
            "backup_of_previous": str(pre.relative_to(REPO_ROOT)),
            "stale_marks": list(f.stale_marks)}


# ── helpers ──────────────────────────────────────────────────────────

def _isna(v) -> bool:
    import pandas as pd
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _jsonable(d: dict[str, Any]) -> dict[str, Any]:
    """numpy scalars are not JSON-serialisable and land in audit detail."""
    out = {}
    for k, v in d.items():
        if hasattr(v, "item"):
            try:
                v = v.item()
            except (AttributeError, ValueError):
                v = str(v)
        out[str(k)] = v
    return out


def invalidate_caches() -> None:
    """Drop the pipeline's memoised dataset reads.

    `ore_loader`, `ore_grades` and `jharkhand_loader` memoise their parsed files
    with `functools.lru_cache`, so without this a running process keeps serving
    pre-edit data until it restarts — and the edit would look like it had done
    nothing.
    """
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    cleared = []
    for mod_name in ("ml_pipeline.data_prep.ore_loader",
                     "ml_pipeline.data_prep.ore_grades",
                     "ml_pipeline.data_prep.jharkhand_loader"):
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
