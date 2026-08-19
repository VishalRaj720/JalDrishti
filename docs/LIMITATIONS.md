# What this system does not know

**One register, kept current.** Everything JalDrishti is uncertain about, blocked on, or
deliberately assuming — physics, data and product. If a number in this product is weaker
than it looks, it is written down here.

The rule this file exists to enforce: *if a model misses a threshold, report it rather
than moving the threshold.* Nothing below has been softened to make the project look
finished.

**Last consolidated:** 2026-08-19. Sources: the ML pipeline readiness review (2026-08-12)
and the R10 audit (2026-08-19). The full chronological review record — including findings
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
| **Per-species R²(log) ≥ 0.60 — radium migration (0.516), compliance (0.431)** | 🔴 **Fails the project's own Gate-4 bar** | Not a tuning failure, a label-shape property. Radium's migration label is **81.8 % exact zeros**, compliance **95.8 % pinned at the 23 mBq/L background**. A squared-error regressor on `log1p` cannot fit a point mass, and R² divides by a near-zero SST. Both *improved* over the previous model (0.475→0.516, 0.403→0.431). The remedy is a **zero-inflated / two-stage head** — a new ML approach, not yet authorised |

**Why this does not invalidate the product:** the analytical engine serves the
authoritative central value for radium, and the conformal bands on those cells cover
0.891–0.986 field-resampled — all above the 0.80 gate. The product shows both, and labels
which engine produced which. **If you consider that gate binding for release, the
pipeline is not ready** until the two-stage head is built.

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

- **CGWB chemistry has no temporal replicates.** 397 wells, **one sample each, one year,
  zero repeats.** This is what blocks NUREG-1569's preferred statistical UCL rules.
  Substituting regional *spatial* spread was tested and **rejected**: sd(TDS) = 286.5
  gives a UCL of 1,965 mg/L, near the BIS limit itself.
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
| O-3 | `react-router-dom` 6.28 — two moderate advisories; the SSR one does not apply. Fix crosses a major version | Open, deployment decision |
| O-4 | Demo accounts with weak public passwords are listed on the login screen | Open — see `DEPLOYMENT.md` §5 |
| O-5 | `/metrics` is unauthenticated | Open — restrict at the gateway |
| O-8 | PDF export is wired but **pagination has never been visually confirmed** — the test harness cannot open a generated PDF | Open, verify by hand |
| O-9 | **Sessions expire in 15 minutes with no refresh path.** `.env` sets `ACCESS_TOKEN_EXPIRE_MINUTES=15`, code defaults to 480, and no `/auth/refresh` exists — a 401 clears the token | Open, deployment decision |

---

## 5. The claims this project should not make

Written down because they are the ones most likely to be overstated in a report or a
presentation:

- **Not "real-time".** There is no sensor ingest, no telemetry, no closed loop. The
  proposal's CPS framing is not satisfied by what exists; this is a screening and
  preparedness tool over historical CGWB data.
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
