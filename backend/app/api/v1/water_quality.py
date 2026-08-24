"""Multi-parameter drinking-water assessment, per well / block / district.

The scoring itself lives in `services/water_quality.py` and touches no database,
so the standard can be tested without one. This module is the SQL and the
guards.

AGGREGATION IN PYTHON, DELIBERATELY. There are 397 samples in the whole state,
so the entire working set fits in one query and one pass. Expressing IS
10500:2012 as a CASE ladder in SQL would put the limits in two places — the
registry and the query — and the second copy is the one that goes stale.

ROLE BOUNDARY. The detail routes are `require_staff` because they return well
coordinates and names. The public `at` route mirrors the existing
`GET /public/risk/at`: block-level only, no well identity, unauthenticated, and
carrying the same disclaimer.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_authenticated, require_staff
from app.models.user import User
from app.services import water_quality as wq

router = APIRouter(prefix="/water-quality", tags=["Water quality"])

_CACHE = "public, max-age=3600"

_DISCLAIMER = (
    "Real laboratory measurements from government (CGWB) groundwater sampling, "
    "judged against IS 10500:2012. These are observations, not predictions from "
    "any simulation, and they are unrelated to the hypothetical ISR scenarios "
    "this platform models elsewhere."
)

#: One sample per well is what this dataset holds — 397 wells, one round, one
#: year, zero repeats (LIMITATIONS.md §3). `DISTINCT ON` picks the newest per
#: well so the query stays correct if repeat sampling is ever ingested.
_SAMPLE_SQL = """
    SELECT DISTINCT ON (w.id)
           w.id::text        AS well_id,
           w.name            AS well_name,
           w.latitude, w.longitude,
           b.id::text        AS block_id,
           b.name            AS block_name,
           d.id::text        AS district_id,
           d.name            AS district_name,
           s.sampled_at,
           {cols}
    FROM monitoring_wells w
    JOIN water_samples s ON s.well_id = w.id
    LEFT JOIN blocks b    ON w.block_id = b.id
    LEFT JOIN districts d ON b.district_id = d.id
    {where}
    ORDER BY w.id, s.sampled_at DESC
"""


def _columns() -> str:
    return ", ".join(f"s.{c}" for c in wq.SAMPLE_COLUMNS)


async def _load(db: AsyncSession, where: str = "", params: Optional[dict] = None
                ) -> list[dict[str, Any]]:
    sql = _SAMPLE_SQL.format(cols=_columns(), where=where)
    rows = (await db.execute(text(sql), params or {})).mappings().all()
    out = []
    for r in rows:
        row = dict(r)
        assessed = wq.assess_sample(row)
        out.append({
            "well_id": row["well_id"], "well_name": row["well_name"],
            "latitude": row["latitude"], "longitude": row["longitude"],
            "block_id": row["block_id"], "block": row["block_name"],
            "district_id": row["district_id"], "district": row["district_name"],
            "sampled_at": row["sampled_at"],
            "wqi": wq.wqi(row),
            **assessed,
        })
    return out


def _rollup(wells: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts, never an average of statuses.

    Averaging a status is how "half the wells are unusable" becomes "moderate".
    The rollup reports how many wells fall in each class and which determinand
    fails most often, and leaves the judgement to the reader.
    """
    n = len(wells)
    above_perm = sum(1 for w in wells
                     if w["summary"]["status"] == wq.STATUS_ABOVE_PERMISSIBLE)
    above_acc = sum(1 for w in wells
                    if w["summary"]["status"] == wq.STATUS_ABOVE_ACCEPTABLE)
    clean = sum(1 for w in wells
                if w["summary"]["status"] == wq.STATUS_ACCEPTABLE)
    untested = sum(1 for w in wells
                   if w["summary"]["status"] == wq.STATUS_NOT_TESTED)

    freq: dict[str, int] = {}
    for w in wells:
        for k in w["summary"]["exceeded"]:
            freq[k] = freq.get(k, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: -kv[1])

    # THE SPLIT THAT KEEPS THIS HONEST.
    #
    # 71 % of Jharkhand's sampled wells exceed some IS 10500 limit, and read
    # without this split that becomes "71 % of the state's water is polluted".
    # It is not. The bulk of those exceedances are hardness, alkalinity, TDS,
    # calcium and magnesium -- the signature of hard-rock aquifer geology, which
    # affects taste, scaling and acceptability rather than health, and which no
    # mine caused.
    #
    # The health-significant set (uranium, fluoride, nitrate, arsenic, iron) is
    # much smaller and much more serious, and it is the number a health officer
    # should see first. Reporting only the combined figure would bury 22 wells
    # of real nitrate exceedance under 264 wells of hard water.
    health = [w for w in wells if w["summary"]["health_exceedances"] > 0]
    health_freq: dict[str, int] = {}
    for w in health:
        for k in w["summary"]["exceeded"]:
            if wq.BY_KEY[k].health:
                health_freq[k] = health_freq.get(k, 0) + 1

    scores = [w["wqi"]["score"] for w in wells if w["wqi"]]
    return {
        "wells": n,
        "health_exceedance_wells": len(health),
        "health_exceedances": [
            {"key": k, "label": wq.BY_KEY[k].label, "wells": c}
            for k, c in sorted(health_freq.items(), key=lambda kv: -kv[1])],
        "aesthetic_only_wells": sum(
            1 for w in wells
            if w["summary"]["exceedances"] and not w["summary"]["health_exceedances"]),
        "interpretation": (
            "Health-significant determinands (uranium, fluoride, nitrate, "
            "arsenic, iron) are counted separately from general and aesthetic "
            "ones (hardness, alkalinity, TDS, calcium, magnesium). Most "
            "exceedances in Jharkhand are the second kind - hard-rock aquifer "
            "chemistry, not contamination."),
        "above_permissible": above_perm,
        "above_acceptable": above_acc,
        "acceptable": clean,
        "not_tested": untested,
        "any_exceedance": above_perm + above_acc,
        "worst_status": wq.worst_status(w["summary"]["status"] for w in wells),
        "top_exceedances": [
            {"key": k, "label": wq.BY_KEY[k].label, "wells": c,
             "pct": round(100.0 * c / n, 1) if n else 0.0}
            for k, c in ranked[:5]],
        "median_wqi": (None if not scores
                       else round(sorted(scores)[len(scores) // 2], 1)),
        "wqi_wells": len(scores),
    }


@router.get("/standard")
async def get_standard(_: User = Depends(require_authenticated)) -> dict[str, Any]:
    """The limits themselves, as data.

    Readable by every signed-in role including `citizen`, on the same principle
    as `GET /ml/assumptions`: a threshold that decides what somebody is told
    about their own drinking water should be inspectable by them.
    """
    return wq.standard_document()


@router.get("/wells")
async def wells(
    response: Response,
    block_id: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    status: Optional[str] = Query(
        None, description="filter: above_permissible | above_acceptable | "
                          "acceptable | not_tested"),
    parameter: Optional[str] = Query(
        None, description="filter to wells exceeding this determinand"),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Every sampled well, fully assessed. Staff only — carries coordinates."""
    where, params = "", {}
    if block_id:
        where, params = "WHERE b.id = :b", {"b": block_id}
    elif district_id:
        where, params = "WHERE d.id = :d", {"d": district_id}

    items = await _load(db, where, params)
    if status:
        items = [w for w in items if w["summary"]["status"] == status]
    if parameter:
        if parameter not in wq.BY_KEY:
            raise HTTPException(404, f"Unknown determinand '{parameter}'.")
        items = [w for w in items if parameter in w["summary"]["exceeded"]]

    response.headers["Cache-Control"] = "no-store"
    return {
        "count": len(items),
        "wells": items[:limit],
        "rollup": _rollup(items),
        "what_this_is": _DISCLAIMER,
    }


@router.get("/districts")
async def districts(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Every district rolled up, worst first."""
    items = await _load(db)
    by: dict[str, list] = {}
    names: dict[str, str] = {}
    for w in items:
        if not w["district_id"]:
            continue
        by.setdefault(w["district_id"], []).append(w)
        names[w["district_id"]] = w["district"]

    out = [{"id": k, "name": names[k], **_rollup(v)} for k, v in by.items()]
    out.sort(key=lambda d: (-d["above_permissible"], -d["any_exceedance"],
                            d["name"]))
    return {
        "districts": out,
        "statewide": _rollup(items),
        "standard": wq.standard_document()["standard"],
        "what_this_is": _DISCLAIMER,
    }


@router.get("/blocks")
async def blocks(
    district_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Blocks rolled up, worst first. The unit a monitoring decision is made in."""
    where, params = ("WHERE d.id = :d", {"d": district_id}) if district_id else ("", {})
    items = await _load(db, where, params)
    by: dict[str, list] = {}
    meta: dict[str, tuple] = {}
    for w in items:
        if not w["block_id"]:
            continue
        by.setdefault(w["block_id"], []).append(w)
        meta[w["block_id"]] = (w["block"], w["district"])

    out = [{"id": k, "name": meta[k][0], "district": meta[k][1], **_rollup(v)}
           for k, v in by.items()]
    out.sort(key=lambda b: (-b["above_permissible"], -b["any_exceedance"],
                            b["name"]))
    return {"blocks": out, "what_this_is": _DISCLAIMER}


@router.get("/well/{well_id}")
async def one_well(
    well_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """One well, every determinand, with the limit beside each value."""
    items = await _load(db, "WHERE w.id = :w", {"w": well_id})
    if not items:
        raise HTTPException(404, "No sample recorded for that well.")
    return {**items[0], "what_this_is": _DISCLAIMER}
