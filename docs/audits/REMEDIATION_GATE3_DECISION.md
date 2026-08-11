# Gate 3 — pilot bake review and decision

**Date:** 2026-08-05 · **Pilot:** 100 scenarios × 48 MC = 2,000 rows
**Compared against:** the deployed `outputs/synthetic_training.csv` (900 scenarios / 18,000 rows)
**Decision: PROCEED to the full re-bake and retrain.** `BETA_SORPTION_STRENGTH` stays at **1.0**
(no damping). Reasoning below.

## Why the first pilot was rejected

The first pilot failed the gate outright: migration labels had gone degenerate, with **75.3 % of
fractured uranium and 99.1 % of fractured radium rows carrying the single value 0.0**. Diagnosed
across 60 scenarios spanning the generator's envelope:

| | count |
|---|---|
| MC-grid label `== 0` but analytic centreline extent `> 0.05 m` | **29 / 60** |
| MC-grid label `== 0` and genuinely immobile | **0 / 60** |

Not one was actually immobile — the zeros were entirely grid quantisation. The 2-D grid is sized to
contain the source disc, so its cells are 5–13 m wide however short the plume is; survivors were
biased low as well (2.93 m gridded vs 17.7 m analytic). This was a **pre-existing** defect that only
became visible once the migration metric was re-based: against a ~420 m upstream-artifact reading, a
6 m cell rounds to nothing. Fixed by measuring travel analytically on the centreline in both engines
(commit `fbdbda9`); area keeps the gridded value, which is grid-stable (9.06 ha across grid_n 200–6000).

## Second pilot — the numbers the decision rests on

**Degeneracy resolved.** Share of exactly-zero migration labels, deployed → pilot:

| regime | species | before | after |
|---|---|---|---|
| fractured | uranium | 0.000 | **0.149** |
| fractured | sulfate | 0.052 | **0.055** |
| fractured | TDS | 0.039 | **0.043** |
| porous | uranium | 0.000 | **0.000** |
| porous | sulfate | 0.032 | 0.008 |
| porous | TDS | 0.028 | 0.015 |
| fractured / porous | radium | 0.611 / 0.603 | 0.987 / 1.000 |

Radium is the one species where all-zero is the *correct* answer: Kd ≈ 500 L/kg gives a matrix
retardation ~4.4×10⁴, and the resulting immobility independently reproduces the BARC (2008) field
observation that radium does not migrate from the Jaduguda tailings. Fidelity row 3.9 asserted this;
until now the served fractured answer contradicted it.

**The migration bands were previously fake.** Median relative band width `(p90−p10)/p50`:

| regime | species | migration before | migration after |
|---|---|---|---|
| fractured | uranium | 0.000 | **2.441** |
| fractured | sulfate | 0.001 | **1.758** |
| fractured | TDS | 0.001 | **1.299** |
| porous | uranium | 0.000 | **1.842** |
| porous | TDS | 0.121 | 1.764 |

Every Monte-Carlo draw used to land on the same grid artifact, so the P10–P90 migration band had
essentially **zero width** and the Mondrian conformal calibration was calibrating a degenerate
target. The bands now carry genuine parameter uncertainty. This is the single largest honesty gain
in the remediation and was not anticipated in the plan.

**Species now separate** (fractured `Xc` at Jaduguda, t = 10 yr): TDS 13.166 m (bit-identical,
Kd = 0) → sulfate 2.817 → uranium 0.192 → radium 0.000. All four previously read 13.166.

**Sanity gates:** band-order violations 0 (area and migration); NaN/inf 0; censor rate 0.0042 →
0.0025; off-scale fraction 0.0107 → 0.0050.

## Judgements recorded against the plan's stop conditions

**"If porous or TDS moved materially, you have a bug — stop."** Both moved, and it is not a bug. The
migration re-base and the area restriction to x > 0 are **regime-independent by construction**, so
both regimes must move; β_eff is fractured-only. The criterion that actually discriminates is the
TDS *front position*, which is bit-identical everywhere — verified structurally in
`test_tds_front_is_untouched_by_the_sorbing_capacity_ratio` (it recomputes the front the
pre-remediation way and requires equality, rather than trusting a pinned literal) and again in the
pin snapshot. β_eff reaches nothing it should not.

**"If uranium fractured migration collapses to near zero at every pin, reconsider damping β_eff."**
Not damped, on evidence. At Jaduguda the exact Tang kernel gives 1.81 m and the approximate
continuum front gives 0.19 m, so **Tang governs the `max()`**. Before the fix the continuum branch
said 13.17 m and won — i.e. the species-blind *approximation* was over-riding the *exact* solution.
β_eff therefore did not shrink the plume so much as restore the correct ordering of the two branches.
Damping it would re-introduce the defect to make the output look busier.
`BETA_SORPTION_STRENGTH = 1.0`; the knob remains for bisecting label changes.

## Accepted consequences, carried into Gate 4

1. **Breach base rate 0.266 → 0.178**, below `E1_geometry_design.md`'s 0.30–0.60 guidance. That
   guidance was written against the artifact-inflated labels, and the rate was already below it
   before this work. Shorter plumes breach a fixed 100 m ring less often — the expected consequence
   of removing a 420 m phantom. Not treated as a blocker.
2. **Radium migration is a zero-variance target.** R² is mathematically undefined there (SST = 0), so
   the Gate 4 per-species R² criterion must **exempt** it explicitly rather than record a failure.
   A constant target is the correct label, not a modelling deficiency.
3. **Fractured uranium area band collapses** (0.120 → 0.002). Honest: when nothing migrates, the
   affected area *is* the leach-zone disc, whose radius is a deterministic function of features the
   model already has (W, Q_in, thickness). The uncertainty moves to migration and compliance, where
   the bands are now wide. Watch coverage for the `fractured|uranium_ppb` cell after the retrain.
4. **Fractured uranium excursion probability falls** (mean 0.373 → 0.014, std 0.413 → 0.057).
   Physically consistent: at ~900× retardation, reaching a 100 m ring inside the horizon needs a
   fracture-water velocity above ~12 m/day. Note that sulfate and TDS retain meaningful excursion
   probabilities (0.152 / 0.310) — which is how real ISR monitoring actually works, detecting
   excursions with conservative indicators (chloride, conductivity) rather than with uranium.
