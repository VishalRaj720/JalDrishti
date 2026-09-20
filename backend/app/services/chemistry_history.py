"""The multi-year CGWB chemistry record (2000-2021), read from the file (R17).

WHERE IT CAME FROM. The National Water Data Portal (National Water
Informatics Centre, Ministry of Jal Shakti) publishes CGWB's manual
groundwater-quality record per state as open data:
  Ground Water Quality Chemical Parameters CGWB Jharkhand (1961 - 2025) Manual
  https://nwdp.nwic.gov.in/dataset/7bb1e7c7-bcc1-48bb-8bcd-32c19473804a/resource/6f642921-d0ed-4e61-8286-d83fd370c5a9
  accessed 2026-09-20; stored as Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv
(the "1961-2025" of the title is the portal's frame; the Jharkhand rows run
2000-2021 with one row each in 2022 and 2023).

WHAT IT IS AND IS NOT. 1,632 analyses at 366 stations, median three per
station, 318 stations with two or more distinct years -- the temporal
replicates the 2023 file (one sample per well) does not have. It carries pH
and EC at 100 %, bicarbonate, chloride, calcium, magnesium and sodium at
92 %, hardness at 81 %, sulphate at 46 %. It carries NO fluoride, NO nitrate,
NO iron, NO arsenic, NO manganese and two uranium values. So it cannot
support a trend in any health determinand this platform bands or alerts on,
and it is not used for either. What it does support is a per-station
baseline and trend for the general chemistry -- and in particular for the
three NUREG-1569-style excursion indicators (chloride, sulphate, TDS/EC)
whose lack of a temporal baseline LIMITATIONS.md section 3 records as the
blocker for the UCL rules.

HOW IT IS USED. Read-only, computed from the file on request and cached in
process; nothing is written to `water_samples`, no band or alert changes.
Stations are matched to the platform's 2023 wells by name (case-insensitive)
or by being within `MATCH_KM` of a well, and the match kind is reported.
Trends use the same Theil-Sen slope and Mann-Kendall test as the level
record (`groundwater_trends`), with the gates lowered to what an annual
chemistry record can meet and stated in the response: a station needs at
least `MIN_SAMPLES` analyses spanning `MIN_SPAN_YEARS`; below that the
result is `insufficient_data`, never "stable".

QA. The charge balance is formed with potassium assumed zero (the file does
not report it; K is a minor cation, typically 1-3 % of the cation sum here)
and the rows say so. Unlike the 2023 file, this record does NOT balance by
construction -- the independence check reports it -- so here the balance is
a genuine check on the analyses.
"""
from __future__ import annotations

import functools
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.services import hydrochem_qa as hq
from app.services.groundwater_trends import mann_kendall, theil_sen

REPO_ROOT = Path(__file__).resolve().parents[3]
CSV = REPO_ROOT / "Datasets" / "cgwb_gwq_chemical_jharkhand_2000_2021.csv"
WELLS_CSV = REPO_ROOT / "Datasets" / "waterQuality_jharkhand.csv"

SOURCE = {
    "provider": "Central Ground Water Board via the National Water Data Portal (NWIC, MoJS)",
    "title": "Ground Water Quality Chemical Parameters CGWB Jharkhand (1961 - 2025) Manual",
    "url": ("https://nwdp.nwic.gov.in/dataset/7bb1e7c7-bcc1-48bb-8bcd-32c19473804a/"
            "resource/6f642921-d0ed-4e61-8286-d83fd370c5a9"),
    "accessed": "2026-09-20",
    "file": CSV.name,
}

#: file column -> platform column
COLUMNS = {
    "Potential of Hydrogen (pH)": "ph",
    "Electric Conductivity (μS/cm)": "ec_us_cm",
    "Total Dissolved Solids (mg/L)": "tds_mg_l",
    "Carbonate (mg/L)": "carbonate_mg_l",
    "Bicarbonate (mg/L)": "bicarbonate_mg_l",
    "Chloride (mg/L)": "chloride_mg_l",
    "Sulphate (mg/L)": "sulphate_mg_l",
    "Fluoride (mg/L)": "fluoride_mg_l",
    "Total Hardness (mgCaCO3/L)": "total_hardness",
    "Calcium (mg/L)": "calcium_mg_l",
    "Magnesium (mg/L)": "magnesium_mg_l",
    "Sodium (mg/L)": "sodium_mg_l",
    "Potassium (mg/L)": "potassium_mg_l",
    "Uranium(mg/L)": "uranium_mg_l",
    "Iron(mg/L)": "iron_ppm",
    "Arsenic (mg/L)": "arsenic_mg_l",
}
#: Nitrate is reported as N, not NO3 (x4.427); it is empty in this file, so no
#: conversion is applied, and the absence is reported rather than silently
#: mapped to a zero.
NITRATE_N_COLUMN = "Nitrate N (mgN/L)"

#: Determinands trended: the general chemistry, led by the excursion indicators.
TRENDED = ("ec_us_cm", "chloride_mg_l", "sulphate_mg_l", "bicarbonate_mg_l",
           "total_hardness", "sodium_mg_l", "calcium_mg_l", "magnesium_mg_l", "ph")
MIN_SAMPLES = 4
MIN_SPAN_YEARS = 3.0
ALPHA = 0.05
MATCH_KM = 1.0


def _years(ts: pd.Series) -> np.ndarray:
    t0 = ts.min()
    return ((ts - t0).dt.total_seconds() / (365.25 * 86400.0)).to_numpy()


@functools.lru_cache(maxsize=1)
def load() -> pd.DataFrame:
    """The file, parsed: platform column names, a datetime, a station key."""
    if not CSV.exists():
        raise FileNotFoundError(CSV)
    raw = pd.read_csv(CSV, encoding="utf-8-sig")
    df = pd.DataFrame({
        "station": raw["Station"].astype(str).str.strip(),
        "district": raw["District"].astype(str).str.strip().str.title(),
        "block": raw["Block"].astype(str).str.strip().str.title(),
        "latitude": pd.to_numeric(raw["Latitude"], errors="coerce"),
        "longitude": pd.to_numeric(raw["Longitude"], errors="coerce"),
        "sampled_at": pd.to_datetime(raw["Data Acquisition Time"],
                                     format="%d-%m-%Y %H:%M", errors="coerce"),
    })
    for src, dst in COLUMNS.items():
        df[dst] = pd.to_numeric(raw[src], errors="coerce") if src in raw.columns else np.nan
    df["nitrate_n_reported"] = pd.to_numeric(raw.get(NITRATE_N_COLUMN), errors="coerce")
    df = df.dropna(subset=["sampled_at", "latitude", "longitude"])
    df["year"] = df["sampled_at"].dt.year
    df["key"] = df["station"].str.lower()
    return df


@functools.lru_cache(maxsize=1)
def wells() -> pd.DataFrame:
    w = pd.read_csv(WELLS_CSV, encoding="utf-8-sig")
    return pd.DataFrame({"well_name": w["Location"].astype(str).str.strip(),
                         "key": w["Location"].astype(str).str.strip().str.lower(),
                         "district": w["District"].astype(str),
                         "latitude": pd.to_numeric(w["Latitude"], errors="coerce"),
                         "longitude": pd.to_numeric(w["Longitude"], errors="coerce")})


def _km(lat1, lon1, lat2, lon2) -> float:
    dy = (lat2 - lat1) * 111.0
    dx = (lon2 - lon1) * 111.0 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


@functools.lru_cache(maxsize=1)
def station_matches() -> dict[str, dict[str, Any]]:
    """station key -> {well_name, kind: name|proximity|none, distance_km}."""
    df, w = load(), wells()
    out: dict[str, dict[str, Any]] = {}
    by_key = {k: r for k, r in w.groupby("key").first().iterrows()}
    for key, g in df.groupby("key"):
        lat, lon = float(g["latitude"].iloc[0]), float(g["longitude"].iloc[0])
        if key in by_key:
            r = by_key[key]
            out[key] = {"well_name": r["well_name"], "kind": "name",
                        "distance_km": round(_km(lat, lon, r["latitude"], r["longitude"]), 2)}
            continue
        d = np.sqrt(((w["latitude"] - lat) * 111.0) ** 2
                    + ((w["longitude"] - lon) * 111.0 * math.cos(math.radians(lat))) ** 2)
        i = int(d.idxmin())
        if float(d.iloc[i]) <= MATCH_KM:
            out[key] = {"well_name": w.loc[i, "well_name"], "kind": "proximity",
                        "distance_km": round(float(d.iloc[i]), 2)}
        else:
            out[key] = {"well_name": None, "kind": "none",
                        "distance_km": round(float(d.iloc[i]), 2)}
    return out


def _trend(g: pd.DataFrame, col: str) -> dict[str, Any]:
    s = g.dropna(subset=[col]).sort_values("sampled_at")
    n = int(len(s))
    if n == 0:
        return {"status": "not_measured", "n": 0}
    span = float((s["sampled_at"].max() - s["sampled_at"].min()).days / 365.25)
    rec: dict[str, Any] = {"n": n, "span_years": round(span, 1),
                           "first": s["sampled_at"].min().date().isoformat(),
                           "last": s["sampled_at"].max().date().isoformat(),
                           "min": float(s[col].min()), "median": float(s[col].median()),
                           "max": float(s[col].max()), "latest": float(s[col].iloc[-1])}
    if n < MIN_SAMPLES or span < MIN_SPAN_YEARS:
        rec["status"] = "insufficient_data"
        rec["note"] = (f"needs >= {MIN_SAMPLES} analyses over >= {MIN_SPAN_YEARS:g} years; "
                       f"this is a baseline, not a trend")
        return rec
    t = _years(s["sampled_at"])
    y = s[col].to_numpy(dtype=float)
    slope = theil_sen(t, y)
    z, p = mann_kendall(y)
    rec.update({"slope_per_year": round(slope, 4), "mk_z": round(z, 3), "mk_p": round(p, 4),
                "status": ("rising" if (p < ALPHA and slope > 0)
                           else "falling" if (p < ALPHA and slope < 0) else "no_trend")})
    # a baseline mean + sd is what a NUREG-style UCL needs; report it, and
    # say n so a reader can judge it (NUREG prefers >= 8 rounds)
    rec["baseline_mean"] = round(float(y.mean()), 3)
    rec["baseline_sd"] = round(float(y.std(ddof=1)), 3) if n > 1 else None
    rec["ucl_mean_plus_2sd"] = (round(float(y.mean() + 2 * y.std(ddof=1)), 3)
                                if n > 1 else None)
    return rec


def _qa_rows(g: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for _, r in g.iterrows():
        row = {c: (None if pd.isna(r[c]) else float(r[c])) for c in
               ("calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "potassium_mg_l",
                "bicarbonate_mg_l", "carbonate_mg_l", "chloride_mg_l", "sulphate_mg_l",
                "fluoride_mg_l", "ec_us_cm")}
        # potassium is not reported anywhere in the file: assume zero, and say so
        row["potassium_mg_l"] = 0.0 if row["potassium_mg_l"] is None else row["potassium_mg_l"]
        row["nitrate_mg_l"] = None
        q = hq.assess(row)
        q["potassium_assumed_zero"] = True
        out.append(q)
    return out


@functools.lru_cache(maxsize=1)
def summary() -> dict[str, Any]:
    df = load()
    matches = station_matches()
    per_station = []
    for key, g in df.groupby("key"):
        m = matches[key]
        trends = {c: _trend(g, c) for c in TRENDED}
        qa = _qa_rows(g)
        per_station.append({
            "station": g["station"].iloc[0], "district": g["district"].iloc[0],
            "block": g["block"].iloc[0],
            "latitude": float(g["latitude"].iloc[0]), "longitude": float(g["longitude"].iloc[0]),
            "n": int(len(g)), "years": sorted(int(y) for y in g["year"].unique()),
            "match": m, "trends": trends,
            "qa": {"n": len(qa),
                   "balanced": sum(1 for q in qa if q["qa_class"] == "balanced"),
                   "questionable": sum(1 for q in qa if q["qa_class"] == "questionable"),
                   "suspect": sum(1 for q in qa if q["qa_class"] == "suspect"),
                   "incomplete": sum(1 for q in qa if q["qa_class"] == "incomplete")},
        })
    n_st = len(per_station)
    matched = [s for s in per_station if s["match"]["kind"] != "none"]
    two_years = [s for s in per_station if len(s["years"]) >= 2]
    # record-wide QA and its independence
    qa_rows = _qa_rows(df)
    by_class = {c: sum(1 for q in qa_rows if q["qa_class"] == c) for c in hq.CLASSES}
    indep = hq.independence_check([
        {**{k: (None if pd.isna(r[k]) else float(r[k])) for k in
            ("calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "bicarbonate_mg_l",
             "carbonate_mg_l", "chloride_mg_l", "sulphate_mg_l", "fluoride_mg_l")},
         "potassium_mg_l": 0.0, "nitrate_mg_l": None}
        for _, r in df.iterrows()])
    coverage = {c: {"n": int(df[c].notna().sum()), "pct": round(float(df[c].notna().mean() * 100), 1)}
                for c in COLUMNS.values()}
    coverage["nitrate_n"] = {"n": int(df["nitrate_n_reported"].notna().sum()), "pct": 0.0}
    trend_counts = {c: {"rising": 0, "falling": 0, "no_trend": 0, "insufficient_data": 0,
                        "not_measured": 0} for c in TRENDED}
    for s in per_station:
        for c in TRENDED:
            trend_counts[c][s["trends"][c]["status"]] += 1
    return {
        "source": SOURCE,
        "records": int(len(df)), "stations": n_st,
        "years": {"first": int(df["year"].min()), "last": int(df["year"].max()),
                  "rows_per_year": {int(k): int(v) for k, v in df["year"].value_counts().sort_index().items()}},
        "stations_with_2_or_more_years": len(two_years),
        "stations_matched_to_2023_wells": {"total": len(matched),
                                           "by_name": sum(1 for s in matched if s["match"]["kind"] == "name"),
                                           "by_proximity": sum(1 for s in matched if s["match"]["kind"] == "proximity"),
                                           "match_km": MATCH_KM,
                                           "with_2_or_more_years": sum(1 for s in matched if len(s["years"]) >= 2)},
        "coverage": coverage,
        "health_determinands": {
            "fluoride": "not reported", "nitrate": "not reported (column exists as N, empty)",
            "uranium": f"{coverage['uranium_mg_l']['n']} values", "iron": "not reported",
            "arsenic": "not reported", "manganese": "not reported",
            "consequence": ("no trend or baseline for any determinand the citizen band or "
                            "the alert scan judges; measured-quality trend forecasting for "
                            "health remains undemonstrated"),
        },
        "trend_counts": trend_counts,
        "gates": {"min_samples": MIN_SAMPLES, "min_span_years": MIN_SPAN_YEARS, "alpha": ALPHA},
        "qa": {"by_class": by_class, "potassium_assumed_zero": True,
               "independence_check": indep},
        "stations_detail": per_station,
        "what_this_is": (
            "The CGWB multi-year chemistry record for Jharkhand, read from the "
            "open-data file and matched to the platform's 2023 wells. It gives the "
            "general chemistry -- led by the ISR excursion indicators chloride, "
            "sulphate and EC -- a per-station baseline and a Theil-Sen/Mann-Kendall "
            "trend. It carries none of the health determinands the platform bands or "
            "alerts on, and it changes no band and no alert."),
    }


def for_well(well_name: str) -> Optional[dict[str, Any]]:
    """The history behind one 2023 well, if a station matches it."""
    s = summary()
    key = well_name.strip().lower()
    for st in s["stations_detail"]:
        m = st["match"]
        if m["well_name"] and m["well_name"].strip().lower() == key:
            return {k: st[k] for k in ("station", "n", "years", "match", "trends", "qa")}
    return None
