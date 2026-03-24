# JalDrishti – Groundwater Contamination Assessment Platform

JalDrishti is a modern **Groundwater Contamination ISR (In-Situ Recovery) Impact Assessment Platform**. It models how uranium and other contaminant plumes propagate through aquifer systems from ISR mining injection points. It supports spatial queries, async physics simulations, machine learning-based predictions, and comprehensive role-based access control (RBAC).

## 🌟 Key Features
- **Spatial Data:** Built-in support for MultiPolygon boundaries for districts, administrative blocks, and aquifers using PostGIS.
- **Asynchronous Physics Simulations:** Advection-Dispersion Equation (ADE) plume geometry and Monte Carlo uncertainty estimation powered by Celery worker tasks.
- **ML Integration:** Supports falling back to realistic prediction stubs or real ML microservice integrations for concentration and vulnerability assessments.
- **RBAC (Role-Based Access Control):** Granular access levels (Admin, Analyst, Viewer).
- **Interactive UI:** React + TypeScript single-page application built on Material UI (MUI), featuring data grids and map-ready abstractions.

## 🏗️ Technology Stack
### Backend
- **Framework:** FastAPI (Python 3.10+) ⚡
- **ORM & Database:** SQLAlchemy 2.0 (Async), PostgreSQL 14+, PostGIS 3.4
- **Task Queue & Caching:** Celery, Redis
- **Authentication:** JWT (Access & Refresh tokens)
- **Migrations:** Alembic

### Frontend
- **Framework:** React 18 + TypeScript + Vite
- **Global Data State:** Redux Toolkit
- **Server State & Caching:** TanStack React Query
- **Styling:** Material UI (MUI v5) + Tailwind CSS

---

## 🚀 Setup & Installation (Local Development)

### 📋 Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ (with `PostGIS` extension installed)
- Redis server (for caching and backend tasks)

### 🗄️ 1. Database Setup
Ensure PostgreSQL is running, then create the database and enable PostGIS:
```sql
CREATE DATABASE groundwater_db;
\c groundwater_db
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 🐍 2. Backend Setup
1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .\.venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables. The default `.env` will connect to `groundwater_db` on localhost with the user `postgres` and password `040812` (update `backend/.env` if your DB credentials are different).
5. Run Alembic migrations to build the schema:
   ```bash
   alembic upgrade head
   ```
6. Seed the database with default users:
   ```bash
   python -m scripts.seed
   ```
7. Start the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```
   *The API will be running at `http://localhost:8000`. Swagger API documentation is available at `/docs`.*

### ⚛️ 3. Frontend Setup
1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   *The application will be accessible at `http://localhost:5173`.*

---

## 🔑 Test Credentials
The `seed.py` script automatically creates three default users corresponding to the available system roles:

| Role | Email | Password | Allowed Actions |
|------|-------|----------|-----------------|
| **Admin** | `admin@jaldrishti.local` | `admin123` | Full access, manage users, run simulations, edit ISR points |
| **Analyst** | `analyst@jaldrishti.local` | `analyst123` | Create & view simulations, edit ISR points, view models |
| **Viewer** | `viewer@jaldrishti.local` | `viewer123` | Read-only access to districts, aquifers, and simulations |

---

## 📂 Project Structure
```text
JalDrishti/
├── backend/                  # FastAPI Application
│   ├── app/
│   │   ├── api/              # API v1 Routers (Auth, Districts, Simms, etc.)
│   │   ├── models/           # SQLAlchemy ORM Models (Spatial, Users)
│   │   ├── repositories/     # Data Access layer
│   │   ├── services/         # Core business logic (Simulations, Auth)
│   │   ├── tasks/            # Celery async tasks
│   │   └── main.py           # Application Factory
│   ├── scripts/              # DB Seeding and debugging scripts
│   └── alembic/              # Database schema migrations
├── frontend/                 # React Application
│   ├── src/
│   │   ├── api/              # Axios instances & interceptors
│   │   ├── components/       # Shared UI components
│   │   ├── pages/            # React Router page views
│   │   ├── redux/            # Store and slices (Auth, UI)
│   │   └── routes/           # RBAC-protected Router definitions
└── docker-compose.yml        # (Experimental) Stack orchestration
```

## 🐳 Docker Deployment (Experimental)
The repository includes a `docker-compose.yml` for containerized setups. However, as the `ml-service` microservice component is a WIP, running via Docker currently requires configuring or commenting out the `ml-service` dependency within the compose manifest.

```bash
docker-compose up --build
```
This spawns the PostgreSQL/PostGIS db, Redis cache, FastAPI backend, and Celery worker synchronously.

---
*Developed for the JalDrishti Groundwater Impact Assessment Platform.*
