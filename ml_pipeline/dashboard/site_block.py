"""
ml_pipeline.dashboard.site_block  --  measured context for the 3-D site block
=============================================================================
2026-09-25. The 3-D block shows the vertical story in place: the ground, the
water table, the rock column, the ore horizon with the plume on it, and the
fronts climbing toward the shallow aquifer. Everything in it is either measured
or an engine output; this module serves the measured part for a square block
around a pin:

  * terrain         -- GLO-30 DEM excerpt (data_prep/terrain.py); None outside
                       the committed belt coverage, and the block says so;
  * wells           -- CGWB monitoring stations inside the block, with their
                       seasonal depth-to-water (the same CSV the flow field and
                       the seasonal vertical band are built from);
  * rivers          -- HydroRIVERS reaches crossing the block (the committed
                       clip keeps mean discharge >= 0.5 m3/s);
  * layers          -- the district's NAQUIM shallow-aquifer base and
                       fractured-zone range (the same `vertical_params_at` the
                       screening uses).

The engine outputs -- plume raster, leach zone, vertical fronts -- come from the
`/api/predict` response of the same run, so the block cannot show a different
answer from the map.
"""
from __future__ import annotations

import base64
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

M_PER_DEG = 111_320.0
REPO_ROOT = Path(__file__).resolve().parents[2]
CGWB_CSV = REPO_ROOT / "Datasets" / "cgwb_waterlevel_jharkhand.csv"
#: CGWB campaign buckets -- identical to data_prep.flow_field._SEASON
_SEASON = {12: "Jan", 1: "Jan", 2: "Jan", 3: "May", 4: "May", 5: "May",
           6: "Aug", 7: "Aug", 8: "Aug", 9: "Nov", 10: "Nov", 11: "Nov"}
_SEASONS = ("Jan", "May", "Aug", "Nov")


@lru_cache(maxsize=1)
def _stations():
    """Per-station median position and per-season mean depth-to-water, with the
    same validity filter and season buckets as the flow field -- but without
    the DEM, which is not present where the API is deployed."""
    import pandas as pd
    df = pd.read_csv(CGWB_CSV, parse_dates=["date"])
    df = df[(df["currentlevel"] >= 0) & (df["currentlevel"] < 100)].copy()
    df["season"] = df["date"].dt.month.map(_SEASON)
    coords = df.groupby("station_name")[["longitude", "latitude"]].median()
    piv = (df.groupby(["station_name", "season"])["currentlevel"].mean()
             .unstack("season").reindex(columns=list(_SEASONS)))
    n = df.groupby("station_name").size().rename("n_readings")
    district = df.groupby("station_name")["district_name"].first()
    years = df.groupby("station_name")["date"].agg(["min", "max"])
    st = coords.join(piv).join(n).join(district).join(years).reset_index()
    return st


def _b64_i16(a: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(a, dtype="<i2").tobytes()).decode("ascii")


def _in_box(lon, lat, box) -> bool:
    w, s, e, n = box
    return w <= lon <= e and s <= lat <= n


def site_block(lon: float, lat: float, half_km: float = 1.5) -> dict:
    from ml_pipeline.data_prep.terrain import terrain_at, elevation_at
    from ml_pipeline.data_prep.naquim_vertical import vertical_params_at
    from ml_pipeline.data_prep.rivers import rivers_geojson

    dlat = half_km * 1000.0 / M_PER_DEG
    dlon = dlat / math.cos(math.radians(lat))
    box = (lon - dlon, lat - dlat, lon + dlon, lat + dlat)

    t = terrain_at(lon, lat, half_km)
    terrain = None
    if t is not None:
        ny, nx = t["elev_m"].shape
        terrain = {"nx": int(nx), "ny": int(ny),
                   "lon_first": t["lon_first"], "lat_first": t["lat_first"],
                   "dlon": t["dlon"], "dlat": t["dlat"],
                   "encoding": "int16 little-endian metres, row 0 = north, base64",
                   "elev_m": _b64_i16(t["elev_m"]),
                   "source": "Copernicus GLO-30 DEM, block-averaged to ~62 m"}

    wells = []
    for r in _stations().itertuples(index=False):
        if not _in_box(r.longitude, r.latitude, box):
            continue
        seas = {s: (None if not np.isfinite(getattr(r, s)) else round(float(getattr(r, s)), 2))
                for s in _SEASONS}
        vals = [v for v in seas.values() if v is not None]
        wells.append({
            "name": r.station_name, "district": r.district_name,
            "lon": round(float(r.longitude), 6), "lat": round(float(r.latitude), 6),
            "ground_m": (None if (g := elevation_at(r.longitude, r.latitude)) is None
                         else round(g, 1)),
            "depth_to_water_m": seas,
            "depth_to_water_range_m": ([min(vals), max(vals)] if vals else None),
            "n_readings": int(r.n_readings),
            "years": [int(r.min.year), int(r.max.year)],
        })

    rivers = []
    for f in rivers_geojson().get("features", []):
        g = f.get("geometry") or {}
        lines = ([g["coordinates"]] if g.get("type") == "LineString"
                 else g.get("coordinates", []) if g.get("type") == "MultiLineString" else [])
        for ln in lines:
            if any(_in_box(x, y, box) for x, y in ln[:: max(1, len(ln) // 50)] + [ln[-1]]):
                rivers.append({"coordinates": [[round(x, 6), round(y, 6)] for x, y in ln],
                               "props": {k: v for k, v in (f.get("properties") or {}).items()
                                         if k in ("DIS_AV_CMS", "ORD_STRA")}})

    vp = vertical_params_at(lon, lat)
    return {
        "center": [lon, lat], "half_km": half_km,
        "bounds": [[box[1], box[0]], [box[3], box[2]]],
        "ground_m": (None if (g := elevation_at(lon, lat)) is None else round(g, 1)),
        "terrain": terrain,
        "terrain_note": (None if terrain else
                         "No committed terrain here: the DEM excerpt covers the "
                         "Singhbhum uranium belt only. The block is drawn flat."),
        "wells": wells,
        "wells_source": ("CGWB national monitoring network, Jharkhand "
                         "(Datasets/cgwb_waterlevel_jharkhand.csv), per-season "
                         "means over 2013-2021"),
        "rivers": rivers,
        "layers": {
            "layer1_base_m": vp["layer1_base_m"],
            "fracture_min_m": vp.get("fracture_min_m"),
            "fracture_max_m": vp.get("fracture_max_m"),
            "district": vp.get("district"),
            "source": vp.get("source"), "confidence": vp.get("confidence"),
        },
        # the network is ~398 stations state-wide (~1 per 200 km2), so a block
        # usually holds none; the nearest one is reported rather than implying
        # local monitoring exists
        "nearest_well": _nearest_station(lon, lat),
    }


def _nearest_station(lon: float, lat: float) -> dict | None:
    st = _stations()
    if st.empty:
        return None
    dx = (st["longitude"].to_numpy() - lon) * M_PER_DEG * math.cos(math.radians(lat))
    dy = (st["latitude"].to_numpy() - lat) * M_PER_DEG
    d = np.hypot(dx, dy)
    k = int(np.argmin(d))
    return {"name": st.iloc[k]["station_name"], "km": round(float(d[k]) / 1000.0, 2),
            "district": st.iloc[k]["district_name"]}
