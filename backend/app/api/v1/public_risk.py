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
from app.services import health_bands as hb

router = APIRouter(prefix="/public/risk", tags=["Public (citizen)"])

# ── the banding rule ─────────────────────────────────────────────────
#
# MOVED TO `services/health_bands.py` ON 2026-08-26, and re-exported here under
# the private names this module has always used.
#
# It moved because it was not one rule. `/citizen/my-area` carried a second,
# uranium-only implementation of the same idea, so a block over the fluoride
# limit read "High concern" on the public map and "Low concern" on the page a
# resident opens to check their own water. A rule that can be stated in two
# places will eventually be stated two ways; this one already had been.
#
# The aliases are not vestigial politeness. `tests/test_r14_citizen_safety.py`
# reaches for `pr._BANDS`, `pr._UNTESTED`, `pr._band_params`, `pr._explain_multi`
# and `pr._join_and` by name, and those tests pin the properties that keep a
# monitoring gap from rendering as a pass. Keeping the names is what lets the
# rule move without loosening a single one of them.
URANIUM_LIMIT_PPB = hb.URANIUM_LIMIT_PPB
NITRATE_LIMIT_MG_L = hb.NITRATE_LIMIT_MG_L
FLUORIDE_ACCEPTABLE_MG_L = hb.FLUORIDE_ACCEPTABLE_MG_L
FLUORIDE_PERMISSIBLE_MG_L = hb.FLUORIDE_PERMISSIBLE_MG_L

_HEALTH_MAXES = hb.HEALTH_MAXES
_BANDS = hb.BANDS
_DRIVER = hb.DRIVER
_UNTESTED = hb.UNTESTED
_band_params = hb.band_params
_join_and = hb.join_and
_explain_multi = hb.explain_multi

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


# `_explain`, `_join_and` and `_explain_multi` USED TO BE DEFINED HERE.
#
# `_join_and` and `_explain_multi` moved to `services/health_bands.py` and are
# re-exported at the top of this module, so nothing that called them changed.
#
# `_explain` was DELETED, not moved, and that is the second half of the
# 2026-08-26 banding fix. It was a uranium-only reading of a band that has been
# multi-determinand since 2026-08-25, and three handlers still called it:
# `/geojson/blocks`, `/{district_id}` and the block popups the citizen map draws
# from them. A block banded "High concern" because its fluoride sat above the
# permissible limit was handed the sentence "Uranium in the 2 wells sampled here
# was well below the 30 ppb safe limit" — beneath the words "High concern", in
# the same card, both generated from the same row.
#
# There is no version of that function worth keeping. Every caller now uses
# `hb.describe`, which reads the band it was actually given, names the
# determinand that set it, and states what nobody analysed.

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
               n_u, n_no3, n_f,
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

    # `n_u`/`n_no3`/`n_f` are projected for `describe`, which needs to know what
    # was actually analysed — both to separate "sampled but never analysed" from
    # "no samples at all", and to name only the determinands a "Low concern"
    # block was genuinely cleared for.
    out = _collection(rows)
    for f in out["features"]:
        p = f["properties"]
        p["band"], p["what_it_means"], p["untested_health"] = hb.describe(
            p, wells=int(p.get("wells") or 0), samples=int(p.get("samples") or 0))
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
    #
    # The three steps this used to spell out inline now live in `hb.describe`,
    # which is what `/citizen/my-area` and `/geojson/blocks` call too. They were
    # correct only here, which is precisely how the surfaces drifted.
    d["band"], explanation, untested = hb.describe(d, wells=wells, samples=samples)

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
               n_u, n_no3, n_f,
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
        d["band"], d["what_it_means"], d["untested_health"] = hb.describe(
            d, wells=int(d.get("wells") or 0), samples=int(d.get("samples") or 0))
        blocks.append(d)

    response.headers["Cache-Control"] = _CACHE
    return {
        "district": dict(district),
        "unit": "ppb", "safe_limit": URANIUM_LIMIT_PPB,
        "blocks": blocks,
        "what_this_is": _DISCLAIMER,
        # Counted AFTER `describe`, which can move a block from 'No data' to
        # 'Not tested'. Counting the raw SQL band here would report a block that
        # has been sampled as one that never was.
        "data_gap": sum(1 for b in blocks if b["band"] in ("No data", "Not tested")),
    }
