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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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


@router.get("/at")
async def risk_at_point(
    response: Response,
    lon: float = Query(..., ge=-180, le=180),
    lat: float = Query(..., ge=-90, le=90),
    db: AsyncSession = Depends(get_db),
):
    """What is known about groundwater at one point. Public, unauthenticated.

    The citizen equivalent of the staff console's pin. It answers "what do you
    know about *here*" from **measurements only** — the containing block and
    district, what sampling found, and the nearest wells. It runs no model and
    returns no ISR geometry: a resident tapping a map must not be able to
    discover where a hypothetical site was placed, and must never be shown a
    prediction dressed as an observation.

    Tapping open ground previously did nothing at all, which made the map look
    broken everywhere outside a polygon a finger happened to land on.
    """
    row = (await db.execute(text(f"""
        WITH hit AS (
            SELECT b.id, b.name, d.name AS district
            FROM blocks b
            JOIN districts d ON d.id = b.district_id
            WHERE b.geometry IS NOT NULL
              AND ST_Contains(b.geometry,
                              ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            LIMIT 1
        )
        SELECT h.id::text, h.name, h.district,
               count(DISTINCT w.id) AS wells,
               count(s.id)          AS samples,
               count(s.uranium_ppb) AS uranium_tests,
               round(max(s.uranium_ppb)::numeric, 1) AS max_uranium_ppb,
               {_BANDS.replace('max_u', 'max(s.uranium_ppb)')} AS band
        FROM hit h
        LEFT JOIN monitoring_wells w ON w.block_id = h.id
        LEFT JOIN water_samples s    ON s.well_id = w.id
        GROUP BY h.id, h.name, h.district
    """), {"lon": lon, "lat": lat, "limit": URANIUM_LIMIT_PPB})).mappings().first()

    response.headers["Cache-Control"] = _CACHE

    if row is None:
        return {
            "inside_jharkhand": False,
            "what_this_is": _DISCLAIMER,
            "message": ("That point is outside the blocks this platform covers. "
                        "Tap somewhere inside Jharkhand."),
        }

    d = dict(row)
    wells, samples = int(d["wells"] or 0), int(d["samples"] or 0)
    tested = int(d["uranium_tests"] or 0)

    # The distinction R10 fixed on the citizen surface and this endpoint must
    # not reintroduce: a block whose wells were sampled but never analysed for
    # uranium is a monitoring gap, not a clean result. `band` alone cannot say
    # which, because both arrive as NULL.
    if samples and not tested:
        explanation = (
            f"The {wells} well{'' if wells == 1 else 's'} here have been sampled, "
            f"but none of those samples were analysed for uranium. There is no "
            f"uranium result to report — that is a gap in testing, not a clean "
            f"result.")
        d["band"] = "Not tested for uranium"
    else:
        explanation = _explain(d["band"], wells)

    nearest = (await db.execute(text("""
        SELECT w.name, b.name AS block,
               round(ST_DistanceSphere(
                   w.location::geometry,
                   ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))::numeric) AS metres,
               round(max(s.uranium_ppb)::numeric, 1) AS max_uranium_ppb,
               count(s.uranium_ppb) AS uranium_tests
        FROM monitoring_wells w
        LEFT JOIN blocks b        ON b.id = w.block_id
        LEFT JOIN water_samples s ON s.well_id = w.id
        WHERE w.location IS NOT NULL
        GROUP BY w.id, w.name, b.name, w.location
        ORDER BY ST_DistanceSphere(
            w.location::geometry, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
        LIMIT 3
    """), {"lon": lon, "lat": lat})).mappings().all()

    advisories = (await db.execute(text("""
        SELECT a.headline, a.species, a.footprint_ha, a.published_at
        FROM advisories a
        WHERE a.status = 'published'
          AND a.footprint IS NOT NULL
          AND ST_Contains(a.footprint,
                          ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
        ORDER BY a.published_at DESC
        LIMIT 5
    """), {"lon": lon, "lat": lat})).mappings().all()

    return {
        "inside_jharkhand": True,
        "point": {"lon": lon, "lat": lat},
        "block": d["name"], "district": d["district"],
        "wells": wells, "samples": samples, "uranium_tests": tested,
        "max_uranium_ppb": d["max_uranium_ppb"],
        "band": d["band"],
        "safe_limit": URANIUM_LIMIT_PPB,
        "what_it_means": explanation,
        "nearest_wells": [dict(w) for w in nearest],
        "advisories": [dict(a) for a in advisories],
        "what_this_is": _DISCLAIMER,
    }


@router.get("/blocks/summary")
async def block_summary(response: Response, db: AsyncSession = Depends(get_db)):
    """How many blocks are safe, unsafe, and unknown — statewide.

    THE COUNT THAT MATTERS IS THE THIRD ONE. Two numbers ("safe" / "unsafe")
    invite the reader to divide one by the other and conclude the state is mostly
    fine. The honest denominator includes every block nobody has measured, and
    those are not evidence of safety — they are the absence of evidence, which is
    why they are reported as their own category and never folded into "safe".

    A block is:
      unsafe    at least one sample at or above the BIS/WHO limit
      watch     highest result over half the limit but under it
      safe      sampled, analysed for uranium, and all results well under
      untested  wells sampled, but no sample ever analysed for uranium
      no data   no groundwater sample at all

    `untested` is split out from `no data` because they are different failures
    with different fixes: one needs a lab determination on a sample that already
    exists, the other needs a well.
    """
    row = (await db.execute(text("""
        WITH per_block AS (
            SELECT b.id,
                   count(s.id)          AS samples,
                   count(s.uranium_ppb) AS u_tests,
                   max(s.uranium_ppb)   AS max_u
            FROM blocks b
            LEFT JOIN monitoring_wells w ON w.block_id = b.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            GROUP BY b.id
        )
        SELECT count(*)                                                AS total,
               count(*) FILTER (WHERE u_tests > 0 AND max_u >= :limit)  AS unsafe,
               count(*) FILTER (WHERE u_tests > 0
                                  AND max_u >= :limit * 0.5
                                  AND max_u <  :limit)                  AS watch,
               count(*) FILTER (WHERE u_tests > 0 AND max_u < :limit * 0.5) AS safe,
               count(*) FILTER (WHERE samples > 0 AND u_tests = 0)       AS untested,
               count(*) FILTER (WHERE samples = 0)                       AS no_data
        FROM per_block
    """), {"limit": URANIUM_LIMIT_PPB})).mappings().one()

    d = {k: int(v or 0) for k, v in row.items()}
    measured = d["unsafe"] + d["watch"] + d["safe"]
    unknown = d["untested"] + d["no_data"]

    response.headers["Cache-Control"] = _CACHE
    return {
        **d,
        "measured": measured,
        "unknown": unknown,
        "safe_limit_ppb": URANIUM_LIMIT_PPB,
        "coverage_pct": round(100.0 * measured / d["total"], 1) if d["total"] else 0.0,
        "headline": (
            f"{measured} of {d['total']} blocks have a uranium result. "
            f"{unknown} do not."),
        "what_unknown_means": (
            "A block with no uranium result is not a safe block. It is a place "
            "nobody has measured, and it is counted separately here so it cannot "
            "be mistaken for a clean one."),
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
