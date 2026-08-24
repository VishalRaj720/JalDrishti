# JalDrishti

A groundwater **uranium-contamination screening platform** for ISR (In-Situ Recovery)
uranium-mining scenarios in Jharkhand, India. It models how uranium and the
co-contaminants ISR mobilises — sulfate, TDS, radium — would spread from a hypothetical
injection point, grounds that in real Texas ISR operating records and real Jharkhand
hydrogeology, and puts it behind a role-aware government portal.

> ### No ISR uranium mine operates in Jharkhand
>
> Every site in this system is **hypothetical**. Commercial ISR is not physically
> plausible in schist-hosted ore, so every output means *"if ISR-strength lixiviant
> entered this aquifer"* — never feasibility, never a permit. No prediction here has ever
> been validated against a real plume, because none exists to validate against.
>
> **Screening and education only.** Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)
> before quoting any number from this system.

The project's three objectives: (1) ML-based prediction of water-quality degradation and
aquifer vulnerability, (2) data-gap analysis with monitoring recommendations, and (3) a
decision-support prototype.

---

## The three parts

| Part | What it is | State |
|---|---|---|
| `ml_pipeline/` | The physics + ML engine. Domenico/Ogata-Banks transport, Tang matrix diffusion, dual-porosity retardation; XGBoost P10/P50/P90 heads with Mondrian split-conformal calibration | **338 tests.** Transport kernel benchmarked against an exact solution; bands validated on the serving distribution |
| `backend/` | FastAPI + PostgreSQL/PostGIS. JWT + 5-role RBAC with Postgres row-level security, provenance spine, immutable audit log, field-observation review, dataset sync, IS 10500 water-quality assessment, groundwater level trends | **402 tests.** Runs the real engine; every stored run pins model card, artifact bundle and git SHA |
| `frontend/portal/` | The portal SPA — Vite + React 18 + TypeScript + Leaflet | Typechecks and builds clean |

**The engine is the authority.** The ML surrogate was trained on that engine's own output,
so it cannot be more accurate than it — it contributes calibrated uncertainty bands.
Every number in the UI says which engine produced it.

## Documentation

Everything tracked lives in `docs/`, except four files that must stay next to the code
because `tools/sync_docs.py`, `validation/end_to_end_audit.py` and
`tests/test_docs_in_sync.py` load them by path.

| Read this | For |
|---|---|
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | **What this system does not know.** Open findings, permanent blockers, claims not to make |
| [`docs/PRODUCT_DESIGN.md`](docs/PRODUCT_DESIGN.md) | How the three components become one product |
| [`docs/DEPLOY_WALKTHROUGH.md`](docs/DEPLOY_WALKTHROUGH.md) | **Start here to deploy.** The click-by-click: which site, what to type, what to check |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | The architecture behind it: the two database roles, the secrets, why one origin |
| [`docs/roles.md`](docs/roles.md) | The four roles + a generated role × endpoint matrix |
| [`docs/FRONTEND_DESIGN.md`](docs/FRONTEND_DESIGN.md) | The portal's sections and responsive contract |
| [`ml_pipeline/ARCHITECTURE.md`](ml_pipeline/ARCHITECTURE.md) | The surrogate explained from zero |
| [`ml_pipeline/README.md`](ml_pipeline/README.md) | Running and retraining the engine |
| [`ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`](ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md) | Provenance of every physical constant |

`docs/local/` is untracked — reference PDFs, learning write-ups, and
`audit-record/`, the chronological review history. That record is kept rather than
summarised because several findings were later **retracted**, and code comments cite them
by name (`review2.md V-8`) as stable identifiers.

## The five roles

| Role | Labelled | Can |
|---|---|---|
| `admin` | Admin | Everything: publishes advisories, syncs datasets, edits the dataset files, operates the model, reads audit, manages accounts |
| `regulator` | Regulator | Decides on what a field officer submits — approve or reject. **Runs the model** (R14): pin, predict, preview, lifecycle, sweep, scenarios, site registration. Cannot publish to citizens, write datasets, operate the model or manage accounts |
| `analyst` | Analyst | Registers sites, runs the engine, saves scenarios, proposes publications |
| `field_officer` | Data Submitter | Submits uranium-ore occurrences and observations for review |
| `citizen` | Resident | Measured results for their area, published advisories, alerts. No coordinates, no model internals |

`regulator` was retired in migration `0019` and **restored in `0022`** with a
narrower, real job. The reason merging it into `admin` was wrong: the person who
accepts evidence into the record should not also be the person who operates the
pipeline that consumes it. A regulator gets the same 403 a citizen would on every
dataset, model and account route.

Migration `0022` also **pins `admin` to exactly one account**. A surplus
administrator is demoted to `analyst` rather than deleted, the account is created
by `scripts/bootstrap_admin`, and the Administration screen offers no role
control for it — so the sole admin cannot be demoted or removed by a stray click.

The full role x endpoint matrix is generated from the live app into
[`docs/roles.md`](docs/roles.md). Regenerate it with
`python -m scripts.authz_matrix` after adding any route, or
`tests/test_authz_matrix.py` fails.

---

## Quick start

### ML pipeline

```bash
python -m pytest ml_pipeline/tests -q
```

```bash
uvicorn ml_pipeline.dashboard.server:app --reload --port 8077
```

Then open `http://localhost:8077` for the engine's own dashboard. Retraining is
documented in [`ml_pipeline/README.md`](ml_pipeline/README.md) — a retrain **must** be
followed by `python -m ml_pipeline.tools.sync_docs`, or `tests/test_docs_in_sync.py`
fails on the stale metrics block.

### Backend

Requires Python 3.12 and PostgreSQL 16+ with PostGIS.

```sql
CREATE DATABASE groundwater_db;
```

```bash
cd backend && pip install -r requirements.txt
```

**Create the restricted application role.** The API and the migrations connect as
*different* Postgres roles, and this is not optional: Postgres skips row-level security
entirely for a superuser, so an API connected as `postgres` silently disables every
policy in migration `0009`.

```bash
python -m scripts.create_app_role --password 'choose-a-real-one'
```

That creates `jaldrishti_app` — `NOSUPERUSER`, `NOBYPASSRLS`, DML only, no ownership, so
it cannot drop a policy that constrains it.

Then `backend/.env` (defaults live in `app/config.py`):

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

At startup the API logs `Row-level security active: N policies, connected as
'jaldrishti_app' (no bypass)`. If it instead warns **`ROW-LEVEL SECURITY IS INERT`**,
`DATABASE_URL` points at a privileged role and access control has fallen back to the
application layer alone.

```bash
python -m scripts.init_db
python -m scripts.seed
uvicorn app.main:app --reload
```

`seed` is idempotent: users dedupe by email, ISR points by name, geodata by file
checksum. Swagger UI at `http://localhost:8000/docs`.

Routes under `/api/v1`: `/auth`, `/users`, `/districts`, `/isr-points`,
`/simulations`, `/preview`, `/lifecycle`, `/scenarios`, `/advisories`,
`/citizen`, `/public/risk`, `/field-observations`, `/data-gaps`, `/dataset-sync`,
`/datasets`, `/model-ops`, `/monitoring-wells`, `/water-samples`,
**`/water-quality`**, **`/groundwater`**, `/ingest`, `/audit`, `/ml`; plus
`/health` and `/metrics`. `/docs` and `/openapi.json` are served in development
and **not in production** unless `DOCS_ENABLED=true`.

`/water-quality/*` assesses every measured determinand against **IS 10500:2012**,
and `/groundwater/*` reports Theil-Sen level trends over the 2013-2021 CGWB
station record. Both read data the platform was already collecting; neither
involves the model, and neither predicts anything.

**The citizen surface bands on health, not on uranium (R14).** `/public/risk/*`
judges a block on every measured health-significant determinand — uranium,
nitrate and fluoride. That is not a refinement: statewide maximum uranium is
28.5 ppb against a 30 ppb limit, so the old uranium-only band **could not colour
a single district red**, while 22 wells exceeded the nitrate limit. Fourteen of
twenty-four districts move once nitrate and fluoride are read. Every response
carries `band_driver` (which substance decided it) and `untested_health` (which
were never analysed — arsenic and iron, nowhere in the state).

`/api/v1/ml/*` re-serves the `ml_pipeline` engine behind the portal's JWT, role guards,
rate limiter and audit middleware, so the browser never talks to the pipeline's own
unauthenticated dashboard on :8077. `predict` there is interactive and **stores nothing**;
`POST /simulations/{id}` is the deliberate act that writes an auditable run.

```bash
cd backend && pytest
```

Uses a dedicated `groundwater_test_db`, built from ORM metadata rather than migrations —
so any `server_default` relied on in raw SQL must also be on the model. Override with
`TEST_DATABASE_URL`.

### Portal

Needs the backend on :8000 — Vite proxies `/api` to it.

```bash
cd frontend/portal && npm install && npm run dev
```

Open `http://localhost:5173`. The **Console** is the main working surface: three
basemaps, every layer toggleable, and an ISR/District mode toggle that decides what a
click means. In ISR mode a click **anywhere in Jharkhand** resolves the hydrogeology
there, runs the engine live with the plume drawn on the map, and offers to register the
location. That live run is ephemeral; saving it is a separate, deliberate act.

Residents get their own map — measured district and block results, monitoring wells and
published advisories, with no ISR site, ore or model output at all.

Nav sections are filtered by role, and a hand-typed URL for a section a role cannot use
renders a refusal. That is convenience, not the boundary: the API and the Postgres RLS
policies enforce access independently.

### Docker

```bash
docker-compose up --build
```

Brings up `db` (PostGIS) + `backend`.

---

## Demo accounts

`python -m scripts.seed` creates one account per role so each can be signed into:

| Role | Email | Password |
|---|---|---|
| analyst | `analyst@jaldrishti.local` | `analyst123` |
| regulator | `regulator@jaldrishti.local` | `regulator123` |
| field_officer | `field@jaldrishti.local` | `field123` |
| citizen | `citizen@jaldrishti.local` | `citizen123` |

**There is no seeded admin.** Migration `0022` pins the role to one account and
`scripts/bootstrap_admin` is the only way to create it — it never accepts a
password on the command line, never prints one, and refuses anything under the
minimum length.

> **These must not survive into production.** They are weak, public, and listed on the
> login screen. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) §5 covers removing them.

## Repository layout

```text
JalDrishti/
├── ml_pipeline/          The engine: physics, synthetic generator, ML, dashboard API
├── backend/              FastAPI app, alembic migrations, seed, tests
├── frontend/
│   ├── portal/           The portal SPA — Vite + React + TS + Leaflet (21 screens)
│   ├── JalDrishti.html   Original static prototype, kept as visual reference
│   └── ml_pipeline/      Vanilla JS + Leaflet UI for the engine's own dashboard
├── Datasets/             Jharkhand geology, water quality/levels, rivers, DEM, NAQUIM refs
├── fetch_data/           Download/ETL scripts for those datasets
├── utilities/            One-off GeoJSON/CSV/PDF prep helpers
├── docs/                 All tracked documentation (local/ is untracked)
└── docker-compose.yml    db (PostGIS) + backend
```

## Working conventions

- **Verify parameters against a cited source** before changing them. `parameters.py`
  entries carry provenance; `JHARKHAND_FIDELITY_MATRIX.md` tracks it.
- **Do not hide weak results.** If a model misses an acceptance threshold, report it
  rather than moving the threshold. `docs/LIMITATIONS.md` §1 is a live example.
- **"No data" is a monitoring gap, never a clean result.**
- **A retrain must be followed by `sync_docs`.** Never fix a stale metrics block by
  editing the prose number.
