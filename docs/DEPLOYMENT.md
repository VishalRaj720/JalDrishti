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

## 8b. The administrator, and the regulator (R12)

**There is exactly one administrator.** It is your account. It operates the
dataset pipeline, the factory reset, the model and account management, and a
second one is not a convenience — it is a second person who can rewrite the
evidence base. `UserService._refuse_second_admin` returns 422 on create and on
promotion, and the `uq_single_admin` partial index in migration `0022` refuses
it again below the application, because an application check is a race between
two requests and an index is not.

**The seed does not create an admin.** `scripts/seed.py` creates one demo
account per *assignable* role — regulator, analyst, field officer, citizen — and
those credentials are weak, public, and excluded from the production frontend
bundle by `import.meta.env.DEV`. The administrator is created separately:

```bash
python -m scripts.bootstrap_admin --email you@example.com
```

The password is **never** taken from an argument — command lines reach shell
history and `ps` output. It is prompted for, or read from
`ADMIN_BOOTSTRAP_PASSWORD` for an automated deploy where the value comes from a
secret store. Only the argon2 hash is written; nothing echoes it back. Run it
again with the same address to reset the password — that is the recovery path.

Migration `0022` converges an existing multi-admin database to one, choosing in
this order: `PRODUCTION_ADMIN_EMAIL` if set, else the oldest admin whose address
is not a seeded `@jaldrishti.local` demo account, else the oldest. Everyone else
is demoted to `analyst` — nobody is deleted and no password changes.

**`regulator` is a real role again**, with a narrower remit than it had before
R7: review the submission queue, approve, reject.

**The rule is "only admin WRITES", not "only admin looks."** A regulator reads
freely — the dataset listing and rows, the sync status, the model status, ISR
points, stored runs — because a reviewer deciding whether a finding is plausible
needs to see what the data currently holds. A role that can see nothing but a
queue cannot judge what it is deciding about.

What it cannot do is anything that CHANGES state outside its own decision: sync
or seed `Datasets/`, factory reset, run model operations, start a simulation,
read the audit log, publish an advisory, or create an admin. Every one of those
is a `POST` behind `require_admin` (or, for starting a run, admin/analyst), and
that boundary is verified over real HTTP in `tests/test_p6_roles.py` — twelve
refusals and five permitted reads.

**There may be as many regulators as you need** — that is the role to give a
second operator. Approving a submission records a decision and nothing else;
writing it into `Datasets/` stays a separate, deliberate, admin-only act.

---

## 8c. Backups — and a restore that has actually been run

`scripts/backup.py` covers the two things that cannot be regenerated: the
`Datasets/` evidence base (only its `original` rows are recoverable from git;
every `added` row came from an approved submission and exists nowhere else) and
PostgreSQL, above all the append-only audit log.

```bash
python -m scripts.backup --verify
```

`--verify` restores the dump into a scratch database, compares row counts table
by table, confirms the row-level security policies came back, and drops the
scratch database. A backup that has never been restored is a hypothesis.

**Result of running it on 2026-08-21:** every table matched — users 6,
audit_log 1685, field_observations 33, advisories 17, alerts 7,
simulation_runs 45, water_samples 397, monitoring_wells 397, districts 24,
blocks 264 — and 21 RLS policies were restored.

Requires `pg_dump` / `pg_restore` / `psql` on PATH, at a major version >= the
server's.

**`backups/` is gitignored, and that matters more than it looks.** The dump
contains every argon2 password hash and the entire audit log; this repository is
public. `Datasets.before-restore-*` — the tree `--restore` moves aside rather
than deleting — is ignored for the same reason.

The dump is taken with `--no-owner --no-acl`, so it restores as any superuser.
Policies are part of the schema and come back; **the `jaldrishti_app` role does
not**. After restoring onto a fresh server run `python -m scripts.create_app_role`
or RLS will be inert and the API will refuse to start (§2.2, F-4).

Schedule it however your host schedules things — cron, a systemd timer, a
managed snapshot alongside it. Nothing here schedules itself.

---

## 9. Known issues to weigh before shipping

Rewritten 2026-08-20 after the deployment readiness audit
(`docs/local/audit-record/DEPLOYMENT_AUDIT_2026-08-20.md`). Four entries that
used to live here are now **enforced by the code** rather than left to whoever
reads this file.

### Closed by the audit — but still needs one action from you

- **Demo accounts (F-1).** `Login.tsx` listed four working accounts, admin
  included, and Vite compiled them into the production bundle — a working admin
  password readable by anyone who viewed source. They are now behind
  `import.meta.env.DEV`, so a production build eliminates them, and
  `npm run build` fails if any credential survives into `dist/`.
  **You must still delete or rotate those four accounts in any deployed
  database** — removing them from the bundle does not disable them. See §5.
- **`/metrics` (F-2).** No longer open by default. Set `METRICS_TOKEN` and the
  endpoint requires `Authorization: Bearer <token>`, which is what a Prometheus
  scrape config sends. With `APP_ENV=production` and no token, it is **not
  mounted at all**. Development is unchanged.
- **Row-level security (F-4).** §2.2 has always warned that RLS is "silently
  inert" if the roles are wrong. With `APP_ENV=production` the API now **refuses
  to start** when it is connected as a superuser or a `BYPASSRLS` role.
  `ALLOW_INERT_RLS=true` overrides it deliberately and still logs CRITICAL.
- **Cache headers (F-5).** Every `/api/` response now defaults to
  `Cache-Control: no-store`; the deliberately public layers set their own header
  and keep it. Previously only 4 of 21 routers set it, so `/audit` and `/users`
  sent nothing.
- **Concurrent dataset writes (F-3).** The syncs and the factory reset rewrite
  whole files inline in the request handler with no lock, so two at once lost
  one of them silently. They now take a Postgres advisory lock and a second
  writer gets a `409` naming the operation already running. Dry runs do not
  contend.

### Still open — decide before a public deployment

- **`react-router-dom` 6.28** carries two moderate advisories. **Neither is
  reachable in this app:** the SSR hydration one needs SSR, which this SPA does
  not use, and the open redirect needs a user-controlled navigation target —
  every `navigate()` call here takes a string literal or an internal UUID.
  Upgrading crosses a major version, so treat it as routine maintenance rather
  than a blocker.
- **The five `POST /ingest/*` routes admit `analyst`** (finding D-2 in
  `docs/roles.md`), meaning an analyst can overwrite reference geography. On a
  multi-user deployment, narrow them to `require_admin` first.
- **Backups are not defined anywhere.** `Datasets/` is the evidence base and
  `audit_log` is append-only and irreplaceable. Write the backup and restore
  procedure, and **test a restore**, before go-live. The audit could not verify
  this because it does not exist.
- **PDF export pagination has never been visually confirmed** (`O-8`). Generate
  one and look at it.
- ~~**Orphaned simulation runs.**~~ **Fixed.** Runs are in-process background
  tasks, so a restart abandoned whatever was in flight and left the row at
  `queued` for ever — three real ones were found sitting from the previous day.
  They are now failed at startup and by `POST /simulations/reap`, with a message
  naming the restart. The sweep only touches runs older than 30 minutes, so
  under `--workers N` one worker's startup cannot kill another's live run.
- ~~**API rate limiting behind a gateway.**~~ **Fixed.** `get_remote_address`
  reads `request.client.host`, which behind a proxy is the PROXY — every
  authenticated user shared one bucket and the first busy user locked out the
  rest. The limiter now keys on the token subject, falling back to the address.
  **Anonymous traffic still keys on the address**, so run uvicorn with
  `--proxy-headers --forwarded-allow-ips=<gateway-ip>` or the whole public
  surface shares one bucket.
- **The ENGINE rate limit is still per client host**
  (`ML_PIPELINE_RATE_LIMIT_PER_MIN`, default 240) and is not keyed per user.
  Size it for real concurrency.
- **Token refresh now exists** (`POST /auth/refresh`, and the client uses it),
  so the hard sign-out described in older revisions of this file is gone. But
  `.env` sets `ACCESS_TOKEN_EXPIRE_MINUTES=15` against a code default of 480 —
  pick one deliberately. See §3.
