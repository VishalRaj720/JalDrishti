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

\newpage

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

\newpage

# Declaration

I, Vishal Raj, admission number 24030480134, enrolled in the B.Tech (Information Technology) programme at B.I.T. Sindri, Dhanbad, declare that the work described in this report, entitled *Smart Water Monitoring: Machine Learning and CPS for Safe & Sustainable Mining* (system name *JalDrishti*), was carried out by me under the guidance of my faculty mentor during the TEXMiN–BIT Sindri UG Fellowship 2025–26.

All sources of data, published methods and prior work used in this project are acknowledged in the text and in the reference list. Numerical results reported here were regenerated from the repository at the commit named on the title page, and every quantitative claim is traceable to a file, a test, a dataset row count or a citation in the Source-to-Claim Register (Appendix H).

AI-assisted software tooling (Claude, Anthropic) was used throughout the project for software development, code review, documentation and drafting, under my direction and review; the design decisions, the datasets chosen, the scientific assumptions adopted and the interpretation of results are my responsibility. This is stated plainly because it is true and because the project's own working rule was that anything weaker than it looks must be written down rather than left for a reader to discover.

The proposal carried a TEXMiN CoE declaration on intellectual property and confidentiality (proposal page 6). Where the final report requires that institutional wording, it is to be attached in the institutional form; this declaration does not replace it.

No part of this work has been submitted elsewhere for any degree or award.

Signature: ______________________  Date: ______________

\newpage

# Acknowledgement

I thank my faculty mentor for guidance throughout the fellowship, and in particular for the advice in April 2026 to look for internationally published ISR operating records when no Indian ISR data could exist — the decision from which the final methodology descends.

I thank the TEXMiN–BIT Sindri Mining CPS Centre of Excellence and B.I.T. Sindri for the fellowship and for the review panel in August 2026.

This project rests entirely on open data published by others: the Central Ground Water Board (CGWB) and the National Water Informatics Centre (National Water Data Portal), for the 2023 groundwater-quality table of the *Annual Ground Water Quality Report 2024*, the 2013–2021 water-level record (via India-WRIS and the India Data Portal), the 2000–2021 chemistry record, the NAQUIM aquifer-mapping reports and the East Singhbhum groundwater information booklet; the Geological Survey of India and the National Remote Sensing Centre (ISRO), whose 1:50,000 lineament layer is served on Bhuvan; the International Atomic Energy Agency for the UDEPO deposit database; the U.S. Geological Survey for the two Texas ISR data releases; the European Space Agency / Copernicus programme for the GLO-30 digital elevation model, distributed by OpenTopography; and Lehner & Grill for HydroRIVERS. The published Jaduguda studies by the Bhabha Atomic Research Centre and the Indian School of Mines provided the only local measurements of mine-water uranium and radium.

The software stands on FastAPI, SQLAlchemy, PostgreSQL/PostGIS, XGBoost, scikit-learn, NumPy/SciPy, pandas/GeoPandas, React, Vite, Leaflet and TanStack Query, and is hosted on Neon, Render and Cloudflare Workers.

\newpage

# Abstract

Groundwater is the primary drinking-water supply across Jharkhand's hard-rock terrain, and the Singhbhum Shear Zone in its south-east is India's uranium province. In-situ recovery (ISR) uranium mining — injecting an oxidising, carbonate-bearing lixiviant into an ore-bearing aquifer — mobilises uranium, sulphate, dissolved solids and radium, and the regulatory experience of ISR in the United States shows that excursions past the wellfield are detected by manual sampling against control limits, after the fact. No ISR mine operates in Jharkhand and commercial ISR is not plausible in schist-hosted ore; this project is therefore a **preparedness screening study**: *if ISR-strength lixiviant entered a Jharkhand aquifer, how far and how fast would contamination move, would it reach the shallow drinking-water aquifer, who should be told, and what should be monitored — and which of those questions can the available data actually answer?*

The delivered system, JalDrishti, couples (i) an analytical contaminant-transport engine — the Domenico/Ogata–Banks plan-view solution with a leach-zone disc, Goltz–Roberts dual-porosity retardation scaled by matrix sorption, a Tang matrix-diffusion envelope, a restoration draw-down law anchored to Texas operating records, first-order uranium attenuation and a NUREG-1569-style 2-of-3 indicator excursion test — with (ii) an XGBoost quantile surrogate trained on 18,000 engine-labelled scenarios placed on real Jharkhand aquifer polygons, calibrated by Mondrian split-conformal prediction, and validated by grouped and leave-aquifer-out cross-validation and by a field-resampled coverage gate; (iii) an IS 10500:2012 assessment of the 397-well CGWB measured record with a tiered alert loop delivered by email; (iv) an observation-based monitoring-gap ranking of all 264 blocks; and (v) a five-role government portal with database-enforced row-level security, deployed on managed hosting.

Principal results: the surrogate reproduces the engine with R²(log) of 0.893 (footprint area), 0.926 (migration distance) and 0.947 (ring concentration) under scenario-grouped cross-validation, beats ridge and stump baselines on every target, and holds 80 % conformal coverage on the serving distribution (0.875–0.885 scenario coverage); it misses the project's own R²(log) ≥ 0.60 gate on two radium cells (0.500, 0.235) because those labels are point masses, and this is reported rather than moved. On the measured record, uranium exceeds its limit at none of 342 tested wells while nitrate exceeds at 22 and fluoride at 32 (11 above the permissible limit); arsenic, iron and manganese have never been analysed anywhere in the record; the three Singhbhum districts have no uranium result at all. At the Jaduguda reference site the modelled 20-year uranium extent is 20.5 m (band 2.7–100 m) while sulphate reaches 73 m and TDS 254 m — the ordering that makes conservative indicators, not uranium, the excursion signal. A global sensitivity analysis shows hydraulic conductivity and the dual-porosity capacity ratio β carry most of the extent's variance; β is derived from the run's own porosities but is not measured anywhere in the Singhbhum belt.

The principal limitation is structural: no field validation of any modelled plume is possible, and the conformal bands quantify parameter uncertainty inside the model's assumptions, not model error. The system is "CPS-ready decision support" over a manual monitoring network, not a live sensing loop.

**Keywords:** groundwater vulnerability; in-situ recovery (ISR) uranium mining; contaminant transport surrogate; conformal prediction; monitoring network design; decision-support system; Jharkhand; IS 10500.

\newpage

# Conventions used in this report

- **Result tags.** Every results subsection and figure caption in §6 carries one of three tags: **[M]** a *measured* quantity (a laboratory value, a station reading); **[S]** a *modelled scenario* result (conditional on the hypothetical ISR operation of §3.6); **[V]** a *model-internal validation* (the surrogate against the engine, the engine against an exact solution). No result in this report is a prediction of real contamination in Jharkhand.
- **Provenance.** Numbers are quoted from artefacts at commit `476a4a9` unless a section says otherwise; the artefact for each is listed in Appendix H. Where a number was produced earlier in the project and the artefact has since changed, the earlier value is given with its date.
- **Citations** are IEEE-numeric, in square brackets, to the reference list. Repository files are cited by path in backticks; the chronological review record kept outside version control is cited as `docs/local/audit-record/<file>`.
- **Version labels.** The surrogate artifacts are versioned by model card: v3 (11 Aug 2026), v4 (20 Sep 2026, the β retrain), v5 (21 Sep 2026, the background-floor retrain — the version reported here). "R10–R17" denote the numbered review-and-remediation passes of August–September 2026, as used throughout the repository's documentation.
- **What is not claimed.** The words *real-time*, *validated against reality*, *accurate* and *predicts contamination* are avoided deliberately; §5 and §7 explain why each would overstate the work.
