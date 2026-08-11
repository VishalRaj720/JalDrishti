# JalDrishti

JalDrishti is a groundwater **uranium-contamination impact assessment** platform for
ISR (In-Situ Recovery) uranium-mining scenarios in Jharkhand. It predicts how uranium
and the co-contaminants ISR mobilises (TDS, sulfate, radium) spread around a
*hypothetical* injection point, grounds those predictions in real Texas ISR operating
data and real Jharkhand hydrogeology, and exposes them through a map UI.

The three project objectives are: (1) ML-based prediction of water-quality
degradation / aquifer vulnerability, (2) data-gap analysis with monitoring
recommendations, and (3) a prototype decision-support tool.

> ⚠️ **Screening and education only.** No ISR mine exists in Jharkhand, so the
> transferred physics has never been validated against a local operation. Not for
> permitting. The frozen limitations are listed in
> [`docs/audits/ML_PIPELINE_READINESS.md`](docs/audits/ML_PIPELINE_READINESS.md) §7.

## Status — 2026-08-11

Three codebases, deliberately **not yet wired together**. Joining them is what
[`PRODUCT_DESIGN.md`](PRODUCT_DESIGN.md) specifies.

| Component | State |
|---|---|
| `ml_pipeline/` | **The mature part.** Physics-informed ISR plume surrogate, 307 passing tests, transport kernel benchmarked against an exact solution, conformal bands validated on the serving distribution, 12-entry assumption register. Frozen. |
| `backend/` | FastAPI + PostgreSQL/PostGIS, JWT + 5-role RBAC, idempotent seed, provenance spine and audit log. Does **not** call `ml_pipeline/` yet — the fabricated stub engine was deleted in P0 and `POST /simulations` returns 501 until P3 wires the real one. |
| `frontend/` | Two separate UIs: the static `JalDrishti.html` prototype (talks to `backend/`), and `frontend/ml_pipeline/` (vanilla JS + Leaflet, talks to the surrogate's own dashboard server). |

## Repository layout

```text
JalDrishti/
├── ml_pipeline/          ISR plume surrogate: physics, synthetic generator, ML, dashboard API
├── backend/              FastAPI app (PostgreSQL/PostGIS), alembic migrations, seed, tests
├── frontend/
│   ├── JalDrishti.html   Static React/Babel/Leaflet prototype against backend/
│   └── ml_pipeline/      Vanilla JS + Leaflet UI for the surrogate dashboard
├── Datasets/             Jharkhand geology, water quality/levels, rivers, DEM, NAQUIM refs
├── fetch_data/           Standalone download/ETL scripts for the datasets above
├── utilities/            One-off GeoJSON/CSV/PDF prep helpers
├── docs/                 All documentation — see docs/README.md
├── PRODUCT_DESIGN.md     How the three components become one product
└── docker-compose.yml    db (PostGIS) + backend
```

## Documentation

Start at [`docs/README.md`](docs/README.md). The short version:

- [`PRODUCT_DESIGN.md`](PRODUCT_DESIGN.md) — the integration spec (root, because it is the active plan)
- [`ml_pipeline/ARCHITECTURE.md`](ml_pipeline/ARCHITECTURE.md) — the surrogate explained from zero
- [`ml_pipeline/README.md`](ml_pipeline/README.md) — quick start and phase history
- [`ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`](ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md) — provenance of every physical constant
- [`docs/roles.md`](docs/roles.md) — the five roles, and a generated role × endpoint matrix
- [`docs/audits/`](docs/audits/) — the audit and remediation record, chronological
- [`docs/local/`](docs/local/) — learning write-ups and reference material (not tracked)

## Running the ML pipeline and its dashboard

```bash
python -m pytest ml_pipeline/tests -q
```

```bash
uvicorn ml_pipeline.dashboard.server:app --reload --port 8077
```

Then open `http://localhost:8077`. Regenerating the training set and retraining is
documented in [`ml_pipeline/README.md`](ml_pipeline/README.md) — note that a retrain
must be followed by `python -m ml_pipeline.tools.sync_docs`, or
`tests/test_docs_in_sync.py` will fail on the stale metrics block.

## Running the backend

### Prerequisites
- Python 3.12
- PostgreSQL 16+ with PostGIS

### 1. Create the database
```sql
CREATE DATABASE groundwater_db;
```

### 2. Install
```bash
cd backend && pip install -r requirements.txt
```

### 3. Create the restricted application role

The API and the migrations connect as **different** Postgres roles. This is not optional: Postgres
skips row-level security entirely for a superuser, so an API connected as `postgres` silently
disables every policy in migration `0009`.

```bash
python -m scripts.create_app_role --password 'choose-a-real-one'
```

That creates `jaldrishti_app` — `NOSUPERUSER`, `NOBYPASSRLS`, DML only, no ownership, so it cannot
drop a policy that constrains it.

### 4. Create `backend/.env`

Defaults live in `app/config.py`.

```env
APP_ENV=development
# What the running API connects as — restricted, so RLS applies.
DATABASE_URL=postgresql+asyncpg://jaldrishti_app:YOUR_APP_PASSWORD@localhost:5432/groundwater_db
# Owner role, used only by alembic and scripts/init_db (CREATE EXTENSION, DDL).
MIGRATION_DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/groundwater_db
DB_NAME=groundwater_db
DB_USER=postgres
DB_PASSWORD=YOUR_PASSWORD
JWT_SECRET=change-this-secret
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
RATE_LIMIT_PER_MINUTE=60
```

The API logs `Row-level security active: N policies, connected as 'jaldrishti_app' (no bypass)` at
startup. If it instead warns `ROW-LEVEL SECURITY IS INERT`, `DATABASE_URL` is pointing at a
privileged role and access control has fallen back to the application layer only.

Who can reach which endpoint is in [`docs/roles.md`](docs/roles.md) — generated from the running app.

### 5. Create tables and seed (idempotent)
```bash
python -m scripts.init_db
```

```bash
python -m scripts.seed
```

`seed` is safe to re-run: users dedupe by email, ISR points by name, and geodata
ingestion dedupes by file checksum.

### 6. Run the API
```bash
uvicorn app.main:app --reload
```

Swagger UI at `http://localhost:8000/docs`. Routes under `/api/v1`: `/auth`, `/users`,
`/districts`, `/blocks`, `/aquifers`, `/isr-points`, `/simulations`,
`/monitoring-stations`, `/monitoring-wells`, `/water-samples`, `/ingest`; plus
`/health`, `/docs`, `/metrics`.

There is no Celery or Redis in this checkout. `POST /simulations` currently returns
501 — see Known gaps.

### Tests
```bash
cd backend && pytest
```

Uses a dedicated `groundwater_test_db`, created automatically and isolated from the
dev database. Override with `TEST_DATABASE_URL`.

## Frontend prototype

```bash
cd frontend && python -m http.server 4173
```

Open `http://localhost:4173/JalDrishti.html`. Loads React/Babel/Leaflet from CDNs and
falls back to mock data if the backend is down.

## Docker

```bash
docker-compose up --build
```

Brings up `db` (PostGIS) + `backend`.

## Seeded users

| Role | Email | Password |
|---|---|---|
| admin | `admin@jaldrishti.local` | `admin123` |
| analyst | `analyst@jaldrishti.local` | `analyst123` |
| citizen | `citizen@jaldrishti.local` | `citizen123` |

The five designed roles are `admin`, `regulator`, `analyst`, `field_officer` and
`citizen`. `viewer` was renamed to `citizen` by migration `0008`; any pre-existing
`viewer` account keeps its email and is moved to the `citizen` role. Only the three
above are seeded — `regulator` and `field_officer` are created per deployment.

## Known gaps

- `POST /simulations` returns 501. The backend's own stub engine was deleted in P0
  (it fabricated results); wiring it to `ml_pipeline/` is P3 in
  [`PRODUCT_DESIGN.md`](PRODUCT_DESIGN.md).
- Two unrelated frontends exist; the product design picks one path.
- The surrogate is calibrated on transferred Texas physics — see the readiness
  report's frozen-limitations section before quoting any number from it.
- Development secrets in `config.py` are placeholders; override them in real
  environments.
