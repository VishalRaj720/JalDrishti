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

# V-4 parser hardening. A mine label is a short proper noun; anything longer is
# a title or footnote sentence, not data. "Longest Sand Production Area" style
# names stay well inside this.
_MAX_MINE_LABEL_CHARS = 40

# PINNED row counts, verified 2026-08-10 against
# Datasets/Real_dataset/Dataset_1/TX_ISR_Final.xlsx. `_load_geochem_sheet`
# raises if a parse deviates, so a workbook edit or a pandas/openpyxl behaviour
# change cannot silently move the source-term envelope this whole model scales
# linearly with.
# Counts are POST-trailer-filter. Pre-filter the sheets read 87 / 9 / 92, i.e.
# the filter removed 1 trailer row from Baseline and 6 from Final
# Post-restoration, and no real mine row (verified: first/last labels are
# 'Altamesa'/'Zamzow', longest surviving label 15 characters).
EXPECTED_GEOCHEM_ROWS = {
    "Baseline": 86,
    "End of Mining": 9,
    "Final Post-restoration": 86,
}


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

    # ---- V-4: terminate the data block instead of ingesting the trailer ----
    # The sheets carry a title line, a REPEATED header token, and numbered
    # footnotes below the data, e.g. on 'Final Post-restoration':
    #   "Post-restoration groundwater composition - Average composition ..."
    #   "Mine"                                             <- repeated header
    #   "1 Lixiviant type from U.S. Environmental Protection Agency (2007)."
    #   "2  The post-restoration average for Rosita PAAs 1 and 2 ..."
    #   "3  Tweeton (1981)"
    # These were previously kept as rows. Harmless TODAY because they carry no
    # parseable numbers, so pd.to_numeric().dropna() removes them from every
    # constituent column -- but the sparsity guards that decide whether to fall
    # back to config values COUNT them, and any future column whose footnote
    # contains a number would be silently ingested as data (review2.md V-4).
    def _is_trailer(label: str) -> bool:
        s = str(label).strip()
        if not s or s.lower() == "nan":
            return True
        if s == label_col:                      # repeated header row
            return True
        if len(s) > _MAX_MINE_LABEL_CHARS:      # prose / footnote sentence
            return True
        if re.match(r"^\d+\s", s):              # numbered footnote "1 Lixiviant..."
            return True
        return False

    # A title line can sit BEFORE the first data row (it does on
    # 'Final Post-restoration'), so we cannot simply cut at the first trailer --
    # doing that emptied the sheet. Skip leading preamble, then terminate at the
    # first trailer AFTER the data block has started.
    labels = data[label_col].astype(str)
    bad = labels.map(_is_trailer).to_numpy()
    good = np.flatnonzero(~bad)
    if good.size:
        start = int(good[0])
        rest_bad = np.flatnonzero(bad[start:])
        stop = start + int(rest_bad[0]) if rest_bad.size else len(data)
        data = data.iloc[start:stop]
    else:
        data = data.iloc[:0]

    # Coerce constituents to numeric (handles '<0.001', 'BDL', etc. -> NaN)
    for c in data.columns:
        if c in CONSTITUENTS:
            data[c] = pd.to_numeric(data[c], errors="coerce")
    data.insert(0, "stage", sheet)
    data = data.reset_index(drop=True)

    # Fail LOUDLY if a re-import changes the sheet layout, rather than silently
    # serving a different source envelope (review2.md V-4).
    expected = EXPECTED_GEOCHEM_ROWS.get(sheet)
    if expected is not None and len(data) != expected:
        raise ValueError(
            f"Texas sheet '{sheet}' parsed {len(data)} data rows, expected "
            f"{expected}. The workbook layout changed, or the trailer filter "
            f"needs updating. Refusing to derive source/restoration terms from "
            f"an unverified parse -- update EXPECTED_GEOCHEM_ROWS deliberately.")
    return data


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
# `chloride_mg_l` is an ISR EXCURSION INDICATOR ONLY -- it is deliberately NOT in
# P.SPECIES, so the synthetic generator never sees it and no retrain is implied.
# Its presence here only adds a key to the returned dicts; every consumer reads
# them as `d[sp] for sp in SPECIES`, so the extra key is inert.
_EOM_COLS = {"uranium_ppb": "Uranium", "sulfate_mg_l": "Sulfate",
             "tds_mg_l": "TDS", "chloride_mg_l": "Chloride"}
_EOM_UNIT_MULT = {"uranium_ppb": 1000.0, "sulfate_mg_l": 1.0,
                  "tds_mg_l": 1.0, "chloride_mg_l": 1.0}


def _eom_per_mine() -> dict[str, pd.Series]:
    """End-of-Mining source concentrations averaged PER MINE, in served units.

    Two of the seven mines contribute two production-area rows each, so a
    row-level statistic pseudo-replicates them (review2.md V-2). Averaging to
    one value per mine makes each independent site count once.
    """
    eom = load_texas_geochem()["End of Mining"]
    label = "Mine" if "Mine" in eom.columns else eom.columns[1]
    mines = eom[label].astype(str).str.strip()
    out = {}
    for key, col in _EOM_COLS.items():
        if col not in eom:
            out[key] = pd.Series([], dtype=float)
            continue
        v = pd.to_numeric(eom[col], errors="coerce") * _EOM_UNIT_MULT[key]
        d = pd.DataFrame({"mine": mines, "v": v}).dropna()
        out[key] = d.groupby("mine")["v"].mean()
    return out


def texas_source_signature() -> dict[str, tuple[float, float]]:
    """Empirical (min, max) source concentrations for U / Sulfate / TDS from the
    Texas 'End of Mining' sheet (the in-aquifer excursion signature).

    WINDOW CHANGED 2026-08-10 (review2.md V-2). This returned the P25-P95
    quantiles of the ROW values -- an asymmetric window with no justification
    anywhere in the code, config or docs, computed over pseudo-replicated rows.
    For uranium it discarded the real observed minimum (O'Hern, 9,000 ppb) and
    truncated the real observed maximum (Benavides, 41,600 ppb) to 34,440, so the
    served envelope was narrower than the evidence at the bottom and invented a
    value at the top that no mine ever reported.

    It is now the FULL OBSERVED RANGE of the per-mine means. With n = 7 mines a
    quantile window is not meaningful anyway, and the full range is the choice
    that adds no assumption: every endpoint is a real measured site value.

    n is small and that matters -- C0 scales the entire concentration field
    linearly. `texas_source_provenance()` reports the sample size and the
    per-mine values so the API can surface them instead of showing four
    significant figures with no context.
    """
    from ml_pipeline.config.parameters import FALLBACK_SOURCE_CONC
    per_mine = _eom_per_mine()
    out = {}
    for key in _EOM_COLS:
        s = per_mine[key]
        out[key] = ((float(s.min()), float(s.max())) if len(s) >= 2
                    else FALLBACK_SOURCE_CONC[key])
    return out


def texas_source_provenance() -> dict:
    """Sample size and per-mine values behind the served C0 envelope (V-2).

    Reported to the user so "13,272 ppb" is never read as a precise figure: it
    descends from nine production-area measurements at seven mines.
    """
    eom = load_texas_geochem()["End of Mining"]
    label = "Mine" if "Mine" in eom.columns else eom.columns[1]
    per_mine = _eom_per_mine()
    env = texas_source_signature()
    return {
        "sheet": "TX_ISR_Final.xlsx :: 'End of Mining'",
        "n_rows": int(len(eom)),
        "n_mines": int(eom[label].astype(str).str.strip().nunique()),
        "window_rule": ("full observed range of per-mine means (no quantile "
                        "window; each mine weighted once)"),
        "per_mine": {k: {m: round(float(x), 1) for m, x in s.items()}
                     for k, s in per_mine.items()},
        "envelope": {k: [round(v[0], 1), round(v[1], 1)] for k, v in env.items()},
        "caveat": ("C0 scales the concentration field linearly and rests on "
                   "n = 9 production-area measurements from 7 Texas mines; it is "
                   "an order-of-magnitude anchor, not a calibrated value."),
    }


def _paired_residual_ratios() -> dict[str, list]:
    """Per-MINE restoration ratios, paired between the two sheets.

    The previous estimator was median(Final Post-restoration) / median(End of
    Mining) -- a ratio of medians over UNPAIRED samples of very different size
    (9 EOM rows vs 92 post rows, only 7 mines common). That does not estimate
    per-site restoration efficiency; it conflates clean-up performance with
    which mines happen to appear in which sheet. Corrected 2026-08-05
    (review2.md V-3) to the median of per-mine ratios.

    Numerically the two are close (uranium 0.0659 -> 0.0600), so this is not a
    large shift in the central value -- the point is the SPREAD it exposes:
    per-mine uranium ratios run 0.023 to 0.248, an order of magnitude, which the
    single served value hid entirely.
    """
    geo = load_texas_geochem()
    eom, post = geo["End of Mining"], geo["Final Post-restoration"]

    def _label(d):
        return "Mine" if "Mine" in d.columns else d.columns[1]

    le, lp = _label(eom), _label(post)
    me = eom[le].astype(str).str.strip()
    mp = post[lp].astype(str).str.strip()
    common = sorted(set(me) & set(mp))
    # chloride: excursion-indicator only, same inert-extra-key argument as
    # _EOM_COLS above. The 'Final Post-restoration' sheet does carry Chloride.
    mapping = {"uranium_ppb": "Uranium", "sulfate_mg_l": "Sulfate",
               "tds_mg_l": "TDS", "chloride_mg_l": "Chloride"}
    out = {}
    for key, col in mapping.items():
        ratios = []
        for m in common:
            e = pd.to_numeric(eom.loc[me == m, col], errors="coerce").dropna()
            q = pd.to_numeric(post.loc[mp == m, col], errors="coerce").dropna()
            if len(e) and len(q) and e.median() > 0:
                ratios.append(float(np.clip(q.median() / e.median(), 0.02, 1.0)))
        out[key] = ratios
    return out


def texas_restoration_residual() -> dict[str, float]:
    """Per-species residual source fraction C_rest/C0, as the PAIRED median of
    per-mine ratios (see _paired_residual_ratios). Falls back to config when
    fewer than 3 mines pair."""
    from ml_pipeline.config.parameters import RESTORATION_FALLBACK_RESIDUAL
    out = {}
    for key, ratios in _paired_residual_ratios().items():
        out[key] = (float(np.median(ratios)) if len(ratios) >= 3
                    else RESTORATION_FALLBACK_RESIDUAL[key])
    return out


def texas_restoration_spread() -> dict[str, tuple[float, float]]:
    """Observed (min, max) per-mine restoration ratio per species -- the REAL
    between-site variability, for the Monte Carlo to sample instead of the
    arbitrary x0.7-1.5 jitter that was narrower than reality and not derived
    from it. Returns multiplicative bounds RELATIVE to the paired median."""
    from ml_pipeline.config.parameters import RESTORATION_FALLBACK_RESIDUAL
    out = {}
    for key, ratios in _paired_residual_ratios().items():
        if len(ratios) >= 3:
            med = float(np.median(ratios))
            out[key] = (float(min(ratios)) / med, float(max(ratios)) / med)
        else:
            out[key] = (0.7, 1.5)
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
