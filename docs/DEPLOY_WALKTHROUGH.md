# Deploying JalDrishti — the actual steps

**Written 2026-08-24 (R13).** `DEPLOYMENT.md` explains the *architecture* and the
trade-offs. This file is the click-by-click: which site to open, what to type,
what to check before moving on.

Budget **about 90 minutes** the first time. Cost: **$0** on free tiers, or about
**$7/month** if you want the API to stay awake.

---

## What you are building

Three pieces, in this order. Do not reorder them — each needs the one before it.

```
   1. Neon            Postgres 16 + PostGIS         the data
   2. Render          the FastAPI service           the API + engine
   3. Cloudflare      static bundle + /api rewrite  the portal
      Pages
```

Everything ends up under **one hostname**, with `/api/*` routed to Render. That
is "Option A" in `DEPLOYMENT.md` §1, and it is the one that needs **no code
change and no CORS**, because the portal already calls `/api/v1/...` as a
same-origin relative path.

---



## Before you start

- [x] The project is pushed to **GitHub**. Deploy from a git clone, never from
      your working directory — your local `Datasets/` holds ~1.1 GB of
      build-time rasters that must not ship. `.dockerignore` and `.gitignore`
      already exclude them.
- [x] You can run `python`, `git` and `npm` locally.
- [x] Generate two secrets now and keep them somewhere safe:

```bash
python -c "import secrets; print('JWT_SECRET      =', secrets.token_urlsafe(64)); print('APP_DB_PASSWORD =', secrets.token_urlsafe(24))"
```

---



## Step 1 — The database (Neon)

Neon is chosen because its free tier carries PostGIS and it gives you a
connection string immediately. Supabase works identically if you prefer it.

1. Open **[https://neon.tech](https://neon.tech)** and sign in with GitHub.
2. **Create a project.** Name it `jaldrishti`. Postgres version **16**.

   **Choose `AWS ap-southeast-1 / Singapore`, and treat this as load-bearing
   rather than a preference.** Neon's region list does not include Mumbai as of
   2026-08-25 -- Singapore is the nearest offered region to India. Deployment
   audit the same day: a project created in `us-east-2` (Ohio) instead measured
   **1,680 ms** to open a TCP connection from India against a 28 ms baseline,
   and `scripts.seed` never finished against it.

   The reason is in the seed's shape, not the network's. `seed_geodata` runs
   **all five ingestion stages in a single transaction**, and the groundwater
   stage walks 398 stations one at a time, each with its own dedupe lookups,
   before inserting ~8,345 readings. That is on the order of ten thousand
   sequential round trips which must all land on **one unbroken connection**:

   | Region | RTT from India | Seed duration | Outcome |
   |---|---|---|---|
   | `ap-southeast-1` (Singapore) | ~30-60 ms | ~5-10 min | fine |
   | `us-east-2` (Ohio) | ~250-1700 ms, observed spiking | 40-80 min, if it survives | died with `ConnectionDoesNotExistError: connection was closed in the middle of operation`, and the single transaction rolled every table back to zero |

   There is no partial credit here. A drop at minute 50 leaves you exactly where
   you started, so a region that merely *usually* holds for an hour is not good
   enough.

   **This constrains your API region too.** Render offers Singapore, so pair
   the two and the API<->DB hop stays in-region (~1-5 ms) while the seed and
   every migration you ever run from your machine stay fast as well. If you
   would rather chase the lowest possible API<->DB latency by putting the API
   in Ohio or Virginia against a Singapore database, you pay that same ~230 ms
   on every request the API makes to Postgres -- worse for a running service
   than for a one-time seed. Keep both in Singapore.
3. On the project dashboard, copy the **connection string**. Neon hands you
   something like:
  ```
   postgresql://neondb_owner:XXXX@ep-something-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
  ```
   **Two things must be changed before this codebase will accept it.**

   **(a) Take the direct host, not the pooler.** If the hostname contains
   `-pooler`, drop that suffix (Neon shows both under *Connection string* →
   *Direct connection*). The pooled endpoint is PgBouncer in transaction mode,
   which breaks asyncpg's prepared statements; and `app/database.py` already
   pools (`pool_size=10, max_overflow=20`), so the second pooler buys nothing.

   **(b) Strip `sslmode` and `channel_binding` from any `+asyncpg` URL.**
   Neither is an asyncpg keyword. SQLAlchemy 2.0.36's asyncpg dialect passes
   query parameters straight through to `asyncpg.connect()`
   (`create_connect_args` does `opts.update(url.query)` with no SSL
   translation), so `?sslmode=require` fails at connect time with:

   ```
   TypeError: connect() got an unexpected keyword argument 'sslmode'
   ```

   The asyncpg spelling is **`?ssl=require`**. So you end up with two shapes,
   and which one you want depends on the driver that reads the variable:

   | Variable | Read by | Shape |
   |---|---|---|
   | `MIGRATION_DATABASE_URL` | psycopg2 (alembic) **and** asyncpg (`init_db`, `seed`) | `postgresql+asyncpg://neondb_owner:XXXX@ep-something.ap-southeast-1.aws.neon.tech/neondb` — **no SSL parameter at all** |
   | `DATABASE_URL` | asyncpg only (`app/database.py`) | `postgresql+asyncpg://jaldrishti_app:PASS@ep-something.ap-southeast-1.aws.neon.tech/neondb?ssl=require` |

   `MIGRATION_DATABASE_URL` carries no SSL parameter because it is consumed by
   **both** drivers and they disagree on the spelling: `alembic/env.py::_sync_url`
   rewrites the scheme to `+psycopg2` but leaves the query string alone, while
   `scripts/init_db.py` and `scripts/seed.py` build an **async** engine from the
   same string. `ssl=require` would break alembic; `sslmode=require` would break
   the other two. Omitting it is safe rather than lax: asyncpg defaults to
   `ssl='prefer'` for TCP addresses (`connect_utils.py`) and libpq's default
   `sslmode` is also `prefer`, so both negotiate TLS — and Neon refuses
   unencrypted connections outright, so `prefer` resolves to TLS or to no
   connection at all.

   Keep the owner string — it is `MIGRATION_DATABASE_URL`.
4. You do **not** need to create the PostGIS extension by hand — migration
   `0001_initial` runs `CREATE EXTENSION IF NOT EXISTS postgis` and
   `postgis_topology` itself. Neon carries both on every Postgres version it
   offers. If you want to fail fast rather than discover it mid-migration, run
   this in the Neon **SQL Editor** first:
  ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS postgis_topology;
  ```
   If either errors, PostGIS is not available on your plan and you must switch
   provider — everything downstream depends on it.



### 1b. Create the restricted role — do not skip this

**This is the single most consequential step in the deployment, and it fails
silently.** Postgres skips row-level security entirely for a superuser or owner.
If the API connects as the owner, all 21 policies still exist, still review
cleanly, and **enforce nothing**.

From your machine, with the repo checked out:

```bash
cd backend
python -m scripts.create_app_role --password 'YOUR_APP_DB_PASSWORD' --dbname neondb
```

`create_app_role` does **not** read `MIGRATION_DATABASE_URL`. It connects with
psycopg2 from the discrete `DB_*` settings, so those are the ones that must
point at Neon in `backend/.env`:

```
DB_HOST=ep-something.ap-southeast-1.aws.neon.tech
DB_PORT=5432
DB_NAME=neondb
DB_USER=neondb_owner
DB_PASSWORD=XXXX
```

No `sslmode` is needed here either — libpq defaults to `prefer` and Neon
answers only over TLS. `--dbname neondb` is required because the setting's
default is the local `groundwater_db`.

This creates `jaldrishti_app` — `NOSUPERUSER`, `NOBYPASSRLS`, DML only, no
ownership, so it cannot drop a policy that constrains it. Run it **before**
`alembic upgrade head`: it issues `ALTER DEFAULT PRIVILEGES`, which grants on
tables created *after* it by the same owner role. Run it afterwards and the
existing tables are still covered by the explicit `GRANT ... ON ALL TABLES`,
but the ordering above is the one that needs no thought.

Your **application** connection string is the Neon one with the user and
password swapped, the driver named, and the asyncpg SSL spelling from step 3b:

```
postgresql+asyncpg://jaldrishti_app:YOUR_APP_DB_PASSWORD@ep-something.ap-southeast-1.aws.neon.tech/neondb?ssl=require
```



### 1c. Create the schema and load the data

Still locally, still pointed at Neon:

```bash
cd backend
alembic upgrade head          # head is 0024_drop_vestigial_sim
python -m scripts.init_db     # enum types
python -m scripts.seed        # districts, blocks, wells, 397 samples, ISR points
```

`seed` is idempotent — users dedupe by email, ISR points by name, geodata by
file checksum — so it is safe to re-run.

Then create the real administrator. There is **no seeded admin**; migration 0022
pins the role to one account:

```bash
python -m scripts.bootstrap_admin --email you@example.com
```

It prompts for the password, never accepts one on the command line, and never
prints it.

**Check before moving on** — in Neon's SQL Editor:

```sql
SELECT count(*) FROM districts;          -- expect 24
SELECT count(*) FROM water_samples;      -- expect 397
SELECT count(*) FROM pg_policies WHERE schemaname = 'public';   -- expect 21
```

---



## Step 2 — The API (Render)

1. Open **[https://render.com](https://render.com)** and sign in with GitHub.
2. **New → Web Service**, and connect your JalDrishti repository.
3. Fill in:

  | Field                          | Value                                          |
  | ------------------------------ | ---------------------------------------------- |
  | Name                           | `jaldrishti-api`                               |
  | Region                         | the one nearest your Neon region               |
  | Branch                         | `main`                                         |
  | Runtime                        | **Docker**                                     |
  | Dockerfile Path                | `backend/Dockerfile`                           |
  | Docker Build Context Directory | `.` *(the repo root — not* `backend/`*)*       |
  | Instance Type                  | `Free` to try, `Starter` ($7/mo) to stay awake |

  > **The build context must be the repo root.** The engine (`ml_pipeline/`)
  > and the data it reads (`Datasets/`) live above `backend/`, and the adapter
  > resolves them three levels up from itself. Building from `backend/`
  > produces an image where every simulation fails with *"ml_pipeline is not
  > importable"*.
4. **Environment → Add Environment Variable**, and add these:

  | Key                           | Value                                                         |
  | ----------------------------- | ------------------------------------------------------------- |
  | `APP_ENV`                     | `production`                                                  |
  | `DATABASE_URL`                | the `jaldrishti_app` URL from step 1b                         |
  | `JWT_SECRET`                  | the 64-char secret you generated                              |
  | `ACCESS_TOKEN_EXPIRE_MINUTES` | `480`                                                         |
  | `RATE_LIMIT_PER_MINUTE`       | `300`                                                         |
  | `AUTH_RATE_LIMIT_PER_MINUTE`  | `10`                                                          |
  | `DOCS_ENABLED`                | `false`                                                       |
  | `HSTS_ENABLED`                | `true`                                                        |
  | `CORS_ORIGINS`                | your final portal origin, e.g. `https://jaldrishti.pages.dev` |

   Do **not** set `MIGRATION_DATABASE_URL` here. The running API has no DDL to
   do, and withholding it means a compromised process cannot drop a policy that
   constrains it. Do **not** set `REDIS_URL`, `CELERY_`*, `ML_SERVICE_URL`,
   `S3_*` or `SENTRY_DSN` — there is no Celery, Redis or task queue in this
   codebase; they are leftovers from an earlier architecture.
5. **Create Web Service.** The first build takes 5–10 minutes (GDAL and
  geopandas are large).
6. **Read the startup log.** You are looking for exactly this line:
  ```
   Row-level security active: 21 policies, connected as 'jaldrishti_app' (no bypass).
  ```
   If you instead see `ROW-LEVEL SECURITY IS INERT`, `DATABASE_URL` is
   pointing at a privileged role. Treat that as a failed deployment and go back
   to step 1b. If the service **refuses to start** and logs
   `Refusing to start with APP_ENV=production`, read the reasons — it is telling
   you a secret is missing or still a placeholder, and it is right.
7. **Set the gateway timeout.** Render's default is 100 s, which is fine. A
  12-point lifecycle trace is ~48 engine solves and takes tens of seconds; if
   you put anything else in front, its read timeout must be above 60 s or the
   report's lifecycle chart will fail in production while working locally.
8. Copy the service URL — `https://jaldrishti-api.onrender.com`. Check it:
  ```bash
   curl https://jaldrishti-api.onrender.com/health
  ```
   Expect `{"status":"ok",...}`. Then confirm the docs are **not** public:
   Expect **404**. A 200 means `DOCS_ENABLED` is not false.

---



## Step 3 — The portal (Cloudflare Pages)

1. Open **[https://dash.cloudflare.com](https://dash.cloudflare.com)** → **Workers & Pages** → **Create** →
  **Pages** → **Connect to Git**, and pick the repository.
2. Build settings:

  | Field                  | Value                     |
  | ---------------------- | ------------------------- |
  | Framework preset       | `Vite`                    |
  | Root directory         | `frontend/portal`         |
  | Build command          | `npm ci && npm run build` |
  | Build output directory | `dist`                    |

   **The output directory is relative to the root directory, not to the repo.**
   An earlier revision of this table paired root `frontend/portal` with output
   `frontend/portal/dist`, which Pages resolves as
   `frontend/portal/frontend/portal/dist` and fails to find. Set root, then
   `dist`.

   The build runs `tsc -b && vite build` and then a guard that greps `dist/` for
   credentials and **fails the build** if any are found. If the build fails on
   `no-credentials-in-bundle`, do not work around it — something secret reached
   the bundle.
3. **Save and Deploy.** You get `https://<project>.pages.dev`.
4. **Routing is already committed.** `frontend/portal/public/_redirects` exists
   and carries the real API hostname, so Pages picks it up on the first build —
   there is nothing to create here. It contains:
  ```
   /api/*  https://jaldrishti-api.onrender.com/api/:splat  200
   /*      /index.html                                     200
  ```
   The first line is the proxy that makes this one origin — status `200`, not
   `301`, so it rewrites rather than redirects. The second is the SPA fallback:
   without it a refresh on `/report/:siteId` returns 404, because that route
   exists only in the browser. Order matters — `/*` first would swallow
   `/api/*` too.

   If you ever move the API to a different host, this file is the one place to
   change.
5. Confirm the rewrite works:
  ```bash
   curl -o /dev/null -w "%{http_code}\n" https://<project>.pages.dev/api/v1/public/risk/districts
  ```
   Expect **200**. This endpoint is deliberately public, so it is the right one
   to test the routing with.

---



## Step 4 — Lock it down

- [ ] **Keep the four demo accounts.** `analyst123`, `regulator123`, `field123`
      and `citizen123` are published on the login screen on purpose — this is a
      fellowship demonstrator and an evaluator who cannot sign in cannot
      evaluate it. `DEPLOYMENT.md` §5 sets out exactly what a stranger holding
      them can and cannot do, and why the posture holds. **Do not** add a fifth
      demo account at a higher privilege, and do not reuse these passwords
      anywhere else.
- [ ] **Confirm the admin is NOT among them.** In Neon's SQL Editor:
      ```sql
      SELECT email, role FROM users ORDER BY role;
      ```
      You want exactly one `admin`, and it must be your bootstrap address — not
      anything ending `@jaldrishti.local`. If an `admin` appears there, stop:
      the seed does not create one, so something else did.
- [ ] Sign in as your real admin and confirm you can reach Administration.
- [ ] **Expect the demo database to drift.** `POST /monitoring-wells` and
      `POST`/`PUT /isr-points` are reachable by `analyst`, so junk wells and
      hypothetical sites will accumulate. That is the accepted trade. Flush it
      with `python -m scripts.seed` (idempotent) or
      `POST /api/v1/model-ops/factory-reset` when it gets noisy.
- [ ] **Confirm the login limiter.** Because the passwords are public, this is
      the control doing the most work. Eleven wrong passwords in a minute should
      start returning 429:
      ```bash
      for i in $(seq 1 12); do curl -s -o /dev/null -w "%{http_code} " -X POST https://<project>.pages.dev/api/v1/auth/login -H 'Content-Type: application/json' -d '{"email":"x@y.z","password":"wrong"}'; done; echo
      ```
      Expect ten `401`s then `429`s. If you get twelve `401`s, the limiter is
      not applying — see `LIMITATIONS.md` §4d, S-1.
- [ ] **Confirm the security headers:**
      ```bash
      curl -sD - -o /dev/null https://<project>.pages.dev/api/v1/public/risk/districts | grep -i "x-frame\|nosniff\|referrer\|strict-transport"
      ```
- [ ] Open the portal as the **citizen** account and confirm no ISR site, no
      coordinates and no model internals appear anywhere. This matters more now
      that anyone can sign in as one.


---



## What will go wrong, and what it means


| Symptom                                                        | Cause                                                                                                                              |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Build fails on `gdal-config not found`                         | Build context is `backend/`, not the repo root — Docker never saw the Dockerfile's system-deps layer as intended. Recheck step 2.3 |
| Every simulation fails, `ml_pipeline is not importable`        | Same cause: the image has no `/app/ml_pipeline`                                                                                    |
| `UnsafeNewEnumValueUsage: unsafe use of new value "citizen"` | `alembic/env.py` is missing `transaction_per_migration=True`. `0007` adds the enum label and `0008` uses it; PostgreSQL will not allow that inside one transaction, so a run-wide transaction can never reach head from an empty database |
| Seed dies with `ConnectionDoesNotExistError`, every table back to 0 | The Neon region is far from you. `seed_geodata` is one transaction over ~10,000 round trips; it cannot survive a blip. Step 1.2 |
| `TypeError: connect() got an unexpected keyword argument 'sslmode'` | A `+asyncpg` URL still carries Neon's `?sslmode=require` or `&channel_binding=require`. asyncpg spells it `?ssl=require`, and `MIGRATION_DATABASE_URL` takes no SSL parameter at all. Step 1, note (b) |
| `prepared statement "__asyncpg_stmt_x__" already exists` | `DATABASE_URL` uses Neon's `-pooler` host, which is PgBouncer in transaction mode. Use the direct endpoint — SQLAlchemy already pools. Step 1, note (a) |
| `invalid connection option "ssl"` from alembic | `MIGRATION_DATABASE_URL` has `?ssl=require` on it. That string is read by psycopg2 as well; leave it bare |
| `create_app_role` cannot connect, or hits `groundwater_db` | It reads `DB_HOST`/`DB_USER`/`DB_PASSWORD`, **not** `MIGRATION_DATABASE_URL`, and its default dbname is local. Step 1b |
| `ROW-LEVEL SECURITY IS INERT` in the log                       | `DATABASE_URL` is the owner, not `jaldrishti_app`. Step 1b                                                                         |
| Service exits with `Refusing to start with APP_ENV=production` | A secret is missing or is still a placeholder. The log lists which                                                                 |
| First request after idle takes 40 s then works                 | Free-tier cold start plus artifact load. Upgrade to Starter, or accept it                                                          |
| Portal loads, every API call 404s                              | `_redirects` missing or output directory wrong. Step 3.4                                                                           |
| Refresh on `/report/...` 404s                                  | The SPA fallback line is missing from `_redirects`                                                                                 |
| Lifecycle chart times out, everything else fine                | Gateway read timeout below 60 s                                                                                                    |
| `429` during ordinary use                                      | `RATE_LIMIT_PER_MINUTE` too low — the Console loads ~14 map layers per navigation. 300 is the tested default                       |


---



## The sentence to keep saying

No ISR uranium mine operates in Jharkhand. Every site in this system is
hypothetical, and every plume output means *"if ISR-strength lixiviant entered
this aquifer"* — never feasibility, never a permit. The water-quality and
groundwater-level screens are the exception: those are **real measurements** from
government sampling, and they are labelled as such on every page.