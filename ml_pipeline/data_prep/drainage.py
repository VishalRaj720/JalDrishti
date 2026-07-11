"""
ml_pipeline.data_prep.drainage  (Stage-B squeeze -- OFFLINE ANALYSIS ONLY)
=========================================================================
Derive a major-stream network from the GLO-30 DEM (priority-flood fill + D8 flow
accumulation) to quantify how far a pin is from perennial drainage -- context for
the fact that the analytical plume's UNBOUNDED down-gradient geometry overstates
far-field reach (a real plume discharges to surface water once it meets a river).

STATUS 2026-07-09: NOT WIRED PER-PIN, and SUPERSEDED for per-pin distance by
data_prep.rivers (HydroRIVERS v1.0, added Stage B2). Validated against known river
towns, this DEM D8 network's per-cell channel placement was unreliable (Jamshedpur,
on the Subarnarekha, came out 8-12 km from the modelled channel; the upland Ranchi
plateau came out CLOSER than Jamshedpur -- inverted). Coarse D8 on a smoothed DEM
wanders channels by several km. It is kept as (a) the offline analysis that
established the state-wide drainage-density statistic below and (b) an independent
cross-check that HydroRIVERS reaches coincide with DEM valley bottoms.

What it DID establish and what IS used: the state-wide drainage-density statistic
-- with a >=120 km2 contributing-area threshold, distance-to-drainage has median
~6 km and P90 ~13 km across Jharkhand. The dashboard uses THAT robust statistic
(config P.FARFIELD_DRAINAGE_MEDIAN_KM) to fire a qualitative FAR-FIELD reach note,
not a fabricated per-pin distance. `drainage_distance_at` is kept for the day a
real river dataset (WRIS/NRSC hydrography) is added; until then it returns None
(no artifact committed).

METHOD (standard hillslope hydrology, no external hydro library)
  1. Decimate the DEM to ~DEM_TARGET_KM cells, minimal smoothing.
  2. Priority-flood depression fill (Barnes et al. 2014, heap variant).
  3. D8 steepest-descent receiver per cell on the filled surface.
  4. Flow accumulation in DECREASING filled-elevation order (valid topological
     order on a depression-free surface).
  5. Threshold accumulation (>= DRAIN_AREA_KM2) -> drainage mask; EDT -> distance.
Build (analysis/PNG only): myvenv/Scripts/python.exe -m ml_pipeline.data_prep.drainage
"""
from __future__ import annotations

import functools
import heapq
import json
import math
from pathlib import Path

import numpy as np

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
DEM_TIF = REPO_ROOT / "Datasets" / "jharkhand_glo30_dem.tif"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
DRAIN_NPZ = ARTIFACT_DIR / "drainage_field.npz"
DRAIN_META = ARTIFACT_DIR / "drainage_field_meta.json"

M_PER_DEG = 111_320.0
GRID_KM = 5.0             # output grid: identical to flow_field / strike_field
DEM_TARGET_KM = 1.0       # drainage is derived at this resolution
DEM_SMOOTH_KM = 1.0       # minimal smoothing -- over-smoothing SHIFTS channels off
                          # the real valley and inflates distance-to-river
DRAIN_AREA_KM2 = 120.0    # contributing area for a cell to count as major drainage


# --------------------------------------------------------------------------- #
# DEM grid
# --------------------------------------------------------------------------- #
def _load_dem_grid(target_km: float):
    """Decimated, lightly smoothed elevation + cell-centre lon/lat + cell size."""
    import rasterio
    from rasterio.enums import Resampling
    from scipy.ndimage import gaussian_filter
    with rasterio.open(DEM_TIF) as d:
        deci = max(1, int(round(target_km * 1000.0 / (d.res[0] * M_PER_DEG))))
        H2, W2 = d.height // deci, d.width // deci
        arr = d.read(1, out_shape=(H2, W2), resampling=Resampling.average).astype(float)
        left, top = d.bounds.left, d.bounds.top
        dlon = (d.bounds.right - d.bounds.left) / W2
        dlat = (d.bounds.top - d.bounds.bottom) / H2
    arr[(arr < -100) | (arr > 3000)] = np.nan
    arr = np.where(np.isfinite(arr), arr, np.nanmax(arr[np.isfinite(arr)]))
    arr = gaussian_filter(arr, sigma=DEM_SMOOTH_KM / target_km)
    lat_c = top - (np.arange(H2) + 0.5) * dlat      # rows: north -> south
    lon_c = left + (np.arange(W2) + 0.5) * dlon
    return arr, lon_c, lat_c, dlat, dlon


# --------------------------------------------------------------------------- #
# Priority-flood depression fill
# --------------------------------------------------------------------------- #
def _priority_flood(dem: np.ndarray) -> np.ndarray:
    H, W = dem.shape
    filled = dem.copy()
    seen = np.zeros((H, W), dtype=bool)
    heap = []
    for i in range(H):
        for j in (0, W - 1):
            heapq.heappush(heap, (dem[i, j], i, j)); seen[i, j] = True
    for j in range(W):
        for i in (0, H - 1):
            if not seen[i, j]:
                heapq.heappush(heap, (dem[i, j], i, j)); seen[i, j] = True
    nbrs = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
    while heap:
        e, i, j = heapq.heappop(heap)
        for di, dj in nbrs:
            ni, nj = i + di, j + dj
            if 0 <= ni < H and 0 <= nj < W and not seen[ni, nj]:
                seen[ni, nj] = True
                ne = dem[ni, nj] if dem[ni, nj] > e else e     # raise to spill level
                filled[ni, nj] = ne
                heapq.heappush(heap, (ne, ni, nj))
    return filled


# --------------------------------------------------------------------------- #
# D8 flow accumulation on the filled surface
# --------------------------------------------------------------------------- #
def _flow_accumulation(filled: np.ndarray, cell_km: float) -> np.ndarray:
    """Contributing-area (km^2) per cell via D8 steepest descent, processed in
    decreasing filled-elevation order (valid topological order, no depressions)."""
    H, W = filled.shape
    nbrs = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
    dd = (1.0, 1.0, 1.0, 1.0, math.sqrt(2), math.sqrt(2), math.sqrt(2), math.sqrt(2))
    rx = np.full((H, W), -1, dtype=np.int64)          # receiver flat index (-1 = outlet)
    for i in range(H):
        fi = filled[i]
        for j in range(W):
            e = fi[j]; best_s = 0.0; best = -1
            for (di, dj), dk in zip(nbrs, dd):
                ni, nj = i + di, j + dj
                if 0 <= ni < H and 0 <= nj < W:
                    s = (e - filled[ni, nj]) / dk
                    if s > best_s:
                        best_s = s; best = ni * W + nj
            rx[i, j] = best
    acc = np.full(H * W, cell_km * cell_km, dtype=float)   # each cell = its own area
    order = np.argsort(filled, axis=None)[::-1]            # high -> low
    rxf = rx.ravel()
    for idx in order:
        r = rxf[idx]
        if r >= 0:
            acc[r] += acc[idx]
    return acc.reshape(H, W)


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def build_drainage_field() -> dict:
    from scipy.ndimage import distance_transform_edt
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    dem, dlon_c, dlat_c, dlat, dlon = _load_dem_grid(DEM_TARGET_KM)
    filled = _priority_flood(dem)
    acc = _flow_accumulation(filled, DEM_TARGET_KM)
    drainage = acc >= DRAIN_AREA_KM2

    # Euclidean distance (in DEM cells) to the nearest drainage cell -> km
    if drainage.any():
        dist_cells = distance_transform_edt(~drainage)
    else:
        dist_cells = np.full(dem.shape, np.inf)
    dist_km = dist_cells * DEM_TARGET_KM

    # sample onto the 5 km flow-field grid (nearest DEM cell per grid centre)
    B = P.JHARKHAND_BOUNDS
    glat = GRID_KM * 1000.0 / M_PER_DEG
    mid_lat = 0.5 * (B["lat_min"] + B["lat_max"])
    glon = GRID_KM * 1000.0 / (M_PER_DEG * np.cos(np.radians(mid_lat)))
    lat_c = np.arange(B["lat_min"], B["lat_max"] + glat, glat)
    lon_c = np.arange(B["lon_min"], B["lon_max"] + glon, glon)
    dist_grid = np.empty((len(lat_c), len(lon_c)))
    for j, la in enumerate(lat_c):
        rr = int(np.abs(dlat_c - la).argmin())
        for i, lo in enumerate(lon_c):
            cc = int(np.abs(dlon_c - lo).argmin())
            dist_grid[j, i] = dist_km[rr, cc]

    np.savez_compressed(DRAIN_NPZ, lon_c=lon_c, lat_c=lat_c,
                        distance_km=dist_grid)
    meta = {
        "grid_km": GRID_KM, "dem_target_km": DEM_TARGET_KM,
        "drain_area_km2": DRAIN_AREA_KM2, "grid_shape": list(dist_grid.shape),
        "drainage_cell_fraction": round(float(drainage.mean()), 4),
        "distance_km_pctiles": [round(float(np.percentile(dist_grid, q)), 1)
                                for q in (10, 50, 90)],
    }
    DRAIN_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    # stash for optional PNG
    build_drainage_field._debug = (dem, drainage, dlon_c, dlat_c)   # type: ignore
    return meta


# --------------------------------------------------------------------------- #
# Runtime
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def load_drainage_field() -> dict:
    z = np.load(DRAIN_NPZ)
    return {k: z[k] for k in z.files}


def drainage_distance_at(lon: float, lat: float) -> float | None:
    """Bilinear distance (km) from the pin to the nearest major drainage, or None
    if the field is unavailable."""
    if not DRAIN_NPZ.exists():
        return None
    df = load_drainage_field()
    lon_c, lat_c = df["lon_c"], df["lat_c"]
    lon = float(np.clip(lon, lon_c[0], lon_c[-1]))
    lat = float(np.clip(lat, lat_c[0], lat_c[-1]))
    i = int(np.clip(np.searchsorted(lon_c, lon) - 1, 0, len(lon_c) - 2))
    j = int(np.clip(np.searchsorted(lat_c, lat) - 1, 0, len(lat_c) - 2))
    tx = (lon - lon_c[i]) / (lon_c[i + 1] - lon_c[i])
    ty = (lat - lat_c[j]) / (lat_c[j + 1] - lat_c[j])
    D = df["distance_km"]
    val = ((D[j, i] * (1 - tx) + D[j, i + 1] * tx) * (1 - ty)
           + (D[j + 1, i] * (1 - tx) + D[j + 1, i + 1] * tx) * ty)
    return round(float(val), 2)


def _render_png():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    dbg = getattr(build_drainage_field, "_debug", None)
    if dbg is None:
        return
    dem, drainage, dlon_c, dlat_c = dbg
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(dem, extent=[dlon_c[0], dlon_c[-1], dlat_c[-1], dlat_c[0]],
              cmap="terrain", origin="upper", alpha=0.7)
    yy, xx = np.where(drainage)
    ax.scatter(dlon_c[xx], dlat_c[yy], s=0.4, c="navy")
    ax.set_title("Derived major drainage (>= %d km2 contributing area)" % DRAIN_AREA_KM2)
    ax.set_xlabel("lon"); ax.set_ylabel("lat"); ax.set_aspect("equal")
    fig.savefig(ARTIFACT_DIR / "drainage_field.png", dpi=110, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    print("building drainage field (reads DEM)...")
    meta = build_drainage_field()
    print(json.dumps(meta, indent=2))
    _render_png()
    print("\nvalidation -- distance to major drainage at known river towns:")
    for name, lon, lat in [("Jamshedpur/Subarnarekha", 86.20, 22.80),
                           ("Dhanbad/Damodar", 86.43, 23.80),
                           ("Ranchi (upland)", 85.33, 23.36),
                           ("Chaibasa", 85.80, 22.55)]:
        print(f"  {name:26s} {drainage_distance_at(lon, lat)} km")
    print(f"\nwrote {DRAIN_NPZ} ({DRAIN_NPZ.stat().st_size/1e3:.0f} KB)")
