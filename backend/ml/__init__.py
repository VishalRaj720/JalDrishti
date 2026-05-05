"""JalDrishti ML package — Month 4 baseline models, features, and prediction service.

Pipeline entrypoints (run from `backend/`):
    python -m ml.feature_pipeline      # build feature matrix from DB
    python -m ml.synthetic             # generate fakedataset/synthetic_*.csv
    python -m ml.load_synthetic        # load synthetic CSV into DB
    python -m ml.train_baselines       # train + evaluate + save .joblib
    python -m ml.shap_analysis         # SHAP plots + top-10 features

Artifacts land in backend/ml/artifacts/.
"""
from pathlib import Path

ML_PACKAGE_DIR = Path(__file__).resolve().parent
ARTIFACTS_DIR = ML_PACKAGE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

REPO_ROOT = ML_PACKAGE_DIR.parents[1]
FAKEDATASET_DIR = REPO_ROOT / "fakedataset"
