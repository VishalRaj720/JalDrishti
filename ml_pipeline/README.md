# ml_pipeline — Physics-Informed ISR Plume Surrogate (Texas → Jharkhand domain adaptation)

A **standalone** redesign (isolated from `DataGen_ModelMVP/`, "approach 1") that maps
real Texas alkaline-ISR groundwater data onto Jharkhand's variable hydrogeology and
predicts the spatiotemporal footprint of a *hypothetical* ISR uranium operation dropped
anywhere in the state.

The transfer problem — uniform Texas sandstone (porous flow) vs. Jharkhand's fractured
crystalline basement / weathered mantle — is solved by **normalizing the physics into
scale-independent dimensionless groups** instead of feeding raw coordinates to the model.

```
ml_pipeline/
├── config/parameters.py          # single source of truth: constants + CITED literature values
├── data_prep/
│   ├── texas_loader.py           # parse TX_ISR_Final.xlsx (messy multi-header) + Dataset 2 CSVs
│   ├── jharkhand_loader.py       # parse aquifer geojson + waterQuality csv; derive K=T/b; pin lookup
│   └── feature_engineering.py    # PHASE 1: dimensionless transport features (the domain bridge)
├── physics/transport.py          # PHASE 2a: vectorized analytical ADE (Domenico) engine
├── synthetic/generate.py         # PHASE 2b: statewide synthetic training-data loop
├── ml/                           # PHASE 3: physics-guided XGBoost (GroupKFold +
│   │                             #   monotone constraints + conformal quantiles)
│   ├── dataset.py                #   feature contract + MONOTONE_MAP (hydrogeology laws)
│   ├── train.py                  #   GroupKFold CV, quantile heads, CQR, breach/P_ex
│   ├── predict.py                #   unified API: analytical vs ML surrogate (Phase-4 toggle)
│   └── shap_analysis.py          #   SHAP feature attribution
├── dashboard/                    # PHASE 4 (next): Streamlit "drop a pin" UI
└── outputs/                      # generated artifacts (gitignored)
```

## What maps to what (from YOUR files — nothing assumed)

| Physics quantity | Source column (real) | Derivation |
|---|---|---|
| Texas matrix porosity φ | `AquiferExemptions.OrePorosity` (28–40%) | direct |
| Texas K | `AquiferExemptions.FormPerm` (5000 mD) | `K = k·ρg/μ` |
| Texas Q_in/Q_out, pore vols | `Restoration.{VolWaterInjected,VolWaterExtract,Days,PoreVolumeOfArea}` | volumetric |
| Alkaline lixiviant ✓ | `TexasISROperations.Leachant` = NaHCO₃/Na₂CO₃ | confirms low-U-retardation regime |
| Source signature C₀(U,SO₄,TDS) | `End of Mining` sheet (excursion concentrations) | quantiles |
| Jharkhand transmissivity T | `Aquifers_Jharkhand.m2_perday` | direct |
| Jharkhand zone thickness b | `Aquifers_Jharkhand.zone_m` | direct |
| **Jharkhand K** | derived | **K = T / b** |
| Jharkhand mobile porosity | `Aquifers_Jharkhand.yeild__` (specific yield) | Sy → φ_mobile |
| Fractured vs porous regime | `Aquifers_Jharkhand.aquifer` (12 lithologies) | `LITHOLOGY_REGIME` |
| Baseline chemistry per pin | `waterQuality_jharkhand.csv` (U ppb, SO₄, EC→TDS) | nearest well |
| Hydraulic gradient i | *not in data* | dashboard slider |

## The hydrogeological chain (Phase 1)

```
Darcy flux        q   = K · i                          [m/day]
Seepage velocity  v   = K · i / φ_mobile               [m/day]   (advection)
Retardation       Rd  = 1 + (ρ_b / n_total) · Kd       [-]       (chemistry; fractured: 1+β)
Contaminant vel.  vc  = v / Rd                         [m/day]
Dispersivity      αL  = 0.83·(log₁₀L)^2.414 ; αT = r·αL [m]      (Xu & Eckstein 1995)
Péclet            Pe  = L / αL                         [-]       (advection vs dispersion)
Pore volumes      PV  = Q_in·t / (φ_mobile·V_swept)    [-]       (throughput)
Containment       η   = Q_net / (q·b·W + Q_net)        [-]       (cone-of-depression capture)
```

These dimensionless groups (Pe, Rd, PV, η, anisotropy αL/αT, τ) are what transfer between
Texas and Jharkhand — a model trained on them is geometry-agnostic.

## Phase 2 transport (analytical, no Flopy/MODFLOW binaries)

Domenico (1987) continuous-source 2D solution with retarded velocity, anisotropic
dispersion (fractured → long narrow plume; porous → round), dual-porosity matrix-diffusion
tailing for fractured zones (Goltz & Roberts 1986), and two-phase advection
(contained during operation, drifting post-closure). Milliseconds per field →
suitable for both bulk training-data generation and live dashboard recompute.

## Run it

```bash
pip install -r ml_pipeline/requirements.txt   # numpy/pandas/scipy/sklearn/geopandas present already

# Phase 1 — inspect the feature bridge & loaders
python -m ml_pipeline.data_prep.texas_loader
python -m ml_pipeline.data_prep.jharkhand_loader
python -m ml_pipeline.data_prep.feature_engineering

# Phase 2a — analytical engine demo (fractured vs porous plume)
python -m ml_pipeline.physics.transport

# Phase 2b — generate the statewide synthetic training set
python -m ml_pipeline.synthetic.generate --scenarios 400 --mc 16
#   -> outputs/synthetic_training.csv  (one row per scenario × time × species; has scenario_id)
#   -> outputs/synthetic_meta.json

# Phase 3 — train the physics-guided surrogate
python -m ml_pipeline.ml.train            # -> ml/artifacts/*.joblib + metrics.json + model_card.json
python -m ml_pipeline.ml.shap_analysis    # -> ml/artifacts/shap_top_*.json (+ PNG)
python -m ml_pipeline.ml.predict          # demo: analytical vs ML toggle
```

### Phase 3 guardrails (enforced + verified)
- **No leakage:** `GroupKFold(5)` on `scenario_id` — a scenario's 15 (time×species) rows never split across folds.
- **Physics-faithful monotonicity:** XGBoost `monotone_constraints` from `dataset.MONOTONE_MAP`
  (Q_in→larger, bleed/Rd/Kd/containment→smaller, K/i/time→larger). Verified empirically post-fit.
  Source-zone width is throughput-coupled so "higher injection → larger plume" is *physical*, not forced.
- **Mappable uncertainty:** quantile heads (P10/P50/P90) + **Conformalized Quantile Regression**
  (Romano et al. 2019) → calibrated 80% coverage (raw 0.45–0.63 → 0.80).
- **Held-out skill (GroupKFold OOF):** area R²=0.97, migration R²=0.98, compliance-conc R²=0.92,
  P_ex R²=0.92, breach AUC=0.999. Top SHAP drivers: advective front `Xc`, source conc, dispersivity, time.

## Targets produced for Phase 3
`affected_area_ha` · `max_migration_distance_m` · `peak_conc` / `delta_peak` ·
`compliance_conc` · `breaches_bis` (BIS breach at monitoring ring) ·
`excursion_probability` (Monte-Carlo over Kd/β/gradient/dispersivity uncertainty).

## Key literature (cited inline in `config/parameters.py`)
BIS IS 10500:2012 · WHO 2017 (U 30 µg/L) · EPA 402-R-99-004B (U Kd) · Davis/USGS Naturita
(alkaline U Kd 0.5–10.6 L/kg) · Xu & Eckstein 1995 (dispersivity) · Gelhar et al. 1992 ·
Domenico 1987 · Goltz & Roberts 1986 · Freeze & Cherry 1979.

> **Scope honesty:** this is an *uncalibrated, theoretical* screening surrogate. Texas-derived
> dispersivities and porous-media Kd are transferred to fractured domains that have **no field
> tracer calibration**. See the "Limitations" section of the build notes. Do not use for permitting
> or as a substitute for site characterization.
