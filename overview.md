# JalDrishti — Complete Developer Overview

> Written for an **intermediate backend developer** who wants to understand the full system,
> study it in the right order, and know what can be safely simplified.

---

## 1. Final Objective of the Project

JalDrishti's final objective is:

> **To give government officials, hydrogeologists, and environmental analysts a single platform where they can upload spatial data, run physics-based contamination simulations, and visually assess which aquifers are at risk from ISR (In-Situ Recovery) uranium mining operations in Jharkhand, India.**

In plain terms:

- Uranium mining (ISR method) involves injecting chemicals underground to dissolve ore.
- This creates contamination plumes that spread through groundwater aquifers.
- JalDrishti models **where** that contamination goes, **how far** it spreads, and **how bad** it is.
- It also tracks real monitoring well data to compare simulated predictions against ground truth.
- Decision makers can then see contamination risk on a map and plan remediation.

The platform is **not** a real-time sensor dashboard. It is a **simulation + data management + spatial visualization** tool.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLIENT BROWSER                               │
│  React 18 + TypeScript + Leaflet (Map) + Redux + React Query         │
│  Port 5173 (Vite dev) or built static files                          │
└───────────────────────┬──────────────────────────────────────────────┘
                        │ HTTP (REST) + WebSocket
                        ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND  :8000                          │
│                                                                      │
│  api/v1/         → Route handlers (12 modules, auth + RBAC)         │
│  services/       → Business logic, physics, spatial, ML calls        │
│  repositories/   → Database access (Generic BaseRepository + custom) │
│  models/         → SQLAlchemy 2.0 ORM (17 tables)                   │
│  schemas/        → Pydantic v2 request/response validators           │
│  tasks/          → Celery task definitions                           │
│  cache.py        → Redis async wrapper                               │
│  dependencies.py → FastAPI DI: get_db, get_current_user, RBAC       │
└──────────┬──────────────────┬─────────────────────┬─────────────────┘
           │                  │                      │
           ▼                  ▼                      ▼
┌──────────────────┐ ┌───────────────────┐ ┌────────────────────────┐
│  PostgreSQL 16   │ │  Redis :6379       │ │  ML Microservice :8001 │
│  + PostGIS 3.4   │ │  db/0 = cache      │ │  (optional, stubs ok)  │
│  :5432           │ │  db/1 = broker     │ │  POST /predict         │
│  groundwater_db  │ │  db/2 = results    │ └────────────────────────┘
└──────────────────┘ └────────┬──────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │  Celery Worker      │
                   │  (async task queue) │
                   │  + Flower UI :5555  │
                   └─────────────────────┘
```

### Data Flow for the Core Feature (Simulation)

```
User clicks "Run Simulation" on ISR Point
       │
       ▼
POST /simulations/{isr_id}
       │
       ▼
Create Simulation record (status=pending)
Queue Celery task: run_simulation_task(sim_id)
       │
       ▼ (inside Celery worker, async)
SimulationService.run(sim_id):
  1. Get ISR point coordinates from PostGIS geometry
  2. Compute groundwater gradient angle (stubbed: random 30–90°)
  3. Compute plume ellipse (Advection-Dispersion Equation):
       rx = dispersivity_L × √days   (longitudinal radius)
       ry = dispersivity_T × √days   (transverse radius)
     → 36-point polygon WKT
  4. ST_Intersects query → find all aquifers inside plume
  5. POST to ML service (or use stubs if unavailable)
  6. Compute affected_area = π × rx × ry
  7. Monte Carlo uncertainty (100 runs, ±15% Gaussian noise)
  8. Recovery suggestion (based on aquifer porosity)
  9. Persist results → Simulation table + SimulationAquifer junction
 10. Refresh district/block aggregates
       │
       ▼
Client polls GET /simulations/{sim_id} → status="completed" + results
```

---

## 3. All Modules Explained

### Backend Entry Points

| File | What it does |
|------|-------------|
| [backend/app/main.py](backend/app/main.py) | FastAPI app factory: creates app, registers routers, mounts CORS, rate limiting, Prometheus, WebSocket, global exception handlers |
| [backend/app/config.py](backend/app/config.py) | Pydantic Settings — reads `.env` into typed Python object. Single source of truth for all config values |
| [backend/app/database.py](backend/app/database.py) | Creates async SQLAlchemy engine + `AsyncSession` factory. `get_db()` yields a session per request |
| [backend/app/dependencies.py](backend/app/dependencies.py) | FastAPI DI: `get_current_user` (decodes JWT), `require_roles(*roles)` (RBAC factory), `get_db` re-export |
| [backend/app/cache.py](backend/app/cache.py) | Thin async Redis wrapper: `cache_get`, `cache_set`, `cache_invalidate_pattern`. All ops are graceful (return None on failure) |
| [backend/app/celery_app.py](backend/app/celery_app.py) | Creates Celery instance, connects broker (Redis db/1) + result backend (Redis db/2) |
| [backend/app/exceptions.py](backend/app/exceptions.py) | Custom exception classes: `AppException`, `ResourceNotFoundError`, `AuthenticationError`, `SimulationDataError`, etc. |

### Models (Database Tables — 17 total)

| File | Tables | Key Relationships |
|------|--------|------------------|
| [backend/app/models/user.py](backend/app/models/user.py) | `users` | standalone |
| [backend/app/models/district.py](backend/app/models/district.py) | `districts` | 1:N → blocks |
| [backend/app/models/block.py](backend/app/models/block.py) | `blocks` | N:1 district, 1:N aquifers, 1:N monitoring_stations |
| [backend/app/models/aquifer.py](backend/app/models/aquifer.py) | `aquifers` | N:1 block, N:N simulations (via junction) |
| [backend/app/models/isr_point.py](backend/app/models/isr_point.py) | `isr_points` | 1:N simulations |
| [backend/app/models/simulation.py](backend/app/models/simulation.py) | `simulations`, `simulation_aquifers` (junction), `plume_parameters` | N:1 isr_point, N:N aquifers |
| [backend/app/models/monitoring_station.py](backend/app/models/monitoring_station.py) | `monitoring_stations`, `groundwater_level_readings` | N:1 block, 1:N readings |
| [backend/app/models/monitoring_well.py](backend/app/models/monitoring_well.py) | `monitoring_wells` | N:1 block, 1:N water_samples |
| [backend/app/models/water_sample.py](backend/app/models/water_sample.py) | `water_samples` | N:1 monitoring_well |
| [backend/app/models/hydraulic_head.py](backend/app/models/hydraulic_head.py) | `hydraulic_heads` | N:1 aquifer |
| [backend/app/models/contamination_event.py](backend/app/models/contamination_event.py) | `contamination_events` | N:1 isr_point |
| [backend/app/models/data_source.py](backend/app/models/data_source.py) | `data_sources` | referenced by water_samples |
| [backend/app/models/piezometric_head.py](backend/app/models/piezometric_head.py) | `piezometric_heads` | N:1 monitoring_station |
| [backend/app/models/ml_model.py](backend/app/models/ml_model.py) | `ml_models` | standalone (version registry) |
| [backend/app/models/spatial_analysis_result.py](backend/app/models/spatial_analysis_result.py) | `spatial_analysis_results` | N:1 simulation, N:1 aquifer |

### API Routes (12 modules)

| File | Prefix | Roles |
|------|--------|-------|
| [backend/app/api/v1/auth.py](backend/app/api/v1/auth.py) | `/auth` | public |
| [backend/app/api/v1/users.py](backend/app/api/v1/users.py) | `/users` | admin only |
| [backend/app/api/v1/districts.py](backend/app/api/v1/districts.py) | `/districts` | viewer(read), analyst+(write) |
| [backend/app/api/v1/blocks.py](backend/app/api/v1/blocks.py) | `/districts/{id}/blocks` | viewer(read), analyst+(write) |
| [backend/app/api/v1/aquifers.py](backend/app/api/v1/aquifers.py) | `/aquifers` | viewer(read), analyst+(write) |
| [backend/app/api/v1/isr_points.py](backend/app/api/v1/isr_points.py) | `/isr-points` | viewer(read), analyst+(write) |
| [backend/app/api/v1/simulations.py](backend/app/api/v1/simulations.py) | `/simulations` | analyst+ |
| [backend/app/api/v1/monitoring_stations.py](backend/app/api/v1/monitoring_stations.py) | `/blocks/{id}/monitoring-stations` | viewer(read), analyst+(write) |
| [backend/app/api/v1/monitoring_wells.py](backend/app/api/v1/monitoring_wells.py) | `/monitoring-wells` | viewer(read), analyst+(write) |
| [backend/app/api/v1/water_samples.py](backend/app/api/v1/water_samples.py) | `/water-samples` | viewer(read), analyst+(write) |
| [backend/app/api/v1/ingest.py](backend/app/api/v1/ingest.py) | `/ingest` | analyst+ |
| [backend/app/api/v1/global_blocks.py](backend/app/api/v1/global_blocks.py) | `/blocks` | viewer |
| [backend/app/api/v1/global_monitoring.py](backend/app/api/v1/global_monitoring.py) | `/monitoring-stations` | viewer |

### Services (Business Logic — most important files)

| File | Complexity | What to focus on |
|------|-----------|-----------------|
| [backend/app/services/simulation.py](backend/app/services/simulation.py) | HIGH | The physics: plume ellipse, Monte Carlo, ML call, PostGIS spatial query |
| [backend/app/services/ingestion.py](backend/app/services/ingestion.py) | HIGH | GeoJSON/CSV parsing, spatial block assignment, data provenance |
| [backend/app/services/auth.py](backend/app/services/auth.py) | LOW | Argon2 hashing, JWT create/decode |
| [backend/app/services/user.py](backend/app/services/user.py) | LOW | Standard CRUD with duplicate checks |
| [backend/app/services/district.py](backend/app/services/district.py) | LOW | District + Block CRUD, geometry string fix |
| [backend/app/services/aquifer.py](backend/app/services/aquifer.py) | MEDIUM | Thickness computation, spatial radius query |
| [backend/app/services/monitoring_station.py](backend/app/services/monitoring_station.py) | LOW | Station CRUD + reading time series |
| [backend/app/services/aggregation.py](backend/app/services/aggregation.py) | MEDIUM | Recomputes district/block-level metrics after simulation |
| [backend/app/services/hydro_literature.py](backend/app/services/hydro_literature.py) | LOW | Lookup table: defaults for porosity/hydraulic conductivity by rock type |

### Repositories (Data Access)

| File | Special queries |
|------|----------------|
| [backend/app/repositories/base.py](backend/app/repositories/base.py) | Generic CRUD: `get`, `get_all`, `count`, `create`, `update`, `delete` |
| [backend/app/repositories/aquifer.py](backend/app/repositories/aquifer.py) | `get_within_radius` (ST_DWithin), `get_intersecting_plume` (ST_Intersects) |
| [backend/app/repositories/monitoring_well.py](backend/app/repositories/monitoring_well.py) | `list_in_bbox` (ST_Within bounding box) |
| [backend/app/repositories/monitoring_station.py](backend/app/repositories/monitoring_station.py) | `get_by_block`, reading pagination |
| [backend/app/repositories/water_sample.py](backend/app/repositories/water_sample.py) | Date range filter, newest-first sort |
| [backend/app/repositories/simulation.py](backend/app/repositories/simulation.py) | `get_by_isr_point`, `get_by_task_id` |

### Tasks (Celery)

| File | Task | Behavior |
|------|------|---------|
| [backend/app/tasks/simulation.py](backend/app/tasks/simulation.py) | `run_simulation_task` | Calls `SimulationService.run()`, retries 3× on failure with 10s backoff |
| [backend/app/tasks/aggregation.py](backend/app/tasks/aggregation.py) | `refresh_aggregates_task` | Recomputes district/block metrics after data changes |

### Migrations

| File | What it created |
|------|----------------|
| [backend/alembic/versions/0001_initial.py](backend/alembic/versions/0001_initial.py) | PostGIS extension, enums, all base tables |
| [backend/alembic/versions/0002_add_monitoring_stations.py](backend/alembic/versions/0002_add_monitoring_stations.py) | Monitoring station tables (some overlap with 0001) |
| [backend/alembic/versions/0003_drop_monitoring_data.py](backend/alembic/versions/0003_drop_monitoring_data.py) | Drops old monitoring_data table |
| [backend/alembic/versions/0004_month3_schema.py](backend/alembic/versions/0004_month3_schema.py) | data_sources, monitoring_wells, water_samples, contamination_events, piezometric_heads, spatial_analysis_results |

---

## 4. Recommended Reading Sequence (Intermediate Backend Dev)

Follow this order. Each phase builds on the previous one.

### Phase 1 — Foundation (Day 1–2)

Goal: Understand what the app is and how it starts.

```
1. docker-compose.yml           ← What infrastructure runs
2. backend/.env                 ← What config values exist
3. backend/app/config.py        ← How config is typed in Python
4. backend/app/database.py      ← How DB sessions work (async SQLAlchemy)
5. backend/app/main.py          ← How the app is assembled
6. backend/requirements.txt     ← What libraries are used and why
```

**Concepts to study at this phase:**
- FastAPI application factory pattern
- Pydantic BaseSettings
- SQLAlchemy 2.0 async engine (`create_async_engine`, `AsyncSession`)
- CORS middleware

---

### Phase 2 — Database Models (Day 2–3)

Goal: Understand the data schema before looking at any logic.

```
7.  backend/app/models/base.py          ← UUIDPrimaryKeyMixin + TimestampMixin
8.  backend/app/models/user.py          ← Simplest model
9.  backend/app/models/district.py      ← Geometry column (PostGIS)
10. backend/app/models/block.py         ← FK relationships
11. backend/app/models/aquifer.py       ← Most field-rich model
12. backend/app/models/isr_point.py     ← POINT geometry
13. backend/app/models/simulation.py    ← Junction table pattern (SimulationAquifer)
14. backend/app/models/monitoring_station.py  ← 1:N time series pattern
15. backend/app/models/monitoring_well.py
16. backend/app/models/water_sample.py  ← Most chemistry fields
17. backend/alembic/versions/0001_initial.py  ← How models become SQL
```

Draw this entity diagram as you read:
```
District → Block → Aquifer
                 → MonitoringStation → GroundwaterLevelReading
                 → MonitoringWell → WaterSample
ISRPoint → Simulation ←→ Aquifer (SimulationAquifer junction)
```

---

### Phase 3 — Auth & Security (Day 3)

Goal: Understand how users log in and how access is controlled.

```
18. backend/app/models/user.py       ← User + role enum
19. backend/app/services/auth.py     ← Argon2 hashing, JWT creation
20. backend/app/dependencies.py      ← get_current_user, require_roles
21. backend/app/api/v1/auth.py       ← Login, signup, refresh endpoints
22. backend/app/schemas/auth.py      ← Request/response shapes
```

---

### Phase 4 — Repository & Service Pattern (Day 4)

Goal: Understand the data access abstraction before reading complex services.

```
23. backend/app/repositories/base.py     ← Generic CRUD (read carefully)
24. backend/app/repositories/user.py     ← How base is extended
25. backend/app/services/user.py         ← How service uses repository
26. backend/app/api/v1/users.py          ← How API uses service
27. backend/app/schemas/user.py          ← What flows in and out
```

This gives you the full vertical slice: `API → Service → Repository → Model`.

---

### Phase 5 — Spatial Features (Day 5)

Goal: Understand how PostGIS is used for geographic queries.

```
28. backend/app/repositories/aquifer.py         ← ST_DWithin, ST_Intersects
29. backend/app/repositories/monitoring_well.py ← ST_Within bounding box
30. backend/app/services/aquifer.py             ← list_within_radius usage
31. backend/app/api/v1/aquifers.py              ← Spatial filter endpoint
32. backend/alembic/versions/0001_initial.py    ← GIST index creation
```

**Key PostGIS functions to study:**
- `ST_DWithin(geom, point, distance)` — radius search
- `ST_Intersects(geom1, geom2)` — overlap test
- `ST_Within(point, bbox)` — containment
- `ST_GeomFromText(wkt, srid)` — WKT string → geometry
- `ST_AsText(geom)` — geometry → WKT string

---

### Phase 6 — Core Domain: Simulation (Day 6–7)

Goal: Understand the central feature of the entire platform.

```
33. backend/app/services/simulation.py   ← Read this very carefully
34. backend/app/tasks/simulation.py      ← How Celery wraps the service
35. backend/app/api/v1/simulations.py    ← Trigger + poll endpoints
36. backend/app/schemas/simulation.py    ← Result shapes
```

While reading `simulation.py`, map each step:
- Step 1–2: Location extraction (WKB parsing)
- Step 3: Plume geometry (_compute_plume_wkt)
- Step 4: Spatial query (ST_Intersects)
- Step 5: ML call (_call_ml_service) + stubs
- Step 6–8: Area, uncertainty, recovery
- Step 9–10: DB persistence + aggregates

---

### Phase 7 — Data Ingestion (Day 8)

Goal: Understand how raw data files become database records.

```
37. backend/app/services/ingestion.py     ← Largest service file (~24KB)
38. backend/app/api/v1/ingest.py          ← Upload endpoints
39. backend/scripts/seed.py               ← How test data is seeded
40. backend/scripts/seed_month3_data.py   ← Month 3 data seeding
```

Focus areas in ingestion.py:
- `_find_block_for_point` — how a lat/lon is assigned to a block via PostGIS
- `_parse_range_midpoint` — how "26-176 m" becomes 101
- `_register_source` — SHA256 checksum deduplication

---

### Phase 8 — Caching & Async Tasks (Day 9)

Goal: Understand Redis usage and async task execution.

```
41. backend/app/cache.py                   ← Redis wrapper
42. backend/app/celery_app.py              ← Celery config
43. backend/app/tasks/aggregation.py       ← Refresh task
44. backend/app/api/v1/monitoring_wells.py ← Cached bbox query
```

---

### Phase 9 — Tests (Day 10)

Goal: Learn how the project is tested and what the test setup looks like.

```
45. backend/tests/conftest.py        ← Fixtures (in-memory SQLite, test client)
46. backend/tests/test_auth.py       ← Auth test examples
47. backend/tests/test_simulations.py ← Core domain tests
```

---

### Phase 10 — Frontend (Day 11–12, optional for backend dev)

If you want to understand the frontend:

```
48. frontend/src/main.tsx            ← Entry point
49. frontend/src/App.tsx             ← Routing
50. frontend/src/api/axiosInstance.ts ← JWT interceptor (auto-refresh)
51. frontend/src/store/              ← Redux slices
52. frontend/src/hooks/useAuth.ts    ← Auth state
53. frontend/src/hooks/useSimulationWebSocket.ts ← Real-time updates
54. frontend/src/components/geospatial/MapView.tsx ← The map
```

---

## 5. Study Resources

### FastAPI & Async Python
- Official FastAPI docs: https://fastapi.tiangolo.com/tutorial/
- FastAPI Beyond CRUD (book-length tutorial): https://fastapi.tiangolo.com/advanced/
- SQLAlchemy 2.0 async docs: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Pydantic v2 docs: https://docs.pydantic.dev/latest/

### PostgreSQL & PostGIS
- PostGIS intro: https://postgis.net/workshops/postgis-intro/
- Key chapter: "Spatial Relationships" (ST_DWithin, ST_Intersects, ST_Within)
- PostgreSQL JSONB guide: https://www.postgresql.org/docs/current/datatype-json.html

### Celery + Redis
- Celery docs (First Steps): https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html
- Redis data structures: https://redis.io/docs/manual/data-types/

### JWT & Security
- JWT intro: https://jwt.io/introduction
- Argon2 docs: https://argon2-cffi.readthedocs.io/

### GeoJSON & Spatial Concepts
- GeoJSON spec: https://geojson.org/
- Coordinate Reference Systems (CRS/SRID): EPSG:4326 = WGS84 = standard lat/lon
- Advection-Dispersion Equation: search "ADE groundwater contamination transport"

### Alembic Migrations
- Alembic tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html

### Testing
- pytest-asyncio docs: https://pytest-asyncio.readthedocs.io/
- httpx AsyncClient docs: https://www.python-httpx.org/async/

---

## 6. What You Can Cut Right Now (Simplification Targets)

These are components that add complexity without being essential to the core objective.
Cut these if you want to understand or demo the project faster.

### Safe to Remove Immediately

| What | File(s) | Why it's safe |
|------|---------|--------------|
| **Flower UI** | docker-compose.yml (flower service) | Just a Celery task monitoring dashboard. Not needed for functionality. |
| **Prometheus metrics** | main.py (`PrometheusInstrumentator`) | Operational observability. Remove the 3 lines in main.py. |
| **Sentry integration** | main.py, requirements.txt (`sentry-sdk`) | Error tracking for production. Remove if just developing. |
| **ML model registry** | models/ml_model.py, migration 0004 | The `ml_models` table is never written to by any service. It's unused. |
| **PiezometricHead model** | models/piezometric_head.py | Duplicates MonitoringStation readings. No API endpoint uses it. |
| **ContaminationEvent model** | models/contamination_event.py | No API endpoint reads or writes to it currently. |
| **SpatialAnalysisResult model** | models/spatial_analysis_result.py | Results are stored in `simulations` table. This table is never populated. |
| **HydraulicHead model** | models/hydraulic_head.py | No endpoint or service uses it. Dead table. |
| **DataSource model** | models/data_source.py | Provenance tracking is good but not critical for MVP. |
| **Rate limiting** | main.py (slowapi), requirements.txt | Only matters in production. Can be removed for development. |
| **`debug_*.py` scripts** | backend/scripts/ | Debugging helpers, not production code. |

### Can Be Simplified (Not Removed)

| What | Current state | Simplification |
|------|--------------|----------------|
| **Celery task queue** | Full Celery + Redis setup | Replace with FastAPI `BackgroundTasks` (already implemented as fallback). Removes Redis/Celery dependency entirely for dev. |
| **Monte Carlo uncertainty** | 100 simulation runs with Gaussian noise | Reduce to 10 runs or use a simple ±15% fixed range. |
| **Groundwater gradient** | Stubbed as random 30–90° | Make it a fixed default (e.g., 45°) until real data is available. |
| **Ingestion service** | 24KB, handles 5 formats | Start with just the GeoJSON district ingestor. Add others as needed. |
| **RBAC** | 3 roles, enforced everywhere | Simplify to just `authenticated` vs `unauthenticated` while building. |
| **Redis caching** | Only used in monitoring_wells bbox | Remove or make optional. The fallback already returns None gracefully. |
| **Global endpoints** | `/blocks`, `/monitoring-stations` (duplicate of nested routes) | Remove the global variants; keep only nested `/districts/{id}/blocks`. |

### The Minimal Core (If You Want to Start Fresh)

The project is really these 5 things:
1. **Auth** — login, JWT, role check
2. **Spatial data** — districts → blocks → aquifers (PostGIS geometry)
3. **ISR points** — injection site locations
4. **Simulation** — plume computation + spatial query
5. **Results** — display what aquifers are affected and by how much

Everything else (monitoring stations, water samples, ingestion, aggregation, caching, ML registry) is support infrastructure that you can add back incrementally.

---

## 7. Complete File Reference

### Backend

```
backend/
├── .env                              ← All environment variables
├── requirements.txt                  ← Python dependencies
├── Dockerfile                        ← Container build
├── alembic.ini                       ← Alembic config
├── alembic/
│   ├── env.py                        ← Migration runner
│   └── versions/
│       ├── 0001_initial.py           ← Base schema
│       ├── 0002_add_monitoring_stations.py
│       ├── 0003_drop_monitoring_data.py
│       └── 0004_month3_schema.py     ← Extended schema
├── scripts/
│   ├── seed.py                       ← Default users + base data
│   ├── seed_month3_data.py           ← Monitoring + water sample data
│   ├── debug_auth.py                 ← Dev helper
│   ├── debug_users.py                ← Dev helper
│   └── test_api_call.py              ← Dev helper
├── tests/
│   ├── conftest.py                   ← Test fixtures
│   ├── test_auth.py
│   └── test_simulations.py
└── app/
    ├── main.py                       ← App factory
    ├── config.py                     ← Settings
    ├── database.py                   ← Async engine
    ├── dependencies.py               ← DI + RBAC
    ├── exceptions.py                 ← Custom exceptions
    ├── cache.py                      ← Redis wrapper
    ├── celery_app.py                 ← Task queue config
    ├── api/
    │   ├── router.py                 ← Aggregates all v1 routers
    │   └── v1/
    │       ├── auth.py
    │       ├── users.py
    │       ├── districts.py
    │       ├── blocks.py
    │       ├── aquifers.py
    │       ├── isr_points.py
    │       ├── simulations.py
    │       ├── monitoring_stations.py
    │       ├── monitoring_wells.py
    │       ├── water_samples.py
    │       ├── ingest.py
    │       ├── global_blocks.py
    │       └── global_monitoring.py
    ├── models/
    │   ├── __init__.py               ← Exports all models (needed by Alembic)
    │   ├── base.py                   ← Mixins: UUID PK + timestamps
    │   ├── user.py
    │   ├── district.py
    │   ├── block.py
    │   ├── aquifer.py
    │   ├── isr_point.py
    │   ├── simulation.py             ← + SimulationAquifer junction + PlumeParameter
    │   ├── monitoring_station.py     ← + GroundwaterLevelReading
    │   ├── monitoring_well.py
    │   ├── water_sample.py
    │   ├── hydraulic_head.py         ← unused
    │   ├── contamination_event.py    ← unused
    │   ├── data_source.py
    │   ├── piezometric_head.py       ← unused
    │   ├── ml_model.py               ← unused
    │   └── spatial_analysis_result.py ← unused
    ├── repositories/
    │   ├── base.py                   ← Generic CRUD
    │   ├── user.py
    │   ├── district.py
    │   ├── aquifer.py                ← Spatial queries
    │   ├── isr_point.py
    │   ├── monitoring_station.py
    │   ├── monitoring_well.py        ← Spatial bbox query
    │   ├── water_sample.py
    │   ├── simulation.py
    │   └── data_source.py
    ├── services/
    │   ├── auth.py
    │   ├── user.py
    │   ├── district.py               ← DistrictService + BlockService
    │   ├── aquifer.py
    │   ├── isr_point.py
    │   ├── monitoring_station.py
    │   ├── monitoring_well.py
    │   ├── water_sample.py
    │   ├── simulation.py             ← CORE DOMAIN LOGIC
    │   ├── ingestion.py              ← Data import pipeline
    │   ├── aggregation.py            ← Post-simulation metrics refresh
    │   └── hydro_literature.py       ← Rock-type defaults lookup
    ├── schemas/
    │   ├── common.py                 ← MessageResponse, JobResponse, PaginatedResponse
    │   ├── auth.py
    │   ├── user.py
    │   ├── district.py               ← District + Block schemas
    │   ├── aquifer.py
    │   ├── simulation.py             ← Simulation + ISRPoint schemas
    │   ├── monitoring_station.py
    │   ├── monitoring_well.py
    │   └── water_sample.py
    └── tasks/
        ├── simulation.py             ← run_simulation_task
        └── aggregation.py            ← refresh_aggregates_task
```

### Frontend

```
frontend/
├── package.json
├── vite.config.ts                    ← Dev server proxy (/api → :8000)
├── tsconfig.json
├── tailwind.config.js
└── src/
    ├── main.tsx                      ← ReactDOM.render + Redux Provider
    ├── App.tsx                       ← React Router routes
    ├── api/
    │   ├── axiosInstance.ts          ← JWT interceptor, auto-refresh
    │   ├── authApi.ts
    │   ├── districtsApi.ts
    │   ├── aquifersApi.ts
    │   ├── isrApi.ts
    │   ├── simulationsApi.ts
    │   └── globalBlocksApi.ts
    ├── components/
    │   ├── layout/                   ← Header, Sidebar, MainLayout
    │   ├── common/                   ← LoadingSpinner, ErrorBoundary
    │   ├── forms/                    ← Domain forms (AquiferForm, IsrPointForm)
    │   ├── geospatial/
    │   │   ├── MapView.tsx           ← Main Leaflet map component
    │   │   └── layers/               ← DistrictLayer, AquiferLayer, PlumeLayer...
    │   ├── districts/
    │   ├── blocks/
    │   ├── aquifers/
    │   ├── isr/
    │   ├── simulations/
    │   └── dashboard/
    ├── contexts/
    │   └── MapContext.tsx            ← Shared map state (zoom, center, active layers)
    ├── hooks/
    │   ├── useAuth.ts
    │   ├── useRBAC.ts                ← Role-based conditional rendering
    │   ├── useSimulationWebSocket.ts ← Real-time simulation progress
    │   ├── useAlerts.ts
    │   ├── useFetchDistricts.ts
    │   ├── useFetchAquifers.ts
    │   ├── useFetchIsrPoints.ts
    │   └── useMonitoringQueries.ts
    └── store/
        ├── index.ts                  ← Redux store setup
        ├── authSlice.ts              ← tokens, user
        ├── simulationsSlice.ts       ← active jobs
        └── uiSlice.ts                ← modals, drawers, alerts
```

---

## 8. Key Architectural Patterns to Understand

### 1. Service → Repository → Model (Layered Architecture)
Every operation flows: `API handler → Service → Repository → Model → DB`.
The API handler never touches the DB directly. The repository never contains business logic.
This separation makes each layer independently testable.

### 2. Dependency Injection via FastAPI
```python
# In dependencies.py
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    ...

def require_roles(*roles):
    async def check(user = Depends(get_current_user)):
        if user.role not in roles:
            raise AuthorizationError()
    return check

# In a route
@router.delete("/{id}", dependencies=[Depends(require_roles("admin"))])
async def delete_district(...):
    ...
```

### 3. Async Everything
All DB calls use `await session.execute(...)`. All service methods are `async def`.
Celery workers call `asyncio.run(service.run(...))` to bridge sync Celery into async service code.

### 4. PostGIS Spatial Queries
Geometries are stored as EWKT (WGS84, SRID=4326). Queries use raw SQL with GeoAlchemy2:
```python
# Example: find aquifers within a plume polygon
await db.execute(
    select(Aquifer).where(
        func.ST_Intersects(Aquifer.geometry, func.ST_GeomFromText(plume_wkt, 4326))
    )
)
```

### 5. Graceful Degradation
- If Redis is down → cache returns None, app continues without cache.
- If Celery/Redis is down → simulation runs in FastAPI BackgroundTask instead.
- If ML service is down → simulation uses stub predictions with realistic ranges.

### 6. JWT Auth Flow
```
Login → server returns access_token (15min) + refresh_token (7days)
Request with expired access_token → 401
Frontend interceptor → POST /auth/refresh with refresh_token
Server returns new access_token
Frontend retries original request
```

---

## 9. Default Test Users

| Role | Email | Password | Can do |
|------|-------|----------|--------|
| admin | admin@jaldrishti.local | admin123 | Everything including delete |
| analyst | analyst@jaldrishti.local | analyst123 | Run simulations, ingest data, CRUD |
| viewer | viewer@jaldrishti.local | viewer123 | Read only |

Seed with: `cd backend && python -m scripts.seed`

---

## 10. Quick Start Commands

```bash
# 1. Full stack with Docker
docker-compose up --build

# 2. Backend only (manual)
cd backend
pip install -r requirements.txt
# Start PostgreSQL + PostGIS separately, then:
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload
# Optional: celery -A app.celery_app worker --loglevel=info

# 3. Frontend only
cd frontend
npm install
npm run dev

# 4. API docs
open http://localhost:8000/docs

# 5. Run tests
cd backend && pytest tests/
```
