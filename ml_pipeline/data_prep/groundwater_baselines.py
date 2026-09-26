"""
ml_pipeline.data_prep.groundwater_baselines
===========================================
Measured uranium and Ra-226 backgrounds around the Singhbhum mines, served as
one continuous field.  [grounding pass 2026-09-26, LIMITATIONS.md 1k]

WHY THIS EXISTS. Two background numbers the engine served were not measurements
where it mattered most:
  * RADIUM -- one constant for the whole state, 23 mBq/L (Jaduguda's regional
    average), because CGWB does not measure radium.
  * URANIUM -- the nearest CGWB well's value, but the well nearest EVERY one of
    the seven deposits has no uranium measurement, so every deposit pin fell
    through to an unsourced default of 1.0 ug/L.
BARC has surveyed village wells around each mining area, and a regional survey
covers East Singhbhum and Saraikela-Kharsawan. Those studies are tabulated, one
row per study x area x species, in
    Datasets/singhbhum_groundwater_radionuclide_baselines.csv
with the SERVED row per area and species marked by a stated rule (a robust
central statistic -- median or geometric mean -- over an arithmetic mean, then
the larger sample). Rows that were not served stay in the file with the reason:
the two BARC surveys of the Turamdih ground disagree by 2x on radium, and that
disagreement is data, not something to average away silently.

THE FIELD. Each served mining-area value sits at the centre of its deposits
(Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv). A pin gets the
inverse-distance-squared blend of those values with a far-field ANCHOR whose
weight equals a single survey's at P.BASELINE_SURVEY_BLEND_KM:

    Cb = (sum_i v_i / d_i^2  +  A / R^2) / (sum_i 1 / d_i^2  +  1 / R^2)

  anchor A  uranium -> the nearest CGWB well when it measured uranium, else the
                       CGWB statewide median (P.BACKGROUND_DEFAULTS)
            radium  -> the regional survey (P.RADIUM_BACKGROUND_MBQ_L, pinned to
                       the CSV's served regional row by the test suite)

At a mining area it returns that area's own survey value; far away, the anchor;
in between it is continuous. Every value is returned with its provenance so the
UI can say which study it came from and when it is borrowed.
"""
from __future__ import annotations

import csv
import functools
import math
from pathlib import Path

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_CSV = REPO_ROOT / "Datasets" / "singhbhum_groundwater_radionuclide_baselines.csv"
REGIONAL_AREA = "singhbhum_regional"
SURVEYED_SPECIES = ("uranium_ppb", "radium_226_mbq_l")
#: The regional survey sampled these two districts; outside them its radium GM
#: is borrowed and the provenance says so. Spellings as the CGWB water-quality
#: file and the NAQUIM tables write them.
REGIONAL_DISTRICTS = frozenset({"e. singhbhum", "east singhbhum", "east singhbum",
                                "purbi singhbhum", "saraikela", "seraikela",
                                "saraikela-kharsawan", "seraikela-kharsawan"})
_KM_PER_DEG = 111.0
_MIN_DIST_KM = 0.05          # inside the centre: the area's own value, ~exactly


@functools.lru_cache(maxsize=1)
def load_rows() -> tuple[dict, ...]:
    """Every study row, as read (values left as strings except where parsed)."""
    with BASELINE_CSV.open(encoding="utf-8") as fh:
        return tuple(dict(r) for r in csv.DictReader(fh))


@functools.lru_cache(maxsize=1)
def _deposit_centres() -> dict[str, tuple[float, float]]:
    from ml_pipeline.data_prep.ore_loader import ORE_CSV
    out = {}
    with ORE_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r["name"].strip() == P.ORE_BELT_NAME:
                continue
            try:
                out[r["name"].strip()] = (float(r["center_lon"]), float(r["center_lat"]))
            except (TypeError, ValueError):
                continue
    return out


def _row(r: dict, lon: float | None, lat: float | None) -> dict:
    return {"area": r["area"], "deposits": [d for d in r["deposits"].split(";") if d],
            "value": float(r["value"]), "statistic": r["statistic"],
            "n_samples": int(r["n_samples"]) if r["n_samples"] else None,
            "range": [float(r["range_lo"]) if r["range_lo"] else None,
                      float(r["range_hi"]) if r["range_hi"] else None],
            "period": r["period"], "citation": r["citation"],
            "doi": r["doi"] or None, "lon": lon, "lat": lat}


@functools.lru_cache(maxsize=1)
def served_surveys() -> dict[str, list[dict]]:
    """species -> the served MINING-AREA rows, each placed at its deposits' centre."""
    centres = _deposit_centres()
    out: dict[str, list[dict]] = {sp: [] for sp in SURVEYED_SPECIES}
    for r in load_rows():
        if r["served"] != "yes" or r["area"] == REGIONAL_AREA:
            continue
        deps = [d for d in r["deposits"].split(";") if d in centres]
        if not deps:
            raise ValueError(f"baseline area {r['area']} names no known deposit")
        lon = sum(centres[d][0] for d in deps) / len(deps)
        lat = sum(centres[d][1] for d in deps) / len(deps)
        out[r["species"]].append(_row(r, lon, lat))
    return out


@functools.lru_cache(maxsize=1)
def regional_survey() -> dict[str, dict]:
    """species -> the regional survey row (served or not)."""
    return {r["species"]: _row(r, None, None) for r in load_rows()
            if r["area"] == REGIONAL_AREA and r["value"]}


def background_for(species: str, lon: float, lat: float, *,
                   nearest_value: float | None, nearest_km: float | None,
                   district: str | None) -> tuple[float, dict]:
    """(served background, provenance) for one species at a pin -- THE rule.

    Called by the serve path (dashboard/resolve.py) and by the training
    generator (synthetic/generate.py) so the two cannot disagree about what a
    background is -- the mirrored-site divergence this project keeps auditing
    for. `nearest_value` is the nearest CGWB well's measurement (None/NaN when
    that well did not measure the species).
    """
    measured = nearest_value is not None and nearest_value == nearest_value
    if species == "radium_226_mbq_l":
        reg = regional_survey().get(species, {})
        anchor = float(P.RADIUM_BACKGROUND_MBQ_L)
        source = (f"regional survey GM ({reg.get('citation', 'Molla et al. 2025')}); "
                  "CGWB does not measure radium")
    elif measured:
        anchor = float(nearest_value)
        source = ("nearest CGWB well"
                  + (f", {nearest_km:.1f} km" if nearest_km is not None else ""))
    else:
        anchor = P.background_default_for(species)
        source = ("CGWB statewide median (342 wells) -- the nearest CGWB well did "
                  "not measure uranium" if species == "uranium_ppb"
                  else "config default -- the nearest CGWB well has no value")
    if species not in SURVEYED_SPECIES:
        return anchor, {"value": anchor, "method": "nearest CGWB well",
                        "dominant": {"area": "anchor", "citation": source},
                        "anchor": {"value": anchor, "source": source},
                        "surveys": []}
    prov = survey_background(species, lon, lat, anchor_value=anchor,
                             anchor_source=source, district=district)
    return prov["value"], prov


def _km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    kx = _KM_PER_DEG * math.cos(math.radians(0.5 * (lat1 + lat2)))
    return math.hypot((lon1 - lon2) * kx, (lat1 - lat2) * _KM_PER_DEG)


def survey_background(species: str, lon: float, lat: float, *,
                      anchor_value: float, anchor_source: str,
                      district: str | None = None) -> dict:
    """The blended background for `species` at a pin, with its provenance.

    `anchor_value` / `anchor_source` are the far-field value and where it came
    from -- the caller owns that choice (resolve.py and the training generator
    make it identically). Species with no survey return the anchor unchanged.
    """
    areas = served_surveys().get(species, [])
    R = float(P.BASELINE_SURVEY_BLEND_KM)
    w_anchor = 1.0 / (R * R)
    num, den = float(anchor_value) * w_anchor, w_anchor
    parts = []
    for a in areas:
        d = max(_km(lon, lat, a["lon"], a["lat"]), _MIN_DIST_KM)
        w = 1.0 / (d * d)
        num += a["value"] * w
        den += w
        parts.append((a, d, w))
    value = num / den
    contributions = sorted(
        ({"area": a["area"], "value": a["value"], "statistic": a["statistic"],
          "distance_km": round(d, 2), "weight_share": round(w / den, 3),
          "citation": a["citation"], "doi": a["doi"]} for a, d, w in parts),
        key=lambda c: -c["weight_share"])
    anchor_share = w_anchor / den
    dominant = (contributions[0] if contributions
                and contributions[0]["weight_share"] >= anchor_share else None)
    borrowed = (species == "radium_226_mbq_l" and district is not None
                and district.strip().lower() not in REGIONAL_DISTRICTS)
    return {
        "value": float(value),
        "method": ("inverse-distance-squared blend of mining-area surveys with a "
                   f"far-field anchor weighted as one survey at {R:g} km"),
        "dominant": (dominant or {"area": "anchor", "citation": anchor_source,
                                  "weight_share": round(anchor_share, 3)}),
        "anchor": {"value": round(float(anchor_value), 4), "source": anchor_source,
                   "weight_share": round(anchor_share, 3),
                   "borrowed_outside_survey_districts": bool(borrowed)},
        "surveys": [c for c in contributions if c["weight_share"] >= 0.001],
    }
