# What this system does not know

**One register, kept current.** Everything JalDrishti is uncertain about, blocked on, or
deliberately assuming — physics, data and product. If a number in this product is weaker
than it looks, it is written down here.

The rule this file exists to enforce: *if a model misses a threshold, report it rather
than moving the threshold.* Nothing below has been softened to make the project look
finished.

**Last consolidated:** 2026-09-20. Sources: the ML pipeline readiness review
(2026-08-12), the R10 audit (2026-08-19), the **R13 deployment-readiness audit
(2026-08-24)**, the **R14 pre-deployment changes (2026-08-25)**, R15 (2026-08-26),
**R16 (2026-09-16)**, which reviewed the deployed portal against the
proposal's deliverables and the eight monthly reports, and **R17 (2026-09-20)**,
the pre-report audit (`docs/PRE_REPORT_AUDIT_AND_PLAN.md`) and the five items it
implemented: the β retrain (§1d, now closed), alert tiers with a structured
record (§4h), plume timeline frames (§4h), hydrochemical QA (§3, §4h) and the
global sensitivity analysis (§1e). The full chronological review record — including findings
that were later **retracted**, which is why it is kept rather than summarised — lives in
`docs/local/audit-record/` and is not tracked in git.

---

## 0. The premise, before anything else

**No ISR uranium mine operates in Jharkhand.** Every site in this system is hypothetical.
Commercial ISR is not physically plausible in schist-hosted ore, so every output means
*"if ISR-strength lixiviant entered this aquifer"* — **never feasibility, never a plan,
never a permit.**

**No field validation is possible, and never will be.** No ISR plume has ever been
measured in Jharkhand. The conformal bands quantify **parameter** uncertainty. They do
not quantify structural model error, and nothing in this product can.

---

## 1. Open — the model misses one of its own gates

| Item | Status | Why |
|---|---|---|
| ~~**Plume extent rests on β, an unmeasured matrix-storage ratio; the band samples inside the assumption**~~ | ✅ **Closed (R17, 2026-09-20) — see §1d** | β is now derived from the run's own porosities (3.0 at Jaduguda, 1–4 across the lithology table), the training prior is log-uniform on [0.3, 20] and the Monte-Carlo band spans a factor of 4 either side. The v4 retrain passes every gate. β is still not a *measurement* — §2 stands |
| **Per-species R²(log) ≥ 0.60 — radium migration (0.412, v6)** | 🔴 **Fails the project's own Gate-4 bar** | Not a tuning failure, a label-shape property. Radium's migration label is **86.3 % exact zeros** (v6). A squared-error regressor on `log1p` cannot fit a point mass, and R² divides by a near-zero SST. The remedy is a **zero-inflated / two-stage head** — a new ML approach, not authorised; the conformal band on those cells still covers (0.91 fractured, 0.95 porous). **Radium compliance now clears the bar (0.235 → 0.746, v6 retrain 2026-09-26), but read why:** its label is still 96.8 % pinned at the scenario's own background, and v6 varies that background (10–23 mBq/L, the BARC survey blend) instead of fixing it at 23 — so the head learns "ring = background" from a feature. The gain is real for serving and says nothing new about radium transport |

**Why this does not invalidate the product:** the analytical engine serves the
authoritative central value for radium. The conformal bands on those cells cover
0.951–0.963 field-resampled (v6, 2026-09-26; every target passes at 0.90–0.92
scenario coverage), all above the 0.80 gate. The product shows both, and labels
which engine produced which. **If you consider that gate binding for release, the
pipeline is not ready** until the two-stage head is built.

---

## 1d. Closed (2026-09-20) — the plume's extent rested on one unmeasured number, and the band did not cover it

**Raised by the project owner from the published Jaduguda report:** *"the spread
is only 1 to 10 m — is the impact really that small?"* Rechecked against the
engine itself rather than argued about.

**What the served run says.** Jaduguda site, uranium, 8 yr operation, 3 yr
sweep, evaluated at 20 yr: footprint 8.2 ha (of which 7.9 ha is the leach zone
itself), **migration 11.7 m** beyond the wellfield, 1 ppb at the monitoring ring
(= background), ML band 0–32 m. Resolved inputs: K at ore depth 0.53 m/day,
gradient 0.00185, mobile porosity 0.0075 → fracture-water velocity ≈ 47 m/yr;
**effective retardation 900**; natural attenuation 0.28/yr.

**What decides it.** The same run with one input changed at a time
(analytical engine, `ml_pipeline.dashboard.server.api_predict`, 2026-09-16):

| Change | Migration | At ring | R_eff |
|---|---|---|---|
| as served (β = 10, k = 0.28/yr) | 11.7 m | 1 ppb | 900 |
| attenuation off (k = 0) | 13.7 m | 1 ppb | 900 |
| horizon 50 yr | 17.1 m | 1 ppb | 900 |
| gradient ×5 (0.01) | 39.6 m | 1 ppb | 900 |
| β = 20 / β = 2 (the Monte-Carlo range) | 8.0 m / 28.3 m | 1 ppb | 1,799 / 181 |
| **β = 3 (what the tool's own porosities imply)** | **22.5 m** | 1 ppb | 271 |
| β = 0.5 | 61 m | 1 ppb | 46 |
| β = 0.1 | 153 m | **665 ppb** | 10 |
| β = 0 (no matrix storage) | **938 m** | **2,644 ppb** | 1 |
| sulfate, as served / β = 0 | 37 m / 741 m | 227 / 722 mg/L | 56 / 1 |

Attenuation, the gradient and the horizon barely move the answer. **One
parameter does: β, the dual-porosity capacity ratio** — how much contaminant
the rock matrix between fractures stores per unit of fracture water. The engine
applies it as `R_eff = 1 + β·R_m` (Goltz & Roberts 1986; `effective_capacity_
ratio`), with R_m ≈ 90 for uranium at Kd = 1 L/kg and 3 % matrix porosity, and
a pinned transfer rate that reaches that equilibrium in ~2.7 yr.

Three things about β are already on record and now matter together:

1. **No Jharkhand measurement constrains it** (§2, fidelity matrix row 3.4:
   no packer or tracer test for the Singhbhum Shear Zone is published). The
   value is a foreign-analogue literature range, (2, 8, 20), served at its
   mean, 10.
2. **The tool's own porosities imply 3, not 10.** β is defined as
   θ_immobile/θ_mobile; with total porosity 0.03 and mobile 0.0075 that is
   3.0. The engine carries two statements of matrix capacity that disagree by
   a factor of three.
3. **The engine's own docstring says the pinned transfer rate over-retards
   uranium at early time** (`matrix_transfer_omega`: physically ~13.7 yr to
   load the matrix, pinned to reach it in 2.7). Over a 20-year horizon that
   is most of the run.

**The consequence for what the product claims.** The P10–P90 band is drawn
from a Monte Carlo that samples β *within* (2, 8, 20). Every value in that
range leaves the plume inside 30 m. The band therefore expresses the
parameter's uncertainty **inside an assumption**, not the uncertainty *of* the
assumption — exactly the structural error §0 says no band here quantifies.
A reader of the 0–32 m band would not learn that a β of 0.5 — a defensible
value for a poorly connected matrix over two decades — gives 61 m, or that
β of 0.1 puts 665 ppb at the monitoring ring.

**Direction of the error.** Small-plume, not large. Every candidate correction
makes the served extent larger: deriving β from the tool's own porosities
(×2), a diffusive rather than first-order matrix clock (the docstring's own
"rigorous upgrade"), or a lower β prior. None makes it smaller. So the served
figures should be read as **the immobile end of a range this tool cannot yet
bound**, and the report says so (R16).

**What was done (R17, 2026-09-20) — the fourth sanctioned change to the frozen
pipeline.** β is a training feature, so this was a re-bake (900 scenarios × 48
draws, 18,000 rows, ~2 h), a retrain, a conformal recalibration, the
field-resampled coverage gate and `sync_docs`. Three changes, in
`config/parameters.py`, `dashboard/resolve.py` and `synthetic/generate.py`:

1. **The served central β is derived, not served.** `β_por = (n_total −
   φ_mobile)/φ_mobile` from the porosities the run already resolves with
   provenance: 3.0 at Jaduguda, 1.0–4.0 across the lithology table, never 10.
   This is a definition, not a calibration — it makes the engine's two
   statements of matrix capacity agree. `hydro.beta_basis` says which path
   produced the value; a user override still wins.
2. **The training prior is log-uniform on [0.3, 20].** A scale parameter
   spanning nearly two decades must not be sampled uniformly: U(2, 20) put
   89 % of its mass above β = 4, above every value the porosity table can
   produce, so the served values would have sat in the thin tail of the
   support. The retrained fractured support is Rd ∈ [1.3, 21] and every
   lithology's β_por lies inside it (test-pinned).
3. **The Monte-Carlo band spans a factor of 4 either side** of the central
   value, log-uniform, clipped to the prior — "the matrix may store four times
   more or four times less than the porosities imply" — in place of a ±40 %
   jitter inside the old assumption. Train and serve share one sampler.

**The diffusive clock was evaluated and not adopted.** A diagnostic at the
three reference sites (Jaduguda deposit, a belt point, Ranchi) compared the
first-order Goltz–Roberts clock with the √t diffusive clock described in the
config: fronts moved 2.1 → 2.0 m (uranium) and 31.2 → 30.2 m (sulfate). Both
clocks reach the capacity cap `1 + β·R_m` within ~3–6 yr of a 20-yr horizon,
so the front runs on the *capacity*, not the kinetics; β is the lever, the
clock is not. The same diagnostic found the retarded-continuum branch governs
at every site and species — the Tang early-arrival envelope never wins at 20 yr
— which contradicts the config's earlier note that Tang "already governs for
sorbing species" and is pinned by `test_r17_beta.py`.

**Before and after** (`ml_pipeline/outputs/snapshot_{pre,post}_r17.json`,
default site operation, 20 yr, analytical engine; ML P10–P90 migration band
from the v3 and v4 surrogates):

| Pin · species | β | Migration | Footprint | At the ring | ML band (migration) |
|---|---|---|---|---|---|
| Jaduguda · uranium | 10 → 3.0 | 10.6 → **20.5 m** | 9.3 → 9.6 ha | 1 → 1 ppb | 2–61 → 2–102 m |
| Jaduguda · sulfate | 10 → 3.0 | 31.7 → **73.1 m** | 10.0 → 11.3 ha | 227 → 244 mg/L | 2–189 → 3–468 m |
| Jaduguda · TDS | 10 → 3.0 | 114 → **254 m** | 12.7 → 17.6 ha | 2,253 → 4,428 mg/L | 5–848 → 15–2,136 m |
| Jaduguda · radium | 10 → 3.0 | 0.3 → 0.6 m | 9.1 → 9.1 ha | 23 → 23 mBq/L | 0–1 → 0–2 m |
| Mid-belt · sulfate | 10 → 2.0 | 19.0 → 60.7 m | 12.4 → 13.7 ha | 46 → 63 mg/L | 2–114 → 4–345 m |
| Ranchi (non-belt) · sulfate | 10 → 2.0 | 8.8 → 25.3 m | 12.3 → 12.7 ha | 31 → 31 mg/L | 1–42 → 2–172 m |

Uranium roughly doubles and stays within tens of metres — `R_m ≈ 90` still
dominates `β·R_m` — while the lixiviant reagents (sulfate, TDS) move two to
three times as far and the band now reaches into the hundreds of metres. That
is the physically expected ordering and the reason NUREG-1569 rejects uranium
as an excursion indicator; the engine's indicator panel already reflects it.
The published Jaduguda advisory footprint is unchanged in kind: block
intersection is done on the central contour, so the alert count does not
inflate; the P90 envelope now feeds a separate `possible_reach` alert (§4h).

**v3 → v4 surrogate** (`ml/artifacts/metrics.json`, all gates unchanged and
passing): area R²(log) 0.892 → 0.894, migration 0.929 → 0.927, compliance
0.957 → 0.947; scenario coverage 0.861 / 0.868 / 0.862; field-resampled
coverage 0.883 / 0.875 / 0.879 (gate 0.80); on-manifold physics laws hold;
excursion-probability R² 0.916. Baselines on the same folds (new in v4):
ridge 0.56 / 0.77 / 0.74 and a depth-1 stump 0.38 / 0.51 / 0.50 against the
surrogate's 0.89 / 0.93 / 0.95. The one regression — radium compliance — is
in §1 above.

**What is still true.** β is not measured. The central value now rests on
lithology-typical porosities (Freeze & Cherry 1979) or a polygon's specific
yield, and the factor-4 band is a judgement about how far typical values may
be from local ones. Fidelity row 3.4 stands: a Singhbhum tracer test is the
only thing that retires it. The sensitivity analysis in §1e says how much of
the output variance it still carries.

---

## 1e. Global sensitivity (R17, 2026-09-20) — which assumptions carry the answer

`ml_pipeline/validation/sensitivity.py` sweeps thirteen inputs (seven
registered ungrounded constants that enter the plan-view solve, six resolved
hydrogeological inputs with their Monte-Carlo ranges) at three reference sites
for uranium and sulfate: one-at-a-time elasticities and Sobol first- and
total-order indices (Saltelli design, N = 256, ~3,800 analytical evaluations
per site and species). Results in `ml/artifacts/sensitivity.json` and the
`sensitivity_*.png` figures; the summary table is reproduced in the report.
The headline is reported there rather than here so this file does not
hand-copy a number the artifact already carries.

---

## 1f. Closed (2026-09-25) — the vertical pathway moved water, not solute

**Found in a review of why the plume "barely moves".** The upward-leakage time
was `separation / (Kv·i/φ)` — the travel time of a water parcel — for every
species. At Jaduguda (20-yr run) uranium, sulfate and TDS all "reached" the
shallow aquifer in **17.5 yr**, and changing β from 3 to 0 did not move that
number, while the same response's horizontal front retarded uranium ~270×
through that β. The product paired its most optimistic horizontal answer with
its most pessimistic vertical one, for the same rock.

**What changed** (`P.VERTICAL_PATH`, `ml_pipeline/dashboard/vertical_path.py`,
fidelity row 3.11). No retrain: the vertical screen is served analytically only.

1. **Matrix retention on the path.** The solute front climbs on the same
   Goltz & Roberts clock and `β_eff = β·R_m` as the horizontal front, with β
   from the confining layer's own porosities (the R17 rule). The wellbore
   pathway is deliberately *not* retarded — an open borehole has no matrix.
2. **Series K.** The column's conductivity is the harmonic mean of the NAQUIM
   K(z) law between the ore top and the shallow-aquifer base (Freeze & Cherry
   1979), not K at ore depth, the tightest point on the path. Jaduguda:
   0.563 → 1.32 m/day.
3. **Kv/Kh measured, not chosen.** Fractured 0.03 → **0.12**, the geometric
   mean of the five pumping-test interpretations from the Maheshwaram granite
   (Maréchal, Wyns, Lachassagne & Subrahmanyam 2004, *J. Geol. Soc. India*
   63(5), Tables 2–3; "2 to 30 times", Maréchal et al. 2003, *C. R.
   Geoscience* 335). The old value sat below four of the five measurements.
   The measured range 0.034–0.61 is re-evaluated on every run
   (`anisotropy_band`).
4. **The salts are reported beside the display species.** Chloride, TDS and
   sulfate are screened on the same geometry, and `first_arrival` names the
   earliest constituent whose source exceeds its drinking-water limit. The
   backend's `aquifer_breach_due` and `aquifer_pathway` alerts now key on it
   (`app.services.alerts.vertical_headline`); runs stored before this change
   carry no `first_arrival` and are read exactly as before.

**Before and after** (20-yr run, default operation, analytical engine; old =
main `d2bb215`, same pins):

| Pin | Before (every species) | Water | TDS | Sulfate | Uranium |
|---|---|---|---|---|---|
| Jaduguda | 17.5 yr [6.4–31.1] | 1.9 | **4.5** [1.0–9.8] | 22.7 | **448** [153–810] |
| Dhanbad | 65.5 yr [24.8–97.2] | 4.7 | 15.0 | 66.9 | 1,130 |
| Ranchi (non-ore) | 110.7 yr [40.7–186.5] | 10.2 | 35.7 | 154 | 2,479 (source suppressed) |

**Direction of the change: both ways, for stated reasons.** The salts arrive
**sooner** than the old headline (the series K and the measured Kv/Kh each
speed the water up; TDS's small matrix storage slows it only ~4×). Uranium
arrives **far later**: it is held back by the same matrix storage that holds
its horizontal front to tens of metres. That ordering is the one NUREG-1569
p.137 gives for rejecting uranium as an excursion indicator, and it is now
visible in the vertical as well as the horizontal answer.

**What is still true.**

* **Kv/Kh is not a Singhbhum measurement.** It comes from the sub-horizontal
  weathering fissures of a granite less than 35 m deep. For folded
  metasediments such as the SSZ schists those fissures are "randomly dipping"
  (Lachassagne, Dewandel & Wyns 2021, *Hydrogeol. J.*,
  doi:10.1007/s10040-021-02339-7), i.e. less anisotropic. Maréchal et al.
  (2004) note tectonic fissures take over beyond 70–90 m. Both point to the
  served value **understating** vertical flow in the belt, which is why the
  measured range is shown and not hidden.
* **Foliation dip is not modelled.** The SSZ fabric dips moderately: "about
  35º towards northeast in Turamdih area" (UCIL feature article on Turamdih,
  p.5); the Jaduguda orebody has "a moderate dip of about 40°" (Bhasin, UCIL,
  IAEA ETDE XA0103130, p.3). A dipping
  permeable fabric would add a vertical component to flow, but rotating a
  permeability tensor needs the along- vs across-foliation K ratio, and no
  hydraulic measurement of it exists for the SSZ. Recorded rather than guessed.
* **The upward gradient is still a scenario assumption** (0.005,
  `UNGROUNDED_PARAMETERS`). A bleed-operated wellfield is a net sink, so over
  the wellfield as a whole the gradient during operations points *into* the ore
  zone; an upward push is realistic around individual injection wells, during
  an imbalance, or in a natural discharge setting. The seasonal band brackets
  it; no deep piezometry exists to replace it.
* **No redox trapping on the vertical path.** The upper part of the column is
  the oxidised weathering profile, where the reducing capacity the horizontal
  uranium rate represents is not established; applying it would be
  anti-conservative. Immaterial within the horizon (uranium arrives in
  centuries).
* **Cost.** Screening three indicators adds ~90 ms per `/api/predict`
  (217 → 304 ms median at Jaduguda), paid again on each stored timeline frame.

**Records that now read differently.** The submitted technical report
(§6.6, appendix row 22; its sources were removed from the repository on 2026-09-27 and remain in git history) quotes the registered
site's uranium run at 18.7 yr / index 0.62 / *high* — a water-parcel time,
species-blind, like every vertical figure before this change. Under this
change a uranium run near that site reports uranium arriving in centuries
(~448 yr at the Jaduguda reference pin) and TDS first within a few years
(~4.5 yr there). The report is a historical record and is not edited; this
section supersedes that figure. Published advisories keep the vertical block of
the run they were published from until they are re-run.

---

## 1g. The plume map, drawn continuously — and why it is still a band (2026-09-25)

**Raised by the project owner:** *"only a rectangle appears in the direction of
the computed vector… it looks like no work has been done."* Two things were
checked, and they have different answers.

**What was a rendering choice, and is fixed.** The map drew two to six *flat*
contour fills, which throws away the field between levels — a plume whose
concentration falls a hundredfold along its length was painted as one block.
The engine now returns the field as a north-up raster
(`dashboard/plume_geometry.py`): each pixel is the analytical
`concentration_field` evaluated at that pixel's own centre, not an interpolation,
with the contours' own masks and display floor (pinned by
`tests/test_plume_raster.py`). The console defaults to it; the contours stay on
top as outlines.

**What is the physics, and is not a defect.** Drawn continuously, the plume is
still a straight-sided band as wide as the wellfield. That is what a wide source
releasing into a steady, uniform regional flow produces when sideways spreading
is small — and field tracer tests show sideways spreading *is* small: at Cape
Cod, 0.96 m longitudinal against **1.8 cm** transverse horizontal dispersivity
(Garabedian, LeBlanc, Gelhar & Celia 1991, *Water Resour. Res.* 27(5):911–924).
Even the most generous literature ratio would soften a 300 m band's edges by
tens of metres. Real plumes become irregular through **heterogeneity** (channelled
flow) and **uncertainty** — the first is not measured anywhere near the
deposits, the second is.

**Why no fracture network was built.** A discrete fracture network was proposed
and then checked against the data it would be conditioned on. Within ±5 km of
Jaduguda the Bhuvan 1:50k map holds **one** lineament; within ±10 km, 16, of
which only 3 are structural joints/fractures (the rest drainage- or
ridge-parallel). Every trace is ≤ 3.0 km — cut up during harvesting — so no
length distribution can be fitted, and no joint spacing, aperture or
persistence data for the SSZ mines is published (fidelity row 3.4). A
wellfield-scale network would therefore be almost wholly assumed: fingers drawn
by the assumptions, not by Singhbhum. Declined for that reason.

**What is drawn instead: the uncertainty the engine already carries.** The
*chance over the limit* layer is the fraction of the engine's own Monte-Carlo
draws — the 48 its served excursion probability already scores (K
heterogeneity, Kd, β ×4, gradient, dispersivity, bleed drift, downtime,
aperture, all registered) — in which the drinking-water limit is exceeded at
each pixel. At the monitoring ring it reproduces the served excursion
probability exactly (test-pinned). It is the existing uncertainty model drawn in
space, not a new one.

**Flow direction, measured (2026-09-25).** The flow field stored the fitted
direction but never how sure it was, so the map fanned only along and across
flow. `data_prep/flow_direction.py` measures it on the flow field's own grid,
stations and kernel. The refit reproduces the served direction exactly. It
measures two ways:
* the weighted-least-squares standard error of the plane's slope, propagated
  to an angle: 7° / **17°** / 46° (p10/p50/p90 over station cells);
* the plane refitted to each monitoring year: circular SD 0.7° / 4° / 20° over
  2013–2020, and **2.8° / 9.9° / 39.5° over 1994–2025** once the 32-year record
  (§1i) was extracted.

The year-by-year spread is smaller than the fit error because nearby wells
repeat the same spatial misfit every year, so the yearly fits agree even where
the plane is a poor description. The fit error is the honest measure.
Both estimate how well the LONG-TERM direction is known — a plume averages over
yearly wobble — so the larger (fit error, or yearly spread / √years) is
served, not their sum. At Jaduguda that is **±22°** (1σ): at a 2 km reach,
about ±800 m sideways. The chance map combines every Monte-Carlo draw with 15
evenly spaced directions (rotations about the wellfield centre). A
user-set bearing is not fanned, and DEM-fallback cells have no statistics and
are drawn unfanned, said so. **This is a lower bound**: the plane is fitted over
~25 km, and local hills and streams can bend flow at the 300 m scale in ways
no regional fit sees. The year-by-year check was extended to 1994–2025 from
CGWB's national water-level tables (§1i); the 2024–25 Year Book has district
summaries only (§1h). Where stations are few the fit error says so: at Bagjata
it is ±79°, which the fan draws as a near-circle rather than a direction.

---

## 1h. The CGWB 2024 quality table (2026-09-25) — what it adds, and what it does not

**Source.** CGWB, *Ground Water Quality Data (2024)*, the national PDF table.
The Jharkhand rows (pages 19–20 pre-monsoon, 101–103 post-monsoon) are
extracted by `ml_pipeline/data_prep/cgwb_gwq_pdf.py` to
`Datasets/cgwb_gwq_2024_jharkhand.csv`. That gives **288 samples** (138 pre, 150
post) in all 24 districts, with contiguous serial numbers (no row lost). The
extractor refuses any page whose header differs from the expected 36 columns.
The *Ground Water Year Book, Jharkhand 2024–25* was also reviewed: it holds
district summaries and maps only. Its station tables (Annexures I–II) are not
in the published file, so it cannot feed the flow field.

**What it does not add: uranium.** Every Jharkhand row has "-" for U, As, Fe,
Mn and the trace metals (other states carry values). The 2023 table
(`waterQuality_jharkhand.csv`) remains the only source of measured uranium, and
the uranium year-on-year comparison is still impossible.

**What it does add: the first measured natural variability.** 127 stations
were sampled in both 2024 seasons, and 275 of the 288 rows lie within 500 m of
a 2023 station. So TDS, sulfate and chloride now have up to three samples per
site. `ml_pipeline/validation/baseline_variability.py` measures how far CLEAN
water moves by itself:

| Excursion rule (2-of-3: TDS, SO₄, Cl) | Share of clean station-pairs that would alarm |
|---|---|
| UCL = baseline × 1.2 (**served**) | **33 %** |
| × 1.5 | 20 % |
| × 2.0 | 12 % |
| × 2.5 | 8 % |
| × 3.0 | 3.5 % |

The single-indicator natural 95th-percentile swings are TDS 2.5×, chloride
4.4× and sulfate 5.7× between seasons. **Consequence for the model:** the lixiviant still
stands out at full strength everywhere tested — at Jaduguda TDS is 3.06×
background against a natural 2.51×. But the margin there is thin, and a 20 %
UCL on these waters would be mostly false alarms. **Caveat that bounds the
use:** these are shallow wells. They are the right aquifer for an
*overlying-aquifer* (vertical-excursion) monitor, but an upper bound for the
deeper ore-zone ring, which damps seasonal swings. The served UCL is therefore
not changed. The register entry now records the measurement, and the value
for the ore-zone ring stays an owner decision.

**Recorded, not used: nitrate.** 116 of 288 samples exceed 45 mg/L (2024 median
~40 mg/L) against 22 of 393 in 2023 (median 18 mg/L). A doubling in one year
could be real, a different well set, or a reporting change. The table cannot
tell which. It is not fed to any alert until checked against CGWB's own
2024 report text.

---

## 1i. The CGWB water-level record 1994 – January 2026 (2026-09-25)

**Source.** CGWB's national depth-to-water tables for the unconfined aquifer
(dug wells), one PDF per campaign:
* January 1994–2025 and January 2026;
* pre-monsoon 1994–2025, plus three decade files;
* August 1994–2025, plus 1994–2023;
* post-monsoon (November) 1994–2023.

`ml_pipeline/data_prep/cgwb_wl_pdf.py` extracts the Jharkhand rows. The
full-span file per campaign is primary; the partial ones are supplementary.
The result is `Datasets/cgwb_waterlevel_jharkhand_1994_2026.csv`: **26,009
readings at about 700 wells, 1994 – January 2026**, against the 9,583 readings
(2013–2021) the engine was built on. Every file extracts exactly as many
Jharkhand rows as its text layer holds; none is refused. The early years are
sparser: about 190 wells a year were read before 2013, 400–550 since 2020.

**How it was checked, because the PDFs are unruled.**
* Column starts are learned per page from the data rows. A word only counts as
  a column start after a column-width gap: the header labels sit ~30 pt off the
  data in some files, and multi-word states ("Jammu & Kashmir") on shared pages
  otherwise create false columns. Both failures were found by tests and fixed.
* One station's long name ("Hanuman Mandir (Near Ag.Office)", Bero) overprints
  its latitude in recent years. Its latitude is recovered from the interleaved
  characters, and the rows are flagged, not dropped.
* **Independent check:** station by station, the record agrees with the
  2013–2021 file already on disk. Of 300 stations with ≥ 4 shared months, 298
  match within 0.1 m (median).

**What the partial files turned out to be.**
* **Three add nothing** (checked reading by reading against the record):
  August 1994–2023, and the pre-monsoon 1994–2003 and 2004–2013 files. Every
  reading is already in the full-span file, and none has more decimals. Where a
  few differ by more than 0.05 m, the full-span file's value stands.
* The pre-monsoon 2014–2024 file gives 732 readings with more decimals, which
  are kept.
* The same file also carries **187 readings (2022–2024) at wells absent from
  every full-span file**. They are markedly deeper (median 9.2 m
  vs 7.3 m), consistent with bore wells: the 2024–25 Year Book counts 122 bore
  wells among Jharkhand's 582 monitoring wells. They are kept, **flagged**
  (`note`), and left out of water-table analyses.
* CGWB's tables print some wells twice at the same coordinates and date: the
  Simdega well also under Gumla (its district until 2001), a Basia well under
  two block names, and repeated Raidih and Karra rows. 104 identical repeats
  collapse to one reading. **81 pairs differ in depth** (at Raidih, Basia,
  Simdega and Borio). At Simdega in 2021–2024 the second row carries the
  Gumla-town reading, 50 km away. Neither row of a pair can be assigned, so
  both are kept, flagged and left out.

`cgwb_wl_pdf.water_table_rows` is the one rule for which rows count. It keeps
unflagged rows and the repaired Bero rows, whose coordinates are exact.

**What it is used for.**
1. **The flow-direction check now spans 32 years** (§1g). The long-term
   direction fitted from 1994–2025 agrees with the served 2013–2021 direction
   to a median **3.3°** (90th percentile 17°), inside the served uncertainty in
   **90 %** of cells, and within 0.8–2° at Jaduguda, Turamdih, Dhanbad and
   Ranchi. The flow field is therefore **not rebuilt**: the longer record
   confirms it rather than changing it (test-pinned).
2. **No widespread water-table decline**
   (`ml_pipeline/validation/water_table_trends.py`: Theil–Sen slope,
   Mann–Kendall test, wells with ≥ 15 years spanning ≥ 20).

   | | Wells | Median trend | Deepening (p < 0.05) | Rising (p < 0.05) |
   |---|---|---|---|---|
   | Statewide, pre-monsoon | 177 | +0.011 m/yr | 29 | 20 |
   | Statewide, post-monsoon | 173 | +0.008 m/yr | 23 | 18 |
   | Uranium-belt districts, pre-monsoon | 24 | +0.003 m/yr | 5 | 5 |
   | Uranium-belt districts, post-monsoon | 23 | −0.025 m/yr | 1 | 6 |

   The steepest decline is one West Singhbhum well at 0.31 m/yr. The network
   shows no net fall, so the 2013–2021 water tables that the vertical
   screening uses remain representative. That is a statement about the
   network, not a guarantee for any one well.

**What it is not.**
* It is not confined-aquifer data. The tables are for the unconfined aquifer,
  so the vertical push (§1f, the upward gradient) is still unmeasured.
* It does not replace `cgwb_waterlevel_jharkhand.csv`, which stays the live
  file: the dataset manager appends approved readings to it, `model_ops`
  rebuilds the flow field from it and `seed.py` loads it.
* It is not yet loaded into the backend database, so the portal's water-level
  views are unchanged.

**Removed from `Datasets/` (2026-09-25):**
`cgwb_gwq_physical_jharkhand_2000_2021.csv`. It was committed with the R17
chemistry record, but its only measurement columns are temperature and
turbidity, and all 1,205 rows leave both empty. No code, test or document read
it. It remains in git history.

---

## 1j. The belt's boreholes, and the 3-D site block (2026-09-25)

**The belt report is recovered.** The NAQUIM report for the uranium districts
covers East Singhbhum, Saraikela-Kharsawan and parts of West Singhbhum
(Phase III, draft, water levels of 2015).
* The project's copy had been a 404 page. CGWB has since removed the report,
  and its current Publications Warehouse lists 48 Jharkhand items with none
  for these districts.
* The Internet Archive kept the file (2022-07-25). It is now
  `Datasets/naquim_reference/cgwb_naquim_e_singhbhum_saraikela_w_singhbhum_parts.pdf`.
* The Saraikela-Kharsawan booklet (2013) was recovered the same way. Much of
  its text is copied from Godda's booklet (coordinates, geology), so only its
  summary table is used, and cautiously.
* The ten NAQUIM PDFs the owner supplied on the same day were word-for-word
  duplicates of reports already held.

**What was extracted.** CGWB's exploratory boreholes of the belt are in
`Datasets/cgwb_exploratory_wells_singhbhum.csv` (48 holes, 43 placed) and
`..._zones.csv`, served by `data_prep/cgwb_boreholes.py`. Sources:
* the recovered report's Annexure III and Tables 11, 15 and 17;
* the East Singhbhum booklet's Table 2 (wells as on March 2003).

Rules of the transcription:
* Values were read from the page images, because the text layer drops blank
  cells.
* Blanks stay blank. A value that sits between columns is noted, not used.
* Five positions are left out: one plainly misprinted (AMD campus, about
  150 km off) and four tests printed without a position.
* Every disagreement between the sources is written into the row.

**Three things they show.**
1. **The shear-zone permeability the engine serves at the mines (D5) is not
   from the mines.** `SHEAR_ZONE_T_M2DAY = 370` rests on 207–570 m²/day.
   * CGWB's own pumping-test table (Table 11) labels those three wells
     (Kalapathar, Baharagora, Manusmuria) **Tertiary sediments**. They are
     51–58 km east of Jaduguda, outside the model's belt.
   * The same tables give 2–101 m²/day for hard rock. The one test near a
     deposit is Kudada, 3 km from Turamdih, at 19 m²/day. Hesel (Potka) gives
     4–6 m²/day.
   * Fidelity row 1.1 and the submitted report say the 207–570 values come
     from "exactly where the mines are". That statement is superseded here.
   * ~~The served value is unchanged, pending the owner's decision.~~ **Decided
     and changed on 2026-09-26: the baseline is now the measured maximum,
     Kudada's 19 m²/day. See §1k.**
2. **The deep aquifer can push upward.** Kudada is recorded as an
   **auto-flowing well** (Table 17), meaning its deep fractures (105–139 m)
   carried water to the surface. The pumping test lists a static level of
   2.42 m bgl, and both are printed.
   * The West Singhbhum NAQUIM tables (2022) give three close
     borehole/dug-well pairs over the same ground. Tantnagar (EW 8.0 vs DW
     5.37/2.95 m bgl) and JNV Jhinkpani (EW 14.2 vs Jorapokhari 6.50/2.85 m)
     push down. Dumirta (EW 2.49 vs DW 7.60/2.40 m) pushes up in the dry
     season.
   * These natural gradients are 0.03–0.23, against the scenario's 0.005
     (`VERTICAL.upward_gradient`), and the sign depends on the site.
   * They are one-time readings from open boreholes, drilled for water
     supply. They bound the question; they do not measure it at a wellfield.
3. **Deep water near Turamdih is low in the excursion indicators.** Kudada's
   deep-fracture sample reads EC 721 µS/cm, Cl 7 and SO₄ 5 mg/L (Table 15).
   A lixiviant would stand out there even more than against the shallow
   baselines of §1h. It is one sample.

The layer depths the engine serves for East Singhbhum (weathered base 20 m,
fractures to 258 m) sit inside what the report records: weathered mantle
15–34 m, fractures 30–200 m, and the deepest on file at 230–232 m (Hesel
EW-2). The `naquim_vertical.csv` source text now cites the recovered report;
no value changed.

**The 3-D site block** (portal: Console → a site's run → *Open the 3-D site
block*; `console/SiteBlock3D.tsx`, three.js, loaded only when opened).

What it draws:

| Element | Source | Status |
|---|---|---|
| Ground | GLO-30 excerpt | measured |
| Walls and cut faces | CGWB three-layer convention at the **district's** NAQUIM depths | not measured at the site, and labelled so |
| Water table | the pin's CGWB-derived depth, as a uniform offset below the ground | measured at points only |
| Boreholes | CGWB drilling, from the published tables | measured |
| Plume | the raster the map paints, laid on the ore top | model output |
| Fronts | `vertical.front_series`, one ring per constituent | model output |

The fronts use the same clock as the printed arrival years, so the animation
cannot disagree with them. A corner is cut away so the ore horizon and the
climb can be seen. Boreholes are drawn through the ground ("x-ray") and wider
than life. Vertical exaggeration (×3 by default) is always printed.

Most blocks hold no borehole: the nearest to Jaduguda are 8–9 km away
(Dabanki, Kendadih, Pathargora). The block therefore lists the nearest ones
with distance and bearing, instead of implying they are at the site.

**What it is not.** It is not a three-dimensional transport model. The plume
is the engine's two-dimensional answer laid on the ore horizon, and the
vertical fronts come from the one-dimensional column screening (§1f). The
block shows those answers in place; it adds no physics of its own.

## 1k. The grounding pass (2026-09-26) — a measured baseline, a labelled hypothetical, local backgrounds

**The owner's framework.** Every run now gives two answers.
1. **The measured-maximum baseline** is the served answer: every metric, the
   vertical screening, the excursion panel and every alert. In the Singhbhum
   shear zone it uses the largest transmissivity measured in the belt's own
   host rock near the deposits, capped at 20 m²/day.
2. **The ISR-feasibility hypothetical** is the same run with only the ore-zone
   K raised to the IAEA's working level for in-situ leaching. It is returned
   under `hypotheticals`, labelled "Not a prediction", and never read by
   anything that alerts (backend test `test_hypotheticals_passthrough.py`).

**The threshold is the IAEA's.**
* IAEA NF-T-1.4 (2016), p. 10: "permeability of the order of 1 m/d (1.2
  darcy) or higher is advantageous. Usually, ISL becomes unfeasible at values
  of the order of about 0.1 m/d and less."
* IAEA-TECDOC-1239 (2001), p. 56 classes "clayey schists and solid rocks" as
  practically impermeable, 0–0.1 m/day.
* UCIL's own note on in-situ leaching lists "good permeability" of the host
  rock as a precondition.
* The hypothetical uses 1 m/day, the "advantageous" level (registered as a
  modelling policy). Every run also reports whether its measured ore-zone K
  is below the 0.1 m/day floor.
* At the deposits' ore-depth seeds:
  * five of the seven are below the floor: Jaduguda 0.034, Narwapahar 0.052,
    Turamdih 0.060, Mohuldih 0.032 and Bagjata 0.045 m/day;
  * the two shallow ones sit between the floor and the working level:
    Bhatin 0.12 m/day at 90 m, Banduhurang 0.18 m/day at 60 m;
  * none reaches 1 m/day.

**D5 changed: 370 → 19 m²/day** (`P.SHEAR_ZONE_T_SOURCE`).
* **Source.** Kudada EW (CGWB), metasediments, 3 km NE of Turamdih: T = 19,
  open hole 15.6–145.4 m.
* **Conversion.** K_ref is chosen so the engine's own K(z) law, integrated
  over the tested interval, returns the measured T: 0.228 m/day at the 45 m
  reference (`resolve.shear_zone_reference`). Plain T/b would decay the tested
  interval twice, about 1.5× too low at ore depth. The thickness is now the
  tested interval, 130 m; 150 m was a choice.
* **Disclosed, not served.** AMD Jamshedpur EW, also metasediments, tested
  101 m²/day, but no position is published. Granite wells across the belt
  districts read 2–39 m²/day.

**The mines bound it** (`validation/mine_inflow_transmissivity.py`). A
dewatered mine is a pumping test at km² scale. UCIL's 2017 pre-feasibility
reports give Narwapahar 2,700 m³/day (developed to 380 m) and Turamdih at
least 3,170 m³/day (to 260 m). Thiem, swept over every plausible geometry,
gives these bulk T values. All are upper bounds, because the pumped water
includes backfill, drilling and rain water.

| Check | Turamdih | Narwapahar |
|---|---|---|
| Bulk T the discharge allows | ≤ 9.1 m²/day | ≤ 5.3 m²/day |
| The engine's served K(z) column, integrated over the drained depth | 24.6 m²/day (2.7×) | 26.0 m²/day (4.9×) |

At Turamdih, in the most generous geometry (only the 60 m level drained),
each candidate T would force this discharge:

| T (m²/day) | Forced discharge |
|---|---|
| 19 | about 0.9× the reported 3,170 m³/day |
| 101 | about 4.8× |
| 370 | about 17.5× |

The baseline therefore sits on the conservative side of the mine data, and
the retired value is ruled out by it.

**What changes at the deposits** (20 yr, default operation, the deposit's
ore-depth seed; `metrics.analytical` against `hypotheticals.isr_feasibility`).
The baseline's ore-zone K is 0.034–0.060 m/day; the hypothetical's is
1 m/day.

| Site | Constituent | Baseline reach | P(exceed) | Hypothetical reach | P(exceed) |
|---|---|---|---|---|---|
| Jaduguda | TDS | 30 m | 0 | 535 m | 1.00 |
| Jaduguda | sulfate | 11 m | 0 | 156 m | 0.56 |
| Jaduguda | uranium | 4 m | 0 | 38 m | 0.06 |
| Turamdih | TDS | 20 m | 0 | 386 m | 0.92 |
| Turamdih | sulfate | 11 m | 0 | 127 m | 0.42 |
| Turamdih | uranium | 5 m | 0 | 36 m | 0.06 |
| Bagjata | TDS | 8 m | 0 | 100 m | 0.50 |
| Bagjata | uranium | 2 m | 0 | 14 m | 0 |

* The first vertical arrival (TDS) is 140 yr at Jaduguda, 48 yr at Turamdih
  and 109 yr at Bagjata, in both answers. The rock above the ore keeps its
  measured K in the hypothetical, because the IAEA criterion concerns the ore
  horizon. The engine computes this rather than assuming it, and would show a
  difference if the two ever became coupled.
* The 2026-09-25 comparison at T = 370 put Jaduguda's TDS reach at 173 m and
  its vertical arrival at 10.5 yr. Both came from the Tertiary value.

**How the hypothetical relates to the Monte-Carlo band.** They answer
different questions, and neither replaces the other.
* **The Monte Carlo is parameter uncertainty within the measured rock.** It
  covers local K heterogeneity, Kd, β, gradient, dispersivity, aperture and
  bleed drift. Its 48 draws vary K by only 0.37–2.46× around the served
  value, so at Jaduguda they span 0.013–0.084 m/day. They never reach the
  IAEA's 1 m/day: nothing measured near the mines supports that.
* **The hypothetical is a different rock class.** It changes K by about 30×,
  and it carries its own Monte-Carlo band inside it.
* **The two bands do not overlap** (20 yr, reach P10–P50–P90, the same 48
  draws):

  | Site | Constituent | Measured rock | P(exceed) | ISR-grade rock | P(exceed) |
  |---|---|---|---|---|---|
  | Jaduguda | TDS | 18–31–59 m | 0 | 215–555–1,395 m | 1.0 |
  | Turamdih | TDS | 10–20–46 m | 0 | 143–378–1,087 m | 0.92 |
  | Jaduguda | uranium | 2–3–7 m | 0 | 15–35–71 m | 0.06 |

* **They must not be merged.** Folding the hypothetical into the Monte Carlo
  would need a probability that the rock is ISR-grade. No data supplies one,
  and the IAEA criterion says the measured rock is not. A merged band would
  print a probability that was really just the weight chosen.

**Backgrounds are local now** (`Datasets/singhbhum_groundwater_radionuclide_baselines.csv`,
7 studies and 16 rows; `data_prep/groundwater_baselines.py`).
* **Radium** was one statewide constant, 23 mBq/L (Jaduguda's regional
  average). A pin now takes the inverse-distance-squared blend (R = 5 km, a
  registered policy) of these mining-area surveys with a regional anchor:

  | Area | Served radium | Source |
  |---|---|---|
  | Jaduguda | 23 mBq/L | Tripathi 2008 |
  | Narwapahar | 13.7 mBq/L (mean) | Rana 2010 |
  | Turamdih complex | 19.8 mBq/L (GM) | Kumar 2015 |
  | Bagjata | 12.4 mBq/L (GM) | Giri 2011 |
  | Regional anchor | 10 mBq/L (GM, 108 wells) | Molla 2025 |

  Outside East Singhbhum and Saraikela-Kharsawan the anchor is borrowed, and
  the provenance says so.
* **Uranium.** The CGWB well nearest every one of the seven deposits has no
  uranium measurement, so every deposit pin served an unsourced 1.0 µg/L.
  Now:
  * Jaduguda 1.1 µg/L (median, Jha 2014);
  * Narwapahar 0.87 µg/L (mean);
  * the Turamdih complex 0.99 µg/L (GM, Kumar 2015);
  * Bagjata 3.22 µg/L (GM, Giri 2011);
  * far from the mines, the nearest CGWB well, or the CGWB statewide median
    of 0.775 µg/L (342 wells), which replaces the 1.0 default.
* **Disagreements are kept.** Two BARC surveys of the Turamdih ground give
  radium GMs of 19.8 (Kumar 2015, about 153 samples over four years) and 9.1
  (Giri 2011, about 40). The larger survey is served and both are recorded.
* **Leverage is small.** Backgrounds sit 1–3 orders of magnitude below their
  limits (U 30 µg/L, Ra 1,000 mBq/L). What changed is that the value is
  measured where it is served.
* **Not acted on.** The regional survey reads ORP +28 to +138 mV in all 108
  wells, which is oxic. That matters for the uranium redox-trapping
  assumption, but field ORP probes are unreliable, so it is recorded only.

**The radium Kd upper end is local.** Maity, Sahu & Pandit (2015) measured
Turamdih soils in site groundwater: 580–1,835 L/kg at the top and
796–2,285 L/kg at 1 m.
* The immobile end member is now 2,285 L/kg. It replaces Thibault's 9,100
  (porous) and an unsourced 2,000 (fractured).
* The mode stays at 13.2. Every local value is for soil with 4–7 % organic
  matter at ambient ionic strength, so the served mode sits 44–173× on the
  mobile side of anything measured here.
* Uranium soil Kd at Turamdih (69–5,524 L/kg, Maity 2013, abstract only) is
  recorded but not served, because an alkaline lixiviant suppresses uranium
  sorption.

**Ore-depth ranges are documented**
(`ore_loader.DEPOSIT_ORE_DEPTH_RANGE_M`; copies in `Datasets/ucil_reference/`):

| Deposit | Documented ore depth | Seed |
|---|---|---|
| Jaduguda | 0–900 m | 180 m (unchanged) |
| Bhatin | 0–135 m | 90 m (was 150, below the ore) |
| Narwapahar | 100–380 m (oxidised above 100 m) | 150 m (unchanged) |
| Turamdih | 50–200 m (economic grade) | 140 m (unchanged) |
| Banduhurang | 0–164 m (pit) | 60 m (unchanged) |
| Bagjata | 0–270 m (reserves; lode to 600 m) | 160 m (unchanged) |
| Mohuldih | 0–250 m (secondary source) | 150 m (was 250, the bottom of the ore) |

The portal prefills a deposit site's ore depth from its seed and prints the
documented range.

**Surrogate v6.** The baseline's ore-zone K spans 0.01–0.2 m/day across the
deposits and depths (0.011 at 600 m). The old surrogate was trained only down
to 0.044, so most deposit runs flagged their ML bands as extrapolating.
* The v6 bake applies the serve path's K(z) law to half the scenarios, at a
  sampled ore depth.
* It draws radium backgrounds over their served range.
* It records the per-species concentration support in the model card.
* The support now reaches fractured K 0.0021–9.8 m/day (was 0.044–10.6), so
  deposit runs no longer flag their K as extrapolated. Jaduguda's TDS
  background (1,779 mg/L) is still outside it; see "Still open".
* v5 → v6, same folds, R²(log):

  | Target | v5 | v6 |
  |---|---|---|
  | area | 0.893 | 0.892 |
  | migration | 0.925 | 0.930 |
  | ring concentration | 0.947 | 0.968 |
  | uranium ring concentration | 0.847 | 0.909 |

* Excursion-probability MAE went from 0.049 to 0.033. Radium's ring head
  rose from 0.235 to 0.746; §1 explains why that is a serving gain, not a
  transport one.
* Full metrics are in ARCHITECTURE §6.5 (generated).

**Sensitivity re-run** (`ml/artifacts/sensitivity.json`, same design as §1e).
With the rock this tight, what carries the answer at Jaduguda has shifted.
* R17 found β second only to K. Now uranium's reach is led by the matrix
  terms: total-order ω 0.48, β 0.22, Kd 0.14. Sulfate's is led by β 0.35,
  Kd 0.24, K 0.17.
* The fracture-matrix constants with no Singhbhum measurement (fidelity row
  3.4) therefore matter *more* now, not less. A tracer test in the belt
  remains the single most valuable missing measurement.

**Fixed while here.** The portal's "No uranium ore here" banner read
`in_ore`, which `/api/pin` never sent. It now does.

**Regression tests re-pointed, not loosened.** Three engine guards had numbers
captured under T = 370 while testing something else: the vertical-path
switches, chloride inertness, and a display change.
* They now run under a `retired_shear_zone` fixture that restores the old
  hydrogeology.
* All three reproduce their old numbers exactly, so D5 is the only thing that
  moved them.
* The 3-D front-animation check moved to a 120 m ore depth, where salinity
  (TDS) arrives inside its 50 yr series.
* Radium's source-zone crossing moved 44.126 → 44.085 yr, because the local
  background changed.
* Two backend tests needed a *declared* indicator excursion within 20 yr.
  They now use a belt site 2 km from Narwapahar, because at the Jaduguda site
  the measured rock no longer brings the reagents to the ring in that time.

**Still open.**
* **Porosity.** Banerjee et al. (2011) measured it on 16 Singhbhum rocks, but
  the full text was not obtained. `TOTAL_POROSITY` and `GRAIN_DENSITY` remain
  literature values, now registered.
* **Jaduguda's TDS background** (1,779 mg/L) comes from one CGWB well about
  8 km away and lies outside trained support. Not revisited here.
* **No pumping test at a deposit itself.** BARC's Turamdih and Jaduguda
  FEFLOW models are INIS metadata-only records: qq2fm-gyc05, tfqne-zyg88,
  7b64j-d8t37 and y21qt-00v59.
* **The submitted report** quotes T = 370 and the results built on it. It is
  not edited; this section supersedes it.

---

## 1b. Closed (2026-08-20) — the vertical breakthrough headline was too slow

**Reported by the project owner from the UI, then reproduced arithmetically, then
fixed.**

The shallow-aquifer panel showed a single headline breakthrough time computed at
the **annual-mean** water table, beside a seasonal band that disagreed with it by
5×. On the run that exposed it: headline **54.4 yr**, dry season **10.6 yr**, wet
season *"not expected"*. A headline outside the interval printed next to it is
not a summary of that interval.

The upward velocity is linear in gradient, `v = Kv·max(i,0)/φ`, and the code
**floors the gradient at zero** — correctly, because a reversed gradient stops
upward transport rather than reversing the front. But the headline evaluated
travel time at `max(mean i, 0)` instead of averaging `max(i(t), 0)` over the
year. Where the seasonal swing crosses zero, `max()` is not linear across the
clamp and those are different numbers:

| Basis | Gradient used | Breakthrough |
|---|---|---|
| Old headline, mean gradient | 0.00370 | 54.4 yr |
| Dry season | 0.01901 | 10.6 yr |
| Wet season | −0.01160 → clamped to 0 | never |
| **Duty-cycle, mean of max(i,0)** | **0.00687** | **≈29 yr** |

The pathway is open ~58 % of the year. **The old headline overstated time to
breakthrough by about 1.9× — it understated the hazard.**

**What was changed.** `_duty_cycle_gradient` in `ml_pipeline/physics/transport.py`
computes the annual mean of `max(i(t), 0)` in closed form and the headline is
evaluated there. Verified on the live UI: the same site now reads **18.7 yr**
against a dry season of 6.8 yr — inside its own band, where it belongs.

- **No retrain was required.** `shallow_impact_screening` is called only by
  `dashboard/server.py` and the tests; it produces no ML training label, so the
  surrogate is untouched. This was checked, not assumed.
- **Nothing was silently overwritten.** The old value is kept as
  `seasonal.breakthrough_years_mean_gradient`, and `breakthrough_basis` says
  which basis produced the headline, so old and new runs stay comparable.
- **The correction is inert where it does not apply.** With no seasonal swing,
  an always-open gradient, or an always-closed one, it returns exactly the old
  number. Pinned by test.
- **Runs stored before 2026-08-20 carry the old headline** and no `vertical`
  block at all (see §4a). They are not retro-corrected.

This is the third sanctioned change inside the otherwise-frozen `ml_pipeline/`.

---

## 1c. Closed (2026-08-20) — the alert system had never delivered an alert

**Found while building the aquifer-reach extension.** Eight advisories had been
published and the `alerts` table was **empty**. Not sparse — empty. The citizen
notification path, which is the product's only channel to a resident, had never
written a row.

`set_rls_context` uses `SET LOCAL`, which Postgres discards at COMMIT —
deliberately, so a pooled connection cannot leak one request's identity into the
next. `AdvisoryService.decide` commits the decision and *then* raises alerts, so
by that point the session had no context at all, `app.bypass_rls` read as `off`,
and the `alerts_write` policy refused every insert. The call was wrapped in
`except Exception`, which logged the refusal and let the publication stand. The
product reported success, showed the advisory to citizens, and notified nobody —
once per publication, for the life of the feature.

`POST /citizen/alerts/scan` had the same defect for the same reason.

**Fixed** by `alerts.raise_for_advisory`, which raises alerts in its own session
under the system context — the pattern `audit.record` has always used. Verified
end to end: publish → 7 alerts written → a citizen subscribed to the affected
block receives them with the hypothetical premise intact.

**The general hazard, written down because it will recur:** *after any commit,
the RLS context is gone until it is set again.* No other route noticed because
they all commit as their last act. Any route that commits and keeps querying is
anonymous from that point on, and RLS-protected tables return nothing rather
than erroring — a silent empty result, not a failure. The same bug bit twice
more the same day inside the fix itself.

**Why no test caught it, and still cannot:** the test database is built from ORM
metadata via `create_all`, so **the RLS policies do not exist in it**. An insert
that production refuses succeeds in the suite. This class of bug is not
runtime-testable in the current harness; `test_r11_publish_and_alerts.py` guards
it at the source level instead, and says so.

---

## 2. Permanently blocked — no data exists

| Item | Why it cannot be closed |
|---|---|
| Fracture β, aperture, Dₑ, ω (fidelity 3.4) | No packer or tracer test for the Singhbhum Shear Zone is published. Aperture *is* Monte-Carlo sampled into the bands; Dₑ is not — `P.FRACTURE` carries no defensible range, and inventing one would relabel an assumption as data |
| Deep piezometry for Singhbhum | The vertical gradient is bracketed by the measured monsoon swing, not measured |
| SSZ hydrogeology generally | β, aperture, Dₑ, ω rest on foreign-analogue literature |
| As / Ni / Cu / Co co-contaminants | Kd data is on disk; how much an alkaline lixiviant mobilises from SSZ ore has never been measured. Blocked on a source term, not on modelling |
| ISR source term for chloride, alkalinity, Rn-222 | Same — never measured at this ore body |

---

## 3. Data gaps that shape what the product may claim

- **The 2023 CGWB chemistry file has no temporal replicates.** 397 wells, **one sample
  each, one year, zero repeats.** Substituting regional *spatial* spread was tested and
  **rejected**: sd(TDS) = 286.5 gives a UCL of 1,965 mg/L, near the BIS limit itself.
  **Partly closed for the general chemistry (R17):** the CGWB 2000–2021 record
  (National Water Data Portal, `Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv`)
  gives 244 of the platform's wells two or more sampling years for EC, chloride,
  sulphate (46 % of analyses), bicarbonate, hardness and the major cations —
  enough for a per-station baseline mean and sd, and a Theil-Sen trend where a
  station clears ≥ 4 analyses over ≥ 3 years (`services/chemistry_history.py`,
  `GET /water-quality/history`). **It carries no fluoride, nitrate, iron, arsenic
  or manganese and two uranium values**, so trend forecasting for any health
  determinand the platform bands or alerts on remains undemonstrated, and the record
  is read-only: no band and no alert uses it.
- **The 2023 file balances by construction.** 393 of 393 computable analyses have a
  charge-balance error within ±3.2 %, and sodium reproduces the balance-implied value
  to within rounding (65 % within 2 mg/L) — consistent with sodium computed by
  difference and hardness from Ca/Mg. The charge balance is therefore **not an
  independent check** on that file, and its zero suspect analyses are not evidence of
  laboratory quality (`services/hydrochem_qa.py`, `GET /water-quality/qa`). The
  2000–2021 record does *not* balance by construction (127 of 753 computable analyses
  suspect) and the check is real there. Nothing is excluded on a QA flag; the flag
  travels with the sample.
- **C₀ rests on n = 9 measurements at 7 Texas mines** and scales the concentration field
  linearly. Reported alongside the answer rather than buried.
- **Sampled ≠ analysed for uranium.** Three districts (East Singhbum 28/28, Saraikela
  Kharsawan 11/11, West Singhbhum 16/16) have wells and samples but **no uranium result**.
  Both surfaces now distinguish *never sampled* from *not tested for uranium*; neither
  ever reads as a clean result.
- **Excursion screening is NUREG-1569-*inspired*, not a licensed programme.** The 2-of-3
  indicator rule (chloride, TDS, sulfate) follows the document's logic; `compliance_status`
  says permanently that this is not regulatory compliance.

---

## 4. Product-level open findings (R10 audit)

| # | Issue | Status |
|---|---|---|
| ~~O-1~~ | ~~No monitoring-siting recommendation~~ | **Resolved (R11).** `GET /data-gaps/recommendations` ranks every block by how badly it is observed, rendered on Data & Gaps with its weights shown. Ranks by *observation*, never by predicted risk — the model is least trustworthy exactly where there is no data |
| ~~O-2~~ | ~~`POST /ingest/*` admits `analyst`~~ | **Resolved.** All five routes are `require_admin`; `roles.md`'s generated matrix confirms it. The prose in that file had gone stale, and was corrected in R11 |
| ~~O-3~~ | ~~`react-router-dom` 6.28 advisories~~ | **Downgraded (2026-08-20).** Neither is reachable: the SSR one needs SSR (this is an SPA), and the open redirect needs a user-controlled navigation target — every `navigate()` call takes a string literal or an internal UUID. Routine upgrade, not a blocker |
| ~~O-4~~ | ~~Demo accounts with weak public passwords on the login screen~~ | **Resolved in code (2026-08-20), one action outstanding.** They were worse than listed: Vite compiled them into the production bundle, so a working *admin* password was readable by anyone who viewed source. Now behind `import.meta.env.DEV`, and `npm run build` fails if a credential reaches `dist/`. **The four accounts must still be deleted or rotated in any deployed database** |
| ~~O-5~~ | ~~`/metrics` is unauthenticated~~ | **Resolved (2026-08-20).** `METRICS_TOKEN` gates it with a bearer token; with `APP_ENV=production` and no token it is not mounted at all |
| O-8 | PDF export is wired but **pagination has never been visually confirmed** — the test harness cannot open a generated PDF | **Still open**, verify by hand |
| ~~O-9~~ | ~~Sessions expire in 15 minutes with no refresh path~~ | **Resolved.** `POST /auth/refresh` exists and is a *sliding session*: it requires a still-valid token, so it extends an active session and cannot resurrect an expired one. A real refresh-token scheme (separate long-lived credential, rotation, server-side revocation) needs a token store this prototype does not have, and is not built |

---

## 4d. R13 (2026-08-24) — what a full-repo audit found

Three classes of finding. The first two were **invisible to review**: the code
looked right, the settings were present and read, and every request succeeded.

### The security controls that enforced nothing

| # | Finding | Fix |
|---|---|---|
| S-1 | **Rate limiting was entirely inert.** `main.py` built a slowapi `Limiter` with `default_limits` and never installed `SlowAPIMiddleware`, which is the only thing that consults them. `RATE_LIMIT_PER_MINUTE=60` sat in `.env`, appeared in the deployment checklist, and applied to nothing. Measured: **120 `POST /auth/login` in 5.7 s, 120 × 401, zero 429s** — about 21 password guesses per second with no lockout | Middleware installed; `app/ratelimit.py` owns the limiter; login and citizen registration carry a separate `AUTH_RATE_LIMIT_PER_MINUTE=10`; `/health` exempt. Re-measured: 10 × 401 then 110 × 429 |
| S-2 | **`docker-compose.yml` pointed the running API at the `postgres` superuser**, so all 21 RLS policies were silently inert. Anyone who ran `docker-compose up` got a system that believed it had row-level security and did not — the exact failure the two-role design exists to prevent, shipped as the default way to run the project | Rewritten: a `migrate` service uses the owner, `backend` uses `jaldrishti_app`, and passwords come from the environment with **no defaults**, so an unset value fails loudly at `up` |
| S-3 | **No production guard on `JWT_SECRET`.** There was one for inert RLS but none for the signing key, which is the more direct failure: a token forged with the published default arrives as a valid administrator, and RLS serves it faithfully — the database cannot tell a real admin from a minted one | `_require_production_secrets` refuses to start with `APP_ENV=production` on a placeholder or under-32-character secret, an empty `DATABASE_URL`, or `CORS_ORIGINS=*` |
| S-4 | The real local Postgres password was **committed in `app/config.py`** (twice) and in `docker-compose.yml`. A default must never be a secret: it is readable by anyone with the source, and it silently *works* on the author's machine, so nothing ever forces it to be replaced | Defaults emptied; startup refuses production without real values |
| S-5 | **No security headers at all** — verified against a live response, not assumed | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, and a restrictive CSP. HSTS is opt-in via `HSTS_ENABLED`, because sent over plain HTTP it pins a browser to a scheme the host cannot answer |
| S-6 | `/docs`, `/redoc` and `/openapi.json` were served **unconditionally**, publishing the full route inventory, every schema and every role guard | Off in production unless `DOCS_ENABLED=true` |
| S-7 | `APP_ENV` was compared inconsistently: CORS tested `== "production"` while metrics tested `.lower() in ("production","prod")`, so `APP_ENV=prod` gated metrics and still opened CORS to **every origin** | One definition, `Settings.is_production` |

Checked and found **clean**: no SQL injection (raw `text()` interpolates only
module constants and allowlisted table and column names; parameters are always
bound), no path traversal (a dataset `key` resolves through a fixed registry),
citizen registration hard-pins the role and gives no account-existence oracle,
and demo credentials are correctly `import.meta.env.DEV`-gated out of the built
bundle. All seven fixes are pinned by `tests/test_security_hardening.py`.

### `POST /scenarios/{id}/run` had never worked

The **third** occurrence of the RLS-after-COMMIT hazard in section 1c. The route
assigned `run.scenario_id` after `SimulationRunService.create()` had already
committed, then committed again — and by then the session had no identity, the
`simulation_runs` policy matched zero rows, and SQLAlchemy raised
`StaleDataError: expected to update 1 row(s); 0 were matched`. The route
returned 500, the background task was never scheduled, and the run sat at
`queued` for ever.

It went unnoticed because the `scenarios` table was **empty**: there was no UI to
create a scenario, so the endpoint had never been called. It was found by
building that UI and pressing the button. The link is now written by the INSERT,
which avoids the hazard rather than working around it.

### The measured record was being collected and not read

`water_samples` has twenty determinand columns, and **fifteen of them are
filled at 99-100 % coverage** — pH, EC, TDS (derived from EC), hardness,
nitrate, fluoride, chloride, sulphate, Ca, Mg, Na, K, PO4, HCO3, CO3 (uranium
is at 86 %; iron, arsenic, turbidity and DO are empty in the seeded CGWB
record) — and **only `uranium_ppb` drove any logic**: 47 code references against 4
each (pure model and schema plumbing) for every other parameter.

That mattered more than it sounds, because **uranium exceeds its limit at zero of
342 tested wells** (maximum 28.5 ppb against a 30 ppb limit), while **nitrate
exceeds at 22 wells, peaking at 121 mg/L — 2.7 times the limit — and fluoride at
32**. The single indicator on screen was the one indicator that never fired, and
33 wells carrying a measured health exceedance were invisible.

Now assessed against **IS 10500:2012** (`services/water_quality.py`,
`GET /water-quality/*`). Nothing is modelled: every number is a laboratory
measurement compared with a published limit.

**Two things this must not be read as saying.** 71 % of sampled wells exceed
*some* IS 10500 limit, and that figure alone misinforms — most of it is hardness,
alkalinity and TDS, which is hard-rock aquifer chemistry rather than
contamination, and no mine caused it. The health-significant count is therefore
reported separately, and first. Second, **arsenic, iron and turbidity are 0 %
populated** in the CGWB file and manganese has no column at all. The proposal
names Fe, Mn and As explicitly, so this is a real data gap, reported as
`not_tested` on every well rather than quietly passed over.

**The composite WQI is a secondary figure, and says so.** Inverse-limit
weighting is the published construction and it has a property that misleads: the
weight is 1/limit, so the smallest-limit determinand dominates. Dasokhap
(Hazaribagh) scores 132.7 — "Unsuitable for drinking" — on a fluoride reading of
1.43 mg/L that is **below** its own permissible limit of 1.5, because fluoride
carries 96 % of the score. Found by reading a real well on the finished screen,
not by inspecting the formula. `dominated_by` now ships with every score and the
UI prints it beside the band.

### Nine years of level readings fed one static raster

`groundwater_level_readings` holds **8,345 measurements from 415 stations,
2013-2021** — the only genuinely temporal data in the project — and was read
solely to bake the flow field, averaging the time axis away. It is now analysed
with **Theil-Sen slope and the Mann-Kendall test**
(`services/groundwater_trends.py`), chosen because these series are short,
irregularly spaced, seasonally forced and contain outliers: every assumption
ordinary least squares needs is violated, and OLS would report a confident slope
regardless.

**The result is undramatic, and that is the finding:** of 331 testable stations,
**5 are declining, 20 recovering and 306 stable**. 84 have too short a record to
test and are reported as *"not enough record"*, never as stable. Fastest decline
0.785 m/yr (Chapodia, Dumka). Median seasonal swing 2.38 m.

### 25 of 115 endpoints had no UI

Including the entire Scenarios feature, all five `/ingest/*` routes, dataset
backup and restore (which section 4c records as "no restore has ever been
tested" — it could not be, from the portal), `PUT /isr-points/{id}` (so a
mistyped site could only be corrected by a cascading delete that also destroys
every run filed against it), and user role editing.

Closed for Scenarios, ingest, restore points, site edit, role edit and
monitoring-well registration. **Deliberately left without UI**, because each is
superseded rather than missing: `GET /water-samples` and `POST
/water-samples/bulk` (the water-quality surface returns strictly more, and bulk
upload goes through `/ingest/water-quality/csv`); `GET /advisories/{id}`,
`GET /scenarios/{id}`, `GET /users/{id}` and `GET /field-observations/{id}` (the
list responses already carry every field); `GET /isr-points/{id}/simulations`
(superseded by `/simulations/runs?isr_id=`); `GET /simulations/{sim_id}` (the
legacy `simulations` table, 0 rows); and `GET /ml/health` plus
`GET /groundwater/method` (operational probes — and `method` is embedded in the
`/trends` response the page already renders).

---

## 4e. R14 (2026-08-25) — the citizen surface stops banding on uranium alone

Five pre-deployment changes requested by the product owner. Two of them change
what a resident is told about their own water, so they are recorded here rather
than in a changelog.

### The public map could not show a high-concern district. At all.

The citizen band was computed from `max(uranium_ppb)` and nothing else.
Statewide maximum uranium is **28.5 ppb against a 30 ppb limit**, so no
district, block or point could ever reach "High concern" no matter what was in
the water — while 22 wells exceeded the nitrate limit (peak 121 mg/L, 2.7x) and
32 exceeded fluoride.

Banding now reads every measured **health-significant** determinand — uranium,
nitrate and fluoride. The result is not marginal: **14 of 24 districts move to
"High concern"**, several of them from readings where uranium is essentially
absent. Lohardaga sat at 0.5 ppb uranium and 48 mg/L nitrate; Gumla at 2.1 and
53.

Four things bound this so it stays honest:

* **Only health determinands band.** Hardness, alkalinity and TDS exceed at
  roughly two-thirds of Jharkhand's wells and are hard-rock aquifer chemistry,
  not contamination. Banding a village red for hard water would bury the wells
  carrying a real nitrate load. They remain on the water-quality surface.
* **`Not tested` is its own band**, grey and never green, distinct from both
  `No data` and `Low concern`.
* **`untested_health` ships with every row.** Arsenic and iron are 0 %
  populated statewide, so they are listed unconditionally — no block in
  Jharkhand has been cleared for them, and a "Low concern" that quietly means
  "clean for the three we happened to measure" is exactly the failure section 3
  exists to prevent. The three districts with wells but no uranium result
  (East Singhbum, Saraikela Kharsawan, West Singhbhum) still say so.
* **`band_driver` names the substance**, because "High concern" without saying
  *what* is high is not actionable: a resident can boil water for bacteria and
  cannot boil out fluoride, and the copy now says which.

### The alert channel that mattered most had never sent an alert

Found while reviewing the alert system, and it is the same defect as the band
above in the one place where it counts.

`scan_measured_exceedances` — the scan the code itself calls **"THE REAL
CHANNEL... for most citizens the only thing on this platform about water they
actually drink today"** — queried `WHERE uranium_ppb > 30`. Statewide maximum
uranium is 28.5 ppb, so it **matched zero rows every time it ran**.

The `alerts` table held eight rows, all `published_screening`. This platform had
warned people eight times about a mine that does not exist and **not once** about
the contamination measured in their own wells.

It scans every health determinand now. On the existing data that is **32 real
alerts** where there were none, including a well at 121 mg/L nitrate — 2.7x the
limit, in a district the old surface banded "Low concern".

Two details that matter more than the count:

* **One alert per well, not per determinand.** A well over both nitrate and
  fluoride is one problem with that well; two notifications would read as two.
  It also keeps the `(block_id, well_name, sampled_at)` unique index correct —
  per-determinand alerts would have collided on it and the second would have
  vanished into `ON CONFLICT DO NOTHING`.
* **The advice is determinand-specific**, because the generic version is
  actively harmful here: boiling *concentrates* nitrate rather than removing it,
  and the nitrate alert says so.

Arsenic and iron are in the scan although nothing measures them today, so the
first lab result that arrives raises an alert without anybody remembering to
come back and add it.

**A scan that finds nothing looks exactly like a scan that found nothing wrong.**
That is why this survived, and it is the third instance in this codebase of a
control that was present, configured, and inert — after the rate limiter and
`POST /scenarios/{id}/run`.

### A published screening now shows what it was, not just where it was

The citizen map drew the footprint polygon and nothing else. It now carries the
operating parameters (how long the hypothetical mine runs, what horizon it was
assessed over, how long clean-up runs, injection rate), the modelled spread, and
whether the run expected the plume to reach shallow drinking water — all of it
already stored on the run, none of it previously joined.

**The ISR coordinate is still withheld.** That is what design section 2 protects
and the reason is unchanged. Known uranium **deposits** are now shown as an
opt-in layer, which is a different thing entirely: published GSI/UDEPO reference
data about rock, not the location of a mine somebody imagined.

**One consequence worth knowing about.** Reading those parameters needs a
scoped system-context query, because `isr_points` and `simulation_runs` are
RLS-protected and a citizen reads nothing from either — a plain join returns
NULL for every column and the response looks complete while every figure reads
"unknown". The better long-term fix is to copy the figures onto the advisory row
at publication time, so a published finding is self-contained and cannot drift
when somebody later edits the site (which the R13 site editor now allows). That
needs a migration and would not backfill the two advisories already published,
so it is written down here rather than half-done.

### A fourth alert kind, and the first that fires on elapsed time

`aquifer_breach_due`. A published screening modelled that contamination would
reach the shallow aquifer after N years; the hypothetical operation's injection
start date is now more than N years ago; so on the model's own terms that
milestone has passed and the people over that aquifer have heard nothing since
the day it was published.

**This is the most easily misread alert in the system**, and the copy is written
accordingly: it opens by stating that no such mine exists, it names the
hypothetical start date it counted from, and it ends by saying that real testing
is the only thing that can answer the question the model raises. It is
`warning`, never `high`.

Five gates, each of which alone would over-claim:

1. The advisory is **published**.
2. The run **actually carries a vertical screening**. Runs stored before
   2026-08-20 have no `vertical` block, and its absence means *not assessed*,
   never *no pathway* (section 4b). Those are skipped and counted.
3. The site has a **real injection start date**. Publication date is not a
   substitute — it is when people were told, not when injection would have
   begun.
4. Elapsed time has passed the modelled breakthrough.
5. Probability at or above **0.5**.

Reach is bounded exactly as section 4a bounds it, and for the same reason:
alerting everyone on the formation would turn one hypothetical 13-hectare plume
into a statewide warning.

**`POST /citizen/alerts/scan-breach-due` defaults to `dry_run=true`** — the
opposite of the other scans. It is the only alert that fires without anybody
having acted, so the operator sees exactly who would be told, and on what basis,
before anyone is.

**On the current data it correctly fires on nobody**, and the reasons are the
result: both originally published advisories predate vertical-screening
persistence, and a freshly published Potka run is at 22 elapsed years against a
29.4-year modelled breakthrough — *due in 7.4 years*, reported rather than
raised.

### `regulator` may now run the model

R12 excluded it, reasoning that whoever reviews field evidence should not also
operate the pipeline that consumes it. Running a screening is not operating the
pipeline, and a CGWB or SPCB officer asking "what would happen if" is the
primary real-world user of a screening tool. Widened to cover pin, predict,
preview, lifecycle, sweep, stored runs, scenarios and site registration.

**What did not move is the part that matters:** publishing to citizens, dataset
writes, model operations and accounts all remain admin-only, and a regulator
hits the same 403 a citizen would.

### A UI failure mode worth recording, because it will recur

Four screens answer a row-level question by rendering a panel *after* the table
that triggered it. On a 415-row station table that panel opens 20,577 px below
the fold, and the button reads as broken.

The fix scrolls the panel into view — and the first two implementations of it
silently did nothing. `requestAnimationFrame` never runs while a tab is not
compositing, and `scrollIntoView({behavior:"smooth"})` is an animation, so it
also returns without error and without scrolling in that state. Measured: smooth
left `scrollTop` at 0 where `auto` moved it 2,143 px. The hook now scrolls,
then **verifies it moved** and jumps if it did not.

---

## 4f. R15 (2026-08-26) — the band R14 fixed had only been fixed on one surface

Section 4e says "the citizen surface stops banding on uranium alone". That was
true of `/public/risk/*` and false of `/citizen/my-area`, which is the screen a
resident who has signed in and followed their own block actually opens.

`my_area` carried its own copy of the rule: its own SQL over `max(uranium_ppb)`,
its own three-rung ladder, its own prose. R14 rewrote the other implementation
and left this one alone, so for a day the product shipped **two citizen bands
that disagreed on the same block**:

| Block condition | Public map | My Area |
|---|---|---|
| fluoride 1.8 mg/L, uranium 2.5 ppb | **High concern** | **Low concern** |
| nitrate 121 mg/L, uranium absent | **High concern** | **No data** |

Neither endpoint was wrong about the rule it had been handed. That is what made
it survive the review that produced 4e: reading either file on its own shows
correct code.

### Three further copies of the same split, found with it

* **`_explain` was uranium-only prose on a multi-determinand band.** Three
  handlers — `/geojson/blocks`, `/{district_id}` and the map popups drawn from
  them — banded on all three determinands and then explained the result with a
  sentence about uranium. A block banded High concern on fluoride was captioned
  "Uranium in the 2 wells sampled here was well below the 30 ppb safe limit",
  directly beneath the words "High concern". The function is deleted, not moved.
* **The `Not tested` band of 4e was unreachable.** The ladder read
  `health_tests = 0 AND max_u IS NULL`, and `health_tests` counts non-null
  uranium results among the three — so the first condition already implied the
  second and every query returned `No data` for a block that had been sampled
  and never analysed. `/at` patched it in Python; the other four handlers did
  not. The ladder now tests `samples = 0`, which is the only term that
  distinguishes the two, and `/blocks/summary` — which had always split them
  correctly with its own FILTER clauses — agrees with the band expression for
  the first time.
* **`iron` was the one member of the health set without `health=True`.** The
  `interpretation` sentence returned by the same module names it; `public_risk`
  calls it a health determinand twice; the alert scanner queries it. Iron is 0
  of 397 measured so no count moved, but it rendered under "general and
  aesthetic" on the water-quality screen, below a sentence naming it as
  health-significant — and the flag would have decided a real exceedance the
  moment anyone ingested an iron result.

### What now holds

The limits, the SQL that applies them, and the plain-language reading of the
result live in `app/services/health_bands.py`. `public_risk.py` re-exports them
under the private names its tests already reach for; `citizen.py` and
`alerts.py` import them. `tests/test_r15_one_band_rule.py` asserts the sharing
by **identity** rather than equality, and fails if `my_area` starts deciding a
band string of its own again.

The residual limitation is unchanged and worth restating: this band reads three
determinands because three are populated. Arsenic and iron are 0 % populated
statewide, so every `untested_health` array names them, and no block in
Jharkhand has been cleared for either.

---

## 4g. R16 (2026-09-16) — the alert system had every gate and no exit

Found while reviewing the deployed portal against the proposal, whose third
deliverable reads *"a user-friendly interface for stakeholders to input data and
receive vulnerability assessments **and alerts**"*.

**What was true on the deployed database.** Publication raised the right alerts
for the right blocks (§1c, §4a, §4e), and wrote them to a table a resident could
read only by signing in, opening the bell, and having earlier *followed* the
block that later turned out to be affected. The Alerts screen said so in its
subtitle — *"this portal does not send SMS or email."* `PRODUCT_DESIGN.md`
§4.4 C3 had specified email delivery; it had never been built. Registration
took a username, an email and a password and nothing about where the person
lived. The measured-exceedance scan had **never been run** on the deployed
database: 32 wells over a health limit, zero alerts. The Jaduguda site had no
`injection_start_date`, so the breach-due alert could never count. Three sites
named `Isr1`, `Try1` and `try2` sat on the public map.

**What changed** (migration `0025`, `services/notify.py`, `main.py`):

* `users.home_block_id` — registration asks where the person lives (block by
  name, or a point resolved by `ST_Contains`) and subscribes the account to it
  in the same transaction. A point outside every block is a 422, not an account
  with no area.
* `alert_deliveries` — one row per (alert, user, channel) attempt with status
  and address. The unique index makes delivery idempotent; the status column
  makes a failed relay visible. RLS-scoped to the row's own user.
* Email via plain SMTP, stdlib in a thread, no dependency. Publication, the
  admin scans and the scheduler all call `deliver_pending`. With `SMTP_HOST`
  unset it sends nothing, records nothing, and reports the backlog — a visible
  number on the Administration screen rather than a silent no-op, which is the
  fourth time this codebase has needed that cure.
* An in-process scheduler runs the measured scan and delivery every
  `ALERT_SCAN_INTERVAL_HOURS`. **The breach-due scan is deliberately not
  automated**: it is dry-run by default for a stated reason (§4e), and the
  Administration screen shows when one is due.
* `/public/risk/blocks/search`, `/blocks/at` and `/public/risk/advisories` are
  unauthenticated — what registration needs before an account exists, and what
  the front page shows before anyone signs in. Published text only; the
  `advisories_read` policy refuses a draft before the code sees it.
* `scripts/seed_demo_story` puts one complete story into an empty deployment,
  through the service layer, as the single admin loaded by role.

**What is still true, and must be said:**

* **No SMS.** Email only. A resident without email is reached only through the
  portal, and the proposal's "local communities" include people with neither.
* **Email requires a provider the operator configures.** The code is done; the
  channel is open only once `SMTP_*` and a verified sender are set on the host.
  Until then the Administration screen says "Email not configured" and counts
  what is waiting.
* **Demo addresses on `.local` are skipped**, not sent, so the four README
  accounts never receive anything — a real address does.
* **The scheduler is in-process.** On a host that sleeps the API (Render's free
  tier), it runs only while the API is awake. The backlog count is how you tell.
* **The CARTO basemaps had begun watermarking every tile** ("API KEY REQUIRED")
  for browser requests while serving clean tiles to `curl`, so nothing in the
  code looked wrong. Replaced with OpenStreetMap and Esri sources, verified
  with browser-shaped headers. Keyless remains the rule.
* The portal's root is now a public front page, and the theme is light by
  default with dark one click away. Neither changes a number.

---

## 4h. R17 (2026-09-20) — the pre-report pass

Five items from `docs/PRE_REPORT_AUDIT_AND_PLAN.md`, implemented and verified;
`docs/PROJECT_FREEZE.md` is the factual record for the report. Findings worth a
line here rather than in a changelog:

* **The β retrain** (§1d, closed) moved the Jaduguda uranium extent from ~11 m to
  ~21 m and the sulfate extent from ~32 m to ~73 m at 20 yr; the P90 band now
  reaches ~100 m (U) and ~470 m (SO₄). The published footprint still intersects
  blocks on the central contour, so alert counts did not change; the P90 envelope
  raises a separate `possible_reach` alert at *warning*.
* **Alert tiers use IS 10500's own two limits.** *Warning* = above acceptable within
  permissible; *alert* = above permissible or above acceptable where the standard
  allows no relaxation; *critical* = ≥ 2× the alert limit or ≥ 2 health determinands
  over their limit at one well — the one **project-defined** rung, labelled as such
  in the rule text stored on every row. A modelled result can never be critical
  (`ck_modelled_never_critical`). Selecting on the acceptable limit made the warning
  rung reachable: **21 wells** between fluoride 1.0 and 1.5 mg/L that the old scan
  (permissible only) never raised. On the local record: 3 critical, 29 alert,
  21 warning measured alerts.
* **The fourth instance of the RLS-after-COMMIT class** (§1c): an upsert needs an
  UPDATE policy, and `alerts` had none. Refused on the first rebuild against a real
  database, invisible to the suite. Migration `0026` adds `alerts_update`.
* **Timeline frames** are separate engine evaluations at up to ~15 horizons, stored
  on the run; a run stored before R17 reads as *not recorded*. The ML band is
  evaluated per frame but not drawn at intermediate horizons on the console, because
  the band ellipses belong to the run's own horizon.
* **Sensitivity** (§1e): K first, β second, then gradient and Kd; the fracture
  aperture, De and ω contribute ≈ 0 to the plan-view outputs at 20 yr; the leach-disc
  growth constants govern the footprint area. Uranium at a non-ore pin is constant
  over the whole design (source suppressed) and is reported as degenerate, not as an
  index.
* **The charge balance finding** (§3): the 2023 file balances by construction.

### 4h-i. Post-freeze fix (2026-09-21) — the lifecycle chart said "no source term" over a 14,000 ppb curve

Found by the owner on the deployed Jaduguda report. The registered site is
0.35 km outside the deposit polygon, so the ore mask classes it **belt**: ore
assumed at low confidence, uranium C0 scaled ×0.30 (14,294 ppb, not zero;
`u_suppressed` false). The engine reports that reduction through the same
`notice` field it uses for a **none** zone, where C0 is forced to trace and
`u_suppressed` is true. `lifecycle.py` copied whichever notice arrived into
`series.suppressed`, and the chart prefixed it "No source term for this
contaminant here." Both cases now travel in separate fields, split on
`hydro.u_suppressed`, and the chart words each honestly. The frame and sweep
services were checked and do not share the defect.

Recorded alongside it, because it reads as a contradiction and is not one: a
uranium sweep point can show *1 ppb at the ring* and *excursion* on the same
dot. The NUREG-1569 2-of-3 test is judged on chloride, TDS and sulfate at the
ring (`EXCURSION_ONLY_SPECIES` + the two ML species), and NUREG rejects uranium
as an indicator because it is retarded (R_eff ≈ 270 here; the uranium front is
26 m from the wellfield at 20 yr, the ring is at 100 m). Every sweep and
lifecycle point now carries `excursion_indicators`, and the chips name them.
Physics unchanged; response schemas gained two additive fields.

### 4h-ii. Post-freeze fix (2026-09-21) — a restored or long-idle source zone could read cleaner than the aquifer around it

Found while checking the sulfate/TDS lifecycle traces the owner asked about
next. Two mechanisms weaken the served source-zone reading after injection
stops — the restoration-sweep credit, and a passive 30-yr-half-life flush that
applies even with **no** restoration planned — and neither had a floor: both
multiply the *absolute* source concentration by a fraction that can fall
arbitrarily close to zero. For a species whose natural background is a large
fraction of its lixiviant C0, that decays the source zone past the water that
is supposedly doing the flushing, which is backwards — passive flushing is
regional groundwater, already at background, so the best it can do is return
the source zone to background, never below it.

At the registered Jaduguda site this was not an edge case: TDS's background
there is 1,779 mg/L (against a 3,656 mg/L source), and TDS's own Texas-derived
restoration ratio (0.337, from real paired pre/post ISR data) already lands
below it — a **routine 5-year restoration sweep held the "source strength"
line at 1,232 mg/L indefinitely**, and an unrestored trace crossed the same
line by ~39 years into the 50-year horizon slider (1,385 mg/L at year 50).
Sulfate's own ratio (0.138) landed within 1% of its background — not yet
wrong there, but not far off. Uranium and radium were never at risk: their
natural backgrounds (~1 ppb, ~23 mBq/L) are negligible next to their C0.

**Fix**: `params_from_features`/`simulate_plume`
([transport.py](../ml_pipeline/physics/transport.py)) gained an explicit
`floor_source_at_background` argument (default `False`, so nothing changes
unless a caller opts in) that floors the post-closure source reading —
`C_res`, which the disc display and the restoration deficit-wave both derive
from — at that site's own resolved `background_conc_Cb`. It is a plain
function argument, not a per-site override, so it applies to any Jharkhand
coordinate through the same served path, keyed on whatever background that
coordinate resolves to. The three live-serve callers
(`ml/predict.py:predict_analytical`, `dashboard/server.py`'s contour build,
`dashboard/isr_excursion.py`'s ring check) and the R17 sensitivity tool
(`validation/sensitivity.py`, "one analytical engine evaluation" by its own
docstring) now pass `True`. A second, independently-computed diagnostic
(`restoration.source_conc_after_restoration` in `predict.py`) was found to
read the pre-fix number and would have silently disagreed with the now-fixed
field — exactly the "diagnostic contradicts the field" defect class QA F-3
already fixed once — and was floored the same way.

**Initially not mirrored in `ml_pipeline/synthetic/generate.py`** — that
module's copy of this same block builds the ML surrogate's (P10/P50/P90)
TRAINING labels for `affected_area_ha` / `max_migration_distance_m` /
`compliance_conc`, and flooring it moves those labels for the same narrow set
of scenarios (high-background species, restored or long-idle runs), which
needs a re-bake and retrain to avoid reintroducing the train/serve divergence
this project has hit three times before. `ml_pipeline/tests/test_attenuation.py`
covers the floor generically (no site involved) and end-to-end at seven real
Jharkhand pins across five districts, including a diagnostic-consistency
check, before the retrain below.

**Closed same day — model card v5** (`python -m ml_pipeline.synthetic.generate
--scenarios 900 --mc 48` → `ml.train` → `ml.shap_analysis` → the 120-scenario
field-mix=1.0 batch → `field_coverage` → `tools.sync_docs` →
`validation.sensitivity --n 256` → `validation.end_to_end_audit`, full chain,
same day). `_draw_params` (the per-MC-draw path `mc_band_labels` and
`excursion_probability` both use) and `label_row`'s central-reference
`simulate_plume` call both now floor at the scenario's own `Cb`, unconditionally
— generate.py has no live-serve/training split to preserve, so there is no
opt-in flag there, only in `transport.py`'s shared function. 18,000 training
rows / 900 scenarios rebaked; retrained surrogate moved only within noise of
v4 (e.g. `max_migration_distance_m` pooled R²(P50) 0.444 → 0.504, per-species
R²(log) changes all under 0.01) — expected, since the fix touches a narrow
scenario slice. Field-resampled coverage: **PASS on all 3 targets**
(0.885 / 0.875 / 0.881 scenario coverage, gate 0.80). End-to-end audit:
**43/44**, the one failure the same pre-existing, already-disclosed radium
R²(log) gate (`max_migration_distance_m` 0.500, `compliance_conc` 0.235 — both
still reported honestly, not moved). `ml_pipeline` suite (373) green against
the new artifacts; `backend` suite (522) re-run green too (it calls the
engine in-process, so it exercises the retrained model, not a mock) —
including `test_ml_artifacts_are_unchanged`, the guard that specifically
fails on any undeclared model change; its baseline hash file
(`backend/tests/ml_artifact_hashes.json`) was regenerated as part of this
commit, deliberately, for exactly the reason its own failure message names.
No remaining gap: the live analytical path and the trained surrogate now
agree on the corrected physics everywhere.

---

## 4a. The aquifer-reach alert, and what bounds it

Publishing now raises a second kind of alert — `aquifer_pathway` — for blocks
that share the shallow aquifer a modelled vertical pathway would enter but that
the horizontal footprint never touches. It is a different claim from the
footprint alert and is worded as one: *you share this water body*, never *your
water is affected*.

**Three gates, because any one alone over-claims:** breakthrough must be credible
within the run's own horizon; the aquifer is resolved by point-in-polygon under
the site; and the reach is bounded by advective travel, `v = K·i/φ` over that
horizon, capped at 25 km.

**Alerting the whole formation was rejected.** The Basement Gneissic Complex
alone covers 48,047 km² — over half of Jharkhand — so "every block touching the
aquifer" would turn one hypothetical 13-hectare plume into a statewide warning.

**Be honest about how often this fires: almost never, and that is the finding.**
Shallow groundwater in Jharkhand's hard rock moves ~1.5 m/yr (Phyllite: K 0.08
m/day, φ 0.04, i 0.0021 → 27 m in 20 years). Even the state's fastest unit, Older
Alluvium (K 5.0, φ 0.3), reaches only ~255 m in 20 years. At every currently
registered site the reach is tens of metres, so the blocks within it were already
alerted by the footprint and this adds nobody. Lateral shallow transport does not
carry a plume to the next block within any period these runs model. The count of
blocks sharing the *formation* is recorded in the audit entry as context and is
explicitly **not** a basis for alerting.

**Not modelled:** movement inside the shallow aquifer after breakthrough. There
is no shallow plume solution in this product. The radius decides *who is told*;
it is not a predicted extent, and the alert body says so.

---

## 4b. Runs stored before 2026-08-20 have no shallow-aquifer record

`shallow_impact_screening` ran on every simulation and its result was thrown
away: the engine returns it at the top level of the payload, not inside `hydro`,
and the persistence step assigned `hydro` alone. So the breakthrough time a user
read on screen came from the live preview and existed nowhere afterwards.

Now stored at `hydro.vertical`. Older runs carry no `vertical` key, and readers
must treat its absence as **"not recorded"**, never as "no pathway" —
`announce_aquifer_reach` returns `reason: no_vertical_screening` and says so
rather than reporting a clean result.

---

## 4c. Closed (2026-08-20) — five deployment findings

From `docs/local/audit-record/DEPLOYMENT_AUDIT_2026-08-20.md`. The audit's verdict was
**NO-GO**, and the reason was worth recording: none of the blockers were product defects.
The application logic passed every P0 check — an unpublished advisory could not reach a
citizen by any of four routes, the citizen surface carried no site or model internals,
and role separation held. What blocked deployment was configuration nobody had been
forced to get right.

| # | Finding | Fix |
|---|---|---|
| F-1 | Working **admin** credentials compiled into the production bundle | Behind `import.meta.env.DEV`; a build-time guard greps `dist/` and fails the build |
| F-2 | `/metrics` served Prometheus output to anyone | Bearer token via `METRICS_TOKEN`; not mounted in production without one |
| F-3 | Dataset writes had **no lock** — two concurrent syncs silently lost one | Postgres advisory lock, `409` on contention, dry runs exempt |
| F-4 | Inert row-level security logged a warning and started anyway | Refuses to start with `APP_ENV=production` unless `ALLOW_INERT_RLS` is set |
| F-5 | `Cache-Control: no-store` on 4 of 21 routers | Default for every `/api/` response; public layers keep their own header |

**One correction, recorded because the mistake is instructive.** The audit first stated
that the development database connects as `postgres` and that RLS was therefore inert
locally. That was wrong — it was read from the default in `config.py` rather than queried
from the live connection, which is precisely the failure the audit's own opening rule
warns against. The API connects as `jaldrishti_app`: no superuser, no `BYPASSRLS`, 19
policies, **RLS genuinely in force**. The blind spot is real only for the *test* database,
which is built from ORM metadata and has no policies at all.

**Still open after this pass:** backups are undefined and no restore has ever been tested;
PDF pagination is unconfirmed; simulations have no reaper for runs orphaned by a restart;
and the engine rate limit is per host, so every user behind a gateway shares one bucket.

---

## 5. The claims this project should not make

Written down because they are the ones most likely to be overstated in a report or a
presentation:

- **Not "real-time".** There is no sensor ingest and no telemetry. This is a
  screening and preparedness tool over historical CGWB data. R13 considered
  building a telemetry-ingest contract fed by a replay of the existing series and
  **deliberately did not**: a 2013-2021 replay dressed as a live feed would be
  the single change in this project most likely to be read as a capability it
  does not have. **What R16 did close is the other half of the CPS claim** —
  threshold → alert → notification → acknowledgement now runs end to end on the
  manual/CGWB record (§4g). The sensing layer remains a 415-station manual
  network; say "CPS-ready decision support", never "a live CPS loop".
- **The level trends are not a forecast.** Theil-Sen describes what the
  measurements did between 2013 and 2021. Nothing is extrapolated forward, and a
  station with fewer than 8 readings or under 3 years of record gets no trend at
  all rather than an uncertain one. **The same holds for the 2000–2021 chemistry
  trends (R17)**: general chemistry only, no health determinand, nothing
  forecast, and a station under 4 analyses or 3 years is a baseline, not a trend.
- **A timeline is not a prediction of when.** Frames are separate engine
  evaluations at fixed horizons; "first exceedance at the 8-year frame" means the
  crossing lies between the 5- and 8-year evaluations of a hypothetical scenario,
  not that anything will happen in year 8.
- **An alert tier is not a health determination.** *Critical* is a project-defined
  multiple of a published limit at one well on one sample; it says nothing about
  exposure.
- **The IS 10500 assessment is not a health determination.** It compares a
  laboratory value with a published limit. It says nothing about exposure,
  duration, treatment at the point of use, or what anybody actually drinks.
- **A "Low concern" band is not a clean bill of health.** It means the
  determinands that were *analysed* came back within limits. Arsenic and iron
  were analysed nowhere in Jharkhand, so no block has been fully cleared, and
  `untested_health` says which substances were never looked for.
- **`aquifer_breach_due` is not a detection.** Nothing has been measured and no
  mine exists. It reports that a published model's own timetable has run out.
- **Not "validated".** Benchmarked against exact analytical solutions, yes. Validated
  against a real plume, never — see §0.
- **Not "scalable to other mining contexts", yet.** The architecture is built for it (the
  species registry splits `SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES` so
  indicators can be added without retraining), but nothing outside uranium ISR in
  Jharkhand has been demonstrated. Claim it as designed-for, not shown.
- **The ML surrogate is not more accurate than the engine.** It was trained on that
  engine's output, so it cannot be. It contributes calibrated uncertainty bands, and
  outside trained support even that guarantee is void — which the UI says out loud.

---

## 6. Where the assumptions live

Ungrounded constants are not hidden in this file. They are registered in
`ml_pipeline/config/parameters.py` as `UNGROUNDED_PARAMETERS`, exposed at
`GET /api/v1/ml/assumptions`, surfaced in the portal, and test-pinned. Provenance for
every physical constant is tracked in `ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`.

**Admin editing of those constants is NOT built.** It was scoped in R11 and deliberately
left out: an edited constant is one of the few changes that genuinely invalidates the
trained surrogate, because every training label was generated using the old value. Building
the editor without the retrain-and-revalidate path behind it would let someone silently put
the model and its own constants out of step. The constants remain code, changed by a commit
that a reviewer can see.
