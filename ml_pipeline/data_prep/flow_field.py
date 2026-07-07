"""
ml_pipeline.data_prep.flow_field  (Phase-2 D1 -- data-derived groundwater flow)
==============================================================================
Offline prep that turns the two hydro datasets into a coarse gridded flow field
so the dashboard can DEFAULT the plume's flow direction and hydraulic gradient
from real data instead of a hand-set azimuth slider and a flat i = 0.005.

Product (per ~5 km cell over Jharkhand), saved to artifacts/flow_field.npz:
  * flow_e, flow_n        unit down-gradient flow vector (E, N)  -> azimuth
  * gradient_i            annual-mean hydraulic gradient magnitude [-]
  * seasonal_amp          RELATIVE swing of the GRADIENT across the 4 CGWB
                          campaigns = (max|.| - min|.|)/(2 mean|.|), feeds the
                          generator's existing gradient_seasonal_amp MC widening
  * source                1 = station plane-fit, 0 = smoothed-DEM fallback
  * n_support, fit_r2     confidence telemetry
  * in_jh                 inside the dissolved state boundary

METHOD (each choice deliberate)
  Head:      h = DEM_elevation(station) - depth_to_water   [CGWB currentlevel].
             Groundwater flows down-gradient (from high h to low h).
  Direction: for each cell, a distance-WEIGHTED PLANE FIT h ~ a*E + b*N + c to
             stations within `radius_km` (the standard hydrogeology "gradient
             from three-plus wells"): grad h = (a,b) points UP-gradient, so flow
             = -(a,b). Vector math throughout -- angles are never averaged.
  Seasonal:  the four CGWB campaigns are bucketed Jan{12,1,2} / May{3,4,5} /
             Aug{6,7,8} / Nov{9,10,11}. Per-station per-season MEAN depth first,
             then the ANNUAL mean = mean of the four season means (NOT the mean
             of all readings -- Jan is over-sampled). Seasonal amp is the swing
             of the fitted gradient MAGNITUDE across seasons, because a uniform
             monsoon rise moves every head but barely changes the gradient.
  Fallback:  cells with < `min_stations` nearby take DIRECTION from the heavily
             Gaussian-smoothed DEM (water table is a subdued replica of macro-
             topography in hard rock); magnitude = SUBDUED_FACTOR * topo slope,
             clipped to the operational envelope. Flagged source = 0.

Build (needs the 703 MB DEM + CGWB CSV):
    myvenv/Scripts/python.exe -m ml_pipeline.data_prep.flow_field
Runtime only reads the small .npz (committed) via load_flow_field()/flow_at().
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
CGWB_CSV = REPO_ROOT / "Datasets" / "cgwb_waterlevel_jharkhand.csv"
DEM_TIF = REPO_ROOT / "Datasets" / "jharkhand_glo30_dem.tif"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
FLOW_NPZ = ARTIFACT_DIR / "flow_field.npz"
FLOW_META = ARTIFACT_DIR / "flow_field_meta.json"

M_PER_DEG = 111_320.0
# CGWB campaign buckets (month -> season label)
_SEASON = {12: "Jan", 1: "Jan", 2: "Jan", 3: "May", 4: "May", 5: "May",
           6: "Aug", 7: "Aug", 8: "Aug", 9: "Nov", 10: "Nov", 11: "Nov"}
SEASONS = ("Jan", "May", "Aug", "Nov")

# Build parameters
GRID_KM = 5.0
RADIUS_KM = 25.0          # station search radius per cell
MIN_STATIONS = 5          # below this -> DEM fallback
SIGMA_KM = 12.0           # Gaussian distance weight scale for the plane fit
DEM_SMOOTH_KM = 10.0      # Gaussian smoothing radius for the topo fallback
DEM_TARGET_KM = 2.0       # decimate the 30 m DEM to ~this before smoothing
SUBDUED_FACTOR = 0.5      # water-table gradient ~ this x topographic slope [hard rock]

_GI_LO, _GI_HI = P.OPERATIONAL_RANGES["hydraulic_gradient"]        # (0.0005, 0.02)
_AMP_HI = P.IRREGULARITY["gradient_seasonal_amp"][1]               # 0.40


# --------------------------------------------------------------------------- #
# Station table: per-station per-season mean depth + coords + DEM elevation
# --------------------------------------------------------------------------- #
def _load_stations() -> pd.DataFrame:
    df = pd.read_csv(CGWB_CSV, parse_dates=["date"])
    df = df[(df["currentlevel"] >= 0) & (df["currentlevel"] < 100)].copy()
    df["season"] = df["date"].dt.month.map(_SEASON)
    # per-station coords (median -- a few stations have jittered fixes)
    coords = df.groupby("station_name")[["longitude", "latitude"]].median()
    # per-station per-season mean depth-to-water
    piv = (df.groupby(["station_name", "season"])["currentlevel"].mean()
             .unstack("season").reindex(columns=SEASONS))
    st = coords.join(piv)
    st["depth_annual"] = st[list(SEASONS)].mean(axis=1, skipna=True)  # bias-corrected
    st = st.dropna(subset=["depth_annual"]).reset_index()
    st["dem_elev"] = _sample_dem(st["longitude"].to_numpy(), st["latitude"].to_numpy())
    st = st[np.isfinite(st["dem_elev"])].reset_index(drop=True)
    # heads (m): elevation - depth. Absent seasons stay NaN.
    for s in SEASONS:
        st[f"h_{s}"] = st["dem_elev"] - st[s]
    st["h_annual"] = st["dem_elev"] - st["depth_annual"]
    return st


def _sample_dem(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    import rasterio
    with rasterio.open(DEM_TIF) as d:
        vals = np.array([v[0] for v in d.sample(np.c_[lons, lats])], dtype=float)
    vals[(vals < -100) | (vals > 3000)] = np.nan      # guard nodata / sea fill
    return vals


# --------------------------------------------------------------------------- #
# Weighted plane fit -> gradient vector (increasing head) at a cell
# --------------------------------------------------------------------------- #
def _plane_gradient(lon0, lat0, lons, lats, heads, sigma_m):
    """Distance-weighted LS fit h ~ a*E + b*N + c. Returns (a, b, r2, n) or None.
    (a, b) is grad(h) [m/m], pointing UP-gradient."""
    good = np.isfinite(heads)
    if good.sum() < MIN_STATIONS:
        return None
    lons, lats, heads = lons[good], lats[good], heads[good]
    cos_lat = np.cos(np.radians(lat0))
    E = (lons - lon0) * M_PER_DEG * cos_lat
    N = (lats - lat0) * M_PER_DEG
    d = np.hypot(E, N)
    w = np.exp(-(d / sigma_m) ** 2)
    if w.sum() < 1e-6:
        return None
    A = np.column_stack([E, N, np.ones_like(E)])
    sw = np.sqrt(w)
    Aw, hw = A * sw[:, None], heads * sw
    p, *_ = np.linalg.lstsq(Aw, hw, rcond=None)
    a, b, c = p
    # weighted R^2 (is the plane meaningful, or noise?)
    pred = A @ p
    ss_res = np.sum(w * (heads - pred) ** 2)
    hbar = np.sum(w * heads) / np.sum(w)
    ss_tot = np.sum(w * (heads - hbar) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else 0.0
    return float(a), float(b), float(r2), int(good.sum())


# --------------------------------------------------------------------------- #
# Smoothed-DEM fallback field (direction where stations are too sparse)
# --------------------------------------------------------------------------- #
def _dem_gradient_grid():
    """Return (lon_c, lat_c, gEast, gNorth) of the down-sampled, heavily smoothed
    DEM's elevation gradient [m/m]. gEast/gNorth are d(elev)/dEast, d(elev)/dNorth."""
    import rasterio
    from rasterio.enums import Resampling
    from scipy.ndimage import gaussian_filter
    with rasterio.open(DEM_TIF) as d:
        deci = max(1, int(round(DEM_TARGET_KM * 1000.0 / (d.res[0] * M_PER_DEG))))
        H2, W2 = d.height // deci, d.width // deci
        arr = d.read(1, out_shape=(H2, W2), resampling=Resampling.average).astype(float)
        left, top = d.bounds.left, d.bounds.top
        dlon = (d.bounds.right - d.bounds.left) / W2
        dlat = (d.bounds.top - d.bounds.bottom) / H2
    arr[(arr < -100) | (arr > 3000)] = np.nan
    arr = np.where(np.isfinite(arr), arr, np.nanmean(arr))
    sigma_cells = DEM_SMOOTH_KM / DEM_TARGET_KM
    sm = gaussian_filter(arr, sigma=sigma_cells)
    lat_c = top - (np.arange(H2) + 0.5) * dlat            # rows: north -> south
    lon_c = left + (np.arange(W2) + 0.5) * dlon
    g_row, g_col = np.gradient(sm)                        # per-cell diffs
    spacing_n = dlat * M_PER_DEG                          # m per row
    spacing_e = dlon * M_PER_DEG * np.cos(np.radians(lat_c))[:, None]
    g_north = -g_row / spacing_n                          # rows go south -> flip
    g_east = g_col / spacing_e
    return lon_c, lat_c, g_east, g_north


def _nearest(vec_lon, vec_lat, lon, lat):
    return int(np.abs(vec_lat - lat).argmin()), int(np.abs(vec_lon - lon).argmin())


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_flow_field() -> dict:
    from ml_pipeline.data_prep.boundary import in_jharkhand
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    st = _load_stations()
    lons_s, lats_s = st["longitude"].to_numpy(), st["latitude"].to_numpy()
    h_ann = st["h_annual"].to_numpy()
    h_seas = {s: st[f"h_{s}"].to_numpy() for s in SEASONS}

    B = P.JHARKHAND_BOUNDS
    dlat = GRID_KM * 1000.0 / M_PER_DEG
    mid_lat = 0.5 * (B["lat_min"] + B["lat_max"])
    dlon = GRID_KM * 1000.0 / (M_PER_DEG * np.cos(np.radians(mid_lat)))
    lat_c = np.arange(B["lat_min"], B["lat_max"] + dlat, dlat)
    lon_c = np.arange(B["lon_min"], B["lon_max"] + dlon, dlon)
    H, W = len(lat_c), len(lon_c)

    dem_lon, dem_lat, dem_gE, dem_gN = _dem_gradient_grid()
    sigma_m = SIGMA_KM * 1000.0
    radius_m = RADIUS_KM * 1000.0

    flow_e = np.zeros((H, W)); flow_n = np.zeros((H, W))
    grad_i = np.full((H, W), np.nan); amp = np.zeros((H, W))
    source = np.zeros((H, W), dtype=np.int8); n_sup = np.zeros((H, W), dtype=np.int16)
    fit_r2 = np.full((H, W), np.nan); in_jh = np.zeros((H, W), dtype=bool)
    # median station gradient / amp -> fill value for DEM cells' amp
    station_amps = []

    for j, lat0 in enumerate(lat_c):
        cos_lat = np.cos(np.radians(lat0))
        for i, lon0 in enumerate(lon_c):
            in_jh[j, i] = in_jharkhand(lon0, lat0)
            # candidate stations within radius (cheap metric box then circle)
            dE = (lons_s - lon0) * M_PER_DEG * cos_lat
            dN = (lats_s - lat0) * M_PER_DEG
            near = np.hypot(dE, dN) <= radius_m
            fit = None
            if near.sum() >= MIN_STATIONS:
                fit = _plane_gradient(lon0, lat0, lons_s[near], lats_s[near],
                                      h_ann[near], sigma_m)
            if fit is not None:
                a, b, r2, n = fit
                mag = np.hypot(a, b)
                if mag > 1e-9:
                    flow_e[j, i], flow_n[j, i] = -a / mag, -b / mag   # down-gradient unit
                grad_i[j, i] = mag
                fit_r2[j, i] = r2; n_sup[j, i] = n; source[j, i] = 1
                # seasonal gradient magnitudes
                mags = []
                for s in SEASONS:
                    fs = _plane_gradient(lon0, lat0, lons_s[near], lats_s[near],
                                         h_seas[s][near], sigma_m)
                    if fs is not None:
                        mags.append(np.hypot(fs[0], fs[1]))
                if len(mags) >= 2:
                    mm = np.array(mags)
                    a_amp = (mm.max() - mm.min()) / (2.0 * mm.mean()) if mm.mean() > 1e-12 else 0.0
                    amp[j, i] = a_amp
                    station_amps.append(a_amp)
            else:
                # DEM fallback: direction from smoothed topo, subdued magnitude
                rr, cc = _nearest(dem_lon, dem_lat, lon0, lat0)
                gE, gN = dem_gE[rr, cc], dem_gN[rr, cc]
                tmag = np.hypot(gE, gN)
                if tmag > 1e-12:
                    flow_e[j, i], flow_n[j, i] = -gE / tmag, -gN / tmag
                grad_i[j, i] = tmag * SUBDUED_FACTOR
                source[j, i] = 0

    grad_i = np.clip(np.nan_to_num(grad_i, nan=0.005), _GI_LO, _GI_HI)
    amp = np.clip(amp, 0.0, _AMP_HI)
    # DEM cells inherit the median station seasonal amp (no seasonal head there)
    if station_amps:
        amp[source == 0] = float(np.clip(np.median(station_amps), 0.0, _AMP_HI))

    np.savez_compressed(
        FLOW_NPZ, lon_c=lon_c, lat_c=lat_c, flow_e=flow_e, flow_n=flow_n,
        gradient_i=grad_i, seasonal_amp=amp, source=source, n_support=n_sup,
        fit_r2=fit_r2, in_jh=in_jh)
    meta = {
        "grid_km": GRID_KM, "radius_km": RADIUS_KM, "min_stations": MIN_STATIONS,
        "sigma_km": SIGMA_KM, "dem_smooth_km": DEM_SMOOTH_KM,
        "subdued_factor": SUBDUED_FACTOR, "n_stations": int(len(st)),
        "grid_shape": [H, W],
        "cells_in_jh": int(in_jh.sum()),
        "station_cells": int(((source == 1) & in_jh).sum()),
        "dem_cells": int(((source == 0) & in_jh).sum()),
        "median_fit_r2": float(np.nanmedian(fit_r2[in_jh & (source == 1)])),
        "gradient_i_pctiles": [float(np.percentile(grad_i[in_jh], q)) for q in (10, 50, 90)],
        "seasonal_amp_pctiles": [float(np.percentile(amp[in_jh], q)) for q in (10, 50, 90)],
    }
    FLOW_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


# --------------------------------------------------------------------------- #
# Runtime: load + bilinear sample
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def load_flow_field() -> dict:
    z = np.load(FLOW_NPZ)
    return {k: z[k] for k in z.files}


def flow_at(lon: float, lat: float) -> dict:
    """Bilinear-sampled flow (azimuth, gradient, seasonal amp) at a pin. Azimuth
    is derived from interpolated unit vectors (never from averaging degrees)."""
    ff = load_flow_field()
    lon_c, lat_c = ff["lon_c"], ff["lat_c"]
    lon = float(np.clip(lon, lon_c[0], lon_c[-1]))
    lat = float(np.clip(lat, lat_c[0], lat_c[-1]))
    i = int(np.clip(np.searchsorted(lon_c, lon) - 1, 0, len(lon_c) - 2))
    j = int(np.clip(np.searchsorted(lat_c, lat) - 1, 0, len(lat_c) - 2))
    tx = (lon - lon_c[i]) / (lon_c[i + 1] - lon_c[i])
    ty = (lat - lat_c[j]) / (lat_c[j + 1] - lat_c[j])

    def bilin(A):
        return ((A[j, i] * (1 - tx) + A[j, i + 1] * tx) * (1 - ty)
                + (A[j + 1, i] * (1 - tx) + A[j + 1, i + 1] * tx) * ty)

    fe, fn = bilin(ff["flow_e"]), bilin(ff["flow_n"])
    az = (np.degrees(np.arctan2(fe, fn)) % 360.0) if np.hypot(fe, fn) > 1e-6 else None
    src = int(round(bilin(ff["source"].astype(float))))
    return {
        "azimuth_deg": None if az is None else round(float(az), 1),
        "gradient_i": round(float(bilin(ff["gradient_i"])), 5),
        "seasonal_amp": round(float(bilin(ff["seasonal_amp"])), 3),
        "source": "stations" if src >= 1 else "dem",
    }


def _render_png(ff: dict):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    lon_c, lat_c = ff["lon_c"], ff["lat_c"]
    step = max(1, len(lon_c) // 45)
    LON, LAT = np.meshgrid(lon_c[::step], lat_c[::step])
    U = ff["flow_e"][::step, ::step]; V = ff["flow_n"][::step, ::step]
    src = ff["source"][::step, ::step]; jh = ff["in_jh"][::step, ::step]
    U = np.where(jh, U, np.nan); V = np.where(jh, V, np.nan)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.quiver(LON, LAT, U, V, np.where(src == 1, 0.0, 1.0), cmap="coolwarm",
              scale=40, width=0.003)
    ax.set_title("Groundwater flow direction (blue=station-fit, red=DEM fallback)")
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.set_aspect("equal")
    fig.savefig(ARTIFACT_DIR / "flow_field.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    print("building flow field (reads DEM + CGWB CSV)...")
    meta = build_flow_field()
    print(json.dumps(meta, indent=2))
    ff = load_flow_field()
    _render_png(ff)
    print("\nspot checks:")
    for name, lon, lat in [("Jaduguda", 86.347, 22.652), ("Ranchi", 85.33, 23.36),
                           ("Dhanbad", 86.43, 23.80), ("Jamshedpur", 86.20, 22.80)]:
        print(f"  {name:11s} {flow_at(lon, lat)}")
    print(f"\nwrote {FLOW_NPZ} ({FLOW_NPZ.stat().st_size/1e3:.0f} KB)")
