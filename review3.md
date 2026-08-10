# Pre-Product-Design Audit — completion check + physics/constants re-verification

> **STATUS 2026-08-10 — REMEDIATED on branch `fix/pipeline-completion`.**
> Every finding below has been actioned or explicitly closed with evidence. The
> authoritative current state is the **ML Pipeline Readiness Report** in
> `ML_PIPELINE_READINESS.md`; this document is left as the audit record of the
> pre-fix state, in the same way `review.md` and `review2.md` were.
>
> Two findings changed shape when investigated, and the corrected versions are
> in the readiness report rather than edited in here: **Rn-222** is not
> excluded by decay physics (it survives to the ring across ~4 % of the model's
> velocity envelope) but by the absence of a source term and by its atmospheric
> pathway; and the regime-contact K seam sat on top of a **second, larger
> defect** — the out-of-distribution guard's tolerance was wider than the entire
> low end of K's trained range, so it could not fire there at all.

**Date:** 2026-08-10 · **Scope:** `ml_pipeline/` only · **Baseline:** 223 tests pass (re-run, 52 s)
**Deployed artifacts:** `ml/artifacts/` rebuilt 2026-08-06 (commit `0c9367a`, measured-Kd radium retrain)
**Method:** read the code, re-derived the equations by hand, ran the engine, and checked the
load-bearing constants against primary sources (NUREG-1569 pulled and text-extracted, not summarised).
**Constraints honoured:** no new datasets proposed as necessary; no new ML approach proposed.

---

## Verdict in one paragraph

**The planned work is NOT complete.** Every item from the *first* audit (`review.md`) has landed, and
two of the eight items from the *second* (`review2.md`) have — V-1 (Domenico error envelope, then the
Ogata–Banks restore and retrain) and V-3 (paired restoration estimator). **Six remain open (V-2, V-4,
V-5, V-6, V-7, V-8)**, all verified still-open in the current tree. Separately, the physics re-check
found **one live defect that is baked into the training labels** (radium restoration residual now
contradicts its own derivation after the 2026-08-06 Kd rebase), **four stale-provenance defects**
(three config comments and one *user-facing* citation that points at the document the code explicitly
rejected), **one arithmetic error in a documented omission**, **one latent unit-convention mismatch**,
and **the same documentation-drift failure the project has already caught twice** — `ARCHITECTURE.md`
§6.5 now under-reports the deployed model badly enough to matter. The equations themselves are sound:
I re-derived the retarded clock, the Ogata–Banks pair, the Tang kernel and the retardation/attenuation
coupling, and all four are correct — the attenuation treatment is in fact *better* justified than its
own comment claims.

---

# PART 1 — Completion status

## 1.1 Closed and verified

| Workstream | Status |
|---|---|
| Phases 0–4 (physics → generator → training → dashboard) | ✅ committed |
| Phase-2 D1–D5 (flow field, strike field, NAQUIM vertical, ore grades, shear-zone T) | ✅ committed |
| Phase-2 Stages A–H (hardening → E1 geometry → atomic cutover) | ✅ committed |
| `review.md` remediation Phases 0–7, rounds 1–3 | ✅ committed (`f27427a` … `289137e`) |
| **V-1** Domenico exact-solution benchmark | ✅ `DOMENICO_ERROR_ENVELOPE.md`; the product approximation measures **±0.1 %** in this parameter box — the West et al. 80 % threat does not apply here; the real 17–42 % low bias was the dropped second Ogata–Banks term, now restored and retrained |
| **V-3** paired restoration estimator | ✅ `_paired_residual_ratios()`; median-of-ratios + real per-mine spread now sampled |

## 1.2 Open — `review2.md` findings never actioned (all re-verified today)

| # | Finding | Evidence it is still open |
|---|---|---|
| **V-2** | Uranium C₀ rests on n = 9 rows / 7 mines; P25–P95 window undocumented and asymmetric | `texas_loader.py:260` still `quantile(0.25), quantile(0.95)`. Ran it: n = 9, 7 mines, full span 6 800–41 600 ppb, served envelope 9 800–34 440. `source_term_context` still reports no sample size |
| **V-4** | Excel parser ingests footnotes/repeated headers as rows | No plausibility gate, no pinned row-count assertion in `texas_loader.py` |
| **V-5** | Conformal 80 % calibrated on the generator distribution, not the served one | No `field_resampled` key in `metrics.json`, no test. `E1_geometry_design.md` §6 gate 5 mandated this batch; it has never been run against a deployed model |
| **V-6** | 12 endpoints, zero auth, zero rate limiting, no caching on 0.48 MB GeoJSON | Confirmed: 12 `@app.` routes, no `slowapi`/`ETag`/`Cache-Control` |
| **V-7** | β moves migration 33× and is user-settable with no comparative answer | `beta: float \| None = Field(None, ge=0, le=50)` unchanged; no default-β answer returned alongside an override |
| **V-8** | t = 0 inconsistency | **Reproduced today at Jaduguda:** `area = 0.0000 ha` but `migration = 0.3356 m`. Nothing has been injected; both should be 0 |

## 1.3 Open — fidelity-matrix rows and named follow-ups

| Item | State |
|---|---|
| 3.4 fracture β / aperture / Dₑ / ω | 🔴 **Genuinely blocked** — no SSZ packer or tracer test is published. Labelling verified complete and honest. Aperture *is* now MC-sampled; Dₑ is not |
| 3.6 third seam | 🔴 **Open and disclosed.** At a genuine regime contact (85.399 °E, 23.312 °N) K still steps **2.16×** because `depth_decay_factor` is clamped into *per-regime trained-K boxes* with different floors. No test in `test_spatial_seams.py` pins it — an ML training artefact is setting the size of a physical discontinuity |
| 3.7 horizontal monsoon transient | 🟡 Measured and **declined on evidence** (gradient rotates 2.5° p50, zero cells reverse). This is a legitimate close, not a gap |
| 3.8 As/Ni/Cu/Co | 🟡 Blocked on source term, not sorption |
| 3.9 Rn-222 | 🔴 Not built. Standard ISR licensing metric |
| 3.10 field validation | 🔴 Permanently impossible |
| Post-restoration **uranium rebound** | 🔴 Flagged 2026-07-13, never built. The source only decays; real ISR sites rebound as residual U re-oxidises. The `RESTORATION_RESIDUAL_FLOOR = 0.02` is a stand-in, not a rebound model |
| `wellfield_width_m` UI label | 🔴 Open (round-2 note): it is the *diameter of the circular well-pattern footprint*, and the label invites reading it as a borehole width |
| Radium zero-inflated head | 🔴 Scoped in `0c9367a`, not built |

## 1.4 Open — the Gate-7 documentation contract is broken again (third time)

`ARCHITECTURE.md` carries its own warning box: *"Numbers in §6.5 are copied from `metrics.json`. If the
two ever disagree, the file is right."* They disagree, after the 2026-08-06 retrain:

| target | §6.5 says | `metrics.json` says | gap |
|---|---|---|---|
| `affected_area_ha` R²(P50) | 0.868 | **0.8418** | −0.03 |
| `max_migration_distance_m` R²(P50) | 0.896 | **0.5346** | **−0.36** |
| `compliance_conc` R²(P50) | 0.738 | **−3.1366** | **−3.87** |
| `excursion_probability` R² | 0.949 | 0.9398 | −0.01 |
| scenario coverage | 0.877 / 0.896 / 0.867 | 0.8567 / 0.8833 / 0.8567 | all still ≥ 0.80 ✓ |

Two consequences beyond the numbers:

1. **§6.5's radium exemption is now stale.** It says radium's migration and compliance targets are
   "zero-variance … R² divides by SST ≈ 0". Since the Kd rebase they have real variance and defined
   R². The honest replacement is not an exemption but a **reported miss**: `r2_log_by_species` for
   radium is **0.4752** (migration) and **0.4027** (compliance), both under the project's own Gate-4
   bar of 0.60. Commit `0c9367a` states this plainly; no document does.
2. **Uranium `compliance_conc` linear R² is −5.79 *within a single species***, so the
   "pooled number mixes ppb/mg/L/mBq/L" defence does not cover it. Log-space is 0.857, i.e. the P50
   head misses the high-concentration tail on the tool's headline regulatory metric. Coverage holds
   (0.947/0.971), so the bands are still doing their job — but the point estimate is soft exactly
   where a regulator would read it.

`README.md:60` is also stale: it states `η = Q_net/(q·b·W + Q_net)`, while the code (and
`transport.py`'s own docstring) implement `η = min(1, Q_net/(q·b·W))`. Different asymptote — the
README's form can never reach complete capture, the code's can, deliberately.

---

# PART 2 — Physics, constants and equations re-verification

## 2.1 Re-derived by hand and CONFIRMED correct

| # | Item | Check |
|---|---|---|
| 1 | **Retarded clock** `I(t) = ∫₀ᵗ dt'/R_app(t')` | Integrated ∫dt/(A − Be^{−at}) = t/A + ln(A − Be^{−at})/(aA) with A = 1+β, B = β, A−B = 1. Code's `log1p(−β·expm1(−at))/(a(1+β))` is that identity, and the `log1p/expm1` form is the numerically right choice at β ~ 10⁶ |
| 2 | **Ogata–Banks second term** | With vt = Xc and D_L t = α_L·Xc ⇒ v/D_L = 1/α_L and 2√(D_L t) = 2√(α_L Xc). `_ogata_banks_second_term` matches exactly. The `x > 0` domain gate is correct — the term is only defined on the semi-infinite domain, and without the gate F_long exceeds 1 upstream |
| 3 | **Tang/Sudicky kernel** | σ = θ_m√(R_m·Dₑ)/b_half, argument σ·t_w/(2√(t−t_w)); with t_w = (x/X_w)·t this collapses to `0.5·σ·√t·r/√(1−r)`. Correct |
| 4 | **Matrix retardation** R_m = 1 + ρ_b·Kd/θ_m, ρ_b = (1−n)ρ_s | Correct, and correctly the *only* place Kd acts in fractured rock |
| 5 | **Attenuation residence time** | Charging k over the **mobile** residence x/v_mobile is algebraically identical to applying a bulk rate k/R over the retarded travel time — i.e. it is the textbook "decay acts on the dissolved fraction only" treatment. The comment defends it as merely "not double-counting"; it is in fact the correct form, and the code deserves the stronger claim |
| 6 | **Xu & Eckstein** α_L = 0.83(log₁₀L)^2.414 | Matches the published relation |
| 7 | **mD → K** | 1 mD → 8.36×10⁻⁴ m/day. Verified |
| 8 | **Decay constants** | Ra-226 1600 yr, Th-230 75 380 yr, U-234 245 500 yr, Th-234 24.1 d, Pa-234m ~1.2 min — all correct |
| 9 | **Regulatory limits** | WHO provisional U 30 µg/L ✓; WHO Ra-226 guidance 1 Bq/L ✓; BIS IS 10500:2012 SO₄ 200/400, TDS 500/2000 ✓; EC→TDS 0.64 ✓ |
| 10 | **Bleed 0.5–3 %** | Confirmed against NRC wellfield data: Nichols Ranch 0.5–1.5 %, Hank 2.5–3.5 % of circulating lixiviant. The 0–8 % training envelope correctly brackets it as failure/aggressive states |
| 11 | **Compliance ring 100 m** | **In range and now citable.** NUREG-1569 §5.7.8.3 p.139: *"used monitor wells as far as 180 m [600 ft] and as near as 75 m [250 ft] from the well field edge"*, with justification required beyond ~150 m [500 ft]. The constant is defensible — it just carries **no citation in config** |
| 12 | **Domenico product approximation** | Their own 240-parameter benchmark measures ±0.1 % on the centreline in this box. Sound |

## 2.2 Defects found

### D-1 · **HIGH · `RADIUM_RESTORATION_RESIDUAL = 0.99` was invalidated by the 2026-08-06 Kd rebase — and it is a training label**

The constant carries its own derivation: anchor `N/Rd_U = ln(1/0.066) = 2.718`, then
`residual_Ra = exp(−2.718 · Kd_U/Kd_Ra)`. The comment computes 0.994–0.997 from **the old Kd values it
names in the text: "fractured: 500 vs 1.0" and "porous: 2400 vs 2.5"**. Commit `d90b915` replaced those
with measured groundwater values. Re-running the *same derivation* on the *current* constants:

| regime | Kd_U | Kd_Ra (mode) | ratio | residual the derivation implies | served |
|---|---|---|---|---|---|
| fractured | 1.00 | 13.2 | 13.2× | **0.814** | 0.99 |
| porous | 2.50 | 13.2 | 5.3× | **0.598** | 0.99 |

So the model asserts a hydraulic sweep removes 1 % of the radium source when its own stated physics now
says 19–40 %. This is the *exact* failure pattern the fidelity matrix already documented once
("fix 3.3 silently voided the guarantee 3.6 had just established, and nothing checked") — and it is
worse here, because `restoration_endpoint_for()` feeds both `synthetic.generate` and `ml.predict`, so
0.99 is **baked into the 18 000-row training set**. Fixing it changes labels ⇒ re-bake + retrain.

### D-2 · **MEDIUM · Four stale-provenance sites, one of them served to users**

- `dashboard/resolve.py:502` — `radium_context.kd_citation` still reads *"EPA 402-R-04-002C Vol III
  Table 5.28 (Thibault et al. 1990 compilation)"*. That is the **soil compilation the rebase
  explicitly rejected** ("orders of magnitude greater than those reported by most researchers"; wrong
  medium). The served Kd band now comes from p.95 groundwater measurements. **A user reading
  provenance is being pointed at the superseded source.**
- `parameters.py:125–137` — the `RADIUM_KD_RANGES` header still opens with "Sand 500 | Silt 36 000 |
  Clay 9 100 … hence Kd three to four orders of magnitude above the uranium values", contradicted by
  the revision note immediately below it.
- `parameters.py:237–239` — "Radium's Kd exceeds uranium's by ~500× … to ~960×". Now 5.3–13.2×.
- `parameters.py:209` — "partition into water against a Kd of 500–2 400 L/kg". Now 6.7–13.2 central.

### D-3 · **LOW (documentation) · The Ra-226 ingrowth table overstates ingrowth by up to 4 600×**

The config tabulates the fraction of secular equilibrium as `1 − exp(−λ_Th230·t)` — the growth of
**Th-230**, not of Ra-226. Freshly deposited U(IV) carries no Th-230 (it is insoluble and was left
behind), so the chain is two-step: Th-230 must grow in *and then* feed Ra-226.

| t | config says | two-step chain | overstated |
|---|---|---|---|
| 1 yr | 0.00092 % | 2.0×10⁻⁷ % | 4 600× |
| 50 yr | 0.046 % | 4.9×10⁻⁴ % | **93×** |
| 1 000 yr | 0.915 % | 0.173 % | 5.3× |
| 10 000 yr | 8.79 % | 6.84 % | 1.3× |

**The conclusion is unaffected and in fact strengthened** — at 50 yr the ingrown radium sits ~2×10⁵×
below the uranium activity, not the stated ~2 200×. `RADIUM_INGROWTH_MODELLED = False` is right. Only
the arithmetic in the justification needs correcting, and the "revisit past ~1 000 yr" trigger is
comfortably conservative.

### D-4 · **LOW now, HIGH if ever enabled · ω unit-convention mismatch**

`apparent_retardation`/`retarded_clock` use `a = ω(1+β)/β`. Solving the coupled mobile/immobile system,
the non-zero eigenvalue is α(1/θ_m + 1/θ_im); that equals ω(1+β)/β **only if ω ≡ α/θ_mobile**. But
`matrix_transfer_omega` derives `ω = 3Dₑ/(R_m L²)`, which is the standard slab approximation for the
**immobile-side** rate α/θ_immobile — for which the correct clock constant is `a = ω(1+β)`.

Feeding one into the other is a **factor β (2–20)** error in how fast the retarded clock matures.
`OMEGA_FROM_GEOMETRY = False`, so nothing served or trained is affected today — this is latent, and
the honest fix is one line of comment in `matrix_transfer_omega` recording which convention the clock
expects, so the flag cannot be flipped on into a silent 8× error.

### D-5 · **MEDIUM · The displayed `retardation_Rd` is not the retardation the physics uses**

`resolve.py:442` reports `retardation_Rd = 1 + β` — species-blind by design (Option A of the
remediation brief). Measured at fractured Jharkhand materials with β = 8:

| species | Kd | UI shows Rd | kinematics use 1 + β_eff | ratio |
|---|---|---|---|---|
| TDS | 0.00 | 9.0 | 9.0 | 1× |
| sulfate | 0.05 | 9.0 | 44.6 | 5× |
| uranium | 1.00 | 9.0 | **720.3** | **80×** |
| radium | 13.20 | 9.0 | **9 398.6** | **1 044×** |

Option A was the right *modelling* call (it keeps the feature contract and OOD box intact). But the
number is on a user-facing surface next to "why is this plume slow", and it is wrong by three orders of
magnitude for radium. Serve-side only, no retrain: report `1 + β_eff` as the effective retardation and
keep raw β as the tracer capacity ratio.

### D-6 · **Ungrounded constants that are NOT on the fidelity matrix's 3.4 list**

Row 3.4 does an honest job on β / aperture / Dₑ / ω. These carry no citation and no flag:

| constant | value | note |
|---|---|---|
| `SOURCE_BV_GAIN` / `SOURCE_BV_REF` | 0.40 / 2.0 BV | Sets the tanh source-widening cap. Affects the leach disc, which is **76–97 % of the headline `affected_area_ha`**. No source |
| `VERTICAL["wellbore_failure_prob"]` | 0.05 | Self-labelled "screening". A real anchor exists and is now in hand — NUREG/CR-6733 §4.3.3 (cited by NUREG-1569 p.139) analyses vertical-excursion detection risk against the licensed spacing of one well per 1.6 ha overlying / 3.2 ha underlying |
| `VERTICAL["Kv_Kh_by_regime"]` | 0.03 / 0.008 | "re-fit from GSI Bhukosh structure" — never done |
| `VERTICAL["upward_gradient"]` | 0.005 | Now bracketed seasonally by 3.7, but the baseline itself is unsourced |
| `IRREGULARITY{…}` | various | Comment says outright "Placeholder ranges -- to be re-fit from TCEQ excursion records"; never done. Enters the MC that produces the bands |
| `INCREMENTAL_FLOOR` | 0.10 | A policy choice, not physics. Fine — but it should say so |

### D-7 · **LOW · Dead code**

`alkalinity_adjusted_kd()` and `KD_ALKALINITY` have no callers outside `test_physics_laws.py`. The
comment already says they are retained "for OPTIONAL ambient far-field context only". Either wire them
to that context or delete them — a tested-but-unused Kd modifier is a trap for the next editor.

---

# PART 3 — Making the hypothetical ISR behave more like a real ISR operation

All of these use data already on disk or now-cited public regulatory guidance. **None needs a new
dataset. None changes the ML approach.**

### R-1 · The excursion criterion is not the one real ISR uses (highest realism gain)

NUREG-1569 p.138: *"an excursion is defined to occur whenever **two or more** excursion indicators in a
monitoring well exceed their upper control limits"*, from a minimum of three indicators that must be
*"not significantly attenuated by geochemical reactions"* — in practice **chloride, conductivity
(explicitly noted as correlated to TDS) and total alkalinity**.

The tool instead declares an excursion when **one contaminant** exceeds a **health limit** (BIS/WHO) at
the ring. Those are different events, and the tool's is systematically *later*: uranium is the most
retarded species it models, so uranium-based excursion probability collapsed to 0.014 in the fractured
deposit cell while sulfate and TDS retained 0.152 / 0.310 — the Gate-3 doc already noticed this is "how
real ISR monitoring actually works" but the metric was never reframed.

**Buildable now:** TDS is already modelled and is the conductivity proxy the regulator names; sulfate
is already modelled and unretarded. Add an ISR-convention indicator excursion (≥2 of the conservative
indicators above a baseline-derived UCL) alongside the existing health-limit breach, and rename the
current one for what it is. Serve-side; no retrain.

### R-2 · Ground and expose the monitor-well ring

`COMPLIANCE_BUFFER_M = 100.0` is defensible but uncited. Cite NUREG-1569 §5.7.8.3 (75–180 m observed,
justify beyond ~150 m), make it an input rather than a constant, and let a user place the ring where a
regulator would. Two further real constraints are free to surface from the same source: perimeter wells
are sampled **at least every 2 weeks**, and an acceptable technical basis is that *"a theoretical
excursion can be controlled at the monitor well locations within 60 days of detection"* — which turns
the tool's reach-vs-time curve into a **detectability and response-time** statement, the thing an
operator is actually judged on.

### R-3 · Post-restoration rebound

Still the largest *physical* realism gap that is not data-blocked in principle. The source only ever
decays; real leached zones rebound as residual U(IV) re-oxidises. The config already cites the evidence
(Wyoming rebound study, EPA's 30-yr monitoring rule) to justify the flush half-life — the same evidence
argues the monotone decay is optimistic. Label-affecting ⇒ bundle with any retrain.

### R-4 · Vertical excursion realism

NUREG/CR-6733 §4.3.3 gives licensed vertical monitor-well density (1 per 1.6 ha overlying, 1 per 3.2 ha
underlying) and the associated detection-risk analysis — a real anchor for `wellbore_failure_prob` and
for whether a vertical excursion would even be *seen*, replacing a bare 0.05.

### R-5 · Framing fixes that cost nothing

- `wellfield_width_m` → say "well-pattern footprint diameter" (open since round 2).
- `operation_years` up to 20 already carries the Tier-2.9 caveat that real single wellfields run 1–3 yr;
  the default should sit in the real range with the long tail labelled as sequential-unit compression.
- `affected_area_ha` should be labelled *wellfield footprint + migrating increment*, since the
  benchmark measured it as 76–97 % leach disc. It is currently read as a transport result.

---

# PART 4 — Recommended order of work

**Tier 1 — correctness, no retrain (do before `product_design.md`):**
1. D-2 stale citations (one is user-facing) · D-3 ingrowth arithmetic · D-4 ω convention note
2. §6.5 / README truth-up, including the radium Gate-4 miss and the uranium compliance tail (D-1.4)
3. V-8 t = 0 · D-5 effective retardation on the UI · R-5 labels

**Tier 2 — no retrain, real work:**
4. V-5 field-resampled coverage gate (the 80 % claim is currently true-of-the-generator)
5. R-1 ISR excursion criterion · R-2 monitor-well ring · V-7 β comparative answer
6. V-2 / V-4 Texas provenance and parser hardening
7. 3.6 third seam (regime-contact K clamp), with the test that is missing

**Tier 3 — needs a re-bake + retrain, so batch them into one:**
8. **D-1 radium restoration residual** (the one live label defect) · R-3 rebound · radium zero-inflated head

**Tier 4 — deployment gate, before the portal in `product_design.md` is exposed:**
9. V-6 auth, rate limiting, GeoJSON caching

---

## Honest limits of this audit

- I re-derived Tang, Goltz–Roberts and Ogata–Banks against their standard published forms and checked
  the implementation is internally consistent; I did not re-read Tang et al. (1981) line by line.
- I did not re-run training, so all model metrics quoted are from the committed `metrics.json`.
- The 3.4 family (β, aperture, Dₑ, ω) remains ungrounded locally. I re-confirmed the labelling is
  complete and could not improve the grounding — no public SSZ hydrogeology exists.
- D-1's implied residuals (0.814 / 0.598) are what *the config's own derivation* yields on the current
  Kd values. Whether that derivation is the right model for a pore-volume sweep of a sorbing solute is
  a separate question — but 0.99 is not defensible under either reading, since it was computed from
  Kd values the code no longer holds.
