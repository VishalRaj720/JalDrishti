"""The citizen-facing aggregate surface.

PRODUCT_DESIGN.md §3.3 (`GET /public/risk/{district_id}`) and §4.4 (C1/C2).
This is the fix for D-3 in `docs/roles.md`: `citizen` could previously reach
exactly one endpoint, so the product's second named audience had no API at all.

WHAT THIS DELIBERATELY DOES NOT EXPOSE. Design §2 forbids non-staff a precise
ISR site coordinate: every site here is *hypothetical*, and publishing a point
for a speculative uranium mine beside a named village invites it being read as a
real plan. So this module serves **only** district- and block-level aggregates
of measured groundwater quality. No site points, no well coordinates, no
simulation output, no plume geometry.

It also reports **measurements, not predictions**. Nothing here comes from the
surrogate or the excursion indicators; it is what CGWB sampling actually found.
That keeps the hypothetical-mine framing and the real-water-quality framing from
blurring on the surface a member of the public sees.

Unauthenticated by design (§3.3), and therefore written to be boring: fixed
aggregate shapes, no free-text filters, no identifiers a caller could pivot on.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(prefix="/public/risk", tags=["Public (citizen)"])

# BIS/WHO drinking-water limit for uranium, the same threshold the rest of the
# platform uses. Bands are plain language on purpose (design §4.4): a citizen
# screen shows "Moderate concern", never a P10-P90 band.
URANIUM_LIMIT_PPB = 30.0

_BANDS = """
    CASE
        WHEN max_u IS NULL              THEN 'No data'
        WHEN max_u >= :limit            THEN 'High concern'
        WHEN max_u >= :limit * 0.5      THEN 'Moderate concern'
        ELSE                                 'Low concern'
    END
"""

_CACHE = "public, max-age=3600"


def _explain(band: str, n: int) -> str:
    if band == "No data":
        return ("No groundwater samples have been collected here yet, so there "
                "is nothing to report. That is a gap in monitoring, not a "
                "clean result.")
    if band == "High concern":
        return (f"At least one of the {n} wells sampled here measured uranium "
                f"at or above the {URANIUM_LIMIT_PPB:g} ppb safe limit for "
                f"drinking water. Contact your block water office about testing.")
    if band == "Moderate concern":
        return (f"Uranium was found in the {n} wells sampled here at more than "
                f"half the {URANIUM_LIMIT_PPB:g} ppb safe limit, but below it. "
                f"Worth watching; not currently over the limit.")
    return (f"Uranium in the {n} wells sampled here was well below the "
            f"{URANIUM_LIMIT_PPB:g} ppb safe limit.")


_DISCLAIMER = (
    "No uranium mine of the type this platform models operates in Jharkhand. "
    "The numbers here are real measurements from government groundwater "
    "sampling, not predictions from any simulation."
)


@router.get("/districts")
async def district_risk(response: Response, db: AsyncSession = Depends(get_db)):
    """Every district, banded. The C1 public map reads this."""
    rows = (await db.execute(text(f"""
        WITH per_district AS (
            SELECT d.id, d.name,
                   count(DISTINCT w.id)  AS wells,
                   count(s.id)           AS samples,
                   max(s.uranium_ppb)    AS max_u
            FROM districts d
            LEFT JOIN blocks b            ON b.district_id = d.id
            LEFT JOIN monitoring_wells w  ON w.block_id = b.id
            LEFT JOIN water_samples s     ON s.well_id = w.id
            GROUP BY d.id, d.name
        )
        SELECT id::text, name, wells, samples,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band
        FROM per_district ORDER BY name
    """), {"limit": URANIUM_LIMIT_PPB})).mappings().all()

    response.headers["Cache-Control"] = _CACHE
    return {
        "unit": "ppb", "safe_limit": URANIUM_LIMIT_PPB,
        "districts": [dict(r) for r in rows],
        "what_this_is": _DISCLAIMER,
    }


@router.get("/{district_id}")
async def district_detail(district_id: uuid.UUID, response: Response,
                          db: AsyncSession = Depends(get_db)):
    """One district, broken down by block. The C2 "My Area" screen reads this."""
    district = (await db.execute(
        text("SELECT id::text, name FROM districts WHERE id = :i"),
        {"i": str(district_id)})).mappings().first()
    if district is None:
        raise HTTPException(status_code=404, detail="District not found.")

    rows = (await db.execute(text(f"""
        WITH per_block AS (
            SELECT b.id, b.name,
                   count(DISTINCT w.id) AS wells,
                   count(s.id)          AS samples,
                   max(s.uranium_ppb)   AS max_u,
                   max(s.sampled_at)    AS last_sampled
            FROM blocks b
            LEFT JOIN monitoring_wells w ON w.block_id = b.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            WHERE b.district_id = :d
            GROUP BY b.id, b.name
        )
        SELECT id::text, name, wells, samples, last_sampled,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band
        FROM per_block ORDER BY name
    """), {"d": str(district_id), "limit": URANIUM_LIMIT_PPB})).mappings().all()

    blocks: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["what_it_means"] = _explain(d["band"], d["wells"])
        blocks.append(d)

    response.headers["Cache-Control"] = _CACHE
    return {
        "district": dict(district),
        "unit": "ppb", "safe_limit": URANIUM_LIMIT_PPB,
        "blocks": blocks,
        "what_this_is": _DISCLAIMER,
        "data_gap": sum(1 for b in blocks if b["band"] == "No data"),
    }
