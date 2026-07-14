# Pre-Retrain QA Sweep — Findings Report

**Date:** 2026-07-13 · **Scope:** `FABLE5_QA_SWEEP_PROMPT.md` battery (§4A–§4E), executed via the
direct-Python path (`resolve_inputs` → `predict_analytical` / `predict("ml")`) + HTTP serve-wiring
checks against `:8077`. ~1,100 cases across 9 pins (fractured/porous, deposit/belt/non-ore),
3 species, both engines. Purpose: find every defect **before the final retrain**.

---

## Ranked findings

### F-1 · CRITICAL · analytical + generator (baked into training labels)
**Mid-restoration clean-up is never credited to the plume field, and the restoration-completion
boundary `rest = t − op` is a hard step discontinuity — the original snap-back bug is only
partially fixed.**

- **Reproduce (step):** Ranchi pin (85.33, 23.36), sulfate, op=5, t=15, sweep `restoration_years`
  finely across 10.0:
  `rest=9.98 → area 6.584 ha, migration 245.3 m` · `rest=10.00 → area 21.527 ha, migration 446.4 m`
  — a **3.3× area step in a 0.02-yr increment**, then **bit-frozen** (21.527 for all rest ≥ 10).
- **Reproduce (freeze + self-contradiction):** Jaduguda (86.347, 22.652), uranium, op=8, t=10:
  for all `rest ≥ 2` the served field is identical (area 28.482 ha, peak 13,273 = C0) while the
  API's own `restoration` diagnostic reports the source at 33.7% → 11.4% over the same sweep —
  **the field and the diagnostic contradict each other.**
- **Invariant violated:** §4A `restoration_years ↑ ⇒ cleaner, smooth`; §4B-1 no snap/freeze.
- **Root cause (confirmed by cell-level field diff):** the simplified Domenico base term paints the
  **entire upstream half-plane** (the wellfield/source-zone box, X ≤ 0 within the transverse
  envelope — ~15.0 ha on the Ranchi grid) at **full C0**. The clean-water subtraction wave
  (erfc → 1 upstream) is the only thing that wipes that box to C_res, and `transport.py:255` gated
  the wave on `Xc_clean > 0` — which `front_position(v, η=1, …)` keeps at **0 for all
  `t ≤ op + rest`**. So the moment the sweep was still running at eval time, the wave switched off
  and the upstream box **snapped back to C0**: +14.9 ha of area (exactly the observed step) and
  "migration" jumping to the box's far corner (√(408² + 182²) = 447 m — the metric is radial).
  Credit also used the **planned** sweep length (`realized_residual(endpoint, rest_days)`),
  violating causality. The generator (`synthetic/generate.py:262-264`) shares the law → the cliff
  was **in the training labels**; the ML reproduced it (m_area 23.0 → 31.0 across rest 1.75 → 2.0).
- **FIXED (2026-07-13, this session):** new `transport.restoration_source_fraction(ref, t, op,
  rest)` credits only the **elapsed** sweep (`realized_residual(ref, clip(t−op, 0, rest))`), applied
  in all three sites (`params_from_features`, `generate._draw_params`, `feature_engineering`); the
  wave is now active whenever a sweep has credit (`C_res < C0`) with its front clamped to the source
  plane mid-sweep (`max(Xc_clean, 1e-3)` — the wall that keeps the upstream box at C_res), and
  `_stack_field` gets an explicit `rest_active` mask. Verified: the Ranchi step is gone
  (6.584 → 6.578 across the boundary), the freeze is now the **correct causal saturation**
  (elapsed = t−op for any still-running sweep), and 9 new regression tests
  (`tests/test_restoration_continuity.py`) pin the behaviour. Re-baked + retrained.

### F-2 · HIGH · ML serve path + training sampling
**The `residual_fraction` model feature is discontinuous at `rest → 0⁺`, and training has no rows
with `rest ∈ (0, 1)` — the ML bands cliff for short sweeps.**

- **Reproduce:** Jaduguda, uranium, op=8, t=10: `rest=0 → m_migr 558.3 m` ·
  `rest=0.25 → m_migr 302.7 m` (**−46% for a 3-month sweep**) while the analytical moves −1.5%
  (498.0 → 490.6). m_area drops 32.2 → 22.1 (−31%).
- **Root cause:** `ml/predict.py:72` — `residual = Texas-endpoint (≈0.066) if rest_days > 0 else
  1.0`: the feature steps 1.0 → 0.066 for an infinitesimal sweep. The generator
  (`generate.py:152-159`) samples `rest_years ∈ {0} ∪ [1, 10]`, so the (0, 1) gap and the
  endpoint-vs-realized inconsistency were never seen in training.
- **FIXED (2026-07-13, this session):** `build_feature_row` now emits `residual_fraction` = the
  **realized elapsed-sweep fraction** (continuous → 1.0 as rest → 0, and it distinguishes mid-sweep
  states) identically for the generator and the serve path; the raw Texas endpoint is carried as
  `_residual_endpoint` for the physics solver (`predict.py` uses it — feeding the realized value
  back into the drawdown law would double-apply it). Generator now samples sweeps down to 0.25 yr.
  Regression-tested (`test_residual_feature_is_realized_and_continuous`). Re-baked + retrained.

### F-3 · MEDIUM · API response (serve-only)
**The `restoration` diagnostic credits the full planned sweep even when the sweep is still
running.** At Jaduguda op=8, rest=3, t=9 (1 yr into a 3-yr sweep) the response reports
`source_conc_after_restoration = 2596.6` while the served field's peak is 13,273 (= C0, zero
credit). Root cause: `ml/predict.py:197` uses planned `rest_years`, not `min(t − op, rest)`.
- **FIXED (2026-07-13, this session):** the diagnostic now uses the elapsed sweep and adds
  `sweep_elapsed_years` + `sweep_complete`, so it always matches the served field.

### F-4 · LOW · ML fidelity (in-support softness)
- Ranchi sulfate: `m_migr` dips −9% as gradient rises 0.0005 → 0.002 (analytical rises).
- Jaduguda: `m_migr` wiggles −1.7% across downtime 0.2 → 0.3.
Isolated, small, in-support; the monotone constraints don't cover the co-moving derived features
(D_L, peclet). Watch after the final retrain; no action if it shrinks.

### F-5 · LOW · numerics
Analytical `migration_m` zigzags ±0.3% (≈±25 m at ~7 km) as wellfield width sweeps 100→800 at high
gradient — `_auto_grid` resolution quantization. Cosmetic at screening scale.

---

## Surprising-but-correct (verified, do NOT "fix")

1. **`operation_years ↑ ⇒ migration ↓` at fixed t with bleed > 0** (spearman −1.00 everywhere).
   Correct: more operating years = more years with the front held by bleed capture, fewer free-drift
   years. Decisive check: at **bleed=0** the front Xc is bit-identical across op=1..20 and area
   rises with throughput (43.5 → 55.4 ha) — the sign law `op↑⇒footprint↑` only holds without
   containment; `MONOTONE_MAPS` correctly leaves `operation_days` unconstrained.
2. **`Q_in ↑` at fixed bleed% ⇒ flat/smaller plume.** The UI slider moves throughput *and*
   containment together (Q_net = Q_in·bleed%); the trained `+` law is at fixed Q_net. Verified
   correct at bleed=0.
3. **Low-gradient fractured migration is gradient-insensitive** (422.76 m for i=0.0005..0.001 at
   Jaduguda): the conservative Tang early-arrival envelope ≈ 1 out to the water front, so migration
   is transverse-dilution-limited. By design.
4. **λ radial↔directional crossing is smooth** (λ 0.70 → 1.28 across gradient 0.001 → 0.0015; area
   21.1 → 25.7 continuous). No E1 seam.
5. **Restoration saturates at the 0.02 residual floor** (~rest ≥ 30 yr: no further change). Floor is
   the Texas clip; intended.
6. **`extrapolation` flags at rest > 10 / time > 20** (new 50-yr sliders): correct honesty, not
   errors. rest=55/time=55 correctly 422.
7. **Shallow impact = 100% "high" at ≤ 180 m ore depth**: advective breakthrough (1.8–8.9 yr) inside
   the evaluation window ⇒ probability saturates. Ordering with depth/thickness is smooth and
   correct (impact 1.00 → 0.33 over 60 → 600 m; breakthrough 1.8 → 33.8 yr).

## All-clear checklist (no findings)

Guardrails: out-of-state 422s (incl. near-boundary Bihar), slider corners (24 extreme combos — no
crash/NaN/negative), determinism (bit-identical repeats), band ordering p10≤p50≤p90 everywhere,
probabilities in [0,1]. Wiring: u-suppression at non-ore pins (ML bypassed, analytical ~0 area),
ore C0 ordering deposit (13,272) > belt (6,636) > none (5.0 trace), shear-zone K on/off (2.467 auto
→ larger plume; explicit K disables), river crossing at Jamshedpur (Subarnarekha, 311 m³/s +
far-field note), per-district NAQUIM vertical (E. Singhbhum profile, fracture band 20–258 m),
flow/strike azimuth provenance (`flow_field+strike`, divide fallback defined), pin ore-depth
suggestions (Jaduguda 180 / Ranchi None), drift monitor live, ML artifacts healthy.

## Retrain gate

**Do not run the final retrain until F-1 and F-2 land** — both change the training labels/features.
Sequence: fix F-1 (three sites) + F-2 (feature + sampling) + F-3 (diagnostic) → full test suite →
re-bake (`synthetic.generate`) → retrain (`ml.train`) → re-run this battery's B1/E2/E3 sweeps to
confirm the step is gone → then the retrain is credibly final.

**Executed 2026-07-13 (this session):** all three fixes implemented; 107/107 tests pass (98 existing
+ 9 new continuity regressions); serve-level reproductions re-run clean (Ranchi boundary step
6.584 → 6.578; Jaduguda smooth to the causal saturation point; diagnostic consistent with the
field); training data re-baked and the surrogate retrained on the corrected labels/features.
