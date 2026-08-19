"""
ml_pipeline.data_prep.ore_loader  (Module 2 -- ore-body masking)
===============================================================
Turn `Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv` into a 3-tier
spatial mask so the engine stops simulating a massive uranium plume at pins
with no uranium ore. ISR leaches what is IN the rock: away from ore, an alkaline
lixiviant only perturbs non-radiological chemistry (sulfate / TDS), not uranium.

Three tiers (most to least confident):
  * "deposit" -- inside a surveyed deposit polygon (+500 m buffer). Real ore ->
                 full uranium source term.
  * "belt"    -- inside the Singhbhum Thrust Belt regional envelope but outside
                 any deposit. The CSV explicitly labels this outline "low
                 confidence / illustrative" -> reduced, clearly-hypothetical C0.
  * "none"    -- everywhere else. No uranium source: clamp C0 to a trace level.

COORDINATE CONVENTION: the WKT in this CSV is standard [lon lat] (verified:
Jaduguda centroid ~ 86.35E, 22.65N), unlike District_Boundary_JH.geojson.
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

from shapely import wkt
from shapely.geometry import Point, mapping
from shapely.ops import unary_union
from shapely.prepared import prep

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
ORE_CSV = REPO_ROOT / "Datasets" / "Jharkhand Ore" / "jharkhand_uranium_deposits.csv"

_DEG_TO_KM = 111.0

# Polish #2: representative ISR-target depth (m) per deposit -- so a deposit pin
# defaults the ore-depth slider to that deposit's real mineralisation depth rather
# than a flat 150 m. Grounded in mining type: Banduhurang is the country's first
# open-PIT U mine (shallow); Mohuldih's ore is documented over ~250 m vertical;
# the rest are deep underground mines in the E-Singhbhum fracture window (45-260 m).
# User-overridable (it only seeds the slider). Off-deposit pins keep 150.
DEPOSIT_ORE_DEPTH_M = {
    "Jaduguda": 180.0, "Bhatin": 150.0, "Narwapahar": 150.0, "Turamdih": 140.0,
    "Banduhurang": 60.0, "Mohuldih": 250.0, "Bagjata": 160.0,
}


def deposit_ore_depth(name: str | None) -> float | None:
    """Representative ISR-target depth (m) for a surveyed deposit, or None."""
    return DEPOSIT_ORE_DEPTH_M.get((name or "").strip())


@functools.lru_cache(maxsize=1)
def _ore():
    """(deposits, belt) prepared geometries + metadata.

    deposits: list of (name, shapely_polygon_buffered, prepared).
    belt:     (polygon, prepared) for the regional envelope, or None.
    """
    deposits, belt, raw_deposits = [], None, []
    added_deposits, added_names = [], set()
    with ORE_CSV.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            geom = wkt.loads(row["geometry_wkt"]).buffer(0)
            name = row["name"].strip()
            if name == P.ORE_BELT_NAME:
                belt = geom
                continue

            # A FIELD-ADDED DEPOSIT MUST NOT REDRAW THE REGIONAL BELT (R11).
            #
            # `raw_deposits` feeds the convex hull that the belt envelope is
            # unioned with, below. That was safe while every row was a surveyed
            # GSI deposit inside the Singhbhum cluster. Once approved field
            # observations began syncing into this file, a single sighting
            # anywhere in Jharkhand stretched the hull from the cluster to that
            # point — turning one local report into a belt spanning tens of
            # kilometres of country with no geological basis, inside which the
            # engine will produce a uranium plume.
            #
            # The belt is a REGIONAL STRUCTURE from published mapping. One field
            # sighting is evidence of ore at that spot; it is not evidence that
            # the structure extends there. So an `added` row still gets its own
            # deposit polygon — the local zone works exactly as intended — but it
            # is kept out of the hull.
            #
            # `record_source` is written by `backend/app/services/datasets.py`.
            # Rows that predate the column, and the shipped rows, have no value
            # and are treated as `original`.
            if (row.get("record_source") or "original").strip() != "added":
                raw_deposits.append(geom)
            else:
                added_deposits.append(geom)
                added_names.add(name)

            buffered = geom.buffer(P.ORE_DEPOSIT_BUFFER_DEG)
            deposits.append((name, buffered, prep(buffered)))

    # ------------------------------------------------------------------ #
    # BELT REGISTRATION FIX (2026-08-04)
    #
    # The hand-drawn belt arc in the CSV describes itself as an "Approximate
    # envelope enclosing the known deposit cluster ... that hosts all deposits
    # above" -- but it does not. Measured: it contains only Jaduguda; the other
    # SIX documented deposits fall 1.0-13.7 km OUTSIDE it, because the arc sits
    # roughly 6 km south of the actual deposit chain. Consequences: pins between
    # real deposits resolved to zone="none", which zeroed the uranium source term
    # AND (because Ra-226 is ore-zone gated) made radium show no plume anywhere
    # off a deposit -- the belt tier was effectively dead.
    #
    # Fix: union the CSV arc with the convex hull of the ACTUAL deposit polygons.
    # Strictly ADDITIVE -- no pin that is currently "belt" loses that status --
    # and derived entirely from deposit coordinates already in the dataset, so it
    # invents no new geology. The hull alone is ~268 km2 versus the arc's ~264,
    # i.e. this corrects the belt's POSITION rather than inflating its extent.
    #
    # The CSV row is deliberately left untouched: it is the record of what was
    # originally drawn, and correcting here keeps the fix visible, tested, and
    # immune to a silent re-import.
    # ------------------------------------------------------------------ #
    # A second, independent defect the hull alone does not cure: the 3.6b source
    # taper ramps C0 from a deposit's own value down to the flat belt value over
    # ORE_TAPER_KM, but `_belt_c0` only runs for zone == "belt". Where the belt
    # does not extend that far around a deposit, the taper has nowhere to act and
    # C0 falls off a cliff to background -- reintroducing exactly the hard step
    # 3.6b was built to remove. Measured before this fix: a pin 12 m outside the
    # Jaduguda halo was already "none". The belt must therefore cover at least
    # the taper radius around every deposit for the taper to be reachable.
    if raw_deposits:
        merged = unary_union(raw_deposits)
        # The taper measures distance from the BUFFERED deposit (raw + 500 m
        # halo), so the belt must be buffered from the raw polygon by the halo
        # PLUS the taper length -- otherwise the belt runs out ~500 m early and
        # the ramp is truncated mid-slope (measured: it died at 2.5 km of 3.0,
        # still at C0 918 of 1706, so the "continuous" taper ended in a cliff).
        taper_deg = P.ORE_DEPOSIT_BUFFER_DEG + float(P.ORE_TAPER_KM) / _DEG_TO_KM
        extra = [merged.convex_hull, merged.buffer(taper_deg)]
        belt = unary_union(extra if belt is None else [belt, *extra])

    # A field-added deposit gets a LOCAL halo, never a share of the hull.
    #
    # Excluding it from the hull alone would leave it with no belt around it, so
    # the 3.6b taper would have nowhere to act and C0 would fall off a cliff at
    # its 500 m buffer — the exact hard step that fix removed. Buffering each
    # added deposit on its own restores the ramp locally while keeping the
    # regional envelope where the published mapping put it.
    #
    # Measured on the real file: one added deposit at Jharia stretched the hull
    # from 200.6 km2 to 1,586.2 km2 — a 7.9x expansion, ~1,386 km2 of country in
    # which the engine would have produced a uranium plume with no geological
    # basis behind it.
    if added_deposits:
        taper_deg = P.ORE_DEPOSIT_BUFFER_DEG + float(P.ORE_TAPER_KM) / _DEG_TO_KM
        local = [g.buffer(taper_deg) for g in added_deposits]
        belt = unary_union(local if belt is None else [belt, *local])

    belt_pair = (belt, prep(belt)) if belt is not None else None
    return deposits, belt_pair


@functools.lru_cache(maxsize=1)
def added_deposit_names() -> frozenset:
    """Deposits that came from an approved field observation, not from mapping.

    They are real ore zones locally, but they carry no regional-structure claim —
    see `_ore`. Exposed so callers and tests can tell the two apart without
    re-reading the CSV.
    """
    _ore()
    import csv as _csv
    with ORE_CSV.open(encoding="utf-8-sig") as fh:
        return frozenset(
            r["name"].strip() for r in _csv.DictReader(fh)
            if (r.get("record_source") or "original").strip() == "added")


def ore_zone_at(lon: float, lat: float) -> dict:
    """Classify a pin into deposit / belt / none, with the nearest deposit name
    and distance (km). Distance is 0 when inside a deposit (+buffer)."""
    deposits, belt_pair = _ore()
    pt = Point(float(lon), float(lat))

    nearest_name, nearest_deg = None, float("inf")
    inside_deposit = None
    for name, geom, pg in deposits:
        if pg.covers(pt):
            inside_deposit = name
            nearest_name, nearest_deg = name, 0.0
            break
        d = geom.distance(pt)
        if d < nearest_deg:
            nearest_name, nearest_deg = name, d

    if inside_deposit is not None:
        zone = "deposit"
    elif belt_pair is not None and belt_pair[1].covers(pt):
        zone = "belt"
    else:
        zone = "none"

    # Distance is reported in BOTH km and whole metres. Rounding to 0.1 km alone
    # displayed a pin 12 m outside Jaduguda as "0.0 km" while the zone read
    # "none" -- a flatly contradictory readout ("you are on the deposit, there is
    # no deposit"). Metres disambiguate the near-miss that the km rounding hides.
    nearest_m = (None if nearest_deg == float("inf")
                 else round(nearest_deg * _DEG_TO_KM * 1000.0))
    return {
        "zone": zone,
        "deposit_name": inside_deposit,
        "nearest_deposit": nearest_name,
        "nearest_deposit_km": (None if nearest_deg == float("inf")
                               else round(nearest_deg * _DEG_TO_KM, 2)),
        "nearest_deposit_m": nearest_m,
        # explicit so callers never infer "inside" from a rounded-to-zero distance
        "inside_deposit": inside_deposit is not None,
    }


@functools.lru_cache(maxsize=1)
def ore_geojson() -> dict:
    """Deposit polygons + belt envelope as a GeoJSON FeatureCollection for the
    map overlay (so users SEE why a zone is or isn't uranium-bearing)."""
    deposits, belt_pair = _ore()
    feats = [{
        "type": "Feature",
        "properties": {"name": name, "tier": "deposit"},
        "geometry": mapping(geom),
    } for name, geom, _ in deposits]
    if belt_pair is not None:
        feats.append({
            "type": "Feature",
            "properties": {"name": P.ORE_BELT_NAME, "tier": "belt"},
            "geometry": mapping(belt_pair[0]),
        })
    return {"type": "FeatureCollection", "features": feats}


if __name__ == "__main__":
    deposits, belt_pair = _ore()
    print(f"[ore] {len(deposits)} deposits + belt={'yes' if belt_pair else 'no'}")
    for name, lon, lat in [("Jaduguda", 86.347, 22.652), ("mid-belt", 86.25, 22.63),
                           ("Ranchi (clean)", 85.33, 23.36),
                           ("Dhanbad (clean)", 86.43, 23.80)]:
        print(f"  {name:16s} -> {ore_zone_at(lon, lat)}")
