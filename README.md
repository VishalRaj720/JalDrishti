# JalDrishti — Groundwater Contamination Assessment Platform

JalDrishti models how uranium and other contaminant plumes propagate through aquifer systems from ISR (In-Situ Recovery) mining injection points. It supports spatial queries, asynchronous physics simulations, ML-based concentration predictions, and role-based access control.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Local Development Setup](#local-development-setup)
- [Docker Setup](#docker-setup)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Test Credentials](#test-credentials)
- [Known Limitations](#known-limitations)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI (async) + Python 3.12 |
| ORM / Database | SQLAlchemy 2.0 (async) + PostgreSQL 16 + PostGIS 3.4 + GeoAlchemy2 |
| Migrations | Alembic |
| Task queue | Celery 5.4 + Redis 7 |
| Auth | JWT HS256 — access tokens (15 min) + refresh tokens (7 days), argon2 hashing |
| Caching | Redis (DB 0 = cache, DB 1 = broker, DB 2 = Celery results) |
| Monitoring | Prometheus (`/metrics`), Celery Flower (port 5555), Sentry (optional) |
| Frontend | React 18 + TypeScript + Vite |
| State | Redux Toolkit + TanStack React Query v5 |
| UI | Material UI v5 + Tailwind CSS |
| Maps | Leaflet + react-leaflet |
| Charts | Recharts |
| Real-time | Socket.io-client (simulation progress via WebSocket) |
| Forms | Formik + Yup |

---

## Local Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 16 with the PostGIS extension
- Redis server running on `localhost:6379`

### 1. Database

```sql
CREATE DATABASE groundwater_db;
\c groundwater_db
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 2. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
# Copy the sample below into backend/.env and update credentials if needed
```

**`backend/.env`**
```env
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/groundwater_db
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
JWT_SECRET=change-this-to-a-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
ML_SERVICE_URL=http://localhost:8001
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
RATE_LIMIT_PER_MINUTE=60
```

```bash
# Run database migrations
alembic upgrade head

# Seed default users and base data
python -m scripts.seed

# (Optional) Seed monitoring stations and water samples
python -m scripts.seed_month3_data

# Start the API server
uvicorn app.main:app --reload
# API available at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

To run async simulations, start the Celery worker in a separate terminal:

```bash
cd backend
source .venv/bin/activate
celery -A app.celery_app worker --loglevel=info
```

### 3. Frontend

```bash
cd frontend
npm install
```

**`frontend/.env`**
```env
VITE_API_BASE_URL=/api/v1
VITE_WS_URL=ws://localhost:8000
```

```bash
npm run dev
# App available at http://localhost:5173
```

---

## Docker Setup

> **Note:** The `ml-service` directory is not included in this repository. Running `docker-compose up` will fail for the `ml-service` container. Comment out or remove the `ml-service` block in `docker-compose.yml` before running.

```bash
# In docker-compose.yml: remove or comment out the ml-service service block

docker-compose up --build
```

Services started:

| Service | Port | Description |
|---|---|---|
| Backend (FastAPI) | 8000 | REST API |
| Frontend (Vite) | 5173 | React SPA |
| PostgreSQL + PostGIS | 5432 | Primary database |
| Redis | 6379 | Cache + task broker |
| Celery Worker | — | Background simulation tasks |
| Flower | 5555 | Celery task monitoring UI |

After the stack is up, seed the database:

```bash
docker exec jaldrishti_backend python -m scripts.seed
```

---

## Architecture

### Infrastructure Topology

```
Browser
  ↕ HTTP  (Vite proxy: /api/v1 → localhost:8000)
  ↕ WS    (Socket.io → localhost:8000)

FastAPI (port 8000)
  ├── PostgreSQL + PostGIS (port 5432)  ← primary data store
  ├── Redis DB 0                        ← response cache (TTL 3600s)
  ├── Redis DB 1                        ← Celery task broker
  └── httpx → ML Service (port 8001)   ← concentration predictions (optional)

Celery Worker
  ├── Redis DB 1  ← receives tasks
  ├── Redis DB 2  ← stores results
  ├── PostgreSQL  ← persists simulation output
  └── httpx → ML Service

Flower (port 5555)  ← Celery monitoring UI
Prometheus scrape at /metrics
```

### Backend Layer Structure

```
backend/app/
├── main.py            # App factory, middleware, error handlers
├── config.py          # Pydantic Settings (env-driven, @lru_cache singleton)
├── database.py        # Async SQLAlchemy engine + session factory
├── dependencies.py    # FastAPI DI: get_db, get_current_user, require_roles()
├── cache.py           # Redis async wrapper (get/set/delete/invalidate_pattern)
├── celery_app.py      # Celery instance configuration
├── api/v1/            # 12 route modules (see API Reference below)
├── services/          # Business logic layer (ingestion.py is 24 KB — most complex)
├── repositories/      # Async DB access via generic BaseRepository pattern
├── models/            # 17 SQLAlchemy ORM models
├── schemas/           # Pydantic v2 request/response schemas
└── tasks/             # Celery task definitions (simulation.py, aggregation.py)
```

**Request flow:**

```
HTTP Request
  → FastAPI Router  (api/v1/*.py)
      DI: AsyncSession, current_user, require_roles()
  → Service Layer   (services/*.py)
      orchestrates business logic, calls repositories and ML service
  → Repository Layer (repositories/*.py)
      SQL via SQLAlchemy async session
  → PostgreSQL + PostGIS
```

### Data Models

All models inherit `UUIDPrimaryKeyMixin` (UUID primary key) and `TimestampMixin` (`created_at`, `updated_at`). Spatial columns use `postgresql_using="gist"` indices for fast intersection queries.

| Model | Key Fields |
|---|---|
| `User` | email, hashed_password, role (admin / analyst / viewer) |
| `District` | name, geometry (MULTIPOLYGON, SRID 4326) |
| `Block` | name, district_id, geometry |
| `Aquifer` | name, type (12 enum values), geometry, porosity, hydraulic_conductivity, transmissivity |
| `IsrPoint` | location (POINT), injection_rate |
| `Simulation` | status, affected_area, vulnerability JSONB, concentration JSONB, task_id |
| `PlumeParameter` | dispersivity_l/t, retardation_factor, decay_constant |
| `SimulationAquifer` | junction table (simulation_id ↔ aquifer_id) |
| `MonitoringStation` | location, elevation, installation_date |
| `MonitoringWell` | depth, casing_material, station_id |
| `WaterSample` | sample_date, parameters (JSONB), well_id |

### Simulation Pipeline (Core Feature)

`SimulationService` runs as a 9-step Celery task:

1. Extract ISR point lon/lat from PostGIS WKB geometry via Shapely
2. Compute groundwater gradient angle (stub: random NE angle pending real piezometric data)
3. Compute plume ellipse via Advection-Dispersion Equation (ADE):
   `rx = dispersivity_L × √days`, `ry = dispersivity_T × √days`
4. PostGIS spatial query — find aquifers intersecting the plume polygon
5. POST to `ML_SERVICE_URL/predict` for concentration/vulnerability predictions (falls back to realistic stubs if unreachable)
6. Compute affected area (`π × rx × ry`)
7. Monte Carlo uncertainty estimation (100 runs, ±15% Gaussian noise)
8. Generate recovery suggestion based on average aquifer porosity
9. Persist to `Simulation` record + insert `SimulationAquifer` junction rows

Real-time progress is pushed to the frontend via Socket.io on the `useSimulationWebSocket` hook.

### Frontend Architecture

```
frontend/src/
├── api/
│   ├── axiosInstance.ts   # Axios with queue-based token refresh on 401
│   └── *.ts               # Per-resource API modules
├── redux/slices/
│   ├── authSlice.ts        # Access/refresh tokens, current user
│   ├── simulationsSlice.ts # Active simulation tracking
│   └── uiSlice.ts          # Modals, drawers, alerts
├── pages/                  # 7 lazy-loaded page components
├── components/             # Feature-organized UI components
├── hooks/                  # Custom hooks (useRBAC, useSimulationWebSocket, etc.)
├── routes/
│   ├── AppRoutes.tsx       # Route definitions with React.lazy
│   └── ProtectedRoute.tsx  # Auth guard + role guard
└── websocket/              # Socket.io client setup
```

**State management:**
- **Redux** — auth tokens (needed outside React tree in axiosInstance), active simulations, UI state
- **React Query** — all server data with 5-min stale / 10-min GC; handles background refetch

**Token refresh:** The axios interceptor queues all concurrent requests during a refresh, replays them on success, and dispatches logout on failure — preventing thundering-herd duplicate refresh calls.

**RBAC:** `useRBAC` hook gates UI elements. `ProtectedRoute` with `allowedRoles` prop gates routes. Backend enforces the same rules via `require_roles()` in `dependencies.py`.

### End-to-End Simulation Flow

```
Frontend                  FastAPI               Celery Worker          DB / ML
   │                         │                       │                   │
   ├─ POST /simulations ────►│                       │                   │
   │                         ├─ INSERT Simulation ──────────────────────►│
   │                         ├─ Enqueue task ───────►│                   │
   │◄─ {id, status:pending} ─┤                       │                   │
   │                         │                       ├─ UPDATE running ─►│
   │                         │                       ├─ Load ISR geom ──►│
   │                         │                       ├─ Compute ADE plume│
   │                         │                       ├─ Spatial query ──►│
   │                         │                       ├─ POST /predict ──►ML
   │                         │                       ├─ Monte Carlo      │
   │                         │                       ├─ UPDATE completed►│
   │◄─ WS: progress events ──┼───────────────────────┤                   │
   │                         │                       │                   │
   ├─ GET /simulations/{id} ►│                       │                   │
   │◄─ Full result JSON ─────┤                       │                   │
```

---

## API Reference

All routes are prefixed `/api/v1`. Swagger UI available at `http://localhost:8000/docs`.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/token` | public | Login, returns access + refresh tokens |
| POST | `/auth/refresh` | refresh token | Issue new access token |
| GET | `/auth/me` | any role | Current user info |
| GET/POST | `/users` | admin | User management |
| GET/POST/PATCH/DELETE | `/districts` | viewer+ | District CRUD + spatial queries |
| GET/POST/PATCH/DELETE | `/blocks` | viewer+ | Block CRUD |
| GET/POST/PATCH/DELETE | `/aquifers` | viewer+ | Aquifer CRUD |
| GET/POST/PATCH/DELETE | `/isr-points` | analyst+ | ISR injection point management |
| POST | `/simulations` | analyst+ | Trigger new simulation |
| GET | `/simulations/{id}` | viewer+ | Poll simulation status and results |
| POST | `/ingest` | analyst+ | Bulk GeoJSON / Excel / CSV upload |
| GET | `/monitoring-stations` | viewer+ | Monitoring station time-series |
| GET | `/water-samples` | viewer+ | Water sample records |
| GET | `/metrics` | public | Prometheus metrics |

---

## Test Credentials

Seeded by `python -m scripts.seed`:

| Role | Email | Password | Permissions |
|---|---|---|---|
| admin | `admin@jaldrishti.local` | `admin123` | Full access, user management |
| analyst | `analyst@jaldrishti.local` | `analyst123` | Run simulations, edit ISR points |
| viewer | `viewer@jaldrishti.local` | `viewer123` | Read-only |

---

## Running Tests

Tests use in-memory SQLite (no PostGIS required). Spatial queries are mocked.

```bash
cd backend
pytest tests/                                       # all tests
pytest tests/test_auth.py::test_login_success -v   # single test
```

---

## Known Limitations

- **`ml-service` directory is absent** — `docker-compose up` will fail unless the `ml-service` block is removed from `docker-compose.yml`. The backend falls back to realistic stub predictions automatically when `ML_SERVICE_URL` is unreachable.
- **Simulation gradient angle is stubbed** — currently uses `random.uniform(30, 90)`; real piezometric data integration is pending.
- **`KEYS` command in cache invalidation** — `cache_invalidate_pattern()` uses Redis `KEYS` (O(N)); replace with `SCAN` before high-traffic use.
- **TypeScript errors present** — run `npm run build` in `frontend/` to see current type errors before making frontend changes.
- **No rate limit on simulation enqueue** — a user can queue many Celery tasks via repeated `POST /simulations`.
