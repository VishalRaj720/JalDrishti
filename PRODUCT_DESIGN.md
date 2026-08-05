# JalDrishti — Product Design: Frontend, Backend API & Database

**Version:** 1.0 · **Date:** 2026-08-05 · **Status:** Design for stakeholder review
**Programme:** TEXMiN–BIT Sindri Mining CPS CoE · *Smart Water Monitoring: ML and CPS for Safe & Sustainable Mining*
**Audience:** CGWB / SPCB regulators, UCIL-class mine operators, TEXMiN reviewers, district administration

---

## 0. What this document decides

The repository currently contains **three disconnected halves**: a legacy CRUD backend (57 endpoints,
PostgreSQL + PostGIS), a scientifically validated simulation engine (`ml_pipeline/`, 12 endpoints, no
auth, no database), and two unrelated frontends. None of them is a product an authority can be handed.

This document specifies one system: which APIs survive, which are deleted, the database that backs
them, the screens authorities actually use, and the access control that makes it safe to expose.

**One-line product statement.** *A regulator-facing portal for tracking hypothetical ISR sites in
Jharkhand: where a contaminant plume would travel, who is downstream, and what the monitoring network
is currently reporting — with every number carrying its provenance and uncertainty.*

The word **hypothetical** is load-bearing and appears in the UI on every simulation surface. No ISR
operation exists in Jharkhand. This is a screening and preparedness tool, not a permitting instrument.

---

## 1. Current state — honest assessment

### 1.1 What exists

| Component | State | Verdict |
|---|---|---|
| `ml_pipeline/` | **Production-grade.** 222 tests, exact-solution-benchmarked transport kernel, conformal uncertainty bands, drift monitor | **Keep — this is the crown jewel** |
| `backend/` (legacy) | 57 endpoints, full CRUD, JWT auth, PostGIS models, Celery, Alembic migrations | **Keep selectively** — good bones, ~40% dead weight |
| `frontend/JalDrishti.html` + `*.jsx` | Static mock: dark theme, hexagon districts, fake risk badges. Not wired to real geometry | **Keep the design language, rebuild the app** |
| `frontend/ml_pipeline/` | Vanilla JS + Leaflet, genuinely functional, real physics | **Absorb into the new app as the Simulation Studio** |

### 1.2 The visual language worth keeping

From `frontend/screenshots/01-map-final2.png` — the existing mock already establishes the right
identity, and stakeholders have seen it:

- Dark map-first console, teal/cyan primary (`#0d9488` family), amber→red risk ramp
- Left rail: search → layer toggles → entity list with risk badges
- Top nav: Map · Analytics · Data Ingest · Users, with a role chip
- Legend pinned bottom-left, zoom/context bottom-right

**Keep all of it.** Replace the hexagons with real GeoJSON, the fake badges with computed indices.

### 1.3 The core problem

The two halves cannot talk. `ml_pipeline/dashboard/server.py` has **no authentication, no rate
limiting, no database, and no concept of a user or a site** — `review2.md` V-6 flagged this. The
legacy backend has all of those but knows nothing about the physics engine. Neither is deployable
alone.

---

## 2. API audit — keep, delete, add

**57 legacy + 12 pipeline = 69 endpoints today → 41 in the target design.**

### 2.1 DELETE — 22 endpoints

| Endpoint(s) | Why it goes |
|---|---|
| `POST/PUT/DELETE /aquifers`, `/blocks`, `/districts` (9 endpoints) | Districts, blocks and aquifer polygons are **reference geography from CGWB/GSI**. They are not user-editable content. Editing them via API silently forks the scientific basis of every simulation. Load them through the versioned ingest pipeline instead. |
| `POST /users`, `PUT /users/{id}`, `DELETE /users/{id}` (3) | Superseded by an invitation + role-assignment flow (§5). Direct user creation with a plaintext password field is the wrong primitive for a government portal. |
| `GET /global_blocks`, `GET /global_monitoring`, `GET /global_monitoring/count` (3) | Undocumented duplicates of the scoped equivalents. Two code paths returning the same entity is how the ml_pipeline species bug happened. |
| `POST /auth/token` (1) | Duplicate of `POST /auth/login`. Keep one. |
| `GET /` root banner (1) | Replaced by the SPA. |
| `POST /api/drift/reset` (1) | Debug affordance. Moves behind admin, not public API. |
| `GET /api/aquifers`, `/api/boundary`, `/api/ore`, `/api/rivers` in **ml_pipeline** (4) | Duplicated by the unified geography service. The pipeline should not serve map layers. |

### 2.2 KEEP — with changes

| Endpoint | Change required |
|---|---|
| `POST /auth/login`, `/logout`, `GET /auth/me` | Add refresh tokens, MFA hook for regulator role |
| `GET /districts`, `/districts/geojson`, `/blocks`, `/aquifers` | Read-only. Add `?simplify=` + `ETag`/`Cache-Control` (review2.md V-6: 0.48 MB uncached today) |
| `GET/POST/PUT/DELETE /isr_points` | **This is the heart of the product** — the hypothetical-site registry. Add `status`, `owner_org_id`, soft delete |
| `GET /isr_points/{id}/simulations` | Keep as-is |
| `POST /simulations/{isr_id}`, `GET /simulations/{sim_id}` | Rewire to call `ml_pipeline`, not the legacy stub |
| `GET/POST /monitoring_stations`, `/{id}/readings` | Keep. This is the CPS data path |
| `GET /monitoring_wells`, `GET/POST /water_samples` | Keep |
| `POST /ingest/*` (5), `GET /ingest/data-quality-report` | Keep, admin-only. The data-quality report is a proposal deliverable ("identify data gaps") |
| `GET /health` | Keep, extend to report ML artifact + DB + queue status |
| `POST /api/predict`, `GET /api/pin`, `/api/flow_field`, `/api/strike_field`, `/api/drift` | Keep, move behind the gateway with auth + rate limits |

### 2.3 ADD — 14 new endpoints

| Endpoint | Purpose |
|---|---|
| `POST /auth/refresh` | Token rotation |
| `GET /orgs`, `POST /orgs`, `POST /orgs/{id}/invite` | Multi-tenant: CGWB, SPCB, UCIL, BIT Sindri as separate orgs |
| `GET /me/permissions` | Frontend renders from server truth, never guesses |
| `GET /sites/{id}/risk` | Composite risk index (§4.4) — the number the map colours by |
| `GET /sites/{id}/downstream` | Receptors at risk: villages, wells, river reaches |
| `POST /scenarios`, `GET /scenarios/{id}`, `POST /scenarios/{id}/compare` | Saved, named, shareable simulation scenarios — **the feature that makes this a product rather than a calculator** |
| `GET /alerts`, `POST /alerts/rules`, `POST /alerts/{id}/ack` | CPS closed loop: threshold breach → alert → acknowledgement |
| `GET /reports/{site_id}.pdf` | Signed, dated regulator report with provenance appendix |
| `GET /audit` | Who ran what, when — non-negotiable for a government portal |

---

## 3. Database design

**PostgreSQL 16 + PostGIS 3.4 + TimescaleDB.** PostGIS is already in use; TimescaleDB is added
because groundwater readings and sensor streams are time-series with a 9,583-row historical base that
will grow continuously under CPS.

### 3.1 Schema map

```
┌─ IDENTITY ────────────────────────────────────────────────┐
│ orgs ──< users ──< user_roles >── roles ──< permissions   │
│                      │                                     │
│                      └──< api_keys        audit_log        │
└────────────────────────────────────────────────────────────┘
┌─ REFERENCE GEOGRAPHY (read-only, versioned) ──────────────┐
│ districts ──< blocks ──< aquifers                          │
│ rivers · lineaments · ore_deposits · naquim_profiles       │
│ dataset_versions ──< dataset_files                         │
└────────────────────────────────────────────────────────────┘
┌─ MONITORING (time-series) ────────────────────────────────┐
│ monitoring_stations ──< groundwater_readings  [hypertable] │
│ monitoring_wells    ──< water_samples         [hypertable] │
│ sensors             ──< sensor_readings       [hypertable] │
└────────────────────────────────────────────────────────────┘
┌─ SIMULATION ──────────────────────────────────────────────┐
│ isr_sites ──< scenarios ──< simulation_runs                │
│                               ├──< run_metrics             │
│                               ├──< run_geometry (PostGIS)  │
│                               └──< run_provenance          │
└────────────────────────────────────────────────────────────┘
┌─ DECISION SUPPORT ────────────────────────────────────────┐
│ alert_rules ──< alerts ──< alert_acknowledgements          │
│ risk_snapshots · reports                                   │
└────────────────────────────────────────────────────────────┘
```

### 3.2 Tables that matter most

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

**`simulation_runs`** — every execution is immutable and reproducible.

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
  extrapolation     TEXT[],                        -- envelope violations
  runtime_ms        INTEGER,
  created_by        UUID NOT NULL REFERENCES users(id),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`groundwater_readings`** — TimescaleDB hypertable.

```sql
CREATE TABLE groundwater_readings (
  station_id   UUID NOT NULL REFERENCES monitoring_stations(id),
  recorded_at  TIMESTAMPTZ NOT NULL,
  level_m_bgl  NUMERIC(7,3) NOT NULL,
  season       TEXT,                                -- Jan/May/Aug/Nov campaign
  source       TEXT NOT NULL DEFAULT 'cgwb',        -- cgwb | sensor | manual
  quality_flag TEXT,                                -- measured | interpolated
  PRIMARY KEY (station_id, recorded_at)
);
SELECT create_hypertable('groundwater_readings','recorded_at');
```

`quality_flag` is required, not optional: the pipeline already distinguishes measured CGWB campaign
months from interpolated ones, and the portal must not launder that distinction.

**`dataset_versions`** — the provenance spine.

```sql
CREATE TABLE dataset_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label         TEXT NOT NULL,                     -- 'CGWB-2013-2021-v1'
  source_org    TEXT NOT NULL,                     -- CGWB | GSI | IAEA | USGS
  citation      TEXT NOT NULL,
  sha256        TEXT NOT NULL,
  row_count     INTEGER,
  n_supporting  INTEGER,   -- e.g. 9 for the Texas uranium source term
  caveat        TEXT,      -- review2.md V-2: surfaces small-n honestly
  ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`n_supporting` and `caveat` exist because of `review2.md` V-2: the uranium source term rests on **9
measurements from 7 mines**, and a portal that renders "13,272 ppb" to four significant figures
without saying so is misleading by omission.

### 3.3 Dataset → table mapping

| Dataset on disk | Target table | Rows |
|---|---|---|
| `District_Boundary_JH.geojson` | `districts` | 24 |
| `Sub_District_Boundary_JH.geojson` | `blocks` | ~260 |
| `Aquifers_Jharkhand.geojson` | `aquifers` | 23 |
| `cgwb_waterlevel_jharkhand.csv` | `monitoring_stations` + `groundwater_readings` | 398 / 9,583 |
| `waterQuality_jharkhand.csv` | `monitoring_wells` + `water_samples` | 397 |
| `jharkhand_rivers.geojson`, HydroRIVERS | `rivers` | — |
| `jharkhand_lineaments.geojson` | `lineaments` | — |
| `Jharkhand Ore/*.csv`, `udepo_*.xlsx` | `ore_deposits` | 7 + belt |
| `naquim_reference/naquim_vertical.csv` | `naquim_profiles` | 24 |
| `Real_dataset/` (Texas ISR) | `reference_isr_records` | 13 / 17 |
| `jharkhand_glo30_dem.tif` | Object storage, not RDBMS | — |

Rasters and the `.npz` field artifacts stay on disk/S3 with checksums in `dataset_files`. Putting a
DEM in Postgres buys nothing.

---

## 4. Frontend design

**Stack:** React 18 + TypeScript + Vite · MapLibre GL (vector tiles, not Leaflet raster) · TanStack
Query · Tailwind + shadcn/ui · Recharts.

MapLibre replaces Leaflet because the portal renders 23 aquifer polygons + 260 blocks + river
networks + plume contours simultaneously; raster tiles and SVG overlays will not hold 60 fps at that
load, and `frontend/ml_pipeline/app.js` already shows strain.

### 4.1 Screens

**1 · Login** — org SSO, role displayed before entry.

**2 · Map Console** *(default landing)* — evolves the existing mock.
- Left rail: search → layer toggles (Districts, Blocks, Aquifers, ISR Sites, Plumes, Stations, Wells,
  Rivers, Ore, Flow field, Fracture strike) → entity list with computed risk badges
- Map: real GeoJSON, plume contours, compliance ring, ML envelope
- Right drawer on select: site summary, latest run, downstream receptors, "Open in Studio"
- **Every plume carries a `HYPOTHETICAL` ribbon.**

**3 · Site Registry** — table + map split. Create, review, publish, archive hypothetical sites.
Columns: code, name, district, ore zone, depth, status, last run, risk, owner org.

**4 · Simulation Studio** — the current `ml_pipeline` dashboard, rebuilt as a first-class screen.
- Left: sliders grouped (Operational, Hydrogeological, Timeline, Depth)
- Centre: map + plume
- Right: metric cards with **P10–P90 bands always visible**, never a bare number
- Bottom: lifecycle timeline with month-by-month animation
- **Provenance drawer** — every input shows source (CGWB polygon / NAQUIM / Texas n=9 / literature)
- Save as named scenario; compare two scenarios side by side

**5 · Monitoring & Alerts** *(the CPS deliverable)* — station map, time-series with seasonal bands,
threshold rules, alert inbox with acknowledgement trail.

**6 · Analytics** — district vulnerability ranking, species comparison, model-vs-BIS/WHO exceedance,
**Data Gap Report** (a named proposal deliverable: which districts lack NAQUIM profiles, which wells
lack recent samples, where the flow field falls back to DEM).

**7 · Data Ingest** *(admin)* — upload, validate, diff against current version, promote.

**8 · Admin** — orgs, users, roles, API keys, rate-limit tiers, audit log.

### 4.2 Non-negotiable UI rules

These come directly from the audit history and exist to stop the portal over-claiming:

1. **No bare point estimates.** Every predicted quantity renders with its band or an explicit
   "deterministic — no band" label.
2. **Extrapolation is loud.** Outside the trained envelope, cards turn amber and state that the
   conformal guarantee is void and the analytical engine is serving.
3. **Provenance on hover** for every input, carrying `n` where small (the Texas n=9 case).
4. **"Total Vulnerable Area" is relabelled.** `review2.md` established it is 76–97% leach-zone disc.
   It becomes **"Contaminated Footprint (wellfield + migrating plume)"** with the split shown.
5. **Migration reads "no measurable migration"** below map resolution, never a misleading `0`.
6. **The hypothetical premise is never more than one glance away.**

---

## 5. Access control & rate limiting

### 5.1 Roles

| Role | Scope | Can |
|---|---|---|
| `super_admin` | System | Everything incl. ingest, model promotion |
| `regulator` | All orgs | Read all sites, publish/archive, export signed reports, resolve alerts |
| `operator` | Own org | CRUD own sites, run sims, respond to alerts |
| `analyst` | Assigned orgs | Run + save scenarios, no publish, no ingest |
| `field_officer` | Assigned stations | Upload readings/samples only |
| `viewer` | Read-only | Published sites, aggregate analytics, no raw coordinates |
| `public` (unauth) | Aggregate | District risk map only; no site detail, no simulation |

Enforced with **row-level security in Postgres** keyed on `owner_org_id`, not only in application
code — so a service bug cannot leak another org's sites.

### 5.2 Rate limiting

Directly answers `review2.md` V-6 (12 endpoints, no auth, no limits, 0.48 MB uncached payloads,
against a frontend that issues one request per simulated month by design).

| Tier | Read | Simulation | Ingest |
|---|---|---|---|
| `public` | 30/min | — | — |
| `viewer` | 120/min | — | — |
| `analyst` / `operator` | 600/min | **30/min, 5 concurrent** | — |
| `regulator` | 600/min | 60/min | — |
| `super_admin` | 1200/min | 120/min | 10/hour |

- Token bucket in Redis, keyed on `user_id` (fall back to IP when unauthenticated)
- Simulation runs go to a **queue with per-user concurrency caps** — a 0.1 s CPU-bound solve must
  never be a synchronous request under load
- Static geography served with `ETag` + 24 h `Cache-Control`, invalidated by `dataset_version`
- Timeline animation switches to a **single batched multi-month endpoint** rather than N requests

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
        │ PostGIS +   │ │ cache  │ │ DEM, .npz,    │
        │ TimescaleDB │ │ queue  │ │ artifacts     │
        └─────────────┘ └────────┘ └───────────────┘
```

**Key decision: `ml_pipeline/` is never exposed directly.** It becomes an internal service behind the
gateway. It keeps its own test suite and release cadence; the gateway owns auth, limits and audit.
This preserves the scientific integrity of a validated codebase while making it safe to deploy.

---

## 7. Delivery plan

| Phase | Scope | Outcome |
|---|---|---|
| **P1** | Postgres schema + migrations; load all `Datasets/` with `dataset_versions` | Real data, versioned, queryable |
| **P2** | Gateway: auth, RBAC, RLS, rate limits, audit; delete the 22 dead endpoints | Safe to expose |
| **P3** | Wire `POST /simulations` → ml_pipeline; scenarios; run persistence | Reproducible runs |
| **P4** | React shell: Login, Map Console, Site Registry | **Demoable to stakeholders** |
| **P5** | Simulation Studio with bands + provenance drawer | Full decision support |
| **P6** | Monitoring & Alerts (CPS loop) + Data Gap Report | Proposal deliverables complete |
| **P7** | Signed PDF reports, audit export, hardening | Production candidate |

**Demo-ready at P4.** Everything before it is foundation; everything after deepens it.

---

## 8. Risks carried into the product

Stated plainly, because the portal must not present them as solved:

1. **No ISR operates in Jharkhand.** Every simulation is hypothetical. Schema, API and UI enforce this.
2. **The uranium source term rests on 9 measurements** (`review2.md` V-2). Surfaced via
   `dataset_versions.n_supporting`.
3. **The conformal 80% guarantee is calibrated on generator scenarios**, whose median gradient is
   1.35× the real field (`review2.md` V-5). Until the field-resampled gate runs, the UI should say
   "80% calibrated on modelled scenarios" — not "80% guaranteed".
4. **β, aperture, D_e, ω are foreign-analogue literature values** with zero Singhbhum measurements.
   Permanent until someone runs a packer or tracer test in the Singhbhum Shear Zone.
5. **Contaminated footprint is wellfield-dominated** (76–97% disc), which is why it is renamed.

A portal that shows these honestly is more defensible to a regulator than one that hides them —
and this project's entire audit history is the argument for that.
