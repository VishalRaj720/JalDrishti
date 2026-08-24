"""Groundwater level trends from the CGWB station record (2013-2021).

The statistics live in `services/groundwater_trends.py` and take no database, so
Theil-Sen and Mann-Kendall are testable against known series rather than only
against whatever happens to be seeded.

COST. 8,345 readings across 415 stations is small, but Theil-Sen is O(n^2) in a
station's reading count and one station here has 1,242 of them. The statewide
roll-up is therefore computed once and cached in-process for an hour; the cache
states its own age rather than pretending to be live.
"""
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_staff
from app.models.user import User
from app.services import groundwater_trends as gt

router = APIRouter(prefix="/groundwater", tags=["Groundwater levels"])

_TTL_SECONDS = 3600
_cache: dict[str, Any] = {"at": 0.0, "data": None}

_SERIES_SQL = """
    SELECT s.id::text  AS station_id,
           s.name      AS station,
           s.village, s.latitude, s.longitude,
           b.name      AS block,
           d.name      AS district,
           r.recorded_at,
           r.groundwater_level
    FROM monitoring_stations s
    JOIN groundwater_level_readings r ON r.station_id = s.id
    LEFT JOIN blocks b    ON s.block_id = b.id
    LEFT JOIN districts d ON b.district_id = d.id
    {where}
    ORDER BY s.id, r.recorded_at
"""


async def _stations(db: AsyncSession, where: str = "",
                    params: Optional[dict] = None) -> list[dict[str, Any]]:
    rows = (await db.execute(text(_SERIES_SQL.format(where=where)),
                             params or {})).mappings().all()
    grouped: dict[str, dict[str, Any]] = {}
    for r in rows:
        st = grouped.setdefault(r["station_id"], {
            "station_id": r["station_id"], "station": r["station"],
            "village": r["village"], "latitude": r["latitude"],
            "longitude": r["longitude"], "block": r["block"],
            "district": r["district"], "_readings": [],
        })
        st["_readings"].append((r["recorded_at"], r["groundwater_level"]))

    out = []
    for st in grouped.values():
        readings = st.pop("_readings")
        out.append({**st, **gt.analyse_station(readings)})
    return out


def _summarise(stations: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts, and the honest denominator beside them.

    `analysed` is reported next to `stations` because "37 declining" means
    something different out of 341 than out of 415, and the difference is
    exactly the stations that lack enough record to say.
    """
    analysed = [s for s in stations if s["trend"]]
    by_trend: dict[str, int] = {}
    for s in analysed:
        by_trend[s["trend"]] = by_trend.get(s["trend"], 0) + 1
    declining = [s for s in analysed if s["trend"] == "declining"]
    swings = [s["seasonal"]["swing_m"] for s in stations
              if s.get("seasonal") and s["seasonal"]["swing_m"] is not None]
    return {
        "stations": len(stations),
        "analysed": len(analysed),
        "insufficient_data": len(stations) - len(analysed),
        "by_trend": by_trend,
        "declining": len(declining),
        "fastest_decline_m_per_year": (
            round(max((s["slope_m_per_year"] for s in declining), default=0.0), 3)
            if declining else None),
        "median_seasonal_swing_m": (
            None if not swings else round(sorted(swings)[len(swings) // 2], 2)),
        "coverage_note": (
            f"{len(analysed)} of {len(stations)} stations carry enough record "
            f"to test for a trend. The rest are not 'stable' - they are "
            f"unmeasured, and are counted separately."),
    }


@router.get("/method")
async def method(_: User = Depends(require_staff)) -> dict[str, Any]:
    """How the trend is computed, published beside the numbers."""
    return gt.method_note()


@router.get("/trends")
async def trends(
    district: Optional[str] = Query(None, description="district name filter"),
    trend: Optional[str] = Query(
        None, description="declining | recovering | stable"),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Every station's trend, worst decline first.

    Cached for an hour and honest about it: `computed_seconds_ago` is returned
    so a caller can tell a fresh answer from a warm one.
    """
    now = time.time()
    if _cache["data"] is None or now - _cache["at"] > _TTL_SECONDS:
        _cache["data"] = await _stations(db)
        _cache["at"] = now
    items = _cache["data"]

    if district:
        items = [s for s in items
                 if (s["district"] or "").lower() == district.lower()]
    if trend:
        items = [s for s in items if s["trend"] == trend]

    # Declining first, steepest at the top; then everything else. Stations with
    # no trend sort last rather than being dropped -- they are the monitoring
    # gap, and this ranking is the one place it is visible.
    items = sorted(
        items,
        key=lambda s: (s["trend"] != "declining",
                       -(s["slope_m_per_year"] or 0.0),
                       s["station"] or ""))

    return {
        "count": len(items),
        "stations": items[:limit],
        "summary": _summarise(_cache["data"]),
        "method": gt.method_note(),
        "computed_seconds_ago": int(now - _cache["at"]),
    }


@router.get("/stations/{station_id}")
async def station_series(
    station_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """One station: its trend, and every reading behind it.

    The series is returned so the chart draws the measurements rather than the
    fitted line alone -- a trend line with no points under it cannot be
    challenged by the person reading it.
    """
    rows = (await db.execute(text(_SERIES_SQL.format(where="WHERE s.id = :s")),
                             {"s": station_id})).mappings().all()
    if not rows:
        raise HTTPException(404, "No readings recorded for that station.")

    readings = [(r["recorded_at"], r["groundwater_level"]) for r in rows]
    head = rows[0]
    return {
        "station_id": head["station_id"], "station": head["station"],
        "village": head["village"], "latitude": head["latitude"],
        "longitude": head["longitude"], "block": head["block"],
        "district": head["district"],
        **gt.analyse_station(readings),
        "series": [{"at": r["recorded_at"], "depth_m": r["groundwater_level"]}
                   for r in rows],
        "method": gt.method_note(),
    }


@router.get("/districts")
async def district_rollup(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
) -> dict[str, Any]:
    """Districts ranked by how many of their stations are declining."""
    now = time.time()
    if _cache["data"] is None or now - _cache["at"] > _TTL_SECONDS:
        _cache["data"] = await _stations(db)
        _cache["at"] = now

    by: dict[str, list] = {}
    for s in _cache["data"]:
        by.setdefault(s["district"] or "Unassigned", []).append(s)

    out = [{"district": k, **_summarise(v)} for k, v in by.items()]
    out.sort(key=lambda d: (-d["declining"], -d["analysed"], d["district"]))
    return {"districts": out, "statewide": _summarise(_cache["data"]),
            "method": gt.method_note()}
