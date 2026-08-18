# Deploying JalDrishti

**Written:** 2026-08-19 (R10). Verified against this checkout, a live PostGIS
database and a running API — not written from memory.

---

## 0. The question, answered directly

> *"I will deploy the backend individually. I will deploy the frontend
> individually. I will change the frontend to attach the backend endpoint. Is
> that right, or is it one thing?"*

**Two services is right, and it is what this repo is already shaped for.** The
backend is a Python ASGI application that needs a PostGIS database and ~80 MB of
data files on disk; the frontend is a Vite build whose output is pure static
assets. They have nothing in common at runtime — different languages, different
scaling behaviour, different failure modes — and hosting the static bundle from
the API process would mean paying for a Python container to serve JavaScript.

**The third sentence is the one to correct.** You should *not* have to "change
the frontend to attach the backend endpoint", and there is a reason to prefer
the option where you don't. Today the frontend calls `/api/v1/...` as a
**same-origin relative path**; `vite.config.ts` proxies it to `:8000` in
development, and no `fetch` call anywhere in the codebase names a host:

```ts
// frontend/portal/vite.config.ts — the existing dev arrangement
proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
```

So you have two ways to go to production, and they differ in exactly one place.

---

## 1. Architecture — pick one of two, and know the trade

### Option A — one origin behind a gateway (**recommended**)

Put the static frontend and the API behind a single hostname, and route by path:

```
https://jaldrishti.example.org/          →  static bundle (frontend/portal/dist)
https://jaldrishti.example.org/api/...   →  the FastAPI service
```

- **No code change.** The relative `/api/v1/...` paths already work.
- **No CORS.** The browser makes same-origin requests, so there is no preflight,
  no allowlist, and no class of bug where production fails in a way development
  cannot reproduce.
- **Cookies and auth stay simple** if you ever move off bearer tokens.
- **Cost:** you need something that does path routing — Nginx, Caddy, Cloudflare,
  or a platform that offers it natively (Vercel/Netlify rewrites, Render, Fly).

### Option B — split origins with an absolute API URL

Frontend on `app.example.org`, API on `api.example.org`.

- Requires a **build-time environment variable**. The API client would need to
  read `import.meta.env.VITE_API_BASE` and prefix requests with it. That change
  does not exist in the codebase yet — `frontend/portal/src/api/client.ts` uses
  bare relative paths — so Option B is the one that costs you an edit.
- Requires a **CORS allowlist** on the backend. `CORS_ORIGINS` already exists in
  `backend/.env`, so the setting is there; you must set it to the exact frontend
  origin and never to `*` once credentials are involved.
- **Buys you:** independent domains and the ability to point a mobile client at
  the same API later.

**Recommendation:** Option A. For a fellowship project the gateway is one config
file, and it removes an entire category of production-only failure. Choose B
only if you already know you need a separately addressable API.

---

## 2. Database — Postgres 16 + PostGIS, and the two-role setup

### 2.1 Provision

You need Postgres **16** with the **PostGIS** extension available. Managed
options that carry PostGIS: Supabase, Neon, Render Postgres, Railway, AWS RDS,
Azure Database for PostgreSQL. A plain "Postgres" add-on without PostGIS will
fail at `scripts.init_db`, which creates the extension.

### 2.2 The two roles — get this right or RLS is silently inert

This is the single most consequential step in the deployment, and it fails
**quietly**. Postgres skips row-level security entirely for a superuser or any
role with `BYPASSRLS`. If the API connects as the owner role, all 19 policies
from migration `0009` still exist, still review cleanly, and **enforce nothing** —
which is worse than having no policies, because the schema claims protection it
is not providing.

So there are two roles, with two URLs:

| Variable | Role | Used for | Privileges |
|---|---|---|---|
| `MIGRATION_DATABASE_URL` | the owner | `alembic upgrade head`, `scripts.init_db` | can DDL, owns the tables |
| `DATABASE_URL` | `jaldrishti_app` | **the running API** | `LOGIN NOSUPERUSER NOBYPASSRLS`, no DDL, no table ownership |

Create the application role:

```bash
cd backend && python -m scripts.create_app_role
```

Then apply the schema with the owner URL, and run the app with the app URL.

### 2.3 Verify it actually applies

The application checks itself at startup (`app/main.py::_warn_if_rls_is_inert`).
On a correct deployment the log says:

```
Row-level security active: 19 policies, connected as 'jaldrishti_app' (no bypass).
```

If instead you see `ROW-LEVEL SECURITY IS INERT`, the API is connected as a
bypassing role and **access control has silently degraded to application-layer
only**. Treat that line as a failed deployment. It is a warning rather than a
hard abort deliberately — a database that cannot answer the check should not
stop the service — so nothing will stop you shipping past it except reading it.

### 2.4 Migrations

```bash
cd backend && alembic upgrade head        # uses MIGRATION_DATABASE_URL
```

Head is `0019_retire_regulator`. Note that `0019` **cannot** drop the
`regulator` label from the `userrole` enum — PostgreSQL will not remove an enum
value inside a transaction — so the label remains in the type forever. The role
is retired in the *application vocabulary* only, and `tests/test_p6_roles.py`
is what keeps it that way. Do not "tidy up" by reintroducing it.

---

## 3. Secrets and environment

`backend/.env` is gitignored, and **nothing sensitive is tracked** — verified
with `git ls-files` against `.env`, secret and credential patterns; the result is
empty. Keep it that way: supply production values through your host's secret
manager, never through a committed file.

### What must be set in production

| Key | Notes |
|---|---|
| `DATABASE_URL` | the **`jaldrishti_app`** role — see §2.2 |
| `MIGRATION_DATABASE_URL` | the owner role; needed only when migrating |
| `JWT_SECRET`, `JWT_REFRESH_SECRET` | **rotate these.** Generate fresh: `python -c "import secrets;print(secrets.token_urlsafe(64))"`. Note the names — these are the JWT signing secrets; there is no `SECRET_KEY` in this codebase |
| `APP_ENV` | `production` |
| `CORS_ORIGINS` | only if you chose Option B; the exact frontend origin, never `*` |
| `RATE_LIMIT_PER_MINUTE` | slowapi; keep a real limit |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | **set this deliberately.** The local `.env` uses `15`; the code default is `480`. There is **no refresh endpoint** — a 401 clears the token and forces a re-login — so 15 minutes means users are signed out mid-task with no recovery. Use `480` unless you build a refresh flow |

### Keys present in `.env` that this deployment does **not** need

`REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `ML_SERVICE_URL`,
`S3_*`, `AWS_*`, `SENTRY_DSN`. There is **no Celery, Redis or task queue in this
codebase** — simulations run as in-process FastAPI background tasks. These are
leftovers from an earlier architecture. Leave them unset; do not provision
infrastructure to satisfy them.

---

## 4. Datasets — what actually has to ship

The engine reads from disk, so files must be on the container. The good news is
that the working set is far smaller than the `Datasets/` directory suggests.

| Path | On disk | Tracked in git | Needed at runtime |
|---|---|---|---|
| `Datasets/` (whole directory) | **1.2 GB** | 29 files, **67 MB** | only the tracked part |
| `Datasets/jharkhand_glo30_dem.tif` | 671 MB | **no** (gitignored) | **no** — build-time only |
| `Datasets/HydroRIVERS_v10_as_shp/` | 362 MB | **no** (gitignored) | **no** — build-time only |
| `Datasets/naquim_reference/` PDFs | 113 MB | partly | no |
| `ml_pipeline/data_prep/artifacts/` | ~750 KB | **yes** | **yes** — precomputed fields |
| `ml_pipeline/ml/artifacts/` | 12 MB | yes (5 files, 32 KB tracked) | **yes** — model + conformal calibration |

**Why the 671 MB DEM does not ship.** `flow_field.py` and `drainage.py` name it,
which looks alarming, but they only open it in the *build* path. At runtime
`load_flow_field()` reads the precomputed, git-tracked
`ml_pipeline/data_prep/artifacts/flow_field.npz`. A clean `git clone` therefore
serves the API correctly without the DEM — verified by reading the load path,
and consistent with the flow-field layer rendering in the portal.

**The constraint this creates:** you cannot rebuild the flow, drainage or strike
fields on the deployed host. That is fine — those are baked artifacts with their
own provenance — but if you ever need to regenerate them, do it locally where the
DEM exists and commit the resulting `.npz`.

So: **deploy from a git clone**, not from a copy of your working directory. A
`docker build` over the working tree would drag 1.1 GB of build-time rasters into
the image. Add a `.dockerignore` mirroring the `Datasets/` entries in
`.gitignore`.

---

## 5. Seeding, and the demo accounts

```bash
cd backend
python -m scripts.init_db      # PostGIS extension + enum types + tables
python -m scripts.seed         # idempotent: users + ISR points + Jharkhand geodata
```

### The demo accounts must not survive into production

`scripts/seed.py` creates one account per role with **weak, public passwords**
(`admin123`, `analyst123`, `field123`, `citizen123`), and the login screen
`frontend/portal/src/pages/Login.tsx` **lists all four on screen with their
passwords** as click-to-fill buttons. That is correct for a fellowship demo and
unacceptable on a public host — it is a documented administrator credential.

Before any deployment reachable from the internet:

1. Create a real admin account with a strong password.
2. Delete or disable the four seeded accounts.
3. Remove the `DEMO_USERS` block from `Login.tsx` (or gate it on
   `import.meta.env.DEV`) and rebuild the frontend.

If you are deploying only for a supervised demo, keep them — but then keep the
deployment behind authentication or an unlisted URL, and never point a public
link at it.

> **Fixed in R10:** `seed.py` previously also created a `regulator` account,
> which would have reintroduced the role migration `0019` retired on every clean
> install. That address is now in `RETIRED_USER_EMAILS`, so a reseed removes it
> rather than minting it.

---

## 6. Building and running

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production put it behind more than one worker only if you have measured it —
simulations run **in-process**, so a worker that is solving transport is not
serving requests. Two to four workers is a reasonable starting point; the
engine solves in roughly 0.26 s warm, but a 12-point, 4-species lifecycle trace
is ~48 solves and takes tens of seconds. Set your gateway's read timeout above
60 s or the report's lifecycle chart will fail in production while working
locally.

### Frontend

```bash
cd frontend/portal
npm ci
npm run build          # tsc -b && vite build  →  dist/
```

Serve `dist/` as static files. It is a single-page app, so **all unmatched
routes must fall back to `index.html`** or a refresh on `/report/:siteId` will
404.

Bundle sizes as built: `index.js` 550 KB (163 KB gzipped) and a separate
`html2pdf.js` chunk of 985 KB (286 KB gzipped). The PDF chunk is **dynamically
imported** and is fetched only when a user clicks *Download PDF*, so it does not
affect first load.

---

## 7. Recommended hosting — simplest path first

| Piece | Service | Rough cost |
|---|---|---|
| Postgres + PostGIS | **Supabase** free tier, or **Neon** free tier | $0 to start; ~$25/mo at scale |
| API container | **Render** web service or **Fly.io** | Free tier possible; ~$7/mo for always-on |
| Static frontend | **Cloudflare Pages**, **Netlify** or **Vercel** | $0 |
| Path routing (Option A) | Cloudflare Pages rewrite, or Netlify `_redirects` | $0 |

**Simplest concrete path:** Neon or Supabase for the database; Render for the
API (it reads `requirements.txt`, gives you a Dockerfile-free deploy, and holds
secrets); Cloudflare Pages for the frontend with a rewrite sending `/api/*` to
the Render URL. That is Option A with no code change and no CORS, for roughly
$7/month.

Two cautions for free tiers: containers that **sleep** make the first engine run
after idle look broken (cold start plus artifact load), and free Postgres tiers
often cap storage below what the seeded geodata needs — check before committing.

---

## 8. Pre-deployment checklist

- [ ] `alembic upgrade head` applied with `MIGRATION_DATABASE_URL` (head = `0019_retire_regulator`)
- [ ] `python -m scripts.create_app_role` run; `DATABASE_URL` points at `jaldrishti_app`
- [ ] Startup log reads **`Row-level security active: 19 policies … (no bypass)`** — not `INERT`
- [ ] `JWT_SECRET` and `JWT_REFRESH_SECRET` rotated to fresh random values
- [ ] `APP_ENV=production`
- [ ] Demo accounts removed, and the demo-credential list removed from `Login.tsx`
- [ ] A real admin account exists with a strong password
- [ ] Gateway configured (Option A) **or** `VITE_API_BASE` implemented and `CORS_ORIGINS` set (Option B)
- [ ] SPA fallback to `index.html` configured for client-side routes
- [ ] Gateway read timeout ≥ 60 s (lifecycle traces)
- [ ] Deployed from a **git clone**; `.dockerignore` excludes the build-time rasters
- [ ] `ml_pipeline/data_prep/artifacts/` and `ml_pipeline/ml/artifacts/` present on the host
- [ ] `python -m scripts.authz_matrix` re-run and `docs/roles.md` committed
- [ ] `python -m pytest tests -q` green in `backend/`
- [ ] `python -m pytest ml_pipeline/tests -q` green (332)
- [ ] `npx tsc --noEmit` and `npm run build` clean
- [ ] `git ls-files` confirms no `.env` or secret is tracked

---

## 9. Known issues to weigh before shipping

- **`react-router-dom` 6.28** carries two moderate advisories (open redirect via
  backslash in `<Link>`/`useNavigate`; constructor injection in SSR hydration —
  the latter does not apply, this app does not use SSR). Upgrading crosses a
  major version, so it is a deliberate change, not a patch. Decide before a
  public deployment.
- **The five `POST /ingest/*` routes admit `analyst`** (finding D-2 in
  `docs/roles.md`), meaning an analyst can overwrite reference geography. On a
  multi-user deployment, narrow them to `require_admin` first.
- **`/metrics` is unauthenticated** (Prometheus). Do not expose it publicly;
  restrict it at the gateway.
- **There is no token refresh.** `JWT_REFRESH_SECRET` and
  `REFRESH_TOKEN_EXPIRE_DAYS` exist in `.env` but nothing implements them: the
  backend exposes no `/auth/refresh`, and the frontend clears the token on any
  401. Session length is therefore exactly `ACCESS_TOKEN_EXPIRE_MINUTES`, with a
  hard sign-out at the end of it. See the note in §3.
