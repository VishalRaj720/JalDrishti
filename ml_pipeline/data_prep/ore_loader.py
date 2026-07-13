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
    deposits, belt = [], None
    with ORE_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            geom = wkt.loads(row["geometry_wkt"]).buffer(0)
            name = row["name"].strip()
            if name == P.ORE_BELT_NAME:
                belt = geom
            else:
                buffered = geom.buffer(P.ORE_DEPOSIT_BUFFER_DEG)
                deposits.append((name, buffered, prep(buffered)))
    belt_pair = (belt, prep(belt)) if belt is not None else None
    return deposits, belt_pair


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

    return {
        "zone": zone,
        "deposit_name": inside_deposit,
        "nearest_deposit": nearest_name,
        "nearest_deposit_km": (None if nearest_deg == float("inf")
                               else round(nearest_deg * _DEG_TO_KM, 1)),
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
