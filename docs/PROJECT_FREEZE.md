# JalDrishti — project freeze and report readiness

**Frozen 2026-09-20 (R17).** From this point no feature is added; only defects are
fixed. This file is the factual source of truth for the Technical Research Report:
every number here was measured on this date on the commits listed in §0, and every
row of the Completion Matrix (§10) names its evidence. Where a claim is weaker than
it looks, it is written down here rather than left for a reader to discover.

The companion documents are `docs/PRE_REPORT_AUDIT_AND_PLAN.md` (what was decided and
why), `docs/TECHNICAL_REPORT_STRUCTURE.md` (what the report will contain) and
`docs/LIMITATIONS.md` (the live register of what the system does not know).

---

## 0. Verification record

| Check | Command / method | Result on 2026-09-20 |
|---|---|---|
| Engine tests | `python -m pytest ml_pipeline/tests -q` | **368 passed** |
| Backend tests | `cd backend && pytest` (`.localenv`, PostgreSQL 18 + PostGIS) | **518 passed**, 376 s |
| Authorization matrix | `python -m scripts.authz_matrix` → `docs/roles.md`; `tests/test_authz_matrix.py` | 152 endpoints × 5 roles, regenerated; test passes |
| RLS | `tests/test_rls.py`, `test_field_observation_isolation.py`; policies listed on the local DB | 3 policies on `alerts` (SELECT, INSERT, **UPDATE** — new in 0026); RLS genuinely in force locally (`jaldrishti_app`) |
| Engine end-to-end audit | `python -m ml_pipeline.validation.end_to_end_audit` | **40 PASS / 1 FAIL** — the radium R²(log) gate, reported not moved |
| Artifact consistency | `test_docs_in_sync.py` (ARCHITECTURE §6.5 = metrics.json); `test_r17_artifacts.py` (training-CSV SHA-256 = model card); `backend/tests/ml_artifact_hashes.json` | all pass |
| Documentation consistency | README, `.claude/CLAUDE.md`, `ml_pipeline/README.md`, fidelity matrix, DEPLOYMENT, DEPLOY_WALKTHROUGH, LIMITATIONS, roles.md | synced in R17 (test counts, head `0026`, four sanctioned changes) |
| Portal build | `npm run build` (tsc -b, vite, credential guard) | builds; "no credentials in 4 built files — F-1 guard passed" |
| Browser walk (local API + portal) | console run → save → timeline scrub/play; Alerts page tiers + seven-field record; Data & Gaps QA + temporal record; report page frames table + β paragraph | verified by reading the DOM and screenshots; no console errors |
| Deployed API | `GET https://jaldrishti-api.onrender.com/health` | 200 after a 53 s cold start (free tier). **Runs the pre-R17 code**: migration `0026`, the v4 artifacts and the rebuild step are for the owner to deploy (§8) |
| PDF export | — | **not re-verified in this pass**; `LIMITATIONS.md` §4 O-8 stands (verify by hand once) |

Commits (branch `r17-beta-alerts-timeline`, on top of `main` at `27fe985`):
`4d07b98` audit + plan · `47ad56d` alert tiers · `7af0326` timeline frames · `1a1164d` β
retrain (v4) · `d34b57b` QA + sensitivity · `a91c44f` CGWB 2000–2021 record · plus the
documentation-sync commit that closes R17.

---

## 1. Final architecture

Three parts, wired together, one deployment:

- **`ml_pipeline/`** — the analytical transport engine (Domenico/Ogata-Banks plan solve
  with the E1 leach-zone disc; Goltz–Roberts dual-porosity retardation with
  `R_eff = 1 + β·R_m`; Tang matrix-diffusion envelope; restoration draw-down law;
  first-order uranium attenuation; NUREG-1569-style 2-of-3 indicator excursion test;
  2.5-D vertical screening with three pathways and a duty-cycle seasonal gradient) and
  the XGBoost surrogate (P10/P50/P90 heads per target, Mondrian split-conformal
  calibration by regime × species, `P_ex` regressor). Statewide inputs: aquifer
  polygons, 5 km flow field from 398 CGWB level stations + GLO-30 DEM, lineament strike
  field, NAQUIM layer table, UDEPO grades, HydroRIVERS receptors, Texas ISR source
  signature. Its own FastAPI dashboard (:8077) is imported **in-process** by the backend.
- **`backend/`** — FastAPI (async) + SQLAlchemy 2 + asyncpg + PostgreSQL 16/PostGIS.
  JWT + argon2; five roles; Postgres row-level security with two database roles;
  immutable audit log; dataset sync with provenance; IS 10500 assessment; Theil-Sen
  level trends; hydrochemical QA; the CGWB 2000–2021 record; monitoring-gap ranking;
  advisory workflow (propose → single-admin publish → alerts → email); alert tiers with
  the seven-field record; timeline frames on stored runs; in-process scheduler for the
  measured scan and delivery. Alembic head **`0026_alert_tiers_explanation`**.
- **`frontend/portal/`** — Vite 6 + React 18 + TypeScript 5.7 + Leaflet + TanStack
  Query. 22 screens; public front page; light/dark themes; every colour a token.

Deployed as Neon (PostgreSQL) + Render (API, free tier) + Cloudflare Workers (portal,
`/api/*` proxied). No queue, no broker, no sensors, no telemetry.

---

## 2. Final datasets

| Dataset | Provider | Rows / extent | Used for | Held in repo |
|---|---|---|---|---|
| Groundwater chemistry 2023 | CGWB (yearbook table) | 397 wells, 24 districts, 20 determinands; **one sample per well**; U at 342; Fe/As 0 % | IS 10500 assessment, citizen band, measured alerts, engine background, QA | `Datasets/waterQuality_jharkhand.csv` |
| Groundwater chemistry 2000–2021 (**new, R17**) | CGWB via National Water Data Portal (NWIC) | 1,632 analyses, 366 stations, 2000–2021; pH/EC 100 %, HCO₃/Cl/Ca/Mg/Na 92 %, hardness 81 %, SO₄ 46 %; **no F, NO₃, Fe, As, Mn**; 2 U values | per-station baseline and trend of the general chemistry (excursion indicators); read-only | `Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv` (+ physical file: temperature, turbidity) |
| Groundwater levels 2013–2021 | CGWB | 9,583 readings, 398 stations, quarterly | flow field (head = DEM − depth), seasonal amplitude, Theil-Sen level trends | `Datasets/cgwb_waterlevel_jharkhand.csv` |
| Aquifer polygons | CGWB/NAQUIM-derived | statewide, lithology, K, Sy, thickness | regime, K, porosities | `Datasets/Aquifers_Jharkhand.geojson` |
| District / sub-district boundaries | GoI | 24 districts, blocks | resolution, alerts by block | `Datasets/*Boundary_JH.geojson` |
| Lineaments | GSI/NRSC Bhuvan | 1,889 features | strike field → anisotropy, display azimuth | `Datasets/jharkhand_lineaments.geojson` |
| Perennial rivers | HydroRIVERS (Lehner & Grill) clip | 4,577 reaches | receptor distance, plume–river crossing | `Datasets/jharkhand_rivers.geojson` |
| NAQUIM vertical table | CGWB NAQUIM reports (21 districts) + E-Singhbhum profile; 3 regional estimates | 24 rows: layer-1 base, fracture range, confined flag | vertical screening | `Datasets/naquim_reference/naquim_vertical.csv` |
| Uranium deposits | GSI polygons; IAEA UDEPO grades | 7 polygons; 9 deposits | ore-zone C₀ gating and grade scaling | `Datasets/Jharkhand Ore/`, `udepo_uranium_deposits.xlsx` |
| Texas ISR records | USGS data releases (Dataset 1, Dataset 2) | 86/9/86 chemistry rows; restoration, area, exemptions | C₀ envelope (n = 9 at 7 mines), restoration residuals and reference years, porosity | `Datasets/Real_dataset/` |
| DEM | Copernicus GLO-30 | statewide, 30 m (703 MB, gitignored) | flow-field bake only | regenerable via `fetch_data/` |
| Synthetic training set | this project (v4 bake) | 900 scenarios × 5 horizons × 4 species = 18,000 rows, 48 MC draws each | surrogate training | gitignored; SHA-256 `3a50ba19…` in the model card; regenerable by seed |

---

## 3. Final ML models

**v4 surrogate** (`ml_pipeline/ml/artifacts/`, model card version 4, trained
2026-09-20 from bake `7af0326`, 40 features, GroupKFold(5) on scenario, leave-aquifer-
out on polygon, Mondrian split-conformal at α = 0.20 with `DELTA_INFLATE = 1.35`).

| Target | R²(log) P50 | Per-species R²(log) (U / SO₄ / TDS / Ra) | Scenario coverage | Field-resampled coverage | Ridge baseline | Stump baseline |
|---|---|---|---|---|---|---|
| affected_area_ha | 0.894 | 0.943 / 0.790 / 0.827 / 0.892 | 0.861 | 0.883 | 0.560 | 0.383 |
| max_migration_distance_m | 0.927 | 0.929 / 0.878 / 0.890 / **0.515** | 0.868 | 0.875 | 0.772 | 0.514 |
| compliance_conc | 0.947 | 0.849 / 0.917 / 0.961 / **0.227** | 0.862 | 0.879 | 0.744 | 0.498 |
| excursion_probability (point) | R² 0.916, MAE 0.049 | — | — | — | — | — |

Gates: scenario coverage ≥ 0.80 ✅; field-resampled coverage ≥ 0.80 ✅; on-manifold
physics laws ✅; band-order violations 0 ✅; **per-species R²(log) ≥ 0.60 ❌ on two
radium cells** (point-mass labels: 81.8 % exact zeros / 95.8 % pinned at background;
compliance fell 0.431 → 0.227 in v4; the conformal band on those cells covers
0.92–0.95). Leave-aquifer-out R²(log): 0.891 / 0.922 / 0.941.

**What the surrogate is:** an emulator of the analytical engine with calibrated
parameter-uncertainty bands. It cannot be more accurate than the engine and has never
been compared with a real plume, because none exists in Jharkhand.

**Explainability:** SHAP top features per head in `shap_top_*.json`.

**Sensitivity** (`ml/artifacts/sensitivity.json`, Sobol N = 256, three sites × two
species, 20 yr): total-order indices on migration — Jaduguda uranium K 0.42, β 0.21,
gradient 0.16; Jaduguda sulfate K 0.39, β 0.24, Kd 0.17; belt uranium β 0.29, K 0.26,
ω 0.18; the fracture aperture and De ≈ 0 everywhere; footprint area governed by the
leach-disc growth constants (SOURCE_BV_GAIN/REF up to 0.55). Registered ungrounded
constants carry 25–49 % of the migration variance, almost all of it β. Uranium at a
non-ore pin is constant over the design (source suppressed) and is reported as
degenerate.

---

## 4. Final assumptions

The scenario is hypothetical throughout: **no ISR uranium mine operates in Jharkhand**,
commercial ISR is not plausible in schist-hosted ore, and every modelled output means
"if ISR-strength lixiviant entered this aquifer". The machine-readable register
`P.UNGROUNDED_PARAMETERS` (12 entries, served at `GET /api/v1/ml/assumptions`) and
`ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md` are authoritative; the ones the report must
state up front:

| Assumption | Value | Basis | Status |
|---|---|---|---|
| Dual-porosity capacity ratio β | derived per run: `(n_total − φ_m)/φ_m` (3.0 at Jaduguda); prior log-U[0.3, 20]; MC band ×4 | lithology-typical porosities (Freeze & Cherry 1979) or polygon specific yield | **not measured**; R17 made the engine's two statements of matrix capacity agree; sensitivity: second only to K |
| Matrix transfer rate ω | 1e-3 /day pinned | generic literature | ungrounded; sensitivity ≈ 0 except belt uranium (0.18) |
| Fracture aperture, De | 250 µm (100–500 sampled), 5e-6 m²/day | foreign crystalline analogues | ungrounded; sensitivity ≈ 0 at 20 yr |
| C₀ (uranium) | 9,000–41,600 ppb envelope, grade-scaled by UDEPO | n = 9 at 7 Texas mines | foreign source term |
| Kd | regime ranges (U fractured 0.3–3 L/kg) | literature, alkaline-ISR suppressed | uncertain, MC-sampled |
| K in the shear zone | T = 370 m²/day over 150 m | E-Singhbhum NAQUIM/profile | one district's data applied to the belt |
| Leach-disc growth | gain 0.4, scale 2 BV | scenario assumption | governs footprint area |
| Vertical: Kv/Kh, upward gradient, wellbore probability | 0.03 / 0.008; 0.005; 0.05 | scenario assumptions, NUREG context | ungrounded |
| Attribution floor | 10 % of the limit | modelling policy | policy |
| Alert `critical` rule | ≥ 2× the alert limit or ≥ 2 health determinands | **project-defined** | labelled in every record |
| Monitoring-gap weights | 30/30/20/15/5 | policy | shown on screen |

---

## 5. Final validation results

- **Physics:** transport kernel benchmarked against the exact Ogata-Banks solution
  (`physics/exact_reference.py`, `validation/domenico_error_sweep.py`); retarded-clock
  closed form = numeric integral; physics-law tests on labels (`test_physics_laws.py`).
- **Surrogate:** §3. Baselines beaten on every target in log space.
- **Engine ↔ backend:** every stored run pins model-card SHA, artifact SHA and code
  version (`ck_sim_runs_completed_is_pinned`); the backend refuses payloads carrying
  measured chemistry; artifact hashes pinned.
- **Security:** rate limiting measured (10 × 401 then 429); RLS verified on the live
  connection (`jaldrishti_app`, no bypass); role × endpoint sweep in `roles.md`;
  production-secret guards; security headers; credential-free bundle.
- **Alerts:** tier ladder pinned by 28 tests; a modelled alert cannot be `critical`
  (CHECK); upsert idempotent and RLS-guarded at the source; on the local record the
  measured scan yields 3 critical / 29 alert / 21 warning; rebuild endpoint verified
  against a real database (which is how the missing UPDATE policy was found).
- **Timeline:** frames are separate engine evaluations (stub-engine test asserts one
  call per frame at that year); the horizon frame equals the run's own metrics on a
  real stored run; first exceedance agrees with an independent scan and with the
  lifecycle calculation.
- **QA:** charge balance verified against a hand-computed analysis; the 2023 file
  balances by construction (sodium by difference), the 2000–2021 file does not.
- **What could not be validated, and never can be with this data:** any modelled
  plume against a measured one; any health-determinand trend; the vertical pathway
  against deep piezometry.

---

## 6. Final limitations (the ones the report must lead with)

1. No field validation of the transport model is possible; the conformal bands
   quantify parameter uncertainty inside the model's assumptions, not structural error.
2. β is derived, not measured; K and β carry most of the extent's variance; a
   Singhbhum tracer/packer test is the only thing that retires this.
3. The radium surrogate misses the project's own R²(log) ≥ 0.60 gate on two cells.
4. The measured record: one sample per well in 2023; Fe/As/Mn never analysed anywhere
   in the state; the three Singhbhum districts have no uranium result; no well depths;
   the 2023 analyses balance by construction so their charge balance is not a QA.
5. The 2000–2021 record supplies temporal baselines for the general chemistry only —
   **measured-quality trend forecasting for any health determinand was not achieved,
   because no dataset exists to achieve it with.**
6. No sensors, no telemetry: the CPS is "CPS-ready decision support" over a manual
   network, never a live loop.
7. Email delivery depends on an SMTP provider the operator configures; no SMS; the
   scheduler sleeps with the free tier.
8. Two vertical-screening constants and the wellbore probability are scenario values.
9. 2.5-D only: no depth-resolved concentration exists to support 3-D, and none was
   invented.
10. No frontend unit tests (the build guard and hand verification only); PDF
    pagination hand-checked, not automated.

---

## 7. Final feature list (as shipped)

Engine: statewide pin → resolved hydrogeology → analytical plume + ML bands; four
species; excursion panel; vertical screening; lifecycle; sweep; assumptions endpoint;
**v4 β**; **sensitivity artifact**. Backend: sites, runs (pinned), preview, scenarios,
compare, advisories (propose/decide/withdraw), alerts (**five kinds, four tiers, seven
fields, P90 possible reach**), email delivery + ledger, scheduler, **timeline frames**,
IS 10500 assessment, WQI, **hydrochemical QA**, **2000–2021 chemistry history**, level
trends, monitoring-gap ranking/siting/matrix, dataset sync/backup/restore, ingest,
audit, five roles + RLS. Portal: front page, console, report (**frames table, β
paragraph**), compare, scenarios, publications, field data, Data & Gaps (**QA and
temporal readouts**), water quality (**history on the well card**), groundwater,
network plan, audit, administration (**rebuild action, tier counts**), datasets,
ingest, my area, alerts (**tiers, record, ladder**), methods, public view.

---

## 8. Final deployment state

Neon + Render + Cloudflare Workers, live, running the **pre-R17 code**. To bring the
deployment to the frozen state the owner runs, in order: `cp .globalenv .env`;
`alembic upgrade head` (→ `0026`); deploy the API with the v4 artifacts; deploy the
portal build; sign in as the single admin and `POST /api/v1/citizen/alerts/
rebuild-explanations` once; re-run one simulation per published site so the
published advisory has frames (runs stored before R17 read as "timeline not recorded").
Email remains dormant until `SMTP_*` and `ALERT_FROM_EMAIL` are set.

---

## 9. Final reproducibility information

- **Engine artifacts:** `model_card.json.reproducibility` — training CSV name and
  SHA-256 (`3a50ba19669ba5ef…`), 18,000 rows / 900 scenarios, bake meta (seed 42,
  MC seed 43, generator version 4, git `7af0326`, β prior and MC factor), trainer git
  SHA, hyper-parameters, the six regeneration commands. `synthetic_meta.json` written
  by every bake. `sync_docs` regenerates ARCHITECTURE §6.5 and `test_docs_in_sync`
  fails on drift.
- **Snapshots:** `ml_pipeline/outputs/snapshot_pre_r17.json` / `snapshot_post_r17.json`
  (72 pin × species × horizon cells, both engines) — the before/after in
  `LIMITATIONS.md` §1d.
- **Backend:** every completed run pins model-card SHA, artifact SHA and code version;
  `tests/ml_artifact_hashes.json` pins the artifact bundle; migrations are the schema
  record; `scripts/seed` is idempotent and `seed_demo_story` builds one complete story.
- **Datasets:** provenance in `docs/local/datasets_source.md` (untracked) and the
  module docstrings (`chemistry_history.py` carries the NWDP URL and access date).
- **Sensitivity:** `python -m ml_pipeline.validation.sensitivity --n 256` (≈ 3 min).

---

## 10. Project Completion Matrix

Status vocabulary: **FIV** fully implemented and validated (internal + external) ·
**IIV** implemented, internally validated only · **FP** functional prototype ·
**SH** simulated/hypothetical · **CO** conceptual · **NA-D** not achieved because of
data limitations.

| Objective / deliverable | Final implementation | Evidence | Validation | Result | Remaining limitation |
|---|---|---|---|---|---|
| **O1 — ISR-source prediction** | Physics-informed transport engine + v4 XGBoost surrogate with conformal bands; statewide inputs; β porosity-derived | `ml_pipeline/`, `ml/artifacts/model_card.json` v4, `metrics.json` | 368 engine tests; exact-solution benchmark; GroupKFold + leave-aquifer-out; scenario coverage 0.86–0.87; field-resampled 0.88; e2e audit 40/41 | R²(log) 0.894 / 0.927 / 0.947; baselines beaten; Jaduguda U 20 yr: 20.5 m (band 2–102 m), SO₄ 73 m | **IIV / SH** — no real plume exists to validate against; radium fails its gate; β not measured |
| **O1 — measured-quality trends (D1 "forecast trends")** | IS 10500 assessment of the 2023 record; Theil-Sen/MK on the 2000–2021 record for general chemistry (EC 13 rising / 6 falling of 175 testable); no forecasting | `services/water_quality.py`, `chemistry_history.py`, `GET /water-quality/history` | 50 water-quality tests incl. 8 for the history; profile pinned | Temporal baselines for Cl/SO₄/EC at 244 wells; **no trend for any health determinand** | **NA-D for health; FP for general chemistry** — the only multi-year record has no F/NO₃/U/Fe/As |
| **O1 — aquifer vulnerability** | Source-specific: vertical screening (3 pathways, duty-cycle gradient, NAQUIM layers), excursion probability, ring concentration; timeline first-exceedance | `transport.py:597–760`, `VerticalPanel.tsx`, `timeline.py` | 368 engine tests incl. seasonal/vertical; timeline tests (12) | Jaduguda: breakthrough headline on the duty-cycle basis; possible-reach alerts | **FP / SH** — Kv/Kh, upward gradient, wellbore probability are scenario values; no intrinsic (DRASTIC) index by design |
| **O2 — data-gap identification (D2)** | Observation-based block ranking with visible weights; gap matrix; `untested_health`; `Not tested` band; hydrochemical QA + independence check; assumptions register; the 2000–2021 coverage table | `monitoring_gaps.py`, `hydrochem_qa.py`, `data_quality.py`, `P.UNGROUNDED_PARAMETERS`, Data & Gaps screen | 8 QA tests; gap tests; register test; e2e audit "assumption register covers 12" | Fe/As 0 %; belt untested for U; one sample per well; 2023 file balances by construction; 12 ungrounded constants named; sensitivity says which matter | **FIV** as an application; the written analysis is the report's §6.9/§7 |
| **O2 — monitoring recommendations** | Ranked blocks + suggested sites + network plan; alert `next_action` names wells inside the modelled reach or records that none exists | `data_gaps.py` (4 routes), `NetworkPlan.tsx`, `alert_tiers.explain_modelled` | `test_r11_monitoring_gaps.py`, `test_r17_alert_tiers.py` | Ranking by observation, never by predicted risk | **FP** — weights are a stated policy |
| **O3 — prototype (D3)** | Deployed portal, 22 screens, 152 endpoints, 5 roles, RLS, audit, advisory workflow | `docs/roles.md`, live URLs | 518 backend tests; browser walk; deployment probes | Working end to end locally; deployed (pre-R17) | **FIV** (as a prototype) — free-tier sleep; deployment of R17 pending the owner |
| **D3 — alerts** | Five kinds, four tiers on IS 10500's limits, seven-field record, P90 possible reach, email + ledger + scheduler, breach-due dry-run | migration `0026`, `alert_tiers.py`, `alerts.py`, `notify.py`, Alerts screen | 28 tier tests + 16 R16 + 11 R11 tests; CHECK constraints; rebuild verified on a real DB | 53 wells over a limit → 3 critical / 29 alert / 21 warning (local) | **FP** — email needs a provider; no SMS; scheduler sleeps on the free tier |
| **D4 — dashboard ("real-time")** | Console, public map, citizen map, report, data screens, timeline scrub/play | portal | browser walk | Everything shown is measured (dated) or modelled (labelled) | **FP** — not real-time: no sensor or telemetry feed exists, and none was faked |
| **D5 — scalability to other mining contexts** | Species registry (`SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES`); chloride added without retrain | `config/parameters.py` | `test_isr_excursion_panel.py` | Designed-for | **CO** — nothing outside uranium ISR in Jharkhand demonstrated |
| **D6 — CPS contribution** | Data → detection → prediction → vulnerability → tiered alert → explanation → recommended action, closed on the manual CGWB record; physical layer manual | `main.py` scheduler, ingest routes, alert loop | R16 delivery tests, R17 tier tests | "CPS-ready decision support" | **CO** for sensing / **FP** for the decision loop |

---

## 11. What the report may and may not say (one line each)

May: "a physics-informed surrogate with calibrated uncertainty, validated against
the engine and its own gates"; "the extent is governed by K and β"; "alerts are tiered
on IS 10500 and every record answers seven questions"; "the measured 2023 record has
no time axis; the 2000–2021 record has one for the general chemistry only".

May not: "validated against real contamination"; "real-time"; "predicts uranium
contamination in Jharkhand"; "the charge balance shows the laboratory data is sound";
"3-D"; "critical alerts indicate a health emergency".
