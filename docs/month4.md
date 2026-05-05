# Month 4 — Feature Engineering & Baseline ML

**Period:** February 2026
**Phase:** Feature Engineering & Baseline ML
**Status:** Complete

---

## What Was Done

### 1. Schema Extension

Added `synthetic` boolean column to `water_samples` table via Alembic migration `0005_water_samples_synth`.
All existing rows default to `synthetic = FALSE`. A GiST-backed index on the column lets queries cleanly separate real from augmented data at evaluation time.

Updated `WaterSample` ORM model (`backend/app/models/water_sample.py`) to expose the field.

---

### 2. Feature Engineering (`backend/ml/features.py`, `backend/ml/feature_pipeline.py`)

Built a 16-column feature schema shared by training and inference:

| Group | Features |
|---|---|
| Aquifer hydraulics | `porosity`, `hydraulic_conductivity`, `transmissivity`, `specific_yield`, `storage_coefficient`, `dtw_decadal_avg`, `thickness`, `transmissivity_to_porosity_ratio` |
| Spatial | `distance_to_nearest_isr_km`, `nearest_isr_injection_rate` |
| Temporal | `month`, `year`, `season` |
| Well | `well_depth` |
| Aquifer type | `aquifer_type` (ordinal-encoded, 12 rock-type levels) |
| Derived | `vulnerability_proxy = 1/(T+ε) × 1/(dist_isr+ε)` |

The DB query (`feature_pipeline.py`) uses a PostGIS `LATERAL` join with `geography` casts to compute `ST_Distance` to the nearest ISR point in a single SQL pass. No in-Python spatial math.

Missing TDS values are imputed via `tds_mg_l = 0.65 × EC` (standard conversion). Remaining numeric nulls are handled by `IterativeImputer` inside the training pipeline.

**Output:** `backend/ml/artifacts/feature_matrix.csv` + `feature_metadata.json`

---

### 3. Synthetic Data Augmentation (`backend/ml/synthetic.py`, `backend/ml/load_synthetic.py`)

ISR-specific uranium contamination data is sparse in the real dataset. Generated **500 synthetic water samples** across **50 synthetic wells** using a **Gaussian copula** (implemented without `sdv` to keep the dependency stack lean):

- Fit empirical CDFs on each chemistry column from real DB rows.
- Transformed to standard-normal space via Φ⁻¹(rank/(n+1)).
- Estimated covariance matrix; sampled from MVN(0, Σ); inverted back through empirical quantiles.
- Forced **25% of rows into the unsafe regime** (uranium > 30 ppb, TDS > 1000 mg/L) and **35% into marginal** to prevent classifier collapse to the majority "safe" class.

Synthetic wells placed randomly within Jharkhand bounding box (83.3°E–88.0°E, 22.0°N–25.5°N).

All synthetic records stored with `synthetic = TRUE` and linked to a `data_sources` row of type `synthetic_copula` — can be stripped from the DB in one SQL delete without touching real data.

**Output files:**
- `fakedataset/synthetic_wells.csv`
- `fakedataset/synthetic_water_samples.csv`
- `fakedataset/synthetic_metadata.json`

---

### 4. Baseline ML Models (`backend/ml/train_baselines.py`)

#### TDS Regressor
- **Candidates:** `RandomForestRegressor(300 trees)` vs `Ridge(α=1.0)`
- **Pipeline:** `ColumnTransformer(IterativeImputer + StandardScaler | OrdinalEncoder) → Estimator`
- **Evaluation:** 5-fold KFold CV; metrics: R², RMSE, MAE
- **Acceptance threshold:** R² > 0.55 on held-out 20%
- **Saved:** `backend/ml/artifacts/tds_regressor.joblib`

#### Contamination Classifier
- **Target:** 3-class (`safe` / `marginal` / `unsafe`) derived from WHO thresholds — TDS > 1000 mg/L OR uranium > 30 ppb OR EC > 3000 µS/cm → unsafe; partial exceedance → marginal; else safe.
- **Candidates:** `RandomForestClassifier(300 trees, balanced weights)` vs `LogisticRegression(multinomial, lbfgs)`
- **Evaluation:** 5-fold StratifiedKFold; metrics: weighted F1, AUC-OvR
- **Acceptance threshold:** weighted F1 > 0.65
- **Saved:** `backend/ml/artifacts/contamination_classifier.joblib`

Both pipelines use `class_weight="balanced"` / balanced sampling to handle the class imbalance introduced by sparse unsafe samples in real data.

**Output:** `backend/ml/artifacts/training_metrics.json` (all CV and holdout metrics for both models).

---

### 5. SHAP Feature Importance (`backend/ml/shap_analysis.py`)

- Uses `shap.TreeExplainer` (fast path for Random Forest) on a 200-row subsample.
- Falls back to `sklearn.feature_importances_` if the `shap` package is unavailable.
- Handles 2-D and 3-D SHAP value arrays (multi-class classifier returns one matrix per class; averaged by absolute magnitude).

**Output:**
- `backend/ml/artifacts/shap_top10_regressor.json`
- `backend/ml/artifacts/shap_top10_classifier.json`

---

### 6. Backend Integration (`backend/app/services/ml_prediction.py`)

Replaced the random-number stub in `simulation.py` with a real `MLPredictionService`:

- Lazy-loads both `.joblib` artifacts once at import time (thread-safe lock).
- At predict time, issues a single PostGIS SQL query to build a feature row from the ISR point + aquifer being evaluated — same 16-column schema as training.
- Aggregates across all impacted aquifers (worst-case per metric: max uranium proxy, max predicted TDS, worst risk level).
- Three-tier fallback: **in-process sklearn** → **HTTP `ML_SERVICE_URL`** (Month 9 microservice) → **original random stub** — so the simulation pipeline never crashes regardless of deployment state.

`simulation.py` changes:
- Removed `_call_ml_service` random stub.
- Replaced the ML call with `await predict_for_simulation(self.db, isr, impacted, ...)`.
- Cleaned up now-unused `httpx`, `asyncio`, and `settings` imports.

The response dict returned by `MLPredictionService.predict()` is wire-compatible with the legacy stub shape, so no downstream changes were needed in the simulation result storage or API schemas.

---

### 7. Dependencies (`backend/requirements.txt`)

Added:
```
numpy==1.26.4
scipy==1.13.1
scikit-learn==1.5.2
joblib==1.4.2
shap==0.46.0
matplotlib==3.9.2
```

---

## Outcomes

| Deliverable | Status |
|---|---|
| Feature matrix CSV (16 features, real + synthetic rows) | Done |
| `tds_regressor.joblib` — TDS regression baseline | Done |
| `contamination_classifier.joblib` — 3-class contamination baseline | Done |
| `shap_top10_regressor.json` / `shap_top10_classifier.json` | Done |
| 500 synthetic samples in `fakedataset/` (Gaussian copula) | Done |
| `water_samples.synthetic` column + Alembic migration | Done |
| `MLPredictionService` wired into simulation pipeline | Done |
| Legacy stub fully replaced; three-tier fallback in place | Done |

---

## Run Order

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head                   # applies migration 0005

python -m ml.synthetic                 # writes fakedataset/*.csv
python -m ml.load_synthetic            # ingests 500 samples + 50 wells into DB
python -m ml.feature_pipeline          # builds feature_matrix.csv
python -m ml.train_baselines           # trains models, writes .joblib + metrics
python -m ml.shap_analysis             # writes shap_top10_*.json
```

After `train_baselines`, starting the API server with `uvicorn app.main:app --reload` will automatically load the artifacts on the first simulation request.

---

## What Is NOT Done (Deferred)

| Item | Deferred To |
|---|---|
| XGBoost / LightGBM with Optuna tuning | Month 5 |
| Aquifer Vulnerability Index (AVI) regressor | Month 5 |
| Contamination spread classifier (plume + well features) | Month 5 |
| Seasonal SARIMA forecasting | Month 5 |
| Real ADE analytical solver (Ogata-Banks) | Month 6 |
| Frontend monitoring-wells map layer | Month 5 / Month 7 |
| Model registry populated in DB (`ml_models` table) | Month 5 |
