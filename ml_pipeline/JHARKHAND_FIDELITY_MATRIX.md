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

| # | Disconnect | Why it matters | Concrete fix for v-next |
|---|---|---|---|
| 3.1 | **The premise**: commercial ISR is physically implausible in SSZ schists — you cannot volumetrically sweep lixiviant through fracture-flow crystalline ore (every commercial ISR mine on Earth is unconsolidated sandstone) | The tool must be read as "IF ISR-strength lixiviant entered this aquifer, where would contamination go" — a legitimate excursion/what-if screen — never as mine feasibility | Keep the framing prominent (UI disclaimer exists); optionally add a "premise" note to the report header |
| 3.2 | **Texas source term** (C0 ranges per species) transplanted to uraninite-in-schist chemistry | Alkaline leach kinetics of massive uraninite + polymetallic sulfides differ from roll-front coffinite; C0 could be off in either direction | No Indian ISR data exists; lab leach columns on SSZ core (UCIL/AMD have such studies) would bound it |
| 3.3 | **K at drinking-aquifer depth applied at ore depth** (140–600 m); no K(z) decay | Deep plume likely too fast/too leaky; velocity errors propagate into every metric | Mine-dewatering inflow records from Jaduguda/Narwapahar (UCIL has decades of them) → back-out deep-zone K; add a depth-decay factor |
| 3.4 | **Fracture parameters ungrounded locally** (β 2–20, aperture 100–500 µm, De, ω all generic literature) | The entire fractured-transport overlay rests on them | Packer tests / tracer tests in the belt, or published SSZ hydro studies; even one local tracer test would anchor β |
| 3.5 | **Attenuation k Wyoming-borrowed** despite different (sulfide-rich, depth-variable) mineralogy; no lithology/depth dependence of k | The equilibrium plume extent x* ∝ 1/k — first-order sensitive | Batch/column reduction tests on SSZ rock; NRC post-restoration stability curves as bounding data; tie k to belt vs non-belt lithology |
| 3.6 | **Data seams**: hard steps at CGWB polygon edges and the binary deposit/belt/shear-zone switches (both engines, verified on the transect) | A pin moved 1 km across a map line can jump ~2× in plume size — users will notice and distrust | Geostatistical K surface (krige NAQUIM + polygon data) instead of polygon lookup; distance-tapered deposit halo instead of binary |
| 3.7 | **No monsoon transients** (recharge pulses, seasonal flow reversal near divides, water-table swing in the vertical module) | Jharkhand's defining hydrologic feature is represented only as band width | Two-season alternating gradient in `front_position` (cheap); full transient needs a numeric solver |
| 3.8 | **No co-contaminants**: SSZ ore carries Cu, Ni, Co, Mo, As — an oxidizing alkaline leach would mobilize them (and pyrite oxidation adds acid + sulfate we may understate) | Real regulatory concern for this specific ore type; we model only U/SO₄/TDS | Add As (and Ni) as species with literature Kd — the species architecture already supports it; sulfate source term deserves a sulfide-oxidation bump |
| 3.9 | **No radiometric daughters** (Ra-226, Rn-222) | Standard ISR licensing metrics; absent entirely | Ra with high Kd + decay is straightforward in the existing species framework |
| 3.10 | **Zero field validation** — no Jharkhand ISR exists or will exist to calibrate against | The uncertainty bands quantify *parameter* uncertainty, not *structural* model error | Permanent limitation; the only honest mitigations are the disclaimer + drift monitor + this document |

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
