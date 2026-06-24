# JalDrishti

JalDrishti is a groundwater **uranium-contamination impact assessment** platform
for ISR (In-Situ Recovery) uranium-mining scenarios in Jharkhand. It predicts how
uranium (and the co-contaminants ISR mobilises — TDS, sulfate, pH) spread around a
hypothetical injection point, grounds those predictions in real data, and exposes
them through an API and map UI for stakeholders.

The three project objectives are: (1) ML-based prediction of water-quality
degradation / aquifer vulnerability, (2) data-gap analysis with monitoring
recommendations, and (3) a prototype decision-support tool.

## Status Snapshot

Updated 2026-06-24 (Month 1 of the 3-month completion plan).

- **Unified ML pipeline (`DataGen_ModelMVP/pipeline/`)** — one schema, uranium as
  the real prediction target, sourced from real Texas ISR + Jharkhand CGWB data.
  Replaces the two earlier, disconnected pipelines.
- **Backend slimmed down** — Celery/Redis, the never-built `ml-service`,
  refresh-token rotation, and five unused models were removed. PostgreSQL/PostGIS
  and three-role RBAC are kept.
- **DB setup is two commands** — `init_db` (create tables) + an idempotent `seed`.
- Frontend remains the static HTML/JSX prototype (vanilla-JS rewrite is Month 3).

## Repository Layout

```text
JalDrishti/
|-- backend/                FastAPI app (PostgreSQL/PostGIS), idempotent seed, tests
|-- DataGen_ModelMVP/
|   |-- pipeline/           Unified ML pipeline (schema, loaders, synth, build, train)
|   `-- Real_dataset/       Real Texas ISR chemistry + mine ops + East Singhbhum DEM
|-- Datasets/               Jharkhand GeoJSON, water-level JSON, water-quality CSV
|-- frontend/               Static Leaflet + JSX prototype (rewrite pending)
`-- docker-compose.yml      db (PostGIS) + backend
```

## The ML pipeline (Objective 1)

See `DataGen_ModelMVP/pipeline/README.md` for full detail. In short:

- **Targets:** uranium (ppb) regressor + safe/marginal/unsafe risk classifier,
  plus TDS / sulfate / pH co-target regressors.
- **Real grounding:** Texas ISR before/during/after uranium signal; Texas mine-ops
  (injection rate, ore grade, ore porosity); Jharkhand CGWB ambient uranium;
  real aquifer hydrogeology via spatial join. Every row is tagged
  `texas_real` / `jharkhand_real` / `synthetic`.

```bash
cd DataGen_ModelMVP
pip install -r requirements.txt
python -m pipeline.build      # -> pipeline/artifacts/unified_dataset.csv
python -m pipeline.train      # -> pipeline/artifacts/*.joblib + metrics.json
```

## Backend

FastAPI + SQLAlchemy (async) + PostgreSQL/PostGIS. JWT auth (single access token)
with `admin` / `analyst` / `viewer` RBAC. Simulations run as in-process background
tasks (no Celery/Redis). In-process cache, Prometheus metrics at `/metrics`.

API routes under `/api/v1`: `/auth`, `/users`, `/districts`, `/blocks`,
`/aquifers`, `/isr-points`, `/simulations`, `/monitoring-stations`,
`/monitoring-wells`, `/water-samples`, `/ingest`. Plus `/health`, `/docs`, `/metrics`.

> Note: `services/ml_prediction.py` is currently a transparent deterministic
> placeholder. Wiring the trained pipeline models into the simulation endpoint is
> the Month-2 task.

## Local Development

### Prerequisites
- Python 3.12
- PostgreSQL 16+ with PostGIS

### 1. Create the database
```sql
CREATE DATABASE groundwater_db;
```

### 2. Backend setup
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env` (defaults live in `app/config.py`):
```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/groundwater_db
JWT_SECRET=change-this-secret
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
RATE_LIMIT_PER_MINUTE=60
```

### 3. Create tables and seed (idempotent)
```bash
python -m scripts.init_db    # PostGIS extension + enum types + all tables
python -m scripts.seed       # users + Jaduguda ISR point + Jharkhand geodata
```
`seed` is safe to re-run: users dedupe by email, ISR points by name, and the
geodata ingestion dedupes by file checksum — re-running does not duplicate rows.

### 4. Run the API
```bash
uvicorn app.main:app --reload
```
Swagger UI at `http://localhost:8000/docs`.

## Frontend Prototype
```bash
cd frontend
python -m http.server 4173      # open http://localhost:4173/JalDrishti.html
```
Loads React/Babel/Leaflet from CDNs; falls back to mock data if the backend is
down. Demo credentials match the seeded users below.

## Docker
```bash
docker-compose up --build       # db (PostGIS) + backend
```

## Testing
```bash
cd backend
pytest                          # runs against a real PostGIS test DB (auto-created)
```
Tests use a dedicated `groundwater_test_db` (created automatically, isolated from
the dev database). Override with `TEST_DATABASE_URL` if needed.

## Seeded Users
| Role | Email | Password |
|---|---|---|
| admin | `admin@jaldrishti.local` | `admin123` |
| analyst | `analyst@jaldrishti.local` | `analyst123` |
| viewer | `viewer@jaldrishti.local` | `viewer123` |

## Known Gaps / Next
- Month 2: fold the trained uranium model into the simulation endpoint; make the
  spread projection real using the East Singhbhum DEM + Jaduguda water levels.
- Month 3: vanilla-JS frontend rewrite + the data-gap analysis panel (Objective 2).
- Development secrets in `config.py` are placeholders — override in real environments.
- `architecture_analysis.md` describes an older, broader architecture and is not an
  accurate map of this checkout.
