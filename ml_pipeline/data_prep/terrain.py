"""
ml_pipeline.data_prep.terrain  --  ground surface for the 3-D site block
=======================================================================
2026-09-25. The 3-D site block draws the real ground over the wellfield, so the
depth column (water table, saprolite, fractured rock, ore) hangs from measured
topography rather than a flat plane.

The source is the Copernicus GLO-30 DEM already used by the flow field
(`Datasets/jharkhand_glo30_dem.tif`, 703 MB, gitignored and absent from any
deployment). So the block cannot read it at serve time. This module clips it
ONCE to the uranium belt -- the Singhbhum Thrust Belt envelope from
`ore_loader`, plus a margin -- block-averages it from 1 arc-second (~30 m) to
`FACTOR` x that, and commits the result as a small artifact. Outside that
coverage `terrain_at` returns None and the block says so: uranium ISR is
suppressed outside the ore zones anyway, and a guessed surface would be worse
than an admitted flat one.

Nothing here feeds the transport engine. It is display context only.

Build (needs the DEM on disk):
    python -m ml_pipeline.data_prep.terrain [--dem path/to/jharkhand_glo30_dem.tif]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEM_TIF = REPO_ROOT / "Datasets" / "jharkhand_glo30_dem.tif"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
TERRAIN_NPZ = ARTIFACT_DIR / "belt_terrain.npz"
TERRAIN_META = ARTIFACT_DIR / "belt_terrain_meta.json"

#: Block-average factor over the native 1 arc-second grid: 2 -> ~60 m cells,
#: ~50 samples across a 3 km block.
FACTOR = 2
#: Margin around the belt envelope, so a block centred on its edge is covered.
MARGIN_KM = 4.0
M_PER_DEG = 111_320.0


def build_terrain(dem_tif: Path = DEM_TIF) -> dict:
    """Clip, block-average and save the belt terrain. Returns the metadata."""
    import rasterio
    from rasterio.windows import from_bounds
    from ml_pipeline.data_prep.ore_loader import _ore

    belt = _ore()[1]
    if belt is None:
        raise RuntimeError("no belt envelope in the ore data -- nothing to clip to")
    w, s, e, n = belt[0].bounds
    lat_c = 0.5 * (s + n)
    dlat_m = MARGIN_KM * 1000.0 / M_PER_DEG
    dlon_m = dlat_m / math.cos(math.radians(lat_c))
    w, e, s, n = w - dlon_m, e + dlon_m, s - dlat_m, n + dlat_m
    with rasterio.open(dem_tif) as src:
        win = from_bounds(w, s, e, n, transform=src.transform).round_offsets().round_lengths()
        z = src.read(1, window=win).astype(np.float64)
        tr = src.window_transform(win)
        res_lon, res_lat = src.res
    z[(z < -100) | (z > 3000)] = np.nan               # nodata / sea fill guard
    H, W = (z.shape[0] // FACTOR) * FACTOR, (z.shape[1] // FACTOR) * FACTOR
    blocks = z[:H, :W].reshape(H // FACTOR, FACTOR, W // FACTOR, FACTOR)
    zc = np.nanmean(blocks, axis=(1, 3))
    if np.isnan(zc).any():                            # fill holes from neighbours
        from scipy.ndimage import distance_transform_edt
        idx = distance_transform_edt(np.isnan(zc), return_distances=False,
                                     return_indices=True)
        zc = zc[tuple(idx)]
    elev = np.round(zc).astype(np.int16)
    # cell-centre coordinates of the coarse grid (row 0 = north)
    lon0 = tr.c + res_lon * FACTOR / 2.0
    lat0 = tr.f - res_lat * FACTOR / 2.0
    dlon, dlat = res_lon * FACTOR, res_lat * FACTOR
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(TERRAIN_NPZ, elev=elev,
                        grid=np.array([lon0, lat0, dlon, dlat], dtype=np.float64))
    meta = {
        "source": "Copernicus GLO-30 DEM (Datasets/jharkhand_glo30_dem.tif)",
        "clip": "Singhbhum Thrust Belt envelope (ore_loader) + %.1f km margin" % MARGIN_KM,
        "block_average_factor": FACTOR,
        "cell_deg": [dlon, dlat],
        "cell_m_approx": round(dlat * M_PER_DEG, 1),
        "shape": list(elev.shape),
        "bounds": [w, s, e, n],
        "elev_range_m": [int(elev.min()), int(elev.max())],
        "use": "display context for the 3-D site block only; never a transport input",
    }
    TERRAIN_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


_CACHE: dict | None = None


def _load() -> dict | None:
    global _CACHE
    if _CACHE is None:
        if not TERRAIN_NPZ.exists():
            return None
        z = np.load(TERRAIN_NPZ)
        lon0, lat0, dlon, dlat = (float(v) for v in z["grid"])
        _CACHE = {"elev": z["elev"], "lon0": lon0, "lat0": lat0,
                  "dlon": dlon, "dlat": dlat}
    return _CACHE


def terrain_at(lon: float, lat: float, half_km: float) -> dict | None:
    """The terrain sub-grid of a square block centred on (lon, lat), or None if
    the block is not wholly inside the committed coverage.

    Returns row 0 = north, with the cell-centre lon/lat of the first cell and
    the cell size, so a renderer can place every vertex without guessing.
    """
    T = _load()
    if T is None:
        return None
    dlat_b = half_km * 1000.0 / M_PER_DEG
    dlon_b = dlat_b / math.cos(math.radians(lat))
    H, W = T["elev"].shape
    i0 = int(math.floor((lon - dlon_b - T["lon0"]) / T["dlon"]))
    i1 = int(math.ceil((lon + dlon_b - T["lon0"]) / T["dlon"]))
    j0 = int(math.floor((T["lat0"] - (lat + dlat_b)) / T["dlat"]))
    j1 = int(math.ceil((T["lat0"] - (lat - dlat_b)) / T["dlat"]))
    if i0 < 0 or j0 < 0 or i1 >= W or j1 >= H:
        return None
    sub = T["elev"][j0:j1 + 1, i0:i1 + 1]
    return {"elev_m": sub, "lon_first": T["lon0"] + i0 * T["dlon"],
            "lat_first": T["lat0"] - j0 * T["dlat"],
            "dlon": T["dlon"], "dlat": T["dlat"]}


def elevation_at(lon: float, lat: float) -> float | None:
    """Bilinear ground elevation [m] at a point, or None outside coverage."""
    T = _load()
    if T is None:
        return None
    fx = (lon - T["lon0"]) / T["dlon"]
    fy = (T["lat0"] - lat) / T["dlat"]
    i, j = int(math.floor(fx)), int(math.floor(fy))
    H, W = T["elev"].shape
    if i < 0 or j < 0 or i + 1 >= W or j + 1 >= H:
        return None
    tx, ty = fx - i, fy - j
    E = T["elev"][j:j + 2, i:i + 2].astype(float)
    top = E[0, 0] * (1 - tx) + E[0, 1] * tx
    bot = E[1, 0] * (1 - tx) + E[1, 1] * tx
    return float(top * (1 - ty) + bot * ty)


if __name__ == "__main__":
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Clip the GLO-30 DEM to the uranium belt.")
    ap.add_argument("--dem", type=Path, default=DEM_TIF,
                    help="GLO-30 GeoTIFF (default: Datasets/jharkhand_glo30_dem.tif)")
    a = ap.parse_args()
    if not a.dem.exists():
        sys.exit(f"DEM not found at {a.dem} -- fetch it with fetch_data/fetchDEM.py")
    print(json.dumps(build_terrain(a.dem), indent=2))
    print("wrote", TERRAIN_NPZ, TERRAIN_NPZ.stat().st_size // 1024, "KB")
