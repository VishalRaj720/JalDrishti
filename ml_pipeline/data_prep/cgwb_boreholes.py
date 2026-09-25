"""
ml_pipeline.data_prep.cgwb_boreholes  --  CGWB exploratory boreholes of the belt
=================================================================================
2026-09-25. The only published record of what lies below the water table near
the Singhbhum uranium deposits: CGWB's exploratory drilling in East Singhbhum,
Saraikela-Kharsawan and the adjoining West Singhbhum blocks. Each borehole
gives its position, depth, the casing set through the weathered overburden,
and the depths (and, where printed, the yields) of the water-bearing zones it
cut; some give a static water level and a pumping-test transmissivity.

Transcribed by hand from the page images (the PDFs' text layers drop blank
cells) into two files:
  Datasets/cgwb_exploratory_wells_singhbhum.csv        one row per borehole
  Datasets/cgwb_exploratory_wells_singhbhum_zones.csv  one row per zone

Sources, cited per row by these keys (page numbers are PDF pages):
  P3   CGWB State Unit Office Ranchi, "Draft report on National Aquifer Mapping
       and Management Plan in East Singhbhum, Saraikela-Kharsawan and parts of
       West-Singhbhum districts (Phase-III)" -- water levels of 2015. Removed
       from cgwb.gov.in; the Internet Archive copy of 2022-07-25 is
       Datasets/naquim_reference/cgwb_naquim_e_singhbhum_saraikela_w_singhbhum_parts.pdf
  ESP  CGWB, Ground Water Information Booklet, East Singhbhum (2013), Table 2:
       exploratory wells as on March 2003 --
       Datasets/naquim_reference/cgwb_east_singhbhum_profile.pdf
  West Singhbhum NAQUIM (2022)  CGWB, Aquifer Maps and Ground Water Management
       Plan, West Singhbhum (August 2022), Annexure II.

Nothing is filled in: a cell the source leaves blank stays blank, a value that
sits between columns is noted and not used, a position that is plainly
misprinted is not placed, and every disagreement between the sources is
written into `note` rather than resolved silently. Zone kinds are CGWB's own
labels: W (water strike in the weathered / fissured zone), F (fracture), G
(granular zone, in the Tertiary sediments). Zone yields are the drilling-time
discharges as printed, not pumping-test rates.

WHAT IT IS NOT. One-time measurements from drilling campaigns (1975-2016),
at sites chosen for water supply, not for the mines. The nearest borehole to a
deposit is ~3 km away (Kudada, from Turamdih). They show what the rock column
is like in this belt; they are not a survey of any wellfield.
"""
from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WELLS_CSV = REPO_ROOT / "Datasets" / "cgwb_exploratory_wells_singhbhum.csv"
ZONES_CSV = REPO_ROOT / "Datasets" / "cgwb_exploratory_wells_singhbhum_zones.csv"
M_PER_DEG = 111_320.0

SOURCES = {
    "P3": ("CGWB, Draft report on National Aquifer Mapping and Management Plan in "
           "East Singhbhum, Saraikela-Kharsawan and parts of West-Singhbhum "
           "districts (Phase-III); Internet Archive copy of cgwb.gov.in, 2022-07-25"),
    "ESP": "CGWB, Ground Water Information Booklet, East Singhbhum (2013), Table 2",
    "WSB": "CGWB, Aquifer Maps and Ground Water Management Plan, West Singhbhum (2022)",
}

_FLOAT = ("lon", "lat", "depth_m", "casing_m", "swl_mbgl", "discharge_lps",
          "drawdown_m", "transmissivity_m2day", "storativity")


def _num(v: str):
    v = (v or "").strip()
    return float(v) if v else None


@lru_cache(maxsize=1)
def load_boreholes() -> tuple[dict, ...]:
    """Every borehole with its zones (top-down). Positions are None where the
    source publishes none or a misprinted one."""
    zones: dict[str, list[dict]] = {}
    with ZONES_CSV.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            zones.setdefault(r["well_id"], []).append({
                "kind": r["kind"], "top_m": _num(r["top_m"]),
                "bottom_m": _num(r["bottom_m"]), "yield_lps": _num(r["yield_lps"]),
                "yield_note": r["yield_note"] or None, "source": r["source"]})
    out = []
    with WELLS_CSV.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            w = {k: (r[k] or None) for k in r}
            for k in _FLOAT:
                w[k] = _num(r[k])
            w["flowing"] = (r["flowing"].strip().lower() == "true")
            w["zones"] = sorted(zones.get(r["well_id"], []), key=lambda z: z["top_m"])
            out.append(w)
    return tuple(out)


def placed() -> list[dict]:
    return [w for w in load_boreholes() if w["lon"] is not None and w["lat"] is not None]


def _km(lon0: float, lat0: float, lon: float, lat: float) -> float:
    dx = (lon - lon0) * M_PER_DEG * math.cos(math.radians(lat0))
    dy = (lat - lat0) * M_PER_DEG
    return math.hypot(dx, dy) / 1000.0


def boreholes_in_box(box: tuple[float, float, float, float]) -> list[dict]:
    """Placed boreholes inside (west, south, east, north)."""
    w_, s_, e_, n_ = box
    return [dict(w) for w in placed() if w_ <= w["lon"] <= e_ and s_ <= w["lat"] <= n_]


def nearest_boreholes(lon: float, lat: float, *, n: int = 5, max_km: float = 15.0,
                      exclude: set[str] | None = None) -> list[dict]:
    """The `n` nearest placed boreholes within `max_km`, each with its distance
    and bearing from the point -- for saying what the nearest measured rock
    column is when none lies inside the block."""
    exclude = exclude or set()
    rows = []
    for w in placed():
        if w["well_id"] in exclude:
            continue
        km = _km(lon, lat, w["lon"], w["lat"])
        if km <= max_km:
            dx = (w["lon"] - lon) * math.cos(math.radians(lat))
            dy = w["lat"] - lat
            rows.append({**w, "km": round(km, 2),
                         "bearing_deg": round(math.degrees(math.atan2(dx, dy)) % 360.0, 0)})
    rows.sort(key=lambda r: r["km"])
    return rows[:n]
