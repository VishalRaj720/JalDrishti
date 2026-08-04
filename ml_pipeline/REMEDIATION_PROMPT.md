# Remediation Brief — closing the 62 → 78 gap in `ml_pipeline/`

**Source of truth:** `review.md` (repo root, commit `bd5d791`). Read it before starting.
**Environment:** Windows / PowerShell, repo root `C:\Users\letsm\OneDrive\Desktop\JalDrishti`, interpreter `myvenv/Scripts/python.exe`.
**Baseline to preserve:** 198 tests passing.

You are the Lead Architect and Hydrogeologist. Execute the phases **in the order given**. Each phase has
an explicit **acceptance gate** with numeric, runnable criteria. **Do not start a phase until the previous
phase's gate passes.** If a gate fails, stop and report rather than proceeding.

---

## 0. Corrections to the earlier draft plan (read first)

The previous version of this plan contained factual errors about the codebase. They are corrected below;
do not follow the old instructions where they conflict.

| Old instruction | Why it is wrong | Correct instruction |
|:---|:---|:---|
| "Fix `max_migration_distance_m` in `plume_metrics`" | There are **two** implementations of this metric. `mc_field_metrics` ([transport.py:883](physics/transport.py:883)) computes the identical radial max for the Monte-Carlo path — **and the MC path is what produces the ML training labels.** Fixing only `plume_metrics` leaves the artifact in every trained band. | Fix **both** `plume_metrics` (transport.py:610-616) and `mc_field_metrics` (transport.py:882-883). `test_physics_laws.py:429` pins them equal and will fail if you fix one — treat that failure as the guard working, not as a test to relax. |
| "`dashboard/predict.py`" | No such file. | `ml/predict.py` — `_restoration_residual()` at line 54, consumed at line 80. |
| "Update `_draw_params` in `physics/transport.py`" | `_draw_params` lives in `synthetic/generate.py:253`. | Physics changes land in **three** mirrored sites: `transport.params_from_features` (:637), `generate._draw_params` (:253), and `feature_engineering.build_feature_row` (:169). All three must agree or train ≠ serve. |
| "Pass sampled aperture into `matrix_sigma` in generate.py **and live serve paths**" | The live serve path is **deterministic** — there is nothing to sample there. | Sample aperture in the **MC only** (`mc_draws` + `_draw_params`), so it widens the P10–P90 bands. The deterministic serve path keeps the central aperture. This is precisely the "parameter uncertainty reaches the bands" mechanism the fidelity matrix claims. |
| "Re-run `python synthetic/generate.py`" | Wrong invocation; the package must be run as a module from the repo root. | `myvenv/Scripts/python.exe -m ml_pipeline.synthetic.generate --scenarios 900 --mc 48` |
| "Retrain XGBoost against the new `mc_field_metrics`" | `mc_field_metrics` is a physics function, not a training target. | Retrain against the re-baked `outputs/synthetic_training.csv` via `myvenv/Scripts/python.exe -m ml_pipeline.ml.train`. |
| "+10 Physics, +5 Arch, +6 ML, +4 Frontend = the 16-point gap" | Those are **sub-score** deltas, not absolute-score deltas; they do not sum to the overall gap. | The overall 62 → 78 target is driven mainly by Findings #1 and #2 (Phase 1). Phases 5–7 protect the gain; they do not independently produce it. |

**Also missing from the old plan and required here:** a baseline snapshot (Phase 0), a pilot-bake diff gate
before the expensive full bake (Phase 3), the feature-vector design decision (D1 below), and documentation
corrections beyond `ARCHITECTURE.md` §6 (Phase 7).

---

## Decision gate D1 — resolve BEFORE writing any Phase 1.2 code

Making fractured retardation species-dependent means the physics uses an effective capacity ratio
**β_eff = β · R_m** (Goltz–Roberts: the immobile zone stores dissolved *and* sorbed mass; `R_m` is already
computed inside `matrix_sigma`, [transport.py:179](physics/transport.py:179)). The question is whether the
**model feature vector** changes with it.

- **Option A (RECOMMENDED — adopt unless you have a reason not to).** β_eff is used inside the physics only.
  `dual_porosity_beta` and `retardation_Rd` keep their current definitions (raw β, 1+β).
  *Why:* `Xc_m` is already a `MODEL_FEATURE` and is recomputed by the corrected `front_position` at both
  train and serve time — so the corrected kinematics reach the surrogate through it. Feature count stays 40,
  the model card, `MONOTONE_MAPS`, and the `hydro_support` OOD box are untouched. Blast radius: physics + labels only.
- **Option B.** Redefine `retardation_Rd = 1 + β_eff`. More physically descriptive and gives the
  `retardation_Rd: -1` monotone constraint real meaning — but the fractured `hydro_support` box for
  `retardation_Rd` widens from ~[3, 21] to ~[3, 10⁶], and `envelope_violations` uses a ±2 % *span* tolerance
  ([resolve.py:127-130](dashboard/resolve.py:127)), so the out-of-distribution guard on Rd goes vacuous.
  If you choose B, you must also switch that support check to log space.

Record the decision in the Phase 1 commit message. Everything below assumes **Option A**.

---

## Phase 0 — Baseline capture (do not skip)

You are about to change physics that moves the headline numbers by an order of magnitude. Without a
before/after record you cannot tell a correct fix from a regression.

1. Branch: `git checkout -b fix/audit-remediation` (main is 4 commits ahead of origin; leave it clean).
2. Write `ml_pipeline/tests/baseline_snapshot.py` (a script, not a test) that, for the pin set below ×
   all 4 species × `time_years ∈ {2, 10, 20}`, records `area_ha`, `migration_m`, `max_downgradient_m`,
   `Xc_m`, `compliance_conc`, `excursion_probability` from `predict_analytical`, plus the ML P10/P50/P90.
   Dump to `ml_pipeline/outputs/baseline_pre_remediation.json`.
   Pins: Jaduguda (86.347, 22.652) · mid-belt (86.25, 22.63) · Ranchi non-ore (85.33, 23.36) ·
   Dhanbad (86.43, 23.80) · the belt-edge pair (86.347, 22.6939) and (86.347, 22.6948).
3. Record `git rev-parse HEAD`, the current `metrics.json`, and `model_card.json` alongside it.

**Gate 0:** `baseline_pre_remediation.json` exists and contains Jaduguda uranium `migration_m ≈ 422.8`,
`max_downgradient_m ≈ 35.9`. If it does not, your harness is wrong — fix it before touching physics.

---

## Phase 1 — Core physics (Findings #1, #2, #4). Label-affecting.

### 1.1 Re-base the migration metric — **both** implementations

- `plume_metrics` ([transport.py:610-616](physics/transport.py:610)): restrict the radial max to
  down-gradient cells. Compute the mask as `mask & (X > 0)` for `max_dist`, or replace
  `max_migration_distance_m` with the `X > 0` radial max. `max_downgradient_m` already exists and is correct —
  keep it. `plume_halfwidth_m` should also be computed on the down-gradient mask (it currently inherits the
  upstream box's transverse extent).
- `mc_field_metrics` ([transport.py:882-883](physics/transport.py:882)): apply the identical restriction to
  `dist[bucket]`. **This is the one that produces training labels.**
- **Area decision:** the upstream artifact box is currently counted in `affected_area_ha`. The E1 disc
  ([E1_geometry_design.md](E1_geometry_design.md) §1) is the *intended* representation of the contaminated
  source footprint. Keep the disc, and restrict the *plume* mask contribution to `X > 0` so the box is not
  double-counting the disc region. Document the choice in the docstring — the disc is the physical claim,
  the box is a solution artifact.

### 1.2 Species-dependent fractured retardation (Option A)

Apply β_eff = β · R_m consistently at all three mirrored sites. Use the same `R_m` expression already in
`matrix_sigma` (do not re-derive it — factor it into a shared helper so the two cannot drift):

- `transport.params_from_features` ([:648-655](physics/transport.py:648)): `beta_k` for the fractured branch.
- `generate._draw_params` ([:276-284](synthetic/generate.py:276)): `beta_k`, **and** the local
  `v_c = v_base / (1 + beta_k)` used for `atten_per_m` ([:313](synthetic/generate.py:313)) — otherwise
  attenuation and kinematics disagree.
- `feature_engineering.build_feature_row` ([:207-220](data_prep/feature_engineering.py:207)): the `beta_k`
  passed to `front_position` for `_Xc_eval_m` and `_Xc_clean_m`. Under Option A the returned
  `dual_porosity_beta` / `retardation_Rd` fields are **unchanged**.

Guard `retarded_clock` numerically for large β: with β ~ 3.6×10⁵ and ω = 1e-3 the closed form is stable
(verified by hand: `I(3650 d) ≈ 0.046 d`), but add an assertion that it returns a finite non-negative value.

**Known residual limitation — document it in the docstring, do not silently ignore it:** ω is held fixed at
1e-3/day while β_eff scales with sorption. Physically the first-order transfer rate should also fall as
matrix retardation rises, so β_eff alone is a partial correction. Record this in the fidelity matrix (Phase 7).

### 1.3 Radium restoration residual (Finding #3)

`ml/predict.py:80` currently falls through to `1.0` because `texas_restoration_residual()` has no radium key.
Route it through a single helper that overlays `P.RADIUM_RESTORATION_RESIDUAL` (0.99), mirroring
[generate.py:165-168](synthetic/generate.py:165).

**Note:** this fix *aligns serve to existing training* — training already sampled 0.99 × noise. It therefore
requires **no re-bake on its own** and could ship as an independent hotfix if you want value before Phase 4.

### 1.4 Propagate fracture-kernel uncertainty (Finding #4)

- Add a draw key `u_aperture` to `mc_draws` ([generate.py:227](synthetic/generate.py:227)) — same
  common-random-number discipline as the existing keys.
- In `_draw_params`, sample the aperture from `P.FRACTURE["full_aperture_m"]` (lo, central, hi) using the
  existing `_triangular` helper, and pass `half_aperture_m = aperture/2` into `matrix_sigma`.
- Leave `De_m2_day` at its central value **unless** you add a defensible range to `P.FRACTURE` first; do not
  invent one. If you leave it fixed, say so in the fidelity matrix rather than implying full propagation.
- The deterministic serve path keeps the central aperture — no change to `params_from_features`.

### Gate 1 (run before Phase 2)

```bash
myvenv/Scripts/python.exe -m pytest ml_pipeline/tests/ -q
```

Numeric criteria, all verified by re-running the Phase 0 snapshot script:

1. **Jaduguda uranium** `migration_m` falls from 422.8 m to within ±25 % of its `max_downgradient_m`.
2. **Ra-226 fractured at Jaduguda**: `Xc_m < 0.1 m` and `migration_m` at least 20× smaller than uranium's.
   (This is the check the current suite cannot make — see Gate 1 test additions.)
3. **TDS invariance anchor:** TDS has `Kd = 0` → `R_m = 1` → β_eff ≡ β. TDS front position must be
   **bit-identical** to the Phase 0 baseline. If TDS moved, β_eff is wired wrong.
4. `predict.py` and `generate.py` return identical restoration residuals for all four species.
5. Fractured `Xc` is **non-increasing** in Kd across `Kd ∈ {0, 1, 10, 100, 500, 2000}`.

New tests to add (in `tests/test_physics_laws.py` unless noted):

- `test_fractured_front_is_non_increasing_in_kd` — criterion 5.
- `test_tds_front_unchanged_by_beta_eff` — criterion 3, with the baseline value pinned as a literal.
- `test_migration_is_downgradient_only` — assert the argmax cell has `X > 0` at a contained/radial pin
  (this is the test whose absence let Finding #1 survive; `test_complete_capture_branch` deliberately
  asserted on `max_downgradient_m` and stepped around it).
- **Generalize `test_phase1_fixes.py:295`** (`test_radium_sorbs_far_more_strongly_than_alkaline_uranium`) —
  it currently forces `regime="porous"`, which is the regime **no deposit pin uses**. Parametrize it over
  both regimes. This is the cherry-pick that made fidelity row 3.9 look verified.
- `test_restoration_residual_train_serve_parity` (in `test_phase1_fixes.py`) — criterion 4.

---

## Phase 2 — Single source of truth (Finding #9). Label-affecting via 1.3, so it must precede the bake.

Create one registry in `config/parameters.py` covering: the `SPECIES` tuple, per-species background
defaults, thresholds, units, and restoration residuals (including the radium overlay from 1.3).

Update importers: `ml/dataset.py:39-41`, `ml/predict.py:50-51`, `dashboard/resolve.py:32-35`,
`synthetic/generate.py:72`, `synthetic/generate.py:189-194` (the `Cb` literals duplicate
`resolve._BG_DEFAULT`). **Delete `resolve.ML_SPECIES` ([resolve.py:33](dashboard/resolve.py:33))** — it has
zero importers; the server correctly imports `predict.ML_SPECIES`.

Extend the existing guard `test_phase1_fixes.py:356` so it asserts **every** module's view of the species
list matches the model card, not just `predict.ML_SPECIES`.

**Gate 2:** full suite green; `grep -rn "ML_SPECIES\|_BG_DEFAULT" ml_pipeline --include=*.py` shows exactly
one definition site each.

---

## Phase 3 — Pilot bake and label diff (mandatory gate before the full bake)

This is the discipline `E1_geometry_design.md` §6 already mandates for label-changing work
("PILOT 100 scenarios first; diff every label distribution vs v2"). Phase 1 changes labels far more than E1 did.

1. `myvenv/Scripts/python.exe -m ml_pipeline.synthetic.generate --scenarios 100 --mc 48 --out ml_pipeline/outputs/pilot_new.csv`
2. Diff every label distribution against the current `outputs/synthetic_training.csv` (subsample to matching
   scenarios or compare distributions): per species × regime, report median and P90 shifts in
   `affected_area_ha_p50`, `max_migration_distance_m_p50`, `compliance_conc_p50`, `excursion_probability`.
3. Sanity checks: band-order violations = 0; censor (`off_scale`) rate not materially above baseline;
   breach base rate still in the 30–60 % range flagged in the E1 doc.

**Gate 3 — human review, not automated.** Expect large, *directional* shifts: fractured migration collapses,
fractured area becomes disc-dominated, TDS essentially unchanged, porous largely unchanged. If porous or TDS
moved materially, you have a bug — stop. If uranium fractured migration collapses to near zero at *every* pin,
reconsider whether β_eff should be damped (add a documented `BETA_SORPTION_STRENGTH` exponent in config, the
same pattern as `K_DEPTH_DECAY_STRENGTH`) rather than shipping a tool that reports "contained" everywhere.
Record the reviewed decision before proceeding.

---

## Phase 4 — Full re-bake and retrain

1. `myvenv/Scripts/python.exe -m ml_pipeline.synthetic.generate --scenarios 900 --mc 48`
2. `myvenv/Scripts/python.exe -m ml_pipeline.ml.train`

**Gate 4:**
- Mondrian scenario-level coverage **≥ 0.80** for all three band targets (current: 0.881 / 0.881 / 0.856).
  If coverage fails, adjust `DELTA_INFLATE` ([train.py:57](ml/train.py:57)) and record why — as was done at
  1.15 → 1.35 — rather than lowering the gate.
- `monotonicity_on_manifold`: both `qin_law_holds` and `bleed_law_holds` true.
- Per-species `r2_log_by_species` ≥ 0.60 for every species × target. Report the pooled R² too, but judge on
  the log/per-species figures — the pooled number mixes ppb, mg/L and mBq/L (see [train.py:110-132](ml/train.py:110)).
- Full suite green against the new artifacts.
- Reset the drift monitor after deploying (`POST /api/drift/reset`) — the pre-change baseline is meaningless
  against new artifacts; same atomic-cutover discipline as E1 Stage H.

---

## Phase 5 — Serve-side spatial seams (Findings #5, #6). No retrain required.

Deliberately after the retrain: these are serve-time corrections that do not touch labels, so they must not
be entangled with the bake.

1. **District λ steps ([resolve.py:331-358](dashboard/resolve.py:331)).** The per-district NAQUIM
   `fracture_max_m` steps at district borders (measured: K 0.147 → 0.256, 1.74× over ~130 m). Blend
   `fracture_max_m` (or the resulting decay factor) across district boundaries using the same inverse-distance
   weighting `jharkhand_loader._blend_K_at_boundary` uses for K. Note the ordering: the K blend runs *before*
   depth decay and is unaware of λ — the blend must be applied to λ itself, not re-applied to K.
2. **Belt-edge compound step ([resolve.py:314-321](dashboard/resolve.py:314)).** K (2.2×), thickness (4×),
   C0 and the attenuation mode all flip at the constructed hull+buffer line. Taper the D5 shear-zone K and
   thickness over `P.ORE_TAPER_KM` using the same ramp shape as `_belt_c0` ([resolve.py:134-167](dashboard/resolve.py:134)),
   composing with the polygon-K blend rather than replacing it. Keep the C0 belt→none step as-is — that one is
   deliberate and documented ("the tool cannot invent contamination"), but update its justification comment,
   which currently describes the CSV geological envelope rather than the post-`61b1260` constructed hull.

**Gate 5:** re-run the two transects from `review.md` §2. Max adjacent-pin |log K| step along the
Ranchi→Jaduguda transect < 0.3 (ratio < 1.35×, down from 1.74×); sulfate area step across the belt edge
< 10 % (down from +37 %). Add a regression test pinning both.

---

## Phase 6 — Frontend (Finding #1 user-facing half)

- `renderMetrics` ([app.js:697](../frontend/ml_pipeline/app.js:697)): the "Max Migration Distance" card now
  receives the corrected metric — verify it reads sensibly at radial pins.
- Fix the Λ<1 note ([app.js:730-734](../frontend/ml_pipeline/app.js:730)): it currently claims the number is
  "source-zone extent, not travel", which was wrong even as a mitigation (the disc radius is ~207 m, the
  reported number was 423 m). Restate it as down-gradient travel with the disc footprint reported separately.
- Confirm `ml_envelope_ellipses` ([plume_geometry.py:114](dashboard/plume_geometry.py:114)) still renders
  sensibly — it uses `migration_m` as the ellipse semi-major axis, so collapsed migration will shrink the
  envelopes substantially. This is correct, but check it does not degenerate to invisible.

**Gate 6:** start the server (`myvenv/Scripts/python.exe -m ml_pipeline.dashboard.server`), load
`http://127.0.0.1:8077`, confirm the default Jaduguda view renders with the corrected migration number, the
corrected Λ note, and a visible ML envelope. **Stop the server afterwards.**

---

## Phase 7 — Documentation truth-up (Finding #7 and the §8 over-claims)

Correct **all** of these, not only `ARCHITECTURE.md` §6:

- `ARCHITECTURE.md` §6.2 (feature count 39 → 40), §6.5 (stale R²/coverage → regenerate from the new
  `metrics.json`), §9 (test count → actual). Prefer generating this section from the artifacts so it cannot
  go stale again.
- `ARCHITECTURE.md` §4.8 — the claim *"migration and compliance metrics track the migrating front, never the
  source footprint"* was false before this work; after Phase 1 it becomes true. State when it became true.
- `ARCHITECTURE.md` §10 — add the residual limitations this work creates: fixed ω under scaled β_eff (1.2),
  and `De` still unsampled if you left it fixed (1.4).
- `QA_SWEEP_REPORT.md` "surprising-but-correct" item #3 — append a correction: the 422.8 m Jaduguda migration
  was a grid-margin artifact, not Tang-envelope physics; the Tang factor decays below the exceedance level
  within ~1.4 m at those inputs.
- `JHARKHAND_FIDELITY_MATRIX.md` — row **3.6** ("K is provably continuous across every boundary") must be
  narrowed to what is now true after Phase 5; row **3.9** must record that the "essentially immobile"
  verification was porous-only and is now demonstrated in the fractured regime as served; row **3.4** should
  record that aperture uncertainty now reaches the bands (and that `De` does or does not).
- `review.md` — leave it untouched. It is the audit record of the pre-fix state.

**Gate 7:** every number quoted in `ARCHITECTURE.md` §6 matches `ml/artifacts/metrics.json` and
`model_card.json` verbatim.

---

## Final verification

1. Full suite green: `myvenv/Scripts/python.exe -m pytest ml_pipeline/tests/ -q`
2. Re-run the Phase 0 snapshot into `outputs/baseline_post_remediation.json`; produce a short
   before/after table for the six pins. This is the evidence that the gap closed.
3. Confirm every `review.md` §2 finding has either a passing regression test or an explicit, recorded
   decision not to fix.
4. Commit per phase (bisectable), then squash-or-merge as you prefer. Suggested messages:
   `fix(ml_pipeline): migration metric measured down-gradient only, both engines` ·
   `fix(ml_pipeline): fractured retardation scales with matrix sorption (Ra-226 immobile)` ·
   `fix(ml_pipeline): radium restoration residual reaches the serve path` ·
   `refactor(ml_pipeline): single species/constant registry` ·
   `feat(ml_pipeline): sample fracture aperture into the uncertainty bands` ·
   `fix(ml_pipeline): taper district-λ and shear-zone K seams` ·
   `docs(ml_pipeline): truth-up architecture, QA report and fidelity matrix`

## Rollback

Every phase is a separate commit on `fix/audit-remediation`. The expensive, hard-to-reverse step is Phase 4
(re-bake + retrain), which overwrites `ml/artifacts/*.joblib`, `metrics.json`, `model_card.json` and
`outputs/synthetic_training.csv`. **Copy the current artifacts directory to
`ml_pipeline/ml/artifacts_pre_remediation/` before running Phase 4** so you can restore the deployed model
without a re-bake. Note that `ml_pipeline/outputs/` is currently gitignored, so the training CSV is **not**
recoverable from git — back it up explicitly.

## Non-goals (do not attempt in this pass)

Discrete fracture network transport; transient monsoon flow; co-contaminants (3.8 — genuinely source-term
blocked); Rn-222; any attempt to calibrate against field data that does not exist (3.10). Adding these is a
separate scope decision, not remediation.
