---
title: "Smart Water Monitoring: Machine Learning and CPS for Safe & Sustainable Mining"
subtitle: "JalDrishti — a physics-informed groundwater contamination screening platform for hypothetical in-situ recovery (ISR) uranium mining in Jharkhand, India. Technical Research Report."
author: "Vishal Raj (Roll No. 24030480134), B.Tech Information Technology (2024–2028), B.I.T. Sindri, Dhanbad"
date: "September 2026"
lang: en-GB
toc: true
toc-depth: 3
numbersections: false
---

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Title page

| | |
|---|---|
| **Project title (as proposed)** | Smart Water Monitoring: Machine Learning and CPS for Safe & Sustainable Mining |
| **System name** | JalDrishti |
| **Student** | Vishal Raj, Roll No. 24030480134 |
| **Programme** | B.Tech, Information Technology (2024–2028) |
| **Department / Institute** | Department of Information Technology, B.I.T. Sindri, Dhanbad, Jharkhand |
| **Faculty mentor named in the proposal** | Prof. Sachin Kumar Agrawal, Assistant Professor, Department of Information Technology, B.I.T. Sindri |
| **Mentor of record in the ten monthly progress reports** | Asst. Prof. Mukesh Chandra, Department of Production & Industrial Engineering, B.I.T. Sindri |
| **Programme** | TEXMiN–BIT Sindri Mining CPS CoE, UG Call for Proposal Fellowship 2025 |
| **Academic year** | 2025–26 |
| **Fellowship period** | 1 November 2025 – August 2026 (10 months), with a post-fellowship freeze-and-report phase in September 2026 |
| **Repository** | github.com/VishalRaj720/JalDrishti (173 commits to `main` at the report commit) |
| **Deployed system** | Portal: jaldrishti.letsmailvishal111.workers.dev · API: jaldrishti-api.onrender.com |
| **Report commit** | `main` at `476a4a9` (v5 model artifacts), 21 September 2026 |

> **Note on the mentor line.** The proposal (page 1) names Prof. Sachin Kumar Agrawal as faculty mentor; all ten monthly progress reports and the consolidated report of 25 June 2026 name Asst. Prof. Mukesh Chandra. Both are recorded here because the documentary record carries both. **[To be confirmed by the student before submission.]**

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Declaration

I, Vishal Raj, admission number 24030480134, enrolled in the B.Tech (Information Technology) programme at B.I.T. Sindri, Dhanbad, declare that the work described in this report, entitled *Smart Water Monitoring: Machine Learning and CPS for Safe & Sustainable Mining* (system name *JalDrishti*), was carried out by me under the guidance of my faculty mentor during the TEXMiN–BIT Sindri UG Fellowship 2025–26.

All sources of data, published methods and prior work used in this project are acknowledged in the text and in the reference list. Numerical results reported here were regenerated from the repository at the commit named on the title page, and every quantitative claim is traceable to a file, a test, a dataset row count or a citation in the Source-to-Claim Register (Appendix H).

AI-assisted software tooling (Claude, Anthropic) was used throughout the project for software development, code review, documentation and drafting, under my direction and review; the design decisions, the datasets chosen, the scientific assumptions adopted and the interpretation of results are my responsibility. This is stated plainly because it is true and because the project's own working rule was that anything weaker than it looks must be written down rather than left for a reader to discover.

The proposal carried a TEXMiN CoE declaration on intellectual property and confidentiality (proposal page 6). Where the final report requires that institutional wording, it is to be attached in the institutional form; this declaration does not replace it.

No part of this work has been submitted elsewhere for any degree or award.

Signature: ______________________  Date: ______________

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Acknowledgement

I thank my faculty mentor for guidance throughout the fellowship, and in particular for the advice in April 2026 to look for internationally published ISR operating records when no Indian ISR data could exist — the decision from which the final methodology descends.

I thank the TEXMiN–BIT Sindri Mining CPS Centre of Excellence and B.I.T. Sindri for the fellowship and for the review panel in August 2026.

This project rests entirely on open data published by others: the Central Ground Water Board (CGWB) and the National Water Informatics Centre (National Water Data Portal), for the 2023 groundwater-chemistry yearbook table, the 2013–2021 water-level record, the 2000–2021 chemistry record and the district NAQUIM reports; the Geological Survey of India and NRSC Bhuvan for the lineament map; the International Atomic Energy Agency for the UDEPO deposit database; the U.S. Geological Survey for the two Texas ISR data releases; the European Space Agency / Copernicus programme for the GLO-30 digital elevation model; and Lehner & Grill for HydroRIVERS. The published Jaduguda studies by the Bhabha Atomic Research Centre and the Indian School of Mines provided the only local measurements of mine-water uranium and radium.

The software stands on FastAPI, SQLAlchemy, PostgreSQL/PostGIS, XGBoost, scikit-learn, NumPy/SciPy, pandas/GeoPandas, React, Vite, Leaflet and TanStack Query, and is hosted on Neon, Render and Cloudflare Workers.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Abstract

Groundwater is the primary drinking-water supply across Jharkhand's hard-rock terrain, and the Singhbhum Shear Zone in its south-east is India's uranium province. In-situ recovery (ISR) uranium mining — injecting an oxidising, carbonate-bearing lixiviant into an ore-bearing aquifer — mobilises uranium, sulphate, dissolved solids and radium, and the regulatory experience of ISR in the United States shows that excursions past the wellfield are detected by manual sampling against control limits, after the fact. No ISR mine operates in Jharkhand and commercial ISR is not plausible in schist-hosted ore; this project is therefore a **preparedness screening study**: *if ISR-strength lixiviant entered a Jharkhand aquifer, how far and how fast would contamination move, would it reach the shallow drinking-water aquifer, who should be told, and what should be monitored — and which of those questions can the available data actually answer?*

The delivered system, JalDrishti, couples (i) an analytical contaminant-transport engine — the Domenico/Ogata–Banks plan-view solution with a leach-zone disc, Goltz–Roberts dual-porosity retardation scaled by matrix sorption, a Tang matrix-diffusion envelope, a restoration draw-down law anchored to Texas operating records, first-order uranium attenuation and a NUREG-1569-style 2-of-3 indicator excursion test — with (ii) an XGBoost quantile surrogate trained on 18,000 engine-labelled scenarios placed on real Jharkhand aquifer polygons, calibrated by Mondrian split-conformal prediction, and validated by grouped and leave-aquifer-out cross-validation and by a field-resampled coverage gate; (iii) an IS 10500:2012 assessment of the 397-well CGWB measured record with a tiered alert loop delivered by email; (iv) an observation-based monitoring-gap ranking of all 264 blocks; and (v) a five-role government portal with database-enforced row-level security, deployed on managed hosting.

Principal results: the surrogate reproduces the engine with R²(log) of 0.893 (footprint area), 0.926 (migration distance) and 0.947 (ring concentration) under scenario-grouped cross-validation, beats ridge and stump baselines on every target, and holds 80 % conformal coverage on the serving distribution (0.875–0.885 scenario coverage); it misses the project's own R²(log) ≥ 0.60 gate on two radium cells (0.500, 0.235) because those labels are point masses, and this is reported rather than moved. On the measured record, uranium exceeds its limit at none of 342 tested wells while nitrate exceeds at 22 and fluoride at 32 (11 above the permissible limit); arsenic, iron and manganese have never been analysed anywhere in the record; the three Singhbhum districts have no uranium result at all. At the Jaduguda reference site the modelled 20-year uranium extent is 20.5 m (band 2.7–100 m) while sulphate reaches 73 m and TDS 254 m — the ordering that makes conservative indicators, not uranium, the excursion signal. A global sensitivity analysis shows hydraulic conductivity and the dual-porosity capacity ratio β carry most of the extent's variance; β is derived from the run's own porosities but is not measured anywhere in the Singhbhum belt.

The principal limitation is structural: no field validation of any modelled plume is possible, and the conformal bands quantify parameter uncertainty inside the model's assumptions, not model error. The system is "CPS-ready decision support" over a manual monitoring network, not a live sensing loop.

**Keywords:** groundwater vulnerability; in-situ recovery (ISR) uranium mining; contaminant transport surrogate; conformal prediction; monitoring network design; decision-support system; Jharkhand; IS 10500.

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# Conventions used in this report

- **Result tags.** Every results subsection and figure caption in §6 carries one of three tags: **[M]** a *measured* quantity (a laboratory value, a station reading); **[S]** a *modelled scenario* result (conditional on the hypothetical ISR operation of §3.6); **[V]** a *model-internal validation* (the surrogate against the engine, the engine against an exact solution). No result in this report is a prediction of real contamination in Jharkhand.
- **Provenance.** Numbers are quoted from artefacts at commit `476a4a9` unless a section says otherwise; the artefact for each is listed in Appendix H. Where a number was produced earlier in the project and the artefact has since changed, the earlier value is given with its date.
- **Citations** are IEEE-numeric, in square brackets, to the reference list. Repository files are cited by path in backticks; the chronological review record kept outside version control is cited as `docs/local/audit-record/<file>`.
- **Version labels.** The surrogate artifacts are versioned by model card: v3 (11 Aug 2026), v4 (20 Sep 2026, the β retrain), v5 (21 Sep 2026, the background-floor retrain — the version reported here). "R10–R17" denote the numbered review-and-remediation passes of August–September 2026, as used throughout the repository's documentation.
- **What is not claimed.** The words *real-time*, *validated against reality*, *accurate* and *predicts contamination* are avoided deliberately; §5 and §7 explain why each would overstate the work.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 1. Introduction

## 1.1 Background

Jharkhand is a hard-rock state. Outside the Damodar valley coalfields and the alluvial fringes, groundwater is stored and transmitted in a thin weathered mantle and in the fractured crystalline rock beneath it — Precambrian gneisses, schists, granites and quartzites of the Chotanagpur plateau and the Singhbhum craton. The Central Ground Water Board's aquifer-mapping (NAQUIM) reports for the state's districts describe a three-layer column: a weathered zone typically 13–30 m deep, a productive fractured zone that dies out somewhere between about 90 and 260 m depending on the district, and massive rock below [37]–[39]. Drinking water is drawn from the first of these layers by hand pumps and dug wells; irrigation and small-town supply reach into the second. The water table in this column swings by several metres between the pre-monsoon and post-monsoon campaigns — the statewide campaign medians in the CGWB record used here are 7.20 m below ground in May and 3.22 m in August [40].

The Singhbhum Shear Zone of East Singhbhum district hosts India's oldest uranium mines — Jaduguda, Bhatin, Narwapahar, Turamdih, Banduhurang, Mohuldih and Bagjata — all of them conventional underground or open-pit operations run by the Uranium Corporation of India Ltd. The ore is uraninite in quartz–chlorite–biotite schists with abundant sulphides (chalcopyrite, pyrite, pyrrhotite); it is simultaneously a copper belt. None of these mines is an ISR operation, and this distinction is the premise of everything that follows.

In-situ recovery (ISR, also "in-situ leach") is the technique that now produces the majority of the world's uranium. Instead of excavating ore, an operator drills injection and recovery wells into a permeable, confined, sandstone-hosted ore body, injects a *lixiviant* — in the alkaline variant, native groundwater fortified with an oxidant and carbonate/bicarbonate — that dissolves uranium as uranyl-carbonate complexes, and pumps the pregnant solution back to the surface. A deliberate net over-extraction (the *bleed*, typically 0.5–3 % of injection) pulls groundwater inward and hydraulically contains the wellfield. Lixiviant that escapes past the ring of monitor wells is an *excursion*; after mining the aquifer must be *restored* by groundwater sweep, reverse osmosis and sometimes chemical reductants, and then monitored for stability [12], [13]. ISR mobilises not only uranium but sulphate, total dissolved solids, radium-226 and, depending on the ore, arsenic, selenium and molybdenum [15], [17].

The regulatory record of ISR in the United States — the Nuclear Regulatory Commission's standard review plan NUREG-1569 [12], its risk-informed baseline NUREG/CR-6733 [13], and the USGS compilation of historic Texas ISR groundwater quality [15]–[17] — is explicit that excursions are detected after the fact by manual sampling of monitor wells against upper control limits on conservative indicator species (chloride, conductivity, total alkalinity), and that uranium itself is rejected as an indicator because it is retarded by reducing conditions in the aquifer [12, §5.7.8.3]. That regulatory logic is reproduced independently by the transport model built here (§6.5) and it shaped the excursion criterion the system uses.

## 1.2 Problem statement

The question this project set out to answer, once the constraints of the data were understood, is conditional:

> *If ISR-strength lixiviant entered a Jharkhand aquifer at a given point, how far and how fast would contamination move; would it reach the shallow drinking-water aquifer; which administrative blocks and which residents should be told; and what should be monitored, where — and which of these questions can the data that exist for Jharkhand actually support?*

The last clause is not a hedge; it is the second of the project's three objectives (§1.5), and the answers to it — where the monitoring record is silent, which physical parameters are unmeasured, and which claims the data cannot bear — occupy as much of this report as the model does.

## 1.3 Motivation

The proposal's motivation (proposal §7–§8) was that conventional groundwater monitoring in mining regions "depends on manual sampling, lab analysis, and threshold-based decision-making, which tend to be reactive rather than predictive". That description was confirmed, rather than merely assumed, by the measured record obtained for Jharkhand: the CGWB groundwater-chemistry yearbook table for 2023 holds 397 wells across 24 districts with **one sample per well, in one year, with no repeats**, and no well depth recorded [40]; the only genuinely temporal data available for the state are quarterly water-level readings (9,583 readings at 398 stations, 2013–2021) [41]. A predictive system in the proposal's sense — one that forecasts a degradation trend from a chemistry time series — was not buildable on that record, and this report says so in §5 and §7.

What *is* buildable, and what the project delivers, is a **screening tool that says what to look for and where**: a transport model grounded in real Jharkhand hydrogeology that turns a hypothetical source into a footprint, a monitoring-ring concentration, an excursion probability and a shallow-aquifer breakthrough time; an assessment of the existing measured record against the Indian drinking-water standard that turns 397 laboratory analyses into block-level bands and tiered alerts delivered to the residents concerned; and a ranking of every block by how poorly it is observed, so that the next sampling round goes where the record is blind rather than where the model is already confident.

## 1.4 Research and technology gap

Four gaps, each substantiated in §2 or found during the project:

1. **No ISR-specific screening tool exists for Indian hard-rock hydrogeology.** The ISR screening literature and every commercial ISR operation on Earth concern unconsolidated or weakly consolidated sandstone aquifers [12], [15]–[17]. Transferring that experience to a fractured metamorphic shear zone requires a stated model of fractured-rock transport — dual porosity, matrix diffusion, fracture-fabric anisotropy — and a statement of which of its parameters are measured locally (§4.4–§4.5, §5.1).
2. **The Indian groundwater-ML literature depends on data that does not exist here.** The random-forest, SVM, gradient-boosting and neural-network studies of groundwater quality in India that the proposal cited as method (§2.2) use multi-station, multi-year records. The Jharkhand record has one sample per well. The gap is not in the algorithms; it is in what they would be trained on.
3. **Monitoring data is collected and not read.** The record contains twenty determinands at 99–100 % coverage; until this project's R13 pass (August 2026) only one of them, uranium, drove any logic in the system — and uranium exceeds its limit at zero wells while nitrate and fluoride exceed at 22 and 32. This was a finding about the project's own earlier design, and it generalises: a threshold that never fires is indistinguishable from a threshold that has nothing to fire on (§4.8, §6.1).
4. **Alerts that reach nobody.** A notification that exists only as a database row, visible to a resident who has signed in, opened a bell and previously followed the right block, is not a notification. Closing the threshold → alert → delivery → acknowledgement loop on a manual record turned out to require four separate fixes, three of them to controls that were present, configured and inert (§4.8, §6.8).

## 1.5 Objectives and deliverables

The proposal's three objectives are reproduced verbatim (proposal §6):

- **O1.** Develop ML-based predictive models to assess water quality degradation and aquifer vulnerability in mining-affected ISR regions.
- **O2.** Identify key data gaps in hydrogeological systems and recommend improved monitoring strategies.
- **O3.** Design a prototype tool that integrates prediction, visualization, and decision-support features for stakeholders.

and its six deliverables (proposal §12):

- **D1.** ML-based predictive models to forecast groundwater quality trends and assess aquifer vulnerability near uranium ISR sites.
- **D2.** Identification of critical data gaps in hydrogeological and chemical monitoring, along with recommendations to improve existing frameworks.
- **D3.** Prototype decision-support tool featuring a user-friendly interface for stakeholders to input data and receive vulnerability assessments and alerts.
- **D4.** Visualization dashboard for real-time monitoring and intuitive interpretation of water quality indicators.
- **D5.** Scalable framework adaptable to other mining contexts, including coal, rare earth, and heavy metal contamination.
- **D6.** Contribution to Mine Safety using AI/ML and CPS Technologies.

The proposal's methodology diagram (proposal §11) prescribed problem scoping → data collection and preprocessing → feature engineering → model development (classification: Random Forest, SVM; regression: Gradient Boosting, ANN) → cross-validation → evaluation → **sensitivity analysis** → **data-gap analysis** → prototype (front end, ML integration, dashboard, *simulate case study*) → testing. Its proposed inputs (proposal §7) were pH, temperature, EC, TDS, turbidity, sulphate, nitrate, chloride, hardness, Fe, Mn, As, groundwater-level fluctuation, distance to mining sites and seasonal rainfall. Section 8 judges the delivered system against these lists, item by item; §7 explains where the delivered methodology departs from the proposed one and why.

## 1.6 Research questions

- **RQ1.** Can a physics-informed surrogate reproduce an analytical contaminant-transport engine across Jharkhand's hydrogeology with calibrated uncertainty, and what does its accuracy mean?
- **RQ2.** Which physical parameters control the modelled plume extent, and are they measured locally?
- **RQ3.** What does the measured CGWB record say about current water quality against IS 10500:2012 — and what does it not say?
- **RQ4.** Where are the monitoring gaps, and how should a monitoring network be prioritised?
- **RQ5.** Can a threshold → alert → notification loop be closed on the existing manual record, and what does closing it require?

Each is answered in §7.

## 1.7 Contributions

The following were built in this project. They are separated deliberately from the prior work they rest on — the Domenico, Ogata–Banks, Tang–Frind–Sudicky and Goltz–Roberts solutions, conformalised quantile regression, NUREG-1569 — which is cited, not claimed.

1. **An analytical ISR transport engine adapted to fractured Indian hard rock**: the E1 leach-zone geometry, the sorption-scaled dual-porosity capacity ratio (`R_eff = 1 + β·R_m`) with β derived from resolved porosities, a causal restoration draw-down law anchored to paired Texas per-mine residuals, a first-order uranium attenuation term graded by ore-zone mineralogy, a depth-decay conductivity law calibrated per district from NAQUIM fracture-depth evidence, and a 2.5-D vertical screening with a duty-cycle seasonal gradient — all resolved statewide from real Jharkhand fields (aquifer polygons, a station-fitted flow field, a lineament strike field, NAQUIM layers, UDEPO grades, HydroRIVERS receptors).
2. **A physics-informed surrogate with a statistical coverage guarantee**: XGBoost P10/P50/P90 heads with physics-derived monotone constraints, Mondrian split-conformal calibration per regime × species, scenario-grouped and leave-aquifer-out validation, a field-resampled coverage gate on the serving distribution, and reported baselines.
3. **A measured-record assessment and a citizen banding rule** on IS 10500's own limit structure, in which "not tested" is a band of its own and never green.
4. **A closed alert loop on a manual record**: five alert kinds, four tiers, a seven-field explanation on every record, email delivery with an idempotent ledger and retry, and a database CHECK that a modelled result can never be "critical".
5. **An observation-based monitoring-network ranking** of all 264 blocks with visible policy weights, a gap matrix and suggested well sites, plus a sample-level hydrochemical QA that exposed the 2023 file's charge balance as a consistency of construction.
6. **A machine-readable assumption register** (`UNGROUNDED_PARAMETERS`, served at `/api/v1/ml/assumptions`), a per-parameter fidelity matrix, a global sensitivity analysis over the registered constants, and a limitations register kept current to the last commit.
7. **A deployed five-role portal** with database-enforced row-level security, an immutable audit log, an advisory publication workflow and 22 screens, verified by 373 engine tests and 522 backend tests.

## 1.8 How the work evolved over ten months

The report reconstructs what was done rather than an idealised version, and the most important thing to say about the project is that its methodology changed substantially twice. The first five months built a data platform and a series of tabular ML models on measured and synthetic chemistry (the proposal's method); the sixth month's attempt to make those models draw a plume showed that they could not, for a structural reason, and the prediction core was rebuilt as a physics engine with a surrogate; the last three months turned that engine into a product and then subjected the whole system to seven numbered review passes that found — and fixed — defects the tests could not see. Table 1.1 gives the chronology; §3–§4 describe the final methodology; §7 returns to why the changes were necessary.

**Table 1.1 — Project chronology, from the ten monthly progress reports (MPRs) and the commit history (173 commits, 26 Dec 2025 – 21 Sep 2026).**

| Month | Theme | What was actually done | Evidence |
|---|---|---|---|
| Nov 2025 | Foundation | Literature review on monitoring-network design, aquifer vulnerability and ISR contamination pathways. Local stack set up: Node.js backend, PostgreSQL, Redis, Docker; microservices architecture designed; React + TypeScript admin front end with JWT login and three roles (admin / analyst / viewer). | MPR Nov 2025 |
| Dec 2025 | Backend migration | Backend migrated from Node.js to **FastAPI** (API / service / repository layers); PostgreSQL + **PostGIS** schema with 13 tables; SQLAlchemy models, Alembic migrations, JWT, RBAC; CRUD APIs for users, districts, blocks, aquifers; a simulation workflow skeleton with a placeholder ML output. | MPR Dec 2025; first repository commit 26 Dec 2025 |
| Jan 2026 | Real CGWB data | CGWB datasets studied; Dhanbad groundwater-level data loaded; aquifer model extended with transmissivity, hydraulic conductivity, fracture and yield fields; ISR-points CRUD API; ingestion API for GeoJSON and CGWB Excel; React Query + Leaflet map of districts and aquifers. | MPR Jan 2026 |
| Feb 2026 | Data layer | Migration `0004` (six tables incl. `monitoring_wells`, `water_samples` with provenance columns); five ingestion pipelines with SHA-256 idempotency and range-string parsing; idempotent seed with a data-quality report; 11 REST endpoints; **first data-gap finding**: Fe and As 100 % null in the chemistry file. Counts: 25 districts, 275 blocks, 24 aquifer polygons, 397 wells / 397 samples. | MPR Feb 2026; commit `ac8725c` |
| Mar 2026 | ML approach 1a | 16-feature schema extracted by a PostGIS LATERAL join; a **Gaussian-copula synthetic generator** (NumPy/SciPy) to balance classes; RF/Ridge **TDS regressor** and RF/logistic **contamination classifier** with 5-fold CV; SHAP; an `MLPredictionService` replacing the random stub with a three-level fallback. | MPR Mar 2026; commit `3ccf59c` |
| Apr 2026 | ML approach 1b | Mentor's advice to use international ISR data. The **USGS Texas ISR dataset** selected [15], [16]; 186 usable rows parsed (detection-limit and "±" strings handled); 5,186-row synthetic set with exponential distance decay and seasonal factors; **rule-scored risk labels**; Random Forest at 91.1 % accuracy / 0.90 macro-F1. | MPR Apr 2026; commit `0ec5d5c` |
| May 2026 | ML approach 1c | Unified pipeline with **uranium as the regression target** (previously dropped): 342 Jharkhand real + 131 Texas real + 3,000 synthetic rows; five models (U, TDS, SO₄, pH regressors; safe/marginal/unsafe classifier); real-only U R²(log) 0.69; backend slimmed (Celery/Redis/Flower removed); two-command database setup. | MPR May 2026; commit `0693b20` |
| Jun 2026 | **The turning point** | Audit of approach 1: in its training data distance-from-mine was random and time never entered the label; the real validation rows had neither. **Rebuild** as a 2-D analytical transport engine (Domenico + Tang + dual porosity + containment + three-phase timeline) with a physics-labelled 13,500-row training set and a monotone-constrained, conformally calibrated XGBoost surrogate; grounding in real Jharkhand fields (flow field, lineaments, NAQUIM, UDEPO, shear-zone transmissivity, rivers); interactive dashboard; ~1,100-case QA sweep at nine pins, four defects fixed. | MPR Jun 2026; commits `6a85293`–`5ad73ff`; `docs/local/comparison.md` |
| Jul 2026 | Reviews and backend rebuild | Fidelity fixes (depth-decay K, attenuation by ore zone, seam blending, **radium-226** as a fourth species → 18,000 rows); **three independent review rounds** (findings #1–#9, V-1–V-8, D-1–D-7) each closed or refuted with evidence; exact-solution benchmark; full Ogata–Banks term restored; migration R² 0.719 → 0.896 across four retrains; backend rebuilt on the real engine (P0–P4): the placeholder simulation engine deleted, a signup privilege-escalation hole closed, **five roles + Postgres row-level security**, field-observation workflow, transposed geometry fixed; React/TypeScript portal. | MPR Jul 2026; PR #6 |
| Aug 2026 | Product and deployment (R10–R15) | Console, publication workflow, resident surface, PDF report, comparison, dataset manager, monitoring-network plan; **IS 10500 assessment** of the 19 unread determinands; Theil–Sen/Mann–Kendall level trends; three **inert security controls** found and wired; deployment audit NO-GO on five conditions, all closed; deployed on Neon + Render + Cloudflare; the **β plume-extent finding** recorded as open; final presentation to the TEXMiN–BIT Sindri panel. | MPR Aug 2026; PRs #7–#9 |
| Sep 2026 | R16, R17 and freeze | R16: the alert loop closed (home block at registration, SMTP delivery, scheduler, front page). R17: pre-report audit; **β derived from porosities and the v4 retrain**; alert tiers with a seven-field record; timeline frames; hydrochemical QA; global sensitivity analysis; the CGWB 2000–2021 record; documentation sync and **project freeze**. Post-freeze fixes: two chart mis-statements, a background floor on the source term with the **v5 retrain**, and an alert-delivery retry defect found while configuring email on the deployed system. | commits `77b721b`–`476a4a9`; `docs/PROJECT_FREEZE.md` |

Three features of this chronology matter for reading the rest of the report. First, the first git commit is dated 26 December 2025, so the November work is documented only in the first MPR. Second, the machine-learning work of March–May 2026 (three successive tabular pipelines) was superseded, not refined: its data files were kept, its models and synthetic generators were deleted from the repository in July (`6a85293`), and §7.2 explains why the reported R² of 0.69 did not validate what it appeared to validate. Third, from July onward the project's method of working was audit-driven: every review pass produced a written finding list, every finding was either fixed with a pinned test or refuted with evidence, and the record of retracted findings was kept because the retraction is itself information (`docs/local/audit-record/README.md`).

## 1.9 Structure of this report

§2 reviews the literature by comparison and ends each subsection with what the reviewed work does not provide for this problem. §3 states the study context, every dataset with its provenance and row count, the data-quality findings, and — in §3.6 — the hypothetical scenario precisely. §4 is the methodology, ordered physics-first: architecture, preprocessing, features, the hydrogeological framework, the plume engine, the surrogate, vulnerability, alerts, uncertainty and data gaps, the CPS architecture, and the software. §5 tabulates assumptions and limitations. §6 reports results with the [M]/[S]/[V] tags. §7 discusses the research questions. §8 is the Project Completion Matrix. §9 concludes; §10 lists future work. The appendices carry the descriptive statistics, the full model metrics, the API and schema summaries, the scenario and assumption registers, sample records, the Source-to-Claim Register, deployment details and the sensitivity tables.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 2. Literature review

The review is organised by the seven bodies of work the project had to draw on, and each subsection ends with one sentence on what that body of work does *not* provide for this problem. The synthesis in §2.8 is the research gap. The first month's reading (MPR Nov 2025) covered monitoring-network design guidance and ISR contamination mechanisms; the ISR regulatory and Texas literature entered in April 2026; the transport-theory, conformal-prediction and Jaduguda literature entered with the June rebuild; and the sensitivity-analysis and hydrochemical-QA references entered with R17 in September 2026.

## 2.1 Groundwater quality assessment: indices versus limits

Two traditions assess groundwater quality. The **index tradition** collapses many determinands into one number: the water quality index (WQI) of Brown et al. [56] and its descendants weight each parameter by a relative weight, most often the inverse of its permissible limit, and sum the weighted sub-indices. The construction is convenient and is widely used for Indian groundwater [57], but it has a property that misleads: because the weight is 1/limit, the determinand with the smallest limit dominates the score regardless of whether it is the determinand of concern. The project found this on a real well before it found it in the formula — Dasokhap (Hazaribagh) scores "unsuitable for drinking" on a fluoride reading of 1.43 mg/L that is *below* its own permissible limit of 1.5 mg/L, because fluoride carries 96 % of the score (`docs/LIMITATIONS.md` §4d). The **limit tradition** compares each determinand with a published standard and reports the class. In India the standard is IS 10500:2012 [25], which defines for each determinand an *acceptable* limit and a *permissible limit in the absence of an alternate source*, with "no relaxation" for nitrate, uranium (via the 2015/2021 amendments) and some others; the WHO guideline value of 30 µg/L for uranium [26] is the provisional health-based value the Indian standard aligns with. CGWB's own assessment practice is limit-based, district by district, in its groundwater year books [39].

The project reports the limit-based assessment first and the composite index second, with the dominant term shown beside every score (§4.7). *What neither tradition provides is a rule for what to say about a well that was never analysed for a determinand — the index treats a missing value as zero and the limit comparison treats it as absent — and the project had to define "not tested" as a class of its own.*

## 2.2 Machine learning for water-quality prediction

The proposal's method (§1.5) named Random Forests, SVMs, gradient boosting and ANNs, and this is the mainstream of the groundwater-ML literature: models trained on multi-station, multi-year records to predict a level or a concentration from hydrogeological and climatic covariates. Sahoo & Jha [58] compared multiple linear regression and ANNs for groundwater-level prediction on such records; Rajaee et al. [59] review the AI methods used for level modelling and the data they need — long, regularly sampled series at many stations. Applied to chemistry, the same families predict a concentration at a well from co-measured determinands, or classify samples into suitability classes.

Three properties of that literature decided the project's course. First, its data requirements: the Jharkhand chemistry record has one sample per well (§3.5), so there is no time axis to learn a trend from, and the March–May 2026 pipelines could only learn cross-sectional relationships between co-measured determinands (§7.2). Second, the target: a concentration measured at a well tells nothing about a plume that does not exist, so a model of measured chemistry cannot answer the ISR question. Third, a body of work the proposal did not name — **surrogate modelling of physics codes**, in which a fast learner is trained to emulate a slow or repeatedly evaluated simulator, and **conformal prediction** [27], [28], which wraps any point predictor in prediction intervals with a finite-sample coverage guarantee under exchangeability. Conformalised quantile regression (CQR) [27] combines a quantile regressor with a split-conformal correction so that the widened interval covers at least 1 − α of new points from the same distribution regardless of how wrong the underlying model is; Mondrian (group-conditional) conformal prediction [28] applies the correction per category so that one group's errors do not borrow another's. Gradient-boosted trees [29] provide the quantile heads (pinball loss) and accept monotone constraints, which is how physical law is injected into a learner that otherwise knows nothing of physics; SHAP values [30] attribute a prediction to its features for explanation.

*The Indian groundwater-ML literature does not provide a method for a record with one sample per well and no plume to learn from; the surrogate-modelling and conformal literature provides the method the project used, but with a guarantee that holds for the emulated model's parameter uncertainty, not for structural error against reality.*

## 2.3 Aquifer vulnerability: intrinsic versus specific

**Intrinsic** vulnerability indices — DRASTIC [53], GOD [54], SINTACS [55] — rate an aquifer's susceptibility to any contaminant from the surface using layers such as depth to water, net recharge, aquifer medium, soil, topography, vadose-zone impact and hydraulic conductivity, weighted and summed. They are source-agnostic and require a soil map, a recharge estimate and a vadose-zone characterisation. **Specific** (or process-based) vulnerability instead asks how a *named* source in a *named* setting reaches a *named* receptor, and is answered by transport modelling rather than by a layered index.

The project deliberately did not build a DRASTIC-type index (`docs/PRE_REPORT_AUDIT_AND_PLAN.md` §3 D-list). The reasons were data and question: three of DRASTIC's seven layers (soil, recharge, vadose zone) would have been invented for Jharkhand rather than measured; and the question is not "is this aquifer susceptible to surface pollution" but "would an injected lixiviant at ore depth reach the shallow drinking-water aquifer" — a source-specific, vertical question that the 2.5-D screening of §4.5 addresses with the layers that *do* exist (the NAQUIM column, the measured water table and its seasonal swing). *The intrinsic-vulnerability literature does not provide a way to ask about a deep injected source, and it needs layers that do not exist at usable resolution for the state.*

## 2.4 Contamination and plume modelling

The analytical family used here is the standard screening toolkit. The one-dimensional advection–dispersion step response is Ogata & Banks [4]; Domenico & Robbins [3] and Domenico [2] extended it to a finite-width source in two and three dimensions by a product of longitudinal and transverse factors, the approximation on which the BIOSCREEN class of screening tools is built [60]. The approximation's error was quantified by West, Kueper & Ungs [10], who showed it can reach tens of per cent when transverse spreading is large relative to the source width — a result that the second review round cited as a threat and the project's exact-solution benchmark showed does not apply in its parameter box (§6.2). Dispersivity is scale-dependent: Gelhar, Welty & Rehfeldt [8] reviewed the field record and Xu & Eckstein [9] fitted the regression `α_L = 0.83 (log₁₀ L)^2.414` used here; Gelhar et al. also give the transverse-to-longitudinal ratios the project uses per regime.

Fractured rock is different. Neretnieks [6] argued that diffusion from fractures into the rock matrix is the dominant retardation mechanism for radionuclides in crystalline rock; Tang, Frind & Sudicky [5] solved transport in a single fracture with matrix diffusion, giving the attenuation kernel the engine uses as an early-arrival envelope; Goltz & Roberts [7] gave the mobile/immobile (dual-porosity) formulation whose late-time apparent retardation is `1 + β` for a conservative tracer and, scaled by matrix sorption, `1 + β·R_m` for a sorbing one. Manning & Ingebritsen [11] give the global crust-scale decline of permeability with depth against which the project bounded its per-district depth-decay law. Sorption itself enters through distribution coefficients: the EPA compendia [46], [47] and the Thibault et al. soil compilation [48], [49] supplied the ranges, with the important caveat, documented in `config/parameters.py`, that uranium's Kd under alkaline carbonate chemistry is low because uranyl-carbonate complexes barely sorb — which is the reason alkaline ISR works.

The ISR-specific literature supplies the source term, the restoration behaviour and the excursion criterion. NUREG-1569 [12] specifies the excursion-monitoring programme (monitor wells at 75–180 m from the wellfield edge, at least three indicator parameters, an excursion declared when two or more exceed their upper control limits) and explicitly rejects uranium as an indicator; NUREG/CR-6733 [13] and NUREG/CR-6870 [14] treat the risk basis and the geochemistry of restoration. The USGS Texas compilations [15]–[17] are the only public records of baseline, end-of-mining and post-restoration groundwater chemistry across many ISR production areas; Reimus et al. [18] measured, in a cross-hole field test at a Wyoming ISR site, that about half of injected U(VI) was reduced to U(IV) within a year where reducing capacity was intact — the calibration point for the project's attenuation rate; Gallegos et al. [19] documented persistent U(IV)/U(VI) and post-restoration rebound at the same site, the evidence behind the project's refusal to let a restored source decay below the measured Texas endpoint; and the EPA's restoration synthesis [20] gives the ≥ 30-year post-restoration monitoring horizon that anchors the source-flush half-life. Newell et al. [21] distinguish the concentration-versus-distance and concentration-versus-time first-order rate constants that the engine's attenuation term applies.

*This literature does not provide a transport model for a fractured shear zone with measured parameters — every fractured-rock coefficient in the engine is a foreign crystalline-rock analogue — nor any measured ISR plume outside sandstone, which is why the engine can be benchmarked but never validated.*

## 2.5 Spatial and hydrogeological modelling for the state

The flow field a plume rides on is, in textbook practice, estimated from hydraulic heads at three or more wells by a plane fit [1]; the project generalises that to a distance-weighted plane fit on a 5 km grid from 398 CGWB stations, with head taken as elevation minus depth-to-water and a smoothed-DEM fallback where stations are sparse — the "water table as a subdued replica of topography" assumption that is standard for hard-rock terrain. Fracture fabric is mapped by the Geological Survey of India's lineament programme [42]; axial (doubled-angle) circular statistics are the standard way to average undirected orientations, and the circular variance measures alignment. The vertical structure comes from CGWB's NAQUIM aquifer-mapping reports [37], [38], which for each district give the weathered-zone base, the depth range of productive fractures and the confined or semi-confined state of the deeper aquifer. Aquifer properties at the polygon scale are CGWB's; where a polygon carries no value the project fills from Freeze & Cherry's lithology-typical ranges [1], flagged as literature. The global permeability–porosity map GLHYMPS [62] was catalogued in the dataset survey but not used, because the CGWB polygons are finer and local.

*What the state-scale hydrogeological literature does not provide is any property at ore depth: every CGWB value characterises the drinking-water aquifer in the upper tens of metres, and no deep piezometry, packer test or tracer test for the Singhbhum Shear Zone has been published.*

## 2.6 Monitoring systems and network design

CGWB's network-design practice is coverage-based — stations per unit area and distance to the nearest observation — and the first month's reading of monitoring-network design guidance (MPR Nov 2025) confirmed that the classical objectives are spatial coverage, temporal frequency and representativeness. ISR-specific monitoring is prescriptive: NUREG-1569 [12] fixes the ring distance, the indicator panel, the sampling interval and the statistical form of the control limit (a simple percentage over baseline is permitted; the preferred rules — mean plus five standard deviations, or ASTM D6312 [61] — require a per-well temporal baseline). Optimal-network design in the research literature sets siting as an optimisation of an information objective, typically variance reduction of a kriged field or of a model's prediction.

The project's ranking (§4.9) is deliberately *observation-based* rather than *risk-based*: a block is prioritised by how badly it is observed — never sampled, sampled but not analysed for uranium, thin coverage, far from a uranium-tested well — with proximity to a hypothetical site given the smallest weight. *The network-design literature does not provide an objective for a setting in which the model is least trustworthy exactly where there is no data; ranking by predicted risk would send crews to the places the model is already confident about, so the project's weights are a stated policy rather than a derived optimum.*

## 2.7 Cyber-physical systems for environmental monitoring

A cyber-physical system (CPS) in the environmental-monitoring sense couples a physical layer (sensors, telemetry), a data layer (ingest, storage, provenance), a computation layer (models), a decision layer (thresholds, classifications) and an action layer (alerts, control), with feedback. The proposal's CPS genesis (proposal §10) described "environmental sensors, real-time data streams and machine learning algorithms in a unified monitoring framework … a closed-loop system." The literature distinguishes systems with a sensing layer from decision-support systems that consume a manual record; what makes a loop "closed" is that a threshold crossing produces a delivered notification and an acknowledged action, whether or not the sensing is automatic.

The project's honest position, stated in §4.10, is that its physical layer is the CGWB manual network (397 chemistry wells, 398–415 level stations), that no sensor or telemetry feed exists, that a replay of the 2013–2021 record dressed as a live feed was considered and rejected because it would misrepresent capability, and that what *was* closed is the other half of the loop: threshold → alert → delivery → acknowledgement on the manual record. *The CPS literature does not provide a sensing layer for Jharkhand groundwater chemistry; the project's contribution is the decision loop, and it says so.*

## 2.8 Research gap

Read together, §2.1–§2.7 locate the gap JalDrishti addresses. The ISR contamination literature is sandstone literature; transferring it to a fractured Indian shear zone requires an explicit fractured-rock transport model whose local parameters are, by the literature's own silence, unmeasured. The groundwater-ML literature assumes temporal, multi-station records that Jharkhand does not have for chemistry, so a "predictive model of degradation trends" in the proposal's sense cannot be trained on measured data — but a surrogate of a physics engine, with conformal uncertainty, can be trained on scenarios placed on real hydrogeology. The vulnerability literature offers intrinsic indices that need layers the state lacks and answer a different question from "would an injected deep source reach shallow wells". The assessment literature offers indices that mislead and limits that say nothing about what was never measured. The network-design literature offers coverage objectives but no rule for a model-blind region. And the CPS literature offers architectures whose physical layer does not exist here.

The gap, then, is a *screening-grade, honestly-bounded* system for hard-rock India: a transport engine with every foreign parameter registered as such, a surrogate whose accuracy is defined as fidelity to the engine, an assessment of the measured record that distinguishes "clean" from "not tested", an alert loop that actually delivers, and a monitoring recommendation that ranks by observation. That is what §3–§6 describe and §8 audits against the proposal.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 3. Study context and data sources

## 3.1 Problem context — the hypothetical ISR scenario

Everything modelled in this report is conditional on a premise that must be stated first: **no ISR uranium mine operates in Jharkhand, and none is planned.** The seven UCIL mines of the Singhbhum Shear Zone are conventional operations in fractured metamorphic rock; every commercial ISR operation on Earth is in unconsolidated or weakly consolidated sandstone, and commercial ISR is not physically plausible in schist-hosted uraninite ore. The project's fidelity matrix records this as its first-ranked disconnect (`ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`, row 3.1), and the user interface was retitled in August 2026 from a mining-feasibility framing to "ISR Contaminant Excursion Screening — not a mining feasibility tool". Every modelled output therefore means *"if ISR-strength lixiviant entered this aquifer at this point"* — a contamination question, never a feasibility judgement, a plan or a permit.

Two consequences follow for how the Texas ISR records are used. They supply what a Jharkhand record cannot: the **source signature** (what an alkaline lixiviant does to groundwater chemistry at the end of mining — uranium, sulphate, TDS, chloride) and the **restoration behaviour** (what fraction of the end-of-mining concentration remains after a real restoration programme, and how long such programmes run). They are *not* used for hydrogeology: every hydraulic property, flow direction, fracture orientation, layer depth and background concentration in the engine is Jharkhand's own (§3.3). The transfer is made in dimensionless form — Péclet number, retardation factor, pore volumes, containment efficiency — so that the physics travels between regions even though the absolute values do not (§4.2–§4.3).

A second premise: **no field validation is possible.** No ISR plume has ever been measured in Jharkhand, and the Texas records are per-mine point chemistry, not plume maps. The engine is benchmarked against exact analytical solutions (§6.2) and its surrogate is validated against the engine; neither has been compared with a real plume, because none exists to compare with. The conformal bands quantify parameter uncertainty inside the model's assumptions; nothing in the system quantifies structural model error, and §5 says so.

## 3.2 Geographic and environmental context

**Terrain and aquifers.** Jharkhand (79,714 km²) is dominated by Precambrian crystalline rock — the Chotanagpur Gneissic Complex in the north and centre, the Singhbhum craton and its shear zone in the south-east — with Gondwana sandstones in the Damodar and other coal basins, Rajmahal basalts in the east, laterite caps and alluvium along the major rivers. The CGWB aquifer polygons used here classify the state into 12 lithologies, of which eight (schist, gneiss, granite, quartzite, charnockite, Basement Gneissic Complex, basalt, intrusive) are treated as *fractured* aquifers and four (limestone, sandstone, laterite, alluvium) as *porous* (`config/parameters.py`, `LITHOLOGY_REGIME`). The Basement Gneissic Complex alone covers 48,047 km², more than half the state — which is why "alert every block on the same aquifer" was rejected as a notification rule (§4.8).

**The vertical column.** The NAQUIM reports for 21 districts, the CGWB district profile for East Singhbhum and regional estimates for the remaining three give a three-layer column per district (`Datasets/naquim_reference/naquim_vertical.csv`): the base of the weathered shallow aquifer (Layer 1) at 13–22 m; productive fractures from about 8–30 m down to a *fracture-death depth* that ranges from 90 m (Khunti) and 100 m (Godda) through 121 m (Ranchi) and 181 m (Dhanbad) to 258 m (East Singhbhum); and the deeper aquifer recorded as confined in the three Singhbhum districts and semi-confined elsewhere. Ore in the Singhbhum deposits lies at 60–250 m (Banduhurang open-pit at the shallow end, Jaduguda's deeper levels at the other) — i.e. inside or at the base of the productive fractured zone, and 100–200 m below the drinking-water aquifer. That separation is what the vertical screening of §4.5 evaluates.

**Regional flow.** The plateau is a divergence: the Subarnarekha drains the south-east past the uranium belt, the Damodar the north-east, the North Koel and Son the north-west. The project's flow field (§4.2) is built from 398 CGWB level stations on a 5 km grid; its hydraulic gradient has a statewide median of 0.0030 (10th–90th percentile 0.0012–0.0076), and at the Jaduguda reference pin resolves to 0.00205 (`ml_pipeline/data_prep/artifacts/flow_field_meta.json`; §6.4).

**Monsoon.** Groundwater in the shallow aquifer is recharged by the June–September monsoon, and the CGWB campaign record shows it: bucketed into the four campaigns, the statewide median depth to water is 7.20 m in May and 3.22 m in August (5.25 m in January, 3.78 m in November), a swing of 3.9 m; the per-station median seasonal swing is 2.38 m and at the Jaduguda pin 4.7 m. The project measured (August 2026) what this does to the *horizontal* gradient — very little: the direction rotates by a median 2.5° (90th percentile 11°, no cell reverses) and the magnitude ratio is 1.05 (p50) — and to the *vertical* gradient across the ore-to-shallow separation — a great deal (§4.5, §6.6). The monsoon is represented statistically (a widened Monte-Carlo gradient range) in the horizontal solve and explicitly (a duty-cycle upward gradient) in the vertical screening; there is no transient recharge model.

## 3.3 Dataset sources

Table 3.1 lists every dataset the delivered system reads, with provider, extent, use and location in the repository. Row counts are those pinned by `ml_pipeline/validation/end_to_end_audit.py` and by the backend seed, re-checked on the report commit. The survey from which these were selected (`docs/local/datasets_source.md`) catalogued twenty candidate sources across five categories; the selection rule was local-first (CGWB and GSI over global grids), provenance over convenience, and refusal to import anything that would make a claim the engine could not support (§3.5 and §7.1 give the rejections).

**Table 3.1 — Datasets read by the delivered system.**

| # | Dataset | Provider / citation | Rows / extent | Used for | Repository path |
|---|---|---|---|---|---|
| 1 | Groundwater chemistry, 2023 | CGWB [39] | 397 wells, 24 districts, 20 determinands; **one sample per well**; U analysed at 342; Fe, As 0 % | IS 10500 assessment, citizen band, measured alerts, engine background concentrations, hydrochemical QA, monitoring-gap ranking | `Datasets/waterQuality_jharkhand.csv` |
| 2 | Groundwater chemistry, 2000–2021 | CGWB via National Water Data Portal, NWIC [41] | 1,632 analyses, 366 stations, 2000–2021; pH/EC 100 %, HCO₃/Cl/Ca/Mg/Na 92 %, hardness 81 %, SO₄ 46 %; **no F, NO₃, Fe, As, Mn**; 2 uranium values | per-station baseline mean/sd and Theil–Sen trend of the general chemistry; read-only | `Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv` (+ physical file: temperature, turbidity) |
| 3 | Groundwater levels, 2013–2021 | CGWB / India-WRIS [40] | 9,583 readings, 398 stations, all months (campaign-bucketed) | flow field (head = DEM − depth), seasonal amplitude, level trends | `Datasets/cgwb_waterlevel_jharkhand.csv` |
| 4 | Aquifer polygons | CGWB / NAQUIM-derived | 24 polygons statewide: lithology, K, specific yield, thickness, transmissivity | regime, K, porosities (with literature fill where a field is "-") | `Datasets/Aquifers_Jharkhand.geojson` |
| 5 | District and sub-district boundaries | Government of India | 24 districts; 264 blocks used for ranking (275 sub-districts loaded) | block resolution, alert targeting, public map | `Datasets/*Boundary_JH.geojson` |
| 6 | Lineaments | GSI / NRSC Bhuvan [42] | 1,889 features; 1,826 structural segments used (799 joint/fracture, 39 dyke, 15 shear zone, 9 fault, 8 fold axis) | strike field → transverse anisotropy and display azimuth | `Datasets/jharkhand_lineaments.geojson` |
| 7 | Perennial rivers | HydroRIVERS v1.0, Lehner & Grill [45], clipped | 4,577 reaches with discharge | receptor distance; plume–river crossing test | `Datasets/jharkhand_rivers.geojson` |
| 8 | NAQUIM vertical table | CGWB NAQUIM district reports [37] + E-Singhbhum profile [38]; 3 regional estimates | 24 rows: Layer-1 base, fracture range, confined flag, confidence | vertical screening; per-district depth-decay length | `Datasets/naquim_reference/naquim_vertical.csv` |
| 9 | Uranium deposits | UCIL deposit outlines (project-digitised) + IAEA UDEPO grades [43] | 7 deposit polygons + a belt envelope; 9 UDEPO Indian deposits | ore-zone gating of the uranium source term; grade scaling; per-deposit ore depth | `Datasets/Jharkhand Ore/`, `Datasets/udepo_uranium_deposits.xlsx` |
| 10 | Texas ISR groundwater quality | USGS data release [15] (Dataset 1) | `TX_ISR_Final.xlsx`: Baseline 86, End-of-Mining 9, Final Post-restoration 86 rows after parsing | source signature (C₀ envelope), paired restoration residuals, porosity | `Datasets/Real_dataset/Dataset_1/` |
| 11 | Texas ISR operations | USGS data release [16] (Dataset 2) | `Restoration.csv` (13 production areas), `TexasISROperations.csv`, `AquiferExemptions.csv`, `MinePermits.csv`, `DisposalVolumes.csv`, `AreaInformation.csv`, `CitationsSources.csv` | restoration reference duration (median 5.0 yr), operating ranges | `Datasets/Real_dataset/Dataset 2/` |
| 12 | Digital elevation model | Copernicus GLO-30 [44] | statewide, 30 m (703 MB, not in git) | flow-field bake only (station head, DEM fallback) | regenerable via `fetch_data/` |
| 13 | Synthetic training set | this project (v5 bake) | 900 scenarios × 5 horizons × 4 species = 18,000 rows; 48 MC draws each; SHA-256 `8ac61f2d…` in the model card | surrogate training; regenerable by seed 42 | `ml_pipeline/outputs/` (not in git) |

Three datasets that were loaded into the database in early 2026 but do not feed the delivered system are noted for completeness: the monitoring-station table of December 2025 (superseded by the level record), the synthetic water-sample rows of March 2026 (flagged `synthetic = TRUE`, later dropped with the `DataGen_ModelMVP` pipeline), and the `Datasets/phase1_sources/` archive of PDFs (EPA and IAEA Kd compendia, the Sethy and Giri papers, the NAQUIM depth evidence) which are literature, not data.

## 3.4 Dataset characteristics

**The measured chemistry record [M].** Table 3.2 gives, per determinand, the count of analysed wells, the minimum, median and maximum, and the number of wells above the IS 10500:2012 acceptable and permissible limits, re-derived from `waterQuality_jharkhand.csv` on the report date (the full table with all columns is Appendix A). Three things stand out. Uranium is below its 30 ppb limit at every one of the 342 wells where it was analysed (maximum 28.5 ppb, median 0.78 ppb); nitrate exceeds its 45 mg/L limit — a "no relaxation" limit — at 22 wells, peaking at 121 mg/L; fluoride exceeds the 1.0 mg/L acceptable limit at 32 wells and the 1.5 mg/L permissible limit at 11. Hardness, calcium and magnesium exceed their acceptable limits at a third to two-thirds of wells, which is hard-rock aquifer chemistry rather than contamination and is reported separately from the health determinands for exactly that reason (§4.7). The carbonate column is zero at all 397 wells, a reporting convention rather than a measurement. The three Singhbhum districts — East Singhbhum (28 wells), Saraikela-Kharsawan (11) and West Singhbhum (16) — were sampled but not analysed for uranium: the uranium belt itself has no uranium result in the record.

**Table 3.2 — Descriptive statistics of the 2023 CGWB chemistry record [M] (397 wells; limits are IS 10500:2012 acceptable / permissible; uranium per WHO 30 µg/L).**

| Determinand | n analysed | Min | Median | Max | Acceptable / permissible limit | n above acceptable | n above permissible |
|---|---|---|---|---|---|---|---|
| pH | 397 | 6.53 | 7.80 | 8.28 | 6.5–8.5 (no relaxation) | 0 | 0 |
| EC (µS/cm) | 393 | 153 | 766 | 2,780 | — | — | — |
| HCO₃ (mg/L) | 393 | 18 | 250 | 1,050 | — | — | — |
| Cl (mg/L) | 397 | 7 | 78 | 430 | 250 / 1,000 | 9 | 0 |
| F (mg/L) | 397 | 0 | 0.42 | 1.91 | 1.0 / 1.5 | **32** | **11** |
| SO₄ (mg/L) | 393 | 2 | 38 | 234 | 200 / 400 | 2 | 0 |
| NO₃ (mg/L) | 393 | 0 | 18 | 121 | 45 (no relaxation) | **22** | **22** |
| Total hardness (mg/L) | 393 | 50 | 260 | 1,060 | 200 / 600 | 264 | 11 |
| Ca (mg/L) | 397 | 6 | 60 | 312 | 75 / 200 | 135 | 5 |
| Mg (mg/L) | 397 | 4 | 26 | 130 | 30 / 100 | 137 | 4 |
| Na (mg/L) | 397 | 1 | 42 | 423 | — | — | — |
| K (mg/L) | 397 | 0 | 6 | 55 | — | — | — |
| PO₄ (mg/L) | 393 | 0 | 0 | 1.3 | — | — | — |
| Fe (ppm) | **0** | — | — | — | 1.0 (no relaxation) | not tested | not tested |
| As (ppb) | **0** | — | — | — | 10 / 50 | not tested | not tested |
| U (ppb) | 342 | 0 | 0.78 | 28.5 | 30 (no relaxation) | **0** | **0** |
| CO₃ (mg/L) | 397 | 0 | 0 | 0 | — | (all zero) | — |

Wells above any health limit at the alert-triggering bar (U > 30 ppb, NO₃ > 45 mg/L or F > 1.5 mg/L): **32** (22 nitrate, 11 fluoride, one well on both). Wells with fluoride between 1.0 and 1.5 mg/L (the warning band, §4.8): **21**. Together these are the 53 measured alerts the deployed scan raises (§6.8).

**The level record [M].** 9,583 readings at 398 stations in 24 districts, 2013–2021, taken in all twelve months but concentrated in the four CGWB campaigns. Bucketed as January (Dec–Feb), May (Mar–May), August (Jun–Aug) and November (Sep–Nov), the statewide campaign medians of depth to water are 5.25, 7.20, 3.22 and 3.78 m. After the Theil–Sen/Mann–Kendall screening of §4.9, 331 stations have a testable record and 84 do not (fewer than 8 readings or under 3 years).

**The 2000–2021 chemistry record [M].** Downloaded from the National Water Data Portal on 20 September 2026 after a profiling decision (§7.1): 1,632 analyses at 366 stations, of which 244 can be matched to the platform's wells with two or more sampling years. It carries the general chemistry (pH, EC, TDS, carbonate, bicarbonate, alkalinity, chloride, nitrate-N at low coverage, sulphate at 46 %, major cations, silica) and *none* of the health determinands the platform bands or alerts on. Its use is therefore restricted to per-station baselines and trends of the excursion-indicator chemistry (§4.9).

**Spatial density.** 397 chemistry wells over 79,714 km² is one well per ~200 km²; 264 blocks have a median of one well each. This is far too sparse to interpolate a concentration field, and the project never does — the engine's background concentration at a pin is the nearest well's value, reported with the distance to that well as part of the data-confidence block.

**The Texas source signature [M].** From the End-of-Mining sheet, per-mine means over nine production-area measurements at seven mines give uranium 9,027–41,595 ppb, sulphate 274–2,976 mg/L and TDS in the same proportion (`config/parameters.py`, `TRAINED_SPECIES_SUPPORT`); the full observed per-mine range is served as the envelope after the second review round rejected a P25–P95 window that narrowed the evidence (`docs/local/audit-record/review2.md` V-2). Paired per-mine restoration ratios (Final Post-restoration / End-of-Mining, median over the seven common mines) are 0.060 for uranium, 0.138 for sulphate, 0.337 for TDS and 0.531 for chloride; the per-mine uranium ratios span 0.023–0.248, an order of magnitude the single served value used to hide. The Texas restoration durations across 13 production areas have a median of 5.0 years (IQR 3.8–6.5; median 18.6 pore volumes), which anchors the restoration draw-down law.

## 3.5 Data quality

The data-quality findings are results in their own right (O2), and are collected here.

1. **One sample per well, in one year.** The 2023 record has no temporal replicates: no trend, no per-well variance, no upper control limit of the mean-plus-five-standard-deviations kind that NUREG-1569 prefers. Substituting the regional spatial spread was tested and rejected — sd(TDS) = 286.5 mg/L gives a control limit of 1,965 mg/L, next to the permissible limit itself (`docs/LIMITATIONS.md` §3). The 2000–2021 record partly closes this for the general chemistry only.
2. **No well depths.** No chemistry sample carries a depth or screen interval; all vertical information is at the district scale. This is the decisive absence behind the 2.5-D decision (§4.5, §7).
3. **Fe, As, Mn never measured.** Iron and arsenic are 0 % populated in the 2023 file; manganese has no column; the 2000–2021 file has none of the three. The proposal named all three. They are reported as `not_tested` on every well rather than passed over, and the alert scanner already reads them so that the first laboratory result to arrive raises an alert without anyone having to remember to add it.
4. **Sampled ≠ analysed for uranium.** 55 wells in the three Singhbhum districts have samples and no uranium result. Both citizen surfaces distinguish *never sampled* from *not tested for uranium*, and neither ever reads as clean.
5. **The 2023 charge balance is a consistency of construction.** The R17 hydrochemical QA (§4.9) found that 393 of 393 computable analyses balance within ±3.2 % (median |CBE| 0.56 %) — a result no routine laboratory batch produces — and that sodium is reproduced from the other ions to a median 1.6 mg/L (65 % within 2 mg/L) and hardness from Ca and Mg within 5 % for 99 % of samples. Sodium was computed by difference; the charge balance is therefore not an independent check on that file, and a count of zero suspect analyses is not evidence of laboratory quality. The independent ion-sum/EC check (median ratio 0.70) passes. On the 2000–2021 file the balance is real: 127 of 753 computable analyses are suspect at the 10 % criterion, and the flag travels with each sample without excluding it.
6. **Year-only sample dates.** The 2023 samples carry a year and no date; `sampled_at` is set to 1 January of that year and is labelled as such.
7. **A demo field observation is in the tracked ore dataset.** During the R11 test of the field-observation workflow (19 August 2026) a submission named `jharia` ("lots of Uranium") was approved and synced into `Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv` as an *added* record with a 400 m radius at 23.39° N 86.28° E, near Dhanbad, where no uranium deposit is known. The R11 fix `0533caa` stopped the belt envelope spreading from it, but the record itself remains, and on the report commit the engine resolves a *deposit-tier* uranium source term (25,300 ppb) at that point. **Found during the writing of this report; recorded here as a data-hygiene defect to be removed through the dataset manager before any further use, and listed in §8 and Appendix H.**

## 3.6 The scenario, precisely

Every modelled result in §6 is conditional on the operating scenario in Table 3.3. Each value carries its provenance; the twelve constants the assumption register names as ungrounded are marked ⚑ and appear in full in Appendix E. Where the console or a registered site overrides a default (the registered Jaduguda site uses Q_in = 1,500 m³/day, W = 300 m, ore depth 150 m, ore thickness 20 m, ring 100 m), the override is stated with the result.

**Table 3.3 — The reference ISR scenario and the transport parameters that govern it.**

| Quantity | Reference value | Trained / allowed range | Provenance |
|---|---|---|---|
| Lixiviant | alkaline (carbonate + oxidant) | — | the only ISR chemistry with public records [12], [15] |
| Uranium source C₀ | 9,027–41,595 ppb envelope; grade-scaled per deposit (Jaduguda deposit pin 15,180 ppb; belt ×0.30 with a 3 km taper; non-ore: trace, suppressed) | as envelope | Texas End-of-Mining per-mine means, n = 9 at 7 mines [15]; UDEPO grade class midpoint / 0.05 % U [43] |
| Sulphate C₀ / TDS C₀ | 1,624.5 mg/L / 3,655.5 mg/L (Texas per-mine means) | 274–2,976 / trained support | [15] |
| Radium-226 C₀ | 1,706 mBq/L (measured maximum, served as the conservative value; GM 371.3) | 23–1,706 | Jaduguda mine-water effluent [22] |
| Background | nearest CGWB well (U median 0.78 ppb; SO₄ 38; TDS from EC × 0.64; Ra 23 mBq/L) | per well | [39]; Ra regional value [24] |
| Injection rate Q_in | 2,500 m³/day (console default); 1,500 at the registered site | 200–8,000 | Texas operations [16] |
| Bleed (net extraction) | 2 % of Q_in | 0–10 % (Q_net 0–400 m³/day) | ISR practice 0.5–3 % [12] |
| Wellfield width W | 300 m (diameter of the circular pattern footprint) | 100–800 m | scenario |
| Operation years | 8 (a multi-wellfield mine unit compressed onto one footprint) | 1–20 | scenario; a single wellfield runs 1–3 yr |
| Restoration sweep | 0 by default; reference 5.0 yr | 0–10 trained; 0–30 served (flagged beyond 10) | Texas median duration [16] |
| Evaluation horizon | 20 yr | 0–20 trained; 0–50 served (flagged beyond 20) | EPA ≥ 30 yr monitoring [20] |
| Monitoring ring | 100 m beyond the wellfield edge | 75–180 m | NUREG-1569 §5.7.8.3 [12] |
| Hydraulic conductivity K | polygon value, blended across contacts, depth-decayed: 0.563 m/day at Jaduguda (T = 370 m²/day over 150 m at the shear zone) | fractured 0.044–10.6; porous 0.096–29.7 | CGWB polygons; E-Singhbhum NAQUIM/profile [38]; K(z) law calibrated per district |
| Gradient i | flow field: 0.00205 at Jaduguda; statewide median 0.0030 | 0.0005–0.02 | 398 CGWB stations + GLO-30 [40], [44] |
| Mobile / total porosity | fractured 0.005–0.010 / 0.01–0.05 (Jaduguda 0.0075 / 0.03) | fractured φ_m 0.006–0.025 | Freeze & Cherry [1]; polygon specific yield where present |
| Dual-porosity capacity ratio β ⚑ | derived: (n_total − φ_m)/φ_m = 3.0 at Jaduguda; 1.0–4.0 across lithologies | prior log-U[0.3, 20]; MC band ×4 | definition; prior and band are foreign-analogue judgements |
| Matrix transfer rate ω ⚑ | 10⁻³ /day | pinned | generic literature |
| Fracture aperture ⚑ / D_e ⚑ | 250 µm (100–500 sampled) / 5×10⁻⁶ m²/day (not sampled) | — | [5], [6] |
| Kd (L/kg) | U fractured 0.3–1.0–3.0, porous 0.5–2.5–8.0; SO₄ 0–0.05–0.3; TDS 0; Ra per regime from [47] | triangular, MC-sampled | [46]–[49] |
| Dispersivity | α_L = 0.83 (log₁₀ L)^2.414; α_T/α_L = 0.02 fractured (0.01–0.10 from strike variance), 0.10 porous | — | [9], [8] |
| Uranium attenuation k | log-triangular (0.05, 0.20, 0.70) /yr; mode by ore zone 0.35 / 0.28 / 0.12 | 0–0.70 | [18]; mineralogy tilt |
| Leach-disc growth ⚑ | gain 0.40, reference 2 bulk volumes | — | scenario |
| Vertical: Kv/Kh ⚑, upward gradient ⚑, wellbore probability ⚑ | 0.03 (fractured) / 0.008 (porous); 0.005; 0.05 | — | scenario; NUREG/CR-6733 context [13] |
| Attribution floor ⚑ | 10 % of the limit | — | modelling policy |
| Excursion control limit ⚑ | baseline × 1.20, bracketed | — | NUREG-1569 "simple percentage" rule [12] |
| Thresholds | U 30 ppb; SO₄ 400 mg/L; TDS 2,000 mg/L; Ra 1,000 mBq/L (WHO); Cl, NO₃, F, hardness per IS 10500 | — | [25], [26] |


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 4. Methodology

The methodology is presented physics-first. The transport engine (§4.5) produces every label the surrogate (§4.6) is trained on, so the engine is the authority and the order of presentation says so; presenting the machine learning first would invite the reading that the surrogate "predicts reality", which it does not.

## 4.1 Overall system architecture

Figure 4.1 shows the delivered system as five layers and the data flow between them; Figure 4.2 the deployed topology. Three repository components implement it: `ml_pipeline/` (the engine, the synthetic-data factory, the surrogate and the engine's own diagnostic dashboard), `backend/` (the FastAPI service, PostgreSQL/PostGIS, the assessment, alert and data-gap services) and `frontend/portal/` (the React/TypeScript portal). The backend imports the engine's FastAPI application **in-process** through an ASGI transport rather than calling a separate service (`backend/app/services/ml_pipeline_adapter.py`): the adapter is the single seam at which the engine would become a network service, and it enforces an allow-list so that no measured chemistry can be passed into a model whose conformal calibration never saw it.

```
Figure 4.1 — Data flow through the delivered system.

  DATA LAYER ......... CGWB chemistry 2023 & 2000-2021 | CGWB levels 2013-21 | aquifer
                       polygons | NAQUIM layers | GSI lineaments | UDEPO grades |
                       HydroRIVERS | GLO-30 DEM | USGS Texas ISR records
        |  preprocessing (4.2): parse, resolve to blocks, bake flow/strike/river fields,
        |  Texas source signature & paired residuals
        v
  PHYSICS ENGINE ..... resolve_inputs(pin) -> feature row (4.3) -> Domenico/Ogata-Banks
  (ml_pipeline/)       plan solve + E1 disc + dual porosity + Tang + restoration wave +
                       attenuation (4.5) -> metrics, contours, NUREG excursion panel,
                       2.5-D vertical screening, 48-draw Monte Carlo
        |                                  ^
        |  900 scenarios x 5 horizons x 4 species = 18,000 physics-labelled rows
        v                                  |
  SURROGATE .......... XGBoost P10/P50/P90 heads + P_ex head, monotone constraints,
  (ml_pipeline/ml)     Mondrian split-conformal calibration (4.6) -> calibrated bands,
                       extrapolation flags, drift monitor
        |
        v
  DECISION LAYER ..... IS 10500 assessment & citizen band (4.7) | alert kinds, tiers,
  (backend/)           seven-field record, delivery ledger, scheduler (4.8) |
                       monitoring-gap ranking, hydrochemical QA, sensitivity (4.9)
        |
        v
  API + PORTAL ....... FastAPI, JWT + 5 roles, Postgres RLS, audit log (4.11) ->
                       22-screen portal: console, report, publications, alerts,
                       my area, data & gaps, network plan, administration
        |
        v
  ACTION ............. advisory published -> block alerts -> email -> acknowledgement;
                       field observation submitted -> regulator review -> dataset sync
```

```
Figure 4.2 — Deployed topology (single-origin, Option A of docs/DEPLOYMENT.md).

  Browser --> Cloudflare Worker (portal static build; proxies /api/* in code)
                    |
                    v
             Render web service (FastAPI + in-process ml_pipeline engine + v5
             artifacts; free tier: sleeps, ~53 s cold start; in-process
             scheduler for the measured scan and email delivery)
                    |
                    v
             Neon PostgreSQL 16 + PostGIS
             two roles: owner (migrations only) and jaldrishti_app
             (NOSUPERUSER, NOBYPASSRLS, DML only) -> row-level security in force
                    |
             SMTP relay (Brevo, port 2525) for alert email
```

## 4.2 Data preprocessing

**Chemistry (2023).** The CGWB table is parsed with `-` treated as missing; TDS is derived from EC where absent (TDS = 0.64 × EC, the mixed-groundwater factor [35]; the February 2026 ingest used 0.65, later aligned); each well is resolved to a block by `ST_Contains` with a nearest-block fallback for wells on a boundary; ingest is idempotent by file SHA-256; every row carries a `record_source` (original or added from an approved observation). The year-only date is set to 1 January and flagged.

**Chemistry (2000–2021).** Parsed from the NWDP CSV; station identity is matched to the platform's wells by name and coordinate proximity; units harmonised; the charge-balance QA of §4.9 doubles as its filter; per-station baseline mean and standard deviation are computed where two or more sampling years exist and a Theil–Sen trend where four or more analyses over three or more years exist.

**Levels → flow field (D1).** Each reading becomes a head, `h = DEM_elevation(station) − depth_to_water`. Readings are bucketed into the four CGWB campaigns (Dec–Feb, Mar–May, Jun–Aug, Sep–Nov), averaged per station per season, and the annual mean is the mean of the four season means so that the over-sampled January campaign does not dominate. On a 5 km grid (82 × 97 cells; 3,247 inside the state) each cell takes a distance-weighted least-squares plane `h ≈ aE + bN + c` through stations within 25 km (Gaussian weight scale 12 km, minimum five stations); the gradient vector is −(a, b), so the flow azimuth and the gradient magnitude come out of vector arithmetic and angles are never averaged. 2,416 cells are station-fitted (median weighted R² = 0.734); 831 sparse cells take direction from a 10 km-smoothed DEM and magnitude from half the topographic slope, flagged `source = 0`. The seasonal amplitude of the fitted gradient magnitude across the four seasons feeds the Monte-Carlo widening. Artefact: `flow_field.npz` (Figure 4.3).

![Figure 4.3 — The baked groundwater flow field: 5 km cells, arrows down-gradient, station-fitted cells and DEM-fallback cells distinguished; 398 CGWB stations, GLO-30 DEM. Source: `ml_pipeline/data_prep/artifacts/flow_field.png`.](figures/fig_flow_field.png)

**Lineaments → strike field (D2/E1).** 1,826 structural segments are gridded on the same 5 km lattice (radius 30 km, minimum 20 segments): the mean strike uses doubled-angle axial statistics, `R̄ = |mean(e^{2iθ})|`, and the circular variance `V = 1 − R̄` measures alignment (statewide V = 0.676; per-cell p10–p90 0.36–0.78; mean strike 79.5°). V sets the transverse-to-longitudinal dispersivity ratio, and the display azimuth is rotated toward the strike by a transmissivity-tensor argument (§4.4). Artefact: `strike_field.npz` (Figure 4.4).

![Figure 4.4 — The fracture-strike field from 1,826 GSI lineament segments: mean strike and circular variance per 5 km cell. Source: `ml_pipeline/data_prep/artifacts/strike_field.png`.](figures/fig_strike_field.png)

**NAQUIM → layer table.** 410 evidence snippets were extracted from the 21 district PDFs into `naquim_depth_evidence.md`, and the layer table of §3.2 was built from them by hand with a per-row confidence and page citation.

**Texas → source signature and residuals.** The three sheets of `TX_ISR_Final.xlsx` are parsed with their header rows located and their unit rows, footnotes and repeated headers rejected by rule (a pinned row-count assertion guards against the parser drifting — review2 V-4); detection-limit strings (`<.001`) and uncertainty notation (`1044±5`) are handled; one pH data-entry error (795) was corrected. Per-mine End-of-Mining means give the C₀ envelope; the paired per-mine ratio of Final-Post-restoration to End-of-Mining medians gives the restoration residual per species (§3.4). The 13 restoration durations in `Restoration.csv` give the 5.0-year reference sweep.

**Boundaries, ore, rivers.** District and sub-district boundaries were found in July 2026 to have been stored with latitude and longitude transposed since February; migration `0011` fixed the data and the loader. The seven deposit outlines were digitised by the project from published positions (two were corrected in July 2026 against independent coordinates); the belt envelope is the deposits' convex hull with a 3.5 km buffer, explicitly labelled as not a surveyed boundary. HydroRIVERS is clipped to the state and rasterised into a distance-to-perennial-river field with reach discharge.

## 4.3 Feature engineering

`build_feature_row` (`ml_pipeline/data_prep/feature_engineering.py`) turns a resolved operating point into the 40-feature row the surrogate is trained and served on. The same function is called by the synthetic generator and by the live server — the *train == serve* invariant that the project's own history (three silent divergences) made a design rule. Table 4.1 groups the features; the full list is in the model card.

**Table 4.1 — The 40 model features.**

| Group | Features | Why they exist |
|---|---|---|
| Regime | `regime_is_fractured` | selects the transport branch (§4.4) |
| Intrinsic hydrogeology | `K_m_day`, `gradient_i`, `phi_mobile`, `phi_total`, `darcy_flux_q = K·i`, `seepage_velocity_v = q/φ_m` | Darcy's law; trees cannot divide, so the ratios are pre-computed |
| Chemistry | `Kd_L_kg`, `retardation_Rd`, `contaminant_velocity_vc` | sorption and its effect on velocity (§4.4) |
| Dispersion | `alpha_L`, `alpha_T`, `anisotropy_ratio`, `D_L = α_L v`, `D_T = α_T v` | scale-dependent dispersivity (§4.4) |
| Dimensionless groups | `peclet_L`, `pore_volumes_PV`, `dimensionless_time_tau`, `dual_porosity_beta` | what transfers between Texas and Jharkhand |
| Operations | `Q_in_m3_day`, `bleed_fraction`, `Q_net_m3_day`, `containment_eta`, `operation_days`, `wellfield_width_m` | the scenario |
| Source | `source_conc_C0`, `background_conc_Cb` | per species; support recorded per species |
| Irregularities and restoration | `downtime_fraction`, `gradient_seasonal_amp`, `restoration_years`, `residual_fraction` (the *realized*, elapsed-credited fraction), `u_attenuation_k` | band width; causal restoration credit |
| Kinematics | `Xc_m`, `Xc_clean_m`, `time_years`, `is_post_closure` | front positions the engine computes analytically |
| Species one-hots | `is_uranium_ppb`, `is_sulfate_mg_l`, `is_tds_mg_l`, `is_radium_226_mbq_l` | one model, four species |

Two leakage controls shape the feature set. There are **no coordinates** among the features: space enters only through resolved physical parameters, so the surrogate cannot invent spatial artefacts of its own (the fidelity matrix's Q4 transect confirmed every step in the ML answer is co-located with a data boundary present in the engine too). And the physics carry-throughs the engine needs but the surrogate must not see (`_eta_eff`, `_source_width_m`, `_grain_density`, `_regime`, `_Xc_clean_m`) are private keys on the row, not features.

## 4.4 Hydrogeological framework

**Regime.** Each of the 12 lithologies is assigned *fractured* or *porous* (Table 3.3). The regime selects which velocity the front runs on, whether the dual-porosity clock and the Tang envelope apply, which Kd table is used, and which transverse anisotropy ratio and vertical Kv/Kh apply.

**Hydraulic properties by lithology.** K, specific yield and thickness come from the polygon where present; effective (mobile) porosity, total porosity and grain density are filled from lithology-typical values [1] where the polygon carries none (fractured mobile porosities 0.005–0.010, total 0.01–0.05; porous 0.08–0.25 and 0.20–0.35). These are drinking-water-aquifer values applied at ore depth, which is the reason for the next two corrections.

**Depth decay of K (fix 3.3, August 2026).** Crystalline-rock permeability falls with depth. The engine applies

$$K(z) = K_{\text{ref}}\,\exp\!\left(-\frac{z - 45}{\lambda}\right), \qquad \lambda = \frac{z_{\text{fb}} - 45}{\ln(1/0.05)} \tag{4.1}$$

where z is the ore depth, 45 m is the depth to which NAQUIM reports fractures as common, z_fb is the district's fracture-death depth from the layer table (258 m in East Singhbhum, 121 m in Ranchi), and K/K_ref = 0.05 at z_fb. Below z_fb the factor is *held*, not extrapolated: extrapolating gave a 23,000× reduction at 300 m for a shallow-fracture district, against about 440× from the global crustal trend of Manning & Ingebritsen [11] over the same interval — the local evidence stops at the fracture base and says "massive rock", not "impermeable". At Jaduguda (180 m) K falls from 2.47 to 0.37 m/day; at the 150 m registered-site depth, to 0.56 m/day.

**Shear-zone transmissivity (D5).** The E-Singhbhum NAQUIM profile records transmissivities of 207–570 m²/day exactly where the deposits lie, several times the generic schist polygon's; the engine applies T = 370 m²/day over a 150 m productive thickness at deposit and belt pins, tapered at the belt edge so the toggle is not a step.

**Seam blending (fix 3.6).** The CGWB layer is finely interleaved — a random in-polygon pin is a median 1.4 km from a contact — so K is blended across mapped contacts in log-K space with weight `w_own = 0.5 + 0.5·min(d/L, 1)`, L ≈ 2.2 km, and the per-district λ and the shear-zone toggle are blended the same way. Measured before/after: the worst single-step area jump on the Ranchi→Jaduguda transect fell from 16.5 ha to 4.75 ha; the district-λ step from 1.74× to 1.015×; the belt-edge shear-zone step from +37 % plume area to +1.7 %; and a regime-contact step of 2.16× that turned out to be caused by an ML-support clamp was removed by deleting the clamp (§7.5). The belt→none step in the uranium source term is deliberately *not* blended: "none" means no ore, and smearing a source into non-ore rock would break the guard that the tool cannot invent contamination.

**Anisotropy from fracture fabric (E1).** The transverse-to-longitudinal dispersivity ratio is set from the strike field's circular variance,

$$\frac{\alpha_T}{\alpha_L} = \operatorname{clip}\!\left(0.02\,\exp\!\frac{V - 0.63}{0.20},\; 0.01,\; 0.10\right) \tag{4.2}$$

anchored so that the state-median V ≈ 0.63 reproduces the literature default of 0.02 for fractured rock [8]; aligned fractures (low V) give a narrow, channelled plume. The plume's display azimuth is rotated from the flow direction toward the strike, blended by alignment strength (the Darcy flux vector rotates toward the high-K direction of a transmissivity tensor).

**Ore-zone gating and grade scaling (Module 2, D4).** The uranium (and radium) source term exists only where uranium ore exists. A pin resolves to *deposit* (inside a deposit polygon or its 500 m halo: C₀ = Texas envelope × grade_deposit / 0.05 % U, clipped to the envelope), *belt* (inside the Singhbhum envelope: 0.30 × the nearest deposit's value, ramped linearly over 3 km from the deposit outline so the tier step is 1.05× rather than 3.3×) or *none* (a trace term of 3 × background with a 5 ppb floor, and `u_suppressed = true` so the surrogate is bypassed and no uranium plume is drawn). Sulphate and TDS are not ore-gated: a lixiviant carries them wherever it is injected.

**Kd.** Distribution coefficients are triangular ranges per species × regime (Table 3.3), sampled per Monte-Carlo draw and served at the central value. Uranium's are low because alkaline-carbonate chemistry suppresses uranyl sorption; radium's are two to four orders of magnitude higher and were rebased in August 2026 from the Thibault soil compilation to measured groundwater values [47] and sampled in log space, which is what gave radium's labels enough variance to be scored at all (§6.2).

**Retardation.** In porous rock, linear equilibrium sorption gives the classical

$$R_d = 1 + \frac{\rho_b K_d}{n}, \qquad \rho_b = (1 - n)\,\rho_{\text{grain}}, \qquad v_c = \frac{v}{R_d} \tag{4.3}$$

with n the total porosity. In fractured rock the bulk-density form is wrong — the solute contacts fracture walls, not the rock volume — so the engine refuses it and applies retardation through two mechanisms: dual-porosity exchange and matrix diffusion (§4.5). The *matrix* retardation `R_m = 1 + ρ_b K_d / θ_m` (θ_m the matrix porosity) is the one place Kd physically acts in fractured rock, and it is the single source of truth for both the Tang attenuation group and the dual-porosity capacity ratio, which must never drift apart.

## 4.5 Contaminant plume simulation

The engine (`ml_pipeline/physics/transport.py`, ~1,500 lines) evaluates a closed-form plan-view concentration field on an auto-sized grid in about 0.2 s and derives its metrics analytically where the grid would quantise them. Its components, in the order they are applied:

**Darcy velocity.** `q = K·i`, `v = q/φ_m` (eq. 4.4). In fractured rock φ_m is under 1 %, which is why fractured plumes move fast per unit flux.

**Containment (the bleed).** From capture-zone theory, a wellfield with net extraction Q_net in regional Darcy flux q through thickness b and width W captures the fraction

$$\eta = \min\!\left(1,\; \frac{Q_{\text{net}}}{q\,b\,W}\right) \tag{4.5}$$

of its own footprint's throughflow; η = 1 is complete capture. Pump downtime degrades it (`η_eff = η(1 − downtime)`); the training generator samples Q_net independently of Q_in so that the surrogate can separate "more throughput" from "more capture".

**Three-phase front.** The leading edge of the plume is

$$X_c(t) = v\,(1-\eta)\,\mathcal{I}\!\big(\min(t, t_{\text{op}})\big) + v\,\big[\mathcal{I}(t) - \mathcal{I}(t_{\text{op}} + t_{\text{rest}})\big]^{+} \tag{4.6}$$

— operation at velocity v(1 − η), the restoration sweep with the front *held* (the conservative representation of a groundwater sweep that in reality pulls water back), and free post-closure drift at v. 𝓘 is the dual-porosity *retarded clock*, the closed-form integral of 1/R_app(t′) for the Goltz–Roberts first-order mobile/immobile model [7]:

$$R_{\text{app}}(t) = 1 + \beta_{\text{eff}}\big(1 - e^{-a t}\big), \quad a = \omega\,\frac{1+\beta_{\text{eff}}}{\beta_{\text{eff}}}, \qquad \mathcal{I}(t) = \int_0^t \frac{dt'}{R_{\text{app}}(t')} \tag{4.7}$$

so that the front moves at water speed early and at v/(1 + β_eff) late. The clock is the identity for porous rock, where v is already the Kd-retarded velocity of eq. 4.3.

**The sorption-scaled capacity ratio.** Until August 2026 the fractured front was species-blind: Kd entered only the Tang term, which is unioned by a maximum and can only extend a plume, so radium moved exactly as fast as sulphate (review finding #2). The correction, which is standard in crystalline-repository safety cases, scales the conservative-tracer capacity ratio by matrix sorption:

$$\beta_{\text{eff}} = \beta \cdot R_m, \qquad R_{\text{eff}} = 1 + \beta\,R_m \tag{4.8}$$

Since R17, β itself is not a served constant but is *derived* from the porosities the run already resolves with provenance:

$$\beta = \frac{n_{\text{total}} - \varphi_m}{\varphi_m} \tag{4.9}$$

(3.0 at Jaduguda with n_total = 0.03 and φ_m = 0.0075; 1.0–4.0 across the lithology table), replacing a literature mean of 10 that the tool's own porosities contradicted by a factor of three. At Jaduguda uranium, R_m ≈ 90 and R_eff ≈ 271; for radium R_eff ≈ 3,500; for TDS (Kd = 0) R_eff = 1 + β = 4. A diagnostic run before the R17 retrain compared this first-order clock with a √t diffusive clock at the three reference sites and found both reach the capacity cap within 3–6 years of a 20-year horizon: the front runs on the *capacity*, not the kinetics, so β is the lever and the clock is not (`docs/LIMITATIONS.md` §1d).

**The plan-view field.** With X_c known, the concentration is the Domenico product [2], [3] with the *full* Ogata–Banks longitudinal factor [4] (the second term was restored in August 2026 after the exact-solution benchmark showed its omission biased concentrations 17–42 % low — §6.2) and the finite-width transverse factor:

$$F_L(x) = \tfrac{1}{2}\operatorname{erfc}\!\frac{x - X_c}{2\sqrt{\alpha_L X_c}} + \tfrac{1}{2}\exp\!\Big(\frac{x}{\alpha_L}\Big)\operatorname{erfc}\!\frac{x + X_c}{2\sqrt{\alpha_L X_c}} \tag{4.10}$$

$$F_T(x, y) = \tfrac{1}{2}\left[\operatorname{erf}\frac{y + W/2}{2\sqrt{\alpha_T x}} - \operatorname{erf}\frac{y - W/2}{2\sqrt{\alpha_T x}}\right] \tag{4.11}$$

$$C_{\text{plume}}(x, y) = C_0\, F_L(x)\, F_T(x, y) \tag{4.12}$$

where x is down-gradient distance from the source plane at the wellfield's down-gradient edge, W is the effective source width, and dispersivities follow Xu & Eckstein [9] evaluated at the transport scale, `α_L = 0.83 (log₁₀ L)^2.414`, with α_T from eq. 4.2. The field is plume-attributable (no background); background is added back at the reporting step.

**Matrix diffusion (Tang envelope).** For fractured rock the engine also evaluates the zero-fracture-dispersion solution of Tang, Frind & Sudicky [5] for concentration along a fracture with diffusion into the matrix,

$$A(x) = \operatorname{erfc}\!\left[\frac{\sigma\sqrt{t}}{2}\cdot\frac{r}{\sqrt{1-r}}\right], \quad r = \frac{x}{X_w}, \qquad \sigma = \frac{\theta_m\sqrt{R_m D_e}}{b} \tag{4.13}$$

where X_w is the *water* front (eq. 4.6 with β = 0), D_e the effective matrix diffusion coefficient and b the fracture half-aperture, and takes the maximum of the retarded-continuum longitudinal factor and this envelope — a deliberately conservative union that can only extend the plume. The R17 diagnostic found the retarded-continuum branch governs at every reference site and species at 20 years; the Tang branch is retained as the early-arrival guard. The aperture is Monte-Carlo-sampled (100–500 µm); D_e is not, because no defensible range exists for it and inventing one would relabel an assumption as data.

**The leach-zone disc (E1).** The wellfield footprint is contaminated by construction. It is drawn as a uniform-concentration disc of radius W_eff/2 centred up-gradient of the source plane, where the effective width grows with throughput,

$$W_{\text{eff}} = W\left(1 + 0.40\tanh\frac{BV}{2}\right), \qquad BV = \frac{Q_{\text{in}}\,t}{\varphi_m\,V_{\text{pattern}}} \tag{4.14}$$

and the disc radius scales with √min(1, PV) so that nothing is drawn before pore volumes have been injected (a July defect drew 7.07 ha at t = 0). The disc is unioned into the *area* metric only; migration and ring concentration track the migrating front and never the source footprint. Between 76 and 97 % of the reported affected area is the disc itself, which is why "footprint" is reported as *wellfield plus a migrating increment* and not as a transport metric.

**Restoration draw-down and the deficit wave.** Restoration exchanges pore volumes; equal fractional removal per pore volume gives exponential decay of the source concentration with *elapsed* sweep time, anchored so that the 5.0-year reference sweep reproduces the paired Texas endpoint and floored at 0.02 (the irreducible residual):

$$\frac{C_{\text{src}}}{C_0} = \max\!\Big(0.02,\; \text{endpoint}^{\,\text{elapsed}/5\,\text{yr}}\Big), \qquad \text{elapsed} = \operatorname{clip}(t - t_{\text{op}},\, 0,\, t_{\text{rest}}) \tag{4.15}$$

A planned-but-future sweep cleans nothing (the QA F-1 fix of July 2026, which removed a 3.3× area snap at the boundary). After closure a passive flush by regional flow continues with a 30-year half-life anchored to the EPA's ≥ 30-year post-restoration monitoring horizon [20]; once a sweep has run, the flush may not take the source below the measured Texas endpoint, because that endpoint is measured on post-restoration *stability* samples and any rebound is already inside it [19] (the R-3 fix, August 2026). The escaped plume keeps its history: a clean-water replacement wave of amplitude (C₀ − C_src) is subtracted with its own front X_clean, released at end of operations and drifting at v,

$$C = C_0\,F_L(x; X_c)\,F_T \;-\; (C_0 - C_{\text{src}})\,F_L(x; X_{\text{clean}})\,F_T \tag{4.16}$$

which is what makes the dark band detach and migrate down-gradient on the map. Two post-freeze corrections (21 September 2026): the source-zone reading is floored at the site's own background, because passive flushing is regional groundwater already at background and cannot dilute the source past it (at Jaduguda's high TDS background, 1,779 mg/L, an unfloored restored source read 1,232 mg/L); and the reading is carried consistently to the lifecycle diagnostic that had computed it independently.

**First-order uranium attenuation.** Down-gradient of the wellfield, dissolved U(VI) meets reducing rock and precipitates as immobile U(IV) — the redox trap that formed the ore. The screening form multiplies the travelling expression (base plume and deficit wave alike, so the wave cannot subtract more than exists) by

$$\exp(-k\,\text{age}), \qquad \text{age} = \frac{x}{v_c} + t_{\text{held}} \tag{4.17}$$

with the two rate-constant senses of Newell et al. [21] — distance (plug-flow travel at the *tracer-retarded* velocity, so that uranium already immobilised by sorption is not charged the reduction rate twice) and time (the years the sweep held the plume still). k is log-triangular (0.05, 0.20, 0.70)/yr per scenario, with the mode tilted by ore-zone mineralogy (deposit 0.35, belt 0.28, non-ore 0.12/yr) and a ×0.5–2 per-draw multiplier; the 0.70 ceiling is the intact-rock value from the Wyoming cross-hole test [18]. It applies to uranium only — sulphate, TDS and chloride are conservative — and never to the source disc, whose reductants the lixiviant deliberately oxidised. The consequence is a finite steady-state extent, `x* = (v_c/k) ln(C₀/threshold)`.

**Metrics.** From the plume field the engine reports: the affected area (cells at or above the *incremental* threshold, `max(threshold − background, 0.10 × threshold)`, unioned with the disc); the maximum migration distance, measured **analytically along the centreline** as the farthest down-gradient point at or above the incremental threshold (a grid read-off quantised short plumes to zero and, before August 2026, returned the distance to the upstream corner of the Domenico artefact box — 422.8 m at Jaduguda for a plume whose true reach was 35.9 m, identical for all species, and baked into the training labels; review finding #1); the concentration at the monitoring ring, `C_plume(ring) + background`; and the breach flag at that ring.

**The NUREG-1569 excursion test.** An excursion is declared when two or more of the three indicator species — chloride, TDS (the conductivity proxy) and sulphate — exceed their upper control limits at the ring, the control limit being baseline × 1.20 bracketed between the baseline and the lixiviant value (the "simple percentage over baseline" rule the review plan permits; its preferred mean-plus-5σ rule needs a per-well temporal series the record lacks). Uranium and radium are deliberately excluded as indicators, exactly as the review plan excludes them. Chloride is computed on the analytical path only (`EXCURSION_ONLY_SPECIES`), which is what let it be added in August 2026 without a retrain. The panel meets NUREG's minimum of three indicators; `compliance_status` states permanently that meeting the count is not regulatory compliance.

**Monte-Carlo bands and excursion probability.** For every scenario 48 draws vary K (log-normal heterogeneity), Kd (triangular), β (log-uniform over [β/4, 4β] clipped to the prior), the fracture aperture, the gradient (widened by the pin's measured seasonal amplitude, ±30 % minimum), dispersivity (×0.7–1.5), net extraction drift, and k. The P10/P50/P90 of area, migration and ring concentration across draws are the distributional labels, and

$$p_{\mathrm{ex}} = \frac{1}{N}\sum_{d=1}^{N} \mathbf{1}\left[ C_d(\mathrm{ring}) \ge \max\left(\mathrm{threshold} - \mathrm{background},\ 0.10\,\mathrm{threshold}\right) \right] \tag{4.18}$$

is the excursion probability — incremental, so that a naturally poor baseline is not blamed on the mine.

**Vertical (2.5-D) screening.** The plan-view solve is depth-integrated over the ore horizon. A separate screening asks whether contamination at ore depth can reach the shallow Layer-1 aquifer through three OR-combined pathways: (1) *dispersive* upward spreading, the Domenico vertical erf factor with α_V/α_L = 0.025 from the source centre to the Layer-1 base; (2) *advective leakage* through the semi-confining fractured zone, `v_up = K_v i_up / φ_conf`, K_v = (K_v/K_h) K_h, breakthrough when `v_up t ≥ Δz` over the gap from the ore *top* to the Layer-1 base (so a thicker ore body shortens the path); (3) a *wellbore* short-circuit at a base probability of 0.05, concentration-gated. The combined index is `p = 1 − (1 − p_disp)(1 − p_adv)(1 − p_well)`, reported as a transparent screening index and never as a calibrated probability, together with every component and the dominant pathway. Two corrections of August 2026 shape it: the upward gradient is bracketed by the measured monsoon swing (wet season suppresses it, possibly closing the pathway; dry season enhances it), reported as a two-end-member band because deep piezometry is unmeasured; and the headline breakthrough time is evaluated on the *duty-cycle* gradient, the annual mean of max(i(t), 0), after the earlier headline at the mean gradient was found to sit outside its own seasonal band and to *understate* the hazard by about 1.9× (`docs/LIMITATIONS.md` §1b). No shallow-aquifer plume after breakthrough is modelled; the radius decides who is told, not how far anything spreads.

**Limitations of the analytical family**, stated where the equations are: uniform steady flow per run; one homogeneous layer per polygon with heterogeneity only statistical; depth-integration (no true 3-D); the Domenico upstream half-plane painted at C₀ (managed by the disc and deficit-wave design and excluded from every travel metric since August 2026); a first-order infinite-sink attenuation where real reducing capacity is finite; the front held rather than reversed during restoration; and a fixed matrix transfer rate ω under a sorption-scaled capacity ratio, which over-retards uranium at early time — bounded by the Tang envelope, which carries the correct √t scaling and governs wherever the continuum branch over-retards. Deriving ω from fracture geometry was implemented, measured and rejected because β_eff·ω cancels R_m and makes early-time retardation species-blind again (`JHARKHAND_FIDELITY_MATRIX.md`, round-2 notes).

**Verification.** The transport kernel is benchmarked against an exact 2-D convolution (`physics/exact_reference.py`: the inverse-Gaussian first-passage density convolved with the transverse factor, self-validated against Ogata–Banks to 10⁻¹⁶ as W → ∞) over 240 parameter sets drawn from the training distribution (§6.2); the retarded clock's closed form is checked against numerical integration (621.1088 vs 621.1088 days in the end-to-end audit); and the physics laws are regression-tested on the *labels* — K↑ ⇒ larger, bleed↑ ⇒ smaller, more Q_in at fixed Q_net ⇒ larger, restoration ⇒ no worse, t = 0 ⇒ zero area and zero migration in both engines — in `tests/test_physics_laws.py`.

**Timeline frames (R17).** For every stored run the engine is re-evaluated at up to ~15 horizons (the base set within the horizon, the horizon itself, and the two phase boundaries), and each frame stores the screening-limit contour, area, migration, ring concentration, phase and the first-exceedance year at the ring. Nothing is interpolated: "first exceedance at the 8-year frame" means the crossing lies between the 5- and 8-year evaluations. The ML band is evaluated per frame but drawn only at the run's own horizon, because the band ellipses belong to that horizon.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

## 4.6 Machine learning

### 4.6.1 Why a surrogate, and what it is not

The proposal promised Random Forest, SVM, gradient-boosting and ANN models trained on measured groundwater data. What was built is a **physics-informed surrogate**: gradient-boosted trees trained on the transport engine's own output over 900 synthetic scenarios placed on real Jharkhand hydrogeology. The substitution is stated here, in the methodology, because it is a methodological decision and not a limitation discovered afterwards.

The reason is the data. The measured record has no time axis and no plume (§3.5); a learner trained on it can predict a concentration at a well from its co-measured chemistry, which the March–May 2026 pipelines did, but it cannot say where an injected source would go, because nothing in the record ever went anywhere. The June 2026 audit of those pipelines (`docs/local/comparison.md`) established that their apparent transport signal — a uranium-versus-distance curve with 70 % feature importance on distance — existed only in their own synthetic generator, where distance was drawn at random and the label computed from it, and that the "real-only R² ≈ 0.69" was scored on rows in which distance and time were blank and median-imputed. It measured the prediction of ambient background, not transport. The June rebuild therefore moved the *physics* into an engine and the *learning* onto the engine's output.

What the surrogate contributes is not accuracy — the engine is right there and is served beside it as the authority — but three things: **calibrated uncertainty bands** that account for parameter uncertainty (K, Kd, β, gradient, dispersivity, bleed drift, attenuation) with a statistical coverage guarantee and without re-running a 48-draw Monte Carlo per request; a **health signal**, because if the surrogate disagrees with the engine on inputs it was trained on, something has changed (the drift monitor); and the groundwork for absorbing field data later, which no closed-form engine can. What it is not: it cannot be more accurate than the engine it learned from; its guarantee holds only inside the trained support, which the UI flags; and it has never been compared with a real plume.

### 4.6.2 Targets and training set

Three band targets — `affected_area_ha`, `max_migration_distance_m`, `compliance_conc` (the ring concentration) — are each learned in log space (`log1p`) by three quantile heads (P10, P50, P90), and one point target, `excursion_probability`, by a regressor: ten XGBoost models [29]. The training set (v5 bake, 21 September 2026) is 900 scenarios × 5 horizons (2, 5, 8, 12, 20 yr) × 4 species = 18,000 rows, 23 aquifer polygons, 48 Monte-Carlo draws per scenario for the distributional labels; 60 % of scenarios draw their gradient, strike variance and seasonal amplitude from the real fields at their pin and 40 % from the operational ranges, so that the surrogate sees both the serving distribution and its margins. The bake is deterministic by seed (42; MC seed 43) and its SHA-256, row count, git SHA and every prior are written into the model card.

### 4.6.3 Quantile regression with physics-derived monotone constraints

Each head minimises the pinball loss `L_q(u) = q·u` for u ≥ 0 and `(q − 1)·u` for u < 0, whose minimiser is the q-th conditional quantile. Hyper-parameters are fixed and recorded, not searched: 450 trees, depth 5, learning rate 0.05, subsample 0.85, column subsample 0.85, L2 regularisation 1.5, histogram method, seed 42 (`metrics.json["config"]`). The absence of a hyper-parameter search is stated in §5.3.

XGBoost accepts per-feature monotone constraints, and the project uses them to inject physical law: 22 constrained features per target (K, gradient, Darcy flux, velocities, X_c, Q_in, pore volumes, C₀, width, downtime and the residual fraction increasing; mobile porosity, R_d, Kd, bleed, Q_net, containment, restoration years, attenuation rate and X_clean decreasing). Every sign is *verified against the labels* in `tests/test_physics_laws.py` rather than assumed; signs that are only conditionally true — operation years, whose direction flips with bleed, and time, because the footprint legitimately grows, stabilises and recedes — are left unconstrained.

### 4.6.4 Conformal calibration

Raw quantile heads under-cover. The project applies split-conformal CQR [27]: scenarios are split into training and calibration folds (grouped, §4.6.5); on the calibration fold the conformity score `s_i = max(q̂₁₀(x_i) − y_i, y_i − q̂₉₀(x_i))` is computed; the ⌈(n + 1)(1 − α)⌉-th smallest score Q̂ widens both edges, `[q̂₁₀ − Q̂, q̂₉₀ + Q̂]`, with α = 0.20. The guarantee under exchangeability is that the widened band covers at least 80 % of new points from the same distribution regardless of how wrong the heads are. It is **Mondrian**: the correction is computed per regime × species cell (eight cells), so fractured uranium does not borrow sulphate's error. And because rows of one scenario are correlated, the gate is **scenario-level** — at least 80 % of scenarios must have all their rows covered — and a finite-sample inflation `DELTA_INFLATE = 1.35` widens the calibration quantile to hold that stricter bar. The per-cell deltas (in log units) are in the model card and Appendix B.

### 4.6.5 Leak-proof validation and the field-resampled gate

Two cross-validations are reported. **GroupKFold(5) on `scenario_id`** keeps all twenty rows of a scenario in one fold, because a model that has seen fifteen rows of a scenario "predicts" the other five trivially. **Leave-aquifer-out on `polygon_id`** holds out whole aquifer polygons (23 groups) to test spatial generalisation to geology never seen in training. Three baselines are fitted on the same features in the same folds (R17): the training-mean predictor, a ridge regression and a depth-1 gradient-boosting stump, reported next to the surrogate so that an R² is never presented without a "compared with what".

The conformal guarantee is calibrated on the generator's distribution, whose median gradient runs about 1.35× the real field's (review2 V-5). The **field-resampled coverage gate** therefore bakes a separate 120-scenario batch with every scenario pinned to the real flow and strike fields (`--field-mix 1.0`), held out from training, and requires ≥ 0.80 scenario coverage on it for every target. If it fails, the rule is to widen the deltas, never to lower the gate.

### 4.6.6 Explainability and the drift monitor

SHAP values [30] (`ml/shap_analysis.py`) rank features per head; the top features are checked against the physics they should reflect (§6.3). Every live request records the relative disagreement between the analytical and surrogate answers; `GET /api/drift` reports the rolling median and flags drift when it exceeds a threshold over a window.

### 4.6.7 Retraining discipline

Every change to a training label — a physics fix, a new species, a prior — is a full re-bake (~2 h), a retrain, a conformal recalibration, the field-resampled gate, `sync_docs` and the end-to-end audit, gated on a pilot label-diff against a byte-identical baseline of the previous artifacts. The surrogate was retrained ten times between June and September 2026; §1.8 and §7.2 record why. The documented metrics block in `ARCHITECTURE.md` §6.5 is generated from `metrics.json` and a test fails if it drifts, because it was hand-copied three times and drifted three times.

## 4.7 Vulnerability and risk assessment

The system produces categories from three different kinds of number, and keeps them apart.

**Modelled excursion risk [S].** From the engine: the excursion probability p_ex (eq. 4.18), the NUREG 2-of-3 declaration, the ring concentration against the incremental threshold, and the migration band. These are reported per run with the engine that produced each.

**Modelled vertical (shallow-aquifer) vulnerability [S].** The 2.5-D index of §4.5 is banded *high / moderate / low / contained* with the dominant pathway and the duty-cycle breakthrough year; a breakthrough probability at or above 0.5 within the run's horizon is the gate the breach-due alert uses.

**Measured health band [M].** Every citizen-facing surface — the public map, the resident's "My Area", the block popups — derives its band from one shared rule (`backend/app/services/health_bands.py`, R15): the maximum measured value of each *health-significant* determinand in the block's wells (uranium, nitrate, fluoride) against its IS 10500 limit. *High concern* if any exceeds its permissible (or no-relaxation) limit; *moderate* if any exceeds acceptable; *low* if all analysed determinands are within limits; **`Not tested`** — grey, never green — if the block has samples but none analysed for the health set; *No data* if it has no sample. Hardness, alkalinity and TDS are deliberately excluded from the band because they exceed at two-thirds of the state's wells and are aquifer chemistry rather than contamination; they remain on the water-quality surface. Two fields travel with every band: `band_driver` (which substance decided it, because "high concern" without a substance is not actionable — a resident can boil for bacteria but cannot boil out fluoride, and boiling *concentrates* nitrate) and `untested_health` (which health determinands were never looked for; arsenic and iron appear unconditionally, so no block in Jharkhand is ever presented as cleared for them).

Why source-specific vulnerability and not DRASTIC: §2.3. The composite WQI is computed as a secondary figure with its `dominated_by` term shown, for the reason in §2.1.

## 4.8 Alert generation and delivery

Five alert kinds, four tiers, seven structured fields, one delivery ledger (migrations `0018`, `0021`, `0023`, `0025`, `0026`; `backend/app/services/alerts.py`, `alert_tiers.py`, `notify.py`).

**Kinds.** `measured_exceedance` — a laboratory value in a block's well over an IS 10500 limit (the *observed* channel; one alert per well listing every breach, with determinand-specific advice). `published_screening` — an advisory was published and the modelled central (P50) footprint intersects the block (`ST_Intersects` of the stored contour with the block polygon). `possible_reach` — the block lies inside the P90 migration envelope but outside the central footprint (R17). `aquifer_pathway` — the block shares the shallow aquifer a modelled vertical pathway would enter, within an advective reach `v = K·i/φ` over the horizon capped at 25 km (three gates; alerting the whole formation was rejected because the Basement Gneissic Complex would turn one 13-hectare plume into a statewide warning). `aquifer_breach_due` — a published run's modelled breakthrough year has elapsed since the site's *injection start date* (five gates; dry-run by default because it is the only alert that fires without anyone acting).

**Tiers (Algorithm 4.1).** The ladder uses IS 10500's own two limits and adds one project-defined rung, labelled as such in every record:

```
Algorithm 4.1 — tier assignment (alert_tiers.py)
observed reading r of determinand d at well w:
    if r > acceptable(d) and r <= permissible(d):                     tier = warning
    if r > permissible(d) or (no-relaxation(d) and r > acceptable(d)): tier = alert
    if r >= 2.0 x alert-limit(d)                                        tier = critical   # project-defined
       or (count of health determinands over their alert limit at w) >= 2: tier = critical   # project-defined
modelled result for block b from run R:
    published_screening (b in P50 footprint):                          tier = notice
        if p_ex(R) >= 0.5 within horizon:                              tier = alert
    possible_reach (b in P90, not P50), aquifer_pathway, breach_due:   tier = warning
    critical is unreachable (CHECK ck_modelled_never_critical)
```

Selecting the warning rung on the acceptable limit made 21 fluoride wells between 1.0 and 1.5 mg/L reachable that a permissible-only scan had never raised.

**The seven fields.** Every alert carries `basis` (observed | modelled), `driver` (determinand, value, unit, limit, times-limit), `where` (block, district, well or footprint hectares), `tier`, `confidence` (observed: laboratory result and sample date, with the charge-balance flag; modelled: the P10–P90 band, extrapolation flags, data-confidence reasons), `next_action` (determinand-specific for observed alerts; for modelled ones, the monitoring wells inside the P90 reach and the first year the ring is predicted to exceed, or the statement that no well exists inside the reach) and `what_happened` (one sentence). The prose body stays for readability; the fields make the workflow auditable and let §6.8 show the chain *data → detection → prediction → vulnerability → alert → explanation → recommended action* as real records.

**Idempotence and RLS.** Alerts are upserted on `(block_id, well_name, sampled_at)` for the measured kind and on `(advisory_id, block_id, kind)` for the modelled kinds; the upsert needs an UPDATE policy on the row-level-secured table, which `alerts` lacked until migration `0026` — the fourth instance of a class of defect this project met (§4.11).

**Delivery.** Registration records the resident's home block (by name, or by a point resolved with `ST_Contains`; a point outside every block is a 422) and subscribes the account to it in the same transaction. `deliver_pending` joins alerts to subscriptions to users with an email address and `alert_email_opt_in`, sends one message per pair over plain SMTP in a worker thread, and records each attempt in `alert_deliveries` with status `sent | failed | skipped` and the SMTP error; the unique index on (alert, user, channel) makes a re-run send nothing twice, demo addresses on reserved domains are skipped, and — since 21 September 2026 — a `failed` row is treated as pending and overwritten on retry, after the deployed system showed three deliveries permanently stuck at "failed" with zero retries. With no SMTP host configured the job sends nothing and reports the backlog as a visible count on the Administration screen. An in-process scheduler runs the measured scan and delivery every 24 hours; the breach-due scan is deliberately not automated.

## 4.9 Uncertainty and data-gap analysis

**Two kinds of uncertainty, kept apart.** *Parameter* uncertainty — how well K, Kd, β, the gradient, the aperture, the dispersivities and the attenuation rate are known — is propagated by the 48-draw Monte Carlo into the P10/P90 labels and by conformal calibration into the served bands. *Structural* uncertainty — whether an equivalent-porous-medium model with a dual-porosity overlay is the right model for a shear zone, whether a Texas source term transfers to uraninite-in-schist — is not propagated by any band, and cannot be; it is registered. The register `UNGROUNDED_PARAMETERS` in `config/parameters.py` names twelve constants (β prior and band, ω, aperture, D_e, the two leach-disc growth constants, the attribution floor, the excursion control-limit percentage, Kv/Kh, the upward gradient, the wellbore probability and the irregularity ranges), each with its kind (scenario assumption / foreign-analogue literature / modelling policy), what it leverages, and what measurement would ground it. It is served at `GET /api/v1/ml/assumptions`, shown on the Methods page, and test-pinned; admin editing of these constants was deliberately not built, because an edited constant invalidates every training label.

**Extrapolation and data confidence.** Every served input is checked against the deployed model card's training envelope (the operational sliders), its per-regime hydro support (K, φ_m, R_d) and the per-species C₀/C_b support; anything outside is listed in `extrapolation`, the analytical engine still serves, and the UI says the band's 80 % no longer means 80 %. A `data_confidence` block reports the distance to the nearest chemistry well, whether the aquifer was resolved by point-in-polygon or by fallback, and the flow-field source (station fit or DEM). Tolerances for decade-spanning quantities are ratio-based, after a 2 %-of-linear-span tolerance was found to be five times the trained K minimum and to let a K three orders of magnitude below support pass silently.

**Global sensitivity analysis (R17).** `ml_pipeline/validation/sensitivity.py` sweeps thirteen inputs — group A, the seven registered ungrounded constants that enter the plan-view solve (β, ω, aperture, D_e, the two disc-growth constants, the attribution floor); group B, six resolved hydrogeological inputs with their Monte-Carlo or literature ranges (K, gradient, mobile porosity, Kd, C₀, k) — at three reference sites (the Jaduguda deposit, a belt point, a non-ore point at Ranchi) for uranium and sulphate at 20 years with 8 years of operation and a 3-year sweep. One-at-a-time elasticities are taken at 7 points per input; Sobol first-order (Saltelli 2010 [50]) and total-order (Jansen 1999 [51]) indices at a base sample of N = 256 (≈ 3,600–3,800 analytical evaluations per site and species), on log-transformed outputs where the range exceeds 20×. Outputs that are constant over the whole design (uranium at a non-ore pin, where the source is suppressed) or pinned at the attribution floor are reported as *degenerate* with indices undefined, not as zeros. Results are §6.9 and Appendix J.

**Hydrochemical QA (R17).** For every analysis with a complete major-ion set the charge-balance error is computed in milliequivalents,

$$\mathrm{CBE} = 100 \cdot \frac{\sum_{c} z_c m_c - \sum_{a} z_a m_a}{\sum_{c} z_c m_c + \sum_{a} z_a m_a} \quad [\%] \tag{4.19}$$

(z_c m_c and z_a m_a the charge-weighted molar concentrations of cations Ca, Mg, Na, K and anions HCO₃, CO₃, Cl, SO₄, NO₃, F, in milliequivalents; pH excluded as negligible between 6.5 and 8.5), with the conventional classes ±5 % accepted, 5–10 % questionable, > 10 % suspect [35], [36], and a second, weaker check of the ion sum against EC (0.55–0.75 expected). An *incomplete* analysis is reported as such, never as a pass. The flag travels with the sample and never removes an exceedance from a band or an alert; a nitrate of 121 mg/L in an unbalanced analysis is still the laboratory's reported nitrate, and the imbalance means the analysis deserves a re-run, not that the number is wrong in a known direction. An `independence_check` reports whether sodium reproduces from the other ions (§3.5).

**Observation-based monitoring ranking (R11).** Every block is scored 0–100 by five factors with visible weights: never sampled (30), sampled but not analysed for uranium (30), wells per 100 km² against a good-coverage bar of 3 (20), distance from the block centre to the nearest uranium-tested well saturating at 25 km (15), and proximity to a registered hypothetical site (5, deliberately the smallest: no such mine exists). Area is the tie-break, not a sixth factor. The weights are a policy, returned in the API response and drawn on screen so that a reader can disagree with the ordering by disagreeing with a number they can see. A gap matrix (block × determinand × tested / not tested), suggested well sites for a chosen block, and a network-plan map follow from the same scoring.

**Level and chemistry trends.** Groundwater-level series are tested by Theil–Sen slope [31], [32] with the Mann–Kendall test [33], [34], chosen because the series are short, irregular, seasonally forced and outlier-prone — every assumption of ordinary least squares is violated, and OLS would report a confident slope regardless. A station with fewer than 8 readings or under 3 years gets *not enough record*, never *stable*. The same module is reused for the 2000–2021 general chemistry (≥ 4 analyses over ≥ 3 years for a trend; otherwise a baseline only). Nothing is extrapolated forward: the trends describe what the measurements did, not what they will do.

## 4.10 CPS architecture

The proposal's CPS genesis described sensors, real-time streams and a closed loop. Table 4.2 states, layer by layer, what is implemented, what is conceptual and what is future — and the physical layer is marked *manual*.

**Table 4.2 — The CPS layers as delivered.**

| Layer | What exists | Status |
|---|---|---|
| Physical / sensing | The CGWB manual network: 397 chemistry wells (one campaign), 398 level stations (quarterly campaigns). No sensor, no telemetry, no live feed. A replay of the 2013–2021 record dressed as a live feed was considered in R13 and refused as a misrepresentation of capability. | **Manual; sensing is conceptual / future** |
| Data | CSV/GeoJSON ingest (admin, SHA-256 idempotent), dataset sync with provenance and restore points, an advisory lock on writes (two concurrent syncs used to lose one), a field-observation submission → regulator review → sync path, an immutable audit log. | Implemented |
| Computation | The transport engine and the surrogate, in-process; timeline frames; sensitivity; hydrochemical QA. | Implemented |
| Decision | IS 10500 assessment, the one banding rule, alert kinds and tiers, the seven-field record, the monitoring ranking. | Implemented |
| Action | Advisory publication by the single admin; alerts raised per block; email delivery with ledger and retry; scheduler; acknowledgement in the resident's inbox. | Implemented (email needs a provider the operator configures; no SMS) |
| Feedback | Field officer submits an observation (e.g. an ore occurrence); regulator approves; admin syncs into the dataset the engine reads; the next run sees it. | Implemented as a workflow; the feedback is human, not sensed |

The honest description is *CPS-ready decision support over a manual monitoring network*: the threshold → alert → notification → acknowledgement half of the loop runs end to end on the CGWB record; the sensing half does not exist and none was faked.

## 4.11 Software architecture

**Backend.** FastAPI (async) with SQLAlchemy 2.0 and asyncpg over PostgreSQL 16 + PostGIS; Alembic with 26 migrations (`0001_initial` … `0026_alert_tiers_and_explanation`); 25 routers exposing **152 endpoints**; 36 service modules; 20 ORM models. Authentication is JWT (python-jose) with argon2 password hashing and a sliding-session refresh; the caller's role is re-read from the database on every request rather than trusted from the token. There is no task queue: simulations run as in-process FastAPI background tasks, and the one scheduled job is an asyncio loop in the application lifespan. The engine is called in-process through `ml_pipeline_adapter`, which allow-lists the payload and pins every completed run to the model-card SHA, the artifact-bundle SHA and the code version (`ck_sim_runs_completed_is_pinned`).

**Roles and row-level security.** Five roles — `admin` (exactly one, enforced by a partial unique index; created by `bootstrap_admin`, never by the UI), `regulator` (reviews field submissions; may run the model; may not publish, write datasets or manage accounts), `analyst`, `field_officer` (*Data Submitter*) and `citizen` (*Resident*, who never sees a coordinate or a model internal — the one distinction with a policy reason: publishing a precise coordinate for a speculative mine next to a named village invites it being read as a plan). Authorization is enforced three times: by API dependencies, by Postgres row-level security policies reading per-transaction settings (`app.current_role`, `app.current_org_id`, `app.bypass_rls`) applied with `SET LOCAL`, and by database privilege — the API connects as `jaldrishti_app` (`NOSUPERUSER`, `NOBYPASSRLS`, DML only, no `CREATE` on `public`), migrations as the owner. The role × endpoint matrix is generated from the running application into `docs/roles.md` and a test fails on drift. The audit log has no UPDATE or DELETE policy for any role, so it is append-only by construction.

**Frontend.** Vite 6 + React 18 + TypeScript 5.7 + Leaflet + TanStack Query; 22 screens (front page, login, overview, console, report, compare, scenarios, publications, field data, water quality, groundwater trends, data & gaps, network plan, datasets, ingest, my area, citizen map, alerts, methods, audit, administration, public view), filtered by role; light and dark themes with every colour a token; keyless basemaps (the CARTO tiles began watermarking browser requests in September 2026 while serving clean tiles to command-line checks). A build guard fails `npm run build` if a credential reaches the bundle, after working admin credentials were found compiled into it in August 2026.

**Test strategy.** 373 engine tests (physics laws on labels, restoration continuity, exact-solution benchmark, review-round regressions, docs-in-sync, artefact provenance, the background floor) and 522 backend tests against a real PostGIS database (RLS on the live connection, the authorization matrix, security hardening measured — 10 logins then 429s — alert tiers, delivery and retry, timeline, QA, water quality). Two things the harness cannot catch are stated rather than hidden: the test database is built from ORM metadata, so **RLS policies do not exist in it** and an insert production refuses succeeds in the suite (guarded at source level, with tests that say so); and the portal has no unit tests beyond the credential guard — every screen was verified by hand in the browser, with the record kept.

**Two engineering findings recorded as method.** First, *after any COMMIT the RLS context is gone*: `SET LOCAL` dies at commit by design, so code that commits and keeps writing is anonymous from then on, and RLS-protected tables return nothing rather than erroring. This caused three silent failures (an alert system that never delivered, a run endpoint that never worked, the alert upsert) and a fourth form (an `ON CONFLICT DO UPDATE` needs an UPDATE policy). The rule adopted: write the value in the original INSERT; check `pg_policies` for UPDATE before any upsert on an RLS table. Second, *configuration that enforces nothing*: a rate limit read into settings and listed in the deployment checklist applied to nothing for months because the middleware that consults it was never installed; the alert insert, the exceedance scan and the docker-compose database role were the same shape. The only detection was to *measure* — count 429s, count rows — and each control now has a test that measures it.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 5. Assumptions and limitations

Each row states an assumption, where it enters the system, the consequence if it is wrong, and how the product discloses it. The source is the live register `docs/LIMITATIONS.md` and the `UNGROUNDED_PARAMETERS` register, reorganised rather than copied; the tables are the reason the results in §6 can be read without over-reading them.

## 5.1 Scientific assumptions

| Assumption | Where it enters | Consequence if wrong | How it is disclosed |
|---|---|---|---|
| No ISR mine exists in Jharkhand; commercial ISR is not plausible in schist-hosted ore; every output means "if ISR-strength lixiviant entered this aquifer" | the premise of every run | every modelled number would be read as a feasibility finding or a forecast | the UI title and disclaimer; `LIMITATIONS.md` §0; this report's conventions |
| Porous-medium ISR physics (Domenico) transfers to fractured schist with a dual-porosity + matrix-diffusion overlay | §4.5 | a real shear-zone plume would be narrow fingers along shears, not a smooth ellipse; extents could be wrong in either direction | fidelity matrix Q1; "screening-grade, indefensible for prediction" |
| Analytical, steady, uniform, single-layer transport | §4.5 | no channelling, no transients, no true 3-D | §4.5 limitations paragraph; the 2.5-D decision |
| Linear equilibrium sorption with literature Kd ranges; alkaline chemistry suppresses uranium sorption | eqs. 4.3, 4.8, 4.13 | retardation wrong by the Kd error; the fractured front is species-dependent only through R_m | Kd sampled into the bands; register entries |
| First-order, infinite-sink uranium attenuation with a Wyoming-calibrated ceiling | eq. 4.17 | long-horizon attenuation overstated where reducing capacity is exhausted, understated where fresh | k sampled over a 14× range; mode tilted by mineralogy; sulphate/TDS carry none |
| β derived from lithology-typical porosities; a log-uniform [0.3, 20] prior; a ×4 band | eq. 4.9; every fractured label | the plume extent scales with β (β = 0.5 → 61 m; β = 0 → 938 m at Jaduguda uranium, 20 yr); the band expresses uncertainty *inside* the prior | `hydro.beta_basis`; §6.9 sensitivity; "a Singhbhum tracer test is the only thing that retires this" |
| Fixed matrix transfer rate ω; foreign-analogue aperture and D_e | eqs. 4.7, 4.13 | early-time over-retardation of uranium in the continuum branch (bounded by the Tang union) | register; sensitivity ≈ 0 at 20 yr except belt uranium |
| Texas source term (n = 9 at 7 mines), grade-scaled, applied to uraninite-in-schist | C₀ | the served C₀ is ~40× the measured Jaduguda passive mine water (GM 357 ppb [22]); leach kinetics of massive uraninite with sulphides differ from roll-front coffinite | `source_term_context` in every response reports the ratio to the measured value |
| Texas restoration endpoints (paired per-mine ratios) | eq. 4.15 | per-mine ratios span an order of magnitude; the single median hides it | the spread is sampled into the bands; the floor at the endpoint is explained |
| Vertical: Kv/Kh, an upward gradient of 0.005, a wellbore probability of 0.05 | §4.5 vertical screening | the shallow-impact index is "violently sensitive" to the gradient (0.005 → moderate, 0.020 → high) | bracketed by the measured monsoon swing as a two-end-member band; register |

## 5.2 Data assumptions and limitations

| Limitation | Where it bites | Consequence | Disclosure |
|---|---|---|---|
| One chemistry sample per well, one year (2023) | trends, control limits, alerts on rate of change | no measured-quality forecast is possible; no per-well UCL of the mean + 5σ kind | §3.5; the 2000–2021 record read for general chemistry only |
| No well depths or screen intervals | any vertical claim | 3-D is unsupported; the vertical column is a district table | §4.5, §7 |
| Fe, As, Mn never measured; CO₃ all zero | health band, alerts, the proposal's input list | no block can be cleared for arsenic or iron | `untested_health` on every band; `not_tested` on every well |
| 55 wells in the three Singhbhum districts un-analysed for uranium | the uranium belt itself | the belt is untested for the one contaminant the tool screens for | `Not tested` band; ranking factor with weight 30 |
| Spatial density ~1 well per 200 km² | background at a pin | the nearest well may be tens of km away | `data_confidence.nearest_well_km` |
| NAQUIM at district scale; three districts on regional estimates | vertical screening, K(z) | a per-district λ and layer base applied to every pin in the district | confidence column in the layer table |
| CGWB values characterise the shallow aquifer, applied at ore depth through a modelled K(z) | every fractured run | the deep K is a law, not a measurement | `extrapolation` reports `hydro:K_m_day` below trained support |
| The 2023 charge balance is a consistency of construction (Na by difference) | QA | zero suspect analyses is not evidence of laboratory quality | `independence_check` reported with the QA summary |
| The 2000–2021 record carries no health determinand | D1 "forecast trends" | trend forecasting for any banded or alerted determinand remains undemonstrated | §7; no band or alert uses the record |
| A demo field observation (`jharia`) sits in the tracked ore dataset | uranium source term near Dhanbad | a deposit-tier hypothetical source where no deposit exists | found during this report; §3.5 item 7; to be removed via the dataset manager |

## 5.3 Modelling (surrogate) limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| The surrogate is trained on the engine's output and cannot exceed it | its accuracy is fidelity to the engine, not to reality | every UI number names its engine; "analytical is the authority" |
| Conformal coverage is guaranteed inside trained support and for parameter uncertainty only | outside support the band no longer means 80 %; structural error is uncovered by any band | `extrapolation` flags; §4.9 |
| Radium labels are point masses (81.8 % exact zeros for migration; 95.8 % pinned at background for compliance) | R²(log) 0.500 / 0.235, below the project's 0.60 gate; a squared-error learner on `log1p` cannot fit a point mass | reported as a miss in the generated metrics block; the analytical engine serves the central value; the conformal band on those cells still covers |
| Hyper-parameters fixed, no search; no ANN/deep families | possibly sub-optimal heads; nothing to learn that XGBoost has not on 18,000 synthetic rows | stated in §4.6.3 and the audit's D-list |
| Tree quantisation seams (~17 % migration across rest 0 → 0.5 yr; ~0.6 ha at the restoration boundary) | step changes in the surrogate where the engine is smooth | measured; the engine stays inside the band at every probed seam (6/6) |
| Pooled back-transformed R² mixes ppb, mg/L and mBq/L (compliance R²(P50) = −4.48) | the pooled number depends on the species mix, not model quality | judged on per-species and log figures |

## 5.4 Simulation (scenario) limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| Every result is conditional on the scenario of §3.6 | changing Q_in, W, operation years or the ring changes every number | the scenario is stated before any result; the registered site's overrides are printed with its report |
| Depth-integrated plan view; 2.5-D vertical screening only | no depth-resolved concentration; no shallow plume after breakthrough | §4.5; "the radius decides who is told, not a predicted extent" |
| Uniform flow direction per run from a 5 km field | a pin between stations takes the interpolated direction; divides are flagged | `flow_field.source`, `near_divide` |
| Horizon ≤ 50 yr, trained to 20; restoration trained to 10 | beyond the trained range the surrogate extrapolates and is flagged; the engine still serves | hollow points on the sweep chart; `extrapolation` |
| Operation years up to 20 represent a multi-wellfield unit on one footprint | a single wellfield runs 1–3 yr | §3.6 |
| The front is held, not reversed, during restoration | conservative: the model cleans slower than a real sweep | §4.5 |

## 5.5 System and engineering limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| No sensors, no telemetry | not real-time; CPS-ready decision support, never a live loop | §4.10; the words "real-time" avoided |
| Email only; no SMS; the SMTP provider is the operator's; the free tier sleeps the API and with it the scheduler | a resident without email is reached only through the portal; alerts wait while the API sleeps | the Administration screen counts the backlog |
| The test database has no RLS policies | RLS-after-COMMIT defects are not runtime-testable in the suite | source-level guards, and tests that say so |
| No frontend unit tests; PDF pagination hand-checked | regressions in the portal are caught by hand | build guard only |
| No run reaper for jobs orphaned by a restart; engine rate limit per host; backups defined but a restore run once | operational, not scientific | `DEPLOYMENT.md` §8c, §9 |
| Deployed API runs the committed artifacts of whichever commit was last deployed | the report's numbers are from `476a4a9`; the deployment must be redeployed to match | §8 of `PROJECT_FREEZE.md` |

## 5.6 Generalisation limits

| Claim | Status |
|---|---|
| Jharkhand only | the datasets end at the state boundary; a pin outside is a 422, because a prediction there would be fabricated |
| Other commodities (coal, rare earth, heavy metals) | *designed for* through the species registry (`SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES`; chloride was added without a retrain as the proof) — **not demonstrated** |
| Any modelled result | a conditional statement about a hypothetical operation, never a forecast of real contamination |
| "Validated" | benchmarked against exact solutions and internally gated — never validated against a real plume, because none exists to validate against |


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 6. Results

## 6.0 What kind of result each subsection reports

**[M]** measured — a laboratory value or a station reading compared with a published limit; nothing modelled. **[S]** modelled scenario — the engine or surrogate evaluated for the hypothetical operation of §3.6; conditional, never a forecast. **[V]** model-internal validation — the surrogate against the engine, or the engine against an exact solution. Every figure caption repeats the tag. Every number in this section was re-derived on the report date from the artefact named in Appendix H; where an earlier value is quoted for comparison it carries its date.

## 6.1 Exploratory data analysis of the measured record [M]

**Exceedances against IS 10500:2012.** Table 3.2 is the descriptive record. The health-significant findings, re-derived from `waterQuality_jharkhand.csv`: uranium is within its 30 ppb limit at all 342 analysed wells (maximum 28.5 ppb at Sukurhutu, Ranchi; median 0.78 ppb); nitrate exceeds 45 mg/L at **22** wells, peaking at 121 mg/L at Biru (Simdega) and 99 mg/L at Lowadih (Ranchi) — 2.7× and 2.2× the limit; fluoride exceeds the 1.0 mg/L acceptable limit at **32** wells and the 1.5 mg/L permissible limit at **11** (maximum 1.91 mg/L at Baresad, Latehar). One well, Gidhaur (Chatra), exceeds both the nitrate and the fluoride permissible limits. In all, **32 wells** carry a health exceedance at the alert-triggering bar and **14 of 24 districts** contain at least one — Bokaro, Chatra, Dhanbad, Garhwa, Godda, Gumla, Hazaribagh, Koderma, Latehar, Lohardaga, Palamu, Ramgarh, Ranchi and Simdega. By contrast 71 % of wells exceed *some* IS 10500 limit, most of it hardness, calcium, magnesium and TDS — hard-rock aquifer chemistry rather than contamination — which is why that figure is never reported first.

**What was not measured.** Iron and arsenic: zero of 397. Manganese, temperature, turbidity, dissolved oxygen: no column (temperature and turbidity exist in the NWDP physical file, 2000–2021). Uranium: 55 wells in East Singhbhum (28), Saraikela-Kharsawan (11) and West Singhbhum (16) sampled and not analysed.

**Hydrochemical QA.** Of 397 analyses, 393 have a complete major-ion set. All 393 balance within ±3.2 % (median |CBE| 0.56 %); none is questionable or suspect. Sodium re-derived from the other ions reproduces the reported value to a median 1.6 mg/L (65 % within 2 mg/L); total hardness equals 2.497 Ca + 4.118 Mg within 5 % for 99 % of samples. The ion-sum/EC ratio has a median of 0.70, inside the expected 0.55–0.75. Conclusion: the 2023 file's charge balance is a consistency of construction and is not evidence of laboratory quality (§3.5). On the 2000–2021 file the balance is genuine — 127 of 753 computable analyses are suspect at 10 %.

**Level trends (Theil–Sen / Mann–Kendall), 2013–2021.** Of 415 stations in the database record, 331 are testable and 84 are not (fewer than 8 readings or under 3 years). **5 stations are declining, 20 recovering, 306 stable.** The fastest decline is 0.785 m/yr at Chapodia (Dumka). The median seasonal swing is 2.38 m. The result is undramatic, and that is the finding: there is no statewide level crisis in this record, and a station with too short a record is reported as such, never as stable.

**Chemistry trends, 2000–2021.** 244 of the platform's wells have two or more sampling years in the NWDP record; 175 clear the trend threshold for electrical conductivity, of which **13 are rising and 6 falling**, the rest without a significant trend. No health determinand can be trended, because none is in the file.

![Figure 6.1 [M] — The public map: districts coloured by the worst measured health determinand (uranium, nitrate or fluoride) against IS 10500:2012; 14 of 24 districts are High concern, driven by nitrate and fluoride, and grey (`Not tested`) is never green. Screenshot from the deployed portal, August 2026.](figures/fig_public_map.png)

## 6.2 Machine-learning model performance [V]

**Table 6.1 — v5 surrogate, GroupKFold(5) on scenario (18,000 rows, 900 scenarios, 23 polygons). Log-space R² of the P50 head; conformal coverage at α = 0.20; baselines on the same folds. Source: `ml_pipeline/ml/artifacts/metrics.json`, 21 Sep 2026.**

| Target | R²(log) P50 | R² (raw, P50) | MAE (P50, physical units) | Scenario coverage (gate ≥ 0.80) | Rows coverage | Mean baseline R²(log) | Ridge R²(log) | Stump R²(log) |
|---|---|---|---|---|---|---|---|---|
| `affected_area_ha` | **0.893** | 0.783 | 6.91 ha | **0.863** | 0.955 | −0.001 | 0.561 | 0.384 |
| `max_migration_distance_m` | **0.926** | 0.504 | 68.8 m | **0.878** | 0.952 | −0.002 | 0.773 | 0.515 |
| `compliance_conc` | **0.947** | −4.48 | 498 (mixed units) | **0.866** | 0.948 | −0.001 | 0.744 | 0.499 |
| `excursion_probability` (point) | R² 0.915 | — | MAE 0.049 | — | — | — | — | — |

The surrogate beats every baseline on every target in log space. The raw-unit R² of the compliance head is strongly negative because the pooled figure mixes ppb, mg/L and mBq/L and its denominator is set by the species mix, not model quality; the per-species figures are the ones to judge.

**Table 6.2 — Per-species R²(log) of the P50 head. Gate ≥ 0.60.**

| Target | Uranium | Sulphate | TDS | Radium-226 |
|---|---|---|---|---|
| `affected_area_ha` | 0.943 | 0.789 | 0.820 | 0.892 |
| `max_migration_distance_m` | 0.930 | 0.878 | 0.884 | **0.500 (fails)** |
| `compliance_conc` | 0.847 | 0.917 | 0.962 | **0.235 (fails)** |

**The radium gate failure, reported not moved.** Radium's migration label is 81.8 % exact zeros and its compliance label 95.8 % pinned at the 23 mBq/L background: a squared-error regressor on `log1p` cannot fit a point mass, and R² divides by a near-zero total sum of squares. The R17 β retrain left migration unchanged (0.516 → 0.515) and *worsened* compliance (0.431 → 0.227) because the wider prior moved a few more scenarios off the background pin; v5 is 0.500 / 0.235. The remedy — a zero-inflated two-stage head — is a new ML approach and was not authorised in the final month. The conformal bands on those cells still cover (0.927–0.951 rows in cross-validation; 0.94–0.965 field-resampled), and the analytical engine serves the authoritative radium value, so the failure is in the surrogate's point estimate, not in its uncertainty guarantee. If the gate is read as binding for release, the pipeline is not ready for radium.

**Leave-aquifer-out (23 polygons held out in turn).** R²(log) 0.890 / 0.921 / 0.941 for area / migration / compliance (raw P50 0.803 / 0.394 / −3.63; MAE 6.97 ha / 73.1 m / 447) — within a few hundredths of the scenario-grouped figures, so spatial generalisation to unseen aquifer polygons costs little.

**Table 6.3 — Conformal coverage per Mondrian cell (rows, cross-validation) and field-resampled coverage (120 scenarios pinned to the real flow and strike fields, held out; gate ≥ 0.80 on scenarios).**

| Target | Cross-validation, worst cell | Field-resampled scenarios | Field-resampled rows | Weakest field cell |
|---|---|---|---|---|
| `affected_area_ha` | fractured\|radium 0.933 | **0.885** PASS | 0.965 | fractured\|sulphate 0.944 |
| `max_migration_distance_m` | fractured\|radium 0.927 | **0.875** PASS | 0.949 | fractured\|TDS 0.874 |
| `compliance_conc` | porous\|radium 0.921 | **0.881** PASS | 0.950 | fractured\|sulphate 0.909 |

Band-order violations (P10 ≤ P50 ≤ P90) in the training set: 0 of 18,000. On-manifold physics laws hold on the surrogate's own output: area rises with Q_in at fixed Q_net (12.1 → 16.4 ha) and falls with bleed at fixed Q_in (16.8 → 15.4 ha).

**The transport kernel against an exact solution.** The second review round hypothesised, citing West et al. [10], that the Domenico product approximation could corrupt results by up to 80 %. The benchmark (`physics/exact_reference.py`, 240 parameter sets drawn from the training distribution; the reference collapses onto Ogata–Banks to 1.1 × 10⁻¹⁶ as W → ∞) disproved it and found the real error elsewhere:

**Table 6.4 — Centreline error of the transport kernel, (model − exact)/exact, August 2026.**

| Position | Product approximation only (full Ogata–Banks retained) | Truncated Ogata–Banks (as then served) p50 | Truncated, p5–p95 |
|---|---|---|---|
| x = 0.5 X_c | 0.00 % | −16.9 % | −39.8 % to −0.0 % |
| x = 1.0 X_c | 0.00 % | −22.4 % | −40.4 % to −5.3 % |
| x = 1.2 X_c | −0.10 % to 0.00 % | −24.3 % | −40.6 % to −11.3 % |
| Down-gradient reach (the migration metric) | — | −3.6 % | −6.5 % to −0.3 % |

The product decoupling costs nothing in this model's parameter box (α_T/α_L 0.01–0.10, sources 147–763 m wide); the dropped second Ogata–Banks term biased every concentration 17–42 % *low* — the opposite of the conservative posture the tool claims — while the threshold-crossing metrics moved only a few per cent. The term was restored (commit `5fb3fe6`) and the surrogate retrained on the exact kernel.

**Retraining history.** Migration R² moved 0.719 → 0.896 across the July label corrections (down-gradient travel, analytical centreline reach, Kd-dependent fractured front), then to 0.929 (v3), 0.927 (v4) and 0.926 (v5). The end-to-end audit on the report commit: **43 of 44 checks pass**; the one failure is the radium gate above.

## 6.3 Feature importance and explainability [V]

Mean absolute SHAP values on the P50 heads (`ml/artifacts/shap_top_*.json`, v5) rank the features the surrogate relies on:

**Table 6.5 — Top SHAP features per head (mean |SHAP|, log-space output).**

| Rank | Footprint area (P50) | Migration (P50) | Excursion probability |
|---|---|---|---|
| 1 | `source_conc_C0` 0.72 | `Xc_m` 1.33 | `Xc_m` 0.230 |
| 2 | `alpha_L` 0.31 | `source_conc_C0` 0.57 | `source_conc_C0` 0.051 |
| 3 | `wellfield_width_m` 0.25 | `residual_fraction` 0.31 | `residual_fraction` 0.028 |
| 4 | `residual_fraction` 0.22 | `is_radium_226_mbq_l` 0.29 | `is_tds_mg_l` 0.027 |
| 5 | `is_radium_226_mbq_l` 0.15 | `is_tds_mg_l` 0.22 | `D_T` 0.019 |
| 6 | `is_tds_mg_l` 0.14 | `containment_eta` 0.15 | `containment_eta` 0.015 |
| 7 | `Kd_L_kg` 0.13 | `is_sulfate_mg_l` 0.12 | `dimensionless_time_tau` 0.015 |
| 8 | `Xc_m` 0.11 | `background_conc_Cb` 0.09 | `background_conc_Cb` 0.014 |

The ranking agrees with the physics it should reflect. The analytical front position X_c — which already folds velocity, containment and the retarded clock — dominates migration and excursion probability, as it must (eq. 4.6); the source concentration and the wellfield width dominate the footprint, which is 76–97 % leach disc (§4.5); the realized restoration fraction and the species one-hots (radium and TDS at the two ends of the retardation range) carry the rest. Containment η appears with the expected sign. No spatial coordinate can appear, because none is a feature.

![Figure 6.2 [V] — SHAP feature attributions for the excursion-probability head (v5). Source: `ml/artifacts/shap_excursion_probability.png`.](figures/fig_shap_pex.png)

## 6.4 Spatial results at three reference sites [S]

**Table 6.6 — Reference-case runs at 20 years (operation 8 yr, Q_in 2,500 m³/day, bleed 2 %, W 300 m, no restoration, ring 100 m), analytical engine with the v5 surrogate band. Re-derived on the report date.**

| Pin (ore zone) | Species | K (m/day) | β | C₀ | Background | Footprint (ha) | Migration (m) | At the ring | p_ex | ML migration P10–P50–P90 (m) |
|---|---|---|---|---|---|---|---|---|---|---|
| Jaduguda deposit (86.347, 22.652), fractured, shear zone | uranium | 0.563 | 3.00 | 15,180 ppb | 1.0 ppb | 9.60 | **20.5** | 1.0 ppb | 0.00 | 2.7 – 18.6 – 100 |
| | sulphate | | | 1,624.5 mg/L | 227 | 11.25 | **73.1** | 244 mg/L | 0.27 | 3.5 – 42 – 467 |
| | TDS | | | 3,655.5 mg/L | 1,779 | 17.62 | **254** | 4,428 mg/L | 0.96 | 10.5 – 235 – 3,043 |
| | radium-226 | | | 1,706 mBq/L | 23 | 9.06 | 0.6 | 23 mBq/L | 0.00 | 0.0 – 0.5 – 2.3 |
| Mid-belt (86.25, 22.63), fractured, belt tier | uranium | 0.429 | 2.00 | 7,590 ppb | 1.0 | 12.53 | 19.5 | 1.0 | 0.00 | 2.6 – 16 – 80 |
| | sulphate | | | 1,624.5 | 46 | 13.66 | 60.7 | 63 | 0.10 | 4.3 – 36 – 333 |
| | TDS | | | 3,655.5 | 669 | 17.94 | 171 | 3,243 | 0.79 | 9.0 – 133 – 1,752 |
| | radium-226 | | | 512 | 23 | 0.00 | 0.0 | 23 | 0.00 | 0 – 0 – 0.4 |
| Ranchi (85.33, 23.36), fractured, non-ore | uranium (suppressed) | 0.094 | 2.00 | 5 (trace) | 0.65 | 0.00 | 0.0 | 0.65 | 0.00 | surrogate bypassed |
| | sulphate | | | 1,624.5 | 31 | 12.66 | 25.3 | 31 | 0.00 | 1.8 – 19 – 142 |
| | TDS | | | 3,655.5 | 463 | 13.64 | 55.6 | 639 | 0.12 | 3.1 – 44 – 553 |
| | radium-226 (suppressed) | | | 23 | 23 | 0.00 | 0.0 | 23 | 0.00 | — |

Resolved hydrogeology at Jaduguda: fractured regime, gradient 0.00205 (flow field), mobile porosity 0.0075 and productive thickness 150 m (shear-zone override), K 0.563 m/day at 150 m after depth decay, R_eff 271 (uranium), 17.3 (sulphate), 4.0 (TDS), ~3,500 (radium). Three readings of this table: the **ordering** uranium ≪ sulphate < TDS in extent, set by R_eff, is the physical reason NUREG rejects uranium as an excursion indicator, and the engine reproduces it without being told; at a **non-ore pin** the uranium source is suppressed and no uranium plume is drawn, while the lixiviant reagents still spread (a lixiviant carries sulphate wherever it is injected); and the **P90 band** for TDS at Jaduguda reaches three kilometres, which is what the `possible_reach` alert exists to tell.

Extrapolation flags: none at 20 years and 0–10 years of restoration; beyond those the sweep chart draws hollow points and the response lists the offending input.

![Figure 6.3 [S] — The console result panel for a Jaduguda-belt pin (uranium, 20 yr, 3 yr sweep), July 2026 build (β = 10, pre-R17): each metric shows the analytical value as the authority with the surrogate's band beside it, the "analytical is the authority" statement, and the NUREG 2-of-3 panel. The migration reads 11.7 m here; the same pin reads ~20 m after the R17 β correction (Table 6.7).](figures/fig_console_result_july.png)

## 6.5 Plume simulation and temporal evolution — the Jaduguda case study [S]

**The registered site.** The site registered on the deployed system sits at 86.36° E 22.65° N, 0.35 km outside the deposit polygon — a *belt* pin (uranium C₀ 14,294.5 ppb: 0.30 × the deposit value ramped over the 3 km taper) — with Q_in 1,500 m³/day, bleed 2 %, 8 years of operation, W 300 m, ore depth 150 m and thickness 20 m, ring 100 m.

**Table 6.7 — Lifecycle at the registered Jaduguda site, no restoration, analytical engine (values at each horizon; the NUREG panel is judged on Cl / TDS / SO₄ at the ring).**

| Year | Phase | Uranium source (ppb) | Footprint (ha) | Uranium migration (m) | Uranium at ring (ppb) | Shallow-aquifer index | Excursion declared | Indicators over UCL |
|---|---|---|---|---|---|---|---|---|
| 0 | operation | 14,294 | 0.00 | 0.0 | 1.0 | 0.05 | no | — |
| 4 | operation | 14,294 | 8.13 | 11.1 | 1.0 | 0.16 | no | — |
| 8 | closure | 14,294 | 8.65 | 12.5 | 1.0 | 0.28 | no | — |
| 12 | post-closure | 13,033 | 8.82 | 16.6 | 1.0 | 0.39 | **yes** | Cl, TDS |
| 16 | post-closure | 11,882 | 8.82 | 19.9 | 1.0 | 0.51 | yes | Cl, TDS |
| 20 | post-closure | 10,833 | 8.99 | 22.7 | 1.0 | 0.62 | yes | Cl, TDS |
| 30 | post-closure (extrapolating) | 8,598 | 9.16 | 28.5 | 1.0 | 0.91 | yes | Cl, TDS, SO₄ |
| 50 | post-closure (extrapolating) | 5,417 | 9.51 | 37.8 | 1.0 | 1.00 | yes | Cl, TDS, SO₄ |

The source is held at strength during injection (that is what injection is), then declines under the 30-year passive flush; the footprint grows during operation and barely afterwards (it is the leach disc); uranium migration grows after closure once containment stops but never reaches the 100 m ring within 50 years (R_eff ≈ 271); the ring nevertheless reads an excursion from the 12-year frame, because chloride (862 vs baseline 192 mg/L at 20 yr) and TDS (4,605 vs 1,779) have arrived — the conservative reagents warn first, as NUREG intends, and sulphate joins the panel by year 30. First exceedance at the ring by species: TDS between the 8- and 12-year frames, sulphate between 20 and 30, uranium never.

**The restoration sweep.** Holding the horizon at 20 years and varying the sweep length: 0 yr → migration 26.4 m at the registered site, excursion declared; 6 yr → 4.2 m, one indicator over (chloride), not declared; 12 yr and beyond → 0 m, source at its ~290 ppb rebound floor, not declared, flagged as extrapolating beyond the trained 10 years. "Zero migration" here means nowhere beyond the wellfield edge is above the 30 ppb limit, not that nothing moved.

**Table 6.8 — Before and after the R17 β correction (default operation, 20 yr, analytical engine; ML migration band from the v3 and v4 surrogates; `ml_pipeline/outputs/snapshot_{pre,post}_r17.json`).**

| Pin · species | β | Migration (m) | Footprint (ha) | At the ring | ML band (m) |
|---|---|---|---|---|---|
| Jaduguda · uranium | 10 → 3.0 | 10.6 → **20.5** | 9.3 → 9.6 | 1 → 1 ppb | 2–61 → 2–102 |
| Jaduguda · sulphate | 10 → 3.0 | 31.7 → **73.1** | 10.0 → 11.3 | 227 → 244 mg/L | 2–189 → 3–468 |
| Jaduguda · TDS | 10 → 3.0 | 114 → **254** | 12.7 → 17.6 | 2,253 → 4,428 mg/L | 5–848 → 15–2,136 |
| Jaduguda · radium | 10 → 3.0 | 0.3 → 0.6 | 9.1 → 9.1 | 23 → 23 mBq/L | 0–1 → 0–2 |
| Mid-belt · sulphate | 10 → 2.0 | 19.0 → 60.7 | 12.4 → 13.7 | 46 → 63 mg/L | 2–114 → 4–345 |
| Ranchi · sulphate | 10 → 2.0 | 8.8 → 25.3 | 12.3 → 12.7 | 31 → 31 mg/L | 1–42 → 2–172 |

Uranium roughly doubled and stayed within tens of metres (R_m ≈ 90 still dominates β·R_m); the reagents moved two to three times as far and their bands reached hundreds of metres. The published Jaduguda advisory's footprint is unchanged in kind — block intersection is done on the central contour, so the alert count did not inflate — and the P90 envelope now raises a separate `possible_reach` alert. The v5 retrain (background floor) left these unrestored 20-year values unchanged and widened the TDS P90 to 3,043 m.

## 6.6 Vertical (2.5-D) screening results [S]

At the registered site (ore top at 140 m, Layer-1 base at 20 m from the East Singhbhum profile, separation 120 m, water table 1.6 m): the dispersive pathway contributes 0.00, the advective-leakage pathway 0.60 (breakthrough fraction 0.602 at 20 years) and the wellbore base rate 0.05, for a combined index of **0.62** — band *high*, dominant pathway advective leakage — with a **duty-cycle breakthrough of 18.7 years** against a dry-season end member of 6.8 years and a wet-season end member of "not expected" (the pathway is open about 58 % of the year). Before the R11 correction the headline read 54.4 years at the mean gradient, outside its own seasonal band and understating the hazard by about 1.9×. The concentration reaching Layer 1 by dispersion is 0.0 — the index is a *pathway-existence* screen, not a concentration.

**Why no 3-D volume is presented.** Table 6.9 is the data the question turns on.

**Table 6.9 — What vertical information exists (from the pre-report audit, §4.1).**

| Quantity | Present? | Resolution | Usable for a vertical axis? |
|---|---|---|---|
| Well depth / screen interval of the chemistry wells | **No** | — | the decisive absence |
| Depth to water | yes, 9,583 readings | point, shallow phreatic | water-table surface only |
| Hydraulic head at depth | **No** | — | the vertical gradient is bracketed by the monsoon swing, not measured |
| Geological layering | yes | district (24 rows) | a 3-layer conceptual column |
| Ore depth / thickness | partly | per deposit, 60–250 m | point estimates |
| K with depth | modelled | a law | assumption |
| Contaminant concentration | model output only | — | no measured plume, no depth |

Any voxel volume rendered from this would be a picture of the erf factor in `vertical_attenuation` presented with the visual authority of a measurement. The system stays 2.5-D, draws the column to scale on the report page, and says so.

## 6.7 Vulnerability assessment [S + M]

**Measured bands [M].** With the three-determinand rule, 14 of 24 districts are *High concern*, several from wells where uranium is essentially absent (Lohardaga: 0.5 ppb uranium, 48 mg/L nitrate; Gumla: 2.1 and 53). Under the earlier uranium-only rule no district could ever have reached High concern, because the statewide maximum is 28.5 ppb against a 30 ppb limit — the public map could not show a high-concern district at all, and the resident's own page disagreed with it for a day (R15). The three Singhbhum districts band on nitrate and fluoride with uranium listed under `untested_health`; every band lists arsenic and iron there unconditionally.

**Modelled excursion and vertical bands [S].** At the Jaduguda reference pin, p_ex is 0.00 for uranium, 0.27 for sulphate and 0.96 for TDS at 20 years; the NUREG panel declares from the 12-year frame; the vertical band is *high* (§6.6). At the non-ore Ranchi pin, uranium is suppressed and the only bands drawn are for the reagents.

**Where the two meet.** The published Jaduguda screening's footprint intersects blocks of East Singhbhum whose measured band is *Low concern* on nitrate and fluoride and *Not tested* for uranium — the product shows both, labelled, and never lets the modelled result colour the measured band.

## 6.8 The alert system [M + S]

**Records on the local seed (report commit).** The measured-exceedance scan raises **53** alerts from the 2023 record: **3 critical** — Biru (Simdega, nitrate 121 mg/L, 2.7× the limit), Lowadih (Ranchi, nitrate 99 mg/L, 2.2×) and Gidhaur (Chatra, over both the nitrate and the fluoride limits) — **29 alert** (the remaining wells above a permissible or no-relaxation limit) and **21 warning** (fluoride between 1.0 and 1.5 mg/L). Before R14 the same scan matched zero rows every time it ran (it queried `uranium_ppb > 30`), and before R17 the 21 warning wells were unreachable (it selected on the permissible limit only).

**Records on the deployed database (21 September 2026, Administration screen):** 55 alerts raised; 4 residents following 7 blocks; email delivery configured that day through the Brevo relay after three connectivity findings — the hosting tier silently drops outbound port 587 (a 20-second timeout with nothing in the relay's log; port 2525 connects), the relay's login is a machine identifier rather than the account address, and the relay's IP allow-list rejected the host's changing egress address until it was opened — and one defect found while doing it: a `failed` delivery was permanent and never retried, because `pending_deliveries` excluded any pair with an existing row and the insert was `ON CONFLICT DO NOTHING` (fixed and pinned, commit `47ab713`).

**Table 6.10 — One alert per basis, as the seven-field record (values from the local seed; the modelled record from the published Jaduguda screening).**

| Field | Observed: Biru, Simdega | Modelled: Jaduguda screening, an East Singhbhum block |
|---|---|---|
| `basis` | observed | modelled |
| `driver` | nitrate 121 mg/L; limit 45 mg/L (no relaxation); 2.7× | uranium; modelled P50 footprint intersects the block; ring p_ex 0.00 at the run's horizon |
| `where` | Biru block, Simdega district; well "Biru" | block, East Singhbhum district; footprint ~9 ha |
| `tier` | **critical** (≥ 2× — project-defined rule, labelled) | **notice** (never critical: `ck_modelled_never_critical`) |
| `confidence` | laboratory result, sampled 2023 (year-only date); charge balance within ±3.2 % (consistency of construction, so not independent) | analytical P50 20.5 m; surrogate band 2.7–100 m; extrapolation: none; nearest chemistry well and its distance |
| `next_action` | re-sample; nitrate is not removed by boiling (boiling concentrates it); test for the un-analysed determinands (Fe, As, Mn); consider an alternate supply | no monitoring well lies inside the P90 reach — none exists to sample; the ring is first predicted to exceed on the indicator panel at the 12-year frame |
| `what_happened` | a government monitoring well in this block was tested and found nitrate 2.7 times the drinking-water limit | a hypothetical screening was published for a block the modelled footprint touches; no mine exists |

**Kinds that fire on nobody, reported as results.** `aquifer_pathway` adds no block at any registered site: shallow groundwater in the state's hard rock moves ~1.5 m/yr (phyllite: K 0.08 m/day, φ 0.04, i 0.0021 → 27 m in 20 years), so every block within the advective reach was already told by the footprint. `aquifer_breach_due` correctly fires on nobody: the two originally published advisories predate vertical-screening persistence, and a Potka run sits at 22 elapsed years against a 29.4-year modelled breakthrough — due in 7.4 years, reported rather than raised.

![Figure 6.4 [S] — The ISR site report for the published Jaduguda screening as a resident or officer downloads it (deployed portal, August 2026; pre-R17 extent).](figures/fig_site_report.png)

## 6.9 Data gaps, monitoring recommendation and sensitivity [M + V]

**The gap matrix, statewide [M]:** 264 blocks; **53 blocks with no monitoring well**; **83 blocks with no level station**; **55 wells never analysed for uranium**; **397 of 397 wells with a single sample**, all stale by the record's own age (2023).

**The ranking [M].** Table 6.11 is the top of the observation-based ranking re-derived from the local database on the report date. The scores sit in a narrow band (61.8–65.2 of 100) because the top blocks share the same two saturated factors; the ordering within the band is the tie-break by area. The finding is not the numbers but the geography: **every one of the top 25 blocks is in East Singhbhum, West Singhbhum, Saraikela-Kharsawan or neighbouring Khunti** — the uranium belt itself is the least-observed part of the state for the one contaminant the tool screens for. Sixteen of the 25 have no well at all; the other nine have wells that were sampled and never analysed for uranium — the cheapest gap in the list to close, because the wells and the sampling round already exist.

**Table 6.11 — Observation-based monitoring priority, top 25 of 264 blocks (weights 30 / 30 / 20 / 15 / 5, a stated policy; area is the tie-break).**

| Rank | Block | District | Score | Wells | U tests | km to nearest U-tested well | Area (km²) |
|---|---|---|---|---|---|---|---|
| 1 | Ghatshila | East Singhbhum | 65.2 | 1 | 0 | 77.7 | 345 |
| 2 | Manoharpur | West Singhbhum | 65.0 | 0 | 0 | 46.1 | 966 |
| 3 | Tonto | West Singhbhum | 65.0 | 0 | 0 | 68.2 | 633 |
| 4 | Goilkera | West Singhbhum | 65.0 | 0 | 0 | 45.5 | 577 |
| 5 | Manjhari | West Singhbhum | 65.0 | 0 | 0 | 74.4 | 319 |
| 6 | Dumaria | East Singhbhum | 65.0 | 0 | 0 | 86.0 | 318 |
| 7 | Anandpur | West Singhbhum | 65.0 | 0 | 0 | 28.8 | 317 |
| 8 | Kumardungi | West Singhbhum | 65.0 | 0 | 0 | 90.2 | 296 |
| 9 | Majhgaon | West Singhbhum | 65.0 | 0 | 0 | 103.4 | 284 |
| 10 | Boram | East Singhbhum | 65.0 | 0 | 0 | 46.5 | 264 |
| 11 | Patamda | East Singhbhum | 65.0 | 0 | 0 | 60.1 | 246 |
| 12 | Sonua | West Singhbhum | 65.0 | 0 | 0 | 44.4 | 224 |
| 13 | Gurbandha | East Singhbhum | 65.0 | 0 | 0 | 102.5 | 222 |
| 14 | Potka | East Singhbhum | 64.8 | 4 | 0 | 60.8 | 615 |
| 15 | Gudri | West Singhbhum | 63.6 | 0 | 0 | 22.7 | 472 |
| 16 | Chakradharpur | West Singhbhum | 63.2 | 1 | 0 | 36.8 | 379 |
| 17 | Kukru | Saraikela-Kharsawan | 62.8 | 0 | 0 | 21.4 | 139 |
| 18 | Hat Gamharia | West Singhbhum | 62.7 | 1 | 0 | 83.0 | 293 |
| 19 | Saraikela | Saraikela-Kharsawan | 62.3 | 1 | 0 | 28.6 | 249 |
| 20 | Musabani | East Singhbhum | 62.1 | 2 | 0 | 77.4 | 249 |
| 21 | Noamundi | West Singhbhum | 61.9 | 3 | 0 | 70.2 | 645 |
| 22 | Erki (Tamar II) | Khunti | 61.8 | 0 | 0 | 19.7 | 519 |
| 23 | Kuchai | Saraikela-Kharsawan | 61.8 | 0 | 0 | 19.7 | 389 |
| 24 | Tantnagar | West Singhbhum | 61.8 | 1 | 0 | 63.4 | 210 |
| 25 | Chaibasa | West Singhbhum | 61.8 | 1 | 0 | 48.9 | 209 |

**Global sensitivity [V].** Table 6.12 gives the Sobol total-order indices (S_T) of the three plan-view outputs to the thirteen inputs at the three reference sites; the full first-order and one-at-a-time tables are Appendix J and the figures in `ml/artifacts/sensitivity_*.png`. Group A is the registered ungrounded constants; group B the resolved hydrogeology with its Monte-Carlo ranges.

**Table 6.12 — Sobol total-order indices, top inputs per output (Saltelli N = 256; 20 yr, 8 yr operation, 3 yr sweep; `ml/artifacts/sensitivity.json`).**

| Site · species | Output | 1st | 2nd | 3rd | 4th | Share carried by group A |
|---|---|---|---|---|---|---|
| Jaduguda · U | migration | **K 0.42** | **β 0.21** | gradient 0.16 | ω 0.10 | 0.32 |
| Jaduguda · U | footprint | SOURCE_BV_REF 0.27 | SOURCE_BV_GAIN 0.22 | β 0.16 | gradient 0.15 | 0.64 |
| Jaduguda · U | ring concentration | K 0.53 | β 0.45 | gradient 0.33 | ω 0.21 | 0.37 |
| Jaduguda · SO₄ | migration | K 0.39 | β 0.24 | Kd 0.17 | gradient 0.13 | 0.28 |
| Jaduguda · SO₄ | footprint | K 0.42 | β 0.21 | gradient 0.17 | Kd 0.15 | 0.34 |
| Jaduguda · SO₄ | ring concentration | K 0.71 | gradient 0.33 | β 0.32 | Kd 0.31 | 0.22 |
| Belt · U | migration | **β 0.29** | K 0.26 | ω 0.18 | gradient 0.14 | 0.49 |
| Belt · U | footprint | SOURCE_BV_GAIN 0.55 | SOURCE_BV_REF 0.37 | gradient 0.07 | K 0.06 | 0.84 |
| Belt · U | ring concentration | K 0.65 | Kd 0.27 | β 0.27 | — | — |
| Belt · SO₄ | migration | β 0.34 | K 0.25 | Kd 0.23 | — | — |
| Ranchi · U | all three | **degenerate** — the source is suppressed at a non-ore pin; the output is constant over the whole design and the indices are undefined, reported as such | | | | |
| Ranchi · SO₄ | footprint | C₀ 0.78 | SOURCE_BV_GAIN 0.25 | SOURCE_BV_REF 0.10 | — | — |

The pattern: hydraulic conductivity first, then β, then the gradient and Kd for the transport outputs; the leach-disc growth constants govern the footprint area (which is the disc); the fracture aperture, D_e and — except for belt uranium — ω contribute approximately nothing at 20 years. Of the parameters that decide the extent, K is a measured polygon value depth-decayed by a law, and β is derived from typical porosities; **neither is a local measurement at ore depth in the shear zone**. The registered ungrounded constants carry 22–49 % of the migration variance, almost all of it β.

![Figure 6.5 [V] — Sobol total-order indices for uranium at the Jaduguda deposit pin, three outputs (`ml/artifacts/sensitivity_jaduguda_deposit_uranium.png`).](figures/fig_sens_jaduguda_uranium.png)

![Figure 6.6 [V] — The same for uranium at the belt pin, where β overtakes K for migration (`ml/artifacts/sensitivity_belt_point_uranium.png`).](figures/fig_sens_belt_uranium.png)

## 6.10 The prototype system

**Screens per role (final build).** All 22 screens exist; each role sees a filtered set. `admin`: everything, including Administration (accounts, dataset sync and restore points, model operations, the alert scans and delivery panel, tier counts), Datasets, Ingest and Audit. `regulator`: the review queue and decisions, plus the console, report, compare, scenarios, publications and data screens. `analyst`: console, report, compare, scenarios, publications (propose), field data, water quality, groundwater, data & gaps, network plan, methods. `field_officer`: field data (submit, withdraw), plus reads. `citizen`: front page, my area, the citizen map (tap anywhere), alerts, published screenings, methods — nothing with a coordinate or a model internal.

**Authorization sweep.** The generated matrix covers **152 endpoints × 5 roles** (`docs/roles.md`); the test that regenerates it fails on drift. Row-level security is verified on the live connection as `jaldrishti_app` (no superuser, no bypass); the `alerts` table carries SELECT, INSERT and UPDATE policies; the audit log carries no UPDATE or DELETE policy for any role. The security-hardening tests measure rather than assert: 10 logins accepted, then 429s.

**The publication workflow, end to end.** An analyst runs the engine at a registered site and saves the run (runs are ephemeral by default; saving is a deliberate act); proposes a screening from the completed run; the single admin decides; publication raises `published_screening` alerts for every block the central footprint touches and `possible_reach` for the P90 envelope, in its own session under the system context; delivery emails each subscriber; the resident sees the advisory, its operating parameters, the modelled spread and whether shallow water was expected to be reached — but never the coordinate. A withdrawn advisory is withdrawn everywhere, including the email channel.

![Figure 6.7 — The deployed front page; every figure is read live from the database (August 2026).](figures/fig_front_page.png)

## 6.11 Performance and deployment

| Measure | Value | Basis |
|---|---|---|
| Analytical engine, one evaluation with the 48-draw Monte Carlo | ~0.2 s locally; ~4 s on the Render free tier | `PROJECT_FREEZE.md` §0; the lifecycle endpoint issues 8–15 evaluations per request and was split per species after a 48-evaluation request was dropped by the gateway in production |
| Bake (900 scenarios × 48 draws) | ~1.5–2 h on the development machine | 21 Sep 2026 run: 11:52 → 13:26 including train, SHAP, the 120-scenario batch, gates, sensitivity and audit |
| Surrogate training | 202 s | v5 trainer log |
| Sensitivity (N = 256, 3 sites × 2 species) | ~2.5 min (≈ 22,000 evaluations) | v5 pipeline log |
| Engine test suite | 373 tests, 32–113 s | report commit |
| Backend test suite (real PostGIS) | 522 tests, 10–17 min | report commit |
| Deployed API cold start | 53 s (free tier sleeps) | probe, 20 Sep 2026 |
| Repository | 173 commits; 26 migrations; 152 endpoints; 22 screens | report commit |

The deployed API runs whichever commit was last deployed; `docs/PROJECT_FREEZE.md` §8 lists the steps that bring the deployment to the report commit (migrate to `0026`, deploy the v5 artifacts, rebuild alert explanations once, re-run one simulation per published site so the advisory has frames).


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# 7. Discussion

## 7.1 The research questions, answered

**RQ1 — Can a physics-informed surrogate reproduce the engine with calibrated uncertainty, and what does its accuracy mean?** Yes, and the meaning is narrow. Under scenario-grouped cross-validation the P50 heads reproduce the engine with R²(log) 0.893 / 0.926 / 0.947, beat ridge and stump baselines fitted on the same features in the same folds (0.56–0.77 and 0.38–0.52), lose only a few hundredths when whole aquifer polygons are held out, and hold the 80 % conformal guarantee on a batch pinned to the real flow and strike fields (0.875–0.885 scenario coverage). Two radium cells fail the project's own R²(log) gate because their labels are point masses; the band on those cells still covers, the engine serves the value, and the failure is stated rather than moved. The accuracy is **fidelity to the engine**: the surrogate was trained on the engine's output, cannot exceed it, and has never been compared with a real plume, because none exists. Its contribution is the band, the speed, and the health signal — not a better answer than the physics.

**RQ2 — Which parameters control the extent, and are they measured locally?** The sensitivity analysis is the backbone of the answer. For migration and ring concentration at the Jaduguda deposit, hydraulic conductivity carries the largest share of the variance (S_T 0.42–0.71), the dual-porosity capacity ratio β the second (0.21–0.45), then the gradient and Kd; at the belt pin β overtakes K for uranium. The footprint area is governed by the leach-disc growth constants, which are scenario assumptions. The fracture aperture, matrix diffusion coefficient and (mostly) transfer rate contribute nothing at 20 years. Of the two parameters that decide the plume, K is a CGWB polygon value for the shallow aquifer, blended and depth-decayed by a law calibrated on NAQUIM fracture depths; β is derived from lithology-typical porosities. **Neither is a measurement at ore depth in the Singhbhum Shear Zone**, and the literature search of July–August 2026 found that none has been published: the shear-zone literature is structural and economic geology, not hydrogeology. A single tracer or packer test in the belt would retire more uncertainty than any further modelling.

**RQ3 — What does the measured record say against IS 10500, and what does it not say?** It says that uranium — the contaminant the project exists to screen for — is within its limit at every one of the 342 wells where it was analysed, and that the health exceedances in Jharkhand's groundwater today are nitrate (22 wells, up to 2.7× the limit) and fluoride (32 above acceptable, 11 above permissible), in 14 of 24 districts. It does not say anything about arsenic, iron or manganese, which were never analysed anywhere in the state despite being named in the proposal; it does not say anything about uranium in the three Singhbhum districts, where 55 wells were sampled and not analysed for it; it does not say whether any of this is getting better or worse, because there is one sample per well; and its charge balance does not vouch for the laboratory, because sodium was computed by difference. The 2000–2021 record adds a time axis for the general chemistry (EC rising at 13 and falling at 6 of 175 testable wells) and none for any health determinand.

**RQ4 — Where are the monitoring gaps, and how should a network be prioritised?** The gaps are: 53 blocks with no well, 83 with no level station, 55 wells un-analysed for uranium, every well single-sampled, no well depths, and three health determinands never measured. Prioritised by observation rather than by predicted risk, **the top 25 of 264 blocks all lie in the uranium belt** — East and West Singhbhum, Saraikela-Kharsawan and Khunti — sixteen of them with no well at all and nine with wells that were sampled and never analysed for uranium. The recommendation that follows is concrete and cheap in its first step: analyse the existing Singhbhum samples for uranium; add Fe, Mn and As to the panel statewide; record well depths and screen intervals; repeat sampling at the same wells so that a trend and a control limit become possible; and, for the model, a tracer or packer test in the shear zone and deep piezometry under the belt.

**RQ5 — Can a threshold → alert → notification loop be closed on the manual record, and what does it take?** Yes, and it took more than building it. On the report commit, 53 measured alerts in three tiers exist on the seed, and on the deployed system alerts are emailed to residents who registered with a home block. Closing the loop required finding that publication had never raised an alert (the RLS context dies at COMMIT), that the exceedance scan had matched zero rows for months (it queried the one determinand that never exceeds), that the rate limiter enforced nothing (the middleware was never installed), that the upsert needed an UPDATE policy the table lacked, and — on the last day — that a failed delivery was never retried. Each control looked correct in the code and in the logs; only measuring (counting rows, counting 429s, watching a relay's log) found it. The loop is closed on a manual record; the sensing half of a CPS does not exist and was not faked.

## 7.2 What the results mean for the objectives, and why the methodology changed

**O1 is met for the ISR source term under stated assumptions, and not met for measured-quality forecasting.** The proposal's D1 — "forecast groundwater quality trends" — was never achievable on a record with one sample per well, and the three tabular pipelines of March–May 2026 that tried to approximate it were, on inspection, learning either cross-sectional chemistry or their own synthetic generator. The June audit's finding is worth restating because it is the most important methodological lesson of the project: the May pipeline reported R²(log) ≈ 0.69 on "real-only" rows, and that number was true, but the real rows carried no distance from any source and no time since injection — both were median-imputed constants — so the model's dominant feature (distance, 70 % importance) was inert on every real row and the score measured the prediction of ambient background uranium. The uranium-versus-distance relationship existed only in the synthetic generator, where distance was drawn at random and the label computed from it. A model that cannot be extended to draw where contamination goes cannot meet O1 for an ISR source, and the decision to replace rather than refine it — deleting several months of work — was the hardest of the project. What replaced it answers the question the proposal actually asks (where, how far, how fast, with what uncertainty), on real hydrogeology, with an accuracy figure whose meaning is stated.

**O2 is met in the application and, with this report, as a document.** The block ranking, the gap matrix, the `Not tested` band, the assumption register and the sensitivity analysis are the data-gap analysis; §6.9 and §7.1 (RQ4) are the written recommendation the proposal's D2 asks for.

**O3 is met and deployed.** The portal, its five roles, the publication workflow, the alerts and the delivery are live, and the Project Completion Matrix (§8) gives each deliverable its status honestly.

## 7.3 Why the surrogate behaves as it does

The SHAP ranking (§6.3) is the physics in another form. The analytical front position X_c dominates migration and excursion probability because eq. 4.6 already folds velocity, containment and the retarded clock into it — the surrogate is largely learning to reproduce a quantity the engine hands it, which is the point of a physics-informed feature set. The source concentration and wellfield width dominate the footprint because the footprint is mostly the leach disc. The species one-hots for radium and TDS sit at the two ends of the retardation range and act as the learner's switch between "immobile" and "conservative". Where the surrogate extrapolates — beyond 20 years, beyond 10 years of restoration, below the trained K floor at a deep pin — the engine still serves, the response lists the input, and the chart draws the point hollow; the tree quantisation seams (17 % in migration across a half-year of restoration) sit inside the band at every probed location.

## 7.4 Spatial and temporal patterns: measured versus modelled

The **measured** geography is nitrate and fluoride in the plateau districts — Simdega, Ranchi, Latehar, Garhwa, Chatra, Godda, Koderma — and hard water almost everywhere; the belt is undocumented. The **modelled** pattern is the opposite kind of statement: contained plumes in fractured rock, with uranium held within tens of metres by matrix capacity (R_eff ≈ 270) while the lixiviant reagents outrun it by an order of magnitude — 254 m for TDS at Jaduguda at 20 years, with a P90 of three kilometres. That ordering is why the ring "reads an excursion" while uranium at the ring is background: the NUREG indicator logic, reproduced by the engine independently and then adopted as the criterion. Temporally, the source is flat during injection, the footprint grows and then barely changes, migration grows after closure once containment stops, and the first ring exceedance is a reagent's, between the 8- and 12-year frames at the registered site. The vertical screening's *high* band with an 18.7-year duty-cycle breakthrough is the one modelled result that would matter most if the scenario were real — and it rests on an upward gradient bracketed by the monsoon swing rather than measured.

## 7.5 Strengths, failures and the uncertainty no band covers

The strengths are the data skeleton — where the water flows, what rock it flows through, where the ore is, what the background chemistry is, what real restorations achieved — and the instrumentation: exact-solution benchmarks, physics laws tested on labels, grouped and spatial cross-validation, a serving-distribution coverage gate, a generated metrics block, a generated authorization matrix, a limitations register kept to the last commit. The failures are on the record and are part of the result: a migration metric that for weeks reported the distance to the corner of a numerical artefact box, certified by a QA sweep as physics; a fractured front that was species-blind; a restoration credit applied before the sweep had run; a leach disc drawn before injection began; a redox term charged twice; a truncated kernel biasing concentrations 17–42 % low; a K-support clamp that set the size of a physical discontinuity; a β served at three times what the model's own porosities implied; a source that could read cleaner than the water flushing it. Each was found by measurement, fixed, and pinned by a test — and each is the kind of defect that survives review by reading.

The uncertainty no band covers is structural. The conformal 80 % is a guarantee about the parameter draws inside the model; it says nothing about whether an equivalent-porous-medium model with a dual-porosity overlay describes a shear zone, whether a Texas alkaline source term transfers to uraninite with sulphides, or whether the fractured-rock coefficients — all foreign analogues — are within an order of magnitude of Singhbhum's. The β table in §5.1 shows the shape of that uncertainty: the same run reads 20 m at the derived β = 3, 61 m at β = 0.5 and 938 m at β = 0. The band expresses "the matrix may store four times more or four times less than the porosities imply"; it does not express "the model may be the wrong model". Nothing in this project can, and the report says so wherever a modelled number appears.

## 7.6 Comparison with the literature

The engine's ordering of species by mobility — TDS and chloride first, sulphate next, uranium far behind, radium immobile — is the ordering the ISR regulatory literature encodes in its choice of indicators [12], and the Jaduguda radium result (0.6 m at 20 years) is consistent with the BARC finding that radium does not migrate from the Jaduguda tailings pond [24]; the earlier version of that check, run in a porous regime no deposit pin uses, is recorded as a retraction. The exact-solution benchmark places the project in the regime West et al. [10] describe as benign — narrow transverse spreading relative to a wide source — and the restored full Ogata–Banks term removes the one bias the benchmark found. The attenuation ceiling and the restoration floor are the two places where a single field study each — Reimus et al. [18] and Gallegos et al. [19] — anchors a parameter, and both are Wyoming sandstone. Against the Indian groundwater-ML literature [58], [59] the comparison is one of data, not of algorithm: those studies have the multi-year, multi-station records that a trend model needs; this one does not, and built a different kind of model for that reason.

## 7.7 Implications for monitoring programmes (deliverable D2)

The recommendations, in the order a programme could act on them:

1. **Analyse the 55 existing Singhbhum samples for uranium.** The wells, the sampling round and the laboratory exist; the belt is the one place the tool screens for uranium and the one place with no result.
2. **Add iron, manganese and arsenic to the statewide panel.** Zero of 397 wells carry any of them; the alert scanner already reads them.
3. **Repeat sampling at the same wells** — even annually — so that a per-well baseline, a control limit of the mean-plus-kσ kind, and a rate-of-change alert become possible; the platform's 2000–2021 ingest path and Theil–Sen module are ready for it.
4. **Record well depths and screen intervals** with every sample. This is the single absence that keeps the system 2.5-D.
5. **Fill the 53 blocks with no well and the 83 with no level station**, starting from the ranking of Table 6.11.
6. **For the model: a tracer or packer test in the Singhbhum Shear Zone and deep piezometry under the belt.** These retire the two parameters — β and the upward gradient — that the sensitivity analysis and the vertical screening say matter most.

# 8. Deliverables and Project Completion Matrix

Status vocabulary (from the freeze record): **FIV** fully implemented and validated (internal and external) · **IIV** implemented, internally validated only · **FP** functional prototype · **SH** simulated / hypothetical · **CO** conceptual · **NA-D** not achieved because of data limitations.

**Table 8.1 — Project Completion Matrix (report commit `476a4a9`).**

| Objective / deliverable | Proposed | Implemented | Validated | Final status | Evidence | Remaining limitation |
|---|---|---|---|---|---|---|
| **O1 / D1 — ISR-source prediction** | RF/SVM/GB/ANN on measured data | physics-informed transport engine + v5 XGBoost surrogate with conformal bands; statewide inputs; β porosity-derived | 373 engine tests; exact-solution benchmark; GroupKFold + leave-aquifer-out; scenario coverage 0.86–0.88; field-resampled 0.875–0.885; audit 43/44 | **IIV / SH** | `ml_pipeline/`, `model_card.json` v5, `metrics.json` | no real plume to validate against; radium fails its gate; β not measured |
| **O1 / D1 — measured-quality trend forecasting** | forecast trends | IS 10500 assessment of the 2023 record; Theil–Sen on the 2000–2021 general chemistry; no forecasting | 50 water-quality tests incl. 8 for the history | **NA-D** (health determinands) / **FP** (general chemistry) | `services/water_quality.py`, `chemistry_history.py` | the only multi-year record has no F, NO₃, U, Fe, As |
| **O1 — aquifer vulnerability** | vulnerability assessment | source-specific: 2.5-D vertical screening, excursion probability, ring concentration, first-exceedance frames | engine tests incl. seasonal/vertical; timeline tests | **FP / SH** | `transport.py`, `VerticalPanel.tsx`, `timeline.py` | Kv/Kh, upward gradient, wellbore probability are scenario values; no intrinsic index by design |
| **O2 / D2 — data-gap identification** | identify gaps | observation-based ranking with visible weights; gap matrix; `Not tested` band; hydrochemical QA; assumption register; sensitivity analysis | QA, gap and register tests; audit check "register covers 12" | **FIV** as an application; this report as the document | `monitoring_gaps.py`, `hydrochem_qa.py`, `UNGROUNDED_PARAMETERS`, §6.9 | weights are a stated policy |
| **O2 / D2 — monitoring recommendations** | recommend strategies | ranked blocks, suggested sites, network plan, alert `next_action`; §7.7 | `test_r11_monitoring_gaps.py`, `test_r17_alert_tiers.py` | **FP** | `data_gaps.py`, `NetworkPlan.tsx` | ranks by observation, never by predicted risk |
| **O3 / D3 — prototype** | user-friendly tool with assessments and alerts | deployed portal, 22 screens, 152 endpoints, 5 roles, RLS, audit, advisory workflow | 522 backend tests; browser walk per role; deployment probes | **FIV** (as a prototype) | `docs/roles.md`, live URLs | free-tier sleep; deployment must be brought to the report commit |
| **D3 — alerts** | alerts | five kinds, four tiers on IS 10500's limits, seven-field record, P90 possible reach, email + ledger + retry + scheduler | 28 tier tests + 17 delivery tests + 11 R11 tests; CHECK constraints; verified against the deployed database | **FP** | migration `0026`, `alerts.py`, `notify.py` | needs an SMTP provider; no SMS; scheduler sleeps with the tier |
| **D4 — "real-time" dashboard** | real-time monitoring | console, public map, citizen map, report, data screens, timeline scrub/play | browser walk | **FP** | portal | **not real-time**: no sensor or telemetry feed exists and none was faked |
| **D5 — scalability to other contexts** | coal, rare earth, heavy metals | species registry (`SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES`); chloride added without retrain | `test_isr_excursion_panel.py` | **CO** | `config/parameters.py` | nothing outside uranium ISR in Jharkhand demonstrated |
| **D6 — CPS contribution** | sensors, streams, closed loop | data → detection → prediction → vulnerability → tiered alert → explanation → action, closed on the manual record; physical layer manual | delivery and tier tests | **CO** for sensing / **FP** for the decision loop | `main.py` scheduler, ingest, alert loop | "CPS-ready decision support", never a live loop |
| Proposed inputs (proposal §7) | pH, T, EC, TDS, turbidity, SO₄, NO₃, Cl, hardness, Fe, Mn, As, levels, distance, rainfall | all read where they exist; Fe/Mn/As never measured; T and turbidity only in the 2000–2021 physical file; rainfall via the measured seasonal swing, not IMD | — | partial by data | §3.4 | three named inputs absent from the record |
| Proposed methods (proposal §11) | RF/SVM/GB/ANN, CV, sensitivity analysis, data-gap analysis, case study | gradient boosting (quantile) with conformal calibration; RF/ridge/logistic in the superseded pipelines; grouped CV; Sobol sensitivity; case study with timeline | — | met with a stated substitution | §4.6, §6.9, §6.5 | SVM/ANN not used — nothing to learn that trees had not on 18,000 synthetic rows |
| Data hygiene (found in this report) | — | a demo field observation (`jharia`) remains in the tracked ore dataset and resolves a deposit-tier source near Dhanbad | — | **open** | §3.5 item 7 | remove through the dataset manager; re-check the deployed database |

# 9. Conclusion

**The problem.** Groundwater is the drinking-water supply of Jharkhand's hard-rock terrain, and the state's south-east is India's uranium province. In-situ recovery mining, were it ever attempted there, would mobilise uranium and its reagents into aquifers whose contamination is detected today, where it is detected at all, by manual sampling against limits, after the fact. No ISR mine exists in Jharkhand; the problem addressed was to build a preparedness screening tool that says where such contamination would go, who should be told, and what the existing monitoring record can and cannot support.

**The methodology.** After five months of platform building and three tabular machine-learning pipelines on measured and synthetic chemistry, the project established that a record with one sample per well and no plume cannot support a transport model of any kind, and rebuilt its prediction core as an analytical contaminant-transport engine — Domenico/Ogata–Banks with a leach-zone disc, sorption-scaled dual-porosity retardation, a matrix-diffusion envelope, a restoration draw-down law anchored to Texas operating records, first-order attenuation and the NUREG-1569 indicator test — grounded in real Jharkhand aquifer polygons, a station-fitted flow field, a lineament strike field, NAQUIM layers and UDEPO grades, and emulated by an XGBoost quantile surrogate with Mondrian conformal bands trained on 18,000 engine-labelled scenarios. Around it were built an IS 10500 assessment of the measured record, a tiered and delivered alert loop, an observation-based monitoring ranking, an assumption register, a global sensitivity analysis and a five-role portal with database-enforced access control, deployed on managed hosting.

**What was achieved.** The surrogate reproduces the engine with R²(log) of 0.89–0.95, beats its baselines, and holds its 80 % coverage on the serving distribution; the engine's kernel is exact to the benchmark and its physics laws hold on its labels. The measured record was read in full for the first time: uranium is within limits everywhere it was analysed, nitrate and fluoride are the health exceedances of Jharkhand's groundwater today, and three named determinands were never measured anywhere. At Jaduguda the modelled 20-year uranium extent is 20.5 m with sulphate at 73 m and TDS at 254 m; the vertical screening's breakthrough is 18.7 years on a duty-cycle basis. Every block in the state is ranked by how poorly it is observed, and the top 25 are all in the uranium belt. Alerts are tiered, explained in seven fields and delivered by email. All of this runs behind 373 engine tests and 522 backend tests.

**The main contribution.** Not the model, which is screening-grade and says so, but the discipline around it: an engine whose every foreign parameter is registered as such, a surrogate whose accuracy is defined as fidelity to that engine, an assessment that distinguishes clean from untested, an alert loop that was made to actually deliver, a monitoring recommendation that ranks by observation, and a limitations register that was kept current to the last commit — including the defects the tests could not see and the findings later retracted.

**The major limitations.** No modelled plume can be validated, and the conformal bands quantify parameter uncertainty inside the model's assumptions, not model error. The plume extent is governed by hydraulic conductivity and the dual-porosity capacity ratio, neither of which is measured at ore depth in the Singhbhum Shear Zone. The radium surrogate misses the project's own gate on two cells. Measured-quality forecasting for any health determinand was not achieved, because no dataset exists to achieve it with. The system is decision support over a manual network, not a live cyber-physical loop. Every modelled result in this report is a conditional statement about a hypothetical operation and never a forecast of real contamination.

# 10. Future work

Only what follows from a limitation named in §5 or a result in §6.

1. **A tracer or packer test in the Singhbhum Shear Zone** (fidelity row 3.4; RQ2). The only measurement that would ground β, the aperture, D_e and ω; the sensitivity analysis says β carries up to half the migration variance.
2. **Deep piezometry under the belt** (§6.6). The vertical screening's upward gradient is bracketed by the monsoon swing, not measured, and the shallow-impact band is decided by it.
3. **Analyse the existing Singhbhum samples for uranium; add Fe, Mn, As; record well depths; repeat sampling** (§7.7). The platform's ingest, QA, trend and alert paths are ready for each.
4. **Temporal chemistry for health determinands.** If CGWB or the state pollution board publish repeat analyses of nitrate and fluoride, the 2000–2021 ingest path and the Theil–Sen module close deliverable D1's "trends" and enable the rate-of-change alert tier that one sample per well forbids.
5. **A zero-inflated, two-stage radium head** (§6.2). The remedy for the point-mass labels is a classifier for "moves at all" followed by a regressor on the tail; it is a new ML approach and was deliberately not attempted in the final month.
6. **A numerical-model cross-check** (MODFLOW/MT3D or a discrete-fracture-network model) at one site, to bound the structural error the analytical family cannot express — a project in itself.
7. **Sensor integration with a real ingest contract**, if a telemetry station is ever installed in the belt; the data layer accepts it, and the CPS diagram's physical layer moves from "manual" to "sensed" only then.
8. **SMS delivery** for residents without email, and a paid hosting tier so the scheduler does not sleep.
9. **Other commodities through the species registry** — coal-mine acid drainage (sulphate, iron, manganese) is the nearest, because its indicators are already in the excursion panel — with the explicit caveat that nothing outside uranium ISR has been demonstrated.
10. **Remove the demo field observation** from the ore dataset (§3.5 item 7) and re-verify the deployed database, before any further use of the deployed system.


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

# References

IEEE numeric. Entries marked ✓ were opened (DOI, publisher page or catalogue record) on 21 September 2026 during the writing of this report; entries marked ○ are canonical works cited from the project's own configuration and documentation and were not re-opened on that date — they should be checked once more before submission. Dataset entries give provider, title, version or year, URL and access date.

**Transport theory and hydrogeology**

[1] ○ R. A. Freeze and J. A. Cherry, *Groundwater*. Englewood Cliffs, NJ: Prentice-Hall, 1979.

[2] ○ P. A. Domenico, "An analytical model for multidimensional transport of a decaying contaminant species," *Journal of Hydrology*, vol. 91, no. 1–2, pp. 49–58, 1987.

[3] ○ P. A. Domenico and G. A. Robbins, "A new method of contaminant plume analysis," *Ground Water*, vol. 23, no. 4, pp. 476–485, 1985.

[4] ○ A. Ogata and R. B. Banks, "A solution of the differential equation of longitudinal dispersion in porous media," U.S. Geological Survey Professional Paper 411-A, 1961.

[5] ○ D. H. Tang, E. O. Frind, and E. A. Sudicky, "Contaminant transport in fractured porous media: Analytical solution for a single fracture," *Water Resources Research*, vol. 17, no. 3, pp. 555–564, 1981.

[6] ○ I. Neretnieks, "Diffusion in the rock matrix: An important factor in radionuclide retardation?," *Journal of Geophysical Research*, vol. 85, no. B8, pp. 4379–4397, 1980.

[7] ○ M. N. Goltz and P. V. Roberts, "Three-dimensional solutions for solute transport in an infinite medium with mobile and immobile zones," *Water Resources Research*, vol. 22, no. 7, pp. 1139–1148, 1986.

[8] ○ L. W. Gelhar, C. Welty, and K. R. Rehfeldt, "A critical review of data on field-scale dispersion in aquifers," *Water Resources Research*, vol. 28, no. 7, pp. 1955–1974, 1992.

[9] ○ M. Xu and Y. Eckstein, "Use of weighted least-squares method in evaluation of the relationship between dispersivity and field scale," *Ground Water*, vol. 33, no. 6, pp. 905–908, 1995.

[10] ○ M. R. West, B. H. Kueper, and M. J. Ungs, "On the use and error of approximation in the Domenico (1987) solution," *Ground Water*, vol. 45, no. 2, pp. 126–135, 2007.

[11] ○ C. E. Manning and S. E. Ingebritsen, "Permeability of the continental crust: Implications of geothermal data and metamorphic systems," *Reviews of Geophysics*, vol. 37, no. 1, pp. 127–150, 1999.

**ISR regulation, records and field studies**

[12] ✓ U.S. Nuclear Regulatory Commission, *Standard Review Plan for In Situ Leach Uranium Extraction License Applications*, NUREG-1569, Final Report, June 2003. https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr1569/

[13] ✓ P. C. Mackin, D. Daruwalla, J. Winterle, M. Smith, and D. A. Pickett, *A Baseline Risk-Informed, Performance-Based Approach for In Situ Leach Uranium Extraction Licensees*, NUREG/CR-6733, U.S. Nuclear Regulatory Commission, Sept. 2001.

[14] ✓ J. A. Davis and G. P. Curtis, *Consideration of Geochemical Issues in Groundwater Restoration at Uranium In-Situ Leach Mining Facilities*, NUREG/CR-6870, U.S. Nuclear Regulatory Commission, Jan. 2007.

[15] ✓ S. M. Hall and T. B. Hennesy, "Historic groundwater quality of in situ recovery (ISR) uranium mines, Texas," U.S. Geological Survey data release, https://doi.org/10.5066/F74T6GC4 (ScienceBase item 5d1ce55ce4b0941bde64cd53). Accessed April 2026; re-checked 21 Sept. 2026.

[16] ✓ U.S. Geological Survey, "Data compiled on historical water use, spatial land disturbance, aquifer disturbance and uranium produced by in situ recovery of uranium from sandstone-hosted uranium deposits in the South Texas Coastal Plain, USA," data release, 2022, https://doi.org/10.5066/P9U7QKC1. Accessed April 2026 (`Datasets/Real_dataset/Dataset 2/Product_10.5066P9U7QKC1_METADATA.xml`).

[17] ✓ S. M. Hall, *Groundwater Restoration at Uranium In-Situ Recovery Mines, South Texas Coastal Plain*, U.S. Geological Survey Open-File Report 2009-1143, 2009. https://pubs.usgs.gov/of/2009/1143/

[18] ✓ P. W. Reimus, M. A. Dangelmayr, J. T. Clay, and K. R. Chamberlain, "Uranium natural attenuation downgradient of an in situ recovery mine inferred from a cross-hole field test," *Environmental Science & Technology*, vol. 53, no. 13, pp. 7483–7493, 2019, doi: 10.1021/acs.est.9b01572. *(Note: the project's configuration comment attributes this study to "Johnson et al. 2019"; the DOI resolves to Reimus et al., cited here correctly.)*

[19] ✓ T. J. Gallegos, K. M. Campbell, R. A. Zielinski, P. W. Reimus, J. T. Clay, N. Janot, J. R. Bargar, and W. M. Benzel, "Persistent U(IV) and U(VI) following in-situ recovery (ISR) mining of a sandstone uranium deposit, Wyoming, USA," *Applied Geochemistry*, vol. 63, pp. 222–234, 2015 (ScienceDirect S0883292715300342).

[20] ✓ U.S. Environmental Protection Agency, *Aquifer Restoration after Uranium Recovery*, EPA/600/F-17/342, 2017.

[21] ○ C. J. Newell, H. S. Rifai, J. T. Wilson, J. A. Connor, J. A. Aziz, and M. P. Suarez, *Calculation and Use of First-Order Rate Constants for Monitored Natural Attenuation Studies*, EPA/540/S-02/500, U.S. EPA, 2002.

**Jaduguda and Jharkhand studies**

[22] ✓ N. K. Sethy et al., "Dissolved uranium, ²²⁶Ra in the mine water effluent: A case study in Jaduguda," *Radiation Protection and Environment*, vol. 36, no. 1, pp. 32–37, 2013, doi: 10.4103/0972-0464.121824.

[23] ✓ S. Giri, M. K. Mahato, G. Singh, and V. N. Jha, "Risk assessment due to intake of heavy metals through the ingestion of groundwater around two proposed uranium mining areas in Jharkhand, India," *Environmental Monitoring and Assessment*, vol. 184, pp. 1351–1358, 2012, doi: 10.1007/s10661-011-2045-3.

[24] ✓ R. M. Tripathi, S. K. Sahoo, V. N. Jha, A. H. Khan, and V. D. Puranik, "Assessment of environmental radioactivity at uranium mining, processing and tailings management facility at Jaduguda, India," *Applied Radiation and Isotopes*, vol. 66, no. 11, pp. 1666–1670, 2008. *(Note: cited in the project's configuration as "BARC, J. Environ. Radioactivity 99"; the groundwater ²²⁶Ra range 3.5–208 mBq/L is from this Applied Radiation and Isotopes paper.)*

**Standards**

[25] ○ Bureau of Indian Standards, *IS 10500:2012 — Drinking Water — Specification (Second Revision)*, New Delhi, 2012, with amendments.

[26] ○ World Health Organization, *Guidelines for Drinking-water Quality*, 4th ed. incorporating the 1st addendum, Geneva, 2017.

**Machine learning and statistics**

[27] ○ Y. Romano, E. Patterson, and E. J. Candès, "Conformalized quantile regression," in *Advances in Neural Information Processing Systems 32 (NeurIPS 2019)*, 2019.

[28] ○ V. Vovk, A. Gammerman, and G. Shafer, *Algorithmic Learning in a Random World*. New York: Springer, 2005.

[29] ○ T. Chen and C. Guestrin, "XGBoost: A scalable tree boosting system," in *Proc. 22nd ACM SIGKDD Int. Conf. Knowledge Discovery and Data Mining*, 2016, pp. 785–794.

[30] ○ S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in *Advances in Neural Information Processing Systems 30 (NeurIPS 2017)*, 2017.

[31] ○ H. Theil, "A rank-invariant method of linear and polynomial regression analysis," *Proc. Koninklijke Nederlandse Akademie van Wetenschappen*, vol. 53, pp. 386–392, 521–525, 1397–1412, 1950.

[32] ○ P. K. Sen, "Estimates of the regression coefficient based on Kendall's tau," *Journal of the American Statistical Association*, vol. 63, no. 324, pp. 1379–1389, 1968.

[33] ○ H. B. Mann, "Nonparametric tests against trend," *Econometrica*, vol. 13, no. 3, pp. 245–259, 1945.

[34] ○ M. G. Kendall, *Rank Correlation Methods*, 4th ed. London: Charles Griffin, 1975.

[35] ○ J. D. Hem, *Study and Interpretation of the Chemical Characteristics of Natural Water*, 3rd ed., U.S. Geological Survey Water-Supply Paper 2254, 1985.

[36] ○ American Public Health Association, *Standard Methods for the Examination of Water and Wastewater*, 23rd ed., Method 1030 E (checking correctness of analyses), 2017.

**Datasets**

[37] ○ Central Ground Water Board, *National Aquifer Mapping and Management Programme (NAQUIM) — district reports for Jharkhand* (21 districts; page citations per row in `Datasets/naquim_reference/naquim_vertical.csv` and the extraction tracker). Accessed July 2026.

[38] ○ Central Ground Water Board, *District Ground Water Profile — East Singhbhum, Jharkhand* (`Datasets/naquim_reference/cgwb_east_singhbhum_profile.pdf`). Accessed July 2026.

[39] ○ Central Ground Water Board, groundwater quality data for Jharkhand, 2023 (tabular extract "table 36"; 397 wells, 24 districts, 20 determinands), as held in `Datasets/waterQuality_jharkhand.csv`. The originating year-book title is to be confirmed before submission.

[40] ○ Central Ground Water Board / India-WRIS, groundwater level monitoring data, Jharkhand, 2013–2021 (9,583 readings, 398 stations), as held in `Datasets/cgwb_waterlevel_jharkhand.csv`. https://indiawris.gov.in ; https://cgwb.gov.in/GW-data-access.html. Accessed January–February 2026.

[41] ○ Central Ground Water Board via National Water Informatics Centre, "Ground Water Quality Chemical Parameters CGWB Jharkhand (1961–2025) Manual" and "…Physical Parameters…", National Water Data Portal (CKAN), packages `ground-water-quality-manual-chemical-parameters-cgwb-f-gfg` and `ground-water-quality-manual-physical-parameters-cgwb`. Downloaded 20 Sept. 2026 (`services/chemistry_history.py` carries the resource URLs).

[42] ○ Geological Survey of India / NRSC Bhuvan, lineament map of Jharkhand (1,889 features), and *GSI lineament mapping manual* (`Datasets/naquim_reference/gsi_lineament_mapping_manual.pdf`). Accessed July 2026.

[43] ○ International Atomic Energy Agency, *World Distribution of Uranium Deposits (UDEPO)* database, India extract (`Datasets/udepo_uranium_deposits.xlsx`). https://www.iaea.org/resources/databases/udepo. Accessed July 2026.

[44] ○ European Space Agency / Copernicus, *Copernicus DEM — GLO-30* (30 m), Jharkhand extract. Accessed July 2026.

[45] ○ B. Lehner and G. Grill, "Global river hydrography and network routing: baseline data and new approaches to study the world's large river systems," *Hydrological Processes*, vol. 27, no. 15, pp. 2171–2186, 2013 (HydroRIVERS v1.0).

[46] ○ U.S. Environmental Protection Agency, *Understanding Variation in Partition Coefficient, Kd, Values*, Vols. I–II, EPA 402-R-99-004A/B, 1999.

[47] ○ U.S. Environmental Protection Agency, *Understanding Variation in Partition Coefficient, Kd, Values*, Vol. III, EPA 402-R-04-002C, 2004 (Table 5.28, radium).

[48] ○ D. H. Thibault, M. I. Sheppard, and P. A. Smith, *A Critical Compilation and Review of Default Soil Solid/Liquid Partition Coefficients, Kd, for Use in Environmental Assessments*, AECL-10125, Atomic Energy of Canada Ltd., 1990.

[49] ○ M. I. Sheppard and D. H. Thibault, "Default solid/liquid partition coefficients, Kds, for four major soil types: A compendium," *Health Physics*, vol. 59, no. 4, pp. 471–482, 1990.

**Sensitivity analysis**

[50] ○ A. Saltelli, P. Annoni, I. Azzini, F. Campolongo, M. Ratto, and S. Tarantola, "Variance based sensitivity analysis of model output. Design and estimator for the total sensitivity index," *Computer Physics Communications*, vol. 181, no. 2, pp. 259–270, 2010.

[51] ○ M. J. W. Jansen, "Analysis of variance designs for model output," *Computer Physics Communications*, vol. 117, no. 1–2, pp. 35–43, 1999.

[52] ○ I. M. Sobol', "Sensitivity estimates for nonlinear mathematical models," *Mathematical Modelling and Computational Experiments*, vol. 1, no. 4, pp. 407–414, 1993.

**Vulnerability indices and water-quality indices**

[53] ○ L. Aller, T. Bennett, J. H. Lehr, R. J. Petty, and G. Hackett, *DRASTIC: A Standardized System for Evaluating Ground Water Pollution Potential Using Hydrogeologic Settings*, EPA/600/2-87/035, U.S. EPA, 1987.

[54] ○ S. S. D. Foster, "Fundamental concepts in aquifer vulnerability, pollution risk and protection strategy," in *Vulnerability of Soil and Groundwater to Pollutants*, TNO Committee on Hydrological Research, Proceedings and Information No. 38, pp. 69–86, 1987.

[55] ○ M. Civita, *Le carte della vulnerabilità degli acquiferi all'inquinamento: teoria e pratica*. Bologna: Pitagora, 1994.

[56] ○ R. M. Brown, N. I. McClelland, R. A. Deininger, and R. G. Tozer, "A water quality index — do we dare?," *Water & Sewage Works*, vol. 117, no. 10, pp. 339–343, 1970.

[57] ○ C. R. Ramakrishnaiah, C. Sadashivaiah, and G. Ranganna, "Assessment of water quality index for the groundwater in Tumkur Taluk, Karnataka State, India," *E-Journal of Chemistry*, vol. 6, no. 2, pp. 523–530, 2009.

**Groundwater machine learning**

[58] ○ S. Sahoo and M. K. Jha, "Groundwater-level prediction using multiple linear regression and artificial neural network techniques: a comparative assessment," *Hydrogeology Journal*, vol. 21, pp. 1865–1887, 2013.

[59] ○ T. Rajaee, H. Ebrahimi, and V. Nourani, "A review of the artificial intelligence methods in groundwater level modeling," *Journal of Hydrology*, vol. 572, pp. 336–351, 2019.

**Screening tools, standards of practice, global data**

[60] ○ C. J. Newell, R. K. McLeod, and J. R. Gonzales, *BIOSCREEN: Natural Attenuation Decision Support System — User's Manual, Version 1.3*, EPA/600/R-96/087, U.S. EPA, 1996.

[61] ○ ASTM International, *ASTM D6312 — Standard Guide for Developing Appropriate Statistical Approaches for Groundwater Detection Monitoring Programs*.

[62] ○ J. Huscroft, T. Gleeson, J. Hartmann, and J. Börker, "Compiling and mapping global permeability of the unconsolidated and consolidated Earth: GLobal HYdrogeology MaPS 2.0 (GLHYMPS 2.0)," *Geophysical Research Letters*, vol. 45, no. 4, pp. 1897–1904, 2018.

**Project documents (not peer-reviewed; cited by path)**

- V. Raj, *Monthly Progress Reports*, November 2025 – August 2026 (ten reports), TEXMiN–BIT Sindri UG Fellowship 2025–26.
- V. Raj, *Proposal: Smart Water Monitoring: Machine Learning and CPS for Safe & Sustainable Mining*, UG Call for Proposal Fellowship Program 2025, TEXMiN–BIT Sindri Mining CPS CoE (`docs/local/My_Proposal.pdf`).
- JalDrishti repository documentation at commit `476a4a9`: `docs/LIMITATIONS.md`, `docs/PROJECT_FREEZE.md`, `docs/PRE_REPORT_AUDIT_AND_PLAN.md`, `docs/TECHNICAL_REPORT_STRUCTURE.md`, `docs/PRODUCT_DESIGN.md`, `docs/DEPLOYMENT.md`, `docs/roles.md`, `ml_pipeline/ARCHITECTURE.md`, `ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`, `ml_pipeline/E1_geometry_design.md`; and the untracked review record `docs/local/audit-record/` (QA sweep 13 July 2026; `review.md` 4 Aug; `review2.md` 5 Aug; `DOMENICO_ERROR_ENVELOPE.md` 5 Aug; `review3.md` 10 Aug; `ML_PIPELINE_READINESS.md` 10 Aug; `R10_AUDIT.md` 19 Aug; `DEPLOYMENT_AUDIT_2026-08-20.md`).


```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

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

**Tables (ORM models at the report commit):** `orgs`, `users` (with `home_block_id`, `alert_email_opt_in`), `districts`, `blocks`, `aquifers`, `monitoring_wells`, `monitoring_stations`, `water_samples` (20 determinands, `record_source`), `data_sources`, `dataset_versions`, `isr_points` (operating parameters, `injection_start_date`, owner org), `scenarios`, `simulation_runs` (request, plume geometry with contours, frames and vertical block; pinned model-card SHA, artifact SHA, code version), `simulations` (legacy, empty), `advisories` (status, headline, what it means, affected blocks, decided_by, published_at), `alerts` (kind, block, severity, tier, basis, explanation JSONB, well fields, advisory link), `alert_deliveries`, `block_subscriptions`, `field_observations`, `audit_log`.

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

Every quantitative claim in the body, its section, and its source at commit `476a4a9` (or the dataset / citation). Reference entries opened on the report date are marked ✓ in the reference list.

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
| 48 | Reference attribution corrections ("Johnson et al. 2019" → Reimus et al.; "J. Environ. Radioact. 99" → Appl. Radiat. Isot. 66) | references | DOI 10.1021/acs.est.9b01572 and publisher records opened 21 Sep 2026 |
| 49 | NUREG-1569 ring 75–180 m, ≥ 3 indicators, 2-of-N, uranium rejected as an indicator | 1.1, 4.5 | NUREG-1569 §5.7.8.3 pp. 137–139 (as quoted in `config/parameters.py`) |
| 50 | Basement Gneissic Complex 48,047 km²; shallow flow ~1.5 m/yr; 27 m / 255 m in 20 yr | 3.2, 6.8 | `docs/LIMITATIONS.md` §4a |

**Reference verification status:** entries 12–20, 22–24 opened on 21 September 2026 (✓); the remaining canonical works and dataset entries (○) were cited from the project's configuration and documentation and should be opened once more before submission, in particular [39] (the exact CGWB year-book title) and [37]/[38] (NAQUIM report titles per district).

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

```{=openxml}
<w:p><w:r><w:br w:type="page"/></w:r></w:p>
```

*End of report.*
