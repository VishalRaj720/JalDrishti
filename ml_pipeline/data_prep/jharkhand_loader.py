"""
ml_pipeline.data_prep.jharkhand_loader
====================================
Turn the Jharkhand files into model-ready hydrogeology, deriving the parameters
the Texas data cannot give us (because Texas is uniform sandstone and Jharkhand
is 12 different lithologies).

Sources actually used:
  Datasets/Aquifers_Jharkhand.geojson   (23 MultiPolygons; 12 lithologies)
      m2_perday -> Transmissivity T [m2/day]
      zone_m    -> weathered/fractured (mobile) zone thickness b [m]
      yeild__   -> specific yield Sy [%]  (drainable / effective porosity proxy)
      aquifer   -> lithology -> fractured vs porous regime
  Datasets/waterQuality_jharkhand.csv   (397 wells; U ppb, SO4, EC, pH, lon/lat)

Key derivation:   K = T / b      (hydraulic conductivity from transmissivity)
                  v = K * i / phi (seepage velocity; i supplied by user/dashboard)
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from ml_pipeline.config.parameters import (
    LITHOLOGY_REGIME, DEFAULT_EFFECTIVE_POROSITY, GRAIN_DENSITY,
    DEFAULT_GRAIN_DENSITY, EC_TO_TDS_FACTOR,
)
from ml_pipeline.data_prep.texas_loader import parse_numeric_range, _rmean

REPO_ROOT = Path(__file__).resolve().parents[2]
AQUIFER_GEOJSON = REPO_ROOT / "Datasets" / "Aquifers_Jharkhand.geojson"
WQ_CSV = REPO_ROOT / "Datasets" / "waterQuality_jharkhand.csv"


# --------------------------------------------------------------------------- #
# Aquifer polygons -> hydrogeology
# --------------------------------------------------------------------------- #
def load_jharkhand_aquifers():
    """Return a GeoDataFrame of the 23 aquifer polygons with derived columns:
        lithology, regime, T_m2_day, thickness_m, K_m_day(min/mean/max),
        eff_porosity, grain_density, confinement.
    Geometry kept (EPSG:4326) for point-in-polygon pin lookup.
    """
    import geopandas as gpd
    gdf = gpd.read_file(AQUIFER_GEOJSON)
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)

    recs = []
    for _, row in gdf.iterrows():
        litho = str(row.get("aquifer", "")).strip()
        regime = LITHOLOGY_REGIME.get(litho, "porous")

        T_lo, T_mean, T_hi = parse_numeric_range(row.get("m2_perday"))   # m2/day
        b_lo, b_mean, b_hi = parse_numeric_range(row.get("zone_m"))      # m (mobile zone)
        if np.isnan(b_mean):
            # fall back to average depth-to-water span if zone thickness missing
            _, b_mean, _ = parse_numeric_range(row.get("mbgl"))
        if np.isnan(b_mean) or b_mean <= 0:
            b_mean = 30.0  # generic hard-rock saturated-zone thickness [Freeze & Cherry]

        # K = T / b   (guard against divide-by-zero / missing T)
        def _K(T):
            return (T / b_mean) if (not np.isnan(T) and b_mean > 0) else np.nan
        K_mean = _K(T_mean)
        if np.isnan(K_mean):
            # last-resort lithology-typical K (m/day) so a pin never returns NaN
            K_mean = {"fractured": 0.5, "porous": 10.0}[regime]
            K_lo, K_hi = K_mean * 0.3, K_mean * 3.0
        else:
            K_lo, K_hi = _K(T_lo), _K(T_hi)

        sy = parse_numeric_range(row.get("yeild__"))[1]   # specific yield %
        phi = (sy / 100.0) if (not np.isnan(sy) and sy > 0) else DEFAULT_EFFECTIVE_POROSITY.get(litho, 0.05)
        phi = float(np.clip(phi, 0.002, 0.35))

        recs.append({
            "objectid": row.get("objectid"),
            "code": row.get("newcode43"),
            "lithology": litho,
            "lithology_detail": str(row.get("aquifer0", "")).strip(),
            "regime": regime,
            "confinement": str(row.get("aquifers", "")).strip(),
            "T_m2_day": T_mean,
            "thickness_m": b_mean,
            "K_m_day": K_mean,
            "K_min_m_day": K_lo,
            "K_max_m_day": K_hi,
            "eff_porosity": phi,
            "specific_yield_pct": sy,
            "grain_density": GRAIN_DENSITY.get(litho, DEFAULT_GRAIN_DENSITY),
            "yield_m3_day": _rmean(row.get("m3_per_day")),
            "area_km2": _rmean(row.get("area_re")),
            "geometry": row.geometry,
        })
    out = gpd.GeoDataFrame(recs, geometry="geometry", crs=4326)
    return out


# --------------------------------------------------------------------------- #
# Water-quality wells -> per-coordinate baseline chemistry
# --------------------------------------------------------------------------- #
def load_jharkhand_water_quality() -> pd.DataFrame:
    """Return well baseline chemistry: lon, lat, U_ppb, sulfate_mg_l, tds_mg_l,
    ph. TDS is estimated from EC (column header is mojibake -> matched by prefix).
    """
    df = pd.read_csv(WQ_CSV)
    df.columns = [str(c).strip() for c in df.columns]
    ec_col = next((c for c in df.columns if c.upper().startswith("EC")), None)

    def num(col):
        return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)

    ec = num(ec_col) if ec_col else pd.Series(np.nan, index=df.index)
    out = pd.DataFrame({
        "longitude": num("Longitude"),
        "latitude": num("Latitude"),
        "district": df.get("District"),
        "location": df.get("Location"),
        "year": num("Year"),
        "ph": num("pH"),
        "uranium_ppb": num("U (ppb)"),
        "sulfate_mg_l": num("SO4"),
        "ec_uS_cm": ec,
        "tds_mg_l": ec * EC_TO_TDS_FACTOR,   # EC -> TDS [Freeze & Cherry]
        "fluoride_mg_l": num("F (mg/L)"),
        "nitrate_mg_l": num("NO3"),
    })
    return out.dropna(subset=["longitude", "latitude"]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# "Drop a pin" lookups
# --------------------------------------------------------------------------- #
def aquifer_at_point(lon: float, lat: float, aquifers=None) -> dict | None:
    """Return the hydrogeology dict of the aquifer polygon containing (lon, lat),
    or the nearest polygon if the pin lands in a gap. Used by the dashboard.
    """
    from shapely.geometry import Point
    if aquifers is None:
        aquifers = load_jharkhand_aquifers()
    pt = Point(lon, lat)
    hit = aquifers[aquifers.contains(pt)]
    if len(hit) == 0:
        # nearest polygon (degrees distance is fine at state scale for selection)
        idx = aquifers.geometry.distance(pt).idxmin()
        row = aquifers.loc[idx]
    else:
        row = hit.iloc[0]
    return {k: row[k] for k in aquifers.columns if k != "geometry"}


def baseline_at_point(lon: float, lat: float, wq: pd.DataFrame | None = None) -> dict:
    """Nearest water-quality well's baseline U / sulfate / TDS / pH for a pin."""
    if wq is None:
        wq = load_jharkhand_water_quality()
    d2 = (wq["longitude"] - lon) ** 2 + (wq["latitude"] - lat) ** 2
    r = wq.loc[d2.idxmin()]
    return {
        "uranium_ppb": float(r["uranium_ppb"]) if pd.notna(r["uranium_ppb"]) else np.nan,
        "sulfate_mg_l": float(r["sulfate_mg_l"]) if pd.notna(r["sulfate_mg_l"]) else np.nan,
        "tds_mg_l": float(r["tds_mg_l"]) if pd.notna(r["tds_mg_l"]) else np.nan,
        "ph": float(r["ph"]) if pd.notna(r["ph"]) else np.nan,
        "district": r.get("district"),
        "dist_deg": float(np.sqrt(d2.min())),
    }


if __name__ == "__main__":
    aq = load_jharkhand_aquifers()
    print(f"[aquifers] {len(aq)} polygons")
    show = aq[["lithology", "regime", "T_m2_day", "thickness_m", "K_m_day", "eff_porosity"]].copy()
    print(show.round(3).to_string(index=False))
    print("\nregime counts:", aq["regime"].value_counts().to_dict())

    wq = load_jharkhand_water_quality()
    print(f"\n[water quality] {len(wq)} wells")
    print("  U(ppb)  median=%.2f  max=%.2f  > 30ppb: %d wells" %
          (wq["uranium_ppb"].median(), wq["uranium_ppb"].max(),
           int((wq["uranium_ppb"] > 30).sum())))
    print("  TDS(mg/L) median=%.0f  SO4 median=%.0f" %
          (wq["tds_mg_l"].median(), wq["sulfate_mg_l"].median()))

    # Example pin near Jamshedpur / East Singhbhum (real uranium belt)
    demo = aquifer_at_point(86.2, 22.8, aq)
    print("\n[pin 86.2E,22.8N] lithology=%s regime=%s K=%.3f m/day phi=%.3f" %
          (demo["lithology"], demo["regime"], demo["K_m_day"], demo["eff_porosity"]))
    print("  baseline:", baseline_at_point(86.2, 22.8, wq))
