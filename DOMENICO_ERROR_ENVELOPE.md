# Domenico Error Envelope — measured against an exact reference

**Date:** 2026-08-05 · **Deliverable for `review2.md` finding V-1**
**Reference:** `ml_pipeline/physics/exact_reference.py` · **Sweep:** `ml_pipeline/validation/domenico_error_sweep.py`
**Raw output:** `ml_pipeline/outputs/domenico_error_sweep.csv`, `domenico_error_summary.json`

## Headline

**The hypothesis that prompted this benchmark was wrong, and the benchmark proves it.**

`review2.md` V-1 argued the Domenico product approximation might be corrupting results by up to 80%,
citing West, Kueper & Ungs (2007). Measured over 240 parameter sets drawn from the model's own
training distribution, **the product approximation contributes ±0.1% on the centreline and 0.000%
off it.** It is, for this model's parameter box, effectively exact.

There *is* a systematic error of 17–42%, but it comes from a different approximation — the **dropped
second Ogata–Banks term** — and it biases every concentration **low**.

## Method

The exact solution is the convolution of the 1-D first-passage density with transverse spreading at
the same arrival time:

```
g(x,τ) = x/√(4πD_L τ³) · exp(−(x−vτ)²/(4D_L τ))          inverse-Gaussian first-passage density
T(y,τ) = ½[erf((y+W/2)/(2√(D_T τ))) − erf((y−W/2)/(2√(D_T τ)))]

EXACT     C = C0 · ∫₀ᵗ g(x,τ)·T(y,τ) dτ
DOMENICO  C = C0 · [∫₀ᵗ g(x,τ) dτ] · T(y, x/v)      ← T pulled out, frozen at mean arrival
```

**Self-validation gate.** As W → ∞ the transverse factor is 1, so the convolution must collapse onto
Ogata–Banks. It does, to **1.1e-16** — machine precision. The sweep refuses to run if this fails, so
no error figure is reported from an unvalidated reference.

Parameters were **sampled from `synthetic_training.csv`**, not from a synthetic grid — Domenico's
error is parameter-dependent, so it must be measured where the model actually operates.

## Results

### Centreline concentration, (Domenico − exact)/exact — negative = under-predicts

| position | p5 | p25 | p50 | p75 | p95 | worst |
|---|---|---|---|---|---|---|
| x = 0.5·Xc | −39.8% | −31.2% | **−16.9%** | −4.7% | −0.0% | 41.7% |
| x = 0.8·Xc | −40.2% | −32.4% | **−20.3%** | −9.6% | −0.8% | 41.9% |
| x = 1.0·Xc | −40.4% | −33.1% | **−22.4%** | −13.2% | −5.3% | 42.1% |
| x = 1.2·Xc | −40.6% | −33.8% | **−24.3%** | −17.0% | −11.3% | 42.2% |

### The same, with the product decoupling isolated (full Ogata–Banks retained)

| position | p5 | p25 | p50 | p75 | p95 |
|---|---|---|---|---|---|
| x = 0.5·Xc | −0.00% | −0.00% | +0.00% | +0.00% | +0.00% |
| x = 1.0·Xc | −0.02% | −0.00% | +0.00% | +0.00% | +0.00% |
| x = 1.2·Xc | −0.10% | −0.00% | +0.00% | +0.00% | +0.00% |

**The entire error is the dropped term.** Restore it and the product form reproduces the exact
convolution to 5+ decimal places, on and off the centreline (checked at y = 0, 0.5, 0.9, 1.0,
1.5 × W/2: all 0.000%).

### Why West et al. report 80% and this model sees 0%

Their error grows with transverse spreading relative to source width. This model runs
**α_T/α_L = 0.01–0.10** with sources **147–763 m wide**, so T(0,τ) is flat across the arrival-time
spread and pulling it out of the integral costs nothing. Their result is correct; it applies to a
parameter regime this tool does not occupy. Citing it as a threat here was wrong.

### Down-gradient reach — the served migration metric

| | p5 | p25 | p50 | p75 | p95 | min | max |
|---|---|---|---|---|---|---|---|
| all | −5.8% | −4.8% | **−3.6%** | −1.8% | −0.4% | −6.5% | −0.3% |
| fractured | | | −4.5% | | −0.8% | | |
| porous | | | −2.9% | | −0.4% | | |

**The migration metric is sound to within ~6%.** A 20–40% concentration error becomes a few percent
in distance because the profile is steep where it crosses the exceedance threshold.

## What this means for the tool

| metric | verdict |
|---|---|
| `max_migration_distance_m` | **Sound** — max 6.5% low |
| `affected_area_ha` | Sound via the same argument (threshold-crossing driven) |
| `compliance_conc`, `peak_conc` | **Biased LOW by 17–42%** (23.6% at the 100 m ring in a sampled case) |
| `breaches_at_compliance`, `excursion_probability` | **Biased LOW** — they threshold a low-biased concentration |

The direction matters: the tool **under-states** contamination concentration and breach likelihood.
That is the opposite of the conservative-screening posture it claims.

## Recommendation — a one-line fix, with the evidence already in hand

Restore the second Ogata–Banks term in `_long_factor` (and mirror it into `_stack_field` and the
deficit wave):

```
½erfc[(x−Xc)/(2√(aL·Xc))]  +  ½exp(x/aL)·erfc[(x+Xc)/(2√(aL·Xc))]
```

(using vt = Xc, D_L·t = aL·Xc, so v/D_L = 1/aL). Needs an overflow guard: `exp(x/aL)` overflows
before `erfc` underflows and `inf·0` is NaN.

**Expected impact.** Concentration metrics become exact rather than 17–42% low. Migration moves ~3%.
Upstream behaviour is unchanged — `exp(x/aL) → 0` for x < 0, so the documented artifact box is
untouched. It also removes a discontinuity at the source plane: the full solution gives exactly
F_long(0) = 1, where the truncation gives less.

**Not applied here.** It changes every training label and needs its own re-bake, retrain and pilot
gate; and it recalibrates one peak-concentration test threshold. It should be a scoped change, not
an end-of-audit patch. The implementation was prototyped and verified against this benchmark before
being reverted, so the work is a re-apply rather than a redesign.

## Two defects found while building this

**1. Test-suite config-state pollution (fixed — `ml_pipeline/tests/conftest.py`).**
`test_physics_laws.py` toggled `P.E1_ENABLED` and reset it to a hard-coded `False` in `finally`
— under a comment reading *"never leak the flag to other tests"* — while the production default is
`True`. Every test running afterwards validated geometry the tool never serves, with the leach-zone
disc switched off. It surfaced as order-dependence: `test_spatial_seams` passed alone and failed in
the suite. An autouse fixture now snapshots and restores every config tunable around each test.

**2. `affected_area_ha` no longer measures transport (found once the leak was fixed).**
With the disc restored, two tests failed that had been passing on non-production geometry. Both
assert that area responds to transport, and it no longer does: **area is 76–97% leach-zone disc.**

- The D5 shear zone genuinely produces a **3.2× larger plume** (migration 86.9 m vs 27.3 m) exactly
  as `JHARKHAND_FIDELITY_MATRIX.md` claims — but a **smaller area**, because a thicker aquifer means
  more swept volume, fewer bulk volumes, and less tanh source widening.
- Restoration cleans concentration, not footprint, so area barely moves while peak concentration
  falls properly.

Both tests were measuring the wellfield footprint and calling it transport. Corrected to assert on
migration and peak concentration, with `test_area_is_dominated_by_the_leach_disc_and_this_is_visible`
added to pin the property so it reads as documented behaviour rather than a latent surprise.

**This is a consequence of the earlier remediation** (restricting the plume mask to x > 0 left the
disc dominant), and the state leak is what hid it. It is defensible — when nothing migrates, the
contaminated ground *is* the wellfield — but "Total Vulnerable Area" should be understood as
*wellfield footprint plus a small migrating increment*, not as a transport metric.

## Limits

- The reference is a 2-D depth-integrated convolution, matching the production engine's plan-view
  formulation. A full 3-D benchmark would additionally test vertical spreading, which this engine
  does not model in the horizontal solve.
- Matrix diffusion (Tang), the disc, attenuation and the deficit wave are excluded by design — this
  isolates the transport kernel. Their own correctness is not addressed here.
- 240 parameter sets; the error is smooth in the parameters, but the tails are sampled, not bounded.
