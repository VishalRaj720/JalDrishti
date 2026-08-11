# JalDrishti — Product Design: Frontend, Backend API & Database

**Version:** 2.0 · **Date:** 2026-08-11 · **Status:** Design for stakeholder review
**Supersedes:** v1.0 (2026-08-05), written before the `review3.md` remediation
**Programme:** TEXMiN–BIT Sindri Mining CPS CoE · *Smart Water Monitoring: ML and CPS for Safe & Sustainable Mining*

**Two audiences, by name:**
1. **Government officials** — CGWB / SPCB / district administration, who need to know which aquifers
   are vulnerable to an ISR process and what the monitoring network is reporting.
2. **Common users** — residents of Jharkhand mining districts, who need a plain answer to
   *"is the groundwater near me at risk, and who do I tell?"*

Everything below is role-based around those two, plus the technical and field staff who serve them.

---

## 0. What this document decides

The repository contains **three disconnected parts**: a legacy CRUD backend, a scientifically
validated simulation engine (`ml_pipeline/`), and a static frontend mock. None is a product an
authority can be handed, and — critically — **they disagree with each other about the physics**
(§1.3). This document specifies one system: which APIs survive, the database behind them, the screens
each audience actually uses, and the access control that makes it safe to expose.

**One-line product statement.** *A groundwater-vulnerability portal for Jharkhand: for officials, where
a hypothetical ISR plume would travel, who is downstream, and what the monitoring network reports; for
residents, whether their area is at risk and what that means — with every number carrying its
provenance and uncertainty.*

The word **hypothetical** is load-bearing and appears on every simulation surface. No ISR operation
exists in Jharkhand. This is a screening and preparedness tool, not a permitting instrument.

### 0.1 What changed from v1.0

v1.0 was written on 2026-08-05. The `review3.md` remediation (merged as PR #6) changed the facts it
was built on. Corrections:

| v1.0 said | Reality now |
|---|---|
| `ml_pipeline`: 222 tests | **260 tests** |
| `ml_pipeline` has "no auth, **no rate limiting**, no database" | Rate limiting (240/min token bucket) and `ETag`/`Cache-Control` on all five overlay endpoints **now exist**. No auth and no database remain true |
| 57 legacy + 12 pipeline endpoints | **55 legacy + 14 pipeline** |
| Risk 3: *"until the field-resampled gate runs, say 80% calibrated on modelled scenarios"* | **The gate has run and passed** (0.865 / 0.904 / 0.913 on a held-out serving-distribution batch). The UI claim can be stronger — see §4.3 |
| — | The pipeline gained the **NUREG-1569 ISR excursion test**, a configurable monitor ring, `/api/assumptions`, and effective-retardation reporting. v1.0 knows about none of them. §4.2 fixes that |

**Three gaps v1.0 had, now addressed:** the ISR excursion framework (§4.2), the common-user audience
(§4.4), and honesty about the CPS sensor path (§7).

---

## 1. Current state — verified assessment

### 1.1 What exists

| Component | State | Verdict |
|---|---|---|
| `ml_pipeline/` | **Production-grade.** 260 tests, exact-solution-benchmarked transport kernel, conformal bands validated on the serving distribution, drift monitor, 12-entry assumption register | **Keep — this is the crown jewel.** Frozen; see `ML_PIPELINE_READINESS.md` |
| `backend/` | 55 endpoints, JWT auth, 3 roles, PostGIS models, Celery, Alembic | **Keep the plumbing, replace the science** (§1.3) |
| `frontend/JalDrishti.html` + `*.jsx` | Static mock, no `package.json`, no build. Hexagon districts, hardcoded risk badges | **Keep the visual language, rebuild the app** |
| `frontend/ml_pipeline/` | Vanilla JS + Leaflet, genuinely functional, real physics | **Absorb as the Simulation Studio** |

### 1.2 The visual language worth keeping

From `frontend/screenshots/01-map-final2.png` — stakeholders have already seen this identity:

- Map-first console, dark map canvas with a **light left rail**, teal primary, green→amber→red risk ramp
- Left rail: search → layer toggles → entity list with risk badges
- Top nav: Map · Analytics · Data Ingest · Users, with a role chip
- Legend bottom-left, zoom bottom-right

**Keep all of it.** Replace the hexagons with the real 24-district GeoJSON and the hardcoded badges
with computed indices.

### 1.3 The core problem — worse than v1.0 stated

v1.0 said the two halves "cannot talk". Verified: they also **contradict each other**.
`backend/app/services/simulation.py` runs a 9-step pipeline in which:

- step 2 sets the groundwater gradient with **`random.uniform(30, 90)`** — a literal random direction;
- step 5 calls `ml_prediction.py`, whose own docstring labels it a **`month1_placeholder`**, not a
  trained model;
- step 6 computes area from a **hardcoded** `rx = 50·√365`, `ry = 10·√365` stub.

Meanwhile `ml_pipeline` derives the gradient from a plane fit over 398 real CGWB stations and solves
Domenico transport with conformal bands. **Two endpoints in one product would return different,
incompatible answers for the same site, and the worse one is the one the legacy API exposes.**

This makes §3 (rewire simulations to `ml_pipeline`) not an enhancement but a **correctness fix**.

Also stale and needing cleanup: `backend/app/services/ml_prediction.py`, `simulation.py`,
`backend/requirements.txt` and `ml_pipeline/README.md` still reference **`DataGen_ModelMVP/`**, a
directory that no longer exists.

---

## 2. Roles — built around the two stated audiences

v1.0 proposed seven roles including `operator` (a "UCLL-class mine operator" with CRUD over its own
sites). That contradicts the product's own premise: **no ISR operates in Jharkhand**, so there is no
operator to onboard. Five roles, mapped to real people:

| Role | Who | Can |
|---|---|---|
| `admin` | BIT Sindri / TEXMiN system owner | Everything incl. ingest, dataset promotion, user management |
| `regulator` | **CGWB / SPCB / district officer** — the primary government user | Read every site, publish/archive, export signed reports, resolve alerts, see raw coordinates |
| `analyst` | Technical staff, researchers | Run and save scenarios, no publish, no ingest |
| `field_officer` | Station/well data collectors | Upload readings and samples only — **the CPS data path** |
| `citizen` | **Common user** (registered or anonymous) | District/block risk view, plain-language explanations, alerts for a subscribed area. **No precise site coordinates, no simulation controls** |

The backend today has only `admin`, `analyst`, `viewer` — `viewer` is renamed and re-scoped to
`citizen`, and `regulator` / `field_officer` are added.

**Why citizens cannot see exact ISR coordinates.** Every site is hypothetical. Publishing a precise
point for a *speculative* mine next to a named village invites it being read as a real plan, and
risks land-value and panic effects the project has no mandate to cause. Citizens get **block-level
aggregation**; regulators get points. This is a deliberate design constraint, not a technical limit.

Enforced with **row-level security in Postgres** keyed on `owner_org_id` and role, not only in
application code — so a service bug cannot leak site detail to a citizen session.

---

## 3. API audit — keep, delete, add

**55 legacy + 14 pipeline = 69 endpoints today → ~40 in the target design.**

### 3.1 DELETE — 22 endpoints

| Endpoint(s) | Why it goes |
|---|---|
| `POST/PUT/DELETE /aquifers`, `/blocks`, `/districts` (9) | Reference geography from CGWB/GSI. Not user-editable content — editing it via API silently forks the scientific basis of every simulation. Load through versioned ingest instead |
| `POST /users`, `PUT /users/{id}`, `DELETE /users/{id}` (3) | Superseded by invitation + role assignment. A plaintext-password create endpoint is the wrong primitive for a government portal |
| `GET /global_blocks`, `/global_monitoring`, `/global_monitoring/count` (3) | Undocumented duplicates of the scoped equivalents. Two code paths for one entity is exactly how the `ml_pipeline` species bug happened |
| `POST /auth/token` (1) | Duplicate of `POST /auth/login` |
| `GET /` root banner (1) | Replaced by the SPA |
| `POST /api/drift/reset` (1) | Debug affordance → admin-only, off the public API |
| `GET /api/aquifers`, `/boundary`, `/ore`, `/rivers` in `ml_pipeline` (4) | Duplicated by the unified geography service. The pipeline should not serve map layers |

### 3.2 KEEP — with changes

| Endpoint | Change required |
|---|---|
| `POST /auth/login`, `/logout`, `GET /auth/me` | Add refresh tokens; MFA hook for `regulator` |
| `GET /districts`, `/districts/geojson`, `/blocks`, `/aquifers` | Read-only; `?simplify=`, `ETag`/`Cache-Control` |
| `GET/POST/PUT/DELETE /isr_points` | **The heart of the product** — the hypothetical-site registry. Add `status`, `owner_org_id`, soft delete |
| `POST /simulations/{isr_id}`, `GET /simulations/{sim_id}` | **Rewire to `ml_pipeline`.** Delete the random-gradient stub and `month1_placeholder` outright (§1.3) |
| `GET/POST /monitoring_stations`, `/{id}/readings` | Keep — the CPS data path |
| `GET /monitoring_wells`, `GET/POST /water_samples` | Keep |
| `POST /ingest/*` (5), `GET /ingest/data-quality-report` | Keep, admin-only. The data-quality report is a named proposal deliverable |
| `GET /health` | Extend to report ML artifact + DB + queue status |
| `POST /api/predict`, `GET /api/pin`, `/api/flow_field`, `/api/strike_field`, `/api/drift`, `/api/assumptions` | Keep behind the gateway with auth + limits |

### 3.3 ADD — new endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/refresh` | Token rotation |
| `GET /orgs`, `POST /orgs/{id}/invite` | CGWB, SPCB, BIT Sindri as separate orgs |
| `GET /me/permissions` | Frontend renders from server truth, never guesses |
| `GET /sites/{id}/risk` | Composite risk index — what the map colours by |
| `GET /sites/{id}/downstream` | Receptors at risk: villages, wells, river reaches |
| `GET /sites/{id}/excursion` | **NEW in v2.0** — the NUREG-1569 indicator excursion state (§4.2) |
| `POST /scenarios`, `GET /scenarios/{id}`, `POST /scenarios/{id}/compare` | Saved, named, shareable scenarios — **what makes this a product rather than a calculator** |
| `GET /public/risk/{district_id}` | **NEW in v2.0** — the citizen-facing aggregate, no auth, heavily cached |
| `GET /alerts`, `POST /alerts/rules`, `POST /alerts/{id}/ack` | CPS loop: breach → alert → acknowledgement |
| `GET /reports/{site_id}.pdf` | Signed, dated regulator report with provenance appendix |
| `GET /audit` | Who ran what, when — non-negotiable for a government portal |

---

## 4. Frontend design

**Stack:** React 18 + TypeScript + Vite · **Leaflet** (as today) · TanStack Query · Tailwind +
shadcn/ui · Recharts.

**Map library decision, revised from v1.0.** v1.0 mandated MapLibre GL vector tiles on a 60 fps
argument. That is premature: `frontend/ml_pipeline/app.js` already renders 23 aquifer polygons, 4,577
river reaches (decimated) and plume contours on Leaflet acceptably, and MapLibre requires standing up
a tile server (tippecanoe / pg_tileserv) — real infrastructure for a UG fellowship prototype. **Ship
on Leaflet; revisit MapLibre only if the 260-block layer measurably drops frames.** Do not pay
infrastructure cost for a hypothetical.

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

### 4.2 NEW — the ISR Excursion panel

**This is the single most product-relevant thing the pipeline gained, and v1.0 predates it.**

A real ISR operation is not judged by "did uranium exceed a drinking-water limit". US NRC NUREG-1569
§5.7.8.3 defines an excursion as **two or more conservative indicator parameters exceeding their
upper control limits** at a perimeter monitoring well — and p.137 explicitly rejects uranium as an
indicator *"because … it may be retarded by reducing conditions in the aquifer."*

The pipeline now implements this, and it **fires earlier than the health-limit breach** — verified at
Jaduguda, gradient 0.005, t = 20 yr: excursion DECLARED while the BIS uranium breach still reads NO.

**Product implication.** For a government official monitoring aquifer vulnerability, this is the
headline, because it is the metric a regulator actually acts on. The panel shows:

- **Excursion status** (`DECLARED` / `none`) and the `n/2` indicator count
- Per indicator (TDS, sulfate): ring concentration vs its upper control limit
- **The panel shortfall, always visible** — a licensed programme uses ≥3 indicators; this model
  carries 2, because chloride and total alkalinity have no ISR source term in the available data
- The monitor ring distance and its NUREG-licensed range (75–180 m)

It sits **next to, not instead of,** the BIS/WHO health-limit result. They answer different questions
and the difference is itself informative.

### 4.3 NEW — how to state the uncertainty claim

v1.0's Risk 3 instructed the UI to say *"80% calibrated on modelled scenarios"* because the
field-resampled gate had never run. **It has now run and passed** on a held-out batch drawn from the
real flow field (median gradient 0.94× the field, vs the training set's 1.34×).

The UI may therefore say: **"80% conformal band, validated on a held-out sample of real Jharkhand
hydrogeology."** It must **not** say "80% guaranteed" — the guarantee is conditional on the parameter
distribution and is void wherever `extrapolation` is non-empty.

### 4.4 NEW — the citizen surface

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

### 4.5 Non-negotiable UI rules

From the audit history, to stop the portal over-claiming:

1. **No bare point estimates** on official surfaces. Every predicted quantity renders with its band or
   an explicit "deterministic — no band" label.
2. **Extrapolation is loud.** Outside the trained envelope, cards turn amber and state that the
   conformal guarantee is void and the analytical engine is serving.
3. **Provenance on hover** for every input, carrying `n` where small (the Texas n = 9 case).
4. **"Total Vulnerable Area" is relabelled** to **"Contaminated Footprint (wellfield + migrating
   plume)"** with the split shown — it is 76–97% leach-zone disc.
5. **Migration reads "no measurable migration"** below map resolution, never a misleading `0`.
6. **The hypothetical premise is never more than one glance away** — and on citizen screens it is in
   the first paragraph.

### 4.6 Frozen constraints inherited from `ml_pipeline`

These come from `ML_PIPELINE_READINESS.md` §7 and **must not be redesigned around**:

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

---

## 5. Database design

**PostgreSQL 16 + PostGIS 3.4.** PostGIS is already in use.

**TimescaleDB removed from the MVP, revised from v1.0.** v1.0 added it for "time-series that will grow
continuously under CPS". The actual load is **9,583 historical rows**, growing four campaigns a year.
Plain Postgres with a BRIN index on `recorded_at` handles that for years, and every added extension is
a deployment dependency the host institution has to support. **Adopt TimescaleDB only when real sensor
streams exist** (§7) — the schema below is compatible either way.

### 5.1 Schema map

```
┌─ IDENTITY ────────────────────────────────────────────────┐
│ orgs ──< users ──< user_roles >── roles ──< permissions   │
│                      └──< api_keys        audit_log        │
└────────────────────────────────────────────────────────────┘
┌─ REFERENCE GEOGRAPHY (read-only, versioned) ──────────────┐
│ districts ──< blocks ──< aquifers                          │
│ rivers · lineaments · ore_deposits · naquim_profiles       │
│ dataset_versions ──< dataset_files                         │
└────────────────────────────────────────────────────────────┘
┌─ MONITORING (time-series) ────────────────────────────────┐
│ monitoring_stations ──< groundwater_readings               │
│ monitoring_wells    ──< water_samples                      │
│ sensors             ──< sensor_readings   [empty; see §7]  │
└────────────────────────────────────────────────────────────┘
┌─ SIMULATION ──────────────────────────────────────────────┐
│ isr_sites ──< scenarios ──< simulation_runs                │
│                               ├──< run_metrics             │
│                               ├──< run_geometry (PostGIS)  │
│                               └──< run_provenance          │
└────────────────────────────────────────────────────────────┘
┌─ DECISION SUPPORT ────────────────────────────────────────┐
│ alert_rules ──< alerts ──< alert_acknowledgements          │
│ risk_snapshots · reports · citizen_subscriptions           │
└────────────────────────────────────────────────────────────┘
```

### 5.2 Tables that matter most

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

**`groundwater_readings`**

```sql
CREATE TABLE groundwater_readings (
  station_id   UUID NOT NULL REFERENCES monitoring_stations(id),
  recorded_at  TIMESTAMPTZ NOT NULL,
  level_m_bgl  NUMERIC(7,3) NOT NULL,
  season       TEXT,                                -- Jan/May/Aug/Nov campaign
  source       TEXT NOT NULL DEFAULT 'cgwb',        -- cgwb | sensor | manual
  quality_flag TEXT NOT NULL,                       -- measured | interpolated
  PRIMARY KEY (station_id, recorded_at)
);
CREATE INDEX ON groundwater_readings USING BRIN (recorded_at);
```

`quality_flag` is **required, not optional**: the pipeline already distinguishes measured CGWB campaign
months from interpolated ones, and the portal must not launder that distinction.

**`dataset_versions`** — the provenance spine.

```sql
CREATE TABLE dataset_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label         TEXT NOT NULL,                     -- 'CGWB-2013-2021-v1'
  source_org    TEXT NOT NULL,                     -- CGWB | GSI | IAEA | NRC
  citation      TEXT NOT NULL,
  sha256        TEXT NOT NULL,
  row_count     INTEGER,
  n_supporting  INTEGER,   -- e.g. 9 for the Texas uranium source term
  caveat        TEXT,      -- surfaces small-n honestly
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`n_supporting` and `caveat` exist because the uranium source term rests on **9 measurements from 7
mines**, and a portal rendering "15,180 ppb" to five significant figures without saying so is
misleading by omission.

### 5.3 Dataset → table mapping

| Dataset on disk | Target table | Rows |
|---|---|---|
| `District_Boundary_JH.geojson` | `districts` | 24 |
| `Sub_District_Boundary_JH.geojson` | `blocks` | ~260 |
| `Aquifers_Jharkhand.geojson` | `aquifers` | 23 |
| `cgwb_waterlevel_jharkhand.csv` | `monitoring_stations` + `groundwater_readings` | 398 / 9,583 |
| `waterQuality_jharkhand.csv` | `monitoring_wells` + `water_samples` | 397 |
| `jharkhand_rivers.geojson` | `rivers` | 4,577 |
| `jharkhand_lineaments.geojson` | `lineaments` | 1,889 |
| `Jharkhand Ore/*.csv`, `udepo_*.xlsx` | `ore_deposits` | 7 + belt |
| `naquim_reference/naquim_vertical.csv` | `naquim_profiles` | 24 |
| `Real_dataset/` (Texas ISR) | `reference_isr_records` | 9 EOM / 7 mines |
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
        │             │ │ queue  │ │ artifacts     │
        └─────────────┘ └────────┘ └───────────────┘
```

**Key decision: `ml_pipeline/` is never exposed directly.** It becomes an internal service behind the
gateway, keeping its own test suite and release cadence; the gateway owns auth, limits and audit. Its
in-process rate limiter stays as defence in depth, not as the primary control.

**Corollary:** the legacy simulation stub is **deleted**, not deprecated. Leaving a second, worse
physics path reachable is the failure mode §1.3 describes.

---

## 7. The CPS story — stated honestly

The proposal commits to Cyber-Physical Systems: *"environmental sensors, real-time data streams and
machine learning in a unified monitoring framework… a closed-loop system."* v1.0 implied this was
built. It is not, and the design must say so to TEXMiN reviewers rather than imply otherwise.

| CPS element | Status |
|---|---|
| Sensor hardware | **Does not exist.** No sensor is deployed |
| Real-time ingest path | **Schema-ready, unfed.** `sensors` / `sensor_readings` exist; `source` already distinguishes `cgwb` \| `sensor` \| `manual` |
| Data → ML → prediction | **Built** — but on historical CGWB campaigns (4/yr), not live streams |
| Threshold → alert → acknowledgement | **Designed** (§3.3, §4.1) — this is the closed loop, and it works on manual/CGWB data today |
| Closed-loop actuation | **Out of scope.** The system advises; it does not control pumps |

**The honest framing:** the portal is a CPS-*ready* decision-support system whose sensing layer is
currently a 398-station manual monitoring network. Swapping a sensor feed into `sensor_readings`
requires no model change. Claiming a live CPS loop today would be the same over-claim the pipeline
audits spent three rounds removing.

---

## 8. Known limitations carried into the product

Stated plainly, because the portal must not present them as solved:

1. **No ISR operates in Jharkhand.** Every simulation is hypothetical. Schema, API and UI enforce it.
2. **The uranium source term rests on 9 measurements from 7 mines**, surfaced via
   `dataset_versions.n_supporting`.
3. **Radium's ML point estimate fails the project's own R² ≥ 0.60 gate** (migration 0.516, compliance
   0.431) because its labels are a point mass — 81.8% exact zeros. **Its uncertainty bands remain
   adequately covered** (0.891–0.986). Product rule: expose radium as *analytical value + band*, never
   as a standalone ML point estimate. This is frozen and out of scope to fix.
4. **β, aperture, Dₑ, ω are foreign-analogue literature values** with zero Singhbhum measurements.
   Permanent until someone runs a packer or tracer test in the Singhbhum Shear Zone.
5. **Contaminated footprint is wellfield-dominated** (76–97% disc), which is why it is renamed.
6. **The ISR excursion panel uses 2 of the ≥3 regulatory indicators** — always disclosed.
7. **No sensors exist** (§7).
8. **The conformal band is validated, not guaranteed** (§4.3), and is void under `extrapolation`.

A portal that shows these honestly is more defensible to a regulator than one that hides them — and
this project's entire audit history is the argument for that.

---

## 9. Delivery plan

| Phase | Scope | Outcome |
|---|---|---|
| **P0** | Delete the legacy simulation stub + `DataGen_ModelMVP` references | No contradictory physics path |
| **P1** | Postgres schema + migrations; load all `Datasets/` with `dataset_versions` | Real data, versioned, queryable |
| **P2** | Gateway: auth, 5 roles, RLS, rate limits, audit; delete the 22 dead endpoints | Safe to expose |
| **P3** | Wire `POST /simulations` → `ml_pipeline`; scenarios; run persistence | Reproducible runs |
| **P4** | React shell: Login, Map Console, Site Registry | ◀ **MVP — demoable to stakeholders** |
| **P5** | Simulation Studio: bands, provenance drawer, **ISR Excursion panel** | Full official decision support |
| **P6** | **Citizen surface** (C1–C4) | Second audience served |
| **P7** | Monitoring & Alerts loop + Data Gap Report | Proposal deliverables complete |
| **P8** | Signed PDF reports, audit export, hardening | Production candidate |

**MVP line is P4.** P0–P4 is the defensible minimum: one physics engine, real data, role-based access,
a map an official can use. P5–P8 deepen it. If the fellowship timeline compresses, **cut from the
bottom, never from P0** — shipping two disagreeing simulation paths is worse than shipping fewer
screens.
