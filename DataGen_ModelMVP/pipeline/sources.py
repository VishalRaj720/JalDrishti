"""sources.py — loaders for the four REAL data sources.

Each loader returns a tidy DataFrame (or helper) in the units fixed by
`schema.py`. Nothing here invents data; the synthetic counterfactual lives in
`synth.py` and is always tagged `data_source == "synthetic"`.

Sources
-------
1. Texas ISR chemistry  -> per-well uranium + co-chemistry, per phase   (REAL target signal)
2. Texas mine operations -> injection rate, ore grade, ore porosity     (REAL ISR features)
3. Jharkhand CGWB quality -> ambient uranium + chemistry, real coords    (REAL local baseline)
4. Jharkhand aquifers    -> transmissivity / yield / depth, point lookup (REAL hydrogeology)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from pipeline import (
    AQUIFERS_GEOJSON,
    JHARKHAND_QUALITY_CSV,
    MINE_OPS_DIR,
    TEXAS_XLSX,
)
from pipeline import schema as S


# =========================================================================
# Shared numeric coercion (Texas sheets are full of "<.001", "1044+/-5", "-")
# =========================================================================
def coerce_num(v) -> float:
    if pd.isna(v):
        return np.nan
    s = str(v).strip()
    if s in ("", "-", "nan", "NaN", "NA"):
        return np.nan
    m = re.match(r"^<\s*(\d*\.?\d+)$", s)            # '<.001' -> half the LOD
    if m:
        return float(m.group(1)) / 2.0
    m = re.match(r"^(-?\d*\.?\d+)\s*\+/?-\s*\d*\.?\d+$", s)  # '1044+/-5' -> 1044
    if m:
        return float(m.group(1))
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


def _range_mid(v) -> float:
    """Parse aquifer property ranges: '26 - 176'->101, '2-3%'->2.5, 'Upto 5%'->5."""
    if pd.isna(v):
        return np.nan
    s = str(v).strip().replace("%", "")
    if s in ("", "-"):
        return np.nan
    s = re.sub(r"(?i)upto", "", s).strip()
    # All aquifer properties are positive; the hyphen/dash is a RANGE separator,
    # never a minus sign, so match unsigned decimals only.
    nums = [float(n) for n in re.findall(r"\d*\.?\d+", s) if n not in ("", ".")]
    if not nums:
        return np.nan
    return float(np.mean(nums))


def _norm_mine(name) -> str:
    """Normalise mine names so chemistry sheets join to the ops CSVs.
    'Altamesa', 'Alta Mesa  PAA-1', 'El Mesquite ' -> 'altamesa', 'altamesa', 'elmesquite'.
    """
    if pd.isna(name):
        return ""
    s = str(name).lower()
    s = re.sub(r"paa[\s-]*\d+", "", s)            # drop production-area suffixes
    s = re.sub(r"\b(project|dome|mine|ext|original|revised|total)\b", "", s)
    s = re.sub(r"[^a-z]", "", s)                  # keep letters only
    return s


# =========================================================================
# 1. Texas ISR chemistry (the real before/during/after uranium signal)
# =========================================================================
# Texas column -> unified column. Uranium is mg/L here -> converted to ppb below.
_TX_CHEM_MAP = {
    "Uranium": "uranium_ppb",      # mg/L * 1000
    "TDS": "tds_mg_l",
    "Sulfate": "sulfate_mg_l",
    "pH": "ph",
    "Iron": "iron_mg_l",
    "Arsenic": "arsenic_ppb",      # mg/L * 1000
    "Conductivity": "_ec_us_cm",   # helper, to backfill TDS if missing
}
_TX_SHEETS = {"baseline": ("Baseline", 2), "mining": ("End of Mining", 1),
              "post": ("Final Post-restoration", 0)}


def _load_tx_sheet(sheet: str, header_row: int) -> pd.DataFrame:
    df = pd.read_excel(TEXAS_XLSX, sheet_name=sheet, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    # strip caption / repeated-header rows that leak into the Mine column
    df = df[df["Mine"].notna()]
    df = df[~df["Mine"].astype(str).str.contains(
        "Post-restoration|Baseline|Groundwater|composition", case=False, na=False)]
    df = df[df["Mine"].astype(str).str.lower().str.strip() != "mine"]
    return df.reset_index(drop=True)


def load_texas() -> pd.DataFrame:
    """Real Texas wells in unified schema, one row per well per phase."""
    frames = []
    for phase, (sheet, hdr) in _TX_SHEETS.items():
        raw = _load_tx_sheet(sheet, hdr)
        if raw.empty:
            continue
        out = pd.DataFrame(index=range(len(raw)))
        out["mine"] = raw["Mine"].astype(str).str.strip()
        out["_mine_key"] = out["mine"].map(_norm_mine)
        for tx_col, uni_col in _TX_CHEM_MAP.items():
            out[uni_col] = raw[tx_col].map(coerce_num) if tx_col in raw.columns else np.nan
        # unit conversions mg/L -> ppb
        out["uranium_ppb"] = out["uranium_ppb"] * 1000.0
        out["arsenic_ppb"] = out["arsenic_ppb"] * 1000.0
        # backfill TDS from EC where missing (0.64 conversion)
        out["tds_mg_l"] = out["tds_mg_l"].where(
            out["tds_mg_l"].notna(), 0.64 * out["_ec_us_cm"])
        out["phase"] = phase
        out["data_source"] = "texas_real"
        frames.append(out.drop(columns=["_ec_us_cm"]))
    df = pd.concat(frames, ignore_index=True)
    # fix impossible pH (data-entry errors)
    df.loc[(df["ph"] < 1) | (df["ph"] > 14), "ph"] = np.nan
    return df


# =========================================================================
# 2. Texas mine operations (real ISR features: flow rate, ore grade, porosity)
# =========================================================================
@dataclass
class MineOps:
    """Per-mine real operational parameters, keyed by normalised mine name."""
    injection_rate_gpm: Dict[str, float]
    ore_grade_pct: Dict[str, float]
    ore_porosity_pct: Dict[str, float]

    # Real-distribution fallbacks (median, std) for mines without a direct match
    rate_dist: tuple
    grade_dist: tuple
    porosity_dist: tuple


def load_mine_ops() -> MineOps:
    ops = pd.read_csv(MINE_OPS_DIR / "TexasISROperations.csv")
    ops.columns = [c.strip() for c in ops.columns]
    ops["_key"] = ops["ISR_OpName"].map(_norm_mine)
    rate = ops.groupby("_key")["IAEA_FlowRate"].apply(
        lambda s: coerce_num(s.dropna().iloc[0]) if s.dropna().size else np.nan)

    def _first_grade(s):
        for v in s.dropna():
            n = coerce_num(str(v).split(",")[0])  # '0.12, 0.15' -> 0.12
            if not np.isnan(n):
                return n
        return np.nan
    grade = ops.groupby("_key")["Grade_U3O8"].apply(_first_grade)

    exempt = pd.read_csv(MINE_OPS_DIR / "AquiferExemptions.csv")
    exempt.columns = [c.strip() for c in exempt.columns]
    exempt["_key"] = exempt["MineName"].map(_norm_mine)
    poro = exempt.groupby("_key")["OrePorosity"].apply(
        lambda s: _range_mid(s.dropna().iloc[0]) if s.dropna().size else np.nan)

    def _dist(series, fallback):
        v = series.dropna()
        return (float(v.median()), float(v.std())) if len(v) >= 2 else fallback

    return MineOps(
        injection_rate_gpm=rate.dropna().to_dict(),
        ore_grade_pct=grade.dropna().to_dict(),
        ore_porosity_pct=poro.dropna().to_dict(),
        rate_dist=_dist(rate, (1000.0, 300.0)),
        grade_dist=_dist(grade, (0.12, 0.04)),
        porosity_dist=_dist(poro, (28.0, 6.0)),
    )


def attach_mine_ops(tx: pd.DataFrame, ops: MineOps) -> pd.DataFrame:
    """Join real per-mine ops onto Texas wells; leave NaN where no match."""
    tx = tx.copy()
    tx["injection_rate_gpm"] = tx["_mine_key"].map(ops.injection_rate_gpm)
    tx["ore_grade_pct"] = tx["_mine_key"].map(ops.ore_grade_pct)
    tx["_ore_porosity_pct"] = tx["_mine_key"].map(ops.ore_porosity_pct)
    return tx


# =========================================================================
# 3. Jharkhand CGWB water quality (real ambient uranium + chemistry)
# =========================================================================
def load_jharkhand() -> pd.DataFrame:
    df = pd.read_csv(JHARKHAND_QUALITY_CSV, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    ec_col = next((c for c in df.columns if c.startswith("EC")), None)
    out = pd.DataFrame(index=range(len(df)))
    out["latitude"] = pd.to_numeric(df["Latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["Longitude"], errors="coerce")
    out["uranium_ppb"] = df["U (ppb)"].map(coerce_num)
    ec = df[ec_col].map(coerce_num) if ec_col else np.nan
    out["tds_mg_l"] = 0.64 * ec                       # CGWB has EC, not TDS
    out["sulfate_mg_l"] = df["SO4"].map(coerce_num) if "SO4" in df.columns else np.nan
    out["ph"] = df["pH"].map(coerce_num) if "pH" in df.columns else np.nan
    out["iron_mg_l"] = np.nan                          # Fe column is empty ('-')
    out["arsenic_ppb"] = np.nan                        # As column is empty ('-')
    out["phase"] = "baseline"                          # no ISR in Jharkhand -> ambient
    out["data_source"] = "jharkhand_real"
    out["mine"] = ""
    out = out[out["uranium_ppb"].notna() & out["latitude"].notna()].reset_index(drop=True)
    return out


# =========================================================================
# 4. Jharkhand aquifers (real hydrogeology + point -> aquifer spatial join)
# =========================================================================
# Effective porosity by aquifer type (hard-rock fractured aquifers are low).
# Literature-typical values; specific yield (real, from geojson) is kept separate.
_POROSITY_BY_TYPE = {
    "basalt": 0.04, "charnockite": 0.02, "gneiss": 0.03, "granite": 0.03,
    "schist": 0.03, "quartzite": 0.02, "limestone": 0.10, "sandstone": 0.18,
    "alluvium": 0.22, "laterite": 0.12, "intrusive": 0.02,
    "basement_gneissic_complex": 0.03, "unknown": 0.05,
}


@dataclass
class AquiferIndex:
    geoms: list
    props: List[dict]

    def lookup(self, lon: float, lat: float) -> dict:
        """Return real hydrogeology for the polygon containing (lon,lat);
        falls back to the nearest polygon centroid when outside all polygons."""
        pt = Point(lon, lat)
        for g, p in zip(self.geoms, self.props):
            if g.contains(pt):
                return p
        # nearest by centroid distance
        d = [pt.distance(g.centroid) for g in self.geoms]
        return self.props[int(np.argmin(d))]


def load_aquifers() -> AquiferIndex:
    gj = json.loads(AQUIFERS_GEOJSON.read_text(encoding="utf-8"))
    geoms, props = [], []
    for feat in gj["features"]:
        p = feat["properties"]
        atype = str(p.get("aquifer", "unknown")).strip().lower().replace(" ", "_")
        transmissivity = _range_mid(p.get("m2_perday"))
        thickness = _range_mid(p.get("zone_m"))
        rec = {
            "aquifer_type": atype if atype in _POROSITY_BY_TYPE else "unknown",
            "aquifer_transmissivity_m2day": transmissivity,
            "aquifer_specific_yield_pct": _range_mid(p.get("yeild__")),
            "depth_to_water_m": _range_mid(p.get("avg_mbgl")),
            "aquifer_thickness_m": thickness,
            "rainfall_mm": _range_mid(p.get("per_cm")),
        }
        rec["aquifer_porosity"] = _POROSITY_BY_TYPE.get(rec["aquifer_type"], 0.05)
        # K = T / saturated thickness (m/day); guard divide-by-zero
        rec["aquifer_hydraulic_conductivity_mday"] = (
            transmissivity / thickness if thickness and thickness > 0 else np.nan
        )
        geoms.append(shape(feat["geometry"]))
        props.append(rec)
    return AquiferIndex(geoms=geoms, props=props)


def enrich_with_aquifer(df: pd.DataFrame, idx: AquiferIndex) -> pd.DataFrame:
    """Add real aquifer hydrogeology columns by spatial join on lat/lon.
    Rows without coordinates (Texas wells) keep whatever the caller set."""
    df = df.reset_index(drop=True).copy()
    cols = ["aquifer_type", "aquifer_transmissivity_m2day",
            "aquifer_hydraulic_conductivity_mday", "aquifer_porosity",
            "aquifer_specific_yield_pct", "depth_to_water_m",
            "aquifer_thickness_m", "rainfall_mm"]
    has_xy = df["latitude"].notna() & df["longitude"].notna()
    recs = {i: idx.lookup(df.at[i, "longitude"], df.at[i, "latitude"])
            for i in df.index[has_xy]}
    joined = pd.DataFrame.from_dict(recs, orient="index")
    for c in cols:
        col = joined[c] if c in joined.columns else pd.Series(dtype=float)
        if c in df.columns:
            df[c] = df[c].astype(object)
            df.loc[col.index, c] = col
        else:
            df[c] = col.reindex(df.index)
    return df
