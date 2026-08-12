# JalDrishti — Product Design: Frontend, Backend API & Database

**Version:** 3.0 · **Date:** 2026-08-11 · **Status:** Implementation-ready
**Supersedes:** v2.0 (2026-08-11, review-patched), v1.0 (2026-08-05)
**Programme:** TEXMiN–BIT Sindri Mining CPS CoE · *Smart Water Monitoring: ML and CPS for Safe & Sustainable Mining*

**Two audiences, by name:**

1. **Government officials** — CGWB / SPCB / district administration, who need to know which aquifers
   are vulnerable to an ISR process and what the monitoring network is reporting.
2. **Common users** — residents of Jharkhand mining districts, who need a plain answer to
   *"is the groundwater near me at risk, and who do I tell?"*

Everything below is role-based around those two, plus the technical and field staff who serve them.

---

## 0. What this document decides

The repository contains **three parts that do not talk to each other**: a CRUD backend, a
scientifically validated simulation engine (`ml_pipeline/`), and a static frontend mock. None is a
product an authority can be handed, and — critically — **two of them disagree about the physics**
(§1.3). This document specifies one system: which APIs survive, the database behind them, the screens
each audience uses, and the access control that makes it safe to expose.

**One-line product statement.** *A groundwater-vulnerability portal for Jharkhand: for officials,
where a hypothetical ISR plume would travel, who is downstream, and what the monitoring network
reports; for residents, whether their area is at risk and what that means — with every number carrying
its provenance and uncertainty.*

The word **hypothetical** is load-bearing and appears on every simulation surface. No ISR operation
exists in Jharkhand. This is a screening and preparedness tool, not a permitting instrument.

### 0.1 What changed from v2.0

v2.0 was patched during a review rather than rebuilt against the tree, and carried stale numbers.
Every factual claim in v3.0 was re-verified on 2026-08-11 against the working copy, the deployed
`metrics.json`, and a live `psql` query. Corrections:

| v2.0 said | Verified reality |
|---|---|
| `ml_pipeline`: 260 tests | **307 tests** |
| `backend/`: "PostGIS models, **Celery**, Alembic" | **No Celery, no Redis** — absent from `requirements.txt` and the tree; `app/tasks/` is an empty package |
| 55 legacy + **14** pipeline = 69 endpoints | 55 legacy + **13** pipeline = **68** |
| `monitoring_stations` 398 / readings 9,583 | **415 stations / 8,345 readings** actually seeded — see §1.4 |
| Field-coverage 0.865 / 0.904 / **0.913** | 0.865 / 0.904 / **0.912** |
| — | The database is now **seeded and live**; v2.0 was written against an empty one (§1.4) |
| — | **5 orphan tables** exist in the DB with no ORM model — schema drift v2.0 never noticed (§1.4) |
| — | Documentation reorganised into `docs/`; all references in this document point at the new paths |

Numbers that v2.0 got right and v3.0 retains: the 22 deletable endpoints, radium's R² failures
(0.516 / 0.431), the 12-entry assumption register, and the NUREG excursion design.

---

## 1. Current state — verified assessment

### 1.1 What exists

| Component | State | Verdict |
|---|---|---|
| `ml_pipeline/` | **Production-grade.** 307 tests, exact-solution-benchmarked transport kernel, conformal bands validated on the serving distribution, drift monitor, 12-entry assumption register | **Keep — this is the crown jewel.** Frozen; see [`docs/audits/ML_PIPELINE_READINESS.md`](docs/audits/ML_PIPELINE_READINESS.md) |
| `backend/` | 55 endpoints, JWT auth, 3 roles, PostGIS models, Alembic (`0001`…`0005`). **No task queue** — simulations run as in-process FastAPI background tasks | **Keep the plumbing, replace the science** (§1.3) |
| `frontend/JalDrishti.html` + `*.jsx` | Static mock, no `package.json`, no build step. Hexagon districts, hardcoded risk badges | **Keep the visual language, rebuild the app** |
| `frontend/ml_pipeline/` | Vanilla JS + Leaflet, genuinely functional, real physics | **Absorb as the Simulation Studio** |

### 1.2 The visual language worth keeping

From `frontend/screenshots/01-map-final2.png` — stakeholders have already seen this identity:

- Map-first console, dark map canvas with a **light left rail**, teal primary, green→amber→red risk ramp
- Left rail: search → layer toggles → entity list with risk badges
- Top nav: Map · Analytics · Data Ingest · Users, with a role chip
- Legend bottom-left, zoom bottom-right

**Keep all of it.** Replace the hexagons with the real 24-district GeoJSON and the hardcoded badges
with computed indices.

### 1.3 The core problem — two engines, one of them wrong

The two halves do not merely fail to talk; they **contradict each other**.
`backend/app/services/simulation.py` runs a 9-step pipeline in which:

- line 136 sets the groundwater gradient with **`random.uniform(30, 90)`** — a literal random direction;
- step 5 calls `ml_prediction.py`, whose own output is tagged **`model: "month1_placeholder"`** (lines 56, 68), not a trained model;
- lines 161–162 compute area from a **hardcoded** `rx = 50·√365`, `ry = 10·√365` stub.

Meanwhile `ml_pipeline` derives the gradient from a plane fit over real CGWB stations and solves
Domenico transport with conformal bands. **Two endpoints in one product would return different,
incompatible answers for the same site, and the worse one is the one the legacy API exposes.**

This makes §3 (rewire simulations to `ml_pipeline`) not an enhancement but a **correctness fix**.

**Dead references still in the tree**, all confirmed present and all pointing at a directory that no
longer exists (`DataGen_ModelMVP/` was deleted from disk *and* git):

| File | Line |
|---|---|
| `backend/app/services/ml_prediction.py` | 5 |
| `backend/app/services/simulation.py` | 84 |
| `backend/requirements.txt` | 29 |
| `ml_pipeline/README.md` | 3 |

### 1.4 NEW — the database is live, and it has drifted

v2.0 designed against an empty database. `groundwater_db` was reset and reseeded on 2026-08-11 and
now holds real data. Verified by direct query:

| Table | Rows | Table | Rows |
|---|---|---|---|
| `groundwater_level_readings` | 8,345 | `districts` | 24 |
| `data_sources` | 419 | `aquifers` | 23 |
| `monitoring_stations` | 415 | `users` | 3 |
| `monitoring_wells` | 397 | `isr_points` | 1 |
| `water_samples` | 397 | `simulations` | 0 |
| `blocks` | 264 | | |

**Two facts the design must absorb:**

**(a) The 398 → 415 station split is correct, not a bug.** `cgwb_waterlevel_jharkhand.csv` has 9,583
rows and **398 distinct `station_name` values**, but **415 distinct `(name, latitude, longitude)`
triples** — the same station name recurs at different coordinates. The seed groups on the triple,
which is right: two physically distinct wells must not merge because a clerk reused a name.
The 9,583 → 8,345 reduction is likewise correct: there are exactly **1,238 duplicate
`(station, date)` pairs** in the source CSV, collapsed by the composite primary key.

> **Design consequence.** `station_name` is **not** a key. Any UI that lists or searches stations by
> name must disambiguate by coordinates, and `GET /monitoring_stations?name=` must be able to return
> more than one result. This is exactly the kind of silent join error that would corrupt a
> district-level risk roll-up.

**(b) Five tables exist in the database with no ORM model.** Migrations `0001`–`0005` created them;
the model files were later deleted without a down-migration:

`contamination_events` · `hydraulic_heads` · `ml_models` · `piezometric_heads` · `spatial_analysis_results`

All five are empty. They are unreachable from the application, invisible to SQLAlchemy, and will
confuse anyone reading the schema. **P1 drops them in migration `0006`.** The ORM currently defines
13 tables across 10 model files (`simulation.py` alone declares `simulations`, `simulation_aquifers`
and `plume_parameters`).

---

### 1.5 NEW — district and block geometry was transposed

Found on 2026-08-12 while building the citizen district aggregate, and fixed by migration `0011`.

`districts.geometry` and `blocks.geometry` were stored as **(lat, lon)** instead of (lon, lat). The
source files are the cause: `District_Boundary_JH.geojson` and `Sub_District_Boundary_JH.geojson`
violate RFC 7946 §3.1.1, while `Aquifers_Jharkhand.geojson` does not — it even declares EPSG:4326 —
which is why aquifers, wells and ISR points were correct and only these two tables were wrong.

**Nothing errored.** The polygons sat at (23.98, 85.68) instead of (85.68, 23.98): valid coordinates,
just in the wrong place. The damage was silent and compounding:

| Symptom | Consequence |
|---|---|
| Every `ST_Within` against a district or block matched nothing | `_find_block_for_point` always fell through to its "nearest block" fallback |
| The fallback picked the same centroid every time | **All 397 monitoring wells were attributed to one block** |
| A district map or aggregate read that attribution | The whole state's groundwater data would have appeared under a single district |

The last row is why this was fixed before §3.5 shipped: the wrong answer would have been
**public-facing and confidently wrong** — exactly the failure mode this document's audit history
exists to prevent.

After the fix, wells distribute sensibly across all 24 districts (Ranchi 54, East Singhbhum 28,
Hazaribagh 27, …). `IngestionService._normalise_axis_order` now detects the order on load rather
than hard-coding a swap, so it corrects itself if the upstream file is ever fixed and leaves
already-correct files alone. Jharkhand's longitude (83.3–87.9) and latitude (21.9–25.4) bands do not
overlap, which makes the detection reliable rather than a guess.

---

## 2. Roles — built around the two stated audiences

v1.0 proposed seven roles including `operator` (a mine operator with CRUD over its own sites). That
contradicts the product's own premise: **no ISR operates in Jharkhand**, so there is no operator to
onboard. Five roles, mapped to real people:

| Role | Who | Can |
|---|---|---|
| `admin` | BIT Sindri / TEXMiN system owner | Everything incl. ingest, dataset promotion, user management |
| `regulator` | **CGWB / SPCB / district officer** — the primary government user | Read every site, publish/archive, export signed reports, resolve alerts, see raw coordinates |
| `analyst` | Technical staff, researchers | Run and save scenarios; no publish, no ingest |
| `field_officer` | Station/well data collectors | Upload readings and samples only — **the CPS data path** |
| `citizen` | **Common user** (registered or anonymous) | District/block risk view, plain-language explanations, alerts for a subscribed area. **No precise site coordinates, no simulation controls** |

The backend today has only `admin`, `analyst`, `viewer` (`backend/app/models/user.py:14-16`).
`viewer` is renamed and re-scoped to `citizen`; `regulator` and `field_officer` are added. This is a
migration, not a greenfield design — existing `viewer` rows map to `citizen`.

**Why citizens cannot see exact ISR coordinates.** Every site is hypothetical. Publishing a precise
point for a *speculative* mine next to a named village invites it being read as a real plan, and
risks land-value and panic effects the project has no mandate to cause. Citizens get **block-level
aggregation**; regulators get points. This is a deliberate design constraint, not a technical limit.

Enforced with **row-level security in Postgres** keyed on `owner_org_id` and role, not only in
application code — so a service bug cannot leak site detail to a citizen session.

> **RLS shipped in P2, and it is inert until one deployment change is made.** Postgres skips
> row-level security entirely for a superuser or any role with `BYPASSRLS`. The API connects as
> `postgres`, which is both. This was verified rather than assumed: a table with
> `FORCE ROW LEVEL SECURITY` and a `USING (false)` deny-all policy still returned **every row** to
> the application's connection.
>
> Writing policies under that connection would be **security theatre** — present in the schema,
> clean on review, enforcing nothing. So P2 ships three things together:
> `0009_isr_owner_org_and_rls` (the policies, plus `isr_points.owner_org_id`),
> `scripts/create_app_role.py` (creates `jaldrishti_app`: `NOSUPERUSER NOBYPASSRLS`, DML only, no
> ownership — so the app cannot drop a policy that constrains it), and a **startup guard** that logs
> a loud warning whenever policies exist but the connected role can bypass them.
>
> **The cutover is done (2026-08-12).** The API connects as `jaldrishti_app`; migrations and
> `init_db` use `MIGRATION_DATABASE_URL` (the owner role) because the app role deliberately cannot
> `CREATE`, `ALTER` or `DROP`. The startup guard now reports
> *"Row-level security active: 4 policies, connected as 'jaldrishti_app' (no bypass)"*.
>
> `tests/test_rls.py` proves enforcement by connecting **as a non-bypassing role** and checking what
> it can actually see, not by asserting rows exist in `pg_policies`. It also pins the policy's staff
> list against `app.dependencies.STAFF_ROLES` so the two cannot drift.
>
> **Two production-only bugs the cutover exposed**, both invisible to the test suite for structural
> reasons — tests connect as `postgres` (bypassing RLS) and hold one session open per test:
>
> 1. **The audit trail died silently.** `audit_log` has RLS enabled and SQLAlchemy emits
>    `INSERT … RETURNING`, which requires the new row to be visible under the SELECT policy —
>    admin and regulator only. Every audit write by anyone else failed, and because `record()`
>    swallows its own errors by design, the trail stopped without a single failed request. Fixed by
>    running the audit writer with the system bypass, which is what `app.bypass_rls` was for.
> 2. **`DetachedInstanceError` on every 403.** The audit middleware read `user.email` off the ORM
>    instance; by then `get_db` had rolled back, which expires instances regardless of
>    `expire_on_commit`. The identity is now captured as plain values at authentication time.
>
> Both are pinned by `tests/test_authz_matrix.py`, which asserts the invariant rather than trying to
> reproduce a session lifecycle the fixtures do not have.

**Who can reach what** is documented — and generated from the running app, not hand-written — in
[`docs/roles.md`](docs/roles.md), together with the three places where the enforced authorization
still disagrees with the role definitions above.

**One RLS semantic worth knowing before relying on it.** A write blocked by a `USING` clause affects
**zero rows; it does not raise**. Postgres only errors on a `WITH CHECK` violation. So a denied
`UPDATE` or `DELETE` fails *silently* — anything built to detect tampering by catching an exception
would never fire. The audit log's append-only guarantee has this shape: there is no `UPDATE` or
`DELETE` policy on `audit_log`, so both affect nothing, for every role.

---

## 3. API audit — keep, delete, add

**55 legacy + 13 pipeline = 68 endpoints today → ~40 in the target design.**

### 3.0 What P2 actually deleted, and one thing this section missed

**55 → 44 endpoints.** The list in §3.1 was written before the code was read closely; three
corrections came out of executing it.

> **A privilege-escalation hole §3.1 did not list.** `POST /auth/signup` was **unauthenticated** and
> accepted a client-settable `role` that flowed into `UserRole(data.role)` with no server-side check.
> Verified exploitable end to end: an anonymous caller created an `admin` (201), logged in, and read
> the admin-only user list (200). §3.1 deleted `POST /users` for being "the wrong primitive for a
> government portal" while the *same primitive, unauthenticated*, sat one router away. **Deleted in
> P2**, with `tests/test_auth_hardening.py` written against the property — no unauthenticated route
> may mint a user — rather than against the path, so it cannot reappear under another name.

**`GET /blocks`, `/monitoring-stations`, `/monitoring-stations/count` are NOT duplicates — kept.**
§3.1 called them "undocumented duplicates of the scoped equivalents". They are not. `GET /blocks`
returns all 264 blocks statewide (`BlockService.list_all`); the scoped route returns one district's.
The Map Console in §4.1 lists Districts, Blocks and Stations as *statewide layers* — deleting these
would have broken the screen this document specifies, and forced 24 nested calls to rebuild it.

**`POST/PUT/DELETE /users` kept, admin-only.** §3.1 deletes them as "superseded by invitation + role
assignment" — but the invitation flow (§3.3) does not exist yet, and with signup gone these are the
only way to administer accounts. They were already behind `require_admin`. Delete them when
`POST /orgs/{id}/invite` ships, not before.

**The 5 `ml_pipeline` deletions are deferred.** §3.1 removes four overlay endpoints because they are
"duplicated by the unified geography service" — a service that does not exist until P4/P5. The
frozen dashboard serves them today. Deleting them in P2 would break a working screen to satisfy a
future one.

### 3.1 DELETE — the original list

| Endpoint(s) | Why it goes |
|---|---|
| `POST/PUT/DELETE /aquifers`, `/blocks`, `/districts` (9) | Reference geography from CGWB/GSI. Not user-editable content — editing it via API silently forks the scientific basis of every simulation. Load through versioned ingest instead |
| `POST /users`, `PUT /users/{id}`, `DELETE /users/{id}` (3) | Superseded by invitation + role assignment. A plaintext-password create endpoint is the wrong primitive for a government portal |
| `GET /global_blocks`, `/global_monitoring`, `/global_monitoring/count` (3) | Undocumented duplicates of the scoped equivalents. Two code paths for one entity is exactly how the `ml_pipeline` species bug happened |
| `POST /auth/token` (1) | Duplicate of `POST /auth/login` |
| `GET /` root banner (1) | Replaced by the SPA |
| `POST /api/drift/reset` (1) | Debug affordance → admin-only, off the public API |
| `GET /api/aquifers`, `/api/boundary`, `/api/ore`, `/api/rivers` (4) | Duplicated by the unified geography service. The pipeline should not serve map layers |

### 3.2 KEEP — with changes

| Endpoint | Change required |
|---|---|
| `POST /auth/login`, `/logout`, `GET /auth/me` | Add refresh tokens; MFA hook for `regulator` |
| `GET /districts`, `/districts/geojson`, `/blocks`, `/aquifers` | Read-only; `?simplify=`, `ETag`/`Cache-Control` |
| `GET/POST/PUT/DELETE /isr_points` | **The heart of the product** — the hypothetical-site registry. Add `status`, `owner_org_id`, soft delete |
| `POST /simulations/{isr_id}`, `GET /simulations/{sim_id}` | **Rewire to `ml_pipeline`.** Delete the random-gradient stub and `month1_placeholder` outright (§1.3) |
| `GET/POST /monitoring_stations`, `/{id}/readings` | Keep — the CPS data path. **Must return multiple rows for a repeated station name** (§1.4a) |
| `GET /monitoring_wells`, `GET/POST /water_samples` | Keep |
| `POST /ingest/*` (5), `GET /ingest/data-quality-report` | Keep, admin-only. The data-quality report is a named proposal deliverable |
| `GET /health` | Extend to report ML artifact + DB status |
| `POST /api/predict`, `GET /api/pin`, `/api/flow_field`, `/api/strike_field`, `/api/drift`, `/api/assumptions`, `/api/health` | Keep behind the gateway with auth + limits |

### 3.3 ADD — new endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/refresh` | Token rotation |
| `GET /orgs`, `POST /orgs/{id}/invite` | CGWB, SPCB, BIT Sindri as separate orgs |
| `GET /me/permissions` | Frontend renders from server truth, never guesses |
| `GET /sites/{id}/risk` | Composite risk index — what the map colours by |
| `GET /sites/{id}/downstream` | Receptors at risk: villages, wells, river reaches |
| `GET /sites/{id}/excursion` | The NUREG-1569-inspired indicator excursion state (§4.2) |
| `POST /scenarios`, `GET /scenarios/{id}`, `POST /scenarios/{id}/compare` | Saved, named, shareable scenarios — **what makes this a product rather than a calculator** |
| `GET /public/risk/{district_id}` | The citizen-facing aggregate; no auth, heavily cached |
| `GET /alerts`, `POST /alerts/rules`, `POST /alerts/{id}/ack` | CPS loop: breach → alert → acknowledgement |
| `GET /reports/{site_id}.pdf` | Signed, dated regulator report with provenance appendix |
| `GET /audit` | Who ran what, when — non-negotiable for a government portal |

---

### 3.4 P3 — simulations on the real engine

`POST /simulations/{isr_id}` now runs `ml_pipeline` and persists the result. It returns **202** with
a queued run; a prediction takes ~5 s, too long to hold a request open. Poll
`GET /simulations/runs/{run_id}`.

| | |
|---|---|
| `POST /simulations/{isr_id}` | admin, analyst. Sliders only — **the location comes from the ISR point, never the body**, so a caller cannot run a scenario at a pin the registry does not hold |
| `GET /simulations/runs/{run_id}` | staff |
| `GET /simulations/runs?isr_id=` | staff |
| `GET /simulations/{sim_id}` | staff. Legacy rows from the pre-P0 engine; nothing writes there any more |

**Reproducibility is enforced, not encouraged.** Every completed run stores `model_card_sha`,
`artifacts_sha` (one digest over the whole artifact bundle, so swapping a single `.joblib` is
visible) and `code_version`. `ck_sim_runs_completed_is_pinned` **rejects a completed run that cannot
name all three** — a screening number a regulator acted on has to be re-derivable.

> **THE ML MODEL DOES NOT CONSUME FIELD DATA.** Only the pin and the operational sliders cross into
> the engine — enforced by an allowlist in `app/services/ml_pipeline_adapter.py` that **refuses**,
> rather than filters, a payload carrying anything else. Everything the engine needs (aquifer
> properties, flow azimuth, gradient, fracture strike, baselines, the Texas source term) it resolves
> from its own `Datasets/` and frozen artifacts.
>
> This is not tidiness. The surrogate's conformal bands were calibrated against a fixed input
> distribution; feeding it freshly approved field chemistry would invalidate that calibration
> **silently** — the bands would still print, and the 80% would no longer be 80%. Routing field data
> into the model requires a deliberate re-bake, retrain and re-run of the coverage gate (§4.6 rule 9).
> `test_approving_field_data_does_not_change_the_model_output` proves it end to end: it runs a
> simulation, has a regulator approve a 9,999 ppb uranium reading at the same coordinates, re-runs,
> and asserts the metrics are byte-identical.

**Still outstanding in P3:** named/saved scenarios and `POST /scenarios/{id}/compare`. Runs are
reproducible but not yet nameable or comparable.

### 3.5 P6 (partial) — the citizen surface

Built early to close D-3 in [`docs/roles.md`](docs/roles.md), where `citizen` could reach exactly one
endpoint and the product's second named audience had no API at all.

| | |
|---|---|
| `GET /public/risk/districts` | **no auth**, cached 1 h. All 24 districts, banded |
| `GET /public/risk/{district_id}` | **no auth**, cached 1 h. Block breakdown with plain-language explanations and a `data_gap` count |

Aggregates only — no site points, no well coordinates, no plume geometry, nothing from a simulation.
These report **measurements, not predictions**: real CGWB sampling, never the surrogate, so the
hypothetical-mine framing and the real-water-quality framing cannot blur on the surface a member of
the public sees. Bands are words (`Low` / `Moderate` / `High concern`), per §4.4's copy rules.

Still outstanding: C3 alert subscription and the C4 methods page.

### 3.6 DECISION — approved field data vs the frozen model

**Decided 2026-08-12.** An approved field observation is authoritative in the portal
immediately, but `ml_pipeline` reads only `Datasets/`. The question was how to close that gap
without letting approved data slide into a frozen, gate-validated model.

**A correction to the framing first.** "Approved chemistry ⇒ ML retraining required" is *not* right
for this pipeline. The 40 trained features (`background_conc_Cb`, `gradient_i`, `source_conc_C0`, …)
are **resolved at serve time** from the datasets. Correcting one well's uranium changes a feature
*value*, not the model, and the surrogate was trained across a range of those values. **Retraining is
required only when the generator's assumptions change** — physics constants, the Texas C0 envelope,
the species set (§4.6 rule 9). A field reading is not that.

**Three options were compared:**

| | Auto-feed DB → engine | Continuous DB → dataset sync | **Admin-triggered export** |
|---|---|---|---|
| Reproducibility | **Broken** — same pin and sliders drift over time with nothing recorded | preserved | preserved |
| `ml_pipeline` freeze | broken; adds a DB dependency its tests forbid | intact | intact |
| Fits the real change rate? | — | built for continuous data | matches a handful of ore sightings |

**Chosen: option 3.** Option 1 fails on the project's core claim — a regulator cannot defend a number
that moves. Option 2 is the right end state if this ever ingests sensor streams (§7) and is heavy
machinery for the expected volume. **No scheduled rebake:** a weekly retrain on a frozen model whose
coverage was hand-verified buys nothing and risks silently replacing those artifacts.

#### The split-brain is made visible, not closed

Three states, surfaced by `GET /dataset-sync/status` and per-feature on
`GET /field-observations/map`:

| | State | Meaning |
|---|---|---|
| 🔴 | `pending_review` | Submitted, not reviewed. Changes nothing. |
| 🟡 | `approved_pending_sync` | Authoritative in the portal, **not yet in `Datasets/`** — the engine does not see it. |
| 🟢 | `approved_in_model` | Synced; the engine now resolves it. |

`GET /simulations/runs/{id}` carries the count too, because a plume is read as *"what we know"*: if
N approved observations were not among its inputs, the reader is told **on the result**, not in a
settings screen. The map returns three separate collections rather than one flagged list — a merged
list invites a client to draw unreviewed or unsynced input as confirmed.

#### Only ore has an automated export

`POST /dataset-sync/ore` (admin only) appends approved ore observations to both files:

| File | Drives |
|---|---|
| `Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv` | `ore_zone_at()` — whether a pin is deposit/belt/none, and therefore **whether a uranium plume is possible at all** |
| `Datasets/udepo_uranium_deposits.xlsx` (header row 8) | `grade_c0_factor()` — scales the source concentration C0 |

Both gain an **`origin` column**: `original` for the rows that shipped, `added` for anything a
regulator approved, so the map can render the two differently. Existing rows are backfilled as
`original` on first sync. Each run backs both files up, tags the batch with a `sync_ref`, marks the
observations synced, clears the pipeline's `lru_cache`d loaders (without which a running process
keeps serving the pre-sync ore map and the sync looks like it did nothing), and audits the batch. It
is idempotent, has a `dry_run`, and refuses a name that collides with an existing deposit — the grade
lookup keys on name, so a duplicate would make C0 ambiguous.

**Verified end to end:** at (85.20, 23.80) the resolved zone is `none`; after a sync it is `deposit`,
and it returns to `none` when the file is restored. That is the case the field-officer role exists
for, and it did nothing at all before this.

**Chemistry and groundwater levels stay manual.** They move a feature value the model already covers,
they are rare, and the audit log gives an admin the old/new values to apply by hand.
`GET /dataset-sync/pending` is the working list.

#### A gap this surfaced — **RESOLVED 2026-08-12**

`source_conc_C0` and `background_conc_Cb` were the only two trained features `envelope_violations()`
never checked. They were looked up in the model card's `training_envelope`, which has no entry for
either, and `env.get(key, (-inf, inf))` turned each lookup into a **silent no-op** — a baseline or
source term outside trained support extrapolated with the conformal 80 % band still printed.

Fixed additively, without touching artifacts or retraining:

- `P.TRAINED_SPECIES_SUPPORT` records the **per-species** C0/Cb box measured from the deployed
  training set. Per species, not global, because the bounds span three orders of magnitude between
  them — one global range would accept a uranium C0 of 25 mBq/L. It lives in config rather than
  being read from the CSV at runtime because `ml_pipeline/outputs/` is gitignored, and a guard that
  vanishes in a clean checkout is the failure being removed. A test re-derives it from the CSV
  whenever present, so a retrain that shifts the support fails the suite.
- `_species_support()` prefers a `species_support` key in the model card, so a future retrain that
  records one wins automatically.
- The tolerance is the same scale-aware rule the hydro check already uses (ratios once the support
  spans a decade), which keeps a 0.4 % boundary case from flagging while a 17 % excursion does.
- `envelope_violations(inputs, hydro=None)` gained an optional second argument, read only for
  `u_suppressed`: in a non-ore zone C0 is deliberately clamped to background and **the server
  already bypasses the surrogate**, so that clamped value is not an ML extrapolation. Without this
  every non-ore pin would turn amber for no reason.

**One real behaviour change, deliberately.** At Jaduguda and Bhatin the measured baseline exceeds
anything the generator sampled — sulfate 227 mg/L against a trained 2–190, TDS 1779 against
97.9–1513.6 — so those runs now report `conc:background_conc_Cb`. The conformal band there was never
guaranteed; the run previously said nothing. Across a spread of eight pins × four species, **4 of 32
combinations flag**, all of them genuine; the non-ore and boundary cases correctly do not.

### 3.7 P3 (final) — named scenarios and comparison

`scenarios` (migration `0014`) names a **set of inputs**, never a result. Running one queues a normal
`simulation_run` tagged with the scenario, so results stay immutable and pinned to the artifacts that
produced them — re-running after a retrain adds a second run with a different `artifacts_sha` rather
than overwriting the first, which is what makes a before/after comparison possible at all.

| | |
|---|---|
| `POST /scenarios` | admin, analyst. Params validated **at save time** against the engine allowlist — a scenario that cannot run is worse than one that is refused, because it looks saved |
| `GET /scenarios`, `GET /scenarios/{id}` | staff |
| `POST /scenarios/{id}/run` | admin, analyst |
| `POST /scenarios/{id}/compare` | staff |
| `DELETE /scenarios/{id}` | archives; runs reference the scenario that produced them |

Names are unique **per site**, not globally — two districts may both want a "baseline".

`compare` reports **why** two runs differ, not just the delta: *inputs differ; same model* / *same
inputs; the MODEL changed* / *both differ — the delta cannot be attributed without re-running one*.
"The number changed" is only actionable once you know which of those happened.

## 4. Frontend design

**Stack:** React 18 + TypeScript + Vite · **Leaflet** (as today) · TanStack Query · Tailwind +
shadcn/ui · Recharts.

Note this is a **greenfield build**: `frontend/` has no `package.json` and no build step today, so
adopting Vite adds tooling rather than replacing it.

**Map library decision.** v1.0 mandated MapLibre GL vector tiles on a 60 fps argument. That is
premature: `frontend/ml_pipeline/app.js` already renders 23 aquifer polygons, 4,577 river reaches
(decimated) and plume contours on Leaflet acceptably, and MapLibre requires standing up a tile server
(tippecanoe / pg_tileserv) — real infrastructure for a UG fellowship prototype. **Ship on Leaflet;
revisit MapLibre only if the 264-block layer measurably drops frames.** Do not pay infrastructure
cost for a hypothetical.

### 4.1 Screens — officials

**1 · Login** — org SSO, role shown before entry.

**2 · Map Console** *(default landing for officials)* — evolves the existing mock.
Left rail search → layer toggles (Districts, Blocks, Aquifers, ISR Sites, Plumes, Stations, Wells,
Rivers, Ore, Flow field, Fracture strike) → entity list with computed risk badges. Right drawer on
select: site summary, latest run, downstream receptors, "Open in Studio". **Every plume carries a
`HYPOTHETICAL` ribbon.**

**3 · Site Registry** — table + map split. Create, review, publish, archive hypothetical sites.

**4 · Simulation Studio** — the current `ml_pipeline` dashboard as a first-class screen. Sliders left,
map centre, metric cards right with **P10–P90 bands always visible**, lifecycle timeline bottom,
**provenance drawer** on every input, save/compare scenarios.

**5 · Monitoring & Alerts** *(the CPS deliverable)* — station map, time-series with seasonal bands,
threshold rules, alert inbox with acknowledgement trail.

**6 · Analytics** — district vulnerability ranking, species comparison, exceedance vs BIS/WHO, and the
**Data Gap Report** (a named proposal deliverable: which districts lack NAQUIM profiles, which wells
lack recent samples, where the flow field falls back to DEM).

**7 · Data Ingest** *(admin)* — upload, validate, diff against current version, promote.

**8 · Admin** — orgs, users, roles, API keys, rate-limit tiers, audit log.

### 4.2 The ISR Excursion panel

**This is the most product-relevant thing the pipeline has, and it is what a regulator actually acts on.**

A real ISR operation is not judged by "did uranium exceed a drinking-water limit". US NRC NUREG-1569
§5.7.8.3 defines an excursion as **two or more conservative indicator parameters exceeding their
upper control limits** at a perimeter monitoring well — and p.137 explicitly rejects uranium as an
indicator *"because … it may be retarded by reducing conditions in the aquifer."*

The pipeline implements this, and it **fires earlier than the health-limit breach** — verified at
Jaduguda, gradient 0.005, t = 20 yr: excursion DECLARED while the BIS uranium breach still reads NO.

The panel shows:

- **Excursion status** (`DECLARED` / `none`) and the indicator count, under a **2-of-3** rule
  (`ISR_EXCURSION_MIN_INDICATORS = 2`, verified in config)
- Per indicator (**chloride, TDS, sulfate**): ring concentration vs its upper control limit
  (UCL = baseline × 1.20, then bracketed per NUREG p.138)
- **A persistent non-compliance statement** — the panel meets NUREG's minimum count of three
  indicators, which makes the test *structurally* like a licensed one but **does not make it one**.
  What is still missing is named in the response: per-well temporal baselines, the
  verification-resampling protocol, the 60-day controllability demonstration, and an actual wellfield
- The monitor ring distance and its NUREG-licensed range (**75–180 m**, verified)

**Why chloride and not alkalinity.** Enrichment was measured on this project's own paired Texas
baseline/end-of-mining data, then tested against *Jharkhand* background:

| indicator | TX enrichment | contrast vs JH background | sensitivity |
|---|---|---|---|
| sulfate | 9.5× | 29.6× | most sensitive |
| **chloride** | 1.7× | **9.9×** | **added** |
| TDS (= conductivity) | 3.1× | 7.6× | in use |
| bicarbonate/alkalinity | 2.2× | **2.5×** | **rejected** |

Two findings inverted the naive assumption. **Alkalinity — the canonical alkaline-ISR signature and a
member of the licensed US triad — is the weakest candidate here**, because Jharkhand hard-rock
groundwater is already bicarbonate-dominated (250 mg/L); it would need 13.3 % of the source to reach
the ring before tripping. **Chloride is the reverse**: the weakest enricher in Texas, but excellent
here, and the only perfectly conservative (Kd = 0) member — so unlike sulfate it is immune to the
sulfide-oxidation false alarms NUREG warns about, a risk *elevated* in the Singhbhum polymetallic
sulphide province. It required **no new dataset** (the `Cl (mg/L)` column was already in the CGWB
file, 397/397 wells) and **no retrain** — it lives in `EXCURSION_ONLY_SPECIES`, deliberately outside
`SPECIES` and `ML_SPECIES`.

> **Architectural note for implementers.** That registry split is load-bearing. `SPECIES` /
> `ML_SPECIES` are `("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")`;
> `EXCURSION_ONLY_SPECIES` is `("chloride_mg_l",)`, resolved on the analytical path only in
> `dashboard/isr_excursion.py`, which never calls the surrogate. **Adding an indicator is cheap;
> adding a predicted species costs a full re-bake and retrain.** Do not let a product requirement
> quietly cross that line.

The excursion result sits **next to, not instead of,** the BIS/WHO health-limit result. They answer
different questions and the difference is itself informative.

### 4.3 How to state the uncertainty claim

The field-resampled gate has run and **passed** on a held-out batch of 120 scenarios / 2,400 rows
drawn from the real flow field, at a 0.80 gate:

| target | scenario coverage | passes |
|---|---|---|
| `affected_area_ha` | 0.865 | ✅ |
| `max_migration_distance_m` | 0.904 | ✅ |
| `compliance_conc` | 0.912 | ✅ |

The UI may therefore say: **"80% conformal band, validated on a held-out sample of real Jharkhand
hydrogeology."** It must **not** say "80% guaranteed" — the guarantee is conditional on the parameter
distribution and is void wherever `extrapolation` is non-empty.

### 4.4 The citizen surface

The proposal names *local communities* as stakeholders and the brief names *common users*. v1.0 gave
them one line (`public` role, "district risk map only"). That is not a designed experience.

**C1 · Public Risk Map** *(no login)* — Jharkhand districts coloured by aggregate vulnerability.
Tap a district → block list with a plain badge. **No site points, no coordinates, no sliders.**

**C2 · "My Area"** — pick or detect a block. One screen, plain language, no jargon:

- *"Groundwater near you: **Moderate concern**"*
- What was measured (nearest CGWB well, its distance, when sampled)
- What is hypothetical (*"no uranium mine of this type operates in Jharkhand; this shows what would
  happen if one did"*) — stated in the **first paragraph**, not a footnote
- What to do: whom to contact, what a household water test costs

**C3 · Subscribe to alerts** — email/SMS when a monitored parameter in a subscribed block crosses a
threshold.

**C4 · Data & Methods** — a readable version of the assumption register from `/api/assumptions`, so a
citizen or journalist can see what the numbers rest on.

**Citizen copy rules.** No units without context (*"30 ppb — the safe limit"*, not `30.0 ppb`). No
P10/P90 bands — a plain three-level band label (*Low / Moderate / High concern*) with "how sure are
we?" as words. No model jargon (`conformal`, `Domenico`, `β_eff`) anywhere on C1–C3.

### 4.4b Field-observation states — the UI contract for P4

The Map Console renders field observations and simulation output on the same canvas, so it must
distinguish three states from the first version. Drawing them as one layer would have to be rebuilt.

| | State | Source | Rendering |
|---|---|---|---|
| 🔴 | **Pending review** | `map.pending_review` | Hollow marker, dashed outline. Never counted in any total. Visible to staff only |
| 🟡 | **Approved, pending dataset sync** | `map.approved_pending_sync` | Solid marker, amber ring + "not in model" chip. Authoritative as an *observation*; the plume on screen did not use it |
| 🟢 | **Approved and in the model** | `map.approved_in_model` | Solid marker, no qualifier. The engine resolves it |

**A global counter belongs in the header**, from `GET /dataset-sync/status`:
*"N approved observations are not yet in the model."* Clicking it opens the amber list
(`GET /dataset-sync/pending`); for an admin it also offers `POST /dataset-sync/ore`.

**And on the result itself.** `GET /simulations/runs/{id}` returns `approved_pending_sync` and a
`sync_note`. The Simulation Studio must show it beside the plume, not in a settings screen: a plume
is read as *"what we know"*, and if approved observations were not among its inputs the reader has to
be told where they are looking.

**Rule:** never merge the three into one list with a status field. A merged list invites a client to
draw unreviewed or unsynced input as confirmed, which is the confusion the whole review workflow
exists to prevent.

### 4.5 Non-negotiable UI rules

From the audit history, to stop the portal over-claiming:

1. **No bare point estimates** on official surfaces. Every predicted quantity renders with its band or
   an explicit "deterministic — no band" label.
2. **Extrapolation is loud.** Outside the trained envelope, cards turn amber and state that the
   conformal guarantee is void and the analytical engine is serving.
3. **Provenance on hover** for every input, carrying `n` where small (the Texas n = 9 case).
4. **"Total Vulnerable Area" is relabelled** to **"Contaminated Footprint (wellfield + migrating
   plume)"** with the split shown — it is 76–97 % leach-zone disc.
5. **Migration reads "no measurable migration"** below map resolution, never a misleading `0`.
6. **The hypothetical premise is never more than one glance away** — and on citizen screens it is in
   the first paragraph.
7. **Field data carries its state.** Every observation renders as 🔴 pending / 🟡 approved-not-synced
   / 🟢 in-model (§4.4b). A value the engine has not seen must never look like one it has.

### 4.6 Frozen constraints inherited from `ml_pipeline`

These come from [`docs/audits/ML_PIPELINE_READINESS.md`](docs/audits/ML_PIPELINE_READINESS.md) §7 and
**must not be redesigned around**:

1. **The analytical engine is the authority**; ML supplies bands only. Never show an ML P50 without
   its band; never let ML override analytical.
2. **Uranium and radium must never be presented as excursion indicators** (NUREG-1569 p.137).
3. **Non-ore zones must not show a uranium plume** — the "tool cannot invent contamination" guard.
4. **`wellfield_width_m` is the well-pattern footprint diameter**, not a borehole width.
5. **Displayed retardation and K must remain the effective/served values**, not the tracer or shallow
   ones.
6. **Thresholds, species set and units are fixed** (U 30 ppb · SO₄ 400 mg/L · TDS 2000 mg/L ·
   Ra-226 1000 mBq/L).
7. **Radium is exposed as analytical value + band, never as a standalone ML point estimate** (§8).
8. Moving the monitor ring off 100 m flags extrapolation by design.
9. **No new datasets, models or modelling approaches** without a re-bake, retrain and re-run of the
   field coverage gate.

### 4.7 P4 — what shipped

`frontend/portal/` — Vite + React 18 + TypeScript, TanStack Query, React Router,
Leaflet. `npm run dev` on :5173, proxying `/api` to :8000 so the browser makes
same-origin requests and production can sit behind the same gateway unchanged.
The UX specification is [`docs/FRONTEND_DESIGN.md`](docs/FRONTEND_DESIGN.md).

**The organising decision: the portal is eight sections filtered per role, not one
dashboard with things greyed out.** A regulator opening the portal needs a decision
queue; a field officer needs their own submission ledger; an analyst needs scenarios;
an admin needs system state; a citizen needs plain language and no coordinates. So
`/overview` resolves to **five different screens**, and the nav is built from the
signed-in role rather than filtered after the fact.

| Section | admin | regulator | analyst | field officer | citizen |
|---|:--:|:--:|:--:|:--:|:--:|
| Overview (role-specific) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Map Console | ✅ | ✅ | ✅ | ✅ | — |
| Simulation Studio | ✅ | ✅ | ✅ | — | — |
| Field Data | ✅ review | ✅ review | — | ✅ submit | — |
| Data & Gaps | ✅ +sync | ✅ | ✅ | ✅ | — |
| Audit | ✅ | ✅ | — | — | — |
| Administration | ✅ | — | — | — | — |
| Public View / "My Area" | ✅ | ✅ | ✅ | ✅ | ✅ |

Route guards are **convenience, not the boundary** — a hand-typed URL renders a
refusal instead of an empty shell, while the API guard and the RLS policy behind it
do the actual enforcement. Both layers were tested independently (below).

**Design decisions worth recording.**

- **The map keeps no raster basemap.** The ml_pipeline dashboard has none either: the
  risk ramp is the information, and tiles compete with it. District fill encodes
  *measured* uranium, never model output.
- **Shape carries identity, colour carries state.** ISR sites are amber **diamonds**;
  amber circles mean "approved, not yet in the model". This was a defect found in the
  first P4 build and it is now a rule.
- **Simulation Studio is a numbered path** — ① site ② contaminant ③ parameters ④ run
  ⑤ save as scenario — because an analyst's failure mode is running the wrong scenario
  confidently, not being unable to find a control.
- **Sliders deliberately extend past the trained envelope.** The analytical engine still
  serves out there and the result is flagged, not refused (§3.6). The rail says so.
- **The citizen surface shows no coordinate, no site, no band, no jargon** — the nav
  even renames Public View to "My Area".

**Nothing unsupported is faked.** Where the backend cannot serve a feature, the UI
renders a `Planned` card naming the phase and the reason:

| Marked planned | Why |
|---|---|
| Plume contour map, P10/P90 migration envelope | The run API persists metrics, excursion state and hydrogeology — not plume geometry (P5) |
| Alert subscriptions | No notification service exists (P7) |
| PDF / signed report export | No report service exists (P8) |
| Bulk ingest upload UI | The five ingest endpoints exist and are admin-only; the upload screen is not built |
| Organisation invitations, API keys | Organisations exist in the schema; no invitation or key endpoint does |

**Five seeded accounts, one per role.** The old three-user demo set (`admin`,
`analyst`, `viewer`) could not exercise a five-role system. `scripts/seed.py` now
seeds one account per role and **retires** `viewer@jaldrishti.local`, deleting it if
present so it cannot linger as an unlabelled login.

**Verified in a real browser against the live API**, not asserted:

- all **five logins** succeed and `/auth/me` returns the expected role for each
- the **API authorization matrix** holds independently of the UI — citizen gets 403 on
  `/isr-points`, `/field-observations/map`, `/dataset-sync/status`, `/audit`, `/users`
  and `/scenarios`, and 200 only on `/public/risk/districts`; analyst and field officer
  get 403 on `/audit` and `/users`; regulator gets 403 on `/users` alone
- the **nav matches the matrix** for every role, and every out-of-role route renders
  the refusal rather than a broken page
- 24 district polygons, the ISR diamond, and 397 monitoring wells draw on the map
- the **tri-state cycle end to end**: field officer submits → 🔴 pending with a full
  old/new diff → regulator approves → header pill flips to 🟡 "1 not in model" →
  admin syncs → 🟢 in model, with `origin=added` rows landing in both ore files and
  `retrain required: false`
- a simulation queued, polled and completed in 14.2 s, rendering P10–P90 bands, the
  2-of-3 excursion table and its provenance triple
- the citizen drill-down renders measured block readings in plain language with the
  monitoring-gap caveat, and **no sync pill, coordinate or model number leaks into it**

**Three defects found and fixed during this verification.**

1. **The wells layer never loaded.** `/monitoring-wells` requires a `bbox` — it is
   viewport-scoped by design — and the client called it without one, so the layer
   silently 422'd. The query now follows the map, rounded to 4 dp to match the
   endpoint's own cache key.
2. **A completed run could sit on "running" forever.** The client disables
   window-focus refetching, and a plain `refetchInterval` is paused while the tab is
   hidden — so switching away mid-run and back stranded the row. Fixed with
   `refetchIntervalInBackground`.
3. **The excursion table's UCL column was always empty** while the "over" column still
   said yes: the client read `i.ucl`, but the payload field is `upper_control_limit`.
   A threshold-free "yes" is exactly the kind of unexplained assertion §4.5 exists to
   prevent. The UCL rule and per-indicator units are now shown too.

A fourth, smaller fix: the public explainer said "the 1 wells sampled here". It is
read by citizens, so it now agrees in number.

---

## 5. Database design

**PostgreSQL 16 + PostGIS 3.4**, both already in use and already seeded (§1.4).

**TimescaleDB is not in the MVP.** v1.0 added it for "time-series that will grow continuously under
CPS". The actual load is **8,345 rows**, growing four campaigns a year. Plain Postgres with a BRIN
index on `recorded_at` handles that for years, and every added extension is a deployment dependency
the host institution has to support. **Adopt TimescaleDB only when real sensor streams exist** (§7) —
the schema below is compatible either way.

### 5.1 Schema map

```
┌─ IDENTITY ────────────────────────────────────────────────┐
│ orgs ──< users ──< user_roles >── roles ──< permissions   │
│                      └──< api_keys        audit_log       │
└───────────────────────────────────────────────────────────┘
┌─ REFERENCE GEOGRAPHY (read-only, versioned) ──────────────┐
│ districts ──< blocks ──< aquifers                         │
│ rivers · lineaments · ore_deposits · naquim_profiles      │
│ dataset_versions ──< dataset_files                        │
└───────────────────────────────────────────────────────────┘
┌─ MONITORING (time-series) ────────────────────────────────┐
│ monitoring_stations ──< groundwater_level_readings        │
│ monitoring_wells    ──< water_samples                     │
│ sensors             ──< sensor_readings   [empty; see §7] │
└───────────────────────────────────────────────────────────┘
┌─ SIMULATION ──────────────────────────────────────────────┐
│ isr_sites ──< scenarios ──< simulation_runs               │
│                               ├──< run_metrics            │
│                               ├──< run_geometry (PostGIS) │
│                               └──< run_provenance         │
└───────────────────────────────────────────────────────────┘
┌─ DECISION SUPPORT ────────────────────────────────────────┐
│ alert_rules ──< alerts ──< alert_acknowledgements         │
│ risk_snapshots · reports · citizen_subscriptions          │
└───────────────────────────────────────────────────────────┘
```

### 5.2 Migrations `0006` / `0007` — **shipped**

**`0006_drop_orphan_tables`** drops the five orphans from §1.4b:

```
contamination_events · hydraulic_heads · ml_models · piezometric_heads · spatial_analysis_results
```

It refuses to run if any of them has gained a row since the audit — dropping an empty orphan is
housekeeping, dropping a populated one is data loss, and the migration is not authorised to make
that call silently. `downgrade()` restores all five with their original columns, indexes and
constraints, and the up→down→up round trip is verified.

> **One recon error worth recording.** §1.4b was drafted believing three of the five were never in
> any migration. They were — `0004_month3_schema` creates them; a line-based grep could not match
> `op.create_table(` against the table name on the next line. **The migration chain is healthy** and
> `alembic upgrade head` on an empty database reproduces the schema exactly. The real fault was
> one-directional: models deleted without a matching down-migration, so the chain kept building
> tables the application could no longer see.

`tests/test_schema_integrity.py` now pins the two together. It stands up a scratch database, runs
`alembic upgrade head`, and diffs the result against `Base.metadata` in both directions — a
migrated table with no model, and a model with no migrated table. The normal suite cannot catch
this, because `conftest.py` builds its schema with `create_all()` and so compares the ORM against
itself.

**`0007_orgs_provenance_audit`** adds `orgs`, `dataset_versions`, `audit_log`, `users.org_id`,
`data_sources.dataset_version_id`, and extends the `userrole` enum. Two deliberate deviations from
what §5.1/§5.3 originally sketched:

**(a) `dataset_versions` does not absorb `data_sources`.** The design gave `dataset_versions` a
`sha256` and a `row_count` — both of which `data_sources` already carries, across 419 rows of real
load history. Two tables owning checksum semantics is the same "two code paths for one entity"
failure §3.1 rejects, and provenance is the last place to accept it. They are split by the
granularity they actually operate at:

| Table | Grain | Owns |
|---|---|---|
| `data_sources` | one row per ingested **batch** | file name, checksum, row count, load time |
| `dataset_versions` | one row per **citable dataset** | label, source org, citation, `n_supporting`, `caveat` |

`data_sources.dataset_version_id` links ledger to spine. All 419 existing loads are linked, zero
unregistered. The grain difference is real: 415 of those rows are per-station groundwater batches
(`gw_level:<station>`) that all came from one CSV.

**(b) `roles` / `user_roles` / `permissions` are deferred to P2.** `users.role` is still the only
thing the auth layer reads. Standing up a parallel, unread role store would recreate exactly the
duplication described in (a). `0007` instead extends the `userrole` enum with `regulator`,
`field_officer` and `citizen` so the vocabulary exists; P2 builds the gateway that reads them and
migrates `viewer` → `citizen` alongside the code that depends on it. The enum change is purely
additive — Postgres cannot remove an enum value, so retiring `viewer` before its readers exist would
strand the running app.

### 5.3 Tables that matter most

**`isr_sites`** — the registry authorities navigate.

```sql
CREATE TABLE isr_sites (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code            TEXT UNIQUE NOT NULL,            -- 'JH-ISR-0001'
  name            TEXT NOT NULL,
  location        GEOGRAPHY(POINT, 4326) NOT NULL,
  district_id     UUID REFERENCES districts(id),
  block_id        UUID REFERENCES blocks(id),
  owner_org_id    UUID NOT NULL REFERENCES orgs(id),
  site_kind       TEXT NOT NULL CHECK (site_kind IN
                    ('hypothetical','proposed','historic_conventional')),
  -- NOTE: no 'operational' value exists. No ISR operates in Jharkhand, and the
  -- schema refuses to let the UI imply otherwise.
  ore_zone        TEXT CHECK (ore_zone IN ('deposit','belt','none')),
  ore_depth_m     NUMERIC(7,2),
  status          TEXT NOT NULL DEFAULT 'draft' CHECK (status IN
                    ('draft','under_review','published','archived')),
  created_by      UUID NOT NULL REFERENCES users(id),
  deleted_at      TIMESTAMPTZ,                     -- soft delete only
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON isr_sites USING GIST (location);
CREATE INDEX ON isr_sites (owner_org_id, status) WHERE deleted_at IS NULL;
```

**`simulation_runs`** — every execution immutable and reproducible.

```sql
CREATE TABLE simulation_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id       UUID NOT NULL REFERENCES scenarios(id),
  status            TEXT NOT NULL DEFAULT 'queued',
  engine            TEXT NOT NULL,                 -- 'analytical' | 'ml' | 'both'
  -- REPRODUCIBILITY. Without these three a result cannot be defended a year
  -- later, and this tool's whole claim is defensibility.
  model_card_sha    TEXT NOT NULL,
  code_version      TEXT NOT NULL,                 -- git SHA
  dataset_version   UUID NOT NULL REFERENCES dataset_versions(id),
  inputs            JSONB NOT NULL,                -- resolved, not raw sliders
  metrics           JSONB,                         -- p10/p50/p90 per target
  excursion         JSONB,                         -- NUREG indicator state (§4.2)
  extrapolation     TEXT[],                        -- envelope violations
  runtime_ms        INTEGER,
  created_by        UUID NOT NULL REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`monitoring_stations`** — with the §1.4a constraint made explicit.

```sql
-- The CGWB source reuses station names across distinct coordinates: 398 names,
-- 415 real stations. The natural key is the triple, NOT the name.
CREATE UNIQUE INDEX ON monitoring_stations (name, ST_SnapToGrid(location::geometry, 0.000001));
```

**`groundwater_level_readings`**

```sql
CREATE TABLE groundwater_level_readings (
  station_id   UUID NOT NULL REFERENCES monitoring_stations(id),
  recorded_at  TIMESTAMPTZ NOT NULL,
  level_m_bgl  NUMERIC(7,3) NOT NULL,
  season       TEXT,                                -- Jan/May/Aug/Nov campaign
  source       TEXT NOT NULL DEFAULT 'cgwb',        -- cgwb | sensor | manual
  quality_flag TEXT NOT NULL,                       -- measured | interpolated
  PRIMARY KEY (station_id, recorded_at)             -- collapses the 1,238 dupes
);
CREATE INDEX ON groundwater_level_readings USING BRIN (recorded_at);
```

`quality_flag` is **required, not optional**: the pipeline already distinguishes measured CGWB
campaign months from interpolated ones, and the portal must not launder that distinction.

**`dataset_versions`** — the citable provenance spine, **as shipped in `0007`**. No `sha256` or
`row_count`: those stay in `data_sources`, per §5.2(a).

```sql
CREATE TABLE dataset_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label         TEXT NOT NULL UNIQUE,              -- 'CGWB-WATERLEVEL-JH-v1'
  source_org    TEXT NOT NULL,                     -- CGWB | GSI | IAEA | NRC
  citation      TEXT NOT NULL,
  n_supporting  INTEGER,   -- e.g. 9 for the Texas uranium source term
  caveat        TEXT,      -- surfaces small-n and known defects honestly
  is_current    BOOLEAN NOT NULL DEFAULT true,
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`n_supporting` and `caveat` are why the table exists. The uranium source term rests on **9
measurements from 7 mines**, and a portal rendering "15,180 ppb" to five significant figures without
saying so is misleading by omission. The five registered datasets and their caveats:

| label | source | n | caveat |
|---|---|---|---|
| `CGWB-WATERLEVEL-JH-v1` | CGWB | 8,345 | 1,238 duplicate `(station, date)` pairs collapsed; station names not unique (398 names, 415 stations) |
| `CGWB-WATERQUALITY-JH-v1` | CGWB | 397 | one sample per well; seasonal and spatial variation inseparable |
| `JH-AQUIFER-v1` | CGWB | 23 | regional averages, not site-specific values |
| `JH-ADMIN-BLOCK-v1` | GSI / SoI | 264 | — |
| `JH-ADMIN-DISTRICT-v1` | GSI / SoI | 24 | — |

The station-name caveat is carried in the data itself, not only in this document, so a query that
joins on name meets the warning where it happens.

### 5.4 Dataset → table mapping

Row counts are **as actually loaded**, not as they appear in the source file.

| Dataset on disk | Target table | Loaded |
|---|---|---|
| `District_Boundary_JH.geojson` | `districts` | 24 |
| `Sub_District_Boundary_JH.geojson` | `blocks` | 264 |
| `Aquifers_Jharkhand.geojson` | `aquifers` | 23 |
| `cgwb_waterlevel_jharkhand.csv` (9,583 rows) | `monitoring_stations` + `groundwater_level_readings` | **415 / 8,345** (§1.4a) |
| `waterQuality_jharkhand.csv` | `monitoring_wells` + `water_samples` | 397 / 397 |
| `jharkhand_rivers.geojson` | `rivers` | 4,577 |
| `jharkhand_lineaments.geojson` | `lineaments` | 1,889 |
| `Jharkhand Ore/*.csv`, `udepo_*.xlsx` | `ore_deposits` | 7 + belt |
| `naquim_reference/naquim_vertical.csv` | `naquim_profiles` | 24 |
| Texas ISR chemistry | `reference_isr_records` | 9 EOM / 7 mines |
| DEM, `.npz` field artifacts | Object storage + `dataset_files` checksums | — |

---

## 6. Target architecture

```
                        ┌──────────────────────────┐
   Browser  ──HTTPS──►  │  API Gateway (FastAPI)   │
   React SPA            │  auth · RBAC · limits    │
                        │  audit · caching         │
                        └────┬──────────┬──────────┘
                             │          │
                ┌────────────▼──┐   ┌───▼─────────────────┐
                │ Core Service  │   │ Simulation Service  │
                │ sites, geo,   │   │ ml_pipeline (as-is) │
                │ monitoring,   │   │ physics + surrogate │
                │ alerts, users │   │ NO public exposure  │
                └───┬───────┬───┘   └───┬─────────────────┘
                    │       │           │
        ┌───────────▼─┐ ┌───▼────┐ ┌────▼──────────┐
        │ PostgreSQL  │ │ Redis  │ │ Object store  │
        │ PostGIS     │ │ cache  │ │ DEM, .npz,    │
        │ (seeded)    │ │ [NEW]  │ │ artifacts     │
        └─────────────┘ └────────┘ └───────────────┘
```

**Key decision: `ml_pipeline/` is never exposed directly.** It becomes an internal service behind the
gateway, keeping its own test suite and release cadence; the gateway owns auth, limits and audit. Its
in-process rate limiter (240/min token bucket) stays as defence in depth, not as the primary control.

**Redis is new infrastructure.** It does not exist in this checkout — v2.0's diagram implied it was
already there. It is worth adding for response caching and the alert queue, but it is a **new
deployment dependency**, and P0–P4 can ship without it using the existing in-process cache. Defer it
to P7 with the alerts loop.

**Corollary:** the legacy simulation stub is **deleted**, not deprecated. Leaving a second, worse
physics path reachable is the failure mode §1.3 describes.

---

## 7. The CPS story — stated honestly

The proposal commits to Cyber-Physical Systems: *"environmental sensors, real-time data streams and
machine learning in a unified monitoring framework… a closed-loop system."* That is not built, and the
design must say so to TEXMiN reviewers rather than imply otherwise.

| CPS element | Status |
|---|---|
| Sensor hardware | **Does not exist.** No sensor is deployed |
| Real-time ingest path | **Schema-ready, unfed.** `sensors` / `sensor_readings` are designed; `source` already distinguishes `cgwb` \| `sensor` \| `manual` |
| Data → ML → prediction | **Built** — but on historical CGWB campaigns (4/yr), not live streams |
| Threshold → alert → acknowledgement | **Designed** (§3.3, §4.1) — this is the closed loop, and it works on manual/CGWB data today |
| Closed-loop actuation | **Out of scope.** The system advises; it does not control pumps |

**The honest framing:** the portal is a CPS-*ready* decision-support system whose sensing layer is
currently a 415-station manual monitoring network. Swapping a sensor feed into `sensor_readings`
requires no model change. Claiming a live CPS loop today would be the same over-claim the pipeline
audits spent three rounds removing.

---

## 8. Known limitations carried into the product

Stated plainly, because the portal must not present them as solved:

1. **No ISR operates in Jharkhand.** Every simulation is hypothetical. Schema, API and UI enforce it.
2. **The uranium source term rests on 9 measurements from 7 mines**, surfaced via
   `dataset_versions.n_supporting`.
3. **Radium's ML point estimate fails the project's own R² ≥ 0.60 gate** — verified in the deployed
   `metrics.json`: migration **0.516**, compliance **0.431** — because its labels are a point mass
   (81.8 % exact zeros). **Its uncertainty bands remain adequately covered** (0.891–0.986). Product
   rule: expose radium as *analytical value + band*, never as a standalone ML point estimate. Frozen
   and out of scope to fix.
4. **β, aperture, Dₑ, ω are foreign-analogue literature values** with zero Singhbhum measurements —
   part of the 12-entry `UNGROUNDED_PARAMETERS` register. Permanent until someone runs a packer or
   tracer test in the Singhbhum Shear Zone.
5. **Contaminated footprint is wellfield-dominated** (76–97 % disc), which is why it is renamed.
6. **The ISR excursion panel is 3 indicators (chloride, TDS, sulfate), 2-of-3.** It meets NUREG's
   minimum count but is **NUREG-1569-inspired screening, not a licensed programme** — the gap is
   named in every response.
7. **No sensors exist** (§7).
8. **The conformal band is validated, not guaranteed** (§4.3), and is void under `extrapolation`.
9. **Station names are not unique** (§1.4a). Any aggregation that groups by name will silently
   over-merge 17 stations.
10. **`analyst` no longer has ingest** (fixed 2026-08-12, roles.md D-2): the five `POST /ingest/*`
    routes are admin-only, because ingest replaces reference geography.
11. **District/block geometry was transposed until migration `0011`** (§1.5). Any analysis run
    against the database before that date used a well-to-block attribution that put all 397 wells in
    one block.
12. **A field observation is evidence, not authority.** Approved field data becomes authoritative in
    `water_samples` / `ore_observations`, but never reaches the surrogate (§3.4). A map value and a
    model input are different things here, deliberately.
13. **The portal and the engine can disagree, on purpose.** Approved data is authoritative here
    immediately but reaches `ml_pipeline` only via a deliberate admin sync (§3.6). The gap is shown
    as an amber state and a count on every run, never hidden.
14. ~~**`source_conc_C0` and `background_conc_Cb` are not envelope-checked**~~ — **RESOLVED
    2026-08-12** (§3.6). Both are now checked per species, with the surrogate-bypass case excluded.
    Consequence: runs at Jaduguda and Bhatin now correctly report an out-of-support baseline.

A portal that shows these honestly is more defensible to a regulator than one that hides them — and
this project's entire audit history is the argument for that.

---

## 9. Delivery plan

| Phase | Scope | Outcome |
|---|---|---|
| **P0** ✅ | Delete the legacy simulation stub; strip the dead `DataGen_ModelMVP` references (§1.3) | **Done.** One physics path. `POST /simulations` returns 501 until P3 |
| **P1** ✅ | `0006` drops the 5 orphans; `0007` adds `orgs`/`dataset_versions`/`audit_log`, links the load ledger, extends the role vocabulary; seed backfills all of it | **Done.** Schema matches reality, provenance spine populated (§5.2). `roles` tables deferred to P2 |
| **P2** ✅ | Auth hardening, 5 roles, RLS, audit; endpoint cull 55 → 44 | **Done.** Closed an unauthenticated privilege-escalation hole (§3.0); `0008` migrated `viewer` → `citizen`; `0009` added `owner_org_id` + policies. **RLS needs the `jaldrishti_app` role switch to take effect** — see §2. Rate limiting already existed (slowapi) |
| **P3** ✅ | Wire `POST /simulations` → `ml_pipeline`; scenarios; run persistence | **Complete.** Real physics replaces the 501; every run pins model card + artifact bundle + git SHA (§3.4); named scenarios with `/run` and `/compare` (§3.7) |
| **P4** ✅ | React shell: Login, Map Console, Site Registry, Review queue | **Done — MVP line reached.** Vite + React + TS on the existing design tokens; verified end to end in a browser against the live API (§4.7) |
| **P5** | Simulation Studio: bands, provenance drawer, **ISR Excursion panel** | Full official decision support |
| **P6** ◐ | **Citizen surface** (C1–C4) | **Partly done early**: `GET /public/risk/districts` and `/public/risk/{district_id}` ship the C1/C2 *data* (§3.5) to close roles.md D-3. The C3 alert subscription and C4 methods page remain |
| **P7** | Monitoring & Alerts loop (+ Redis) + Data Gap Report | Proposal deliverables complete |
| **P8** | Signed PDF reports, audit export, hardening | Production candidate |

**MVP line is P4.** P0–P4 is the defensible minimum: one physics engine, real data, role-based access,
a map an official can use. P5–P8 deepen it. If the fellowship timeline compresses, **cut from the
bottom, never from P0** — shipping two disagreeing simulation paths is worse than shipping fewer
screens.

**P0 is one day's work and removes a correctness bug.** It should land before anything else in this
plan, independent of whether the rest is scheduled.

---

## 10. Verification record

Every quantitative claim in this document was checked on 2026-08-11 against the working copy:

| Claim | How verified |
|---|---|
| 307 tests | `python -m pytest ml_pipeline/tests -q` |
| 55 backend endpoints | `grep -c '@router\.(get\|post\|put\|patch\|delete)' backend/app/api/v1/*.py` |
| 13 pipeline endpoints | `grep -c '@app\.' ml_pipeline/dashboard/server.py` |
| No Celery / Redis | absent from `backend/requirements.txt`; `app/tasks/` empty |
| Row counts, orphan tables | `psql groundwater_db` against `information_schema` |
| 398 names / 415 stations / 1,238 dupes | pandas over `cgwb_waterlevel_jharkhand.csv` |
| Radium 0.516 / 0.431; coverage 0.865 / 0.904 / 0.912 | `ml_pipeline/ml/artifacts/metrics.json` |
| Species split, 2-of-3 rule, 75–180 m ring | `ml_pipeline/config/parameters.py` |
| 4 dead `DataGen_ModelMVP` references | `grep -rn DataGen_ModelMVP backend/ ml_pipeline/` |
| P3 runs on the real engine | live run against `groundwater_db` as `jaldrishti_app`: completed in 4.6 s, provenance pinned |
| Approved field data does not move the model | `test_approving_field_data_does_not_change_the_model_output` — metrics byte-identical across an approved 9,999 ppb reading |
| ML artifacts untouched by backend work | all 16 sha256 digests match `backend/tests/ml_artifact_hashes.json` |
| Geometry fix | `ST_XMin/XMax` on `districts` before (21.97..25.35) and after (83.33..87.92) migration `0011` |
| Ore sync changes what the engine resolves | `ore_zone_at(85.20, 23.80)`: `none` → `deposit` after a sync, `none` again after restore |
| `origin` tags round-trip | both files re-read as `['added', 'original']` |
| Sync leaves ML artifacts alone | `retrain_required: false`; all 16 artifact digests unchanged |
| C0/Cb envelope guard | 25 new tests; 4/32 real pin-species combinations flag, all genuine; artifacts unchanged |
| Fix is additive | `ml_pipeline` 307 → 332 passing, backend 105 unchanged, end-to-end audit 43/44 (same documented radium miss) |

If a number here ever disagrees with the code, **the code is right and this document is stale.**
