# Jharkhand ISR Fidelity Matrix — The Raw Truth

**Date:** 2026-07-16 · **Scope:** full-system audit of `ml_pipeline/` against real
Singhbhum Shear Zone (SSZ) geology and real commercial ISR practice.
Companion to `ARCHITECTURE.md` (how it works) — this document says **how true it is**.

**The one-sentence verdict up front:** this system is an honest, well-instrumented
*contamination-screening* tool wearing real Jharkhand data, but its *operational ISR
physics* is Texas sandstone physics adapted with recognized fractured-rock overlays —
and one premise-level disconnect (commercial ISR is not physically plausible in
schist-hosted ore) must never be forgotten when reading its outputs.

---

## Direct answers to the four audit questions

### Q1 — The Hard-Rock vs Sandstone problem

**How heavily do we lean on Tang to make a porous-media equation mimic schist?**
Heavily, and knowingly. The base solution (Domenico) is a porous-continuum model.
Fractured behavior is layered on through three overlays:

1. **Dual-porosity retarded clock** (Goltz & Roberts): apparent late-time
   retardation `1+β`, β sampled 2–20 (central 8–10 → the UI's Rd ≈ 11).
2. **Tang/Neretnieks matrix diffusion** (aperture 100–500 µm, De = 5×10⁻⁶ m²/day):
   the early-arrival envelope, taken as `max(continuum front, Tang)` — a
   *conservative union*, so Tang can only extend the plume, never shrink it.
3. **Real fracture-strike anisotropy** (GSI lineaments → circular variance V →
   α_T/α_L 0.01–0.10 + flux-azimuth rotation).

This is the standard "equivalent porous medium + matrix-diffusion overlay"
screening approach — *defensible for screening, indefensible for prediction*.
What it cannot do: discrete fracture networks, channeling along individual
structures, flow-wetted-surface statistics, or connectivity percolation. A real
SSZ plume would be a few narrow fingers along shears, not a smooth ellipse.

> **Superseded in part, 2026-08-10.** "The UI's Rd ≈ 11" was true of the number
> the UI *displayed* and false of the retardation the engine *used*. `1+β` is the
> CONSERVATIVE-TRACER value; since the sorbing-capacity correction the kinematics
> run on `β_eff = β·R_m`, which at fractured Jharkhand materials is **720 for
> uranium and ~9,400 for radium**. The UI now shows the effective value with the
> tracer value beside it. The paragraph below is still correct about the
> *mechanism* (capacity retardation, not bulk sorption) — only the magnitude it
> quotes was the wrong one of the two.

**Is Rd ≈ 11 defensible?** As an *order of magnitude*, yes — it is **not sorption**
(the code correctly refuses bulk-density Kd retardation in fractured rock,
`feature_engineering.py:96-112`); it is matrix-capacity retardation `1+β` with
Kd acting only inside the Tang matrix term (`matrix_sigma`). That structure is
textbook-correct (Goltz & Roberts 1986; Neretnieks 1980). But β = 2–20, the
aperture range, De, and the transfer rate ω = 10⁻³/day are **generic crystalline-rock
literature values — zero Singhbhum measurements** behind any of them.

### Q2 — Hydro parameters: Jharkhand-real or Texas-borrowed?

Mostly **Jharkhand-real, but shallow-aquifer-real**:

- **K, φ, T, thickness**: from the CGWB `Aquifers_Jharkhand.geojson` polygons —
  real Indian data (schist K 1.88 / 1.12 m/day), *not* Texas values. The D5
  shear-zone correction (T = 207–570 m²/day, NAQUIM E. Singhbhum) is also real.
- **Hydraulic gradient**: *not* a fixed baseline — the D1 flow field plane-fits
  real CGWB water-level stations (DEM fallback), so the ~0.0019–0.006 values are
  data-derived per pin. This is one of the most genuinely local parts.
- **The catch:** all CGWB values characterize the **drinking-water aquifer
  (weathered + upper fractured zone, tens of m)**, and we apply them at ore depth
  (140–600 m). Crystalline-rock K typically falls 10–100× with depth; we have no
  K(z) model. The deep plume is therefore probably **too fast/too leaky** in-model.
- **Monsoon**: represented *statistically*, not dynamically — the real pre/post-
  monsoon water-level swing sets `gradient_seasonal_amp`, which widens the MC
  gradient range and hence the bands. There is no transient recharge pulse, no
  seasonal flow reversal, no water-table rise/fall in the solution itself.

For reference, the commercial ISR window is roughly K ≈ 0.1–10 m/day in
*porous, confined sandstone*; our shear-zone K = 2.47 m/day sits numerically
inside that window but is fracture-dominated — same number, different physics.

### Q3 — Is the attenuation range (k = 0.05–0.7/yr) right for SSZ mineralogy?

**Direction: yes. Magnitude: borrowed.** The range is anchored to a Wyoming
unmined roll-front cross-hole test. The Jaduguda host assemblage — uraninite in
quartz-chlorite-biotite schists with abundant **chalcopyrite, pyrite, pyrrhotite,
marcasite, molybdenite** (it is simultaneously a copper belt) plus Fe²⁺-bearing
chlorite/biotite — has real, arguably *rich* reducing capacity per rock volume.
Two opposing local effects we cannot quantify:

- **Against attenuation**: fracture flow contacts only the flow-wetted surface —
  a tiny fraction of that reductant inventory — so the *effective* field k could
  be well below the matrix chemistry's potential.
- **For attenuation**: matrix diffusion (which we model via Tang) actively carries
  U *into* the reductant-rich matrix — a real synergy sandstones don't have.

Sampling k over a 14× range into the P10–P90 bands is the honest treatment of
this ignorance; a single "Jharkhand k" would be fiction. Depth-variability of
sulfide content: acknowledged, unmodeled.

### Q4 — Does the ML create spatial seams between Ranchi and Jaduguda?

**No — empirically probed and cleared.** A 13-point transect Ranchi→Jaduguda
(sulfate, both engines) shows every step is **co-located with a data boundary and
present in BOTH engines**: the aquifer-polygon K edge near 85.75°E (analytical
−16.5 ha, ML −25.1 ha) and the shear-zone override at the deposit (+7.2 vs +9.8).
The surrogate has **no lon/lat features** — space enters only through resolved
physics parameters, so it *cannot* invent spatial artifacts of its own; it tracks
the analytical through every boundary with a 3–38% gap (largest where the flow
field's gradient peaks), consistently on the conservative (high) side, inside the
calibrated bands. The real seams are **data seams**: hard CGWB polygon edges and
the binary shear-zone/deposit switches. Tree quantization exists on *parameter*
axes (≈17% migration step across rest 0→0.5 yr; ≈0.9 ha at the restoration
boundary) — verified to sit inside the 80% conformal bands (6/6 + 12/12 checks).

---

## The Matrix

### Tier 1 — HIGH FIDELITY (genuinely real-world, genuinely local)

| # | Component | Why it qualifies |
|---|---|---|
| 1.1 | **Aquifer properties** (K, φ, T, b per polygon) | CGWB-published Jharkhand data, incl. the D5 NAQUIM shear-zone transmissivity (207–570 m²/day) exactly where the mines are |
| 1.2 | **Groundwater flow field** (gradient + azimuth per pin) | Plane-fit of real CGWB monitoring-station levels; DEM fallback; divide detection; the plume travels where Jharkhand water actually flows |
| 1.3 | **Fracture fabric** (plume elongation + azimuth rotation) | Real GSI lineament map → axial statistics → anisotropy; the plume shape responds to the actual SSZ structural grain |
| 1.4 | **Ore geography & grades** | UCIL deposit polygons + IAEA-UDEPO grades; uranium source exists only where uranium ore exists; per-deposit depths (Jaduguda 180 m, Banduhurang 60 m…) |
| 1.5 | **Water-quality baselines** | Real CGWB wells; incremental-exceedance logic prevents blaming mining for natural background |
| 1.6 | **Vertical stratification** | Per-district NAQUIM fracture-zone depths (E. Singhbhum 20–258 m), real post-monsoon water table as the shallow receptor |
| 1.7 | **Timeline logic** | Three-phase front; elapsed-credit restoration (causal — planned future cleans nothing); saturation at the post-closure window; dual-rate decay matching EPA MNA guidance (distance + time constants) |
| 1.8 | **Restoration empirics** | Endpoint residuals + 5.0-yr sweep anchor from real Texas operator records (13 production areas); EPA 30-yr horizon grounds the flush half-life |
| 1.9 | **Receptors** | HydroRIVERS perennial reaches with real discharge; precise plume-polygon crossing detection |
| 1.10 | **Uncertainty honesty** | Conformal 80% bands (verified coverage gates), extrapolation flags, drift monitor, ~zero-U plume enforced outside ore zones |

### Tier 2 — ENGINEERING APPROXIMATIONS (defensible screening trade-offs)

| # | Simplification | Trade-off assessment |
|---|---|---|
| 2.1 | 2-D plan view + decoupled vertical screening | BIOSCREEN-class standard; loses true 3-D plume shape |
| 2.2 | Domenico closed form (incl. its upstream-box artifact, managed by the disc/wall design) | Milliseconds instead of hours per run; second-order vs parameter uncertainty |
| 2.3 | EPM + dual-porosity + Tang overlay for fractured rock | The right *structure* for screening; conservative union; can't do discrete networks |
| 2.4 | Steady-state flow, monsoon as statistical amplitude | Bands carry the seasonality; no transient dynamics |
| 2.5 | First-order attenuation, infinite-sink, k sampled 0.05–0.7/yr | Standard screening form; finite reductant capacity acknowledged, not modeled |
| 2.6 | Plug-flow age for decay (x/v_c + hold time) | Approximate front shape near the toe; error ≪ k uncertainty |
| 2.7 | Homogeneity per polygon + lognormal K in MC | Heterogeneity is statistical, not spatial — no channels |
| 2.8 | ML tree quantization within calibrated bands | Verified: analytical stays inside P10–P90 at every probed seam |
| 2.9 | `operation_years` up to 20 = sequential mine unit compressed onto one footprint | Real single wellfields run 1–3 yr; interpret long ops accordingly |

### Tier 3 — FLAWS / DISCONNECTS (the raw truth + the fix)

> **STATUS UPDATE 2026-08-01 — fixes 3.1, 3.2, 3.3, 3.5 and 3.6 are now
> IMPLEMENTED** (all serve-side, no retrain; **135 tests pass**, regressions
> pinned in `tests/test_phase1_fixes.py`). Rows below carry ✅ / 🟡 / 🔴 with
> exactly what changed and what remains.
>
> **Data-availability verdict for the still-open items** (searched 2026-07-31 and
> 2026-08-01; downloaded sources archived in `Datasets/phase1_sources/`):
>
> | Fix | Verdict |
> |---|---|
> | **3.4** fracture β / aperture / Dₑ | 🔴 **Data does not exist publicly.** SSZ literature is structural geology only — no packer or tracer test published. Left as an explicit limitation |
> | **3.7** monsoon transients | 🟡 Seasonal water levels are already on disk (CGWB) — this is a *modelling* task, not a data gap |
> | **3.8** As/Ni/Cu/Co | 🟡 Sorption (Kd) data **found and archived**; the ISR **source term** for SSZ ore does not exist publicly → cannot build honestly |
> | **3.9** Ra-226 | 🟢 **Fully unblocked** — source term, background and Kd all now in hand; build deferred only because it forces a retrain |
> | **3.10** field validation | 🔴 **Permanently impossible** — no ISR plume has ever been measured in Jharkhand |

| # | Disconnect | Why it matters | Concrete fix for v-next |
|---|---|---|---|
| 3.1 | ✅ **FIXED** — **The premise**: commercial ISR is physically implausible in SSZ schists (every commercial ISR mine on Earth is unconsolidated sandstone) | The tool must be read as "IF ISR-strength lixiviant entered this aquifer, where would contamination go" — never as mine feasibility | **Done:** UI retitled "ISR Contaminant Excursion Screening"; scope line states *"Not a mining feasibility tool"*; disclaimer now leads with the sandstone-vs-schist premise mismatch |
| 3.2 | ✅ **PARTLY FIXED** — **Texas source term** transplanted to uraninite-in-schist chemistry | Alkaline leach kinetics of massive uraninite + polymetallic sulfides differ from roll-front coffinite | **Done:** the API now reports a `source_term_context` block comparing the served C0 against **measured** Jaduguda mine-water uranium (94–843.3 ppb, GM 357.4; Sethy et al. 2013, DOI 10.4103/0972-0464.121824 — full text archived in `Datasets/phase1_sources/`). At Jaduguda the model runs **37× the measured passive mine water** — the transplant gap is now *reported, not hidden*. **Still open:** replacing C0 outright needs SSZ leach-column tests (UCIL/AMD) |
| 3.3 | ✅ **FIXED** — **K at drinking-aquifer depth applied at ore depth**; no K(z) decay | Deep plume too fast/too leaky; velocity errors propagate into every metric | **Done:** `P.depth_decay_factor()` applies `K(z) = K_ref·exp(−(z−45)/λ)`, with λ calibrated **per district from its own NAQUIM-documented fracture-death depth** (`naquim_vertical.csv fracture_max_m`; E Singhbhum 258 m, Ranchi 121 m). Grounded in the auto-extracted evidence digest `naquim_depth_evidence.md` — *"fractures generally die down with the depth and below 175 m"* (Deoghar), *"none beyond 180 m"* (W Singhbhum), *"common within 45 m"*. Result at Jaduguda 180 m: K 2.467 → 0.369 m/day, plume 31 → 14 ha. Clamped into the trained K box so **no retrain and no extrapolation flag**. Tunable via `K_DEPTH_DECAY_STRENGTH` |
| 3.4 | 🔴 **BLOCKED — DATA DOES NOT EXIST PUBLICLY.** Fracture parameters ungrounded locally (β 2–20, aperture 100–500 µm, De, ω all generic literature) | The entire fractured-transport overlay rests on them | **Searched 2026-07-31 and 2026-08-01 — confirmed unavailable.** The SSZ literature is extensive but entirely *structural/economic geology* (shear-deformation timing, textural development, IOCG mineralisation, geophysical alteration mapping) — **not hydrogeology**. No packer test, tracer test, or measured fracture aperture for the Singhbhum belt is published. Nearest usable analogues are foreign crystalline sites (SKB Äspö, Stripa, Nagra Grimsel) and NGRI Maheshwaram (Indian granite, different province). UCIL holds packer/dewatering records institutionally but has not published them. **Deliberately NOT "fixed"** — inventing a local-sounding value would relabel an assumption as data. Values remain flagged in config as foreign-analogue literature |
| 3.5 | ✅ **PARTLY FIXED** — **Attenuation k Wyoming-borrowed** despite different (sulfide-rich, depth-variable) mineralogy | The equilibrium plume extent x* ∝ 1/k — first-order sensitive | **Done:** the sampled k's *mode* is now graded by ore-zone mineralogy (`U_ATTENUATION_MODE_BY_ZONE`): deposit 0.35 → belt 0.28 → non-ore 0.12 /yr, reflecting the documented polymetallic-sulphide load (chalcopyrite/pyrite/pyrrhotite) inside the Singhbhum belt versus oxidised country rock. The (lo, hi) envelope is unchanged so every value stays in trained support. **Still open:** absolute rates remain literature-derived — SSZ batch/column reduction tests or NRC post-restoration stability curves would replace them |
| 3.6 | ✅ **MOSTLY FIXED (claim narrowed 2026-08-05 — see the correction note below the table)** — **Data seams**: hard steps at CGWB polygon edges and the binary deposit/belt/shear-zone switches | A pin moved 1 km across a map line can jump ~2× in plume size — users will notice and distrust | **Done (no new data needed):** `aquifer_at_point` now blends K across mapped contacts — `w_own = 0.5 + 0.5·min(d/L, 1)` in log-K space, L ≈ 2.2 km. At a contact the weight is 0.5 **from both sides**, so K is provably continuous across every boundary, and it returns to the untouched mapped value at distance L. The QA transect's worst single-step area jump fell **16.5 ha → 4.75 ha**, and the mid-transect polygon seam to ~2.3 ha. Blend is disclosed via `_k_blend` (never silent) and disableable via `K_BOUNDARY_BLEND_ENABLED`. **Measured while doing this:** the CGWB layer is finely interleaved — a random in-polygon pin is a median of only **~1.4 km** from a contact, so K is genuinely uncertain at most locations; this is a smoothing of the whole field, not a patch on a few edges. **3.6b also now done:** the deposit→belt source-strength tier was a hard ~3.3× step at the ore outline; C0 is now ramped linearly from the nearest deposit's own grade-scaled value down to the flat belt value over `ORE_TAPER_KM` = 3 km. Worst adjacent uranium C0 ratio along a walk out of Jaduguda: **3.33× → 1.05× at the outline**. Two bugs were caught and fixed in review while doing this — clipping the ramp to the raw Texas envelope let a halo pin 200 m from Jaduguda resolve *stronger than the deposit itself* (21,088 vs 13,272 ppb), and the same clip pushed the far-belt value *up* to the envelope floor, erasing the belt tier's deliberate weakness. **Deliberately NOT tapered:** the belt→**none** transition. "None" means no uranium ore, and smearing source strength into non-ore rock would break the existing "the tool cannot invent contamination" guard — that step is a real physical boundary, not an artefact |
| 3.7 | ✅ **PARTLY FIXED — vertical half built; horizontal half measured and deliberately declined.** No monsoon transients (recharge pulses, seasonal flow reversal near divides, water-table swing in the vertical module) | Jharkhand's defining hydrologic feature was represented only as band width | **Measured 2026-08-03 from `cgwb_waterlevel_jharkhand.csv` (9,583 readings, 398 stations, 2013–2021).** **(a) HORIZONTAL — declined on evidence:** seasonal swing of the horizontal gradient is negligible — direction p50 **2.5°** (p90 11°, **zero cells reverse**), magnitude ratio p50 **1.05** / p90 1.23. The monsoon lifts every head together, so it barely rotates or steepens the regional gradient. The MC already samples gradient over **±30% minimum**, so an alternating two-season front would add structure entirely *inside existing noise* — at the cost of a full 18k-row retrain. The matrix's own original premise ("seasonal flow reversal near divides") is **not supported by the data**; that is recorded in `P.VERTICAL_SEASONAL` rather than silently dropped. **(b) VERTICAL — built:** the water table swings **3.91 m** (p50; Aug 3.22 → May 7.20 m bgl) across the ~110–120 m ore-top→Layer-1 separation = a vertical-gradient change of **0.0355, seven times** the pinned `upward_gradient` = 0.005. The shallow-impact index is violently sensitive to it (0.005 → 30 yr *moderate*; 0.020 → 7.5 yr *high*), so the tool was reporting **one number for a parameter whose seasonal range spans contained→high**. `shallow_impact_screening()` now returns a `seasonal` block: the wet season SUPPRESSES the upward gradient (it may go negative → pathway closed, floored at 0) and the pre-monsoon dry season ENHANCES it. At Jaduguda (per-pin swing 4.72 m) breakthrough moves **11.5 → 56.8 yr**. **Reported as a TWO-END-MEMBER BAND, never a point** — `static_deep_head` (upper) vs `in_phase_deep_head` (lower, ≡ today's behaviour) — because CGWB monitors *shallow phreatic* wells (median 3–7 m bgl) and **no deep piezometry for Singhbhum is published** (UCIL/AMD, the same wall as 3.4). Sensitivity is flagged on arrival-time ratio too, not just the band label, so a pin that stays "contained" while breakthrough moves 5× is still surfaced. **No ML retrain** — the module is downstream-analytical; the 40-feature / 4-species card is untouched, guarded by `test_3_7_did_not_touch_the_trained_surrogate`. **Still open:** a true transient (recharge/discharge in time) needs a numeric solver plus local specific yield — neither is on disk |
| 3.8 | 🟡 **PARTLY UNBLOCKED — sorption data found, source terms still missing.** No co-contaminants: SSZ ore carries Cu, Ni, Co, Mo, As | Real regulatory concern for this specific ore type; we model only U/SO₄/TDS | **Found & archived (2026-08-01):** Kd values for all of these now on disk — EPA 402-R-99-004 Vol III (As, Ra), [IAEA TECDOC TE-2095](https://www-pub.iaea.org/MTCD/publications/PDF/TE-2095web.pdf) and [SKB R-09-27](https://skb.com/publication/1951648/R-09-27.pdf) (Ni, Cu, Co, Ra — note Ni/Cu are **absent from the EPA compendium**, which is why the IAEA/SKB compilations were needed). Local *background* ranges also exist (Giri et al. 2012, Bagjata/Banduhurang: Cu 0.78–20, Ni 1.05–20.1, Pb 1.4–28.4 µg/L). **Still blocked:** the **source term** — how much As/Ni/Cu/Co an oxidising alkaline lixiviant would mobilise from SSZ ore — has no published measurement anywhere (needs SSZ leach-column tests; UCIL/AMD institutional). Sorption without a source term cannot be modelled honestly, so this stays unbuilt |
| 3.9 | ✅ **FIXED (Ra-226 built AND trained).** Rn-222 still absent | Standard ISR licensing metric | **Done — every input is measured or cited, none invented:** source term = Jaduguda mine water 40–1706 mBq/L (Sethy et al. 2013); background 23 mBq/L (BARC 2008); Kd from **EPA 402-R-04-002C Vol III Table 5.28** (Sand 500, Silt 36,000, Clay 9,100 L/kg — Thibault et al. 1990); threshold = **WHO 1 Bq/L** (BIS IS-10500 sets none). Ore-zone gated (Ra is a U-decay product → no ore, no source). Verified physically: in porous media Ra's Rd = **14,841 vs uranium's 16.5**, collapsing the front 15.8 m → 0.018 m — i.e. essentially immobile, which **independently reproduces the BARC field finding** that radium does not migrate from the Jaduguda tailings pond. **Now IN the trained surrogate** (retrained 2026-08-02, 18,000 rows / 4 species / 40 features) — it was analytical-only when first built, and the ML head is now active for radium with calibrated P10–P90 bands like any other species. **Judgement recorded:** the measured *geometric mean* (371.3) lies below the WHO level, so serving it would make every screen exactly zero; the measured *maximum* (1706) is served instead as the conservative screening value, with the full distribution reported via `radium_context`. **Still open:** Rn-222; and folding Ra into the surrogate needs a deliberate retrain |
| 3.10 | 🔴 **PERMANENTLY IMPOSSIBLE.** Zero field validation — no Jharkhand ISR exists or will exist to calibrate against | The uncertainty bands quantify *parameter* uncertainty, not *structural* model error | Permanent limitation; the only honest mitigations are the disclaimer + drift monitor + this document |

---

## Correction notes — 2026-08-05 remediation (audit `review.md`, branch `fix/audit-remediation`)

An external audit ran the deployed build rather than reading it, and four of the
statuses above did not survive that. Recorded here rather than edited away,
because *how* a fidelity register goes stale is itself a finding.

### Row 3.6 — "K is provably continuous across every boundary" was FALSE

The proof held for the aquifer polygons it was written about, and was then
invalidated by two *later* changes that each added a new categorical map on top:

| seam | measured before | after |
|---|---|---|
| district λ (fix 3.3's per-district NAQUIM fracture-death depth) | K **1.74×** over ~130 m, inside one polygon and one lithology | **1.015×** |
| D5 shear-zone toggle at the belt outline | K 2.2×, thickness 4×; sulfate plume area **+37%** over 100 m | **+1.7%** |

Both are now blended/tapered with the same 0.5-at-the-border weighting the
aquifer blend uses, so the smoothings compose. The lesson is structural: fix 3.3
(2026-08-01) silently voided the guarantee 3.6 (2026-08-01) had just established,
and nothing checked. `tests/test_spatial_seams.py` now pins both at their measured
coordinates.

**A third seam remains, and is NOT fixed.** At a genuine regime contact
(Alluvium/porous ↔ Basement Gneissic Complex/fractured, 85.399 °E 23.312 °N) K
steps **2.16×** — because `depth_decay_factor`'s result is clamped into the
*deployed model's per-regime trained-K box*, and the two regimes have different
floors (0.0959 vs 0.0444 m/day). Two adjacent pins with the same physical
K(z) = 0.033 m/day are served 2.2× apart purely by which training box they land
in. Regime cannot be blended — it selects a different transport equation — so the
lithological step itself is legitimate; what is not legitimate is an **ML training
artefact setting the size of a physical discontinuity**. Fixing it means either
dropping the clamp (and accepting honest extrapolation flags) or making the
support box regime-continuous. Deliberately left open and disclosed.

### Row 3.9 — the radium verification was regime-cherry-picked

"Verified physically: in porous media Ra's Rd = 14,841 … essentially immobile,
which independently reproduces the BARC field finding" was **true in a regime no
deposit pin ever uses**. Every Singhbhum deposit resolves to *fractured* schist
with the D5 override, and in the fractured branch Kd entered only the Tang term —
which is unioned with `max()` and can therefore only ever *extend* a plume. The
served fractured radium answer was a 423 m, 13.7 ha plume identical to sulfate's:
the exact opposite of the cited validation. The test that "confirmed" the row
hard-coded `regime="porous"`.

Fixed by making the dual-porosity capacity ratio sorption-dependent
(β_eff = β·R_m, `transport.effective_capacity_ratio`). Fronts at Jaduguda t=10 yr
now separate by sorption as they always should have: TDS 13.166 m (Kd = 0,
bit-identical to before) → sulfate 2.817 → uranium 0.192 → radium 0.000. All four
previously read 13.166 m. The row's claim is now true **as served**, and its test
is parametrised over both regimes.

### Row 3.4 — uncertainty propagation was claimed but not implemented

The fracture aperture is flagged in `parameters.py` as carrying "the LOWEST
confidence of any parameter in this config", and Q3 above presents wide sampling
as this model's honest treatment of exactly that kind of ignorance. It was
nonetheless served **and trained** at its central value — every `matrix_sigma`
call omitted the aperture argument — so its factor-5 literature range contributed
**zero** variance to the P10–P90 bands. Now sampled per Monte-Carlo draw.
`De` remains fixed: `P.FRACTURE` carries no defensible range for it, and inventing
one would relabel an assumption as data. Say "aperture is propagated, De is not"
rather than "row 3.4 uncertainty is propagated".

### Not in this register at all — the metric the whole tool leads with

`max_migration_distance_m` was a radial max over the entire solution grid, so it
returned the distance to the **upstream corner of the Domenico artifact box** —
422.8 m at Jaduguda for a plume whose true down-gradient reach was 35.9 m,
identical for every species because C0 cancels. It was baked into the ML labels,
and [`docs/audits/QA_SWEEP_REPORT.md`](../docs/audits/QA_SWEEP_REPORT.md) had certified it as correct Tang physics (now retracted
there). Fixing it then exposed a second, pre-existing defect underneath: the
solution grid is sized to the source disc, so travel was quantised to zero for
short plumes — 29 of 60 sampled scenarios read exactly 0.0 m while not being
immobile at all. Travel is now measured analytically on the centreline.

Consequence worth stating plainly: **the migration P10–P90 bands were previously
meaningless.** Every Monte-Carlo draw landed on the same grid artefact, so the
band had ~zero width and the Mondrian conformal calibration was calibrating a
constant. Relative band width is now 1.3–4.0.

### Round 2 (2026-08-05) — the plume was far too small, and round 1 caused part of it

A literature cross-check (prompted by the served answer looking implausibly
contained) found the fractured uranium plume moving ~0.4 m in 20 years, against
real ISR practice where excursions are routinely detected at 100–150 m monitoring
rings. Three causes, one of them introduced by round 1:

1. **Redox trapping was double-counted** (dominant). `exp(-k·age)` charged the
   reduction rate over the **sorption-retarded** residence, `age = x/v_c` with
   `v_c = v/(1+β·R_m)`. But retardation and redox trapping both remove uranium
   from the advancing front — uranium held in the matrix by sorption is *already*
   immobilised, which is precisely what the retardation term represents — so
   charging it the reduction rate for that same residence removes the mass twice.
   It also asserted ~900× more reduced uranium than the finite reducing capacity
   this config already flags as unmodelled. Measured: **0.4699 decay per metre**,
   i.e. the plume annihilated within 1 m, below the model's own grid resolution.
   Now charged on the mobile residence: 0.00587/m, which back-checks against the
   Wyoming test that calibrated k (100 m in 3.6 yr losing ~50%, vs ~50% in ~1 yr
   observed). **This was a round-1 side-effect**: β_eff correctly retarded the
   front and simultaneously, silently, inflated the attenuation by the same 82×.

2. **The leach-zone disc existed before the mine did.** Drawn at full radius and
   full C₀ from t = 0 — π·(150 m)² = **7.07 ha of "vulnerable area" at zero pore
   volumes injected**. Radius now scales `√(min(1, PV))`, so area grows linearly
   with throughput from nothing and saturates within weeks. Training times start
   at t = 2 yr, so this changes the served early-time answer only.

3. **Depth decay is real but secondary** — 4.08 m at 50 m ore depth against
   0.44 m at 180 m, a ~9× effect, versus the attenuation's ~80×.

**A fix that was implemented, measured and rejected** — recorded because the
reasoning outlives the decision. Deriving ω from fracture geometry
(ω = 3·D_e/(R_m·L²)) is self-defeating: β_eff·ω = 3·β·D_e/L², **R_m cancels**, so
early-time retardation becomes species-blind — the exact defect β_eff exists to
remove (radium's front rose to 9.50 m against uranium's 13.22 m). The deeper
reason is that a first-order mobile/immobile model *cannot* represent early-time
matrix diffusion: true uptake grows as √(R_m·D_e·t), so retardation scales as
√R_m, and the first-order form can only deliver R_m or R_m⁰. The **Tang kernel
already carries the correct √ scaling** and governs through the `max()` — fixing
(1) is what let it win. `OMEGA_FROM_GEOMETRY` and the derivation of the √t clock
that *would* fix the continuum branch are retained in config, default off.

**Correction to a claim made during this work:** the fixed ω was described as
"1000× to 10⁶× off". That used an *assumed* 0.1–10 m fracture spacing. The
model's own aperture and mobile porosity imply L = b_half/φ_mobile ≈ **1.7 cm**,
giving t_eq ≈ 14 yr for uranium against the pinned 2.7 yr — a **~5× error**.

Served effect at Jaduguda (ore depth 180 m, t = 20 yr): uranium **0.44 → 7.11 m**,
sulfate 20.00 m, TDS 77.12 m, radium 0.00 m; t = 0 area **7.07 → 0.00 ha**;
maxed-out uranium **33 → 622.6 m**. Label diff over an identical 100-scenario
pilot moved **only fractured uranium (×4.08)** and left all other regime×species
cells bit-identical — the expected signature, since uranium is the only species
with k > 0 and fractured the only regime with β_eff.

**Still open after round 2:** `wellfield_width_m` is the *diameter of the circular
well-pattern footprint*, not a width or a borehole size, and the UI label invites
exactly that misreading.

---

## Correction notes — 2026-08-10 remediation (audit `review3.md`, branch `fix/pipeline-completion`)

A third audit ran before the product-design phase. What it found, and what
changed. Rows above are left as written; this is the current state.

### Row 3.6 — the THIRD seam is now closed, and the guard that hid it was broken

The regime-contact step (Alluvium/porous ↔ Basement Gneissic Complex/fractured,
85.399 °E 23.312 °N) was left open in the 2026-08-05 note because K stepped
**2.16×** there purely from `depth_decay_factor`'s result being clamped into the
deployed model's **per-regime trained-K box** (floors 0.0959 vs 0.0444 m/day).

Fixed by **deleting the clamp**, not by widening it. The clamp existed so our own
correction would not raise an out-of-distribution flag — i.e. it suppressed
exactly the signal the user needs. K is now the physical value and
`envelope_violations` reports the consequence. Measured across the contact:
**2.16× → 1.07×**, and the residual variation is the aquifer-polygon blend doing
its job.

**A second defect surfaced underneath.** With the clamp gone the flag still did
not fire, because the hydro-OOD guard used a tolerance of **2 % of the LINEAR
span**. For fractured K (support 0.044–10.6 m/day) that tolerance is 0.21 — about
**five times the trained minimum itself** — so a served K three orders of
magnitude below support raised nothing. The guard was only ever exercised at the
*high* end (β = 50, K = 50), which is why two prior audits called it working.
Tolerances are now ratio-based for positive quantities spanning more than a
decade.

### Row 3.3 — the depth-decay law was being extrapolated past its own evidence

`K(z) = K_ref·exp(−(z−45)/λ)` is calibrated on ONE interval: 45 m down to the
district's NAQUIM-documented fracture-death depth. It was being run far below
that. For a shallow-fracture district (Ranchi, base 121 m) the factor at 300 m
came out at **4.3 × 10⁻⁵ — a 23,000× reduction**.

Two independent checks reject that. Locally, the NAQUIM reports say "massive
rock" below the fracture base — low permeability, not vanishing permeability, and
the evidence simply stops there. Globally, Manning & Ingebritsen (1999)
(log k = −14 − 3.2 log z, k in m², z in km; ~3–4 orders over the upper 2 km) give
about **440×** between 45 m and 300 m, so the model exceeded the global crustal
trend by ~50×. The decay is now **held at its fracture-base value below the
fracture base**. Serve-time only — K is sampled from polygon ranges when labels
are baked, so no retrain. Consequence: pins flagged as extrapolating at 300 m ore
depth fall from **98 % to ~10 %** of the state, and the flags that remain are real.

### Row 3.9 — Rn-222 assessed and CLOSED as scope, not as physics

The first hypothesis tested was "a 3.82-day half-life means radon cannot reach
the ring". **That is false over part of this model's own envelope** and is
recorded as such: at the p99 seepage velocity (14.3 m/day) 28 % of the radon
survives 100 m, and 4.3 % of training rows retain >1 %. Radon is not modelled for
two other reasons — there is no Rn-222 source term for this ore body (Sethy et
al. 2013 report U and Ra-226 only), and radon's governing exposure pathway at an
ISR facility is **atmospheric** (wellhead and header-house degassing), which a
saturated-zone transport model structurally cannot address.

### NEW ROW 3.11 — the excursion criterion was not the regulatory one

Not previously in this register at all. The tool declared an excursion when a
**single** species exceeded a **health limit** at the ring. NUREG-1569 §5.7.8.3
p.138 defines one as **two or more** *indicator* parameters over their upper
control limits, and p.137 explicitly rejects the species this tool led with:
*"Uranium is not considered a good excursion indicator because, although it is
mobilized by in situ leaching, it may be retarded by reducing conditions in the
aquifer."* That is the same mechanism this model computes independently
(β_eff ≈ 700 plus redox trapping), so the tool and the regulator agreed on the
physics while disagreeing on the metric.

Now implemented on the species already transported — TDS (the conductivity proxy
NUREG names) and sulfate. **Measured effect:** at Jaduguda, gradient 0.005,
t = 20 yr, the indicator test declares an excursion while the uranium health
limit is still clear. That ordering — conservative indicators warning first — is
the entire reason the indicator system exists, and the tool now reproduces it.
**Limitation, reported in every response:** a licensed panel needs ≥ 3
indicators; this model carries 2. Chloride and total alkalinity have no ISR
source term in the available data.

### NEW — post-restoration rebound, closed with data rather than a new model

Open since 2026-07-13. The source only ever decayed, while real leached zones can
rebound. The specific defect was that the served source fraction was
`restoration_credit × disc_flush_factor`, **compounding without bound**: at
op = 8, t = 50 yr it reached 0.023 × C₀, *below* the empirical Texas restoration
endpoint of 0.060.

No rebound magnitude was invented. Verified instead that the Texas endpoint is
already a post-rebound number: the sheet is headed *"Average composition of
groundwater achieved AFTER RESTORATION WAS COMPLETE"* and its footnote refers to
**"stability samples"** — the regulatory demonstration that the aquifer has
stopped changing. So the fix is to stop claiming clean-up the data does not show:
once a sweep has run, the passive flush may not take the source below the
demonstrated stable endpoint. Unrestored scenarios keep the full 30-yr flush.

### NEW — the radium restoration residual had gone stale and was a training label

`RADIUM_RESTORATION_RESIDUAL = 0.99` was computed from Kd values the config
stopped holding at the 2026-08-06 rebase (its own comment still named
"fractured: 500 vs 1.0"). Re-running the **same derivation** on the current
constants gives **0.806 (fractured) / 0.571 (porous)** — the model was asserting
a sweep removes 1 % of the radium source while its own physics said 19–43 %. It
also still used the pre-V-3 unpaired uranium anchor. Now 0.81, with a test that
re-derives it from the live constants instead of pinning the number.

---

## Bottom line

- **What is real:** where the water flows, what rock it flows through, where the
  ore is, what the background chemistry is, what real restorations achieved, and
  when things can causally happen. The *data skeleton is genuinely Jharkhand*.
- **What is approximated:** how a plume spreads in fractured rock — right
  structure (EPM + dual porosity + matrix diffusion + real fabric), generic
  coefficients, conservative unions, all wrapped in calibrated uncertainty.
- **What is fiction, honestly labeled:** that ISR mining could operate in this
  rock at all, and that Texas source chemistry transfers to uraninite-schist ore.
  The tool's value survives this because it answers the *contamination* question
  ("if this source existed here, who is downstream"), not the *mining* question.
