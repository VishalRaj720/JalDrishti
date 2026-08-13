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


def _collection(rows) -> dict[str, Any]:
    """Rows carrying a `gj` GeoJSON-geometry string -> a FeatureCollection.

    The geometry is serialised by PostGIS rather than round-tripped through
    shapely: these are whole-state polygon sets, and simplifying and encoding
    them in the database is both faster and one fewer place for the coordinate
    order to get transposed.
    """
    import json
    return {
        "type": "FeatureCollection",
        "safe_limit": URANIUM_LIMIT_PPB,
        "what_this_is": _DISCLAIMER,
        "features": [{
            "type": "Feature",
            "geometry": json.loads(r["gj"]),
            "properties": {k: v for k, v in r.items() if k != "gj"},
        } for r in rows],
    }


def _explain(band: str, n: int) -> str:
    # This text is read by the public, so it says "the 1 well" rather than
    # "the 1 wells" — many blocks have a single sampled well.
    wells = "well" if n == 1 else "wells"
    if band == "No data":
        return ("No groundwater samples have been collected here yet, so there "
                "is nothing to report. That is a gap in monitoring, not a "
                "clean result.")
    if band == "High concern":
        one_of = "The" if n == 1 else "At least one of the"
        return (f"{one_of} {n} {wells} sampled here measured uranium "
                f"at or above the {URANIUM_LIMIT_PPB:g} ppb safe limit for "
                f"drinking water. Contact your block water office about testing.")
    if band == "Moderate concern":
        return (f"Uranium was found in the {n} {wells} sampled here at more than "
                f"half the {URANIUM_LIMIT_PPB:g} ppb safe limit, but below it. "
                f"Worth watching; not currently over the limit.")
    return (f"Uranium in the {n} {wells} sampled here was well below the "
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


# ── map geometry for the citizen surface ─────────────────────────────
# Declared BEFORE `/{district_id}`: that route's path parameter is a UUID, so
# "geojson" would not bind to it, but FastAPI matches in declaration order and
# putting these after would turn a typo into a confusing 422 rather than a 404.
#
# WHY THESE EXIST AND WHAT THEY STILL WITHHOLD. Design §2 forbids the public a
# precise coordinate for a *hypothetical ISR site*. It does not forbid the
# public a map of their own district: administrative boundaries and CGWB
# monitoring locations are published government reference data, and a citizen
# being told "moderate concern" without being shown where deserves better. So
# these serve boundaries, well positions and measured aggregates — and still no
# ISR site, no ore polygon, no plume, no model output of any kind.

@router.get("/geojson/districts")
async def district_geojson(response: Response, db: AsyncSession = Depends(get_db)):
    """District polygons carrying the same bands as `/districts`."""
    rows = (await db.execute(text(f"""
        WITH per_district AS (
            SELECT d.id, d.name, d.geometry,
                   count(DISTINCT w.id) AS wells,
                   count(s.id)          AS samples,
                   max(s.uranium_ppb)   AS max_u
            FROM districts d
            LEFT JOIN blocks b            ON b.district_id = d.id
            LEFT JOIN monitoring_wells w  ON w.block_id = b.id
            LEFT JOIN water_samples s     ON s.well_id = w.id
            WHERE d.geometry IS NOT NULL
            GROUP BY d.id, d.name, d.geometry
        )
        SELECT id::text, name, wells, samples,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.002)) AS gj
        FROM per_district ORDER BY name
    """), {"limit": URANIUM_LIMIT_PPB})).mappings().all()

    response.headers["Cache-Control"] = _CACHE
    return _collection(rows)


@router.get("/geojson/blocks")
async def block_geojson(response: Response, db: AsyncSession = Depends(get_db),
                        district_id: Optional[uuid.UUID] = None):
    """Block polygons, banded. The finest granularity the public surface offers."""
    rows = (await db.execute(text(f"""
        WITH per_block AS (
            SELECT b.id, b.name, b.geometry, d.name AS district,
                   count(DISTINCT w.id) AS wells,
                   count(s.id)          AS samples,
                   max(s.uranium_ppb)   AS max_u
            FROM blocks b
            JOIN districts d              ON d.id = b.district_id
            LEFT JOIN monitoring_wells w  ON w.block_id = b.id
            LEFT JOIN water_samples s     ON s.well_id = w.id
            -- CAST(:d AS uuid), not `:d::uuid`: SQLAlchemy's text() bind
            -- parser reads the `::` as part of the parameter name and emits
            -- the colon literally, which Postgres then rejects.
            WHERE b.geometry IS NOT NULL
              AND (CAST(:d AS uuid) IS NULL OR b.district_id = CAST(:d AS uuid))
            GROUP BY b.id, b.name, b.geometry, d.name
        )
        SELECT id::text, name, district, wells, samples,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.001)) AS gj
        FROM per_block ORDER BY district, name
    """), {"limit": URANIUM_LIMIT_PPB,
           "d": str(district_id) if district_id else None})).mappings().all()

    out = _collection(rows)
    for f in out["features"]:
        f["properties"]["what_it_means"] = _explain(
            f["properties"]["band"], f["properties"]["wells"])
    response.headers["Cache-Control"] = _CACHE
    return out


@router.get("/geojson/wells")
async def well_geojson(response: Response, db: AsyncSession = Depends(get_db)):
    """Monitoring-well positions with their measured result.

    Deliberately reduced: position, block, and what was found. No well id, no
    depth, no source reference — enough to answer "is anyone testing near me,
    and what did they find", not enough to be a pivotable copy of the network.
    """
    rows = (await db.execute(text(f"""
        WITH per_well AS (
            SELECT w.id, w.name, w.latitude, w.longitude, b.name AS block,
                   d.name AS district,
                   count(s.id)        AS samples,
                   max(s.uranium_ppb) AS max_u,
                   max(s.sampled_at)  AS last_sampled
            FROM monitoring_wells w
            LEFT JOIN blocks b         ON b.id = w.block_id
            LEFT JOIN districts d      ON d.id = b.district_id
            LEFT JOIN water_samples s  ON s.well_id = w.id
            GROUP BY w.id, w.name, w.latitude, w.longitude, b.name, d.name
        )
        SELECT name, latitude, longitude, block, district, samples, last_sampled,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band
        FROM per_well ORDER BY district, block
    """), {"limit": URANIUM_LIMIT_PPB})).mappings().all()

    response.headers["Cache-Control"] = _CACHE
    return {
        "type": "FeatureCollection",
        "safe_limit": URANIUM_LIMIT_PPB,
        "what_this_is": _DISCLAIMER,
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [float(r["longitude"]), float(r["latitude"])]},
            "properties": {k: v for k, v in r.items()
                           if k not in ("latitude", "longitude")},
        } for r in rows],
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
