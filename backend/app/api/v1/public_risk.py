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

# ── Health limits, IS 10500:2012 ─────────────────────────────────────
#
# Kept in step with `services/water_quality.py`, which owns the full
# eighteen-determinand registry. Only the HEALTH-significant ones band a block:
# hardness, alkalinity and TDS exceed at two-thirds of Jharkhand's wells and are
# hard-rock aquifer chemistry, not contamination. Banding a village "High
# concern" for hard water would bury the wells that carry a real nitrate load.
NITRATE_LIMIT_MG_L = 45.0     # "No relaxation" — any exceedance is the worst class
FLUORIDE_ACCEPTABLE_MG_L = 1.0
FLUORIDE_PERMISSIBLE_MG_L = 1.5

#: Arsenic and iron are health determinands with NO data in the CGWB file
#: (0 of 397 samples). They are deliberately absent from the band expression
#: rather than defaulted to a pass — a block whose arsenic was never measured
#: must not be banded on the assumption that it is clean. `health_tests` counts
#: only what was actually analysed, and a block with none reads "Not tested".

#: Columns every banding query must compute. Kept as one string so the six
#: queries that band cannot drift apart.
_HEALTH_MAXES = """
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
"""

# THE BAND, ACROSS EVERY MEASURED HEALTH DETERMINAND.
#
# Until 2026-08-25 this read `max_u` alone, and that was actively misleading:
# uranium exceeds its limit at ZERO of 342 tested wells in Jharkhand, while
# nitrate exceeds at 22 (peak 121 mg/L, 2.7x the limit) and fluoride at 32. The
# public map therefore told residents of those blocks "Low concern" on the
# strength of the one determinand that never fires.
#
# `Not tested` is a distinct band from `No data` and from `Low concern`: a block
# with wells and samples but no health determinand analysed has not been shown
# to be safe. Neither may ever render green.
_BANDS = """
    CASE
        WHEN health_tests = 0 AND max_u IS NULL THEN 'No data'
        WHEN health_tests = 0                   THEN 'Not tested'
        WHEN max_u   >= :limit                  THEN 'High concern'
        WHEN max_no3 >  :no3_limit              THEN 'High concern'
        WHEN max_f   >  :f_permissible          THEN 'High concern'
        WHEN max_f   >  :f_acceptable           THEN 'Moderate concern'
        WHEN max_u   >= :limit * 0.5            THEN 'Moderate concern'
        ELSE                                         'Low concern'
    END
"""

#: Which determinand set the band, so a citizen is told WHAT is wrong rather
#: than only that something is. Mirrors the CASE above, in the same order.
_DRIVER = """
    CASE
        WHEN health_tests = 0                   THEN NULL
        WHEN max_u   >= :limit                  THEN 'uranium'
        WHEN max_no3 >  :no3_limit              THEN 'nitrate'
        WHEN max_f   >  :f_permissible          THEN 'fluoride'
        WHEN max_f   >  :f_acceptable           THEN 'fluoride'
        WHEN max_u   >= :limit * 0.5            THEN 'uranium'
        ELSE                                         NULL
    END
"""


#: Which health determinands were never analysed here.
#:
#: Arsenic and iron are 0 % populated statewide, so they are listed
#: unconditionally — no block in Jharkhand has been cleared for them, and a
#: "Low concern" band that silently means "clean for the three we happened to
#: measure" is the failure LIMITATIONS.md section 3 exists to prevent.
_UNTESTED = """
    array_remove(ARRAY[
        CASE WHEN n_u   = 0 THEN 'uranium'  END,
        CASE WHEN n_no3 = 0 THEN 'nitrate'  END,
        CASE WHEN n_f   = 0 THEN 'fluoride' END,
        'arsenic', 'iron'
    ], NULL)
"""


def _band_params() -> dict:
    """Every banding query binds the same four limits."""
    return {
        "limit": URANIUM_LIMIT_PPB,
        "no3_limit": NITRATE_LIMIT_MG_L,
        "f_acceptable": FLUORIDE_ACCEPTABLE_MG_L,
        "f_permissible": FLUORIDE_PERMISSIBLE_MG_L,
    }

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


def _join_and(items: list[str]) -> str:
    """'a', 'a and b', 'a, b and c' — this text is read by the public."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _explain_multi(d: dict, wells: int) -> str:
    """Plain-language reading of a multi-determinand band.

    Names the substance that set the band. "High concern" with no explanation
    of WHAT is high is not actionable — a resident can boil water for bacteria
    but cannot boil out fluoride, and the advice differs by determinand.
    """
    band, driver = d.get("band"), d.get("band_driver")
    w = "well" if wells == 1 else "wells"

    if band == "No data":
        return ("No groundwater samples have been collected here yet, so there "
                "is nothing to report. That is a gap in monitoring, not a clean "
                "result.")
    if band == "Not tested":
        return ("Samples were collected here but not analysed for any "
                "drinking-water health substance. That is a gap in testing, not "
                "a clean result.")

    detail = {
        "uranium": (f"uranium at {d.get('max_uranium_ppb')} ppb against a "
                    f"{URANIUM_LIMIT_PPB:g} ppb limit"),
        "nitrate": (f"nitrate at {d.get('max_nitrate_mg_l')} mg/L against a "
                    f"{NITRATE_LIMIT_MG_L:g} mg/L limit"),
        "fluoride": (f"fluoride at {d.get('max_fluoride_mg_l')} mg/L against a "
                     f"{FLUORIDE_ACCEPTABLE_MG_L:g} mg/L limit "
                     f"({FLUORIDE_PERMISSIBLE_MG_L:g} where no other source "
                     f"exists)"),
    }.get(driver or "", "")

    if band == "High concern":
        advice = {
            "nitrate": ("Nitrate is mainly a risk to infants under six months. "
                        "Do not use this water to make formula feed."),
            "fluoride": ("Long-term fluoride exposure causes dental and skeletal "
                         "fluorosis. Boiling does not remove it."),
            "uranium": "Boiling does not remove uranium.",
        }.get(driver or "", "")
        return (f"Testing of the {wells} {w} here found {detail}. {advice} "
                f"Contact your block water office about testing and about an "
                f"alternative supply.").strip()

    if band == "Moderate concern":
        return (f"Testing of the {wells} {w} here found {detail}. It is not over "
                f"the limit where no other source exists, but it is worth "
                f"watching and worth asking your block water office about.")

    # Name only what was ACTUALLY analysed. Saying "uranium, nitrate and
    # fluoride were all within limits" at a block where uranium was never
    # measured contradicts the gap sentence appended right after it, and the
    # reassuring half is the half a reader remembers.
    measured = [n for n, c in (("uranium", d.get("n_u")),
                               ("nitrate", d.get("n_no3")),
                               ("fluoride", d.get("n_f"))) if int(c or 0) > 0]
    return (f"{_join_and(measured).capitalize()} in the {wells} {w} sampled here "
            f"{'was' if len(measured) == 1 else 'were'} within the "
            f"drinking-water limits.")


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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
            FROM districts d
            LEFT JOIN blocks b            ON b.district_id = d.id
            LEFT JOIN monitoring_wells w  ON w.block_id = b.id
            LEFT JOIN water_samples s     ON s.well_id = w.id
            GROUP BY d.id, d.name
        )
        SELECT id::text, name, wells, samples,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band,
               {_DRIVER} AS band_driver,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health
        FROM per_district ORDER BY name
    """), _band_params())).mappings().all()

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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
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
               {_DRIVER} AS band_driver,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.002)) AS gj
        FROM per_district ORDER BY name
    """), _band_params())).mappings().all()

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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
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
               {_DRIVER} AS band_driver,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geometry, 0.001)) AS gj
        FROM per_block ORDER BY district, name
    """), dict(_band_params(),
               d=str(district_id) if district_id else None))).mappings().all()

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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests,
                   max(s.sampled_at)  AS last_sampled
            FROM monitoring_wells w
            LEFT JOIN blocks b         ON b.id = w.block_id
            LEFT JOIN districts d      ON d.id = b.district_id
            LEFT JOIN water_samples s  ON s.well_id = w.id
            GROUP BY w.id, w.name, w.latitude, w.longitude, b.name, d.name
        )
        SELECT name, latitude, longitude, block, district, samples, last_sampled,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band,
               {_DRIVER} AS band_driver,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health
        FROM per_well ORDER BY district, block
    """), _band_params())).mappings().all()

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
        ),
        agg AS (
            SELECT h.id, h.name, h.district,
                   count(DISTINCT w.id) AS wells,
                   count(s.id)          AS samples,
                   count(s.uranium_ppb) AS uranium_tests,
{_HEALTH_MAXES}
            FROM hit h
            LEFT JOIN monitoring_wells w ON w.block_id = h.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            GROUP BY h.id, h.name, h.district
        )
        SELECT id::text, name, district, wells, samples, uranium_tests,
               n_u, n_no3, n_f,
               round(max_u::numeric, 1)   AS max_uranium_ppb,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health,
               {_BANDS}  AS band,
               {_DRIVER} AS band_driver
        FROM agg
    """), dict(_band_params(), lon=lon, lat=lat))).mappings().first()

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
    # not reintroduce: a block whose wells were sampled but never analysed for a
    # determinand is a monitoring gap, not a clean result.
    #
    # WIDENED 2026-08-25. This used to override the band to "Not tested for
    # uranium" whenever `uranium_tests == 0`, which was right when uranium was
    # the only thing judged. It is now wrong: Musabani has two sampled wells
    # with no uranium result but with nitrate and fluoride results, and throwing
    # away a real nitrate measurement because a different determinand is missing
    # tells a resident less than the data supports. So the band now reports what
    # WAS measured, and the gap is stated alongside it rather than replacing it.
    untested = list(d.get("untested_health") or [])
    health_tested = int(d.get("n_u") or 0) + int(d.get("n_no3") or 0) \
        + int(d.get("n_f") or 0)

    if samples and not health_tested:
        explanation = (
            f"The {wells} well{'' if wells == 1 else 's'} here have been sampled, "
            f"but none of those samples were analysed for uranium, nitrate or "
            f"fluoride. There is no drinking-water health result to report — "
            f"that is a gap in testing, not a clean result.")
        d["band"] = "Not tested"
    else:
        explanation = _explain_multi(d, wells)

    if untested and samples:
        explanation += (
            f" Not every substance was analysed here: no result for "
            f"{_join_and(untested)}. A substance nobody measured has not been "
            f"shown to be safe.")

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
        "max_nitrate_mg_l": d.get("max_nitrate_mg_l"),
        "max_fluoride_mg_l": d.get("max_fluoride_mg_l"),
        "band": d["band"],
        "band_driver": d.get("band_driver"),
        "untested_health": untested,
        "safe_limit": URANIUM_LIMIT_PPB,
        "limits": {"uranium_ppb": URANIUM_LIMIT_PPB,
                   "nitrate_mg_l": NITRATE_LIMIT_MG_L,
                   "fluoride_mg_l": FLUORIDE_PERMISSIBLE_MG_L},
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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests
            FROM blocks b
            LEFT JOIN monitoring_wells w ON w.block_id = b.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            GROUP BY b.id
        )
        SELECT count(*) AS total,
               count(*) FILTER (
                   WHERE health_tests > 0
                     AND (max_u >= :limit OR max_no3 > :no3_limit
                          OR max_f > :f_permissible))                   AS unsafe,
               count(*) FILTER (
                   WHERE health_tests > 0
                     AND NOT (max_u >= :limit OR max_no3 > :no3_limit
                              OR max_f > :f_permissible)
                     AND (max_f > :f_acceptable
                          OR max_u >= :limit * 0.5))                    AS watch,
               count(*) FILTER (
                   WHERE health_tests > 0
                     AND NOT (max_u >= :limit OR max_no3 > :no3_limit
                              OR max_f > :f_permissible)
                     AND NOT (max_f > :f_acceptable
                              OR max_u >= :limit * 0.5))                AS safe,
               count(*) FILTER (WHERE samples > 0 AND health_tests = 0) AS untested,
               count(*) FILTER (WHERE samples = 0)                      AS no_data
        FROM per_block
    """), _band_params())).mappings().one()

    d = {k: int(v or 0) for k, v in row.items()}
    measured = d["unsafe"] + d["watch"] + d["safe"]
    unknown = d["untested"] + d["no_data"]

    response.headers["Cache-Control"] = _CACHE
    return {
        **d,
        "measured": measured,
        "unknown": unknown,
        "safe_limit_ppb": URANIUM_LIMIT_PPB,
        "judged_on": {
            "uranium_ppb": URANIUM_LIMIT_PPB,
            "nitrate_mg_l": NITRATE_LIMIT_MG_L,
            "fluoride_mg_l": FLUORIDE_PERMISSIBLE_MG_L,
            "note": ("Health-significant determinands only. Hardness, "
                     "alkalinity and TDS exceed at most Jharkhand wells and are "
                     "aquifer chemistry, not contamination — they are reported "
                     "on the water-quality surface and do not band a block."),
        },
        "coverage_pct": round(100.0 * measured / d["total"], 1) if d["total"] else 0.0,
        "headline": (
            f"{measured} of {d['total']} blocks have a drinking-water health "
            f"result. {unknown} do not."),
        "what_unknown_means": (
            "A block with no health result is not a safe block. It is a place "
            "nobody has measured, and it is counted separately here so it cannot "
            "be mistaken for a clean one. Arsenic and iron are unmeasured "
            "statewide, so no block has been fully cleared."),
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
                   max(s.uranium_ppb)    AS max_u,
                   max(s.nitrate_mg_l)   AS max_no3,
                   max(s.fluoride_mg_l)  AS max_f,
                   count(s.uranium_ppb)  AS n_u,
                   count(s.nitrate_mg_l) AS n_no3,
                   count(s.fluoride_mg_l) AS n_f,
                   count(s.uranium_ppb)
                     + count(s.nitrate_mg_l)
                     + count(s.fluoride_mg_l) AS health_tests,
                   max(s.sampled_at)    AS last_sampled
            FROM blocks b
            LEFT JOIN monitoring_wells w ON w.block_id = b.id
            LEFT JOIN water_samples s    ON s.well_id = w.id
            WHERE b.district_id = :d
            GROUP BY b.id, b.name
        )
        SELECT id::text, name, wells, samples, last_sampled,
               round(max_u::numeric, 1) AS max_uranium_ppb,
               {_BANDS} AS band,
               {_DRIVER} AS band_driver,
               round(max_no3::numeric, 1) AS max_nitrate_mg_l,
               round(max_f::numeric, 2)   AS max_fluoride_mg_l,
               {_UNTESTED} AS untested_health
        FROM per_block ORDER BY name
    """), dict(_band_params(), d=str(district_id)))).mappings().all()

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
