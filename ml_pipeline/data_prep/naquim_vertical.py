"""
ml_pipeline.data_prep.naquim_vertical  (Phase-2 D3 -- per-district vertical model)
=================================================================================
Replaces the single state-wide `VERTICAL["layer1_base_m"] = 30 m` in the shallow-
aquifer screening (Module 5A) with a per-district value read from the CGWB NAQUIM
district reports, plus the fractured-aquifer depth range and confinement note.

  * naquim_vertical.csv (curated, in Datasets/naquim_reference/) holds one row per
    district for which a NAQUIM report exists. Numbers were extracted from the
    reports at the pages logged in NAQUIM_extraction_tracker.md and hand-curated
    (auto-regex leads were verified against the source prose, never blindly
    trusted). The Singhbhum ore belt uses the higher-confidence web-sourced
    values (the E-Singhbhum NAQUIM PDF was a broken download -- see the tracker).
  * district_at(lon, lat) resolves the pin to one of the 24 districts by point-in-
    polygon on District_Boundary_JH.geojson (same [lat,lon] axis-swap as boundary).
  * vertical_params_at(lon, lat) -> {layer1_base_m, fracture depth range, confined,
    district, source, confidence}. Districts with no report fall back to the
    state-wide VERTICAL default, flagged confidence="default".

layer1_base_m = representative base of the shallow (weathered / Aquifer-I) zone --
the depth where dug wells and shallow handpumps draw and below which the semi-
confining fractured Layer-2 begins. A shallower base is the more conservative
(less separation from the ore) screening choice.
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

from shapely.geometry import shape, Point
from shapely.ops import transform

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
DISTRICT_GEOJSON = REPO_ROOT / "Datasets" / "District_Boundary_JH.geojson"
NAQUIM_CSV = REPO_ROOT / "Datasets" / "naquim_reference" / "naquim_vertical.csv"

DEFAULT_LAYER1_BASE_M = float(P.VERTICAL["layer1_base_m"])   # 30 m state-wide fallback


def _swap_xy(geom):
    """District_Boundary_JH.geojson stores [lat, lon] -> swap to [lon, lat]."""
    return transform(lambda x, y, z=None: (y, x), geom)


@functools.lru_cache(maxsize=1)
def _districts():
    """List of (district_name, polygon) in (lon, lat), healed."""
    import json
    fc = json.loads(DISTRICT_GEOJSON.read_text(encoding="utf-8"))
    out = []
    for f in fc["features"]:
        name = str(f["properties"].get("District", "")).strip()
        geom = _swap_xy(shape(f["geometry"])).buffer(0)
        out.append((name, geom))
    return out


def district_at(lon: float, lat: float) -> str | None:
    """District containing the pin; if none covers it (just outside the border),
    the nearest district by polygon distance. None only if the geojson is empty."""
    p = Point(float(lon), float(lat))
    nearest, best = None, float("inf")
    for name, geom in _districts():
        if geom.covers(p):
            return name
        d = geom.distance(p)
        if d < best:
            nearest, best = name, d
    return nearest


@functools.lru_cache(maxsize=1)
def load_naquim_vertical() -> dict:
    """district(lower) -> row dict from naquim_vertical.csv. Empty if absent."""
    if not NAQUIM_CSV.exists():
        return {}
    rows = {}
    with open(NAQUIM_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = r["district"].strip().lower()
            rows[key] = r
    return rows


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def vertical_params_at(lon: float, lat: float) -> dict:
    """Per-district vertical parameters for the shallow-impact screening, with a
    state-wide fallback. `layer1_base_m` is always a valid float."""
    district = district_at(lon, lat)
    table = load_naquim_vertical()
    row = table.get((district or "").lower())
    if row is None:
        return {
            "district": district,
            "layer1_base_m": DEFAULT_LAYER1_BASE_M,
            "fracture_min_m": None, "fracture_max_m": None,
            "aq2_confined": None, "source": "state-wide default (no NAQUIM report)",
            "confidence": "default",
        }
    lb = _to_float(row.get("layer1_base_m"))
    return {
        "district": district,
        "layer1_base_m": lb if lb is not None else DEFAULT_LAYER1_BASE_M,
        "fracture_min_m": _to_float(row.get("fracture_min_m")),
        "fracture_max_m": _to_float(row.get("fracture_max_m")),
        "aq2_confined": row.get("aq2_confined") or None,
        "source": row.get("source") or "NAQUIM",
        "confidence": row.get("confidence") or "med",
    }


if __name__ == "__main__":
    print(f"districts loaded: {len(_districts())} | csv rows: {len(load_naquim_vertical())}")
    for name, lon, lat in [("Jaduguda", 86.347, 22.652), ("Ranchi", 85.33, 23.36),
                           ("Dhanbad", 86.43, 23.80), ("Deoghar", 86.70, 24.48),
                           ("Chatra", 84.87, 24.20)]:
        print(f"  {name:10s} -> {vertical_params_at(lon, lat)}")
