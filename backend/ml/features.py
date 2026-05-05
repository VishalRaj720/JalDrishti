"""Feature engineering for Month 4 baseline ML.

`FeatureBuilder` is the single source of truth for the training feature schema
and is reused at inference time by `MLPredictionService`. This guarantees the
feature vector seen at predict time has the same columns / order as training.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# WHO / BIS thresholds (mg/L unless suffixed)
WHO_TDS_LIMIT = 1000.0
WHO_TDS_MARGINAL = 500.0
WHO_URANIUM_PPB_LIMIT = 30.0      # 0.03 mg/L
WHO_URANIUM_PPB_MARGINAL = 15.0
WHO_EC_LIMIT = 3000.0             # µS/cm — saline
WHO_EC_MARGINAL = 1500.0

CONTAMINATION_CLASSES = ["safe", "marginal", "unsafe"]

NUMERIC_FEATURES: List[str] = [
    "porosity",
    "hydraulic_conductivity",
    "transmissivity",
    "specific_yield",
    "storage_coefficient",
    "dtw_decadal_avg",
    "thickness",
    "transmissivity_to_porosity_ratio",
    "distance_to_nearest_isr_km",
    "nearest_isr_injection_rate",
    "well_depth",
    "month",
    "year",
    "vulnerability_proxy",
]

CATEGORICAL_FEATURES: List[str] = [
    "aquifer_type",
    "season",
]

ALL_FEATURES: List[str] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Aquifer type vocabulary mirrors app.models.aquifer.AquiferType
AQUIFER_TYPE_VOCAB = [
    "basalt", "charnockite", "gneiss", "limestone", "sandstone",
    "alluvium", "basement_gneissic_complex", "granite", "intrusive",
    "laterite", "quartzite", "schist", "unknown",
]

SEASON_VOCAB = ["pre_monsoon", "monsoon", "post_monsoon"]


def classify_contamination(
    tds: Optional[float], uranium_ppb: Optional[float], ec_us_cm: Optional[float]
) -> Optional[str]:
    """Return contamination class from any subset of the three indicators.

    Returns None only when ALL three are missing.
    """
    indicators = []
    if tds is not None and not np.isnan(tds):
        if tds > WHO_TDS_LIMIT:
            indicators.append("unsafe")
        elif tds > WHO_TDS_MARGINAL:
            indicators.append("marginal")
        else:
            indicators.append("safe")
    if uranium_ppb is not None and not np.isnan(uranium_ppb):
        if uranium_ppb > WHO_URANIUM_PPB_LIMIT:
            indicators.append("unsafe")
        elif uranium_ppb > WHO_URANIUM_PPB_MARGINAL:
            indicators.append("marginal")
        else:
            indicators.append("safe")
    if ec_us_cm is not None and not np.isnan(ec_us_cm):
        if ec_us_cm > WHO_EC_LIMIT:
            indicators.append("unsafe")
        elif ec_us_cm > WHO_EC_MARGINAL:
            indicators.append("marginal")
        else:
            indicators.append("safe")
    if not indicators:
        return None
    # Worst case wins
    if "unsafe" in indicators:
        return "unsafe"
    if "marginal" in indicators:
        return "marginal"
    return "safe"


def month_to_season(month: int) -> str:
    if 6 <= month <= 9:
        return "monsoon"
    if 10 <= month <= 12 or month == 1:
        return "post_monsoon"
    return "pre_monsoon"


@dataclass
class RawSampleRow:
    """Schema of the joined dataframe pulled from DB (one row per water sample)."""
    sample_id: str
    well_id: str
    sampled_at: pd.Timestamp
    well_depth: Optional[float]
    well_lat: float
    well_lon: float

    aquifer_type: Optional[str]
    porosity: Optional[float]
    hydraulic_conductivity: Optional[float]
    transmissivity: Optional[float]
    specific_yield: Optional[float]
    storage_coefficient: Optional[float]
    dtw_decadal_avg: Optional[float]
    aquifer_min_depth: Optional[float]
    aquifer_max_depth: Optional[float]

    distance_to_nearest_isr_km: Optional[float]
    nearest_isr_injection_rate: Optional[float]

    tds_mg_l: Optional[float]
    ec_us_cm: Optional[float]
    uranium_ppb: Optional[float]


class FeatureBuilder:
    """Stateless transformer: raw joined dataframe -> (X, y_reg, y_clf, meta)."""

    EPS = 1e-6

    @staticmethod
    def derive_features(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        # thickness
        out["thickness"] = (
            out["aquifer_max_depth"].astype(float) - out["aquifer_min_depth"].astype(float)
        )

        # T/n ratio — robust to zero/None porosity
        out["transmissivity_to_porosity_ratio"] = out["transmissivity"] / (
            out["porosity"].fillna(0.0) + FeatureBuilder.EPS
        )

        # vulnerability proxy: high T and low distance => more vulnerable
        out["vulnerability_proxy"] = (
            1.0 / (out["transmissivity"].fillna(out["transmissivity"].median()) + FeatureBuilder.EPS)
        ) * (
            1.0 / (out["distance_to_nearest_isr_km"].fillna(50.0) + FeatureBuilder.EPS)
        )

        # temporal
        ts = pd.to_datetime(out["sampled_at"], utc=True, errors="coerce")
        out["month"] = ts.dt.month.fillna(6).astype(int)
        out["year"] = ts.dt.year.fillna(ts.dt.year.median() if ts.notna().any() else 2024).astype(int)
        out["season"] = out["month"].apply(month_to_season)

        # impute TDS from EC if missing (0.65 conversion factor)
        ec = out["ec_us_cm"].astype(float)
        tds = out["tds_mg_l"].astype(float)
        out["tds_mg_l"] = tds.where(tds.notna(), 0.65 * ec)

        # categorical fillna
        out["aquifer_type"] = out["aquifer_type"].fillna("unknown").astype(str).str.lower()
        out.loc[~out["aquifer_type"].isin(AQUIFER_TYPE_VOCAB), "aquifer_type"] = "unknown"

        return out

    @staticmethod
    def split_xy(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.DataFrame]:
        """Returns (X, y_regression, y_classification, meta_df)."""
        df = FeatureBuilder.derive_features(df)

        # classification target
        df["contamination_class"] = df.apply(
            lambda r: classify_contamination(
                r.get("tds_mg_l"), r.get("uranium_ppb"), r.get("ec_us_cm")
            ),
            axis=1,
        )

        # drop rows with no usable target signal at all
        usable = df["contamination_class"].notna() & df["tds_mg_l"].notna()
        df = df[usable].reset_index(drop=True)

        # ensure all expected feature columns are present
        for col in NUMERIC_FEATURES:
            if col not in df.columns:
                df[col] = np.nan
        for col in CATEGORICAL_FEATURES:
            if col not in df.columns:
                df[col] = "unknown"

        X = df[ALL_FEATURES].copy()
        y_reg = df["tds_mg_l"].astype(float)
        y_clf = df["contamination_class"].astype(str)
        meta = df[["sample_id", "well_id", "sampled_at"]].copy()
        return X, y_reg, y_clf, meta


def feature_schema() -> Dict[str, list]:
    """Persisted alongside trained models so MLPredictionService can rebuild
    feature vectors with the exact same columns / categorical vocab."""
    return {
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "all_features": ALL_FEATURES,
        "aquifer_type_vocab": AQUIFER_TYPE_VOCAB,
        "season_vocab": SEASON_VOCAB,
        "classification_classes": CONTAMINATION_CLASSES,
        "thresholds": {
            "tds_unsafe": WHO_TDS_LIMIT,
            "tds_marginal": WHO_TDS_MARGINAL,
            "uranium_ppb_unsafe": WHO_URANIUM_PPB_LIMIT,
            "uranium_ppb_marginal": WHO_URANIUM_PPB_MARGINAL,
            "ec_unsafe": WHO_EC_LIMIT,
            "ec_marginal": WHO_EC_MARGINAL,
        },
    }
