"""Where to sample next — the proposal's recommendation deliverable.

WHY THIS EXISTS. The TEXMiN proposal asks for two things about data gaps:
*identification* and *recommendations*. Identification was built and is strong —
`/public/risk/*` and Data & Gaps already show which blocks have no wells, and R10
added the distinction between "never sampled" and "sampled but never analysed for
uranium". Nothing turned that into an ordered list of where a limited sampling
budget should go, which is the half a person can act on. `LIMITATIONS.md` records
it as open finding O-1.

WHAT THIS IS NOT. It is not a model output. No plume is simulated, no surrogate
is called, and the score says nothing about whether contamination is present —
only about how badly a place is *observed*. Ranking by predicted risk would be
circular: the model is least trustworthy exactly where there is no data, so
letting it choose where to sample would send crews to the places the model is
most confident about and leave the blind spots blind.

THE WEIGHTS ARE A POLICY CHOICE, NOT A MEASUREMENT. There is no published
optimal-network objective for this setting, so any weighting is a judgement. They
are therefore module constants with a stated rationale, returned in the API
response, and rendered on screen next to the ranking — so a reader can disagree
with the ordering by disagreeing with a number they can see, rather than having
to read the source. That is the same discipline `UNGROUNDED_PARAMETERS` applies
to the physics.

GROUNDING. CGWB's own network-design practice is the reference point for the two
structural factors — coverage per unit area, and distance to the nearest
observation. The uranium-specific factor comes from this project's own finding
that several Singhbhum blocks have sampled wells with no uranium determination at
all, which BIS 10500 treats as a required parameter for a drinking-water source.
Neither is a citation for the *weights*; those remain ours.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Each factor scores 0–1, then these weights sum them to a 0–100 priority.
#: Rationale is carried alongside because it is shown to the user.
WEIGHTS: dict[str, dict[str, Any]] = {
    "never_sampled": {
        "weight": 30,
        "why": ("A block with no monitoring well is entirely unobserved. Nothing "
                "else in this list can be said about it, and no advisory can ever "
                "be issued for it."),
    },
    "sampled_not_analysed": {
        "weight": 30,
        "why": ("Wells exist and have been sampled, but no sample was analysed for "
                "uranium — so the one contaminant this platform exists to screen "
                "for is unmeasured. Cheapest gap to close: the wells and the "
                "sampling round already exist."),
    },
    "coverage": {
        "weight": 20,
        "why": ("Wells per 100 km². A large block with one well is thinly observed "
                "even though it is not a blank."),
    },
    "distance_to_tested_well": {
        "weight": 15,
        "why": ("How far the block centre is from the nearest well with a uranium "
                "result. Distance is how far an assumption has to travel before it "
                "reaches a measurement."),
    },
    "near_hypothetical_site": {
        "weight": 5,
        "why": ("Proximity to a registered hypothetical ISR site. Deliberately the "
                "smallest factor: no such mine exists, so letting a speculative "
                "location dominate a real monitoring plan would be backwards."),
    },
}

#: Above this, a block is "well covered" on the coverage factor alone.
GOOD_COVERAGE_WELLS_PER_100KM2 = 3.0
#: Distance at which the distance factor saturates.
FAR_KM = 25.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_block(row: dict[str, Any]) -> dict[str, Any]:
    """Score one block 0–100. Pure, so the weighting is testable in isolation."""
    wells = int(row.get("wells") or 0)
    tests = int(row.get("uranium_tests") or 0)
    samples = int(row.get("samples") or 0)
    area = float(row.get("area_km2") or 0.0)

    factors: dict[str, float] = {
        "never_sampled": 1.0 if wells == 0 else 0.0,
        # Only meaningful where wells exist: a blank block is already fully
        # scored by `never_sampled` and must not be counted twice.
        "sampled_not_analysed": 1.0 if (wells > 0 and samples > 0 and tests == 0) else 0.0,
        "coverage": (
            1.0 if area <= 0 or wells == 0 else
            _clamp01(1.0 - (wells / max(area, 1.0) * 100.0) / GOOD_COVERAGE_WELLS_PER_100KM2)
        ),
        "distance_to_tested_well": (
            1.0 if row.get("km_to_tested_well") is None
            else _clamp01(float(row["km_to_tested_well"]) / FAR_KM)
        ),
        "near_hypothetical_site": (
            0.0 if row.get("km_to_isr") is None
            else _clamp01(1.0 - float(row["km_to_isr"]) / FAR_KM)
        ),
    }

    score = sum(factors[k] * WEIGHTS[k]["weight"] for k in WEIGHTS)
    return {"score": round(score, 1), "factors": {k: round(v, 3) for k, v in factors.items()}}


def _reason(row: dict[str, Any], factors: dict[str, float]) -> str:
    """One plain sentence saying why this block is where it is in the list."""
    wells = int(row.get("wells") or 0)
    tests = int(row.get("uranium_tests") or 0)
    samples = int(row.get("samples") or 0)

    if wells == 0:
        return ("No monitoring well has ever been installed here. Nothing is known "
                "about this block's groundwater.")
    if samples > 0 and tests == 0:
        return (f"{wells} well(s) here have been sampled {samples} time(s), but no "
                f"sample was analysed for uranium. Adding the determination to the "
                f"next routine round would close this gap without new drilling.")
    if factors["coverage"] > 0.6:
        return (f"Only {wells} well(s) across {row.get('area_km2', 0):.0f} km² — thin "
                f"coverage for a block this size.")
    if factors["distance_to_tested_well"] > 0.6:
        km = row.get("km_to_tested_well")
        return (f"The nearest uranium result is {km:.0f} km away, so conditions here "
                f"are inferred rather than measured.")
    return (f"{wells} well(s) with {tests} uranium result(s). Reasonably observed; "
            f"listed for completeness.")


async def recommendations(db: AsyncSession, *, limit: int = 25,
                          district: Optional[str] = None) -> dict[str, Any]:
    """Blocks ranked by how badly they need sampling."""
    rows = (await db.execute(text("""
        WITH per_block AS (
            SELECT b.id, b.name, d.name AS district,
                   b.geometry,
                   ST_Area(b.geometry::geography) / 1e6      AS area_km2,
                   count(DISTINCT w.id)                      AS wells,
                   count(s.id)                               AS samples,
                   count(s.uranium_ppb)                      AS uranium_tests,
                   max(s.uranium_ppb)                        AS max_uranium_ppb
            FROM blocks b
            JOIN districts d              ON d.id = b.district_id
            LEFT JOIN monitoring_wells w  ON w.block_id = b.id
            LEFT JOIN water_samples s     ON s.well_id = w.id
            WHERE b.geometry IS NOT NULL
              AND (CAST(:district AS text) IS NULL OR d.name = CAST(:district AS text))
            GROUP BY b.id, b.name, d.name, b.geometry
        ),
        tested_wells AS (
            SELECT w.location
            FROM monitoring_wells w
            JOIN water_samples s ON s.well_id = w.id
            WHERE w.location IS NOT NULL AND s.uranium_ppb IS NOT NULL
        )
        SELECT p.id::text, p.name, p.district,
               round(p.area_km2::numeric, 1)        AS area_km2,
               p.wells, p.samples, p.uranium_tests,
               round(p.max_uranium_ppb::numeric, 1) AS max_uranium_ppb,
               round((
                   SELECT min(ST_DistanceSphere(
                       ST_Centroid(p.geometry), t.location::geometry)) / 1000.0
                   FROM tested_wells t
               )::numeric, 1) AS km_to_tested_well,
               round((
                   SELECT min(ST_DistanceSphere(
                       ST_Centroid(p.geometry), i.location::geometry)) / 1000.0
                   FROM isr_points i WHERE i.location IS NOT NULL
               )::numeric, 1) AS km_to_isr
        FROM per_block p
    """), {"district": district})).mappings().all()

    scored = []
    for r in rows:
        d = dict(r)
        for k in ("area_km2", "km_to_tested_well", "km_to_isr", "max_uranium_ppb"):
            if d.get(k) is not None:
                d[k] = float(d[k])
        s = score_block(d)
        d.update(s)
        d["reason"] = _reason(d, s["factors"])
        # `band` is deliberately absent: this list is about observation, not risk,
        # and pairing a priority with a risk band invites reading one as the other.
        scored.append(d)

    # Area is the tie-break, not a sixth weighted factor.
    #
    # Blocks with no well at all legitimately score identically — they are
    # equally unobserved, and inventing a weight to separate them would dress a
    # sort order up as a measurement. But a 318 km² blank block is a larger gap
    # than a 50 km² one, and a crew planning a route needs *an* order. So the
    # score stays honest about the tie and the ordering within it is stated:
    # larger unobserved area first, then alphabetical for stability.
    scored.sort(key=lambda x: (-x["score"], -(x.get("area_km2") or 0.0), x["name"]))
    return {
        "generated_for": district or "all districts",
        "count": len(scored),
        "recommendations": scored[:limit],
        "weights": WEIGHTS,
        "constants": {
            "good_coverage_wells_per_100km2": GOOD_COVERAGE_WELLS_PER_100KM2,
            "far_km": FAR_KM,
        },
        "tie_break": (
            "Blocks with no well at all score identically because they are equally "
            "unobserved. Among them the larger area is listed first, then "
            "alphabetically. That is a sort order, not a measurement."),
        "what_this_is": (
            "A ranking of how poorly observed each block is — not a prediction of "
            "contamination. No simulation is run and no model is called. The "
            "weights below are a policy judgement, not a measurement, and are "
            "shown so the ordering can be argued with."),
    }


# ═══════════════════════════════════════════════════════════════════════
# Where inside a block to actually put the well
#
# The ranking above answers "which block", which is as far as a priority list
# can go. The next question a person asks is "where do I send the drilling rig",
# and a block is 200-900 km2 — far too coarse to act on.
#
# THE CRITERION: maximise distance from every existing uranium-tested well,
# subject to staying inside the block. That is standard coverage-based sampling
# design — a new observation is worth most where the nearest existing one is
# furthest, because that is where the interpolated value is currently least
# constrained by data. It is a *geometric* criterion and makes no claim about
# where contamination is; ranking candidate sites by predicted concentration
# would be circular in exactly the way the block ranking already avoids.
#
# Points are sampled deterministically (fixed seed) so the same block returns
# the same suggestion every time. A siting recommendation that moved between
# page loads could not be taken to a field team.
#
# WHAT THIS IS NOT: a survey. Land ownership, access, drilling feasibility,
# depth to bedrock and local permission are all unknown here, and every response
# says so. These are candidate coordinates to start a site visit from, not
# instructions to drill.
# ═══════════════════════════════════════════════════════════════════════

#: Candidate points sampled inside a block before scoring. Enough to resolve a
#: few hundred metres in a typical 250 km2 block; more just costs time.
CANDIDATE_POINTS = 400
#: Deterministic sampling — see above.
CANDIDATE_SEED = 20260819
#: Suggested sites are spread at least this far apart, so three suggestions are
#: three genuinely different places rather than one place three times.
MIN_SEPARATION_KM = 2.0


async def suggested_sites(db: AsyncSession, block_id: str, *,
                          n: int = 3) -> dict[str, Any]:
    """Candidate well coordinates inside one block, best-covered-gap first."""
    meta = (await db.execute(text("""
        SELECT b.name, d.name AS district,
               round((ST_Area(b.geometry::geography) / 1e6)::numeric, 1) AS area_km2,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(b.geometry, 0.001)) AS gj
        FROM blocks b JOIN districts d ON d.id = b.district_id
        WHERE b.id = CAST(:id AS uuid) AND b.geometry IS NOT NULL
    """), {"id": block_id})).mappings().first()
    if meta is None:
        from app.exceptions import AppException
        raise AppException("no such block, or it has no geometry", status_code=404)

    rows = (await db.execute(text("""
        WITH b AS (
            SELECT geometry FROM blocks WHERE id = CAST(:id AS uuid)
        ),
        candidates AS (
            SELECT (ST_Dump(ST_GeneratePoints(geometry, :n_pts, :seed))).geom AS pt
            FROM b
        ),
        tested AS (
            SELECT w.location::geometry AS g
            FROM monitoring_wells w
            JOIN water_samples s ON s.well_id = w.id
            WHERE w.location IS NOT NULL AND s.uranium_ppb IS NOT NULL
        ),
        any_well AS (
            SELECT w.location::geometry AS g
            FROM monitoring_wells w WHERE w.location IS NOT NULL
        )
        SELECT ST_X(c.pt) AS lon, ST_Y(c.pt) AS lat,
               COALESCE((SELECT min(ST_DistanceSphere(c.pt, t.g)) FROM tested t),
                        999999) / 1000.0 AS km_to_tested,
               COALESCE((SELECT min(ST_DistanceSphere(c.pt, a.g)) FROM any_well a),
                        999999) / 1000.0 AS km_to_any_well
        FROM candidates c
        ORDER BY km_to_tested DESC
    """), {"id": block_id, "n_pts": CANDIDATE_POINTS,
           "seed": CANDIDATE_SEED})).mappings().all()

    import math

    def km_apart(a: dict, b: dict) -> float:
        dlat = (a["lat"] - b["lat"]) * 111.32
        dlon = ((a["lon"] - b["lon"]) * 111.32
                * math.cos(math.radians((a["lat"] + b["lat"]) / 2)))
        return math.hypot(dlat, dlon)

    picked: list[dict[str, Any]] = []
    for r in rows:
        cand = {k: (float(v) if v is not None else None) for k, v in r.items()}
        # Greedy, with a separation floor: without it the top three candidates
        # are almost always the same corner of the block, which is one
        # suggestion printed three times.
        if any(km_apart(cand, p) < MIN_SEPARATION_KM for p in picked):
            continue
        picked.append(cand)
        if len(picked) >= n:
            break

    import json
    for i, p in enumerate(picked, start=1):
        p["rank"] = i
        p["km_to_tested_well"] = round(p.pop("km_to_tested"), 1)
        p["km_to_nearest_well"] = round(p.pop("km_to_any_well"), 1)
        p["lat"] = round(p["lat"], 5)
        p["lon"] = round(p["lon"], 5)
        p["why"] = (
            f"The nearest well with a uranium result is "
            f"{p['km_to_tested_well']} km away — the least-observed part of this "
            f"block." if p["km_to_tested_well"] < 900 else
            "No well anywhere has a uranium result to measure distance from, so "
            "any point in this block is equally unobserved.")

    return {
        "block_id": block_id,
        "block": meta["name"],
        "district": meta["district"],
        "area_km2": float(meta["area_km2"]),
        "geometry": json.loads(meta["gj"]),
        "sites": picked,
        "criterion": (
            "Maximum distance from any existing uranium-tested well, inside the "
            "block. A new observation is worth most where the nearest existing "
            "one is furthest, because that is where the value is least "
            "constrained by data."),
        "caveat": (
            "These are candidate coordinates to start a site visit from — NOT a "
            "survey and NOT a drilling instruction. Land ownership, access, "
            "depth to bedrock, drilling feasibility and local permission are all "
            "unknown to this system and will decide the actual location."),
        "determinism": (
            f"Candidates are sampled with a fixed seed ({CANDIDATE_SEED}), so this "
            f"block returns the same suggestion every time. A recommendation that "
            f"moved between page loads could not be taken to a field team."),
    }


async def suggested_sites_bulk(db: AsyncSession, *, top: int = 10, n: int = 2,
                               district: Optional[str] = None) -> dict[str, Any]:
    """Suggested well sites for the top-N blocks at once, for a statewide map.

    The per-block endpoint answers "where in THIS block"; a monitoring programme
    is planned across a district, not one block at a time, so this returns the
    whole proposed network in one response — plus the wells that already exist,
    so the two can be drawn together. A proposal is only judgeable next to what
    is already there.

    Kept to `top` blocks and `n` sites each because each block runs its own
    point-sampling pass; asking for all 264 would be a slow request nobody reads.
    """
    ranked = await recommendations(db, limit=top, district=district)

    out: list[dict[str, Any]] = []
    for block in ranked["recommendations"]:
        s = await suggested_sites(db, block["id"], n=n)
        out.append({
            "block_id": block["id"], "block": block["name"],
            "district": block["district"], "score": block["score"],
            "reason": block["reason"], "wells": block["wells"],
            "uranium_tests": block["uranium_tests"],
            "area_km2": block["area_km2"],
            "geometry": s["geometry"], "sites": s["sites"],
        })

    existing = (await db.execute(text("""
        SELECT w.name, w.latitude, w.longitude, d.name AS district,
               count(s.uranium_ppb) AS uranium_tests,
               count(s.id)          AS samples
        FROM monitoring_wells w
        LEFT JOIN blocks b        ON b.id = w.block_id
        LEFT JOIN districts d     ON d.id = b.district_id
        LEFT JOIN water_samples s ON s.well_id = w.id
        WHERE w.latitude IS NOT NULL AND w.longitude IS NOT NULL
        GROUP BY w.id, w.name, w.latitude, w.longitude, d.name
    """))).mappings().all()

    return {
        "blocks": out,
        "proposed_total": sum(len(b["sites"]) for b in out),
        "existing_wells": [dict(w) for w in existing],
        "existing_total": len(existing),
        "tested_total": sum(1 for w in existing if (w["uranium_tests"] or 0) > 0),
        "weights": ranked["weights"],
        "criterion": (
            "Blocks are ranked by how poorly they are observed; within each, "
            "sites maximise distance from any existing uranium-tested well."),
        "caveat": (
            "Candidate coordinates to start a site visit from — NOT a survey and "
            "NOT a drilling instruction. Land ownership, access, depth to bedrock "
            "and local permission will decide the actual location."),
    }


# ═══════════════════════════════════════════════════════════════════════
# The data-deficiency matrix
#
# One column per KIND of gap, one row per district. The point is not the counts
# — it is that each column has a consequence, and those consequences are what
# `LIMITATIONS.md` is made of. A gap nobody can name the effect of is a
# statistic; a gap with its effect written beside it is a limitation.
#
# Every dimension is measured from the database, not asserted. `blocks` is the
# capability that gap denies and `implies` is the sentence it forces the project
# to say. Those two fields are why this is worth building rather than counting
# wells.
# ═══════════════════════════════════════════════════════════════════════

STALE_YEARS = 3

#: Gap kind -> what it means, what it stops the project doing, what it forces us
#: to admit. `key` matches the column name produced by the SQL below.
GAP_DIMENSIONS: list[dict[str, str]] = [
    {
        "key": "blocks_no_wells",
        "label": "Blocks with no well",
        "means": "No monitoring well has ever been installed in the block.",
        "blocks": "Any statement at all about that block's groundwater.",
        "implies": ("Coverage is not uniform. A district-level figure is an average "
                    "over blocks that were measured and blocks that never were, and "
                    "must not be read as describing the whole district."),
    },
    {
        "key": "wells_never_analysed_u",
        "label": "Wells never analysed for uranium",
        "means": ("The well exists and has been sampled, but no sample was ever "
                  "analysed for uranium."),
        "blocks": "Any uranium statement for that location — including a clean one.",
        "implies": ("'No data' on the uranium surface is a gap in ANALYSIS, not a "
                    "clean result. The well and the sampling round already exist, so "
                    "this is the cheapest deficiency in the register to close."),
    },
    {
        "key": "wells_single_sample",
        "label": "Wells with only one sample",
        "means": "One measurement, one date. No repeat visit.",
        "blocks": ("Any trend, any seasonal signal, and any statistically-derived "
                   "control limit."),
        "implies": ("This is why the excursion UCL is a fixed percentage above "
                    "baseline rather than NUREG-1569's preferred statistical rule: "
                    "that rule needs a per-well temporal series and there is none. "
                    "Substituting regional spatial spread was tested and rejected."),
    },
    {
        "key": "blocks_no_level_station",
        "label": "Blocks with no water-level station",
        "means": "No groundwater-level observation point in the block.",
        "blocks": "A measured hydraulic gradient there.",
        "implies": ("The flow field falls back to smoothed DEM topography wherever "
                    "stations are sparse, so flow direction in those blocks is "
                    "inferred from surface shape rather than from measured head."),
    },
    {
        "key": "wells_stale",
        "label": f"Wells not sampled in {STALE_YEARS}+ years",
        "means": "The most recent sample predates the last three years.",
        "blocks": "Any claim that a result is current.",
        "implies": ("Results are historical. This platform screens and prepares; it "
                    "does not monitor in real time, and nothing here should be "
                    "described as live."),
    },
]


async def gap_matrix(db: AsyncSession) -> dict[str, Any]:
    """Per-district counts across every named gap dimension."""
    rows = (await db.execute(text(f"""
        WITH well_stats AS (
            SELECT w.id, w.block_id,
                   count(s.id)          AS samples,
                   count(s.uranium_ppb) AS u_tests,
                   max(s.sampled_at)    AS last_sampled
            FROM monitoring_wells w
            LEFT JOIN water_samples s ON s.well_id = w.id
            GROUP BY w.id, w.block_id
        ),
        block_stats AS (
            SELECT b.id, b.district_id,
                   count(DISTINCT ws.id) AS wells,
                   count(DISTINCT st.id) AS stations
            FROM blocks b
            LEFT JOIN well_stats ws          ON ws.block_id = b.id
            LEFT JOIN monitoring_stations st ON st.block_id = b.id
            GROUP BY b.id, b.district_id
        )
        SELECT d.name AS district,
               count(DISTINCT bs.id)                                 AS blocks,
               count(DISTINCT bs.id) FILTER (WHERE bs.wells = 0)     AS blocks_no_wells,
               count(DISTINCT bs.id) FILTER (WHERE bs.stations = 0)  AS blocks_no_level_station,
               count(DISTINCT ws.id)                                 AS wells,
               count(DISTINCT ws.id) FILTER (WHERE ws.samples > 0
                                               AND ws.u_tests = 0)   AS wells_never_analysed_u,
               count(DISTINCT ws.id) FILTER (WHERE ws.samples = 1)   AS wells_single_sample,
               count(DISTINCT ws.id) FILTER (
                   WHERE ws.last_sampled IS NOT NULL
                     AND ws.last_sampled < now() - interval '{STALE_YEARS} years'
               )                                                     AS wells_stale
        FROM districts d
        LEFT JOIN block_stats bs ON bs.district_id = d.id
        LEFT JOIN well_stats  ws ON ws.block_id = bs.id
        GROUP BY d.name
        ORDER BY d.name
    """))).mappings().all()

    districts = [dict(r) for r in rows]
    totals: dict[str, int] = {
        d["key"]: sum(int(r.get(d["key"]) or 0) for r in districts)
        for d in GAP_DIMENSIONS
    }
    totals["blocks"] = sum(int(r["blocks"] or 0) for r in districts)
    totals["wells"] = sum(int(r["wells"] or 0) for r in districts)

    return {
        "dimensions": GAP_DIMENSIONS,
        "districts": districts,
        "totals": totals,
        "stale_years": STALE_YEARS,
        "what_this_is": (
            "One column per KIND of data gap, measured from the database. Each "
            "column carries the capability it denies and the limitation it forces "
            "this project to state — a gap nobody can name the effect of is a "
            "statistic; a gap with its effect beside it is a limitation."),
    }
