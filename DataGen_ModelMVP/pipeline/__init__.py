"""JalDrishti unified ML pipeline (Month 1).

One schema, one generation methodology, uranium as the real prediction target.

Modules
-------
schema   : single source of truth for columns, units, thresholds, risk rule
sources  : loaders for the four REAL data sources (Texas ISR chemistry,
           Texas mine operations, Jharkhand CGWB quality, Jharkhand aquifers)
synth    : physically-grounded "ISR-in-Jharkhand" counterfactual generator
build    : assembles texas_real + jharkhand_real + synthetic -> unified_dataset.csv
train    : uranium regressor + risk classifier + co-target regressors

Run order
---------
    python -m pipeline.build      # -> artifacts/unified_dataset.csv
    python -m pipeline.train      # -> artifacts/*.joblib + metrics.json
"""
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PKG_ROOT = PIPELINE_DIR.parent                      # DataGen_ModelMVP/
REAL_DIR = PKG_ROOT / "Real_dataset"
REPO_ROOT = PKG_ROOT.parent                          # JalDrishti/
DATASETS_DIR = REPO_ROOT / "Datasets"
ARTIFACTS_DIR = PIPELINE_DIR / "artifacts"

# Real source paths
TEXAS_XLSX = REAL_DIR / "Dataset_1" / "TX_ISR_Final.xlsx"
MINE_OPS_DIR = REAL_DIR / "Dataset 2"
JHARKHAND_QUALITY_CSV = DATASETS_DIR / "waterQuality_jharkhand.csv"
AQUIFERS_GEOJSON = DATASETS_DIR / "Aquifers_Jharkhand.geojson"

SEED = 42
