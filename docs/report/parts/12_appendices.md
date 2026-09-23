\newpage

# Appendices

## Appendix A — Descriptive statistics and hydrochemical QA of the measured record [M]

Re-derived from `Datasets/waterQuality_jharkhand.csv` (397 rows, 24 districts, year 2023) on 21 September 2026. Values in mg/L unless noted; "-" in the source is treated as missing.

| Determinand | n | Min | p25 | Median | p75 | Max | Above acceptable | Above permissible |
|---|---|---|---|---|---|---|---|---|
| pH | 397 | 6.53 | — | 7.80 | — | 8.28 | 0 | 0 |
| EC (µS/cm) | 393 | 153 | — | 766 | — | 2,780 | — | — |
| CO₃ | 397 | 0 | 0 | 0 | 0 | 0 | — | — |
| HCO₃ | 393 | 18 | — | 250 | — | 1,050 | — | — |
| Cl | 397 | 7 | — | 78 | — | 430 | 9 | 0 |
| F | 397 | 0.00 | — | 0.42 | — | 1.91 | 32 | 11 |
| SO₄ | 393 | 2 | — | 38 | — | 234 | 2 | 0 |
| NO₃ | 393 | 0 | — | 18 | — | 121 | 22 | 22 |
| PO₄ | 393 | 0.00 | — | 0.00 | — | 1.30 | no limit | — |
| Total hardness (as CaCO₃) | 393 | 50 | — | 260 | — | 1,060 | 264 | 11 |
| Ca | 397 | 6 | — | 60 | — | 312 | 135 | 5 |
| Mg | 397 | 4 | — | 26 | — | 130 | 137 | 4 |
| Na | 397 | 1 | — | 42 | — | 423 | no limit | — |
| K | 397 | 0 | — | 6 | — | 55 | no limit | — |
| Fe (ppm) | 0 | — | — | — | — | — | not tested | — |
| As (ppb) | 0 | — | — | — | — | — | not tested | — |
| U (ppb) | 342 | 0.00 | — | 0.78 | — | 28.52 | 0 | 0 |

Quartiles are omitted where the report script did not compute them; the median, minimum and maximum are exact. Uranium per district: analysed at every well except East Singhbhum (0 of 28), Saraikela-Kharsawan (0 of 11) and West Singhbhum (0 of 16).

**Hydrochemical QA summary (2023 file, `GET /water-quality/qa`):** computable analyses 393; within ±5 %: 393 (all within ±3.2 %; median |CBE| 0.56 %); questionable 0; suspect 0; incomplete 4. Independence check: sodium re-derived by charge difference reproduces the reported value to a median 1.6 mg/L, 65 % within 2 mg/L; hardness = 2.497 Ca + 4.118 Mg within 5 % for 99 % of samples — the balance is a consistency of construction. Ion-sum/EC median 0.70 (expected 0.55–0.75). **2000–2021 file:** computable 753; suspect (> 10 %) 127; the check is independent there.

**Level record:** 9,583 readings, 398 stations (415 in the database after ingest of station metadata), 2013–2021; campaign medians of depth to water January 5.25 m, May 7.20 m, August 3.22 m, November 3.78 m; Theil–Sen classes: 5 declining, 20 recovering, 306 stable, 84 not enough record.

## Appendix B — Full surrogate metrics (model card v5, `metrics.json`)

**Configuration.** 40 features; GroupKFold n_splits = 5 on `scenario_id`; α = 0.20; `DELTA_INFLATE` = 1.35; calibration split seed 0; XGBoost `n_estimators` 450, `max_depth` 5, `learning_rate` 0.05, `subsample` 0.85, `colsample_bytree` 0.85, `reg_lambda` 1.5, `tree_method` hist, `random_state` 42; 22 monotone-constrained features per target; training CSV SHA-256 `8ac61f2db8540c046748765ac00be59bf4112a8d5cef1dc3ffeeae088a6d22b4`, 18,000 rows, 900 scenarios; bake meta version 5, seed 42, MC seed 43, generator git `8d2499d`, β prior [0.3, 20], MC factor 4, field-mix 0.6, horizons [2, 5, 8, 12, 20]; trained 2026-09-21T07:41:38Z.

**B.1 Per-target, scenario-grouped CV.**

| Target | R² P10 / P50 / P90 (raw) | R²(log) P50 | MAE P10 / P50 / P90 | Coverage rows / scenarios / top-5 % tail |
|---|---|---|---|---|
| affected_area_ha | 0.847 / 0.783 / 0.862 | 0.893 | 4.07 / 6.91 / 8.71 ha | 0.955 / 0.863 / 0.933 |
| max_migration_distance_m | 0.843 / 0.504 / 0.820 | 0.926 | 17.5 / 68.8 / 111.8 m | 0.952 / 0.878 / 0.955 |
| compliance_conc | 0.721 / −4.48 / −1.86 | 0.947 | 135.9 / 498.2 / 635.2 | 0.948 / 0.866 / 0.911 |
| excursion_probability | R² 0.915 | — | MAE 0.049 | n = 18,000 |

**B.2 Baselines (same features, same folds).**

| Target | Mean: R²(log) / MAE | Ridge: R²(log) / R² / MAE | Stump: R²(log) / R² / MAE | Surrogate P50: R²(log) / R² / MAE |
|---|---|---|---|---|
| affected_area_ha | −0.001 / 23.2 | 0.561 / 0.719 / 11.1 | 0.384 / −0.032 / 20.2 | 0.893 / 0.783 / 6.91 |
| max_migration_distance_m | −0.002 / 163.5 | 0.773 / −1.78 / 122.5 | 0.515 / 0.013 / 146.6 | 0.926 / 0.504 / 68.8 |
| compliance_conc | −0.001 / 886.5 | 0.744 / (raw R² degenerate) / — | 0.499 / 0.142 / 670.4 | 0.947 / −4.48 / 498.2 |

The ridge baseline's raw-unit R² and MAE on `compliance_conc` are degenerate (back-transforming a linear log-space fit through mixed units), which is itself an argument for judging in log space.

**B.3 Leave-aquifer-out (23 polygons).** area R²(P50) 0.803 / log 0.890 / MAE 6.97 ha; migration 0.394 / 0.921 / 73.1 m; compliance −3.63 / 0.941 / 447.1.

**B.4 Per-cell conformal deltas (log units) and per-cell row coverage, CV.**

| Cell | Area δ / coverage | Migration δ / coverage | Compliance δ / coverage |
|---|---|---|---|
| fractured \| radium | 0.574 / 0.933 | 0.233 / 0.927 | 0.076 / 0.951 |
| fractured \| sulphate | 1.017 / 0.949 | 1.117 / 0.939 | 1.274 / 0.946 |
| fractured \| TDS | 1.466 / 0.971 | 1.741 / 0.973 | 0.695 / 0.948 |
| fractured \| uranium | 0.238 / 0.966 | 0.862 / 0.958 | 1.928 / 0.963 |
| porous \| radium | 0.579 / 0.948 | 0.518 / 0.942 | 0.043 / 0.921 |
| porous \| sulphate | 1.106 / 0.952 | 1.868 / 0.946 | 1.299 / 0.948 |
| porous \| TDS | 1.294 / 0.957 | 2.110 / 0.954 | 0.661 / 0.939 |
| porous \| uranium | 0.290 / 0.967 | 0.991 / 0.976 | 2.049 / 0.969 |

**B.5 Field-resampled coverage (120 scenarios, 2,400 rows, field-mix 1.0).** area rows 0.965 / scenarios 0.885 (weakest cell fractured|sulphate 0.944); migration 0.949 / 0.875 (fractured|TDS 0.874); compliance 0.950 / 0.881 (fractured|sulphate 0.909). All pass the 0.80 gate.

**B.6 Trained support (model card `hydro_support` and `training_envelope`).** Fractured: φ_m 0.006–0.025, R_d 1.30–20.6, K 0.044–10.6 m/day. Porous: φ_m 0.01–0.08, R_d 1.0–50,535, K 0.096–29.7. Operational: Q_in 200–8,000 m³/day; Q_net 0–400; bleed 0–0.10; operation 1–20 yr; horizon 0–20 yr; gradient 0.0005–0.02; W 100–800 m; restoration 0–10 yr; k 0–0.70/yr. Per-species C₀ / C_b support in `TRAINED_SPECIES_SUPPORT`.

**B.7 Monotone constraint map (per band target).** +1: `K_m_day`, `gradient_i`, `darcy_flux_q`, `seepage_velocity_v`, `contaminant_velocity_vc`, `Xc_m`, `Q_in_m3_day`, `pore_volumes_PV`, `source_conc_C0`, `background_conc_Cb`, `wellfield_width_m`, `downtime_fraction`, `residual_fraction`. −1: `Xc_clean_m`, `phi_mobile`, `retardation_Rd`, `Kd_L_kg`, `bleed_fraction`, `Q_net_m3_day`, `containment_eta`, `restoration_years`, `u_attenuation_k`. 0 (unconstrained): `time_years`, `is_post_closure`, `dimensionless_time_tau`, the species one-hots.

## Appendix C — API and role summary

Twenty-five routers under `/api/v1` exposing 152 endpoints (the generated role × endpoint matrix is `docs/roles.md`, regenerated by `python -m scripts.authz_matrix`; `tests/test_authz_matrix.py` fails on drift):

| Router | Purpose | Typical roles |
|---|---|---|
| `auth` | login, refresh (sliding session), me | all |
| `users` | accounts, role edit (single admin pinned) | admin |
| `districts`, `monitoring_wells`, `water_samples` | reference data | staff |
| `isr_points` | hypothetical site registration, edit, delete (survivable) | analyst, regulator, admin |
| `ml` | pin resolution, predict, assumptions register, drift, boundary/ore/river/flow/strike layers | staff |
| `preview`, `simulations`, `lifecycle`, `scenarios` | ephemeral preview, stored runs (pinned), sweep, lifecycle, named scenarios, compare, timeline | analyst, regulator, admin |
| `advisories` | propose / decide / withdraw a screening | analyst proposes; admin decides |
| `citizen`, `public_risk` | my area, alerts, block search, published advisories, delivery status and manual send (admin) | citizen; unauthenticated for the public surface |
| `water_quality`, `groundwater`, `data_gaps` | IS 10500 assessment, QA, 2000–2021 history, level trends, ranking, gap matrix, siting | staff |
| `field_observations` | submit / withdraw / review queue / decide | field_officer submits; regulator decides |
| `datasets`, `dataset_sync`, `ingest`, `model_ops`, `audit` | dataset manager with restore points, sync, CSV/GeoJSON ingest, model operations, audit log | admin |

Authorization tallies and the full matrix: `docs/roles.md` §5.

## Appendix D — Database schema and row-level security

**Tables (ORM models at the report commit):** `orgs`, `users` (with `home_block_id`, `alert_email_opt_in`), `districts`, `blocks`, `aquifers`, `monitoring_wells`, `monitoring_stations`, `water_samples` (20 determinand columns — the 2023 CGWB file fills 17 of them, plus TDS derived from EC — and `record_source`), `data_sources`, `dataset_versions`, `isr_points` (operating parameters, `injection_start_date`, owner org), `scenarios`, `simulation_runs` (request, plume geometry with contours, frames and vertical block; pinned model-card SHA, artifact SHA, code version), `simulations` (legacy, empty), `advisories` (status, headline, what it means, affected blocks, decided_by, published_at), `alerts` (kind, block, severity, tier, basis, explanation JSONB, well fields, advisory link), `alert_deliveries`, `block_subscriptions`, `field_observations`, `audit_log`.

**Migrations:** `0001_initial` … `0026_alert_tiers_and_explanation` (26). Notable: `0004` month-3 schema; `0007` orgs/provenance/audit; `0008` viewer → citizen; `0009` ISR owner org and RLS; `0011` fix swapped district axes; `0012` simulation runs; `0016` plume geometry; `0017` advisories; `0018` citizen alerts; `0019`/`0022` regulator retired and restored with the single-admin index; `0021` aquifer-pathway alerts; `0023` breach-due; `0025` home block and delivery ledger; `0026` tiers, basis, explanation, `ck_modelled_never_critical`, `ck_basis_matches_kind`, `possible_reach`, `alerts_update` policy.

**Row-level security (representative policies; the complete list is asserted by `tests/test_rls.py` and printed at API startup):** `isr_points_read` (staff only; citizens never read a coordinate); `simulation_runs` (owner org / staff); `advisories_read` (published only for citizens; drafts refused before code sees them); `alerts` SELECT / INSERT / UPDATE (system context for writes); `alert_deliveries_own` FOR ALL (bypass or own user); `audit_log` (no UPDATE or DELETE policy for any role — append-only). Per-transaction settings: `app.current_role`, `app.current_org_id`, `app.current_user_id`, `app.bypass_rls`, applied with `SET LOCAL`. API role `jaldrishti_app`: `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, DML only, `CREATE` on `public` revoked.

## Appendix E — Scenario parameters and the assumption register

E.1 is Table 3.3 in long form; the columns there are the authoritative values at the report commit (`ml_pipeline/config/parameters.py`). E.2 is the machine-readable register served at `GET /api/v1/ml/assumptions`.

**E.2 `UNGROUNDED_PARAMETERS` (12 entries).**

| Key | Value | Kind | What it leverages | What would ground it |
|---|---|---|---|---|
| `SOURCE_BV_GAIN` | 0.40 | scenario assumption | the E1 leach-disc radius via W_eff; the disc is 76–97 % of reported area | per-pattern lixiviant flare or exempted-vs-pattern area data |
| `SOURCE_BV_REF` | 2.0 BV | scenario assumption | how fast source-width growth saturates | as above |
| `INCREMENTAL_FLOOR` | 0.10 | modelling policy | how much of a naturally poor baseline the mine is held responsible for; every exceedance threshold | a regulator's attribution rule |
| `ISR_UCL_BASELINE_INCREASE` | 0.20 | scenario assumption | when the 2-of-3 indicator test fires | per-well temporal baseline series (NUREG's mean + 5σ) |
| `DUAL_POROSITY.beta_prior` | log-U [0.3, 20]; central derived per run; MC ×4 | foreign-analogue literature | effective retardation of every fractured plume | a Singhbhum tracer test |
| `DUAL_POROSITY.mass_transfer_omega` | 10⁻³ /day | foreign-analogue literature | how fast the retarded clock matures | as above |
| `FRACTURE.full_aperture_m` | (1, 2.5, 5) × 10⁻⁴ m | foreign-analogue literature | Tang envelope; MC-sampled | a Singhbhum packer test |
| `FRACTURE.De_m2_day` | 5 × 10⁻⁶ | foreign-analogue literature | Tang envelope; not sampled | a defensible range; none exists |
| `VERTICAL.Kv_Kh_by_regime` | 0.03 / 0.008 | scenario assumption | advective upward leakage | structural analysis or packer data |
| `VERTICAL.upward_gradient` | 0.005 | scenario assumption | the shallow-impact index (0.005 → moderate, 0.020 → high) | deep piezometry for Singhbhum |
| `VERTICAL.wellbore_failure_prob` | 0.05 | scenario assumption | floor on the shallow-impact index | ISR mechanical-integrity failure statistics (NUREG/CR-6733 gives no frequency) |
| `IRREGULARITY` | downtime and drift ranges | scenario assumption | band width | TCEQ/NRC excursion and downtime records |

## Appendix F — Sample inputs and outputs

**F.1 One engine request (through the backend adapter's allow-list) and the shape of its response — the registered Jaduguda site, uranium, 20 yr, no restoration.**

Request:

```json
{"lon": 86.36, "lat": 22.65, "injection_rate_m3_day": 1500.0, "bleed_percent": 2.0,
 "operation_years": 8.0, "wellfield_width_m": 300.0, "monitor_ring_m": 100.0,
 "ore_depth_m": 150.0, "ore_thickness_m": 20.0, "species": "uranium_ppb",
 "time_years": 20.0, "restoration_years": 0.0}
```

Response, abridged (top-level keys: `pin, hydro, species, threshold, azimuth_deg, azimuth_source, containment, mode, notice, far_field_note, nearest_river_km, river_crossing, ore_zone, restoration, vertical, timeline, isr_excursion, beta_override, wellfield_geometry, extrapolation, plume, metrics, ml_envelope, ml_envelope_skipped, ml_status, disagreement`):

```json
{"hydro": {"lithology": "Schist", "regime": "fractured", "K_m_day": 0.527, "phi_mobile": 0.0075,
           "n_total": 0.03, "thickness_m": 136.9, "Kd_L_kg": 1.0, "retardation_Rd": 4.0,
           "retardation_effective": 270.8, "dual_porosity_beta": 3.0, "beta_basis": "porosity_derived",
           "ore_zone": {"zone": "belt", "nearest_deposit": "Jaduguda", "nearest_deposit_km": 0.35},
           "u_suppressed": false, "source_conc_C0": 14294.5, "background_conc_Cb": 1.0},
 "threshold": 30.0,
 "notice": "Prospective Belt (Singhbhum envelope): hypothetical low-confidence ore assumed — uranium source term reduced.",
 "metrics": {"analytical": {"area_ha": 8.99, "migration_m": 22.7, "compliance_conc": 1.0,
                            "excursion_probability": 0.0, "breach": 0},
             "ml": {"area_ha": {"p10": "...", "p50": "...", "p90": "..."}, "migration_m": {"...": "..."},
                    "compliance_conc": {"...": "..."}, "excursion_probability": 0.018, "off_scale": false}},
 "isr_excursion": {"excursion_declared": true, "indicators_over_ucl": 2, "indicators_required": 2,
                   "indicators_available": 3, "rule": "2-of-3: ...", "indicators": ["chloride ...", "tds ...", "sulfate ..."]},
 "vertical": {"separation_m": 120.0, "layer1_base_m": 20.0, "water_table_m": 1.6,
              "advective_breakthrough_fraction": 0.602, "years_to_vertical_breakthrough": 18.7,
              "breakthrough_basis": "duty_cycle", "shallow_impact_probability": 0.622, "risk_band": "high",
              "pathways": {"dispersive": 0.0, "advective_leakage": 0.602, "wellbore": 0.05}},
 "extrapolation": [], "restoration": null}
```

**F.2 One alert record with its seven fields:** Table 6.10.

**F.3 One published advisory (structure):** `id`, `isr_point_id` (withheld from citizens), `run_id` (pinned SHAs), `status: published`, `headline`, `what_it_means`, `species`, `affected_blocks[] {id, name, district, overlap_ha}`, `proposed_by`, `decided_by`, `published_at`; the citizen view joins the run's operating parameters (operation years, horizon, sweep, injection rate), the modelled spread, whether shallow water was expected to be reached, and the timeline frames — never the coordinate.

## Appendix G — Screenshots

Included in this report: the public map (Fig. 6.1), the console result panel (Fig. 6.3, July 2026 build), the site report (Fig. 6.4), the front page (Fig. 6.7), the flow and strike fields (`figures/fig_flow_field.png`, `figures/fig_strike_field.png`), the SHAP figure (Fig. 6.2) and the sensitivity figures (Figs. 6.5–6.6). **To be captured from the final build before submission**, one per role: login; overview per role; console with a run, the timeline scrub and the NUREG panel; report with the frames table and the β paragraph; compare; scenarios; publications (propose and decide); field data (submit and review); water quality with the QA and history readouts; groundwater trends; data & gaps with the QA and temporal readouts; network plan; datasets and ingest; administration with the delivery panel and tier counts; my area; citizen map; alerts with tiers, the seven-field record and the ladder; methods with the assumptions register; audit.

## Appendix H — Source-to-Claim Register

Every quantitative claim in the body, its section, and its source at commit `476a4a9` (or the dataset / citation). Every reference entry was checked against its source record on 21 or 23 September 2026; the head of the reference list says how.

| # | Claim | § | Source |
|---|---|---|---|
| 1 | 173 commits; 26 migrations; 152 endpoints; 22 screens; 5 roles | 1.8, 4.11 | `git rev-list --count HEAD`; `backend/alembic/versions/`; `docs/roles.md`; `frontend/portal/src/pages/` |
| 2 | 373 engine tests; 522 backend tests | many | `pytest ml_pipeline/tests -q` (373 passed); `cd backend && pytest` (522 passed), 21 Sep 2026 |
| 3 | End-to-end audit 43/44; the one failure is the radium R²(log) gate | 6.2 | `python -m ml_pipeline.validation.end_to_end_audit`, 21 Sep 2026 |
| 4 | v5 metrics: R²(log) 0.893 / 0.926 / 0.947; coverage 0.863 / 0.878 / 0.866; field 0.885 / 0.875 / 0.881; baselines; LAO; P_ex R² 0.915 | 6.2, App. B | `ml_pipeline/ml/artifacts/metrics.json`, `model_card.json` v5 |
| 5 | Radium per-species R²(log) 0.500 / 0.235; labels 81.8 % zeros / 95.8 % pinned | 6.2 | `metrics.json`; `docs/LIMITATIONS.md` §1 |
| 6 | Hyper-parameters; DELTA_INFLATE 1.35; α 0.20; 22 constraints per target | 4.6, App. B | `metrics.json["config"]`; `model_card.json["reproducibility"]` |
| 7 | Training set 18,000 rows, 900 scenarios, 23 polygons, 48 MC draws, SHA-256 `8ac61f2d…` | 4.6 | `model_card.json["reproducibility"]` |
| 8 | 397 wells, 24 districts, 2023; U 0/342, max 28.5; NO₃ 22 (max 121); F 32 above 1.0, 11 above 1.5; 32 wells over a health limit; 21 warning; Fe/As 0 %; 55 un-analysed for U (28/11/16) | 3.4, 6.1 | pandas re-derivation from `Datasets/waterQuality_jharkhand.csv`, 21 Sep 2026 |
| 9 | 3 critical wells (Biru, Lowadih, Gidhaur); 14 districts High concern | 6.1, 6.8 | same re-derivation; `alert_tiers.py` rules |
| 10 | 53 measured alerts: 3 critical / 29 alert / 21 warning | 6.8 | `docs/PROJECT_FREEZE.md` §5 (local record); consistent with claim 8 |
| 11 | Deployed: 55 alerts, 4 residents following 7 blocks; email working 21 Sep 2026 | 6.8 | Administration screen of the deployed portal (owner screenshot, 21 Sep 2026) |
| 12 | Charge balance: 393/393 within ±3.2 %, median 0.56 %; Na by difference (1.6 mg/L median, 65 % within 2); hardness identity 99 %; EC ratio 0.70; 2000–2021: 127/753 suspect | 3.5, 6.1 | `backend/app/services/hydrochem_qa.py` docstring (first run 20 Sep 2026); `docs/LIMITATIONS.md` §3 |
| 13 | Levels: 9,583 readings, 398 stations, 2013–2021; campaign medians 5.25 / 7.20 / 3.22 / 3.78 m; trends 5 / 20 / 306 / 84; fastest 0.785 m/yr Chapodia; median swing 2.38 m | 3.2, 6.1 | `Datasets/cgwb_waterlevel_jharkhand.csv`; `config/parameters.py` `WATER_TABLE_CAMPAIGNS_M`; `docs/LIMITATIONS.md` §4d |
| 14 | 2000–2021: 1,632 analyses, 366 stations; 244 wells ≥ 2 years; EC 13 rising / 6 falling of 175 | 3.3, 6.1 | `Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv`; `docs/PROJECT_FREEZE.md` §2, §10 |
| 15 | Flow field: 5 km grid, 3,247 cells, 2,416 station-fit, 831 DEM, median R² 0.734; gradient p10/50/90 0.0012/0.0030/0.0076 | 3.2, 4.2 | `ml_pipeline/data_prep/artifacts/flow_field_meta.json` |
| 16 | Strike field: 1,826 segments (799 joints); mean strike 79.5°; V 0.676 | 3.3, 4.2 | `ml_pipeline/data_prep/artifacts/strike_field_meta.json` |
| 17 | Monsoon horizontal-gradient swing: direction p50 2.5°, magnitude ratio 1.05 | 3.2 | `JHARKHAND_FIDELITY_MATRIX.md` row 3.7 |
| 18 | NAQUIM layer table values (Layer-1 base 13–22 m; fracture base 90–258 m) | 3.2 | `Datasets/naquim_reference/naquim_vertical.csv` |
| 19 | Texas: 86/9/86 rows; C₀ envelope 9,027–41,595 ppb (n = 9, 7 mines); paired residuals 0.060 / 0.138 / 0.337 / 0.531; U per-mine 0.023–0.248; restoration median 5.0 yr (IQR 3.8–6.5), 18.6 PV | 3.4 | `ml_pipeline/data_prep/texas_loader.py` (`texas_restoration_residual()` printed 21 Sep 2026); `config/parameters.py` `TRAINED_SPECIES_SUPPORT`; `ARCHITECTURE.md` §4.9 |
| 20 | Jaduguda reference-case table (20.5 / 73.1 / 253.8 / 0.6 m; bands; p_ex; resolved K 0.563, β 3.0, gradient 0.00205) | 6.4 | re-derived 21 Sep 2026 via `resolve_inputs` + `predict_analytical` + `predict("ml")`, v5 artifacts |
| 21 | Registered-site lifecycle table; TDS ring arrival 8–12 yr; sulphate 20–30; U never; NUREG declared from yr 12; Cl 862 / TDS 4,605 at 20 yr; sweep 0/6/12 yr → 26.4 / 4.2 / 0 m | 6.5 | engine runs through `ml_pipeline_adapter`, 21 Sep 2026 |
| 22 | Vertical: separation 120 m, breakthrough 18.7 yr (duty cycle), dry 6.8 yr, index 0.62, high; old headline 54.4 yr; pathway open ~58 % | 6.6 | engine run 21 Sep 2026; `docs/LIMITATIONS.md` §1b |
| 23 | β table (β = 10 → 11.7 m … β = 0 → 938 m) | 5.1, 7.5 | `docs/LIMITATIONS.md` §1d (analytical engine, 16 Sep 2026) |
| 24 | Before/after R17 table (Table 6.8) | 6.5 | `ml_pipeline/outputs/snapshot_{pre,post}_r17.json`; `docs/LIMITATIONS.md` §1d |
| 25 | Exact-solution benchmark: product error ±0.1 %; truncated term −17 to −42 %; reach −3.6 % p50, −6.5 % worst | 6.2 | `docs/local/audit-record/DOMENICO_ERROR_ENVELOPE.md` (5 Aug 2026); `physics/exact_reference.py` |
| 26 | Migration R² 0.719 → 0.896 → 0.929 → 0.927 → 0.926 | 6.2 | commits `f27427a`, `2451427`, `1a1164d`, `476a4a9`; `ARCHITECTURE.md` §6.5 history |
| 27 | Migration artefact 422.8 m vs 35.9 m true reach; 29 of 60 scenarios read 0.0 m | 4.5 | `docs/local/audit-record/review.md` finding #1; `JHARKHAND_FIDELITY_MATRIX.md` correction notes |
| 28 | Fractured front species-blind (13.17 m for Kd ∈ {0, 1, 500, 2000}) | 4.5 | `review.md` finding #2 |
| 29 | Redox double-count 0.4699/m → 0.00587/m; disc 7.07 ha at t = 0; uranium 0.44 → 7.11 m | 4.5, 7.5 | fidelity matrix round-2 notes |
| 30 | Depth decay: 23,000× vs ~440× (Manning & Ingebritsen); Jaduguda K 2.47 → 0.37 m/day at 180 m | 4.4 | fidelity matrix row 3.3 and 10 Aug note |
| 31 | Seams: 16.5 → 4.75 ha; 1.74× → 1.015×; +37 % → +1.7 %; 2.16× → 1.07× | 4.4 | fidelity matrix rows 3.6 and correction notes |
| 32 | SHAP top features (Table 6.5) | 6.3 | v5 `shap_analysis` output, 21 Sep 2026; `ml/artifacts/shap_top_*.json` |
| 33 | Sensitivity indices (Tables 6.12, J.1) | 6.9, App. J | `ml_pipeline/ml/artifacts/sensitivity.json`, 21 Sep 2026 |
| 34 | Ranking top 25; gap totals 264 / 53 / 83 / 55 / 397 | 6.9 | `monitoring_gaps.recommendations()` and `gap_matrix()` on the local database, 21 Sep 2026 |
| 35 | Weights 30/30/20/15/5; good coverage 3 wells/100 km²; far 25 km | 4.9 | `backend/app/services/monitoring_gaps.py` |
| 36 | Rate limiter inert: 120 logins in 5.7 s, 120 × 401; now 10 × 401 then 429 | 4.11, 7.1 | `docs/LIMITATIONS.md` §4d S-1; `tests/test_security_hardening.py` |
| 37 | Publication never raised an alert; scan matched zero rows; run endpoint never worked; upsert needed UPDATE policy | 4.11, 7.1 | `docs/LIMITATIONS.md` §1c, §4d, §4e, §4h |
| 38 | Delivery retry defect; Render blocks 587; Brevo login and IP allow-list | 6.8 | commit `47ab713`; owner's Render logs and Brevo screens, 21 Sep 2026 |
| 39 | Belt-notice mis-statement and excursion-indicator chip; background floor and v5 retrain | 4.5, 6.5 | commits `02e01e5`, `8d2499d`, `476a4a9`; `docs/LIMITATIONS.md` §4h-i, §4h-ii |
| 40 | `jharia` demo observation in the ore dataset resolves a 25,300 ppb deposit-tier source at 23.39° N 86.28° E | 3.5, 8, 10 | `Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv` (record_source `added`); `resolve_inputs` at that point, 21 Sep 2026; commit `0533caa` |
| 41 | Cold start 53 s; engine ~0.2 s local vs ~4 s deployed; bake and train durations | 6.11 | `docs/PROJECT_FREEZE.md` §0; pipeline log 21 Sep 2026 |
| 42 | Project chronology (Table 1.1) | 1.8 | the ten MPRs; `git log`; `docs/local/comparison.md` |
| 43 | May 2026 pipeline: 3,473 rows; real-only U R²(log) 0.69; distance importance ~0.70; time unused | 1.8, 7.2 | MPR May and June 2026; `docs/local/comparison.md` §3 |
| 44 | April 2026: 5,186 rows; RF 91.1 % / 0.90 F1 | 1.8 | MPR Apr 2026 |
| 45 | June 2026 first surrogate metrics (area R² 0.869, cov 82.4 % …) | 1.8 | MPR Jun 2026 |
| 46 | Proposal objectives, deliverables, inputs, methodology diagram | 1.5, 8 | `docs/local/My_Proposal.pdf` pp. 1–5 |
| 47 | Mentor discrepancy (proposal vs MPRs) | title page | proposal p. 1; all ten MPRs §2 |
| 48 | Citation corrections in `config/parameters.py` comments, made 23 Sep 2026: "Johnson et al. 2019" → Reimus et al. 2019 [18]; "BARC, J. Environ. Radioactivity 99 (2008) 1245" → Tripathi et al. 2008 [24] for the 23 mBq/L regional ²²⁶Ra value, and Tripathi et al. 2012 (*Radiat. Prot. Dosim.* 148(2), 211–218, doi:10.1093/rpd/ncr014) for the <3.5–208 mBq/L potable-well range, which this report does not use. No computed value changed. | references; §3.6 (Table 3.3) | Crossref records for 10.1021/acs.est.9b01572 and 10.1016/j.apradiso.2007.12.019; publisher abstract of 10.1093/rpd/ncr014 |
| 49 | NUREG-1569 ring 75–180 m, ≥ 3 indicators, 2-of-N, uranium rejected as an indicator | 1.1, 4.5 | NUREG-1569 §5.7.8.3 pp. 137–139 (as quoted in `config/parameters.py`) |
| 50 | Basement Gneissic Complex 48,047 km²; shallow flow ~1.5 m/yr; 27 m / 255 m in 20 yr | 3.2, 6.8 | `docs/LIMITATIONS.md` §4a |

**Reference verification status:** all 62 entries were checked on 21 and 23 September 2026 — journal articles against their Crossref DOI records; books, reports and standards against publisher, issuing-body or catalogue records; the three EPA K_d volumes, the East Singhbhum booklet and the NRSC lineament manual against the PDFs in `Datasets/`; and the datasets against their files, their download scripts and, where it could be reached, the provider's portal. The check changed the dataset entries materially: [37] names the 22 NAQUIM reports actually held (the draft said "21 districts"), [39] identifies the 2023 chemistry as the Jharkhand table of CGWB's *Annual Ground Water Quality Report 2024*, [40] records the India Data Portal as the redistributor of the India-WRIS level record, [42] records that the lineament file is a partial grid-sampled harvest, and [44] records OpenTopography as the DEM distributor. One detail remains open: the table number of the 2023 chemistry within the CGWB report [39], because cgwb.gov.in refused automated access on 23 September 2026.

## Appendix I — Deployment details

Topology: Figure 4.2. Hosts: Neon (PostgreSQL 16 + PostGIS; two roles — the owner for migrations via `MIGRATION_DATABASE_URL`, `jaldrishti_app` for the API via `DATABASE_URL` with `?ssl=require`); Render (the API, free tier, in-process engine and scheduler, committed v5 model binaries); Cloudflare Workers (the portal build, proxying `/api/*` in code so that one origin serves both).

Environment variables (values redacted): `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `JWT_SECRET`, `JWT_REFRESH_SECRET` (rotated; ≥ 32 characters enforced), `APP_ENV=production`, `CORS_ORIGINS` (never `*`), `RATE_LIMIT_PER_MINUTE=300`, `AUTH_RATE_LIMIT_PER_MINUTE=10`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `DOCS_ENABLED=false`, `METRICS_TOKEN`, `HSTS_ENABLED`, `ALLOW_INERT_RLS` (unset), `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=2525`, `SMTP_USER` (the relay's machine login, not the account address), `SMTP_PASSWORD` (the relay's SMTP key), `SMTP_STARTTLS=true`, `ALERT_FROM_EMAIL` (a sender the relay has verified), `ALERT_FROM_NAME`, `PORTAL_URL`, `ALERT_SCAN_INTERVAL_HOURS=24`. Startup refuses production with a placeholder secret, an empty database URL, `CORS_ORIGINS=*`, or inert RLS. Steps to bring the deployment to the report commit: `docs/PROJECT_FREEZE.md` §8 (migrate to `0026`, deploy v5 artifacts, rebuild alert explanations once, re-run one simulation per published site); then remove the `jharia` record through the dataset manager and re-verify.

## Appendix J — Sensitivity analysis, full tables

Method: `ml_pipeline/validation/sensitivity.py`; analytical engine only; horizon 20 yr, operation 8 yr, restoration 3 yr; OAT at 7 points per input; Sobol first-order S1 (Saltelli 2010 [50]) and total-order S_T (Jansen 1999 [51]) at base N = 256; log-transformed outputs where the range exceeds 20×; 13 inputs (group A: seven registered constants; group B: six resolved hydrogeological inputs). Figures: `ml/artifacts/sensitivity_*.png`.

**Table J.1 — Sobol S_T (S1 in parentheses) per input; outputs migration / footprint area / ring concentration.**

*Jaduguda deposit · uranium (fractured, deposit):* β 0.21 (0.21) / 0.16 (0.07) / 0.45 (0.12) · ω 0.10 (0.09) / 0.15 (0.00) / 0.21 (0.02) · aperture 0.01 / 0.00 / 0.00 · D_e 0.01 / 0.00 / 0.01 · SOURCE_BV_GAIN 0.00 / 0.22 (0.14) / 0.00 · SOURCE_BV_REF 0.00 / 0.27 (0.28) / 0.00 · INCREMENTAL_FLOOR 0.00 / 0.00 / 0.00 · **K 0.42 (0.44) / 0.12 (0.03) / 0.53 (0.16)** · gradient 0.16 (0.13) / 0.15 (0.03) / 0.33 (0.05) · φ_m 0.04 / 0.08 / 0.11 · Kd 0.06 / 0.09 / 0.15 · C₀ 0.00 / 0.00 / 0.00 · k 0.00 / 0.00 / 0.02.

*Jaduguda deposit · sulphate:* β 0.24 (0.22) / 0.21 (0.10) / 0.32 · ω 0.03 / 0.03 / 0.14 · aperture 0.00 / 0.00 / 0.00 · D_e 0.00 / 0.00 / 0.00 · GAIN 0.00 / 0.07 / 0.00 · REF 0.00 / 0.10 / 0.00 · FLOOR 0.00 / 0.00 / 0.00 · **K 0.39 (0.37) / 0.42 (0.23) / 0.71 (0.34)** · gradient 0.13 / 0.17 / 0.33 · φ_m 0.05 / 0.08 / 0.12 · Kd 0.17 (0.13) / 0.15 (0.12) / 0.31 · C₀ 0.01 / 0.00 / 0.17 (0.08).

*Belt point · uranium (fractured, belt):* **β 0.29 (0.30)** / 0.04 / 0.27 · ω 0.18 (0.15) / 0.05 / 0.25 · aperture 0.02 / 0.00 / 0.00 · D_e 0.03 (0.06) / 0.00 / 0.00 · GAIN 0.00 / **0.55 (0.43)** / 0.00 · REF 0.00 / 0.37 (0.29) / 0.00 · FLOOR 0.00 / 0.00 / 0.00 · K 0.26 (0.22) / 0.06 / **0.65** · gradient 0.14 (0.10) / 0.07 / 0.24 (0.11) · φ_m 0.05 / 0.03 / 0.11 · Kd 0.09 (0.10) / 0.03 / 0.27 · C₀ 0.00 / 0.00 / 0.00 · k 0.01 / 0.00 / 0.02.

*Belt point · sulphate:* β 0.34 (0.31) / 0.17 (0.08) / 0.39 · ω 0.04 / 0.03 / 0.13 · aperture 0.01 / 0.00 / 0.00 · D_e 0.00 / 0.00 / 0.00 · GAIN 0.00 / 0.28 (0.29) / 0.00 · REF 0.00 / 0.19 (0.14) / 0.00 · FLOOR 0.00 / 0.00 / 0.00 · K 0.25 (0.22) / 0.23 / 0.50 (0.11) · gradient 0.12 / 0.11 (0.18) / 0.26 · φ_m 0.07 / 0.07 / 0.18 · Kd 0.23 (0.21) / 0.13 (0.19) / 0.26 · C₀ 0.01 / 0.00 / 0.11.

*Ranchi non-ore · uranium:* **degenerate** for all three outputs — the source is suppressed (`u_suppressed = true`), the output is constant over the whole design and the indices are undefined; reported as such, not as zero.

*Ranchi non-ore · sulphate:* β 0.28 (0.07) / 0.01 / 0.49 · ω 0.10 / 0.00 / 0.24 · aperture 0.00 / 0.00 / 0.00 · D_e 0.00 / 0.00 / 0.00 · GAIN 0.00 / 0.25 (0.17) / 0.00 · REF 0.00 / 0.10 (0.11) / 0.00 · FLOOR 0.00 / 0.00 / 0.00 · K 0.22 / 0.00 / 0.58 · gradient 0.23 / 0.01 / 0.40 · φ_m 0.19 / 0.00 / 0.23 · Kd 0.24 / 0.01 / 0.40 (0.29) · **C₀ 0.28 (0.14) / 0.78 (0.67) / 0.02**.

Reading: the transport outputs are governed by K and β with the gradient and Kd next; the footprint is governed by the leach-disc growth constants (and, at the non-ore pin, by C₀ through the attribution threshold); the fracture aperture, D_e and the attribution floor contribute ≈ 0 at 20 years; ω matters only for the ring concentration and for belt uranium. Where S1 is well below S_T the input acts mainly through interactions (β and K on the ring concentration).

\newpage

*End of report.*
