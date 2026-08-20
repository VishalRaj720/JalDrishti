# What this system does not know

**One register, kept current.** Everything JalDrishti is uncertain about, blocked on, or
deliberately assuming — physics, data and product. If a number in this product is weaker
than it looks, it is written down here.

The rule this file exists to enforce: *if a model misses a threshold, report it rather
than moving the threshold.* Nothing below has been softened to make the project look
finished.

**Last consolidated:** 2026-08-20. Sources: the ML pipeline readiness review (2026-08-12)
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
