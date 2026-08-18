# R10 audit — console, report, restyle, and the state of the objective

**Date:** 2026-08-19
**Scope:** the work in R10, plus the API surface sweep, role audit and objective
audit requested in `NEXT_BUILD_PROMPT.md` §4.

---

## 0. Coverage — what this audit actually covers

The request was a review "code by code, line by line". **This is not that, and
saying otherwise would be the first false statement in a document about not
making false statements.** What follows is what was genuinely examined.

**Read in full this session:**
`pages/Console.tsx`, `pages/CitizenMap.tsx`, `pages/IsrReport.tsx`,
`console/RunResult.tsx`, `console/VerticalPanel.tsx`, `console/LifecycleChart.tsx`,
`map/useRail.ts`, `map/basemaps.ts`, `styles/theme.css`, `styles/layout.css`,
`docs/roles.md`, `scripts/authz_matrix.py` (role list), `scripts/seed.py` (user
seeding), `app/main.py` (RLS startup guard).

**Read in part** (targeted at a specific question):
`api/client.ts` (types), `components/bits.tsx` (`bandOf`/`RiskBand`),
`map/plume.ts` (`drawPlume` contract), `console/mapLayers.ts`,
`api/v1/citizen.py` (the no-data split), `api/v1/lifecycle.py` (returned fields),
`api/v1/preview.py`, `services/simulation_run.py` (`_plume_geometry`),
`data_prep/flow_field.py` (runtime vs build-time DEM).

**Not read:** the majority of `backend/app` — most routers, all repositories,
all schemas, most services and models; most frontend pages (`Overview`,
`Publications`, `Administration`, `FieldData`, `Audit`, `Methods`, `MyArea`,
`PublicView`, `Alerts`, `Login`); the test suites themselves; and
**`ml_pipeline/` in its entirety**, which was off-limits by instruction and was
verified only by running its 332 tests.

**Verification method matters here.** The in-app browser pane could not
composite frames, so **no screenshot was taken and no visual judgement was made
from a rendered image**. React synthetic events *did* fire — unlike previous
sessions — so interactions were driven for real and their results read back from
the DOM. Everything labelled "verified" below means a DOM or computed-style
assertion against the running application, not a look at a picture.

---

## 1. Audit against the objective (`docs/local/My_Proposal.pdf`)

The proposal names six deliverables. Verdicts with evidence:

| # | Deliverable | Verdict | Evidence |
|---|---|---|---|
| 1 | **ML-based predictive models** to forecast groundwater quality trends and assess aquifer vulnerability near uranium ISR sites | **Met** | `ml_pipeline/` — XGBoost P10/P50/P90 quantile heads plus excursion probability, Mondrian split-CQR conformal calibration per regime × species, benchmarked against exact solutions. 332 tests green this session. Served through `/api/v1/ml` and exercised by the Console |
| 2 | **Identification of critical data gaps** and monitoring recommendations | **Partly met** | The *identification* exists and is good: `pages/DataGaps.tsx` is a dedicated screen, `GET /ingest/data-quality-report` backs it, "no data" is enforced as a monitoring gap rather than a clean result throughout, and R10 fixed the staff-side contradiction (§3.1). What is **missing is the recommendation half** — nothing in the product says *where to put the next monitoring well*. Every ingredient is present (well positions, per-block coverage, modelled footprints, the flow field) and no screen composes them into a ranked siting recommendation. This is the largest remaining gap against the proposal |
| 3 | **Prototype decision-support tool** with a user-friendly interface for stakeholders | **Met** | Four-role portal; analysts register sites and run the engine, admins publish, residents read plain language. R10 removed the defect that made the map unusable outside the ore belt, which had been undercutting this deliverable badly |
| 4 | **Visualization dashboard** for monitoring and intuitive interpretation | **Met** | Console (one map, plume/leach zone/compliance ring/ML envelope, 13 layers), citizen map, lifecycle traces, depth schematic, and as of R10 a publication-grade report with a map figure and PDF export |
| 5 | **Scalable framework** adaptable to other mining contexts | **Partly met** | The architecture supports it — the species registry splits `SPECIES`/`ML_SPECIES`/`EXCURSION_ONLY_SPECIES` so indicators can be added without retraining, and the physics is generic ADE transport. But nothing has been *demonstrated* outside uranium ISR in Jharkhand, and the domain adaptation (Texas → Jharkhand) is specific. Claim it as designed-for, not as shown |
| 6 | **Contribution to mine safety using AI/ML and CPS** | **Partly met** | The AI/ML contribution is real and documented. The **CPS (cyber-physical) claim is not**: the proposal describes "real-time monitoring" and a "closed-loop system", and this system has no sensor ingest, no live telemetry and no actuation. It is a screening and preparedness tool over historical CGWB data. The word "real-time" in deliverable 4 is not satisfied and should not be claimed |

**Honest summary: three met, three partly met, none unmet.** The two things a
reviewer is most likely to challenge are the absent monitoring *recommendation*
(deliverable 2) and the "real-time / CPS / closed-loop" framing (deliverables 4
and 6), which the current system does not support.

---

## 2. API surface sweep

**102 endpoints** in the live OpenAPI schema (the brief estimated ~103).

Method: match each route against frontend call sites and backend test files by
its literal path fragments. **This is approximate** — the frontend calls
`/districts` while tests call `/api/v1/districts`, and parameterised routes share
prefixes. Two different matchers (leading-literal vs discriminating-tail) gave
13 and 20 "dead" routes; the intersection below is what both agree on, and the
contested ones were then checked by hand.

### Confirmed dead — no UI, no test

| Route | Note |
|---|---|
| `POST /ingest/aquifers/geojson` | the five bulk-upload endpoints — **and they admit `analyst`** (finding D-2) |
| `POST /ingest/districts/geojson` | " |
| `POST /ingest/subdistricts/geojson` | " |
| `POST /ingest/groundwater-levels/json` | " |
| `POST /ingest/water-quality/csv` | " |
| `GET /ml/drift` | |
| `GET /ml/health` | |
| `GET /monitoring-stations` | |
| `GET /monitoring-stations/count` | |
| `GET|POST /blocks/{id}/monitoring-stations` | full station CRUD, plus `{station_id}` and `/readings` |
| `GET /aquifers`, `GET /aquifers/{id}` | superseded by `/ml/aquifers`, which the Console does use |
| `GET|POST /water-samples`, `/water-samples/bulk` | no UI; **tests do cover these** |
| `GET /metrics` | Prometheus. Unauthenticated — restrict at the gateway |

### Corrections to the brief's assumptions

- **`/scenarios/*` is not entirely dead.** `GET /scenarios` *is* called, from
  `pages/Overview.tsx:192`. The detail, `/run` and `/compare` routes have no UI.
  The "repurpose as saved runs" work remains unbuilt.
- **`/districts/{id}/blocks` is dead** — the brief was right. An early matcher
  reported it as live; that was `/districts` matching the district list call.
- **`/simulations/{sim_id}` (legacy)** cannot be separated from
  `/simulations/{isr_id}` by path matching alone — they are the same shape. Not
  resolved here.

**No route was deleted.** The owner's standing choice — *surface only, delete
nothing* — was respected.

---

## 3. Defects found and fixed in R10

### 3.1 The staff "No data" contradiction (§4.4 of the brief) — **fixed**

The district list read *"East Singhbum · 28 wells · 28 samples · **No data**"*.
`bandOf(max_uranium_ppb)` returned "No data" whenever uranium was null, which
conflates two different gaps: never sampled, and sampled but never analysed for
uranium. `citizen.py` already drew this distinction for residents; the staff
surface did not.

`bandOf` now takes an optional sample count and returns **"Not tested for
uranium"** when samples exist but uranium is null. Both remain the `none` band —
grey and dashed, never green — so no gap can read as a clean result.

**Verified** against the live API: three districts have this shape (East
Singhbum 28/28, Saraikela Kharsawan 11/11, West Singhbhum 16/16). The rail row
now reads *"East Singhbum · 28 wells · 28 samples · Not tested for uranium"*, and
the drawer explains the distinction.

### 3.2 `seed.py` reintroduced the retired `regulator` role — **fixed**

`SEED_USERS` still contained `regulator@jaldrishti.local` with
`UserRole.regulator`. Running `python -m scripts.seed` against a fresh database
therefore **minted a regulator account on every clean install** — reintroducing
the exact role migration `0019` retired and `tests/test_p6_roles.py`
(`test_no_regulator_accounts_remain`) asserts cannot exist. Because the enum
label survives in Postgres permanently, a seeder that mints one is precisely the
risk that test was written to catch.

Moved to `RETIRED_USER_EMAILS`, so a reseed now *removes* the account.

### 3.3 `docs/roles.md` advertised a role nobody can hold — **fixed**

`scripts/authz_matrix.py` still listed `UserRole.regulator` in `ROLE_ORDER`, so
the generated matrix published a reachability figure — *"regulator 12/102"* — for
a retired role, and the hand-written prose above it called `regulator` "**the
primary government user**". That is the strongest possible argument for bringing
the role back, sitting in the authorization document.

Generator corrected, doc regenerated, and the stale prose rewritten: four roles,
the retirement explained, the `require_regulator_or_admin` naming (retained,
admin-only) documented, and the out-of-date `x/54` tallies and resolved D-3 drift
row corrected.

### 3.4 A wrong statement in the new report summary — **found in verification, fixed**

The first draft of the executive summary printed *"The engine declined to produce
a uranium source term here"* whenever `notice` was non-empty. At Jaduguda the
notice is *"Prospective Belt … source term reduced"* and arrives **alongside a
real 8.5 ha result** — so the report stated a refusal directly above a non-zero
footprint. Now gated on `ore_zone.zone === "none"`; any other notice renders as a
qualification. Caught only because the rendered text was read back.

### 3.5 Pointer-capture fragility — hardened

`setPointerCapture` ran before the drag listeners were attached, and it *throws*
if the pointer is not active. The throw left the handle visually dragging with
nothing listening. Now wrapped; capture is an optimisation, not a requirement.

---

## 4. The console defect, root cause confirmed

The reported symptom — *"clicking outside the Singhbhum belt shows district
details instead of resolving hydrogeology"* — had a precise cause, and it was not
the engine.

`districts` is a **default-on layer whose polygons tile the entire state**, and
its click handler called `L.DomEvent.stop`, so the map's own click handler — the
one that drops an ISR pin — never fired anywhere in Jharkhand. Inside the ore
belt the `ore` polygons render on top and do **not** stop propagation, so the
click bubbled to the map and a pin dropped. That is exactly why pins appeared to
work in the belt and nowhere else.

**Verified fixed.** A dispatched click at the map centre lands on
`path.leaflet-interactive` (a district polygon) at 23.60 °N, 85.30 °E — well
outside the belt — and now produces exactly **one** drawer, in ISR pin mode, with
the engine resolving Ramgarh: fractured regime, K = 2.072 m/day, thickness
17.5 m, flow azimuth 19.1°, gradient 0.01223, nearest well 8.8 km.

### The "two columns" report — a second, separate bug

On `CitizenMap.tsx` the cause was different and unambiguous: `screening` and
`sel` were **independent state**, each rendering its own `<aside className="drawer">`
as a flex item. Selecting a published footprint and then a district really did
put two drawers side by side. Now a ternary, so the markup cannot express two.

---

## 5. Open issues, not fixed

| # | Issue | Why not fixed |
|---|---|---|
| **O-1** | **No monitoring-siting recommendation** (proposal deliverable 2) | A genuine feature, not a defect. All inputs exist; needs a design decision about what "recommended" means before it is built |
| **O-2** | **`POST /ingest/*` admits `analyst`** (D-2, long-standing) | Changing who may overwrite reference geography is a decision, not a cleanup. One-line fix: `require_admin` |
| **O-3** | **`react-router-dom` 6.28 advisories** (2 moderate) | Fix crosses a major version. Pre-existing, unrelated to R10 |
| **O-4** | **Demo credentials on the login screen** | Correct for a demo, unacceptable public. Documented in `DEPLOYMENT.md` §5 |
| **O-5** | **`/metrics` unauthenticated** | Restrict at the gateway; documented |
| **O-6** | **`/scenarios/{id}`, `/run`, `/compare` have no UI** | The "saved runs" repurpose is unbuilt. Surfaced, not deleted |
| **O-7** | **`require_regulator_or_admin` still carries the retired name** | Behaviour is correct (admin-only, pinned by `test_reviewing_is_admin_only`); renaming touches many call sites for no behavioural gain. Now documented in `roles.md` |
| **O-8** | **PDF pagination not visually confirmed** | The export path is wired and the light print palette applies, but the harness cannot open a generated PDF. **Untested end-to-end — verify by hand before relying on it** |
| **O-9** | **Sessions die after 15 minutes with no recovery** | Found by being logged out mid-audit. `backend/.env` sets `ACCESS_TOKEN_EXPIRE_MINUTES=15`, while `app/config.py` defaults to `480` ("8h — practical for a single-token prototype"). There is **no `/auth/refresh` endpoint at all**, and `client.ts` handles 401 by calling `clearToken()` and raising *"Session expired — sign in again."* So `JWT_REFRESH_SECRET` and `REFRESH_TOKEN_EXPIRE_DAYS` are unused config, and a user loses their work after 15 idle minutes. A 12-point lifecycle trace takes tens of seconds; a report left open across a meeting is a forced re-login. **Fix before deployment: set `ACCESS_TOKEN_EXPIRE_MINUTES` to the code default of 480, or build the refresh flow the config already anticipates.** Left as a decision rather than changed, because `.env` is the owner's local configuration |

---

## 6. Test and build status

| Check | Result |
|---|---|
| `python -m pytest ml_pipeline/tests -q` | **332 passed** in 146 s — engine untouched |
| `npx tsc --noEmit` | clean |
| `npm run build` | clean; `index.js` 550 KB (163 KB gz), `html2pdf` split into its own 985 KB chunk, dynamically imported |
| `python -m scripts.authz_matrix` | re-run; `docs/roles.md` regenerated |
| `python -m pytest tests -q` (backend) | **203 passed** in 681 s |
| `npm audit` | `html2pdf.js` pinned to **0.14.0**; its transitive `jspdf`/`dompurify` advisories are resolved at that version. Remaining: the two pre-existing `react-router` advisories (O-3) |
