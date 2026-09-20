# JalDrishti — Technical Research Report: structure and evidence map

**Written 2026-09-20**, alongside `PRE_REPORT_AUDIT_AND_PLAN.md`. This file is the
contract for the report: what each section contains, which artefact in the repository
is the evidence for it, which figures and tables it carries, and which claims it may and
may not make. It is written *before* the improvements in the plan are implemented, so
sections that depend on those improvements say so and name the fallback.

---

## 0. Is the proposed structure right? — assessment and the changes made

The baseline structure in the brief (title page → declaration → acknowledgement →
abstract → keywords → 1 Introduction → 2 Literature → 3 Study context and data →
4 Methodology → 5 Assumptions and limitations → 6 Results → 7 Discussion →
8 Deliverables → 9 Conclusion → 10 Future work → References → Appendices) is the
right skeleton for a fellowship technical report and is kept. Six changes, each with
its reason:

| # | Change | Reason |
|---|---|---|
| 1 | **§3 gains "3.6 The hypothetical scenario, precisely"** — a one-page specification of the ISR operation that is modelled (lixiviant, injection rate, wellfield width, operation years, restoration, horizon), with each value's provenance | The whole project is conditional on a scenario. A reader must be able to find, in one place, exactly what is being assumed before any result is read |
| 2 | **§4 is reordered physics-first**: 4.4 Hydrogeological framework and 4.5 Plume simulation come *before* 4.6 Machine learning | The ML surrogate is trained on the engine's output; presenting ML before the engine would invert the dependency and invite the reading that the ML "predicts reality". The engine is the authority and the report's order should say so |
| 3 | **§4.6 gains "Why a surrogate, and what it is not"** and a **baseline comparison** subsection | The proposal promised RF/SVM/GB/ANN on measured data. What was built is a physics-informed surrogate with conformal uncertainty. The report must state the substitution and the reason (no time axis in the measured record; no plume to learn from) in the methodology, not in the limitations |
| 4 | **§6 Results gains "6.0 What kind of result each subsection reports"** — a two-line legend: *measured*, *modelled (scenario)*, *model-internal validation* | The brief's rule "distinguish prediction vs simulation vs observation" is enforced structurally by tagging every result subsection rather than by relying on adjectives in the prose |
| 5 | **§6.6 "3-D results" is replaced by "6.6 Vertical (2.5-D) screening results"** | 3-D is not supported by the data (plan §4.3). The section reports what the vertical screening produces and states why no 3-D volume is presented — a negative result that belongs in Results, not in an apology |
| 6 | **§8 Deliverables is merged with the Project Completion Matrix** (Proposed → Implemented → Validated → Final status → Evidence → Remaining limitation) | One table serves both the brief's §8 and Phase 12; two would drift |

One structural addition outside the numbered sections: a **Source-to-Claim Register**
(Appendix H) listing every quantitative claim in the report with its source — a file
path and commit, a dataset and row count, or a citation. It is what Phase 14's
"maintain a source-to-claim mapping" asks for, and it is the artefact that makes the
integrity audit checkable rather than asserted.

**Citation style:** IEEE numeric, unless the mentor specifies otherwise. Datasets are
cited as references with provider, title, version/year, URL and access date.

**Length guide:** 60–80 pages including appendices for an UG fellowship technical
report; the main body (§1–§10) should not exceed ~45 pages. Figures are numbered and
captioned with the *kind* of result (measured / modelled / validation) in the caption.

---

## Front matter

### Title page
Project title (as in the proposal: *Smart Water Monitoring: Machine Learning and CPS
for Safe & Sustainable Mining*); system name JalDrishti; student name and admission
number; Department of Information Technology; B.I.T. Sindri, Dhanbad; mentor (Prof.
Sachin Kumar Agrawal, Assistant Professor, IT); TEXMiN–BIT Sindri Mining CPS CoE, UG
Call for Proposal Fellowship 2025; academic year 2025–26; submission month.

### Declaration
Use the institutional/TEXMiN format if one is issued for the final report (the proposal
carried a TEXMiN declaration on IP and confidentiality — page 6 of the proposal; check
whether the final report needs the same wording). Do not invent institutional text. If
none exists, a plain originality statement: work done by the student under the mentor's
guidance; sources acknowledged; no part submitted elsewhere; AI-assisted tooling was
used for software development and drafting under the student's direction and review
(state this plainly — it is true and it is better disclosed than discovered).

### Acknowledgement
Mentor; TEXMiN CoE and BIT Sindri; data providers by name (CGWB / NWIC, GSI/NRSC Bhuvan,
IAEA UDEPO, USGS — the Texas ISR datasets, Copernicus GLO-30, HydroSHEDS/HydroRIVERS);
open-source libraries (FastAPI, PostGIS, XGBoost, scikit-learn, Leaflet, React).

### Abstract (200–300 words)
Problem (groundwater vulnerability near ISR; reactive monitoring) → context (no ISR mine
exists in Jharkhand; the study is a preparedness screening on real hydrogeology) →
method (physics-informed transport engine, XGBoost surrogate with conformal bands,
IS 10500 assessment of the measured record, block-level alerting, data-gap ranking) →
key results (numbers from §6: surrogate held-out skill and coverage; the measured
exceedance counts; the Jaduguda case-study extent with its band; the data gaps found)
→ contribution → the principal limitation (no field validation is possible; plume
extent rests on an unmeasured matrix-storage ratio).
**Forbidden words:** real-time, validated (against reality), accurate, predicts
contamination.

### Keywords (5–8)
groundwater vulnerability; in-situ recovery (ISR) uranium mining; contaminant transport
surrogate; conformal prediction; monitoring network design; decision-support system;
Jharkhand; IS 10500.

---

## 1. Introduction

| § | Content | Evidence / source |
|---|---|---|
| 1.1 Background | Groundwater as the primary supply in Jharkhand's hard-rock terrain; ISR mechanism (alkaline lixiviant, mobilised U, SO₄, TDS, Ra); why excursions matter; the Singhbhum Shear Zone as India's uranium province (UCIL underground mines — *not* ISR) | Literature (NUREG-1569; ISR reviews; CGWB NAQUIM; UCIL/AERB publications) |
| 1.2 Problem statement | If ISR-strength lixiviant entered a Jharkhand aquifer, how far and how fast would contamination move, would it reach the shallow drinking-water aquifer, who should be told, and what should be monitored — and which of these questions can the available data answer? | — |
| 1.3 Motivation | Conventional monitoring = manual sampling, lab analysis, threshold decisions, reactive; the measured record here has one sample per well; a screening tool that says what to look for, where, is the practical contribution | Plan §2, §5 |
| 1.4 Research / technology gap | (i) No ISR-specific screening tool for Indian hard-rock hydrogeology; (ii) porous-medium ISR experience (Texas, Wyoming) does not transfer to fractured schist without a stated model; (iii) monitoring data is collected and not read (the R13 finding); (iv) alerts that reach nobody | Literature + project findings |
| 1.5 Objectives | O1–O3 verbatim from the proposal; D1–D6 listed | Proposal §6, §12 |
| 1.6 Research questions | RQ1 Can a physics-informed surrogate reproduce an analytical transport engine across Jharkhand's hydrogeology with calibrated uncertainty? RQ2 Which parameters control the modelled extent, and are they measured locally? RQ3 What does the measured CGWB record say about current water quality against IS 10500, and what does it not say? RQ4 Where are the monitoring gaps, and how should a network be prioritised? RQ5 Can a threshold → alert → notification loop be closed on the existing manual record? | Each RQ is answered in §7 |
| 1.7 Contributions | List only what this project built: the engine adaptation (E1 geometry, dual-porosity, Jharkhand fields), the surrogate with Mondrian conformal bands and field-resampled coverage gate, the measured-record assessment and citizen banding rule, the alert loop with delivery, the observation-based monitoring ranking, the assumption register, the deployed portal. **Separate** from prior work (Domenico, Tang, Goltz-Roberts, CQR, NUREG-1569) which is cited, not claimed | Repo |

---

## 2. Literature review

Compare, do not summarise. Each subsection ends with one sentence on what the reviewed
work does *not* provide for this problem. Minimum: 30–40 verified references overall.

| § | Scope | What to compare | Gap sentence feeds |
|---|---|---|---|
| 2.1 Groundwater quality assessment | WQI construction and its known failure (inverse-limit weighting), IS 10500 / WHO / BIS limits, CGWB assessment practice | index-based vs limit-based reporting | §4.7, §6.1 |
| 2.2 ML for water-quality prediction | RF/SVM/GBM/ANN studies on Indian groundwater; what data they had (multi-year, many stations); surrogate modelling of physics codes; conformal prediction in environmental ML | data requirements vs what exists here | §4.6 |
| 2.3 Aquifer vulnerability | DRASTIC/GOD/SINTACS (intrinsic) vs source-specific/process-based vulnerability; why intrinsic indices need soil/recharge/vadose layers | intrinsic vs specific | §4.7 |
| 2.4 Contamination / plume modelling | Domenico & Robbins; Ogata-Banks; Tang-Frind-Sudicky; Goltz-Roberts; dual-porosity in crystalline rock; ISR excursion literature (NUREG-1569, NUREG/CR-6733); Texas/Wyoming ISR restoration records | analytical vs numerical; porous vs fractured | §4.5 |
| 2.5 Spatial / hydrogeological modelling | flow-field estimation from head observations; lineament-based anisotropy; NAQUIM aquifer mapping | — | §4.4 |
| 2.6 Monitoring systems and network design | CGWB network design norms; ISR monitor-well spacing (NUREG); optimal-network objectives | observation-based vs risk-based siting | §4.9 |
| 2.7 ML/CPS environmental monitoring | CPS architectures for environmental sensing; what "closed loop" means; examples with and without sensors | — | §4.10 |
| 2.8 Research gap | One page synthesising 2.1–2.7 into the gap JalDrishti addresses | — | §1.4 |

**Rule:** every reference in this section must be verified to exist (DOI or stable URL
opened) and to support the sentence it is attached to. No reference is added from
memory without verification. Keep a `references_verified.csv` (Appendix H) with
DOI/URL, access date, and the claim number it supports.

---

## 3. Study context and data sources

| § | Content | Evidence |
|---|---|---|
| 3.1 Problem context — the hypothetical ISR scenario | No ISR mine exists in Jharkhand; commercial ISR is not plausible in schist-hosted ore; every output is conditional; how the Texas records are used (source signature, restoration) and how they are *not* (hydrogeology) | `README.md`, `LIMITATIONS.md` §0, `texas_loader.py` |
| 3.2 Geographic / environmental context | Jharkhand hard-rock terrain; Singhbhum Shear Zone; the 3-layer hydrogeological column; regional flow (plateau divergence, Subarnarekha, Damodar); monsoon-driven water-table swing (median 2.38 m; 3.22 m wet vs 7.20 m dry statewide medians) | `flow_field.png`, `naquim_vertical.csv`, `VERTICAL_SEASONAL` |
| 3.3 Dataset sources — one table, every dataset | CGWB chemistry 2023 (397 wells, 24 districts, 20 determinands); CGWB levels 2013–2021 (9,583 readings, 398 stations); NAQUIM (21 reports + 1 profile); aquifer polygons; district/sub-district boundaries; Bhuvan lineaments (1,889); HydroRIVERS clip (4,577 reaches); GLO-30 DEM; UDEPO (9 deposits); GSI ore polygons (7); USGS Texas ISR Dataset 1 (86/9/86 rows) and Dataset 2; **NWDP multi-year chemistry if integrated (plan §6.1)** | `Datasets/`, `datasets_source.md` (local), `end_to_end_audit` pinned row counts |
| 3.4 Dataset characteristics | Descriptive statistics per determinand (min/median/max/n, share above acceptable and permissible); station map; year distribution of levels; district coverage; **charge-balance distribution (plan B4)** | new EDA script → Appendix A tables, Fig. 3.x |
| 3.5 Data quality | Missing values by column (Fe, As 0 %; U 86 %; CO₃ all zero); the 55 un-analysed-for-uranium wells and where they are; one sample per well; no well depths; spatial sparsity (1 well per ~200 km²); level records too short at 84 stations; charge-balance failures | plan §5, `data_quality.py`, B4 output |
| **3.6 The scenario, precisely** (added) | Table of every operating and transport parameter for the reference case with provenance: lixiviant reagents, C₀ envelope (9,000–41,600 ppb from n = 9 at 7 mines), Q_in, bleed, wellfield width, operation 8 yr, restoration ref 5.0 yr, horizon, β prior **(post-R17)**, Kd ranges, K(z) law, α_L relation, the 12 ungrounded parameters | `config/parameters.py`, `JHARKHAND_FIDELITY_MATRIX.md`, `/api/v1/ml/assumptions` |

---

## 4. Methodology

| § | Content | Figures / tables | Evidence |
|---|---|---|---|
| 4.1 Overall system architecture | One original diagram: data → preprocessing → engine → surrogate → risk/vulnerability → API (RBAC, RLS) → portal → alert/notification; a second diagram of the deployed topology (Neon, Render, Cloudflare Workers) | Fig. 4.1, 4.2 | `PRODUCT_DESIGN.md`, `DEPLOYMENT.md` |
| 4.2 Data preprocessing | Chemistry: parsing, "-" handling, EC→TDS factor, well/block resolution (`ST_Contains`); levels: campaign bucketing (Jan/May/Aug/Nov), per-station seasonal means; DEM+levels → head → distance-weighted plane fit → flow field (5 km grid, R² 0.73 median); lineaments → strike/dispersion field; NAQUIM → layer table; Texas → C₀ envelope and restoration residual; boundary/ore/river clips | Fig.: flow-field arrows; Table: preprocessing steps and row counts | `data_prep/*.py` |
| 4.3 Feature engineering | The 40 features grouped (hydrogeology, transport-derived, operation, species one-hots, time), each with its formula and why it exists; monotone constraints; leakage controls | Table 4.x | `feature_engineering.py`, `dataset.MONOTONE_MAPS`, `model_card.json` |
| 4.4 Hydrogeological framework | Regime (porous/fractured) by lithology; K, porosities, grain density by lithology; K(z) depth decay capped at NAQUIM fracture base; shear-zone transmissivity correction (T 207–570 m²/day, one district's data, applied to the belt); anisotropy from strike dispersion; ore-zone C₀ gating and UDEPO grade scaling | Fig.: 3-layer column; Table: parameters by lithology | `parameters.py`, `resolve.py`, `ore_grades.py` |
| 4.5 Contamination / plume simulation | Equations: Domenico plan solution with E1 leach-zone disc union; front position with retarded clock; `R_eff = 1 + β·R_m`; Tang kernel; attenuation; restoration drawdown law; disc flush; NUREG 2-of-3 excursion rule; vertical screening (three pathways, duty-cycle gradient); Monte-Carlo band. **β: the porosity-derived central value and log-uniform prior (R17), and the diagnostic that decided the clock.** Limitations of the analytical family (uniform flow, no heterogeneity, depth-integration) | Eqs. 4.1–4.n; Fig.: benchmark vs exact solution; Fig.: β sensitivity | `transport.py`, `exact_reference.py`, `domenico_error_sweep.py`, plan §4.2 |
| 4.6 Machine learning | **Why a surrogate, and what it is not** (trained on engine output; cannot exceed it; contributes calibrated bands and speed); targets (area, migration, compliance conc — log; P_ex); XGBoost quantile heads P10/P50/P90; Mondrian split-conformal by regime × species; GroupKFold(5) on scenario + leave-aquifer-out on polygon; `DELTA_INFLATE` and why; field-resampled coverage gate; hyper-parameters (fixed `COMMON`, stated); **baselines (ridge, depth-1 GBM) in the same folds (R17)**; SHAP | Table: hyper-parameters; Table: baselines vs surrogate | `train.py`, `metrics.json`, `field_coverage.py` |
| 4.7 Vulnerability / risk assessment | How outputs become categories: excursion probability; vertical band (high/moderate/low/none) and the 0.5 breach probability; citizen health band (uranium + nitrate + fluoride; `Not tested` ≠ `No data` ≠ `Low`); why source-specific vulnerability and not DRASTIC; WQI as secondary with `dominated_by` | Table: banding rules with limits and sources | `health_bands.py`, `water_quality.py`, `public_risk.py` |
| 4.8 Alert generation | The four kinds; **tiers (Notice / Warning / Alert / Critical) with the IS 10500 acceptable/permissible basis and the one project-defined multiplier (R17)**; the seven-field explanation; footprint ∩ block by `ST_Intersects`; P90 possible reach; aquifer-pathway reach bound (`v = K·i/φ`, cap 25 km); breach-due five gates; idempotence; delivery (SMTP, ledger, scheduler) | Alg. 4.1 (pseudocode); Table: tiers | `alerts.py`, `notify.py`, migration `0018/0021/0023/0025/0026` |
| 4.9 Uncertainty and data-gap analysis | Parameter uncertainty (MC + conformal) vs structural (β, §0 of the register); extrapolation flags; data-confidence; observation-based block ranking with visible weights (30/30/20/15/5, policy); suggested sites; gap matrix; charge-balance QA; **global sensitivity analysis method (R17)** | Table: weights and rationale; Alg.: sensitivity | `monitoring_gaps.py`, `data_quality.py`, `sensitivity.py` |
| 4.10 CPS architecture | Layer diagram: physical (CGWB manual network — *manual, not sensors*), data (ingest/sync, provenance), computation (engine, surrogate), decision (bands, tiers), action (alerts, delivery, acknowledgement), feedback (field observations reviewed by regulator). Explicit table: implemented / conceptual / future for each layer | Fig. 4.x | `LIMITATIONS.md` §5, `ingestion.py`, `field_observation.py` |
| 4.11 Software architecture | FastAPI + SQLAlchemy async + PostGIS; 5 roles, JWT, 21 RLS policies and the two-role database design; audit log; background tasks (no queue — stated); React/Vite/Leaflet portal (22 screens); ML adapter; deployment; test strategy (337 + 462 tests; what the test DB cannot catch — RLS) | Fig.: ER diagram (Appendix); Table: endpoint groups | `roles.md`, `DEPLOYMENT.md`, `test_rls.py` |

---

## 5. Assumptions and limitations

Structured as six tables, one per subsection, each row: *assumption → where it enters →
consequence if wrong → how the product discloses it*. Source: `LIMITATIONS.md` and
`UNGROUNDED_PARAMETERS`, reorganised — not copied.

- 5.1 Scientific: no ISR mine; porous-to-fractured transfer; analytical transport
  family; equilibrium sorption; first-order attenuation; matrix-storage ratio prior.
- 5.2 Data: one sample per well; no depths; Fe/As/Mn absent; C₀ from n = 9; NAQUIM at
  district scale; 3 districts on regional estimates; level record short at 84 stations.
- 5.3 Modelling: surrogate ≤ engine; conformal covers parameter uncertainty only; radium
  point-mass labels; OOD behaviour; fixed hyper-parameters.
- 5.4 Simulation: scenario values (§3.6); depth-integration; uniform flow per run;
  no shallow-aquifer plume after breakthrough; horizon ≤ 50 yr.
- 5.5 System / engineering: no sensors; email only; scheduler sleeps on free tier;
  test DB has no RLS policies; PDF pagination hand-checked; no frontend unit tests.
- 5.6 Generalisation: Jharkhand only; other commodities designed-for, not shown;
  results are conditional statements, never forecasts of real contamination.

---

## 6. Results

**6.0 Legend.** Each subsection is tagged **[M]** measured, **[S]** modelled scenario, or
**[V]** model-internal validation. Every figure caption repeats the tag.

| § | Tag | Content | Figures / tables | Source artefact |
|---|---|---|---|---|
| 6.1 Exploratory data analysis | M | Determinand distributions; exceedance counts against acceptable/permissible (uranium 0/342; nitrate 22; fluoride 32 — re-derive at report time); district map of health-band; charge-balance results; level-trend classes (5 declining / 20 recovering / 306 stable / 84 untestable) | Fig. 6.1–6.4; Table 6.1 | `/water-quality/*`, `/groundwater/*`, B4 output |
| 6.2 ML model performance | V | Per-target R² (raw, log), MAE in physical units, per-fold; per-species; leave-aquifer-out; conformal coverage per Mondrian cell and field-resampled; **baseline comparison**; the radium gate failure stated with its cause | Table 6.2–6.4; Fig.: calibration/coverage plot | `metrics.json` (post-R17), `ARCHITECTURE.md` §6.5 (generated) |
| 6.3 Feature importance / explainability | V | SHAP top-10 for area, migration, P_ex; agreement with physics (velocity, containment η, β, C₀) | Fig. 6.5 | `shap_top_*.json` |
| 6.4 Spatial results | S | Reference-case runs at three sites (deposit / belt / non-belt); resolved hydrogeology per site; plume extents with bands; excursion panel; river-crossing note; extrapolation flags | Fig. 6.6 (maps); Table 6.5 | stored runs, `/ml/predict` |
| 6.5 Plume simulation and **temporal evolution** | S | Jaduguda case study: frames at 2/5/10/20/50 yr; ring concentration vs time; phase boundaries; first-exceedance year; restoration effect; **before/after β table** | Fig. 6.7 (frames), Fig. 6.8 (strip chart); Table 6.6 | `plume.timeline` (R17), `LIMITATIONS.md` §1d table |
| 6.6 Vertical (2.5-D) screening | S | Breakthrough time (duty-cycle basis) and seasonal band; pathway split; per-district layer depths; the depth schematic; statement of why no 3-D volume is presented (data table from plan §4.1) | Fig. 6.9; Table 6.7 | `shallow_impact_screening`, `VerticalPanel` |
| 6.7 Vulnerability assessment | S + M | Citizen bands statewide (14/24 High concern, driven by nitrate/fluoride); `Not tested` districts; vertical band per site; excursion probability | Fig. 6.10 (public map); Table 6.8 | `/public/risk/*` |
| 6.8 Alert system | M + S | Records from the deployed database: counts by kind and tier; one full alert per basis reproduced with its seven fields; delivery ledger status; the timeline of tiers for the case study | Table 6.9; Fig. 6.11 (workflow with real records) | `alerts`, `alert_deliveries` |
| 6.9 Data gaps and uncertainty | M + V | Block ranking (top 25 with factor scores); suggested sites; gap matrix; coverage layer; **sensitivity analysis results** (which parameters control which output, per site); β sensitivity | Fig. 6.12–6.14; Table 6.10–6.11 | `/data-gaps/*`, `sensitivity.json` |
| 6.10 System / prototype | — | Screens per role (final build only); role × endpoint matrix summary; RBAC/RLS verification (62-endpoint × 6-principal sweep); audit-log sample | Fig. 6.15 (screenshots); Table 6.12 | `roles.md`, `test_authz_matrix.py` |
| 6.11 Performance / deployment | — | Engine eval time local vs Render (0.22 s vs ~4 s); lifecycle request budget; cold start; test-suite sizes and runtimes; bundle size | Table 6.13 | measured at report time |

**Rules for §6:** no result is quoted from a document — each is re-derived at report
time from the artefact named, and the number in the Source-to-Claim Register carries
the commit hash. Negative results (radium gate; alert kinds that fire on nobody; the
NWDP file if it fails the decision rule) are reported as results.

---

## 7. Discussion

Answer the five research questions in order, then:

- What the results mean for the objectives (O1 met for the ISR source under stated
  assumptions; not met for measured-quality forecasting and why; O2 met in the
  application and in this document; O3 met and deployed).
- Why the surrogate behaves as it does (SHAP vs physics; where it extrapolates).
- The parameters that matter (β first; C₀; K/T in the shear zone) and whether they
  are measured — the sensitivity results are the backbone here.
- Spatial and temporal patterns: measured (nitrate/fluoride geography, level trends)
  vs modelled (contained plumes in fractured rock; sulfate/TDS outrun uranium — the
  NUREG indicator logic reproduced independently).
- Strengths, failures, uncertainty — including the structural uncertainty no band
  covers.
- Comparison with literature (transport in crystalline rock; ISR excursion experience;
  Indian groundwater ML studies and their data).
- Implications for monitoring programmes: the concrete recommendations (test the
  Singhbhum belt for uranium; add Fe/As/Mn; repeat sampling; record well depths;
  packer/tracer test for β; deep piezometers) — this *is* deliverable D2.

---

## 8. Deliverables and Project Completion Matrix

One table (plan §12 template): each of D1–D6 and the sub-components (engine, surrogate,
vulnerability, plume, visualization, 2.5-D, alerts, data-gap analysis, backend/API,
database, dashboard, deployment, documentation) with Proposed → Implemented → Validated
→ Final status → Evidence → Remaining limitation. Status vocabulary fixed to the seven
classes used in the audit.

---

## 9. Conclusion

Five paragraphs, one per question in the brief (problem, methodology, achievement,
main contribution, major limitations). No new numbers; no adjectives from the forbidden
list; the conditional nature of every modelled result restated once.

---

## 10. Future work

Only what follows from a limitation named in §5 or a result in §6: field deployment of
monitoring at the ranked blocks; well-depth and screen records; a local tracer/packer
test for β; deep piezometry in the belt; temporal chemistry sampling (or the NWDP
record if it was not integrated); sensor integration with a real ingest contract;
zero-inflated radium head; numerical-model cross-check; SMS; other commodities via the
species registry.

---

## References

IEEE numeric. Categories to make sure are covered: transport theory (Domenico & Robbins
1985; Ogata & Banks 1961; Tang, Frind & Sudicky 1981; Neretnieks 1980; Goltz & Roberts
1986; Gelhar et al. 1992; Xu & Eckstein 1995; Freeze & Cherry 1979); ISR regulation and
experience (NUREG-1569; NUREG/CR-6733; USGS Texas ISR data releases — cite the DOI in
`Product_10.5066P9U7QKC1_METADATA.xml`); standards (IS 10500:2012 and its amendments;
WHO GDWQ); conformal prediction (Romano, Patterson & Candès 2019 CQR; Vovk et al.);
XGBoost (Chen & Guestrin 2016); SHAP (Lundberg & Lee 2017); trend tests (Theil 1950;
Sen 1968; Mann 1945; Kendall 1975); charge balance (Hem 1985; APHA); datasets (CGWB /
NWIC NWDP; NAQUIM reports by district; Bhuvan/GSI lineaments; IAEA UDEPO; Copernicus
GLO-30; HydroRIVERS — Lehner & Grill 2013); Jharkhand hydrogeology and Jaduguda
environmental studies. Every entry verified as in §2.

---

## Appendices

| App. | Content | Source |
|---|---|---|
| A | Descriptive statistics tables; charge-balance table | EDA script output |
| B | Full model metrics (`metrics.json` rendered); per-fold and per-cell tables; baselines | artefacts |
| C | API reference summary and role × endpoint matrix | `roles.md` (generated) |
| D | Database schema (ER diagram, RLS policy list) | migrations, `test_rls.py` |
| E | Scenario parameter table with provenance (long form of §3.6); `UNGROUNDED_PARAMETERS` | `parameters.py`, `/ml/assumptions` |
| F | Sample inputs/outputs: one `/ml/predict` request and response; one published advisory; one alert with fields | live system |
| G | Screenshots of every screen per role (final build, dated) | portal |
| H | **Source-to-Claim Register** and `references_verified.csv` | maintained during writing |
| I | Deployment details and environment variables (secrets redacted) | `DEPLOYMENT.md` |
| J | Sensitivity-analysis full tables | `sensitivity.json` |

---

## Integrity audit — the checklist run before delivery

Scientific: every claim in the Source-to-Claim Register resolves; assumptions in §3.6/§5
match `parameters.py` at the cited commit; limitations in §5 match `LIMITATIONS.md`;
results in §6 re-derived from artefacts at that commit. Data: every dataset in §3.3 has a
citation and a row count that matches `end_to_end_audit`. ML: targets, folds, metrics,
baseline and coverage all present; no accuracy adjective without a number. Simulation:
scenario stated before results; 2.5-D only. Software: architecture text matches the
tree; screenshots from the final build; every endpoint named exists in `roles.md`.
Research: gap established by comparison; contributions separated from cited work;
references verified; no sentence copied from any source (paraphrase check on the
literature section); figures original or attributed with permission.

The forbidden-word scan (revolutionary, groundbreaking, cutting-edge, highly accurate,
real-time as a capability, validated against reality, predicts contamination) is run
over the final text and must return zero hits outside quoted proposal language.
