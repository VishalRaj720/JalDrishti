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
├── dashboard/                    # PHASE 4: FastAPI backend + Leaflet frontend
│   │                             #   (envelope guard, extrapolation flag, HCO3->Kd)
├── tests/                        # physics-law regression tests (run under pytest)
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

Domenico (1987) continuous-source 2D solution, upgraded in the 2026-07 Phase-0/1
remediation:

- **Geometry:** source plane at the **downgradient wellfield edge** (conservative
  areal-source convention); compliance ring at `COMPLIANCE_BUFFER_M` beyond it.
- **Three-phase kinematics:** operation (front at `v·(1−η)`, with η =
  `min(1, Q_net/(q·b·W))` mass-balance capture — complete capture possible),
  restoration (front held; source stepped to `residual·C0` from the real Texas
  post-restoration sheets via Domenico superposition), post-closure drift.
- **Fractured regime:** time-dependent apparent retardation `R_app(t)` (closed-form
  retarded clock, Goltz & Roberts 1986) + the Tang/Frind/Sudicky (1981) matrix-
  diffusion kernel as an early-arrival envelope — Kd acts physically through the
  matrix-retardation group σ; open apertures give early far breakthrough.
- **Time-consistent throughput:** PV/BV, the tanh source widening and the
  dispersivity length scale are evaluated at the time slice, not end-of-operation.
- **Incremental exceedance:** area/breach scored on mining-attributable
  concentration `max(threshold − background, 0.1·threshold)` — ambient water
  already at the limit cannot flood the grid.

Milliseconds per field → suitable for both bulk training-data generation and live
dashboard recompute. Physics laws are regression-tested on the LABELS
(`ml_pipeline/tests/test_physics_laws.py`), not on the constrained model.

## Run it

```bash
pip install -r ml_pipeline/requirements.txt   # numpy/pandas/scipy/sklearn/geopandas present already

# Phase 1 — inspect the feature bridge & loaders
python -m ml_pipeline.data_prep.texas_loader
python -m ml_pipeline.data_prep.jharkhand_loader
python -m ml_pipeline.data_prep.feature_engineering

# Phase 2a — analytical engine demo (fractured vs porous plume)
python -m ml_pipeline.physics.transport

# Physics-law regression tests (labels, not the model)
python -m pytest ml_pipeline/tests/test_physics_laws.py -q

# Phase 2b — generate the statewide synthetic training set (v2: MC band labels)
python -m ml_pipeline.synthetic.generate --scenarios 900 --mc 48
#   -> outputs/synthetic_training.csv  (scenario_id + polygon_id groups;
#      P10/P50/P90 parameter-uncertainty labels per target)
#   -> outputs/synthetic_meta.json     (use --out <path> to write elsewhere)

# Phase 3 — train the physics-guided surrogate
python -m ml_pipeline.ml.train            # -> ml/artifacts/*.joblib + metrics.json + model_card.json
python -m ml_pipeline.ml.shap_analysis    # -> ml/artifacts/shap_top_*.json (+ PNG)
python -m ml_pipeline.ml.predict          # demo: analytical vs ML toggle
```

### Phase 3 guardrails (v2 — enforced + honestly verified)
- **No leakage, two skill numbers:** `GroupKFold(5)` on `scenario_id` (interpolation
  skill) **and** leave-aquifer-out CV on `polygon_id` (new-hydrogeology skill,
  enabled by jittered pins): area R² 0.94 / 0.92, migration 0.90 / 0.87,
  compliance-conc 0.88 / 0.87, P_ex R² 0.94 (MAE 0.062).
- **Per-target monotone maps** (`dataset.MONOTONE_MAPS`) — the shared v1 tuple
  forced signs the physics violates. Q_out (the collinear constraint back-door)
  is dropped. Verified **on-manifold** post-fit: the raw operating point is swept
  through the inference feature builder, so coupled features move together —
  area rises with Q_in at fixed Q_net and falls with bleed at fixed Q_in.
- **Bands that mean something:** labels are MC P10/P50/P90 over parameter
  uncertainty (Kd, local log-K, β, gradient×seasonality, dispersivity, bleed
  drift; common random numbers). Conformal calibration is **honest Mondrian
  split-CQR**: OOF conformity scores aggregated per (regime×species cell ×
  scenario) by max, δ from a 50% calibration split, coverage reported on the
  untouched half — scenario-level ≈ 0.80–0.82, every cell ≥ 0.88 row-level
  (fractured/uranium included), top-5% tail ≈ 0.89–0.91. The v1 pipeline
  evaluated coverage on the rows that set δ (an identity, not a validation).
- **One risk number:** `excursion_probability` = breach fraction of the same MC
  draws; the separate breach classifier is retired.
- **Phase 3.5 — constrain the estimate, free the uncertainty:** monotone
  constraints apply to the **P50 central estimate only**; the P10/P90 band edges
  are unconstrained (`dataset.CONSTRAIN_BANDS`). A quantile band of the switch-
  like compliance concentration is not monotone in every driver, and forcing it
  cost ~0.7 R² on the compliance P90 and ~0.16 on the migration P10, which the
  conformal δ then absorbed as blunt, over-wide bands. Freeing the edges lifts
  compliance P90 R² 0.15→0.83 and migration P10 0.69→0.85, leaves every P50
  unchanged (physics + on-manifold intact), holds 80% coverage, and shrinks the
  bands 27–33%. (Verified empirically first: the front-minus-ring feature was
  redundant and MC labels are clean — the constraints were the cause.)

Top SHAP drivers (v2): dispersivity `alpha_L`, advective front `Xc_m`, wellfield
width, clean-up front `Xc_clean_m`, source concentration.

## Targets produced for Phase 3 (v2: distributional)
`{affected_area_ha, max_migration_distance_m, compliance_conc}_{p10,p50,p90}` —
Monte-Carlo parameter-uncertainty quantiles (Kd triangular, local log-K
heterogeneity, β, gradient×seasonality, dispersivity, bleed drift; common
random numbers across the whole run) · `excursion_probability` (breach fraction
of the SAME draws — the separate breach classifier is retired) · deterministic
central `affected_area_ha` / `compliance_conc` / `peak_conc` kept as reference.

## Key literature (cited inline in `config/parameters.py`)
BIS IS 10500:2012 · WHO 2017 (U 30 µg/L) · EPA 402-R-99-004B (U Kd) · Davis/USGS Naturita
(alkaline U Kd 0.5–10.6 L/kg) · Xu & Eckstein 1995 (dispersivity) · Gelhar et al. 1992 ·
Domenico 1987 · Goltz & Roberts 1986 · Freeze & Cherry 1979.

> **Scope honesty:** this is an *uncalibrated, theoretical* screening surrogate. Texas-derived
> dispersivities and porous-media Kd are transferred to fractured domains that have **no field
> tracer calibration**. See the "Limitations" section of the build notes. Do not use for permitting
> or as a substitute for site characterization.
