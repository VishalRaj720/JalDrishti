# JalDrishti

JalDrishti is a groundwater contamination impact assessment platform focused on ISR (In-Situ Recovery) mining scenarios in Jharkhand. The current repository contains a substantial FastAPI backend, seeded geospatial and water-quality data pipelines, baseline ML assets, and a static browser prototype for the UI.

## Status Snapshot

Reviewed against the repository on 2026-05-06.

- Backend API is the most complete part of the project.
- Month 3 data foundation work is present: schema extensions, ingestion flows, monitoring wells, water samples, and supporting datasets.
- Month 4 baseline ML work is present: synthetic data generation, feature engineering, model training scripts, SHAP analysis, and committed ML artifacts.
- Frontend is currently a static HTML + JSX prototype in `frontend/`, not a Vite or packaged React application.
- `docker-compose.yml` defines backend infrastructure, but the referenced `ml-service/` directory is missing and there is no frontend container.
- Backend tests are wired up, but the current test environment is incomplete because `aiosqlite` is not listed in `backend/requirements.txt`.

## Current Repository Layout

```text
JalDrishti/
|-- backend/            FastAPI app, Alembic migrations, Celery tasks, ML code, tests
|-- frontend/           Static React/Babel prototype and browser-side API client
|-- docs/               Project notes and progress docs for Month 3 and Month 4
|-- Datasets/           GeoJSON, CSV, and JSON source datasets
|-- fakedataset/        Synthetic wells and water samples used for baseline ML
|-- .claude/            Project guidance and working notes for Claude Code
|-- docker-compose.yml  Local infra definition for DB, Redis, backend, Celery, Flower, ml-service
`-- architecture_analysis.md
```

## What Is Implemented

### Backend

The backend is built with FastAPI, SQLAlchemy async, PostgreSQL/PostGIS, Alembic, Celery, Redis, and Pydantic settings.

Implemented areas:

- JWT auth with access and refresh tokens
- Role-based access control for `admin`, `analyst`, and `viewer`
- District, block, aquifer, and ISR point management
- District GeoJSON export
- Monitoring station and groundwater reading APIs
- Monitoring well and water sample APIs
- Bulk ingestion endpoints for district GeoJSON, subdistrict GeoJSON, aquifer GeoJSON, groundwater-level JSON, and water-quality CSV
- Async simulation trigger with Celery-first execution and FastAPI background fallback
- Redis cache wrapper and bbox caching for monitoring-well queries
- Prometheus metrics at `/metrics`

### Simulation and ML

The simulation path is implemented, but still partially heuristic:

- Plume footprint generation is based on a simplified ADE-style ellipse
- Aquifer impact detection uses PostGIS spatial intersection
- Prediction path uses a three-level fallback:
  1. In-process sklearn artifacts from `backend/ml/artifacts/`
  2. HTTP call to `ML_SERVICE_URL`
  3. Randomized stub payload
- Monte Carlo uncertainty and recovery suggestions are included in simulation output

Month 4 ML assets included in the repository:

- `backend/ml/features.py`
- `backend/ml/feature_pipeline.py`
- `backend/ml/train_baselines.py`
- `backend/ml/shap_analysis.py`
- `backend/ml/artifacts/tds_regressor.joblib`
- `backend/ml/artifacts/contamination_classifier.joblib`
- `backend/ml/artifacts/training_metrics.json`
- `backend/ml/artifacts/shap_top10_regressor.json`
- `backend/ml/artifacts/shap_top10_classifier.json`

### Frontend

The frontend in this repo is a prototype, not the production React app described in some older docs.

What exists today:

- `frontend/JalDrishti.html` as the entry point
- JSX files loaded in-browser through Babel Standalone
- Leaflet-based map UI
- Browser-side API client in `frontend/jaldrishti-api.js`
- Mock dataset fallback in `frontend/jaldrishti-data.js`
- Screenshots showing the prototype UI states

Behavior:

- The prototype attempts to use the FastAPI backend at `http://localhost:8000/api/v1`
- If the backend is unavailable, key flows fall back to mock/demo data

## API Surface

All API routes are mounted under `/api/v1`.

Main route groups:

- `/auth`
- `/users`
- `/districts`
- `/districts/{district_id}/blocks`
- `/blocks`
- `/aquifers`
- `/isr-points`
- `/simulations`
- `/blocks/{block_id}/monitoring-stations`
- `/monitoring-stations`
- `/monitoring-wells`
- `/water-samples`
- `/ingest`

Useful non-versioned routes:

- `/health`
- `/docs`
- `/redoc`
- `/metrics`

## Data Assets

Repository data sources include:

- District and sub-district boundary GeoJSON files in `Datasets/`
- Aquifer GeoJSON files in `Datasets/`
- Groundwater-level JSON files in `Datasets/waterLevelJson/`
- Water-quality CSV in `Datasets/waterQuality_jharkhand.csv`
- Synthetic wells and samples in `fakedataset/`

Based on the Month 3 and Month 4 project docs, the seeded data pipeline is intended to support:

- 25 districts
- 275 blocks
- 24 aquifers
- 29 monitoring stations
- 419 groundwater readings
- 397 monitoring wells
- 397 water samples
- 500 synthetic water samples across 50 synthetic wells

## Local Development

### Prerequisites

- Python 3.12 recommended
- PostgreSQL 16 with PostGIS
- Redis 7
- A browser for the frontend prototype

Node.js is not required for the current frontend prototype because it is not built with npm in this checkout.

### 1. Database

```sql
CREATE DATABASE groundwater_db;
\c groundwater_db
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `backend/.env` if needed. The app already has development defaults in `app/config.py`, but an explicit `.env` is safer:

```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/groundwater_db
DB_HOST=localhost
DB_PORT=5432
DB_NAME=groundwater_db
DB_USER=postgres
DB_PASSWORD=YOUR_PASSWORD
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
JWT_SECRET=change-this-secret
JWT_REFRESH_SECRET=change-this-refresh-secret
ML_SERVICE_URL=http://localhost:8001
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000
RATE_LIMIT_PER_MINUTE=60
```

Run migrations and seed base users:

```bash
alembic upgrade head
python -m scripts.seed
```

Optional data seed for the Month 3 dataset layer:

```bash
python -m scripts.seed_month3_data
```

Start the API:

```bash
uvicorn app.main:app --reload
```

Backend URLs:

- API root: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

### 3. Celery worker

If you want async simulations through Celery instead of FastAPI background tasks:

```bash
cd backend
celery -A app.celery_app worker --loglevel=info
```

Optional Flower dashboard:

```bash
cd backend
celery -A app.celery_app flower --port=5555
```

### 4. Optional Month 4 ML pipeline

These scripts exist and are documented in the repo:

```bash
cd backend
python -m ml.synthetic
python -m ml.load_synthetic
python -m ml.feature_pipeline
python -m ml.train_baselines
python -m ml.shap_analysis
```

## Running the Frontend Prototype

Because the current frontend is a static HTML prototype, the simplest way to run it is to serve the `frontend/` directory locally:

```bash
cd frontend
python -m http.server 4173
```

Then open:

```text
http://localhost:4173/JalDrishti.html
```

Notes:

- The page loads React, Babel, and Leaflet from CDNs.
- The prototype first tries the local FastAPI backend.
- If the backend is unavailable, much of the UI still works with mock data.
- Default demo credentials in the prototype match the seeded backend users:
  - `admin@jaldrishti.local` / `admin123`
  - `analyst@jaldrishti.local` / `analyst123`
  - `viewer@jaldrishti.local` / `viewer123`

## Docker

`docker-compose.yml` currently defines these services:

- `db`
- `redis`
- `backend`
- `celery-worker`
- `flower`
- `ml-service`

Current caveats:

- `ml-service` points to `./ml-service`, but that directory is not present in this repository.
- There is no frontend service in the compose file.
- The compose setup is useful mainly for backend infrastructure.

If you want to use compose today, comment out or remove the `ml-service` block first:

```bash
docker-compose up --build
```

## Testing

Backend tests live in `backend/tests/`.

Test command:

```bash
cd backend
pytest tests
```

Current status:

- The test suite is configured to use in-memory SQLite with `sqlite+aiosqlite:///:memory:`
- In the current checkout, `aiosqlite` is missing from `backend/requirements.txt`
- As a result, `pytest tests` currently fails at import time until `aiosqlite` is installed

## Seeded Users

Created by `python -m scripts.seed`:

| Role | Email | Password |
|---|---|---|
| admin | `admin@jaldrishti.local` | `admin123` |
| analyst | `analyst@jaldrishti.local` | `analyst123` |
| viewer | `viewer@jaldrishti.local` | `viewer123` |

## Documentation Index

Useful repo documents:

- `docs/overview.md` - broad project explanation and study notes
- `docs/FEBRUARY_month3.md` - Month 3 data-foundation delivery notes
- `docs/month4.md` - Month 4 feature engineering and baseline ML notes
- `architecture_analysis.md` - repo architecture analysis
- `.claude/CLAUDE.md` - project guidance and workflow notes for Claude Code

Some of these documents describe planned or historical architecture that is broader than what is runnable in the current checkout. Treat this README as the source of truth for the repository's present state.

## Known Gaps

- Frontend is a prototype bundle, not a packaged React/Vite application.
- `docker-compose.yml` references a missing `ml-service/` directory.
- Simulation physics still use stubbed/randomized groundwater gradient logic.
- Development defaults in `backend/app/config.py` and `docker-compose.yml` include placeholder or weak secrets and should be overridden in real environments.
- Tests are not currently runnable from a fresh install without adding `aiosqlite`.
- Some older docs still describe a fuller frontend architecture than what exists in `frontend/` today.
