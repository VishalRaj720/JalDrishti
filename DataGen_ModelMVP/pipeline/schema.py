"""schema.py — the single source of truth for the unified dataset.

Every loader, the synthetic generator, and the trainer import from here so that
column names, units, and the risk rule can never drift apart again (the old
`generate_dataset.py` and `backend/ml/features.py` disagreed on all three).

UNITS (fixed for the whole project)
-----------------------------------
    uranium_ppb            micrograms / litre   (Texas mg/L is x1000 -> ppb)
    tds_mg_l, sulfate_mg_l milligrams / litre
    ph                     standard units
    *_m, *_km, depth       metres / kilometres
    transmissivity         m^2 / day
    hydraulic_conductivity m / day
    injection_rate_gpm     US gallons / minute  (Texas IAEA_FlowRate)
    ore_grade_pct          % U3O8

WHO / BIS drinking-water thresholds drive the risk label.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

# --- WHO / BIS thresholds -------------------------------------------------
URANIUM_UNSAFE_PPB = 30.0      # WHO provisional guideline 0.030 mg/L
URANIUM_MARGINAL_PPB = 15.0    # below-guideline watch band
TDS_UNSAFE_MGL = 1000.0        # BIS permissible (no alt source)
TDS_MARGINAL_MGL = 500.0       # BIS acceptable
SULFATE_UNSAFE_MGL = 400.0     # BIS permissible
SULFATE_MARGINAL_MGL = 250.0   # BIS acceptable

RISK_CLASSES = ["safe", "marginal", "unsafe"]
PROVENANCE = ["texas_real", "jharkhand_real", "synthetic"]
PHASES = ["baseline", "mining", "post"]
SEASONS = ["pre_monsoon", "monsoon", "post_monsoon", "winter"]

# --- Column groups --------------------------------------------------------
# Model INPUTS (what a stakeholder/scenario supplies + spatial join provides)
NUMERIC_FEATURES = [
    "distance_from_isr_km",
    "days_since_injection",
    "injection_rate_gpm",
    "ore_grade_pct",
    "aquifer_transmissivity_m2day",
    "aquifer_hydraulic_conductivity_mday",
    "aquifer_porosity",
    "aquifer_specific_yield_pct",
    "depth_to_water_m",
    "aquifer_thickness_m",
    "rainfall_mm",
]
CATEGORICAL_FEATURES = ["aquifer_type", "season"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Prediction TARGETS
PRIMARY_TARGET = "uranium_ppb"
# Co-targets transferable across BOTH datasets (present in Texas AND Jharkhand)
CO_TARGETS = ["tds_mg_l", "sulfate_mg_l", "ph"]
# Carried for completeness but NOT locally validated (empty in the Jharkhand CSV).
# Available Texas-side / synthetic only — never claimed as Jharkhand ground truth.
TX_ONLY_CHEM = ["iron_mg_l", "arsenic_ppb"]
REGRESSION_TARGETS = [PRIMARY_TARGET] + CO_TARGETS
CLASSIFICATION_TARGET = "risk_class"

# Bookkeeping columns
META_COLS = ["data_source", "phase", "latitude", "longitude", "mine"]

# Full unified column order
UNIFIED_COLUMNS = (
    META_COLS
    + ALL_FEATURES
    + REGRESSION_TARGETS
    + TX_ONLY_CHEM
    + [CLASSIFICATION_TARGET]
)


def _band(value: Optional[float], marginal: float, unsafe: float) -> Optional[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if value > unsafe:
        return "unsafe"
    if value > marginal:
        return "marginal"
    return "safe"


def derive_risk_class(
    uranium_ppb: Optional[float],
    tds_mg_l: Optional[float] = None,
    sulfate_mg_l: Optional[float] = None,
) -> Optional[str]:
    """Uranium-led, worst-case risk class.

    Uranium is the primary ISR contaminant and dominates the label; TDS and
    sulfate (lixiviant residue) act as supporting indicators. Returns None only
    when every indicator is missing.
    """
    bands = [
        _band(uranium_ppb, URANIUM_MARGINAL_PPB, URANIUM_UNSAFE_PPB),
        _band(tds_mg_l, TDS_MARGINAL_MGL, TDS_UNSAFE_MGL),
        _band(sulfate_mg_l, SULFATE_MARGINAL_MGL, SULFATE_UNSAFE_MGL),
    ]
    bands = [b for b in bands if b is not None]
    if not bands:
        return None
    if "unsafe" in bands:
        return "unsafe"
    if "marginal" in bands:
        return "marginal"
    return "safe"


def assign_risk_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add/overwrite `risk_class` from the chemistry columns."""
    df[CLASSIFICATION_TARGET] = df.apply(
        lambda r: derive_risk_class(
            r.get(PRIMARY_TARGET), r.get("tds_mg_l"), r.get("sulfate_mg_l")
        ),
        axis=1,
    )
    return df


def month_to_season(month: int) -> str:
    """Jharkhand IMD seasons."""
    if 3 <= month <= 5:
        return "pre_monsoon"
    if 6 <= month <= 9:
        return "monsoon"
    if 10 <= month <= 11:
        return "post_monsoon"
    return "winter"  # Dec-Feb
