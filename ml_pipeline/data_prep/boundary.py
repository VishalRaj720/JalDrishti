"""
ml_pipeline.data_prep.boundary  (Module 1 -- hard geographic boundary)
=====================================================================
Strict Jharkhand state-border enforcement for the dashboard. Replaces the soft
1-degree bounding-box cushion that let a pin land ~111 km into Bihar / West
Bengal / Odisha and still return a (wrong) prediction from the nearest aquifer.

The dissolved district boundary is the authority: any pin outside it (plus a
small border tolerance) is rejected before any hydrogeology is resolved.

DATA QUIRK (verified 2026-07): District_Boundary_JH.geojson stores coordinates
as [lat, lon] -- the axes are swapped versus the GeoJSON spec AND versus every
other file in Datasets/ (the aquifer polygons and the ore WKT are [lon, lat]).
We swap on load so all downstream code speaks a single (lon, lat) convention.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

from shapely.geometry import shape, Point, mapping
from shapely.ops import unary_union, transform
from shapely.prepared import prep

REPO_ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_GEOJSON = REPO_ROOT / "Datasets" / "District_Boundary_JH.geojson"

# ~200 m border tolerance in degrees (1 deg lat ~ 111 km). Absorbs digitization
# noise so a legitimate pin exactly on the state line is not spuriously rejected.
BORDER_TOLERANCE_DEG = 0.002


def _swap_xy(geom):
    """District_Boundary_JH.geojson is stored [lat, lon] -> swap to [lon, lat]."""
    return transform(lambda x, y, z=None: (y, x), geom)


@functools.lru_cache(maxsize=1)
def _boundary():
    """(union_geom, prepared_geom): the 24-district boundary dissolved into one
    (multi)polygon, axis-swapped to (lon, lat), self-healed and buffered by the
    border tolerance. Cached -- prepared covers() is microseconds per pin."""
    fc = json.loads(BOUNDARY_GEOJSON.read_text(encoding="utf-8"))
    geoms = [_swap_xy(shape(f["geometry"])) for f in fc["features"]]
    union = unary_union(geoms)
    # buffer(0) heals any self-intersections from the swap/dissolve; the second
    # buffer expands by the border tolerance.
    union = union.buffer(0).buffer(BORDER_TOLERANCE_DEG)
    return union, prep(union)


def in_jharkhand(lon: float, lat: float) -> bool:
    """True iff (lon, lat) is inside the dissolved Jharkhand boundary (+tolerance).
    covers() (not contains()) so a pin exactly on the border passes."""
    _, pg = _boundary()
    return bool(pg.covers(Point(float(lon), float(lat))))


@functools.lru_cache(maxsize=4)
def boundary_geojson(simplify_deg: float = 0.005) -> dict:
    """Simplified boundary as a GeoJSON geometry (lon/lat) for the map overlay
    and the client-side inverse mask. Read-only -- do not mutate the result."""
    union, _ = _boundary()
    simp = union.simplify(simplify_deg) if simplify_deg > 0 else union
    return mapping(simp)


if __name__ == "__main__":
    union, _ = _boundary()
    print(f"[boundary] dissolved bounds (lon,lat) = "
          f"{tuple(round(v, 3) for v in union.bounds)}")
    for name, lon, lat in [("Ranchi", 85.33, 23.36), ("Jaduguda", 86.35, 22.65),
                           ("Patna(Bihar)", 85.14, 25.61),
                           ("Kolkata(WB)", 88.36, 22.57),
                           ("2km across border", 83.31, 23.60)]:
        print(f"  {name:20s} inside={in_jharkhand(lon, lat)}")
