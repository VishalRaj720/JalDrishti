# JalDrishti — pre-report audit and improvement plan

**Written 2026-09-20.** Purpose: decide, with evidence, what must be done to the
project before the Technical Research Report is written, and what must *not* be
done. Nothing below was taken from documentation alone; every status was checked
against the tree, the data files, the running tests, or the deployed API on the
date above. Where a claim rests on a document rather than on code, it says so.

The companion file `TECHNICAL_REPORT_STRUCTURE.md` fixes the report's structure.
This file fixes what the report will be *about*.

---

## 0. What was inspected, and how

| Check | Method | Result |
|---|---|---|
| Original objectives | `docs/local/My_Proposal.pdf` (6 pages, text + methodology diagram) extracted with pdfplumber and read in full | §1 |
| Engine tests | `python -m pytest ml_pipeline/tests -q` | **337 passed, 1 skipped**, 104 s |
| Engine end-to-end audit | `python -m ml_pipeline.validation.end_to_end_audit` | 39 PASS / **2 FAIL** — the two known ones (§2.2) |
| Backend tests | `pytest` under `.localenv` against local PostGIS | **462 passed**, 630 s (README still says 402 — drift, §2) |
| Deployed API | `GET https://jaldrishti-api.onrender.com/health` | 200 after a 53 s cold start (free tier); public advisories endpoint returns the one published Jaduguda screening |
| Data files | pandas profile of `Datasets/waterQuality_jharkhand.csv`, `cgwb_waterlevel_jharkhand.csv`, `naquim_vertical.csv`; headers of the Texas files | §5 |
| Re-bake cost | `generate --scenarios 6 --mc 48` timed at 46 s → **~2 h for the 900-scenario bake** | §11 |
| External data | NWDP (nwic.gov.in) CKAN API queried for CGWB Jharkhand quality datasets | §6 |

### 0.1 Backend test result

`462 passed in 630.50s` (2026-09-20, local PostgreSQL 18 + PostGIS, `.localenv`). No failures, no skips.

---

## 1. The original objectives, extracted from the proposal

The proposal (TEXMiN–BIT Sindri UG Fellowship 2025, *Smart Water Monitoring: Machine
Learning and CPS for Safe & Sustainable Mining*) commits to three objectives, six
deliverables, a stated CPS genesis, a list of input parameters, and a methodology
diagram. They are reproduced here in condensed form because the report must be
judged against **these**, not against what the code happens to do.

**Objectives (proposal §6)**

- **O1.** Develop ML-based predictive models to assess water-quality degradation and
  aquifer vulnerability in mining-affected ISR regions.
- **O2.** Identify key data gaps in hydrogeological systems and recommend improved
  monitoring strategies.
- **O3.** Design a prototype tool that integrates prediction, visualization and
  decision-support features for stakeholders.

**Deliverables (proposal §12)**

- **D1.** ML-based predictive models to *forecast groundwater quality trends* and assess
  aquifer vulnerability near uranium ISR sites.
- **D2.** Identification of critical data gaps in hydrogeological and chemical
  monitoring, with recommendations to improve existing frameworks.
- **D3.** Prototype decision-support tool with a user-friendly interface for stakeholders
  to input data and receive vulnerability assessments **and alerts**.
- **D4.** Visualization dashboard for *real-time* monitoring and interpretation of
  water-quality indicators.
- **D5.** Scalable framework adaptable to other mining contexts (coal, rare earth, heavy
  metals).
- **D6.** Contribution to Mine Safety using AI/ML and CPS technologies.

**CPS genesis (proposal §10).** "Integrating environmental sensors, real-time data
streams and ML algorithms into a unified monitoring framework … a closed-loop system."

**Proposed inputs (proposal §7).** pH, temperature, EC, TDS, turbidity; sulphate,
nitrate, chloride, hardness (Ca, Mg); Fe, Mn, As; groundwater-level fluctuation,
distance to mining sites, seasonal rainfall/monsoon variation.

**Methodology diagram (proposal §11).** Problem scoping → data collection and
preprocessing → feature engineering/selection → model development (*classification:
Random Forest, SVM; regression: Gradient Boosting, ANN*) → cross-validation and
hyper-parameter tuning → evaluation and comparison → **sensitivity analysis** →
**data-gap analysis** (identify missing data points, recommend additional monitoring)
→ prototype (front end, ML integration, dashboard, *simulate case study*) → testing.

The five-point framing in the request maps onto these as: (1) → O1/D1, (2) → O2/D2,
(3) → O2/D2, (4) → O3/D3/D4, (5) → D3/D6.

---

## 2. Completion audit

Classification key: **FIV** fully implemented and validated · **IWV** implemented but
weakly validated · **FP** functional prototype · **SH** simulated/hypothetical ·
**PM** placeholder/mock · **CO** conceptual only · **M** missing.

| Objective / feature | Current implementation | Evidence | Status | Scientific / technical quality | Remaining gap |
|---|---|---|---|---|---|
| **Water-quality degradation prediction — ISR source (O1, D1)** | Physics engine (Domenico/Ogata-Banks plan solve, Tang matrix diffusion, Goltz-Roberts dual-porosity clock, E1 leach-zone geometry, restoration drawdown law) + XGBoost P10/P50/P90 surrogate with Mondrian split-conformal calibration, 40 features, 4 species | `ml_pipeline/physics/transport.py`, `ml/train.py`, `ml/artifacts/metrics.json` (n = 17,835 rows, 900 scenarios), `validation/end_to_end_audit.py` | **IWV / SH** | Engineering rigour is high: kernel benchmarked against an exact solution (`physics/exact_reference.py`), leakage-controlled GroupKFold on scenario *and* on aquifer polygon, conformal coverage gated on a field-resampled batch (0.865/0.904/0.912). Structurally **unvalidatable**: no ISR plume exists in Jharkhand to compare against | (a) plume extent rests on β, served at 10 while the tool's own porosities imply ~2–3 (`LIMITATIONS.md` §1d; confirmed in code: `DUAL_POROSITY.beta_range=(2,8,20)`, served at the mean in `resolve.py:311`, sampled U(2,20) in `generate.py:182`); (b) radium misses the project's own R²(log) ≥ 0.60 gate on 2 of 8 cells; (c) **no baseline model** is reported alongside the surrogate; (d) hyper-parameters are fixed (`COMMON` in `train.py`), no search reported |
| **Water-quality prediction — from *measured* data (D1 "forecast trends")** | None as ML. Measured chemistry is assessed against IS 10500:2012 (`services/water_quality.py`, 15 determinands) and banded (`services/health_bands.py`) | 397 wells, **one sample each, all 2023** (`Datasets/waterQuality_jharkhand.csv`, profiled) | **M** as forecasting; **FIV** as rule-based assessment | The rule-based assessment is correct and well tested; but *nothing forecasts a chemistry trend*, because the data has no time axis. The proposal's classification/regression on measured data was never possible with this file | The only way to honour D1's "trends" is temporal chemistry data (§6.1). Absent that, the report must say forecasting of measured quality was not achievable and why |
| **Aquifer vulnerability (O1, D1)** | *Source-specific* vulnerability: `shallow_impact_screening` (3 pathways: dispersive, advective leakage, wellbore), vertical attenuation (Domenico erf), duty-cycle seasonal gradient, per-district NAQUIM layer split, excursion probability `P_ex`, compliance-ring concentration | `transport.py:597-760`, `config/parameters.py` `VERTICAL`, `naquim_vertical.csv` (24 districts, 21 from NAQUIM PDFs, 3 regional estimates), portal `console/VerticalPanel.tsx` | **FP / SH** | Conceptually sound and to scale; but `Kv/Kh`, `upward_gradient=0.005`, `wellbore_failure_prob=0.05` are registered scenario assumptions with no local measurement. No *intrinsic* vulnerability index (DRASTIC-type) exists — a deliberate choice that the report must defend | Explain why source-specific vulnerability was chosen over intrinsic; do not build DRASTIC (§3 D4) |
| **Plume simulation (O1, O3)** | 2-D depth-integrated concentration field in the ore horizon + 2.5-D vertical screening; Monte-Carlo parameter bands; time horizon 0–50 yr; restoration; NUREG-1569 2-of-3 excursion test on Cl/TDS/SO₄ | `transport.py`, `dashboard/server.py`, `dashboard/isr_excursion.py`, 337 tests | **FIV** (against exact solutions) / **SH** (against reality) | The single largest scientific weakness of the whole project is β (§4.2). Everything else in the transport chain has provenance in `JHARKHAND_FIDELITY_MATRIX.md` | β prior and central value (§10, item 1) |
| **Spatial visualization (O3, D4)** | Console (Leaflet; 3 basemaps; aquifers, ore, wells, rivers, strike, advisories; ISR/District modes; live engine run on click), citizen map, report map, network-plan map, front page map | `frontend/portal/src/pages/Console.tsx` (1,319 lines), `console/mapLayers.ts`, `CitizenMap.tsx`, `NetworkPlan.tsx` | **FIV** (builds and typechecks; verified in R15/R16 by browser) | Good. Bands drawn as P10/P90 envelope ellipses; extrapolation flagged as a chip | No **time animation** of the plume (§8); no statewide **coverage/confidence layer** (§9) |
| **Alert system (D3)** | 4 kinds — `measured_exceedance` (lab results vs IS 10500), `published_screening` (footprint ∩ block), `aquifer_pathway` (shared shallow aquifer within advective reach), `aquifer_breach_due` (elapsed time vs modelled breakthrough, dry-run by default). Severities `info / warning / high`. Block subscriptions + home block at registration; email via SMTP; in-process scheduler; delivery ledger with RLS | `backend/app/services/alerts.py` (904 lines), `notify.py`, migration `0025`, `tests/test_r16_alert_delivery.py`; deployed DB holds 33 alerts | **FP** (verified end-to-end locally; email dormant until `SMTP_*` set on the host) | Thresholds are the published IS 10500 limits; severity = multiple of the limit. Honest about observed vs modelled in the body prose. **Not** structured: the seven questions in the brief (what / which parameter / where / how serious / observed-or-predicted / confidence / what next) are answered in free text or not at all. No "critical" tier. No uncertainty attached to a modelled alert. No rate-of-change trigger (impossible on one sample per well) | §7 |
| **Data-gap identification (O2, D2)** | Block ranking by observation (never by predicted risk) with visible weights; suggested well sites; gap matrix; `data_quality.py`; `untested_health` on every band; `Not tested` band distinct from `No data`; `UNGROUNDED_PARAMETERS` register exposed at `/ml/assumptions`; `LIMITATIONS.md` | `services/monitoring_gaps.py`, `api/v1/data_gaps.py` (4 routes), `pages/DataGaps.tsx`, `NetworkPlan.tsx` | **FP** (application-level) | The weights (30/30/20/15/5) are a stated policy, not a measurement, and say so. No sample-level **analytical QA** (charge balance) exists although every major ion is measured | The written data-gap analysis (D2 as a *document*) does not exist yet — it becomes report §6.9/§7. Add charge-balance QA (§10 item 5) |
| **CPS integration (D4, D6, §10 of proposal)** | No sensors, no telemetry. Sensing layer = CGWB manual network (397 chemistry wells, 415 level stations). CSV ingest (`/ingest/*`, admin), dataset sync, threshold → alert → notification → acknowledgement loop, scheduler | `main.py` `_alert_scheduler`, `services/ingestion.py` | **CO** for sensing; **FP** for the decision loop | R13 deliberately refused to fake a live feed with a 2013-2021 replay. Correct. "CPS-ready decision support", never "a live CPS loop" (`LIMITATIONS.md` §5) | Report must draw the CPS diagram with the physical layer marked *manual / future* |
| **ML validation (O1)** | GroupKFold(5) on `scenario_id`; leave-aquifer-out on `polygon_id`; conformal coverage per Mondrian cell; field-resampled coverage gate; on-manifold physics-law checks; SHAP top features; docs generated from `metrics.json` and test-pinned | `train.py`, `validation/field_coverage.py`, `test_docs_in_sync.py`, `shap_top_*.json` | **IWV** | Internal validation is unusually thorough. Two honest failures: radium R²(log) 0.516 / 0.431 on migration/compliance (point-mass labels). **Missing for a research report:** a baseline comparison (e.g. ridge on the same features) and a per-target held-out error table in physical units | Add baseline metrics in the retrain (§10 item 1) |
| **Decision support (O3, D3)** | Propose → single-admin publish → citizen advisory + alerts; field-observation review (regulator); scenarios; run compare; PDF report; monitoring-siting recommendations; Methods page | `services/advisory.py`, `field_observation.py`, `run_compare.py`, `pages/IsrReport.tsx`, `Publications.tsx` | **FIV** | Workflow is real and audited (immutable audit log). PDF pagination "never visually confirmed" (`LIMITATIONS.md` §4 O-8) | Verify PDF by hand once before the report screenshots |
| **Temporal simulation** | Evaluation-horizon slider re-runs the engine live (0–50 yr); lifecycle curves (8 points, one species per request since R16); engine maps model time to a calendar (`_timeline`) | `Console.tsx:949`, `api/v1/lifecycle.py`, `server.py:232` | **FP** (partial) | Everything needed exists in the engine | No frame-by-frame plume animation, no "first exceedance at the ring" marker, no alert-timing overlay (§8) |
| **Uncertainty display** | P10/P50/P90 bands (ML) drawn as ellipses; `extrapolation` flags per feature; `data_confidence` (nearest well km, PIP fallback); assumptions endpoint | `plume_geometry.py:149`, `resolve.py:42`, `Console.tsx:1264` | **FP** | Bands are *parameter* uncertainty inside the β assumption; the register says so | Join risk + uncertainty + coverage in one view; carry P90 "possible reach" into advisories (§9) |
| **Security, RBAC, deployment** | JWT + argon2, 5 roles, 21 Postgres RLS policies, rate limiting (measured), security headers, single-admin pin, production-secret guards; Neon + Render + Cloudflare Workers | `tests/test_security_hardening.py`, `test_rls.py`, `test_authz_matrix.py`, live probes | **FIV** | Solid. Free tier sleeps the API (53 s cold start measured today) and with it the scheduler | Acceptable for a demonstrator; state it |
| **Scalability to other mining contexts (D5)** | Species registry split (`SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES`); chloride added without retrain as proof | `config/parameters.py` | **CO** | Designed-for, not demonstrated | Claim as designed-for only |
| **Documentation** | `README.md`, `docs/*.md` (7), `ml_pipeline/*.md` (4), generated `roles.md`, LIMITATIONS register | — | FIV with **drift**: README and `.claude/CLAUDE.md` say "402 tests"; the suite has **462** today; `roles.md` must be regenerated after any route change | Sync before the report (§10 item 7) |
| **Automated tests — frontend** | Only `tests/no-credentials-in-bundle.mjs` (build guard). No unit/component/e2e tests | `frontend/portal/tests/` | **M** | Every portal behaviour was verified by hand in the browser (R14–R16 records) | Optional smoke tests (§3 C) |
| **Reproducibility of the trained model** | Artifacts committed; **training CSV gitignored** and absent from this worktree (`outputs/synthetic_training.csv` exists only in the main checkout, 15 MB, 2026-08-10); seed and generator version in `synthetic_meta.json` | `end_to_end_audit`: `[FAIL] training CSV present — missing` | **IWV** | The bake is deterministic by seed, so the CSV is regenerable in ~2 h | Commit `synthetic_meta.json` + a hash of the CSV next to the artifacts (§10 item 1) |

### 2.1 Summary verdict

The prototype (O3) is complete and deployed. The data-gap machinery (O2) is
implemented in the application and needs only its *document*. The prediction
objective (O1) is met **for the ISR source term** by a physics-informed surrogate whose
internal validation is strong and whose external validation is impossible — and it is
**not met for measured water quality**, because the measured record has no time axis.
The one scientific defect that a reviewer would find on the first screen is β.

### 2.2 The two failing gates, and what to do with each

| Gate | Value | Decision |
|---|---|---|
| Training CSV present | missing in this worktree | Regenerated by the β re-bake; commit its hash and meta afterwards |
| Radium R²(log) ≥ 0.60 | 0.516 / 0.431 | **Not fixed by code in the last month.** The remedy (zero-inflated two-stage head) is a new ML approach. The report states the failure, its cause (81.8 % exact-zero labels), that conformal coverage on those cells still holds (0.891–0.986), and that the analytical engine serves the central value. This is the "report it rather than move the threshold" rule applied to itself |

---

## 3. Where the smallest work buys the most scientific quality

Ranking criteria, scored 1–5 (5 = best for the project): relevance to an objective
(R), scientific value (S), demonstration value (D), data availability (A),
implementation ease (I), validation ease (V), time (T, 5 = short), risk of unreliable
assumptions (K, 5 = low), improvement to the report (P).

| # | Candidate | R | S | D | A | I | V | T | K | P | Σ | Bucket |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | β: porosity-derived central value + wider prior; re-bake, retrain, recalibrate, sync docs | 5 | 5 | 4 | 5 | 3 | 4 | 3 | 4 | 5 | 38 | **A** |
| 2 | Baseline model + reproducibility meta bundled into the same retrain | 4 | 4 | 2 | 5 | 5 | 5 | 5 | 5 | 5 | 40 | **A** |
| 3 | Documentation sync (README/CLAUDE counts, roles.md regen, LIMITATIONS §1d closure) | 3 | 2 | 2 | 5 | 5 | 5 | 5 | 5 | 5 | 37 | **A** |
| 4 | NWDP multi-year CGWB chemistry for Jharkhand (temporal replicates) | 5 | 5 | 4 | **?** | 3 | 3 | 3 | 3 | 5 | 34+ | **B (conditional)** |
| 5 | Alert tiers grounded in IS 10500 + structured seven-field explanation + P90 "possible reach" | 5 | 3 | 5 | 5 | 4 | 4 | 4 | 4 | 5 | 39 | **B** |
| 6 | Plume timeline frames for stored runs (t₀…tₙ) with ring concentration and first-exceedance marker | 4 | 3 | 5 | 5 | 3 | 4 | 3 | 5 | 4 | 36 | **B** |
| 7 | Sample-level QA: ionic charge balance on all 397 analyses (+ EC–TDS consistency) | 4 | 4 | 3 | 5 | 5 | 5 | 5 | 5 | 4 | 40 | **B** |
| 8 | Global sensitivity analysis (OAT + Sobol-style) over the 12 registered ungrounded parameters at 3 reference sites — an offline experiment for the report | 4 | 5 | 3 | 5 | 4 | 4 | 4 | 5 | 5 | 39 | **B** |
| 9 | Coverage/confidence map layer (blocks by observation score; nearest-tested-well distance) | 4 | 3 | 4 | 5 | 4 | 4 | 4 | 5 | 3 | 36 | **B/C** |
| 10 | Vertical x–z cross-section of the plume (Domenico product form; same physics as the existing screening) | 3 | 2 | 4 | 4 | 3 | 3 | 3 | 4 | 3 | 29 | **C** |
| 11 | Groundwater-level decline warning (Theil-Sen + Mann-Kendall, already computed) | 3 | 2 | 3 | 5 | 4 | 4 | 4 | 4 | 2 | 31 | **C** |
| 12 | Frontend smoke tests (Playwright: login per role, console run, publish) | 2 | 1 | 1 | 5 | 3 | 5 | 3 | 5 | 2 | 27 | **C** |
| 13 | Hydrochemical facies (Piper) and irrigation indices (SAR, %Na) from the measured ions | 2 | 2 | 2 | 5 | 5 | 5 | 5 | 5 | 3 | 34 | **C** (EDA only) |
| 14 | Uranium imputation for the 55 un-analysed Singhbhum wells from hydrochemistry | 3 | 2 | 2 | 4 | 4 | 2 | 4 | 2 | 2 | 25 | **C→D** (extrapolation into the one belt that differs geologically) |
| 15 | True 3-D voxel plume / 3-D volume rendering | 2 | 0 | 5 | 1 | 2 | 1 | 2 | 1 | 1 | 15 | **D** |
| 16 | IMD gridded rainfall → recharge → gradient | 2 | 1 | 2 | 4 | 3 | 1 | 3 | 1 | 2 | 19 | **D** |
| 17 | Telemetry / sensor replay "real-time" feed | 3 | 0 | 4 | 2 | 3 | 1 | 3 | 1 | 1 | 18 | **D** |
| 18 | DRASTIC intrinsic-vulnerability index | 3 | 2 | 3 | 2 | 3 | 2 | 3 | 1 | 2 | 21 | **D** |
| 19 | ANN / deep models / new ML families | 1 | 1 | 2 | 5 | 3 | 2 | 3 | 3 | 1 | 21 | **D** |
| 20 | Zero-inflated radium head (new ML approach) | 3 | 3 | 1 | 5 | 2 | 3 | 2 | 3 | 2 | 24 | **D** (this month) |
| 21 | Admin-editable physics constants | 1 | 0 | 2 | 5 | 3 | 2 | 3 | 1 | 0 | 17 | **D** |
| 22 | SMS gateway | 2 | 0 | 3 | 3 | 3 | 3 | 3 | 5 | 1 | 23 | **D** (future work) |
| 23 | HydroBASINS / HydroLAKES receptor layers | 1 | 1 | 1 | 5 | 3 | 3 | 3 | 4 | 0 | 21 | **D** (already assessed and rejected 2026-07-11) |
| 24 | Numerical model (MODFLOW/MT3D) cross-check | 3 | 4 | 2 | 2 | 1 | 2 | 1 | 3 | 3 | 21 | **D** (out of scope) |

### A. Must fix — before the report

- **A1. β.** See §4.2. The served plume is the immobile end of a range the tool cannot
  bound; the owner has already found this on the published Jaduguda report. Correct the
  central value from the model's own resolved porosities, widen the prior so the band
  expresses the structural uncertainty, re-bake, retrain, re-run every gate, `sync_docs`.
- **A2. Baseline and reproducibility.** A research report that presents an R² without a
  baseline invites the question "compared with what?". Fit a ridge regression (and a
  depth-1 gradient-boosting stump) on the same features in the same GroupKFold and report
  both next to the surrogate. Commit `synthetic_meta.json` and the SHA-256 of the training
  CSV with the artifacts so the trained model is traceable to a bake.
- **A3. Documentation sync.** Test counts in README and CLAUDE.md, `roles.md`
  regeneration, `LIMITATIONS.md` §1d moved from *open* to *closed* with the before/after
  table, model-card version bump.

### B. High-value additions

- **B1. Temporal chemistry (conditional).** The National Water Data Portal lists
  *Ground Water Quality Chemical Parameters CGWB Jharkhand (1961–2025) Manual* (CSV,
  348 KB) and the matching *Physical Parameters* file (temperature, turbidity; 153 KB).
  If it holds ≥ 2 sampling years for ≥ 50 stations that can be matched to the 2023 wells,
  it closes the project's most-cited data limitation and enables chemistry trends, per-station
  baseline statistics and a rate-of-change alert tier. Decision after profiling (§6.1).
- **B2. Alert tiers and explanation.** Warning / Alert / Critical grounded in IS 10500's
  own two-limit structure; a seven-field structured explanation on every alert; P90
  "possible reach" blocks told at Warning tier. §7.
- **B3. Timeline frames.** Per stored run, N frames of the screening-limit contour with
  ring concentration, phase and first-exceedance year, computed once in the run's
  background task and stored with it; scrub/play control in the console and report. §8.
- **B4. Charge-balance QA** on every analysis; **B5. global sensitivity analysis** as a
  report experiment. Both cheap, both answer boxes in the proposal's own methodology
  diagram ("sensitivity analysis", "identify missing data points").
- **B6. Coverage layer** on the map from the ranking that already exists. §9.

### C. Nice to have

Vertical x–z section; level-decline warning; Playwright smoke tests; Piper/SAR in the
EDA; uranium imputation as a *report-only* experiment with honest cross-validation.

### D. Do not build

3-D voxel plume (no vertical data — §4.1); rainfall/recharge chain (uncalibrated; the
seasonal signal is already *measured* in the level record); telemetry replay (misrepresents
capability); DRASTIC (different question, three of seven layers would be invented);
ANN/deep models (nothing to learn that XGBoost has not, on 17.8 k synthetic rows); the
two-stage radium head (a new ML approach with one month left); editable constants
(invalidates the surrogate); SMS (provider cost; future work); basins/lakes (already
rejected with evidence); a MODFLOW cross-check (a project in itself).

---

## 4. The 2-D plume, β, and the 3-D question

### 4.1 What vertical or temporal information actually exists

| Quantity | Present? | Where | Resolution | Usable for a vertical axis? |
|---|---|---|---|---|
| Well latitude/longitude | Yes | 397 chemistry wells; 415 level stations | point | Plan position only |
| **Well depth / screen interval** of the chemistry wells | **No** | — | — | **The decisive absence.** No sample has a known depth |
| Depth to water | Yes | 9,583 readings, 398 stations, 2013–2021, quarterly | point, shallow phreatic (median 3–7 m bgl) | Water-table surface only |
| Surface elevation | Yes (gitignored, 703 MB GLO-30) | used to bake the flow field | 30 m | Head = elevation − depth-to-water, shallow only |
| Hydraulic head, deep | **No** | no deep piezometry published for Singhbhum | — | The vertical gradient is *bracketed by the monsoon swing*, not measured |
| Geological layering | Yes | `naquim_vertical.csv`: weathered-zone base 13–22 m, fracture range to 90–258 m, confined flag, per district | **district** (24 rows) | A 3-layer conceptual column, not a 3-D geology |
| Ore depth / thickness | Partly | 7 deposits: literature depth estimates 60–250 m; thickness is a user slider | per deposit | Point estimate, no geometry |
| Hydraulic conductivity with depth | Modelled | `K(z)` depth-decay law, capped at the NAQUIM fracture base | law, not data | Assumption |
| Contaminant concentration | **Model output only** | — | — | No measured plume in Jharkhand; Texas records are per-mine, no depth |
| Time series | Levels only | as above | quarterly | Yes — but for levels, not chemistry |
| Spatial sampling density | 397 wells / 79,714 km² ≈ 1 per 200 km² | — | — | Far too sparse to interpolate anything in 3-D |

### 4.2 β — the number that decides the plume

The engine applies matrix storage as `R_eff = 1 + β·R_m` (Goltz & Roberts 1986,
`effective_capacity_ratio`), with `R_m ≈ 90` for uranium. Confirmed in code today:

- `config/parameters.py:763` — `beta_range = (2.0, 8.0, 20.0)`, annotated *"FIDELITY
  FLAW 3.4 — beta AND omega ARE UNGROUNDED LOCALLY"*.
- `dashboard/resolve.py:309-311` — served β = mean of the range = **10**.
- `synthetic/generate.py:182` — training draws β ~ U(2, 20); the Monte-Carlo band
  multiplies it by (0.6–1.4). So the band lives *inside* the (2, 20) assumption.
- `dual_porosity_beta` is a model feature (`model_card.json`), so changing its prior
  invalidates every label → re-bake + retrain.

What the model's own porosities imply, lithology by lithology
(`β_por = (n_total − n_mobile) / n_mobile` from `TOTAL_POROSITY` and
`DEFAULT_EFFECTIVE_POROSITY`): Schist 2.0 · Gneiss 1.5 · Granite 1.0 · Quartzite 1.5 ·
Charnockite 2.3 · Basement Gneissic Complex 2.75 · Basalt 4.0 · Intrusive 1.9 — and 3.0
at Jaduguda with the shear-zone mobile porosity of 0.0075. None is near 10.

The register's sensitivity table (`LIMITATIONS.md` §1d, Jaduguda, U, 20 yr): β = 10 →
11.7 m; β = 3 → 22.5 m; β = 0.5 → 61 m; β = 0.1 → 153 m and 665 ppb at the ring;
β = 0 → 938 m. Attenuation, gradient and horizon barely move it.

**On the "bottleneck vs false alarm" concern.** Both failure modes are real and they are
not symmetric:

- Serving β = 10 understates the extent for every lithology the tool resolves — the
  plume is drawn at roughly half the extent its own porosities imply.
- Simply lowering β to make the plume "look right" would be the opposite error: an
  unmeasured number tuned to an expectation.

The defensible position is to **stop choosing the number**: derive the central value
from quantities the engine already resolves with provenance (the porosities), put a
prior on it that spans the literature range of the *ratio* (not just its high end), and
let the band carry the structural uncertainty. Concretely:

1. Central β per run = `β_por` from the resolved lithology (in-support, provenance
   already on file).
2. Training prior: **log-uniform on [0.3, 20]** (a scale parameter spanning nearly two
   decades must not be sampled uniformly — U(2,20) put 89 % of its mass above β = 4).
3. Monte-Carlo band per scenario: log-uniform on `[β_por/4, 4·β_por]` clipped to the
   prior, so the P10–P90 expresses "the matrix may store four times more or four times
   less than the porosities imply".
4. The published **footprint and its block intersection stay on the central (P50)
   contour** — so the alert count does not inflate — and the P90 becomes a separately
   labelled "possible reach" (§7). At Jaduguda this moves the headline from ~12 m to
   ~22 m with a band reaching ~60 m: honest, not alarming.
5. The diffusive-clock upgrade (`R_app(t) = 1 + (2/√π)·σ·√t`, already derived in the
   config comments) is **evaluated first, adopted only if it changes the governing
   branch**: the config notes that the Tang kernel already governs for sorbing species
   via `max()`. A one-page diagnostic (which branch governs at the three reference sites)
   decides it before any label is generated.

Validation gates (unchanged, deliberately): band-order violations = 0; scenario coverage
≥ 0.80 on all three targets; field-resampled coverage ≥ 0.80; on-manifold physics laws;
per-species R²(log) reported, not gated away; `test_docs_in_sync`; the before/after
sensitivity table goes into `LIMITATIONS.md` §1d as *closed* and into the report.

### 4.3 Can a meaningful 3-D plume be constructed?

**No — and the honest reason is in the table above.** A 3-D concentration volume needs
either measured concentrations at known depths (none exist: no sample has a depth), or
a layered hydrogeological model with vertical properties at the scale of the plume
(what exists is a 3-layer *district* column with one K-decay law). Any voxel volume
rendered from this data would be a rendering of the erf factor in `vertical_attenuation`
— i.e. a picture of an assumption presented with the visual authority of a measurement.

**What the model already is.** The Domenico solution *is* three-dimensional in form; the
plan-view solve is depth-integrated over the ore horizon (thickness = the ore-thickness
input), and the vertical dimension is handled separately by the erf attenuation and the
three-pathway screening with per-district layer depths and the measured seasonal water
table. That is a **2.5-D** model with an explicit vertical *screening*, and the portal
already draws it to scale (`VerticalPanel.tsx`). This is the ceiling the data supports.

**Recommendation.**
- Keep 2.5-D. State in the report exactly why 3-D is not supported (the table in §4.1
  goes into the report's data-gap section — the absence of well depths *is* one of the
  monitoring gaps O2 asks for).
- Optional (C-list): an x–z section along the plume axis drawn from the same product
  form the screening uses, labelled with its α_V/α_L = 0.025 assumption. Useful for
  explaining the vulnerability question in the report; it introduces no new physics
  and no new data, and it must never be called "3-D".
- Never: voxel volumes, isosurfaces, or depth-resolved concentrations at wells.

---

## 5. Data we hold and do not use

Profiled today: `waterQuality_jharkhand.csv` = 397 rows, 24 districts, **year 2023
only**, 0 duplicate coordinates.

| Variable | Coverage | Used today for | Defensible additional use | Recommendation |
|---|---|---|---|---|
| pH | 397/397 | background context at the nearest well; IS 10500 range check; ambient-Kd context (not applied) | EDA; charge-balance sanity | keep as is |
| EC | 393/397 | TDS estimate (EC × factor); IS 10500 via TDS | **EC vs Σ-ions consistency check** (QA) | **B4** |
| CO₃ | 397 but **all zero** | nothing | nothing — report the zero column as a reporting artefact, not a result | report |
| HCO₃ | 393 | ambient alkalinity context; alkalinity limit | **charge balance** (anion) | **B4** |
| Cl | 397 | excursion-indicator baseline; IS limit | charge balance | **B4** |
| F | 397 | banding, alerts, IS limit | — | keep |
| SO₄ | 393 | excursion baseline; IS limit | charge balance | **B4** |
| NO₃ | 393 | banding, alerts | charge balance; spatial-outlier flag per district | **B4**; C |
| PO₄ | 393 | IS has no limit → listed as `no_limit` | EDA only | — |
| Total hardness, Ca, Mg | 393–397 | IS limits | charge balance (cations) | **B4** |
| Na, K | 397 | nothing beyond display | charge balance; SAR / %Na irrigation indices (the proposal names irrigation) | **B4**; C |
| Fe, As | **0/397** (all "-") | reported as `not_tested`; alert scanner ready | nothing — this is a finding, not a variable | report as the data gap it is |
| U | 342/397 | everything ISR-related | — | keep; the 55 un-analysed wells are all in the three Singhbhum districts — the belt itself is untested for uranium |
| Mn, temperature, turbidity, DO | **absent** (no column) | — | temperature and turbidity exist in the NWDP *physical* file (§6.1) | via B1 |
| Groundwater level (9,583 readings) | 2013–2021 | flow-field bake; Theil-Sen trends; seasonal amplitude in the vertical screening | level-decline warning (C) | keep; C |
| DEM | gitignored | flow-field bake only | nothing further needed | keep |
| Aquifer polygons (lithology, K, Sy) | statewide | K, porosity, regime | — | keep |
| Lineaments (1,889) | statewide | strike field → anisotropy, display azimuth | — | keep |
| Rivers (4,577 reaches) | statewide | receptor distance, plume-crossing note | — | keep |
| NAQUIM vertical | 24 districts | layer split, fracture range, confined flag | — | keep |
| UDEPO grades | 9 deposits | grade-scaled C₀ | — | keep |
| Texas ISR: `TX_ISR_Final.xlsx` (86/9/86 rows), `AquiferExemptions`, `Restoration`, `TexasISROperations` | read | C₀ envelope, residuals, porosity, restoration reference years, operating ranges | — | keep |
| Texas ISR: `AreaInformation`, `MinePermits`, `DisposalVolumes`, `CitationsSources` | **not read** | — | `CitationsSources` belongs in the report's references; the others carry no transport information | cite; leave |
| Sub-district boundaries (19 MB) | loaded as `blocks` | block resolution, alerts | — | keep |

**Verdict.** The measured record is now read almost completely (R13–R15 closed the
"collected and not read" finding). The one genuinely unused *information* in the file
is the **internal consistency of each analysis** — every major ion is present, which
is exactly what a charge-balance test needs, and no such test exists. That is the
cheapest defensible addition in this plan.

---

## 6. External datasets — investigated, not assumed

### 6.1 CGWB groundwater quality, National Water Data Portal — **recommend, conditional**

Found today via the portal's CKAN API (`nwdp.nwic.gov.in/api/3/action/package_search`):

| | Chemical parameters | Physical parameters |
|---|---|---|
| Package | `ground-water-quality-manual-chemical-parameters-cgwb-f-gfg` | `ground-water-quality-manual-physical-parameters-cgwb` |
| Jharkhand resource | *Ground Water Quality Chemical Parameters CGWB Jharkhand (1961 – 2025) Manual*, CSV, **347,780 bytes** | *… Physical Parameters CGWB Jharkhand (1961 – 2025) Manual*, CSV, 153,435 bytes |
| Stated variables | pH, EC, TDS, CO₃, HCO₃, alkalinity, Cl, SO₄, NO₃, PO₄, TH, Ca, Mg, Na, K, F, SiO₂ (per the portal description; trace metals "included" — to be verified in the file) | temperature, turbidity |
| Provider | CGWB via National Water Informatics Centre | same |
| Access | direct CSV download, no login seen in the API response | same |

- **Compatibility:** same provider and network as the 2023 file the project already
  uses; join by station name and/or coordinate proximity.
- **What it enables if it holds temporal replicates:** chemistry trends per station
  (Theil-Sen/Mann-Kendall already implemented for levels — reuse the module), a
  per-station baseline mean and UCL for the NUREG-style excursion statistics that
  `LIMITATIONS.md` §3 says are blocked, a *rate-of-change* alert tier, and — for the
  report — the first use of measured data with a time axis in O1.
- **Preprocessing:** parse; harmonise units and detection-limit strings; de-duplicate
  stations; charge-balance QA (B4 doubles as its filter); map to blocks by
  `ST_Contains`.
- **Assumptions introduced:** station identity continuity across decades; laboratory
  method changes over time (treat pre-2000 rows with suspicion; report the year
  distribution).
- **Decision rule:** integrate only if ≥ 2 distinct sampling years for ≥ 50 stations
  matchable to the current wells. Otherwise document the attempt and keep the current
  file.
- **Cost:** ~1 h to profile; 1–2 days to integrate (ingest path exists:
  `/ingest/water-quality/csv`; the `water_samples` table already keys on
  `(well_id, sampled_at)`).
- **Not done today:** the file has not been downloaded — that needs your go-ahead
  (348 KB + 153 KB, from `nwdp.nwic.gov.in`).

### 6.2 Everything else — considered and rejected, or already held

| Dataset | Verdict | Reason |
|---|---|---|
| IMD gridded rainfall (0.25°, 1901–) | **reject** | Would need rainfall → recharge → gradient with no calibration; the monsoon effect on the gradient is already *measured* in the quarterly level record and enters the model as `seasonal_amp` |
| WRIS telemetry water levels (hourly) | **reject** | Few Jharkhand stations; the only use would be to make a "real-time" claim the project has decided not to make |
| Copernicus GLO-30 DEM | already held | baked into the flow field |
| CGWB NAQUIM district reports | already held | 21 of 24 districts extracted |
| Bhuvan/GSI lineaments | already held | strike field |
| IAEA UDEPO | already held | grade-scaled C₀ |
| USGS Texas ISR (Dataset 1 & 2) | already held | source term, restoration |
| Soil / land-use (NBSS&LUP, Bhuvan LULC) | **reject** | only needed for DRASTIC, which is not being built |
| HydroBASINS / HydroLAKES | **reject** | assessed 2026-07-11 with evidence; adds no receptor coverage |
| UCIL/AERB Jaduguda monitoring | not a dataset | published papers only (one already in `Datasets/phase1_sources`); use as a literature anchor in the report, not as data |
| JSPCB water quality | **reject** | surface water; groundwater coverage negligible |

---

## 7. The alert system — from "a row in a table" to a decision-support workflow

### 7.1 What is feasible with the current data, trigger by trigger

| Trigger | Feasible now? | How | Basis |
|---|---|---|---|
| Concentration threshold (observed) | **Yes — built** | `scan_measured_exceedances`, IS 10500 limits | observed |
| Predicted future concentration | **Yes — built** in part | `published_screening` (footprint), `aquifer_breach_due` (modelled breakthrough elapsed); the ring concentration and P_ex exist on the run but are not in the alert | modelled |
| Rate of change — chemistry | **No** (one sample per well) → **yes after B1** | Theil-Sen on ≥ 3 samples | observed |
| Rate of change — levels | Yes (C) | `groundwater_trends` already classifies declining stations | observed |
| Anomaly detection | Yes, as a **staff** (not citizen) alert | charge-balance failure > 10 %; per-district spatial outlier (> 3 MAD) | data-quality |
| Spatial propagation | **Yes — built** (P50 footprint ∩ block) → add P90 possible reach | ML envelope ellipse already computed (`ml_envelope_ellipses`) | modelled + uncertainty |
| Proximity to sensitive / down-gradient zones | Yes | monitoring wells and perennial reaches inside the P90 reach → "what to monitor next" | modelled |
| Uncertainty | Yes | attach P10–P90 migration, `extrapolation` flags, `data_confidence` to modelled alerts | — |
| Multiple parameters | **Yes — built** (one alert per well listing every breach) | — | observed |
| Deterioration over time | only via B1 or levels | — | observed |

### 7.2 Tiers — using the standard's own structure, not invented numbers

IS 10500:2012 already defines two limits per determinand: the *acceptable* limit and the
*permissible limit in the absence of an alternate source* (with "no relaxation" for
nitrate, uranium and others). The service already classifies every reading into
`acceptable / above_acceptable / above_permissible`. The tiers therefore fall out of the
standard, with one project-defined threshold that must be labelled as such:

| Tier | Observed (laboratory) | Modelled (screening) | Label in copy |
|---|---|---|---|
| **Notice** | — | a screening was published for your block; P50 footprint | "modelled, not measured" |
| **Warning** | above *acceptable* but within *permissible* (e.g. F 1.0–1.5 mg/L); or a "possible reach" block (inside P90, outside P50); or breach-due | as now for `aquifer_pathway`, `aquifer_breach_due` | "observe / test" |
| **Alert** | above *permissible* (or above acceptable where the standard says no relaxation) and < 2× | ring concentration predicted above the limit within the run's horizon with P_ex ≥ 0.5 | "act" |
| **Critical** | ≥ 2× the limit, **or** two or more health determinands above their limit at the same well *(project-defined multiplier — say so)* | never for a modelled result (no mine exists) | "immediate attention" |

The existing `warning`/`high` split at 2× survives as Warning→Alert→Critical; the change
is one more rung and a name for it.

### 7.3 The seven questions, as fields not prose

Add to every alert (schema + migration `0026`, response, email template):

`basis` (observed | modelled) · `driver` (determinand, value, unit, limit, times_limit)
· `where` (block, district, well name or footprint ha) · `tier` · `confidence`
(observed: laboratory result, sample date; modelled: P10/P90 band, extrapolation flags,
data-confidence reasons) · `next_action` (determinand-specific: re-sample, test for the
un-analysed determinands, alternate supply; modelled: which wells lie inside the P90
reach and when the ring is first predicted to exceed) · `what_happened` (one sentence).

The prose body stays for readability; the fields make the workflow auditable and let
the report show the chain *data → detection → prediction → vulnerability → alert →
explanation → recommended action* as a table of real records rather than a diagram.

---

## 8. Temporal simulation — feasible, and worth more than a prettier map

Everything needed exists in the engine: `time_years` is an input; the analytical solve is
0.2 s locally; the lifecycle endpoint already evaluates 8 horizons; `_timeline` maps
model time to a calendar. What is missing is only the *frames* and the *control*.

**Design.**
- At run completion (already a background task), evaluate the analytical engine at
  N = 10 horizons (0, 1, 2, 3, 5, 8, 10, 15, 20, horizon) and store per frame: the
  screening-limit contour polygons, footprint ha, migration m, ring concentration, phase
  (operation / restoration / post-closure), and `first_exceedance_year` at the ring if
  any. Store as `plume.timeline` on the run (≈ 10 × a decimated ring — small).
- Console and report: a scrub/play control that swaps the drawn contour, with a strip
  chart of ring concentration vs time and a marker at the first exceedance and at the
  modelled shallow breakthrough. Compare page: two runs side by side at the same t.
- Nothing is animated that the engine did not compute; the ML band is not interpolated
  between frames (it is drawn at the run's own horizon only, as now).
- Cost: N extra engine evaluations per run — trivial locally, ~40 s on Render, inside a
  job that is already asynchronous.

**Why it matters for the report.** Figure: five frames of the Jaduguda run at 2, 5, 10,
20, 50 yr with the ring and the shallow-aquifer breakthrough year marked; table: the
year each tier would first fire. That is the demonstration the proposal's "simulate case
study" box asks for.

---

## 9. Uncertainty and data gaps — show it, do not describe it

Already on screen: P10/P50/P90; extrapolation chips; nearest-well distance; the
`Not tested` band; `untested_health`; the block observation ranking with visible weights;
the gap matrix; the assumptions register. What is missing is the *join*:

1. **Coverage layer** (B6): blocks shaded by the observation score that
   `/data-gaps/recommendations` already computes; a second layer "distance to nearest
   uranium-tested well". Toggleable on the console and the citizen map so that risk and
   coverage can be read together. No new computation.
2. **P90 possible reach in the advisory** (B2): the published record carries the
   central footprint *and* the P90 ellipse, and the map draws both, dashed.
3. **Charge-balance QA** (B4): each of the 397 analyses gets a charge-balance error;
   > 5 % flagged, > 10 % excluded from banding with the reason shown. A standard test
   (Hem 1985; Freeze & Cherry 1979) that turns "we trust the lab" into a number.
4. **Global sensitivity analysis** (B5): an offline script over the 12 registered
   ungrounded parameters at three reference sites (Jaduguda deposit, a belt point, a
   non-belt point) with one-at-a-time ranges *and* a Sobol-style variance decomposition
   on migration, area and ring concentration. Output: one figure and one table for the
   report; also stored as a JSON artifact and surfaced on the Methods page. This is the
   "sensitivity analysis" box of the proposal, and it is what makes the β discussion a
   result instead of an anecdote.

---

## 10. The final feature set

| # | Feature | Objective | Why it matters | Data required | Complexity | Scientific risk | Recommendation |
|---|---|---|---|---|---|---|---|
| 1 | **β correction + retrain** (porosity-derived central value, log-uniform prior, MC band; diagnostic on the diffusive clock first; baseline models and reproducibility meta bundled) | O1 | The served plume is half the extent the model's own porosities imply; a reviewer finds it on the first screen | none new | M (≈ 3 h compute + 1 day) | Low — it removes an inconsistency; every gate stays | **Do first** |
| 2 | **Alert tiers + structured explanation + P90 possible reach** | D3, O3 | Turns alerts into the auditable workflow the brief asks for; uses IS 10500's own two limits | none new | M (1–2 days) | Low; one project-defined multiplier, labelled | **Do** |
| 3 | **Timeline frames on stored runs** | O3, D4 | The "simulate case study" of the proposal, shown as change over time; report figure | none new | M (1–2 days) | None | **Do** |
| 4 | **Charge-balance QA + global sensitivity analysis** | O2, O1 | Two proposal boxes answered with standard methods; feeds report §3.5 and §6 | none new | S (1 day both) | None | **Do** |
| 5 | **Documentation sync + LIMITATIONS closure + Completion Matrix** | all | Report integrity | — | S (½ day) | None | **Do** |
| 6 | **NWDP temporal chemistry** | O1 (D1 trends), O2 | The only path to "forecast trends" on measured data; closes the register's §3 blocker | 2 CSVs, ~0.5 MB | M (profile ½ day; integrate 1–2 days if it qualifies) | Medium — decades of lab-method drift; mitigated by QA and year filtering | **Profile, then decide** |
| 7 | Coverage layer | O2 | Risk + uncertainty + coverage in one view | none new | S (½ day) | None | Do if time |
| 8 | x–z section | O1 | Explains the vulnerability question better than a number | none new | M (1 day) | Low if labelled | Optional |
| 9 | Level-decline warning; Playwright smoke tests; Piper/SAR | — | quality-of-life | none | S–M | None | Optional |

### If this were my project, the five things I would implement before writing

1. **β** — because it is the one thing a hydrogeologist on the panel will ask about, and
   the fix is a re-bake, not a new theory.
2. **Alert tiers and the seven-field explanation** — because D3 says "alerts", and the
   report's central figure should be a real alert record answering the seven questions.
3. **Timeline frames** — because "simulate case study" is in the proposal and a
   time-evolving plume with the first-exceedance year is the demonstration that
   distinguishes a screening tool from a map.
4. **Charge balance + sensitivity analysis** — one day, two proposal boxes, two report
   sections.
5. **Documentation sync and the Completion Matrix** — so that every number in the
   report is traceable to a file at a commit.

And, in parallel, **profile the NWDP file** (item 6): if it delivers temporal replicates,
it is worth more than items 3 and 4 together, and the decision takes an hour.

---

## 11. Implementation plan (Phase 11) — order, gates, and what each step must not touch

Constraints honoured throughout: `ml_pipeline/` physics is changed only where sanctioned
(β prior/central value; optional clock), and every change is recorded in
`LIMITATIONS.md` as the fourth sanctioned change; no route removed; no migration that
rewrites existing rows; RLS traps (§CLAUDE.md) checked on every new write path; frozen
artifacts replaced atomically with backups.

### WP-0 — Start the long job first (day 1, hour 0)

1. Branch `r17-beta-and-alert-workflow` from `main`.
2. Diagnostic script (scratch): at Jaduguda / belt / non-belt, for U and SO₄, report
   which branch governs the front (continuum clock vs Tang) and the migration under
   {β = 10, β_por, β_por/4, 4β_por} with and without the diffusive clock. **Decision:**
   adopt the clock only if it changes the governing branch; record the table either way.
3. Config change: `DUAL_POROSITY` gains `beta_prior = ("log_uniform", 0.3, 20.0)` and
   `beta_from_porosity = True`; `resolve.py` computes `β_por`; `generate.py` samples the
   prior and the MC band; `feature_engineering` unchanged (β stays a feature).
4. Unit tests first: β_por per lithology; prior sampling bounds; MC band clipped;
   served β equals β_por when no override; `E1` and every existing law test still green.
5. Back up `ml/artifacts/` → `ml/artifacts_pre_r17/`, `outputs/` likewise.
6. **Kick off the bake in the background** (`--scenarios 900 --mc 48`, ~2 h), then the
   field batch (`--scenarios 120 --mc 48 --field-mix 1.0`, ~15 min).

### WP-1 — While the bake runs: alerts (days 1–2)

1. Migration `0026`: `alerts.tier`, `basis`, `explanation JSONB`; backfill tier from
   severity (`info→notice`, `warning→warning`, `high→alert`, and `≥2×` or multi-breach
   → `critical` recomputed by the scan on next run). Writes go in the original INSERT.
2. `alerts.py`: tier ladder from `water_quality.py`'s status classes; structured
   fields; P90 possible-reach blocks (from the stored ML envelope ring) at Warning with
   the "possible reach" wording; `next_action` lists monitoring wells inside the P90
   reach (PostGIS `ST_Within`).
3. Email template and portal `Alerts.tsx`, `MyArea.tsx` cards render the fields.
4. Tests: tier assignment per status class; multi-breach → critical; modelled never
   critical; possible-reach never duplicates a footprint alert; RLS source-level guard
   on the new INSERT path; `authz_matrix` regenerated.

### WP-2 — Timeline frames (day 2–3)

1. `simulation_run.py` background task: after the run, call the adapter at the N
   horizons, store `plume.timeline`.
2. Router: `GET /simulations/runs/{id}/timeline` (already-authorised roles; the citizen
   surface gets frames only for a *published* run via `/public/risk/advisories/{id}/timeline`).
3. Portal: scrub/play in `RunResult`/`Console`, strip chart in `IsrReport`, side-by-side
   in `Compare`.
4. Tests: frame count and ordering; first-exceedance year matches the lifecycle
   endpoint; a run without timeline (pre-R17) reports `not recorded`, never "no change".

### WP-3 — QA and sensitivity (day 3)

1. `services/data_quality.py`: charge-balance error per sample (meq/L from Ca, Mg, Na,
   K vs HCO₃, CO₃, Cl, SO₄, NO₃, F); EC vs Σ-ions ratio; thresholds 5 % / 10 % with the
   citation; surfaced on Data & Gaps and the water-quality well card; excluded samples
   listed with reason.
2. `ml_pipeline/validation/sensitivity.py`: OAT + Sobol-style (Saltelli sampling, 512
   samples) over `UNGROUNDED_PARAMETERS` at three sites; writes
   `ml/artifacts/sensitivity.json` + PNG; Methods page reads it.
3. Tests: charge balance on a hand-computed sample; sensitivity script runs on a tiny
   sample count and produces the schema.

### WP-4 — Retrain and gates (when the bake finishes)

1. `train.py`: add ridge and depth-1 GBM baselines in the same GroupKFold, written to
   `metrics.json["baselines"]`; write the training-CSV SHA-256 and `synthetic_meta` into
   `model_card.json`.
2. Train → SHAP → field coverage → `sync_docs` → full engine suite → `end_to_end_audit`.
3. Gates as §4.2. If a gate fails, **report it and stop** — do not widen deltas by hand
   or narrow the prior to pass.
4. Serve-side check: Jaduguda before/after table (migration, ring conc, area, P10–P90)
   for U and SO₄ → `LIMITATIONS.md` §1d closed; `test_ml_artifacts_are_unchanged`
   baseline updated deliberately, with the reason in the commit.

### WP-5 — Optional, only if WP-1…4 are green: NWDP integration, coverage layer

1. Download the two CSVs (with your go-ahead), profile: years, stations, matchable
   wells, units. Decision by the §6.1 rule.
2. If yes: ingest via the existing CSV path; charge-balance QA; `groundwater_trends`
   generalised to chemistry; rate-of-change tier in `alerts.py`; report figure.
3. Coverage layer: one new toggle reading `/data-gaps/recommendations`.

### WP-6 — Re-audit (Phase 12) and docs

Full suites (engine, backend), `authz_matrix`, `end_to_end_audit`, browser walk of every
screen per the demo script, PDF opened by hand, deployed API redeployed and probed,
`seed_demo_story` re-run on Neon by you. Then the Completion Matrix (§12).

**Effort:** ≈ 7–9 working days plus ≈ 3 h compute, leaving the remainder of the month
for the report. If time compresses: WP-0/4 and WP-1 are non-negotiable; WP-2 next;
WP-3 is a day; WP-5 is the first thing to drop.

---

## 12. Final validation — the Completion Matrix to be filled after WP-6

| Original objective / deliverable | Final implementation | Evidence (file / test / URL) | Validation performed | Result | Remaining limitation |
|---|---|---|---|---|---|
| O1 — ISR-source prediction | | | | | |
| O1 — measured-quality trends (D1) | | | | | |
| O1 — aquifer vulnerability | | | | | |
| O2 — data gaps identified (D2) | | | | | |
| O2 — monitoring recommendations | | | | | |
| O3 — prototype (D3) | | | | | |
| D3 — alerts | | | | | |
| D4 — dashboard | | | | | |
| D5 — scalability | | | | | |
| D6 — CPS contribution | | | | | |

Rules for filling it: every "Result" cell is a number or a named artefact; every
"Validation" cell names the test file or the manual procedure and its date; a blank is a
blank, never "planned".

---

## 13. What I need from you before implementation starts

1. **Approve the five items** in §10 (and say whether the optional ones are in).
2. **β approach** — confirm the porosity-derived central value with a log-uniform prior
   [0.3, 20] and a ×4 Monte-Carlo band, or state a different prior you can defend.
3. **Permission to download** the two NWDP CSVs (348 KB + 153 KB from
   `nwdp.nwic.gov.in`) for profiling.
4. **Compute window** — the bake and retrain take ~3 h on this machine; it can run in
   the background of a session.
5. **Deployment** — after WP-4/WP-1 you will need to run `alembic upgrade head` and
   redeploy the API with the new artifacts; I will not run production migrations.

*Closing note: both suites are green on this date — engine 337 passed / 1 skipped, backend 462 passed. The two `end_to_end_audit` FAILs are the known, documented ones (§2.2).*
