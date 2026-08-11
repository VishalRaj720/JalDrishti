# ML Pipeline Readiness Report

**Date:** 2026-08-10 · **Branch:** `fix/pipeline-completion` · **Scope:** `ml_pipeline/` only
**Baseline at start:** 223 tests, deployed artifacts of 2026-08-06
**Now:** **260 tests pass** · **40/41** end-to-end audit checks pass · re-baked + retrained
**Audits closed:** `review.md`, `review2.md`, `review3.md`

---

## 1. Fixed

### Physics / constants (label-affecting)

| # | Finding | What changed |
|---|---|---|
| **D-1** | `RADIUM_RESTORATION_RESIDUAL = 0.99` had gone stale and was a **training label** | Its own comment still named the Thibault soil Kd ("fractured: 500 vs 1.0") that the 2026-08-06 rebase replaced, and it used the pre-V-3 unpaired uranium anchor. Re-running the same derivation on live constants gives **0.806 fractured / 0.571 porous**; served **0.81** (fractured — every Singhbhum deposit pin resolves there, and it is the conservative end). Guarded by a test that *re-derives* it rather than pinning the number |
| **Rebound** | Post-restoration source decayed without bound, passing **below** the measured endpoint (0.023 vs 0.060 at t = 50 yr) | No rebound magnitude invented. Verified the Texas endpoint is already post-rebound — the sheet reads *"composition achieved after restoration was complete"* with **"stability samples"** in its footnote. Once a sweep has run the passive flush may not take the source below that demonstrated stable endpoint. Unrestored scenarios unchanged. New shared `source_strength_fraction()` collapses the two mirrored `f_src` sites into one |
| **V-2** | C₀ envelope was an undocumented P25–P95 window over pseudo-replicated rows | Replaced with the **full observed range of per-mine means** — uranium 9,800–34,440 → **9,000–41,600 ppb**. It had discarded the real minimum (O'Hern 9,000) and invented a maximum no mine reported. `texas_source_provenance()` now reports n = 9 rows / 7 mines |

### Physics / constants (serve-time, no retrain)

| # | Finding | What changed |
|---|---|---|
| **D-3** | Ra-226 ingrowth table used a **one-step** Th-230 calculation | Corrected to the two-step Bateman chain. It had overstated 50-yr ingrowth by **93×**; the conclusion (omit it) is unchanged and now *better* supported — ~2×10⁵ below the parent activity, not ~2,200 |
| **D-4** | ω unit-convention mismatch | `apparent_retardation` expects the **mobile**-side rate; `matrix_transfer_omega` returns the **immobile**-side one. A factor-β (2–20) error if ever enabled. Documented at both ends; path stays gated off |
| **3.3** | Depth-decay extrapolated far past its evidence | Calibrated only 45 m → NAQUIM fracture base, but run below it: **23,000×** reduction at 300 m for a shallow-fracture district. Against Manning & Ingebritsen (1999) that interval is ~**440×**. Now **held at the fracture-base value** below the fracture base |
| **3.6** | Regime-contact K seam, left open by the previous audit | **Clamp deleted, not widened.** It existed so our own correction wouldn't raise the OOD flag — suppressing the signal the user needs. K steps **2.16× → 1.07×** across the contact |
| **NEW** | **The OOD guard could not fire at the low end of K** | Found while fixing the above. Tolerance was 2 % of the *linear* span; for fractured K (0.044–10.6) that is 0.21 — **~5× the trained minimum itself** — so a served K 500× below support raised nothing. Two prior audits called this guard "working" because it was only ever exercised at the high end. Now ratio-based for decade-spanning quantities |

### Serving / UI

| # | Finding | What changed |
|---|---|---|
| **D-2** | Four stale-provenance sites, one **user-facing** | `radium_context.kd_citation` pointed at EPA Table 5.28 — the soil compilation the rebase explicitly rejected ("unusually large … orders of magnitude greater than most researchers"). Now cites the p.95 groundwater measurements and says what Table 5.28 is retained for |
| **D-5** | UI retardation contradicted the physics by 3 orders of magnitude | Showed `Rd ≈ 11` for every species while the engine ran on **720 (U)** and **9,400–11,700 (Ra)**. Both now shown, each labelled |
| **NEW** | Hydro line showed `K = 2.467` while the engine ran on `0.369` | Same class, found during browser verification. Now shows the served K plus the shallow value and the decay that connects them |
| **D-7** | `alkalinity_adjusted_kd` was dead code claiming to be "retained for context" | Wired to that context and surfaced as `kd_ambient_alkalinity_adjusted` |
| **V-7** | β moves migration 47× and was settable with no comparison | Overriding β now returns the default-β answer alongside it |
| **V-8** | `t = 0` gave `area = 0.00 ha` but `migration = 0.336 m` | Fixed in **both** engines; reproduced first, then fixed |
| **V-6** | 12 endpoints, no rate limiting, no caching | Dependency-free token bucket (240/min, burst 60 — above the timeline animation's legitimate rate); ETag + `Cache-Control` on all five deterministic overlays; posture stated in `/api/health` rather than implied to be solved |
| **`wellfield_width_m`** | Label invited reading it as a borehole width | UI now reads **"Well-pattern footprint ⌀"**; response carries a `wellfield_geometry` block. Field name kept — it is a trained feature |

### Data integrity

| # | Finding | What changed |
|---|---|---|
| **V-4** | Excel parser ingested titles, a repeated header and numbered footnotes as data rows | Trailer filter (skips leading preamble, terminates at the first trailer after data starts) plus **pinned row counts** that raise on drift. Removed 1 row from Baseline and 6 from Final Post-restoration; **restoration residuals bit-identical**, confirming no real data was cut |

### Real-world ISR alignment

| # | Finding | What changed |
|---|---|---|
| **R-1** | The excursion criterion was **not the regulatory one** | NUREG-1569 §5.7.8.3 p.138 defines an excursion as **two or more indicators** over their upper control limits, and p.137 explicitly rejects the species this tool led with: *"Uranium is not considered a good excursion indicator because … it may be retarded by reducing conditions."* Built on the conservative species already transported (TDS = the conductivity proxy NUREG names, + sulfate). **Measured: at Jaduguda / gradient 0.005 / t = 20 yr it declares an excursion while the uranium health limit is still clear** — conservative indicators warning first, which is the entire reason the system exists |
| **R-2** | Compliance ring was an uncited round number | Grounded: NUREG-1569 p.139 records licensed rings at **75–180 m**, justification required beyond ~150 m. 100 m sits inside that. Now a bounded input; moving it flags extrapolation (the ML head was trained at 100 m) and moves the reported concentration with the drawn circle |
| **R-4** | Vertical screening had no monitoring context | Reports licensed vertical monitor-well density (1 per 1.6 ha overlying / 3.2 ha underlying, NUREG/CR-6733 §4.3.3) next to the pathway index |
| **Rn-222** | Carried as open | **Assessed and closed as scope, not physics.** My first hypothesis — "a 3.82-day half-life means it cannot reach the ring" — is **false** over part of this model's envelope (28 % survives at the p99 velocity; 4.3 % of rows retain > 1 %) and is recorded as such. Excluded because there is **no Rn-222 source term** for this ore body and because its governing pathway is **atmospheric**, which a saturated-zone model cannot address |

### Process defects

- **D-6** — 12 ungrounded constants moved from prose into a machine-readable `UNGROUNDED_PARAMETERS` register, exposed at `/api/assumptions` and pinned by a test that fails if a value changes without the register moving.
- **Doc drift** — `ARCHITECTURE.md` §6.5 is now **generated** from `metrics.json` by `tools/sync_docs.py`, with `test_docs_in_sync.py` failing the suite when stale. It had drifted across three retrains; the last claimed a migration R² nearly double the deployed one.
- **SHAP artifacts** were from 2026-07-03 — five retrains stale. Regenerated.
- **README** stated `η = Q_net/(q·b·W + Q_net)`; the code implements `min(1, Q_net/(q·b·W))`. Fixed.

---

## 2. Still Open

**One acceptance gate is not met. It is stated here rather than reframed.**

| Item | Status | Why it remains |
|---|---|---|
| **Per-species R²(log) ≥ 0.60 — radium migration (0.516) and compliance (0.431)** | 🔴 **FAILS the project's own Gate-4 bar** | **Not a tuning failure — a label-shape property.** Radium's migration label is **81.8 % exact zeros** and its compliance label is **95.8 % pinned at the 23 mBq/L background**. A single squared-error regressor on `log1p` cannot fit a point mass, and R² divides by a near-zero SST. Both cells *improved* over the deployed model (0.475 → 0.516; 0.403 → 0.431). The documented remedy is a **zero-inflated / two-stage head** — a new ML approach, which this task excluded. **Needs your authorization to build.** |
| 3.4 fracture β / aperture / Dₑ / ω | 🔴 Permanently blocked | No packer or tracer test for the Singhbhum Shear Zone is published. Aperture *is* MC-sampled into the bands; Dₑ is not — `P.FRACTURE` carries no defensible range and inventing one would relabel an assumption as data |
| 3.8 As / Ni / Cu / Co co-contaminants | 🟡 Blocked on source term | Kd data is on disk; how much an alkaline lixiviant mobilises from SSZ ore has never been measured |
| 3.10 Field validation | 🔴 Permanently impossible | No ISR plume has ever been measured in Jharkhand. The bands quantify **parameter** uncertainty, not structural model error |
| ISR indicator panel | ✅ **Closed 2026-08-11** — chloride added as a third excursion-only indicator (2-of-3). No new dataset, no retrain. Alkalinity excluded on measured grounds (contrast 2.5× vs chloride 9.9×) | Still not a licensed programme; `compliance_status` says so permanently |
| Excursion UCL percentage | 🟡 Registered scenario assumption | NUREG's preferred statistical rules need a per-well **temporal** baseline series. Verified: the CGWB file has 397 wells, **one sample each, one year, zero repeats**. Substituting regional spatial spread was tested and rejected (sd(TDS) = 286.5 → UCL 1,965 mg/L, near the BIS limit itself) |

---

## 3. Retrained / Re-baked Components

| Component | Action |
|---|---|
| `outputs/synthetic_training.csv` | **Re-baked** — 900 scenarios × 5 times × 4 species = **18,000 rows**, 48 MC draws, 23 polygons |
| `ml/artifacts/*.joblib` (9 band heads + pex) | **Retrained** on the new labels |
| `metrics.json`, `model_card.json` | Regenerated (v3, 40 features, 4 species) |
| SHAP artifacts | Regenerated (were 5 retrains stale) |
| `outputs/field_batch.csv` | **New** — 120 scenarios at `field_mix = 1.0` (serving distribution), held out |
| Backups | `ml/artifacts_pre_review3/`, `outputs/_pre_review3_backup/` |

**Trigger:** three label-affecting changes (D-1, rebound floor, V-2 envelope), batched into **one** bake per the project's own discipline. **Gate 3 pilot** (100 scenarios) ran first: 0 band-order violations, 0 NaN/inf, off-scale 0.0038 → 0.0025, breach rate 0.186 → 0.172, and every distribution shift explicable — verdict PROCEED.

---

## 4. Latest Model Metrics

All from `ml/artifacts/metrics.json`, generated into `ARCHITECTURE.md` §6.5.

| target | R² (P50) | R² (log) | scenario coverage | rows coverage |
|---|---|---|---|---|
| `affected_area_ha` | 0.7727 | 0.8923 | **0.8611** | 0.9534 |
| `max_migration_distance_m` | 0.5433 | 0.9288 | **0.8822** | 0.9553 |
| `compliance_conc` | −5.5828 | 0.9566 | **0.8606** | 0.9429 |
| `excursion_probability` | 0.9155 | — | — | — |

Per-species R²(log) — **judge on these**; the pooled figure mixes ppb, mg/L and mBq/L:

| target | radium | sulfate | TDS | uranium |
|---|---|---|---|---|
| `affected_area_ha` | 0.890 | 0.785 | 0.824 | 0.945 |
| `max_migration_distance_m` | **0.516** ✗ | 0.888 | 0.892 | 0.932 |
| `compliance_conc` | **0.431** ✗ | 0.904 | 0.968 | 0.859 |

**Field-resampled coverage — the gate `E1_geometry_design.md` §6 mandated and that had never been run (V-5):**

| target | scenario coverage | rows | verdict |
|---|---|---|---|
| `affected_area_ha` | 0.8646 | 0.9599 | PASS |
| `max_migration_distance_m` | 0.9042 | 0.9645 | PASS |
| `compliance_conc` | 0.9125 | 0.9642 | PASS |

The batch is a genuine serving-distribution sample — median gradient **0.94×** the real flow field, against the training set's **1.34×** (reproducing the 1.35× mismatch V-5 measured).

**Not hidden:** pooled `compliance_conc` R²(P50) is **−5.58** (was −3.14). Within-species uranium is also negative in linear space while its log-space fit is 0.859 — the head misses the high-concentration tail. Coverage on that cell holds (0.947). Area R²(P50) also fell (0.842 → 0.773): the wider, evidence-complete C₀ envelope and the rebound floor added real label variance.

**Worst Mondrian cell anywhere:** 0.891 (field-resampled, `fractured|radium|area`) — all 24 cells clear 0.80.

---

## 5. Physics Validation

Independently re-derived, not merely read:

- **Retarded clock** — closed form vs 200,001-point numeric integration: **621.1088 vs 621.1088**.
- **Ogata–Banks second term** — substitution vt = Xc, D_L·t = α_L·Xc verified; the `x > 0` domain gate is correct (without it F_long exceeds 1 upstream).
- **Tang kernel** — σ = θ_m√(R_m·Dₑ)/b_half and the t_w = (x/X_w)·t scaling reduce exactly to the implemented form.
- **Attenuation coupling** — charging k over the *mobile* residence is algebraically identical to decaying only the dissolved fraction. The code was **better justified than its own comment claimed**.
- **Radium residual** — re-derived from live constants: served 0.81 vs derived 0.806.
- **Depth decay** — bounded by Manning & Ingebritsen: model 20× vs global 433× at 300 m.
- **t = 0** — zero area *and* zero migration in both engines.
- **Rebound floor** — source never falls below the measured endpoint; restoration still monotone in sweep length.

Grounded against primary sources: NUREG-1569 §5.7.8.3 (text-extracted, not summarised) for the ring, excursion definition, indicator selection and UCL bracket; NRC wellfield records for bleed (Nichols Ranch 0.5–1.5 %, Hank 2.5–3.5 %); WHO for U 30 µg/L and Ra-226 1 Bq/L; Xu & Eckstein, Gelhar, Goltz & Roberts, Freeze & Cherry for the transport relations.

---

## 6. Real-World ISR Alignment

| Aspect | Before | Now |
|---|---|---|
| Excursion criterion | 1 species over a **health limit** | **≥2 of N conservative indicators over UCLs** (NUREG-1569), health limit reported alongside |
| Lead indicator | Uranium | TDS + sulfate. **Uranium and radium explicitly excluded**, quoting the regulator's own reason |
| Detection ordering | Health breach only | Indicators fire **before** the health limit — verified live in the UI |
| Monitor ring | Uncited 100 m | Grounded 75–180 m, configurable, justification flag beyond 150 m |
| Sampling cadence / response | Absent | 14-day interval and the 60-day controllability basis reported |
| Vertical monitoring | Absent | Licensed well densities reported next to the pathway index |
| Restoration realism | Decayed to zero indefinitely | Held at the demonstrated **stability** endpoint |

---

## 7. Data Gaps / Limitations

**No new datasets were introduced.** One primary regulatory document (NUREG-1569) was consulted as a *citation*, not ingested as data.

- **No SSZ hydrogeology exists publicly** — β, aperture, Dₑ, ω remain foreign-analogue literature (fidelity 3.4).
- **No deep piezometry for Singhbhum** — the vertical gradient is bracketed by the measured monsoon swing, not measured.
- **CGWB chemistry has no temporal replicates** — 397 wells, one sample each. This is what blocks NUREG's preferred statistical UCL rules.
- **No ISR source term** for As/Ni/Cu/Co, chloride, alkalinity or Rn-222 at this ore body.
- **C₀ rests on n = 9 measurements at 7 Texas mines** and scales the concentration field linearly — now reported with the answer.
- **No field validation is possible.**
- **The premise:** commercial ISR is not physically plausible in schist-hosted ore. Every output means *"if ISR-strength lixiviant entered this aquifer"* — never feasibility.

---

## 8. Documentation & UI Consistency

Verified by `validation/end_to_end_audit.py` (**40/41**) and `tests/` (**260 pass**):

- ✅ No stale values in docs or config — metrics block generated and test-locked.
- ✅ No UI value contradicts the physics — retardation and K both verified equal to the served values.
- ✅ No citation points at a rejected source — the radium Kd citation was the last one.
- ✅ Every ungrounded assumption registered, API-exposed and test-pinned (12).
- ✅ Training labels consistent with current physics — C₀ envelope spans 0.99–1.00 of the live range.
- ✅ Documented metrics are from this run.
- ✅ ISR excursion logic matches NUREG-1569.
- ✅ Field-like validation has actually been run and recorded.
- ✅ All tests pass.
- 🔴 One known finding remains unresolved — §2, stated plainly.

---

## 9. Final Verdict

# READY for `product_design.md` — with one named exception

Every critical finding from all three audits is resolved, verified and test-guarded. The physics is re-derived and grounded, the labels match the physics, the conformal guarantee now holds on the distribution users actually query, and no documented or displayed value contradicts what the engine computes.

**The exception, stated so it cannot be missed:** the surrogate's **point estimate for radium** misses the project's own R²(log) ≥ 0.60 bar on two cells (migration 0.516, compliance 0.431). I did **not** move the threshold and did **not** hide it — it is printed in `ARCHITECTURE.md`, returned by the audit as a FAIL, and explained above as a point-mass label problem rather than a tuning problem.

**Why it does not block product design:** the analytical engine serves the authoritative central value for radium, the conformal bands on those cells cover (0.891–0.986 field-resampled, all above the 0.80 gate), and the product surfaces both. Product design does not depend on that point estimate.

**If you consider that gate binding for release**, then the pipeline is **NOT READY** until a zero-inflated or two-stage radium head is built — which is a **new ML approach** and therefore outside what this task authorized. Say the word and I will scope it as its own change.

Nothing in `PRODUCT_DESIGN.md` has been created or modified.
