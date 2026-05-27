"""
generate_dataset.py
-------------------
Step 1 + Step 2 of the JalDrishti MVP pipeline.

1. Loads the REAL USGS Texas ISR groundwater dataset (TX_ISR_Final.xlsx)
2. Extracts per-phase distributions (Baseline / End-of-Mining / Post-restoration)
3. Generates a larger synthetic dataset that:
     - preserves real chemistry distributions and correlations
     - adds 6 ISR-context features (lat/lon, distance, depth, K, porosity, rainfall, season)
     - simulates ISR-proximity contamination spread
     - assigns risk_level labels (0/1/2) from a transparent rule

Output: synthetic_isr_dataset.csv
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(seed=42)
BASE_DIR = Path(__file__).resolve().parent

# ----------------------------------------------------------------------
# 1. LOAD + CLEAN THE REAL DATASET
# ----------------------------------------------------------------------
SOURCE_XLSX = BASE_DIR / "Real_dataset" / "Dataset_1" / "TX_ISR_Final.xlsx"

NUM_COLS = [
    "Calcium", "Magnesium", "Sodium", "Potassium", "Bicarbonate",
    "Sulfate", "Chloride", "Fluoride", "Nitrate-N", "Silica",
    "pH", "TDS", "Conductivity", "Alkalinity",
    "Arsenic", "Cadmium", "Iron", "Lead", "Manganese",
    "Selenium", "Ammonia-N", "Uranium", "Molybdenum", "Radium-226",
]


def _coerce(v):
    """Convert messy strings like '<.001', '1044+/-5', 'nan' to floats."""
    if pd.isna(v):
        return np.nan
    s = str(v).strip()
    if s == "" or s.lower() == "nan":
        return np.nan
    m = re.match(r"^<\s*(\d*\.?\d+)$", s)          # '<.001' -> 0.0005
    if m:
        return float(m.group(1)) / 2.0
    m = re.match(r"^(-?\d*\.?\d+)\s*\+/?-\s*\d*\.?\d+$", s)  # '1044+/-5' -> 1044
    if m:
        return float(m.group(1))
    try:
        return float(s)
    except ValueError:
        return np.nan


def _load_sheet(sheet, header_row):
    df = pd.read_excel(SOURCE_XLSX, sheet_name=sheet, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[~df["Mine"].astype(str).str.contains(
        "Post-restoration|Baseline|Groundwater", na=False, regex=True)]
    df = df[df["Mine"].astype(str).str.lower() != "mine"]
    df = df[df["Mine"].notna()].reset_index(drop=True)
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = df[c].apply(_coerce)
    # fix obvious pH outliers (data-entry errors)
    if "pH" in df.columns:
        df.loc[(df["pH"] < 1) | (df["pH"] > 14), "pH"] = np.nan
    return df


def load_real_data():
    baseline = _load_sheet("Baseline", header_row=2)
    mining   = _load_sheet("End of Mining", header_row=1)
    post     = _load_sheet("Final Post-restoration", header_row=0)
    return baseline, mining, post


# ----------------------------------------------------------------------
# 2. BUILD REAL ROWS IN OUR TARGET SCHEMA
# ----------------------------------------------------------------------
# Mapping: our spec feature  ->  column in TX dataset
FEATURE_MAP = {
    "pH":         "pH",
    "EC":         "Conductivity",
    "TDS":        "TDS",
    "sulfate":    "Sulfate",
    "nitrate":    "Nitrate-N",
    "chloride":   "Chloride",
    "iron":       "Iron",
    "manganese":  "Manganese",
    "arsenic":    "Arsenic",
}

# Jharkhand-ish synthetic geographic context (East Singhbhum uranium belt)
JK_LAT_MIN, JK_LAT_MAX = 22.4, 22.9
JK_LON_MIN, JK_LON_MAX = 86.0, 86.6
SEASONS = ["pre-monsoon", "monsoon", "post-monsoon", "winter"]


def _random_context(n, phase):
    """Generate ISR/hydrogeological context columns for n rows.

    Distance is drawn so that 'mining' rows tend to be CLOSE to ISR, baseline rows
    tend to be FAR, and post-restoration rows are intermediate. This mirrors
    physical reality: post-mining wells are by definition near the field.
    """
    lat = RNG.uniform(JK_LAT_MIN, JK_LAT_MAX, n)
    lon = RNG.uniform(JK_LON_MIN, JK_LON_MAX, n)

    if phase == "baseline":
        # Mostly far, some near (baseline measured before mining anywhere)
        distance = RNG.lognormal(mean=np.log(8.0), sigma=0.6, size=n).clip(0.2, 25)
    elif phase == "mining":
        distance = RNG.lognormal(mean=np.log(1.0), sigma=0.5, size=n).clip(0.1, 5)
    else:  # post
        distance = RNG.lognormal(mean=np.log(2.5), sigma=0.7, size=n).clip(0.2, 12)

    # Crystalline / sandstone aquifer ranges (AquiParameter / GLHYMPS)
    depth = RNG.uniform(5, 60, n)                       # m below ground
    K     = RNG.lognormal(np.log(2.0), 0.9, n).clip(0.05, 50)   # m/day
    poro  = RNG.normal(0.25, 0.06, n).clip(0.10, 0.40)
    season = RNG.choice(SEASONS, size=n, p=[0.25, 0.30, 0.25, 0.20])
    # Rainfall depends on season (Jharkhand IMD typical annual ~1200 mm)
    rain_base = {"pre-monsoon": 60, "monsoon": 350, "post-monsoon": 90, "winter": 25}
    rainfall = np.array([rain_base[s] for s in season]) + RNG.normal(0, 30, n)
    rainfall = rainfall.clip(0, None)
    return lat, lon, distance, depth, K, poro, rainfall, season


def _to_target_schema(real_df, phase):
    """Convert one of the real sheets to the unified target schema."""
    n = len(real_df)
    if n == 0:
        return pd.DataFrame()

    out = pd.DataFrame(index=range(n))
    for our, theirs in FEATURE_MAP.items():
        out[our] = real_df[theirs].astype(float).values if theirs in real_df.columns else np.nan

    lat, lon, dist, depth, K, poro, rain, season = _random_context(n, phase)
    out["latitude"]              = lat
    out["longitude"]             = lon
    out["distance_from_isr"]     = dist
    out["groundwater_depth"]     = depth
    out["rainfall"]              = rain
    out["hydraulic_conductivity"] = K
    out["porosity"]              = poro
    out["season"]                = season
    out["phase"]                 = phase             # bookkeeping only
    out["synthetic_data"]        = False
    return out


# ----------------------------------------------------------------------
# 3. SYNTHETIC ROW GENERATOR
# ----------------------------------------------------------------------
def _phase_stats(df, col):
    """Return (median, lo, hi) for log-normal-like sampling, robust to NaNs."""
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(s) < 3:
        return None
    return float(np.log(s.clip(lower=1e-6).median())), float(s.clip(lower=1e-6).std())


def generate_synthetic(real_baseline, real_mining, real_post,
                       n_safe=2000, n_med=1500, n_high=1500):
    """Draw synthetic rows in each risk class, with statistics grounded in the
    corresponding real phase.

      safe   -> baseline phase (far from ISR, clean chemistry)
      medium -> post-restoration phase (intermediate, residual contamination)
      high   -> end-of-mining phase (close to ISR, peak contamination)
    """
    sources = {
        "safe":   (real_baseline, "baseline", n_safe),
        "medium": (real_post,     "post",     n_med),
        "high":   (real_mining,   "mining",   n_high),
    }

    rows = []
    for risk_class, (src_df, phase, n) in sources.items():
        # Pre-compute log-normal sampling params for each chemistry feature
        params = {}
        for col_our in FEATURE_MAP.keys():
            col_real = FEATURE_MAP[col_our]
            s = pd.to_numeric(src_df[col_real], errors="coerce").dropna()
            if len(s) < 3:
                params[col_our] = None
                continue
            if col_our == "pH":
                # pH is roughly normal; sample directly
                params[col_our] = ("normal", s.mean(), max(s.std(), 0.2))
            else:
                # Log-normal for concentrations
                logvals = np.log(s.clip(lower=1e-6))
                params[col_our] = ("lognormal", logvals.mean(), max(logvals.std(), 0.3))

        # Geographic / hydro context
        lat, lon, dist, depth, K, poro, rain, season = _random_context(n, phase)

        synth = pd.DataFrame(index=range(n))
        for col, p in params.items():
            if p is None:
                synth[col] = np.nan
                continue
            kind, m, sd = p
            if kind == "normal":
                vals = RNG.normal(m, sd, n)
                synth[col] = np.clip(vals, 5.5, 9.5)   # pH physical bounds
            else:
                vals = np.exp(RNG.normal(m, sd, n))
                synth[col] = vals

        # --- physical coupling: enforce real correlations ---
        # 1) EC ~ TDS (real corr ≈ 0.96). Override EC from TDS with noise.
        synth["EC"] = synth["TDS"] * RNG.normal(1.65, 0.15, n)
        synth["EC"] = synth["EC"].clip(lower=50)

        # 2) Distance attenuation: contaminants decay with distance from ISR.
        #    Apply for medium/high classes (the source is the ISR field).
        if risk_class in ("medium", "high"):
            # decay factor: 1.0 at 0 km, ~0.3 at 5 km, ~0.05 at 15 km
            decay = np.exp(-dist / 4.5)
            # baseline level to fall back to (clean groundwater)
            base = {"sulfate": 100, "TDS": 800, "EC": 1500, "iron": 0.2,
                    "manganese": 0.05, "arsenic": 0.01, "nitrate": 0.5,
                    "chloride": 400}
            for c, b in base.items():
                synth[c] = b + (synth[c] - b) * decay
            # pH partially returns to neutral with distance
            synth["pH"] = 7.8 + (synth["pH"] - 7.8) * decay

        # 3) Hydraulic conductivity amplifies plume reach.
        #    A high-K aquifer means the same distance shows MORE contamination.
        if risk_class in ("medium", "high"):
            k_factor = (K / 2.0) ** 0.3        # gentle multiplier
            for c in ["sulfate", "TDS", "EC", "iron", "manganese", "arsenic"]:
                synth[c] = synth[c] * k_factor

        # 4) Monsoon dilutes; pre-monsoon concentrates (factor 0.85 / 1.15)
        season_factor = np.where(season == "monsoon", 0.85,
                          np.where(season == "pre-monsoon", 1.15, 1.0))
        for c in ["TDS", "EC", "sulfate", "chloride", "nitrate"]:
            synth[c] = synth[c] * season_factor

        # Add context columns
        synth["latitude"]              = lat
        synth["longitude"]             = lon
        synth["distance_from_isr"]     = dist
        synth["groundwater_depth"]     = depth
        synth["rainfall"]              = rain
        synth["hydraulic_conductivity"] = K
        synth["porosity"]              = poro
        synth["season"]                = season
        synth["phase"]                 = phase
        synth["synthetic_data"]        = True
        synth["_intended_class"]       = risk_class  # for sanity check only
        rows.append(synth)

    return pd.concat(rows, ignore_index=True)


# ----------------------------------------------------------------------
# 4. RISK LABELING (transparent rule)
# ----------------------------------------------------------------------
# Thresholds informed by:
#  - WHO/BIS drinking water standards (TDS 500/2000 mg/L, sulfate 250/400, Fe 0.3, Mn 0.1, As 0.01)
#  - USGS Texas ISR observed end-of-mining medians (sulfate ~1100, TDS ~3700, U ~12 mg/L)
def _score_row(r):
    score = 0
    # pH outside 6.5-8.5 is suspicious
    if pd.notna(r["pH"]) and (r["pH"] < 6.5 or r["pH"] > 8.5):
        score += 1
    # TDS
    if pd.notna(r["TDS"]):
        if r["TDS"] > 3000: score += 2
        elif r["TDS"] > 1500: score += 1
    # EC (correlated with TDS but use independently if TDS missing)
    if pd.notna(r["EC"]):
        if r["EC"] > 4500: score += 2
        elif r["EC"] > 2500: score += 1
    # Sulfate (lixiviant residue is the cleanest single ISR signal)
    if pd.notna(r["sulfate"]):
        if r["sulfate"] > 600: score += 2
        elif r["sulfate"] > 250: score += 1
    # Heavy metals
    if pd.notna(r["iron"]) and r["iron"] > 1.0: score += 1
    if pd.notna(r["manganese"]) and r["manganese"] > 0.3: score += 1
    if pd.notna(r["arsenic"]) and r["arsenic"] > 0.05: score += 2
    if pd.notna(r["arsenic"]) and r["arsenic"] > 0.01: score += 1
    # Proximity
    if r["distance_from_isr"] < 1.5: score += 2
    elif r["distance_from_isr"] < 5: score += 1
    # High-K aquifer increases vulnerability
    if r["hydraulic_conductivity"] > 10: score += 1

    if score >= 7:  return 2   # high
    if score >= 4:  return 1   # medium
    return 0                    # low


def assign_risk(df):
    df["risk_level"] = df.apply(_score_row, axis=1).astype(int)
    return df


# ----------------------------------------------------------------------
# 5. MAIN
# ----------------------------------------------------------------------
def main():
    print("Loading real USGS Texas ISR data…")
    baseline, mining, post = load_real_data()
    print(f"  baseline n={len(baseline)}  mining n={len(mining)}  post n={len(post)}")

    print("\nConverting real rows to target schema…")
    real_rows = pd.concat([
        _to_target_schema(baseline, "baseline"),
        _to_target_schema(mining,   "mining"),
        _to_target_schema(post,     "post"),
    ], ignore_index=True)
    print(f"  total real rows: {len(real_rows)}")

    print("\nGenerating synthetic rows…")
    synth_rows = generate_synthetic(baseline, mining, post,
                                    n_safe=2000, n_med=1500, n_high=1500)
    print(f"  total synthetic rows: {len(synth_rows)}")

    # Drop helper col before merge
    synth_rows = synth_rows.drop(columns=["_intended_class"])

    full = pd.concat([real_rows, synth_rows], ignore_index=True)

    # Order columns per the spec, then meta
    ordered = ["latitude","longitude","distance_from_isr","groundwater_depth",
               "pH","EC","TDS","sulfate","nitrate","chloride","iron",
               "manganese","arsenic","rainfall","hydraulic_conductivity",
               "porosity","season","phase","synthetic_data"]
    full = full[ordered]

    print("\nAssigning risk labels…")
    full = assign_risk(full)

    out = Path(__file__).parent / "synthetic_isr_dataset.csv"
    full.to_csv(out, index=False)
    print(f"\nSaved -> {out}  (shape={full.shape})")

    print("\nClass distribution:")
    print(full["risk_level"].value_counts().sort_index()
          .rename({0:"Low",1:"Medium",2:"High"}).to_string())
    print("\nReal vs synthetic:")
    print(full["synthetic_data"].value_counts().to_string())


if __name__ == "__main__":
    main()
