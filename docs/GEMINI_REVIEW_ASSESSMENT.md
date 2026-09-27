# Assessment of Gemini's review of JalDrishti, with a fix plan for each valid point

## Context

Gemini reviewed the JalDrishti fellowship report and raised four technical flaws, three recommended
improvements and a closing question about how the XGBoost surrogate behaves when lixiviant parameters
leave its training distribution. You asked for each point to be checked against the actual methodology,
code and stated scope, not accepted as written. For each point that holds up you asked for a practical,
grounded fix plan. For each that cannot be fixed within scope you asked what would be needed. **Nothing
is implemented at this stage.**

Method. I read the report source that `docs/project_report/build.py` compiles into the .docx (ch01–ch14,
same text) and checked each claim against the code that produces the numbers: `ml_pipeline/config/parameters.py`,
`physics/transport.py`, `data_prep/feature_engineering.py`, `synthetic/generate.py`, `dashboard/resolve.py`,
`dashboard/vertical_path.py`, `dashboard/server.py`, `dashboard/drift.py`, `ml/predict.py`,
`ml/artifacts/model_card.json`, `backend/app/services/alerts.py` and `docs/LIMITATIONS.md`. I checked the
physics with hand calculations using Python's `math` module only (listed in the Appendix). The engine itself
could not be run: numpy and the geo stack are not installed in the review container, and they were not
installed for this assessment. **Every number below marked "estimate" is a hand calculation,
not an engine output.** Literature was checked by web search; sources are at the end.

---

## Summary verdicts

| # | Gemini's point | Verdict | One-line reason |
|---|---|---|---|
| 1 | A constant, high ambient K_d ignores uranyl-carbonate complexation | **Partly valid; the premise is factually wrong** | The engine already uses an alkaline-suppressed K_d (fractured 0.3–1.0–3.0 L/kg), not 10–50. R_eff ≈ 271 comes from the crystalline matrix term ρb/n ≈ 89, not from a high K_d. But field evidence at lixiviant-strength alkalinity supports K_d ≈ 0.1 L/kg, and the matrix term magnifies that gap about 9×. |
| 2 | Domenico/continuum smooths over fracture channelling | **Valid, and stronger than Gemini argued** | The engine's flowing porosity (0.75%) is 150–3,900 times what the cubic law allows for its own K and aperture range. Its "fast single-fracture" Tang branch runs at the continuum velocity, so it can never show channelling. |
| 3 | Vertical path: borrowed K_v/K_h, dip ignored, harmonic mean under-estimates | **Partly valid** | The borrowed K_v/K_h and the ignored dip tensor are valid, and the project already discloses both. The harmonic-mean criticism is wrong: depth-decay layering applies along a dipping path too. Gemini missed a bigger lever: the upward gradient of 0.005 against a measured 0.03–0.23. |
| 4 | The measured-rock baseline "violates injection mechanics" | **Partly valid; misframed** | Injection at 2,500 m³/day into K = 0.034 m/day is marginal and may exceed fracture pressure, not "near zero". There is also no injectivity check. But the plume barely moves because regional drift is slow, not because of injection physics. |
| Q | Surrogate behaviour when lixiviant parameters go out of distribution | **Real gaps found** | The analytical engine is always the displayed value, and box checks exist. But K_d (fractured) and the top feature Xc_m are never checked, there is no joint-support check, trees extrapolate flat, and the "possible reach" alert is built from the ML P90 even when out of support. |

Minor correction to Gemini: the 2023 CGWB file balances within ±3.2% (report §7.1), not "0.0%". Gemini's
other restatements are accurate: T = 19 m²/day, K = 0.034 m/day, ≥ 3,170 m³/day at Turamdih, 48 boreholes,
R² values, coverage, radium R² of 0.412 with 86.3% exact zeros, and 463 + 533 tests.

---

## Issue 1 — Uranium K_d under alkaline lixiviant (uranyl-carbonate complexation)

### What the code actually does
- `parameters.py:780-801` `KD_RANGES["uranium_ppb"]`: fractured **(0.3, 1.0, 3.0) L/kg**, porous **(0.5, 2.5, 8.0)**,
  explicitly "suppressed by uranyl-carbonate complexation" [EPA 1999; Davis et al. 2004]. The locally measured
  Turamdih soil K_d (69–5,524 L/kg, Maity 2013) is recorded but deliberately **not** served.
- R_eff at Jaduguda: R_m = 1 + ρb·K_d/n_total with n_total = 0.03 and ρb = 2,667.5 kg/m³, so **ρb/n ≈ 89 L/kg**.
  With K_d = 1.0: R_m = 89.9, and R_eff = 1 + β·R_m = 1 + 3 × 89.9 = **270.8**. The 271 comes from low crystalline
  porosity magnifying a *small* K_d, not from a K_d of 10–50.
- Redox trapping of uranium, exp(−k·age), with k = 0.05–0.70/yr (deposit mode 0.35) is already modelled
  (`parameters.py:1185-1201`), so "attenuation is not modelled" is also inaccurate.

### What is valid
1. **The served K_d is still too high for lixiviant-strength alkalinity.** Smith Ranch–Highland (Wyoming ISR)
   column tests at alkalinity **540 mg/L** gave uranium retardation of only **1.47–1.69** relative to a tracer, and
   about 4.3 when alkalinity was lowered to 360 mg/L [Dangelmayr et al. 2017]. Estimate: for sandstone
   (ρb/n ≈ 6) that is **K_d ≈ 0.1 L/kg**, 3–30 times below the served fractured range. The Texas lixiviant this
   engine uses carries **625 mg/L HCO₃⁻** (`parameters.py:424`). In-situ K_d falls with alkalinity (Naturita: 0.5–10.6 mL/g)
   [Davis et al. 2004], and Ca–UO₂–CO₃ ternary complexes suppress sorption further (on quartz, 77% sorbed with no
   Ca → 10% at 8.9 mM Ca) [Fox et al. 2006]. Jharkhand water is Ca–HCO₃ type.
2. **The matrix amplifies the error.** Every 0.1 L/kg of K_d adds about 9 to R_m. Estimate, R_eff against K_d at Jaduguda:

   | K_d (L/kg) | 0 | 0.01 | 0.03 | 0.1 | 0.3 | 1.0 | 3.0 |
   |---|---|---|---|---|---|---|---|
   | R_eff | 4.0 | 6.7 | 12 | 31 | 84 | **271** | 804 |

3. **Chemistry is static.** The plume has one K_d everywhere. There is no link between uranium mobility and how much
   lixiviant is present at a point.

### What is not valid, or overstated
- "Ambient K_d ≈ 10–50 L/kg is applied": false for this code (see above).
- "Uranium moves almost as fast as TDS": this does **not** follow for dual-porosity crystalline rock. Even at
  K_d = 0.1, R_eff = 31 against 4 for TDS. It only holds if K_d is ≲ 0.01 L/kg.
- Two effects Gemini ignored push the other way. (a) The Singhbhum ore is sulphide-rich, and pyrite oxidation
  (FeS₂ + 3.75 O₂ + 3.5 H₂O → Fe(OH)₃ + 2 SO₄²⁻ + 4 H⁺) consumes bicarbonate, so alkalinity near the ore may fall
  and K_d rise. (b) Calcite saturation controls uranium desorption [Dangelmayr et al. 2017].
- **Redox attenuation caps the answer** (estimate). With the served attenuation, uranium's steady extent is
  x* = (v_tracer/k)·ln(C0/threshold) ≈ (0.85 m/yr ÷ 0.35/yr) × 6.3 ≈ **15 m** in measured rock and **≈ 450 m** in the
  ISR-grade hypothetical. Cutting K_d alone would take measured-rock uranium from 3.9 m to about 15 m, not to
  TDS's 30 m, unless attenuation is also revisited (see M2 below).

### Fix plan
1. **Re-anchor the uranium K_d prior** (`parameters.py` `KD_RANGES`). Proposed fractured range (0.03, 0.15, 1.0) L/kg,
   drawn log-triangular (the existing `_kd_sample` does this automatically when the span is > 20×). Porous range
   re-derived the same way. Cite Dangelmayr 2017, Davis 2004 and Fox 2006, and record the Singhbhum-specific gap
   (chlorite–sericite schist with apatite and magnetite).
2. **Alkalinity-coupled K_d at the uranium front** (new function in `physics/transport.py`):
   - Lixiviant mixing fraction f(x,t) = (C_Cl − C_Cl,bg)/(C_Cl,0 − C_Cl,bg), taken from the chloride solution the
     engine already computes for the excursion test (K_d = 0).
   - Local alkalinity = Alk_bg + f·(Alk_lix − Alk_bg), with an optional buffering sink for calcite precipitation
     or pyrite acidity. Endpoints are data: CGWB HCO₃/Ca/pH at the pin, and Texas end-of-mining chemistry in `TX_ISR_Final.xlsx`.
   - K_d_U = g(Alk, Ca, pH), a lookup table computed offline (step 3).
   - Solve for the front position X_U with `scipy.optimize.brentq`. The front falls as K_d rises and K_d falls as f
     rises, so the root is unique. Reuse `front_position` and `effective_capacity_ratio`.
   - Useful property: because R_U,lix (~31) > R_alkalinity (~4), the uranium front stays inside the lixiviant body
     while mining continues. In practice the lixiviant-alkalinity K_d governs, and the coupling matters mainly after
     closure, as ambient water displaces the lixiviant.
3. **Offline PHREEQC K_d study** (new `ml_pipeline/validation/phreeqc_kd_study.py`, **not** a runtime dependency).
   - Use the `phreeqpython`/IPhreeqc wrapper with a generalised-composite surface complexation model (as in Dangelmayr
     2017 and Davis 2004) or the ferrihydrite model, with Ca/Mg–UO₂–CO₃ constants included.
   - Sweep the ambient-to-lixiviant mixing line at the three reference pins, then tabulate g(·) into `parameters.py`
     with provenance.
   - Verify: run a 1-D PHREEQC TRANSPORT column with stagnant (dual-porosity) cells [Lipson et al. 2007; PHREEQC Ex. 13]
     along the plume centreline, and pin a test that the analytical front is within a stated tolerance.
4. **Couple redox attenuation to the same f** (see M2 below).
5. **Mirror every change** in `feature_engineering.build_feature_row` and `generate._draw_params`, so that train
   matches serve. Then **re-bake and retrain the surrogate (v7)**: the K_d prior change invalidates the labels,
   exactly as the R17 β change did.
6. **Report**: rewrite §4.4 and §4.5 Step 4, and the §7.5 wording on the "uranium far behind TDS" ordering. State
   that the ordering depends on K_d ≥ ~0.1 L/kg and on redox attenuation.

**Cannot be fixed without data:** K_d on Singhbhum rock itself. That needs batch and column tests on drill core
with a synthetic carbonate lixiviant (the Dangelmayr design), and BET surface area for the site density.

---

## Issue 2 — Continuum (Domenico) transport against fracture channelling

### What the code actually does
- An equivalent continuum (Domenico/Ogata–Banks) plus a Goltz–Roberts dual-porosity clock, combined with max()
  with a Tang single-fracture "early-arrival" envelope (report §4.5 Step 5).
- **The Tang branch uses the continuum water front**: `generate.py:423` sets `Xw = front_position(v, …)`, with
  v = K·i/φ_mobile, and `transport.py:365-376` scales t_w = (x/Xw)·t. Its fracture velocity is therefore the
  continuum velocity, which is why "the Tang envelope never wins at 20 yr" (`parameters.py:869-871`).
- φ_mobile = **0.0075** at Jaduguda comes from the aquifer polygon's **specific yield**
  (`jharkhand_loader.py:76`). It is **not decayed with depth**, while K is decayed to 15% at 180 m.
- The pinned ω = 1e-3/day implies matrix blocks about **0.12 m** half-width (√(3·De/ω)).
- Gemini's "anisotropy along lineaments" suggestion is already partly in place. E1 rotates the flux direction
  toward the lineament strike (`strike_field.flux_azimuth`) and sets α_T from strike dispersion. The measured
  ±22° direction uncertainty is fanned on the chance map.

### Why the point is valid (estimate, cubic law, K = 0.034 m/day, i = 0.00205)

| Full aperture 2b | Implied spacing | Flowing porosity | Fracture velocity | Engine continuum v |
|---|---|---|---|---|
| 100 µm | 2.1 m | 4.8e-5 | 1.45 m/day | 0.0093 m/day |
| 250 µm (served central) | 32 m | 7.7e-6 | 9.1 m/day | 0.0093 m/day |
| 500 µm | 260 m | 1.9e-6 | 36 m/day | 0.0093 m/day |

- The served φ_mobile is **150–3,900 times** the flowing porosity that the engine's own K and aperture range allow.
- A Tang single fracture at 250 µm and 20 years, ignoring containment and dilution: TDS at **0.62 of the source at
  1 km**; uranium (K_d = 1) at 0.02 at 500 m. That is **hundreds of metres, against the served 30 m and 4 m**.
- At 100 µm the matrix diffusion is strong enough that the reach collapses again.
- Conclusion: **the conceptual-model choice dominates the answer**. The served 48-draw band (K × 0.37–2.46) is far
  narrower than this structural uncertainty. Also, the "0% Domenico error" check (§7.4) verified the maths of the
  continuum equation. It did not test the continuum concept against fractures.

### What cannot be done, and why
The report's reason for declining a full 3-D DFN still holds. There is one lineament within 5 km of Jaduguda, and
no published aperture, spacing or persistence data. A DFN would be almost entirely assumed.

### Fix plan (a "DFN-lite" grounded in the belt's own borehole logs)
1. **Consistency diagnostic** (small, no retrain). For each run, compute the implied spacing
   s = ρg(2b)³/(12μK) and flowing porosity 2b/s. Return them in the response and the assumption register, and warn
   when φ_mobile exceeds the cubic-law value by more than 10×. Add a unit test.
2. **A physically consistent channel branch** replacing the Tang branch's continuum velocity (`transport.py`,
   mirrored in `generate.py` and `feature_engineering.py`):
   - **Conductive fracture set.** Take zone depths and yields from `Datasets/cgwb_exploratory_wells_singhbhum_zones.csv`
     (63 water-bearing zones in the belt boreholes). Split the measured, depth-decayed T among zones by yield:
     T_i = T·y_i/Σy.
   - **Apertures.** Hydraulic aperture 2b_i = (12μT_i/ρg)^(1/3). Transport aperture = c·2b_i with c sampled from 1 to 10,
     because the mass-balance aperture is at least the hydraulic aperture [Tsang 1992].
   - **Velocity and attenuation.** Channel velocity v_i = T_i·i/(c·2b_i). Keep the existing `tang_attenuation` and
     `matrix_sigma` with b = c·b_i. Semi-infinite matrix is valid here, because √(De·t/R_m) ≈ 0.2 m over 20 years,
     far less than s/2.
   - **Monitoring-well concentration** = flux-weighted Σ(T_i/ΣT)·C_i, which is what a ring well samples.
     Containment η applies to channel flux as it does now.
   - **Served value** = max(continuum, channel), the engine's own stated rule ("the larger of the two is used, so fast
     early arrival is not missed"). Aperture and c are sampled in the Monte Carlo, so the band finally carries this
     structural uncertainty.
3. **Exact reference.** Add the Sudicky & Frind (1982) parallel-fracture solution, Laplace domain with numerical
   inversion, following the `validation/exact_reference.py` pattern. Test the channel branch against it at spacings
   where the finite matrix matters.
4. **Retrain in the same v7 bake as Issue 1** (the labels change).
5. **Lineament-tensor alignment (Gemini's improvement #2): low priority.** It is already partly done, and near the
   deposits the lineament data are too sparse. Velocity and channelling, not orientation, drive the answer.

**Field data that would settle it:** a cross-hole tracer test with a conservative and a sorbing tracer (fracture
velocity, flow-wetted surface, β and ω together), packer tests, and borehole televiewer logs for fracture
frequency and orientation.

---

## Issue 3 — Vertical pathway: K_v/K_h, structural dip, harmonic mean

### What the code actually does
- `vertical_path.py:89-117`: the column K is the harmonic mean of the NAQUIM depth-decay law between the ore top and
  the base of Layer 1. `parameters.py:1792-1793`: K_v/K_h = 0.12 (Maheshwaram granite), with the measured band
  0.034–0.61 evaluated on every run. Upward gradient 0.005 (`:1803`).
- LIMITATIONS §1f already states that dip is not modelled (Turamdih about 35° NE, Jaduguda about 40°) and that the
  granite ratio "may understate" vertical flow.

### Assessment
- **Valid:** K_v/K_h is borrowed from another rock type. "Completely different" is an overstatement, because both are
  hard-rock weathered and fissured aquifers, but fissure orientation does differ. Ignoring the dipping-foliation
  tensor is also valid. Estimate with the rotated tensor, K_zz = K∥sin²θ + K⊥cos²θ and K_xz = (K∥−K⊥)sinθcosθ:
  - At θ = 35–40° and K⊥/K∥ = 0.01–0.3, **K_zz/K_h ≈ 0.41–0.70, which is 3.4–5.8 times the served 0.12** (at the top of
    the band already shown).
  - The cross term K_xz ≈ 0.33–0.49 K∥ lets the *horizontal* regional gradient drive vertical flux, about ±40% of the
    vertical term. It adds when flow runs up-dip and subtracts when it runs down-dip.
- **Not valid:** "the harmonic mean severely under-estimates". The K layering is depth-driven fracture closure,
  which also acts along a dipping path. For a straight path at dip θ, ds = dz/sinθ, so the harmonic mean along the
  path is identical to the harmonic mean over depth. "Cross-layer matrix diffusion" misreads the model: transport is
  Darcy leakage with matrix *retention*, and retention applies along foliation fractures too.
- **Partly valid:** fault or shear conduits whose K does not decay with depth would bypass the series column.
  Kudada's artesian deep fractures (105–139 m) show that deep conduits with upward head exist in the belt.
- **Missed by Gemini, and larger:** the upward gradient 0.005 against the measured belt well-pair gradients of
  0.03–0.23, in either direction (report §4.6). That is a 6–46 times lever on vertical flux.

### Fix plan (served analytically only, so no retrain)
1. **Dip-rotated tensor** (new helper in `physics/transport.py`, called from `vertical_path.screening_geometry`):
   - Invert the measured horizontal K for K∥ = K_h/√(cos²θ + a·sin²θ).
   - Compute q_z = K_zz·i_z + K_zx·i_x, with i_x the regional gradient projected on the dip direction (from the
     flow-field azimuth).
   - Take the path along the flux vector, keeping the harmonic mean of the depth law.
   - Report the worst (upward) sign.
2. **Dip data.** Add a per-deposit dip and dip-direction table in `Datasets/`, sourced from the UCIL documents already
   cited plus GSI Bhukosh planar structures. Belt pins default to 30–60°, flagged as such. The anisotropy
   a = K⊥/K∥ is unmeasured: sample it log-uniform over [0.01, 1] as a band.
3. **Structural-conduit route** (a fourth route beside dispersion, leakage and old wells):
   - K does not depth-decay along the conduit.
   - It applies only if a mapped structural lineament lies within a set distance of the wellfield.
   - Its probability is a registered assumption, the same way the 5% old-well probability is.
4. **Upward gradient.** Replace the 0.005 point value with a band built from the measured belt well pairs, or at
   minimum show that band beside the result.
5. **Tests:**
   - θ = 90° gives K_zz = K∥, and θ = 0 gives K⊥.
   - The tensor is symmetric positive-definite.
   - The harmonic mean is invariant to path angle.
   - Arrival time is monotone in dip.

**Needs field data:** oriented packer or cross-hole tests (along- vs across-foliation K), and deep piezometers for
the upward gradient.

---

## Issue 4 — The "two answers" paradox (injectivity at K = 0.034 m/day)

### Assessment
- **Misframed:** the engine does not model injection-driven radial flow beyond the leach-zone disc. The plume "barely
  moves" because regional drift is slow: v = K·i/φ ≈ 0.009 m/day, about 3.4 m/yr for water, then β-retarded. It is
  not because injection into tight rock is being modelled.
- **Overstated:** "injectivity nearly zero or immediate hydrofracturing" (estimate). Using the Muskat five-spot
  formula, Δh = Q_w/(πKb)·[ln(d/r_w) − 0.619], for K = 0.034 m/day and 16–64 m³/day per injector (40–160 injectors
  over 300 m):
  - Ore thickness b = 20 m (the default): **66–151 m** of head rise.
  - b = 130 m: 10–23 m.
  - Fracture-initiation headroom at 180 m, with σ_min between 0.5 and 0.8 of the vertical stress (unmeasured): **about 60–210 m**.
  - Verdict: **marginal**. Injection works at low per-well rates with many wells, and may exceed fracture pressure at
    the upper end.
- **Valid core:** the engine takes Q_in independent of K and has no injectivity check. US Class III rules forbid
  injection pressure that "initiates new fractures or propagates existing fractures" [40 CFR 146.33]. If low
  injectivity were met with higher pressure, the induced fractures would raise K and could open vertical paths. The
  measured-rock baseline is then not the conservative answer for a *production* wellfield. The physically consistent
  pairs are (measured rock, an injectable or accidental volume of lixiviant) and (ISR-grade rock, commercial rate).

### Fix plan (no retrain)
1. **Injectivity module** (`physics/transport.py` helper, called from `resolve`/`server`):
   - Inputs: K at ore depth, ore thickness, wellfield width, pattern spacing d (15–30 m), r_w, depth.
   - Computes N_inj = π(W/2)²/(2d²), the per-well Q, the Muskat head rise, and a fracture headroom band from
     σ_min = 0.5–1.0 σ_v, noting that the stress regime is unmeasured.
   - Returns feasible, marginal or infeasible, plus Q_max.
2. **Serving policy.** Show the verdict on the measured-rock answer and relabel it when the rate is infeasible ("the
   requested rate is not injectable here without stimulation"). Optionally add a rate-capped variant. The
   hypothetical is unchanged. The injectivity verdict never raises alerts.
3. **Report:** a paragraph in §4.5 Step 9 explaining why the baseline plume is slow (drift, not injection), and the
   stimulation caveat for the vertical route.

**Needs field data:** in-situ stress (minifrac or hydraulic-fracturing stress test) and a deposit pumping test.

---

## Issues Gemini missed (found while checking)

- **M1** — φ_mobile is shallow specific yield, served undecayed at ore depth (Issue 2). It is fixed by the
  diagnostic and the channel branch.
- **M2** — Redox attenuation is applied inside the lixiviant body:
  - The lixiviant is oxidising and carbonate-rich, and Ca–UO₂–CO₃ complexes are known to inhibit U(VI) reduction.
  - The regional survey reads oxic ORP (LIMITATIONS §1k).
  - Fix: k_eff = k·(1−f)^m using the same mixing fraction f as Issue 1, with m sampled. This is part of the Issue 1 work.
- **M3** — The upward gradient is a bigger lever than K_v/K_h (Issue 3).
- **M4** — The "possible reach" alert uses the ML P90 even when out of support (see the next section).

---

## Final question — how the surrogate handles lixiviant parameters outside the training distribution

### Current behaviour (verified in code)
1. **The engine comes first.** Every `/api/predict` runs the analytical engine. Its central value, maps, excursion
   probability, vertical screening and published-screening alerts are what users read. The ML model only adds
   P10–P90 bands (`server.py:685`, `:782-803`).
2. **Box checks** (`resolve.py:115-188`, `envelope_violations`) run against the model card:
   - Q_in 200–8,000 m³/day, Q_net 0–400, bleed 0–10%, operation 1–20 yr, horizon 0–20 yr (the UI allows up to 50),
     restoration 0–10 yr (UI up to 30), width 100–800 m, gradient, and uranium attenuation k 0–0.7.
   - Per-species C0 and C_b (uranium C0 9,016–41,497 ppb), with a scale-aware ratio tolerance.
   - K, φ_mobile and R_d per regime.
   - A moved monitoring ring is flagged.
   - Any violation raises a loud "Outside trained support … conformal guarantee void" banner (`RunResult.tsx:208`).
     Nothing is refused.
3. **Routing.** In non-ore zones the ML call for uranium and radium is bypassed.
4. **Drift monitor** (`drift.py`). Each request records the relative gap between the analytical and ML P50. A rolling
   window of 500 raises a "drifting" flag at a 25% median after at least 20 samples. This is a process-health signal,
   not a per-request gate.
5. **Monotone constraints** on the P50 heads. For example, C0 up never moves the prediction down, even outside
   support. P10 and P90 are unconstrained and are re-sorted afterwards.
6. **Physics features.** Xc_m (the engine's own front position) is a feature, so some out-of-distribution changes
   reach the model through physics the engine computes.

### Gaps
- **G1 — flat extrapolation.** Trees are piecewise-constant, so beyond the last split the prediction stops changing.
  - Lixiviant *stronger* than trained (C0 above the maximum) → reach, area and ring concentration **under-predicted**
    (non-conservative).
  - *Weaker* than trained → over-predicted. This already happens: belt-tier uranium C0 = 0.30 × the deposit value
    (`parameters.py:1579`) sits below the 9,016 ppb minimum by design, so the ML answers as if C0 were ~9,016.
- **G2 — K_d is never checked in fractured rock.** For the fractured regime `retardation_Rd` = 1 + β
  (`feature_engineering.py:113-114`). A user K_d slider value (`resolve.py:409`) of, say, 0.05 L/kg, which is exactly
  Gemini's carbonate scenario, raises **no flag**, although uranium trained only on 0.3–3.0.
- **G3 — many trained features are never checked:**
  - Xc_m, the top SHAP feature.
  - PV, τ, η, Péclet, D_L, D_T.
  - Downtime, seasonal amplitude, anisotropy and residual fraction.
- **G4 — no joint-support test.** Inputs that are each in range can still form a combination the model never saw
  (for example, uranium with a small K_d and a large Xc_m).
- **G5 — conformal widening is a constant per (regime, species) cell** (`predict.py:134-135`), so it cannot widen for
  novel inputs, and the guarantee needs exchangeability.
- **G6 — the "possible reach" alert** (`alerts.py:237-262`) draws its geometry from the ML P90 envelope with no
  extrapolation gating. An out-of-support band therefore decides which blocks get a warning.
- **G7 — no lixiviant-chemistry features** (HCO₃, oxidant, pH). A change in lixiviant chemistry is visible only through K_d, which is itself unchecked (G2).

### Fix plan
1. **Engine Monte Carlo fallback band.** When any flag fires, or the per-request disagreement is above a set
   threshold, serve P10/P50/P90 from the engine's own 48 draws. Reuse `mc_param_draws` and `mc_scenario`
   (`predict.py:168-209`): these draws already run for the excursion probability. Label the band "engine Monte Carlo
   (surrogate out of support)".
2. **Complete the support box.**
   - At training time, record per-cell min/max and 1st/99th percentiles for all 40 model features in the model card
     (`train.py`).
   - Extend `envelope_violations` to use it, adding K_d_L_kg per species × regime and Xc_m.
3. **Joint novelty score** (per Mondrian cell).
   - Compute a kNN distance in standardised log-feature space against the calibration rows (18,000 × 40 is small).
   - Turn it into a conformal p-value by ranking against the calibration scores, and flag when p < 0.01. This gives a
     controlled false-alarm rate.
   - Store it as an artifact and score it in `predict.py`.
4. **Gate G6.** When the run is flagged, build the P90 envelope from the engine Monte Carlo P90 (or max of ML and
   engine), and record the basis in the alert explanation. Add a backend test.
5. **Out-of-distribution stress test** (new `validation/ood_stress.py`).
   - Shift sets, labelled with engine MC: C0 × 0.25–4, uranium K_d 0.01–0.3, Q up to 15,000 m³/day, bleed 0–0.2%,
     horizon 20–50 yr, operation up to 30 yr.
   - Report coverage against distance from support.
   - Pin tests: the flag rate on the shift sets is at least a chosen target, and coverage on in-support rows stays at
     or above 0.80.
6. **Widen the training support in the v7 bake** that Issue 1 forces anyway: the new uranium K_d prior, belt-tier C0,
   and horizon to 50 yr. The most common production extrapolations then fall inside support.
7. **Optional (research):** weighted conformal under covariate shift [Tibshirani et al. 2019]. Served runs cluster at
   the deposits, unlike the statewide training set. A domain classifier on logged `simulation_runs` rows versus
   training rows would supply the likelihood-ratio weights.

---

## Suggested order and scope

| Phase | Work | Retrain? |
|---|---|---|
| P1 (small) | OOD fixes 1, 2 and 4; injectivity module (Issue 4); cubic-law diagnostic (Issue 2.1); dip tensor, conduit route and gradient band (Issue 3); report wording | No |
| P2 (medium) | Uranium K_d re-anchoring and alkalinity coupling, attenuation coupling (Issue 1, M2); channel branch (Issue 2.2); training-support widening (OOD fix 6); **one v7 bake and retrain** | Yes |
| P3 (offline) | PHREEQC K_d study and dual-porosity verification; Sudicky–Frind exact reference; OOD stress test; optional weighted conformal | Validation only |
| Field only | Tracer, packer and televiewer work; batch/column K_d on core; deep piezometers; in-situ stress; a deposit pumping test | — |

**Decisions needed before implementation:**
- (a) Should the channel branch enter the **served** answer through the existing max() rule, or be shown as a third
  labelled answer? It could raise measured-rock reach and excursion probability substantially.
- (b) Should the new uranium K_d prior be adopted before the PHREEQC study, or only after it?
- (c) Should the upward-gradient band replace the 0.005 point value in alerts, or only be displayed?

## Critical files (for the later implementation)
- Config: `ml_pipeline/config/parameters.py` (KD_RANGES, U attenuation, VERTICAL, FRACTURE, and new
  INJECTIVITY / CHANNEL / DIP blocks with an assumption-register entry for each).
- Physics: `ml_pipeline/physics/transport.py` (Tang branch velocity, channel branch, uranium K_d-at-front, dip
  tensor, injectivity).
- Keep train == serve in sync: `ml_pipeline/data_prep/feature_engineering.py` and `ml_pipeline/synthetic/generate.py`.
- Serving: `ml_pipeline/dashboard/resolve.py`, `vertical_path.py`, `server.py`.
- Surrogate: `ml_pipeline/ml/train.py`, `dataset.py`, `predict.py`.
- Alerts: `backend/app/services/alerts.py`.
- Validation (new): `ml_pipeline/validation/` (`ood_stress.py`, `phreeqc_kd_study.py`, a parallel-fracture reference).
- Data: `Datasets/` (lixiviant and ambient chemistry endpoints, deposit dip table).
- Docs: `docs/LIMITATIONS.md`, `ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`, report chapters 4, 7, 9 and 12.

**Existing code to reuse:**
- `front_position`, `effective_capacity_ratio`, `matrix_sigma`, `tang_attenuation`, `confining_path_conductivity`.
- `P.depth_decay_factor`, `P.kd_range_for`, `_kd_sample`, `mc_draws`, `excursion_probability`.
- `mc_param_draws`, `mc_scenario`, `envelope_violations` / `_outside`, `MONITOR`.
- `strike_field.flux_azimuth`, the `validation/exact_reference.py` pattern, and the Texas loader for lixiviant chemistry.

## Verification (for the implementation phase)
- Run the engine tests (`pytest ml_pipeline/tests`) and the backend tests (real PostGIS, `backend/pytest.ini`).
  Each new function gets unit tests: the tensor limits, the brentq uniqueness of the K_d-at-front root, the channel
  branch against the parallel-fracture reference, and the injectivity limits.
- Before and after tables at the three reference pins (Jaduguda, belt point, Ranchi), with both answers, in the
  LIMITATIONS style. Re-run `validation/end_to_end_audit.py` and `validation/sensitivity.py`.
- v7 retrain gates: R²(log) ≥ 0.60 per species, scenario coverage ≥ 0.80 in group K-fold, leave-aquifer-out and the
  field test, plus the new OOD stress gates.
- Backend: a test that a flagged run's possible-reach alert uses the engine P90; the existing
  `test_hypotheticals_passthrough.py` stays green.

## Status
Assessment only (2026-09-27). **No code, data or model changes.** Implementation waits for
answers to decisions (a)–(c) above.

## Appendix — hand calculations (Python `math` only; not engine runs)
- R_eff = 1 + β(1 + ρb·K_d/n), with β = 3, n = 0.03, ρs = 2,750 kg/m³.
- Cubic law: K_f = ρg(2b)²/12μ, spacing s = K_f·2b/K_bulk, v_f = K_f·i.
- Tang: C/C0 = erfc(σ·t_w / 2√(t − t_w)), with σ = n·√(R_m·De)/b and De = 5e-6 m²/day.
- Muskat five-spot: Δh = Q/(πKb)·[ln(d/r_w) − 0.619], with r_w = 0.075 m.
- Tensor rotation formulas as given in Issue 3.

## Sources
- Davis et al. 2004, in-situ uranium K_d at Naturita: https://www.sciencedirect.com/science/article/abs/pii/S0883292704000800
- NUREG/CR-6820, Naturita surface complexation modelling: https://www.nrc.gov/regulations-legislation/nureg-series-publications/publications-prepared-by-nrc-contractors/cr6820
- Fox, Davis & Zachara 2006, calcium and U(VI) adsorption: https://www.sciencedirect.com/science/article/abs/pii/S0016703705009439
- Dangelmayr et al. 2017, Smith Ranch–Highland columns: https://www.sciencedirect.com/science/article/abs/pii/S0883292716305807
- Lipson et al. 2007, PHREEQC in fractured bedrock: https://ngwa.onlinelibrary.wiley.com/doi/10.1111/j.1745-6584.2007.00318.x
- PHREEQC Example 13, dual-porosity transport: https://gibbsstudio.io/examples/phreeqc/manual/13%20-%201D%20Dual%20Porosity%20Transport/13%20-%201D%20Dual%20Porosity%20Transport.html
- Sudicky & Frind 1982, parallel fractures (WRR 18(6):1634), via review: https://link.springer.com/chapter/10.1007/978-94-007-1306-2_6
- Tsang 1992, equivalent apertures: https://agupubs.onlinelibrary.wiley.com/doi/10.1029/92WR00361
- NAS, *Rock Fractures and Fluid Flow*, ch. 5: https://www.nationalacademies.org/read/2309/chapter/7
- 40 CFR 146.33, Class III injection pressure: https://www.ecfr.gov/current/title-40/chapter-I/subchapter-D/part-146/subpart-D/section-146.33
- Tibshirani et al. 2019, conformal prediction under covariate shift: https://arxiv.org/pdf/1904.06019
