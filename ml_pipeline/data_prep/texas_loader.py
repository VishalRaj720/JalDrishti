"""
ml_pipeline.data_prep.texas_loader
================================
Parse the *real* Texas ISR files into tidy frames. Nothing here assumes a
column that was not verified to exist in the uploaded data.

Sources actually used (paths relative to repo root):
  Datasets/Real_dataset/Dataset_1/TX_ISR_Final.xlsx
      sheets: 'Baseline', 'End of Mining', 'Final Post-restoration', 'Standards'
  Datasets/Real_dataset/Dataset 2/Restoration.csv      (Q_in / Q_out / pore volumes)
  Datasets/Real_dataset/Dataset 2/AquiferExemptions.csv(OrePorosity, FormPerm)
  Datasets/Real_dataset/Dataset 2/TexasISROperations.csv (flow rate, leachant)

The messy geochem sheets have a title row, a header row, and a units row before
data. We detect the header row by looking for the constituents 'Sulfate' and
'Uranium' rather than hard-coding a row index.
"""
from __future__ import annotations

import re
from pathlib import Path
import numpy as np
import pandas as pd

# Resolve repo root from this file: ml_pipeline/data_prep/texas_loader.py -> repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
XLSX = REPO_ROOT / "Datasets" / "Real_dataset" / "Dataset_1" / "TX_ISR_Final.xlsx"
DS2 = REPO_ROOT / "Datasets" / "Real_dataset" / "Dataset 2"

# Canonical constituent names we care about (others kept as-is if present).
CONSTITUENTS = [
    "Calcium", "Magnesium", "Sodium", "Potassium", "Carbonate", "Bicarbonate",
    "Sulfate", "Chloride", "Fluoride", "Nitrate-N", "Silica", "pH", "TDS",
    "Conductivity", "Alkalinity", "Arsenic", "Cadmium", "Iron", "Lead",
    "Manganese", "Mercury", "Selenium", "Ammonia-N", "Uranium", "Molybdenum",
    "Radium-226",
]


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def parse_numeric_range(value) -> tuple[float, float, float]:
    """Parse strings like '28-40', '12 -240', 'Upto 5%', '870, 1000', '> 500', '-'
    into (low, mean, high). Returns (nan, nan, nan) when nothing parseable.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return (np.nan, np.nan, np.nan)
    s = str(value).strip()
    if s in {"", "-", "NaN", "nan", "Not available", "Not Found"}:
        return (np.nan, np.nan, np.nan)
    # Plain numerics INCLUDING scientific notation ('8.15E+10') first -- the
    # regex path below would split the mantissa and exponent into two numbers.
    try:
        f = float(s)
        if np.isfinite(f):
            return (f, f, f)
        return (np.nan, np.nan, np.nan)
    except ValueError:
        pass
    s_clean = s.replace("%", "").replace(">", " ").replace("<", " ").replace("~", " ")
    s_clean = s_clean.replace("Upto", " ").replace("upto", " ").replace("Up to", " ")
    # A hyphen BETWEEN two digits is a range separator ("20-300"), not a minus
    # sign. Normalize it so the second value is not parsed as negative. Every
    # quantity in these files (T, K, porosity, thickness, conc.) is >= 0, so we
    # also drop signed matching entirely.
    s_clean = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " ", s_clean)
    nums = re.findall(r"\d+\.?\d*", s_clean)
    nums = [float(n) for n in nums]
    if not nums:
        return (np.nan, np.nan, np.nan)
    lo, hi = min(nums), max(nums)
    # 'Upto X' -> treat as (0, X/2, X)
    if re.search(r"up\s*to", s, flags=re.I):
        return (0.0, hi / 2.0, hi)
    return (lo, float(np.mean(nums)), hi)


def _rmean(value) -> float:
    return parse_numeric_range(value)[1]


def _strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


# --------------------------------------------------------------------------- #
# Geochemistry sheets (Baseline / End of Mining / Final Post-restoration)
# --------------------------------------------------------------------------- #
def _load_geochem_sheet(sheet: str) -> pd.DataFrame:
    """Read a constituent sheet with an unknown number of preamble rows.
    Detect the header row by presence of 'Sulfate' + 'Uranium', drop the
    units row, coerce constituent columns to numeric.
    """
    raw = pd.read_excel(XLSX, sheet_name=sheet, header=None)
    header_row = None
    for i in range(min(6, len(raw))):
        row_vals = {str(v).strip() for v in raw.iloc[i].tolist()}
        if "Sulfate" in row_vals and "Uranium" in row_vals:
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"Could not locate header row in sheet '{sheet}'")

    cols = [str(v).strip() for v in raw.iloc[header_row].tolist()]
    data = raw.iloc[header_row + 1:].copy()
    data.columns = cols
    # Drop the units row (its 'Calcium' or 'Sulfate' cell reads 'mg/L')
    def _is_units(row) -> bool:
        for key in ("Sulfate", "Calcium", "TDS"):
            if key in data.columns:
                cell = str(row.get(key, "")).strip().lower()
                if cell in {"mg/l", "standard units", "umhos/cm", "pci/l"}:
                    return True
        return False
    data = data[~data.apply(_is_units, axis=1)]
    # Drop fully empty rows and rows with no mine label
    label_col = "Mine" if "Mine" in data.columns else data.columns[0]
    data = data[data[label_col].notna()]
    data = data.dropna(how="all")

    # Coerce constituents to numeric (handles '<0.001', 'BDL', etc. -> NaN)
    for c in data.columns:
        if c in CONSTITUENTS:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    data.insert(0, "stage", sheet)
    return data.reset_index(drop=True)


def load_texas_geochem() -> dict[str, pd.DataFrame]:
    """Return tidy Baseline / End of Mining / Final Post-restoration frames."""
    out = {}
    for sheet in ("Baseline", "End of Mining", "Final Post-restoration"):
        out[sheet] = _load_geochem_sheet(sheet)
    return out


def load_texas_standards() -> pd.DataFrame:
    """EPA primary MCL / secondary standards table (for cross-checking vs BIS)."""
    raw = pd.read_excel(XLSX, sheet_name="Standards", header=None)
    rows = []
    for i in range(1, len(raw)):
        sym = str(raw.iat[i, 0]).strip()
        if sym in {"", "nan", "NaN"}:
            continue
        rows.append({
            "symbol": sym,
            "name": str(raw.iat[i, 1]).strip(),
            "epa_primary_mcl": _rmean(raw.iat[i, 2]),
            "epa_secondary": _rmean(raw.iat[i, 3]),
            "tx_secondary": _rmean(raw.iat[i, 4]),
            "unit": str(raw.iat[i, 5]).strip(),
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Operational data (Dataset 2)
# --------------------------------------------------------------------------- #
def load_restoration() -> pd.DataFrame:
    """Restoration.csv -> per production-area injection/extraction volumes.

    NOTE on regime: these volumes are from the RESTORATION (aquifer clean-up)
    phase, where net extraction is large (multiple pore-volume sweep), so the
    extract/inject ratio here is ~2x, NOT the 0.5-3 % operational *production*
    bleed. The synthetic loop uses the operational bleed from config; this ratio
    is retained only as real-data context / an upper bound on net extraction.
        Q_out = VolWaterExtract / Days     [gal/day -> m3/day]
        Q_in  = VolWaterInjected / Days
        restoration_net_ratio = Q_out / Q_in
    """
    GAL_TO_M3 = 0.00378541
    df = _strip_cols(pd.read_csv(DS2 / "Restoration.csv"))
    rec = []
    for _, r in df.iterrows():
        days = _rmean(r.get("Days"))
        v_ext = _rmean(r.get("VolWaterExtract"))
        v_inj = _rmean(r.get("VolWaterInjected"))
        q_out = (v_ext * GAL_TO_M3 / days) if days and days > 0 else np.nan
        q_in = (v_inj * GAL_TO_M3 / days) if days and days > 0 else np.nan
        net_ratio = (q_out / q_in) if (q_in and q_in > 0 and not np.isnan(q_out)) else np.nan
        rec.append({
            "mine": str(r.get("MineName", "")).strip(),
            "prod_area": str(r.get("ProdAreaName", "")).strip(),
            "pore_volume_of_area_gal": _rmean(r.get("PoreVolumeOfArea")),
            "vol_extract_gal": v_ext,
            "vol_inject_gal": v_inj,
            "days": days,
            "q_out_m3_day": q_out,
            "q_in_m3_day": q_in,
            "restoration_net_ratio": net_ratio,
        })
    return pd.DataFrame(rec)


def load_aquifer_exemptions() -> pd.DataFrame:
    """AquiferExemptions.csv -> Texas host-rock physics: porosity, permeability,
    exempted thickness/area, average dissolved solids. Converts FormPerm (mD)
    to hydraulic conductivity K (m/day).
    """
    from ml_pipeline.config.parameters import millidarcy_to_m_per_day
    df = _strip_cols(pd.read_csv(DS2 / "AquiferExemptions.csv"))
    rec = []
    for _, r in df.iterrows():
        phi = _rmean(r.get("OrePorosity"))
        phi = phi / 100.0 if (not np.isnan(phi) and phi > 1.0) else phi  # % -> fraction
        perm_mD = _rmean(r.get("FormPerm"))
        K = millidarcy_to_m_per_day(perm_mD) if not np.isnan(perm_mD) else np.nan
        rec.append({
            "mine": str(r.get("MineName", "")).strip(),
            "ore_porosity": phi,
            "form_perm_mD": perm_mD,
            "K_m_day": K,
            "exempt_area_m2": _rmean(r.get("AqExemptArea_EPA")),
            "exempt_thickness_m": _rmean(r.get("ExempThick_EPA")),
            "avg_tds_mg_l": _rmean(r.get("AvgDissolvedSolids")),
        })
    return pd.DataFrame(rec)


def load_operations() -> pd.DataFrame:
    """TexasISROperations.csv -> flow rate, leachant (confirms alkaline NaHCO3),
    grade and recovery factor.
    """
    df = _strip_cols(pd.read_csv(DS2 / "TexasISROperations.csv"))
    rec = []
    for _, r in df.iterrows():
        rec.append({
            "mine": str(r.get("ISR_OpName", "")).strip(),
            "flow_rate_raw": _rmean(r.get("IAEA_FlowRate")),  # units per source; normalized later
            "grade_u3o8": _rmean(r.get("Grade_U3O8")),
            "production_u3o8": _rmean(r.get("Production_U3O8")),
            "avg_recovery_pct": _rmean(r.get("AvgRecFactor")),
            "leachant": str(r.get("Leachant", "")).strip(),
            "mineral": str(r.get("Mineral", "")).strip(),
        })
    return pd.DataFrame(rec)


# --------------------------------------------------------------------------- #
# Convenience: derived Texas source signature (end-of-mining minus baseline)
# --------------------------------------------------------------------------- #
def texas_source_signature() -> dict[str, tuple[float, float]]:
    """Empirical (min, max) source concentrations for U / Sulfate / TDS taken
    from the Texas 'End of Mining' sheet (the in-aquifer excursion signature).
    Falls back to config ranges if the sheet is too sparse.
    """
    from ml_pipeline.config.parameters import FALLBACK_SOURCE_CONC
    geo = load_texas_geochem()
    eom = geo["End of Mining"]
    out = {}
    mapping = {"uranium_ppb": "Uranium", "sulfate_mg_l": "Sulfate", "tds_mg_l": "TDS"}
    for key, col in mapping.items():
        vals = pd.to_numeric(eom.get(col), errors="coerce").dropna() if col in eom else pd.Series([], dtype=float)
        if key == "uranium_ppb":
            vals = vals * 1000.0  # mg/L -> ppb
        if len(vals) >= 2:
            out[key] = (float(vals.quantile(0.25)), float(vals.quantile(0.95)))
        else:
            out[key] = FALLBACK_SOURCE_CONC[key]
    return out


def texas_restoration_residual() -> dict[str, float]:
    """Per-species residual source fraction after restoration, derived from the
    real sheets:  residual = median('Final Post-restoration') / median('End of
    Mining').  This is the C_rest/C0 step applied by the transport engine's
    restoration superposition. Clipped to [0.02, 1.0]; falls back to config
    values when a sheet is too sparse.
    """
    from ml_pipeline.config.parameters import RESTORATION_FALLBACK_RESIDUAL
    geo = load_texas_geochem()
    eom, post = geo["End of Mining"], geo["Final Post-restoration"]
    mapping = {"uranium_ppb": "Uranium", "sulfate_mg_l": "Sulfate", "tds_mg_l": "TDS"}
    out = {}
    for key, col in mapping.items():
        e = pd.to_numeric(eom.get(col), errors="coerce").dropna() if col in eom else pd.Series(dtype=float)
        p = pd.to_numeric(post.get(col), errors="coerce").dropna() if col in post else pd.Series(dtype=float)
        if len(e) >= 2 and len(p) >= 2 and e.median() > 0:
            out[key] = float(np.clip(p.median() / e.median(), 0.02, 1.0))
        else:
            out[key] = RESTORATION_FALLBACK_RESIDUAL[key]
    return out


if __name__ == "__main__":
    geo = load_texas_geochem()
    for k, v in geo.items():
        print(f"[geochem] {k:24s} rows={len(v):3d} cols={len(v.columns)}")
    print("[standards] rows=", len(load_texas_standards()))
    res = load_restoration()
    print("[restoration] rows=", len(res),
          "| median net extract/inject ratio=", round(res["restoration_net_ratio"].median(skipna=True), 3),
          "| median Q_in(m3/day)=", round(res["q_in_m3_day"].median(skipna=True), 1))
    aqx = load_aquifer_exemptions()
    print("[aquifer_exemptions] rows=", len(aqx),
          "| median porosity=", round(aqx["ore_porosity"].median(skipna=True), 3),
          "| median K(m/day)=", round(aqx["K_m_day"].median(skipna=True), 3))
    ops = load_operations()
    print("[operations] leachants=", sorted(set(ops["leachant"]) - {""}))
    print("[source signature]", texas_source_signature())
    print("[restoration residual C_rest/C0]", texas_restoration_residual())
