# JalDrishti unified ML pipeline (Month 1)

This package replaces the two earlier, disconnected pipelines
(`DataGen_ModelMVP/generate_dataset.py` + `ML_model.py`, and `backend/ml/*`)
with **one schema, one generation methodology, and uranium concentration as the
real prediction target** — sourced from real ISR data rather than a proxy.

The old scripts are left in place untouched; nothing here deletes them.

## What it predicts (Objective 1)

Given a hypothetical uranium **ISR injection point** and a query
`(distance, time)`, the models predict:

| Model | Target | File |
|---|---|---|
| Uranium regressor | `uranium_ppb` (log1p) | `artifacts/uranium_regressor.joblib` |
| Risk classifier | `safe / marginal / unsafe` (WHO-derived) | `artifacts/risk_classifier.joblib` |
| Co-target regressors | `tds_mg_l`, `sulfate_mg_l`, `ph` | `artifacts/cotarget_*.joblib` |

ISR alters more than uranium — it changes TDS, sulfate (lixiviant residue) and
pH too — so those are modelled as co-targets. Iron/arsenic are carried in the
schema but **not modelled**: they are empty in the Jharkhand source, so they
could never be locally validated.

## Data sources — what is REAL vs SYNTHETIC

Every row carries a `data_source` tag. Nothing is silently invented.

| `data_source` | Rows | What it is | Role |
|---|---|---|---|
| `texas_real` | ~131 | USGS Texas ISR chemistry, 3 phases (`TX_ISR_Final.xlsx`) | the real before/during/after **uranium signal** |
| `jharkhand_real` | 342 | CGWB 2023 ambient uranium + chemistry (`waterQuality_jharkhand.csv`) | real **local baseline** (24 districts, incl. 28 in E. Singhbhum) |
| `synthetic` | 3000 | "ISR-in-Jharkhand" counterfactual (`synth.py`) | the **mining/post** scenario that cannot be observed locally |

Synthetic rows are generated for **mining/post phases only**. The baseline class
is covered entirely by real data — we never fabricate observable measurements.

Real grounding inside the synthetic generator:
- **Aquifer hydrogeology** (transmissivity, K, porosity, yield, depth) comes from
  a real point→polygon spatial join against `Aquifers_Jharkhand.geojson`.
- **ISR operating parameters** (injection rate, ore grade, ore porosity) are
  sampled from the real Texas mine-operations tables (`Real_dataset/Dataset 2/`).
- **Per-phase contaminant levels** are anchored to the real Texas phase
  distributions; uranium then decays exponentially with distance, with the plume
  length scaling as √K, plus seasonal dilution.

## Units (fixed project-wide — see `schema.py`)

- `uranium_ppb` — Texas data is mg/L and is multiplied by 1000 to match the
  Jharkhand CGWB ppb scale. **This is the single biggest fix vs. the old code,
  where the real Texas `Uranium` column was loaded then silently dropped.**
- `tds_mg_l`, `sulfate_mg_l` in mg/L; Jharkhand TDS derived as `0.64 × EC`.
- transmissivity m²/day, hydraulic conductivity m/day, distances km.

## How to run

```bash
cd DataGen_ModelMVP
pip install -r ../backend/requirements.txt   # needs pandas, numpy, scikit-learn, shapely, openpyxl
python -m pipeline.build      # -> artifacts/unified_dataset.csv
python -m pipeline.train      # -> artifacts/*.joblib + metrics.json
```

`*.joblib` binaries are git-ignored (regenerate with `train`); the
`unified_dataset.csv`, `feature_schema.json` and `metrics.json` are tracked.

## Honest results (held-out test; see `artifacts/metrics.json`)

Synthetic rows dominate, so we report metrics **both** overall and on real-only
test rows. The real-only number is the one that reflects real-world signal.

| Model | Metric | All test | Real-only test |
|---|---|---|---|
| Uranium regressor | R²(log) | 0.86 | **0.69** |
| Uranium regressor | median abs err | 35 ppb | **3.8 ppb** |
| Risk classifier | macro-F1 | 0.57 | **0.56** |

The classifier detects `unsafe` well (F1 ≈ 0.89) but struggles on the narrow
`marginal` band (F1 ≈ 0.30). The gap between "all" and "real-only" is expected
and is reported deliberately rather than hidden.

## Honest limitations (these feed Objective 2 — data gap analysis)

- **No real Jharkhand ISR ground truth exists** (there is no operating ISR mine
  in Jharkhand). The mining/post signal is transferred from Texas + synthesised;
  it is a defensible analog, not a local measurement.
- The real Jharkhand uranium is **ambient/baseline** only (max 28.5 ppb).
- Heavy metals (Fe, As) and dissolved oxygen are unmeasured in the Jharkhand
  source, so ISR's effect on them cannot be validated locally.
- Water-level station coverage is concentrated in Dhanbad, not the East
  Singhbhum uranium belt, limiting a real hydraulic-gradient estimate there
  (addressed in Month 2 using the supplied DEM + Jaduguda-area stations).
