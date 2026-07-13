"""
ml_pipeline.data_prep.rivers  (Stage-B2 -- perennial-river receptor context)
===========================================================================
Replaces the deferred hand-rolled DEM drainage network (data_prep.drainage, whose
coarse D8 channel placement was unreliable) with the HydroRIVERS v1.0 global
hydrography (hand-corrected, per-reach long-term discharge). Gives the dashboard a
TRUSTWORTHY per-pin "distance to nearest perennial river": when a predicted plume
reach exceeds it, the plume would intercept and discharge to surface water instead
of migrating indefinitely down-gradient. Serve-time CONTEXT only -- never caps or
feeds a label, so the one-retrain discipline is untouched.

PERENNIAL threshold = long-term average discharge DIS_AV_CMS >= 1.0 m3/s: a stream
carrying >= 1 cumec year-round is a genuine baseflow-fed (gaining) stream that
intercepts a groundwater plume. Validated against known rivers (Subarnarekha at
Jamshedpur ~2 km, Damodar ~3 km, Ganga at Sahibganj <1 km) with the Ranchi-plateau
DIVIDE correctly the farthest -- the exact ordering the DEM D8 network inverted.

  * clip_asia_to_jharkhand() -- one-time: read the Asia shapefile within the
    Jharkhand bbox, keep reaches (DIS>=0.5, a margin for re-thresholding) that
    intersect the state boundary buffered outward (border rivers matter -- the
    Ganga IS the north border, the Subarnarekha exits east), simplify, and write
    the committable Datasets/jharkhand_rivers.geojson. The 200 MB Asia shapefile
    stays gitignored.
  * build_river_field() -- per-5 km-cell distance (km) to the nearest PERENNIAL
    reach, on the identical grid as flow_field/strike_field -> artifacts/
    river_field.npz. Distances computed in UTM 45N (metres, accurate).
  * river_distance_at(lon, lat) / rivers_geojson() -- runtime.
Build:  myvenv/Scripts/python.exe -m ml_pipeline.data_prep.rivers
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

import numpy as np

from ml_pipeline.config import parameters as P

REPO_ROOT = Path(__file__).resolve().parents[2]
ASIA_SHP = (REPO_ROOT / "Datasets" / "HydroRIVERS_v10_as_shp"
            / "HydroRIVERS_v10_as_shp" / "HydroRIVERS_v10_as.shp")
RIVERS_GEOJSON = REPO_ROOT / "Datasets" / "jharkhand_rivers.geojson"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
RIVER_NPZ = ARTIFACT_DIR / "river_field.npz"
RIVER_META = ARTIFACT_DIR / "river_field_meta.json"

M_PER_DEG = 111_320.0
GRID_KM = 5.0
UTM_JH = 32645                 # WGS84 / UTM 45N -- metric CRS covering Jharkhand
PERENNIAL_DIS_CMS = 1.0        # long-term mean discharge -> "perennial gaining stream"
CLIP_KEEP_DIS_CMS = 0.5        # kept in the committed geojson (map + re-threshold)
CLIP_BUFFER_DEG = 0.25         # keep reaches this far outside the state border
_KEEP_COLS = ["HYRIV_ID", "MAIN_RIV", "LENGTH_KM", "UPLAND_SKM",
              "DIS_AV_CMS", "ORD_STRA"]


# --------------------------------------------------------------------------- #
# One-time clip: Asia shapefile -> committable Jharkhand geojson
# --------------------------------------------------------------------------- #
def clip_asia_to_jharkhand() -> dict:
    import geopandas as gpd
    import warnings
    warnings.filterwarnings("ignore")
    from ml_pipeline.data_prep.boundary import _boundary

    B = P.JHARKHAND_BOUNDS
    bbox = (B["lon_min"] - 0.3, B["lat_min"] - 0.3,
            B["lon_max"] + 0.3, B["lat_max"] + 0.3)
    gdf = gpd.read_file(ASIA_SHP, bbox=bbox)
    gdf = gdf[gdf["DIS_AV_CMS"] >= CLIP_KEEP_DIS_CMS].copy()
    union, _ = _boundary()
    keep_area = union.buffer(CLIP_BUFFER_DEG)
    gdf = gdf[gdf.intersects(keep_area)].copy()
    gdf["geometry"] = gdf.geometry.simplify(0.001)      # ~100 m, lighten payload
    gdf = gdf[_KEEP_COLS + ["geometry"]]
    RIVERS_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(RIVERS_GEOJSON, driver="GeoJSON")
    return {"reaches": int(len(gdf)),
            "perennial_reaches": int((gdf["DIS_AV_CMS"] >= PERENNIAL_DIS_CMS).sum()),
            "size_kb": round(RIVERS_GEOJSON.stat().st_size / 1e3, 1)}


@functools.lru_cache(maxsize=1)
def load_rivers():
    """Clipped Jharkhand river reaches (GeoDataFrame, EPSG:4326)."""
    import geopandas as gpd
    return gpd.read_file(RIVERS_GEOJSON)


# --------------------------------------------------------------------------- #
# Distance-to-perennial-river field (same 5 km grid as flow_field)
# --------------------------------------------------------------------------- #
def build_river_field() -> dict:
    from shapely import STRtree
    from shapely.geometry import Point
    import pyproj
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rivers = load_rivers()
    perennial = rivers[rivers["DIS_AV_CMS"] >= PERENNIAL_DIS_CMS].to_crs(UTM_JH)
    geoms = perennial.geometry.values
    tree = STRtree(geoms)
    to_utm = pyproj.Transformer.from_crs(4326, UTM_JH, always_xy=True).transform

    B = P.JHARKHAND_BOUNDS
    dlat = GRID_KM * 1000.0 / M_PER_DEG
    mid_lat = 0.5 * (B["lat_min"] + B["lat_max"])
    dlon = GRID_KM * 1000.0 / (M_PER_DEG * np.cos(np.radians(mid_lat)))
    lat_c = np.arange(B["lat_min"], B["lat_max"] + dlat, dlat)
    lon_c = np.arange(B["lon_min"], B["lon_max"] + dlon, dlon)
    dist_km = np.empty((len(lat_c), len(lon_c)))
    for j, la in enumerate(lat_c):
        for i, lo in enumerate(lon_c):
            p = Point(*to_utm(float(lo), float(la)))
            k = int(tree.nearest(p))
            dist_km[j, i] = p.distance(geoms[k]) / 1000.0

    np.savez_compressed(RIVER_NPZ, lon_c=lon_c, lat_c=lat_c, distance_km=dist_km)
    meta = {
        "grid_km": GRID_KM, "perennial_dis_cms": PERENNIAL_DIS_CMS,
        "perennial_reaches": int(len(perennial)),
        "grid_shape": list(dist_km.shape),
        "distance_km_pctiles": [round(float(np.percentile(dist_km, q)), 2)
                                for q in (10, 50, 90)],
    }
    RIVER_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


@functools.lru_cache(maxsize=1)
def load_river_field() -> dict:
    z = np.load(RIVER_NPZ)
    return {k: z[k] for k in z.files}


def river_distance_at(lon: float, lat: float) -> float | None:
    """Bilinear distance (km) from the pin to the nearest perennial river, or None
    if the field artifact is absent."""
    if not RIVER_NPZ.exists():
        return None
    rf = load_river_field()
    lon_c, lat_c = rf["lon_c"], rf["lat_c"]
    lon = float(np.clip(lon, lon_c[0], lon_c[-1]))
    lat = float(np.clip(lat, lat_c[0], lat_c[-1]))
    i = int(np.clip(np.searchsorted(lon_c, lon) - 1, 0, len(lon_c) - 2))
    j = int(np.clip(np.searchsorted(lat_c, lat) - 1, 0, len(lat_c) - 2))
    tx = (lon - lon_c[i]) / (lon_c[i + 1] - lon_c[i])
    ty = (lat - lat_c[j]) / (lat_c[j + 1] - lat_c[j])
    D = rf["distance_km"]
    val = ((D[j, i] * (1 - tx) + D[j, i + 1] * tx) * (1 - ty)
           + (D[j + 1, i] * (1 - tx) + D[j + 1, i + 1] * tx) * ty)
    return round(float(val), 2)


@functools.lru_cache(maxsize=1)
def rivers_geojson() -> dict:
    """Perennial river polylines (GeoJSON) for the map overlay (Stage C)."""
    rivers = load_rivers()
    per = rivers[rivers["DIS_AV_CMS"] >= PERENNIAL_DIS_CMS].copy()
    return json.loads(per.to_json())


@functools.lru_cache(maxsize=1)
def _perennial_wgs84():
    """Perennial reaches (EPSG:4326) + their spatial index, cached."""
    rivers = load_rivers()
    return rivers[rivers["DIS_AV_CMS"] >= PERENNIAL_DIS_CMS].reset_index(drop=True)


def plume_river_discharge(plume_rings_lonlat) -> dict | None:
    """Precise geometric test: does the BIS-breach plume polygon actually CROSS a
    perennial river? (Polish #1 -- replaces the coarse reach>distance heuristic
    when it can.) `plume_rings_lonlat` = list of [[lon,lat], ...] rings. Returns
    the crossing reach's discharge, or None if the plume reaches no river."""
    if not RIVER_NPZ.exists() or not plume_rings_lonlat:
        return None
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = []
    for r in plume_rings_lonlat:
        if not r or len(r) < 4:
            continue
        try:                                   # buffer(0) heals marching-squares
            p = Polygon(r).buffer(0)           # self-intersections into valid geometry
        except Exception:
            continue
        if not p.is_empty:
            polys.append(p)
    if not polys:
        return None
    plume = unary_union(polys)
    per = _perennial_wgs84()
    idx = list(per.sindex.query(plume, predicate="intersects"))
    if not idx:
        return None
    hit = per.iloc[idx]
    return {"intersects": True,
            "n_reaches": int(len(hit)),
            "max_discharge_cms": round(float(hit["DIS_AV_CMS"].max()), 1)}


if __name__ == "__main__":
    if not RIVERS_GEOJSON.exists():
        print("clipping Asia HydroRIVERS -> Jharkhand ...")
        print(json.dumps(clip_asia_to_jharkhand(), indent=2))
    print("building river distance field ...")
    print(json.dumps(build_river_field(), indent=2))
    print("\nvalidation -- distance to nearest perennial river (km):")
    for name, lon, lat in [("Jamshedpur/Subarnarekha", 86.20, 22.80),
                           ("Damodar @ Bermo", 85.99, 23.78),
                           ("Sahibganj/Ganga", 87.64, 25.25),
                           ("Ranchi plateau (divide)", 85.33, 23.36),
                           ("Jaduguda", 86.347, 22.652)]:
        print(f"  {name:26s} {river_distance_at(lon, lat)} km")
    print(f"\nwrote {RIVER_NPZ} ({RIVER_NPZ.stat().st_size/1e3:.0f} KB)")
