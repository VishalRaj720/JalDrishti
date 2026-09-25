"""
ml_pipeline.data_prep.flow_direction  --  how well the flow direction is known
==============================================================================
2026-09-25. The flow field (flow_field.py) fits a distance-weighted plane
through CGWB heads around each 5 km cell and keeps the down-gradient direction.
It never kept how SURE that direction is, so the plume was always drawn along a
single bearing. This module measures that uncertainty two independent ways, on
the flow field's own grid, stations, heads and kernel:

  * fit statistics  -- the standard error of the fitted direction from the
                       weighted least-squares covariance of the plane's slope
                       (homoscedastic sandwich with Kish effective sample size),
                       propagated to an angle by the delta method;
  * year-by-year    -- the same plane refitted to each monitoring year's own
                       heads (2013-2021) and the circular standard deviation of
                       those yearly directions.

WHAT EACH ONE MEANS, and why the fan uses the larger of the two estimates of
the SAME thing. A plume travelling for decades follows the LONG-TERM mean
direction; year-to-year wobble mostly averages out along its path rather than
swinging the whole plume. What is uncertain is that long-term direction, and
there are two estimates of how well it is known: the regression standard error,
and the year-to-year scatter divided by sqrt(number of years). They are not
added (that would count one uncertainty twice); the larger is served, and both
are reported.

WHAT IT IS NOT. The plane is fitted over ~25 km. Local hills and streams can
bend flow at the 300 m wellfield scale in ways no regional fit sees, so this is
a LOWER bound on the direction uncertainty at a site. DEM-fallback cells (too
few stations) carry no statistical uncertainty and are reported as None.

Build (needs the DEM, to turn depth-to-water into head at each station):
    python -m ml_pipeline.data_prep.flow_direction [--dem path/to/dem.tif]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from ml_pipeline.data_prep import flow_field as FF

ARTIFACT_DIR = FF.ARTIFACT_DIR
DIR_NPZ = ARTIFACT_DIR / "flow_direction.npz"
DIR_META = ARTIFACT_DIR / "flow_direction_meta.json"
#: a year's plane is fitted only with this many stations in the cell radius --
#: the flow field's own threshold, so a yearly fit is never looser than it
MIN_STATIONS = FF.MIN_STATIONS
#: a station-year counts only with at least this many of the four campaigns,
#: so a year of only monsoon readings cannot pose as an annual head
MIN_SEASONS_PER_YEAR = 2


def plane_fit_with_se(lon0, lat0, lons, lats, heads, sigma_m):
    """The flow field's weighted plane fit, plus the standard error of the
    down-gradient AZIMUTH [deg]. Returns (azimuth_deg, se_deg, n) or None.

    Same kernel and design matrix as `flow_field._plane_gradient`; the slope
    covariance is the homoscedastic sandwich
        Cov(p) = s^2 (A'WA)^-1 (A'W^2 A) (A'WA)^-1,
        s^2    = [sum w r^2 / sum w] * n_eff / (n_eff - 3),  n_eff = (sum w)^2 / sum w^2,
    and theta = atan2(-a, -b) gives, by the delta method,
        Var(theta) = (b^2 Var a + a^2 Var b - 2ab Cov(a,b)) / (a^2 + b^2)^2.
    """
    good = np.isfinite(heads)
    if good.sum() < MIN_STATIONS:
        return None
    lons, lats, heads = lons[good], lats[good], heads[good]
    cos_lat = math.cos(math.radians(lat0))
    E = (lons - lon0) * FF.M_PER_DEG * cos_lat
    N = (lats - lat0) * FF.M_PER_DEG
    w = np.exp(-(np.hypot(E, N) / sigma_m) ** 2)
    if w.sum() < 1e-6:
        return None
    A = np.column_stack([E, N, np.ones_like(E)])
    AtW = A.T * w
    M = AtW @ A
    try:
        Minv = np.linalg.inv(M)
    except np.linalg.LinAlgError:
        return None
    p = Minv @ (AtW @ heads)
    a, b = float(p[0]), float(p[1])
    r = heads - A @ p
    n_eff = w.sum() ** 2 / np.sum(w ** 2)
    if n_eff <= 3.5:
        return None
    s2 = float(np.sum(w * r ** 2) / w.sum()) * n_eff / (n_eff - 3.0)
    cov = s2 * Minv @ ((A.T * w ** 2) @ A) @ Minv
    mag2 = a * a + b * b
    if mag2 < 1e-18:
        return None
    var_t = (b * b * cov[0, 0] + a * a * cov[1, 1] - 2 * a * b * cov[0, 1]) / (mag2 ** 2)
    az = math.degrees(math.atan2(-a, -b)) % 360.0
    se = math.degrees(math.sqrt(max(var_t, 0.0)))
    return az, se, int(good.sum())


def _circ_sd_deg(angles_deg: np.ndarray) -> float:
    """Circular standard deviation sqrt(-2 ln R) [deg] of AXIAL-free angles."""
    th = np.radians(angles_deg)
    R = float(np.hypot(np.mean(np.sin(th)), np.mean(np.cos(th))))
    return float(np.degrees(math.sqrt(max(-2.0 * math.log(max(R, 1e-12)), 0.0))))


def _yearly_heads(st) -> tuple[list[int], np.ndarray]:
    """(years, heads[year, station]): per station per year, the mean of that
    year's campaign means (the flow field's own bias correction), minus depth
    from the station's DEM elevation. NaN where the year has too few campaigns."""
    import pandas as pd
    df = pd.read_csv(FF.CGWB_CSV, parse_dates=["date"])
    df = df[(df["currentlevel"] >= 0) & (df["currentlevel"] < 100)].copy()
    df["season"] = df["date"].dt.month.map(FF._SEASON)
    # Jan readings belong to the monitoring year that began the previous May
    df["myear"] = df["date"].dt.year - (df["date"].dt.month <= 2).astype(int)
    seas = (df.groupby(["station_name", "myear", "season"])["currentlevel"].mean()
              .reset_index())
    agg = seas.groupby(["station_name", "myear"])["currentlevel"].agg(["mean", "count"])
    agg = agg[agg["count"] >= MIN_SEASONS_PER_YEAR]["mean"].unstack("myear")
    years = sorted(int(y) for y in agg.columns)
    idx = {name: k for k, name in enumerate(st["station_name"])}
    H = np.full((len(years), len(st)), np.nan)
    elev = st["dem_elev"].to_numpy()
    for name, row in agg.iterrows():
        k = idx.get(name)
        if k is None:
            continue
        for yi, y in enumerate(years):
            v = row.get(y)
            if v is not None and np.isfinite(v):
                H[yi, k] = elev[k] - float(v)
    return years, H


def build_direction_uncertainty() -> dict:
    ff = FF.load_flow_field()
    lon_c, lat_c = ff["lon_c"], ff["lat_c"]
    source, in_jh = ff["source"], ff["in_jh"]
    st = FF._load_stations()                      # samples FF.DEM_TIF at stations
    lons_s, lats_s = st["longitude"].to_numpy(), st["latitude"].to_numpy()
    h_ann = st["h_annual"].to_numpy()
    years, H_year = _yearly_heads(st)
    sigma_m, radius_m = FF.SIGMA_KM * 1000.0, FF.RADIUS_KM * 1000.0

    Hn, Wn = len(lat_c), len(lon_c)
    se_fit = np.full((Hn, Wn), np.nan)
    year_sd = np.full((Hn, Wn), np.nan)
    n_years = np.zeros((Hn, Wn), dtype=np.int16)
    az_check = np.full((Hn, Wn), np.nan)
    for j, lat0 in enumerate(lat_c):
        cos_lat = math.cos(math.radians(lat0))
        for i, lon0 in enumerate(lon_c):
            if source[j, i] != 1:
                continue
            dcell = np.hypot((lons_s - lon0) * FF.M_PER_DEG * cos_lat,
                             (lats_s - lat0) * FF.M_PER_DEG)
            near = dcell <= radius_m
            fit = plane_fit_with_se(lon0, lat0, lons_s[near], lats_s[near],
                                    h_ann[near], sigma_m)
            if fit is None:
                continue
            az_check[j, i], se_fit[j, i] = fit[0], fit[1]
            az_y = []
            for yi in range(len(years)):
                fy = plane_fit_with_se(lon0, lat0, lons_s[near], lats_s[near],
                                       H_year[yi][near], sigma_m)
                if fy is not None:
                    az_y.append(fy[0])
            if len(az_y) >= 3:
                year_sd[j, i] = _circ_sd_deg(np.array(az_y))
                n_years[j, i] = len(az_y)

    np.savez_compressed(DIR_NPZ, lon_c=lon_c, lat_c=lat_c, se_fit_deg=se_fit,
                        year_sd_deg=year_sd, n_years=n_years, azimuth_deg=az_check)
    sel = in_jh & np.isfinite(se_fit)
    sel_y = in_jh & np.isfinite(year_sd)
    mean_unc = np.maximum(np.nan_to_num(se_fit, nan=0.0),
                          np.nan_to_num(year_sd / np.sqrt(np.maximum(n_years, 1)), nan=0.0))
    meta = {
        "source": "CGWB water levels (Datasets/cgwb_waterlevel_jharkhand.csv) + GLO-30 "
                  "station elevations; flow_field's grid, kernel and radius",
        "years": years,
        "min_seasons_per_station_year": MIN_SEASONS_PER_YEAR,
        "cells_with_fit_se": int(sel.sum()),
        "cells_with_year_sd": int(sel_y.sum()),
        "se_fit_deg_pctiles": [round(float(np.percentile(se_fit[sel], q)), 2) for q in (10, 50, 90)],
        "year_sd_deg_pctiles": [round(float(np.percentile(year_sd[sel_y], q)), 2) for q in (10, 50, 90)],
        "served_sd_deg_pctiles": [round(float(np.percentile(mean_unc[sel], q)), 2) for q in (10, 50, 90)],
        "max_abs_azimuth_diff_vs_flow_field_deg": None,
    }
    # the refit must reproduce the served direction -- same data, same kernel
    fe, fn = ff["flow_e"], ff["flow_n"]
    az_ff = np.degrees(np.arctan2(fe, fn)) % 360.0
    d = np.abs(((az_check - az_ff) + 180.0) % 360.0 - 180.0)
    meta["max_abs_azimuth_diff_vs_flow_field_deg"] = round(float(np.nanmax(d[sel])), 6)
    DIR_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


_CACHE: dict | None = None


def _load() -> dict | None:
    global _CACHE
    if _CACHE is None:
        if not DIR_NPZ.exists():
            return None
        z = np.load(DIR_NPZ)
        _CACHE = {k: z[k] for k in z.files}
    return _CACHE


def direction_uncertainty_at(lon: float, lat: float) -> dict | None:
    """Direction uncertainty at the nearest station-fitted cell, or None where
    the flow direction came from the DEM fallback (no statistics exist)."""
    D = _load()
    if D is None:
        return None
    i = int(np.argmin(np.abs(D["lon_c"] - lon)))
    j = int(np.argmin(np.abs(D["lat_c"] - lat)))
    se = float(D["se_fit_deg"][j, i])
    if not math.isfinite(se):
        return None
    ysd = float(D["year_sd_deg"][j, i])
    ny = int(D["n_years"][j, i])
    of_mean = (ysd / math.sqrt(ny)) if (math.isfinite(ysd) and ny > 0) else None
    served = max(se, of_mean or 0.0)
    return {
        "se_fit_deg": round(se, 2),
        "year_to_year_sd_deg": (round(ysd, 2) if math.isfinite(ysd) else None),
        "n_years": ny,
        "year_sd_of_mean_deg": (None if of_mean is None else round(of_mean, 2)),
        "served_sd_deg": round(served, 2),
        "basis": ("larger of the plane-fit standard error and the year-to-year "
                  "spread / sqrt(years): two estimates of how well the LONG-TERM "
                  "direction is known; a lower bound at wellfield scale"),
    }


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Direction uncertainty of the flow field.")
    ap.add_argument("--dem", type=Path, default=FF.DEM_TIF)
    a = ap.parse_args()
    if not a.dem.exists():
        sys.exit(f"DEM not found at {a.dem}")
    FF.DEM_TIF = a.dem                      # _load_stations samples station elevations
    print(json.dumps(build_direction_uncertainty(), indent=2))
