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

- [ ] The project is pushed to **GitHub**. Deploy from a git clone, never from
      your working directory — your local `Datasets/` holds ~1.1 GB of
      build-time rasters that must not ship. `.dockerignore` and `.gitignore`
      already exclude them.
- [ ] You can run `python`, `git` and `npm` locally.
- [ ] Generate two secrets now and keep them somewhere safe:

```bash
python -c "import secrets; print('JWT_SECRET      =', secrets.token_urlsafe(64)); print('APP_DB_PASSWORD =', secrets.token_urlsafe(24))"
```

---

## Step 1 — The database (Neon)

Neon is chosen because its free tier carries PostGIS and it gives you a
connection string immediately. Supabase works identically if you prefer it.

1. Open **<https://neon.tech>** and sign in with GitHub.
2. **Create a project.** Name it `jaldrishti`. Choose the region nearest you
   (`AWS ap-south-1 / Mumbai` if offered). Postgres version **16**.
3. On the project dashboard, copy the **connection string**. It looks like:
   ```
   postgresql://neondb_owner:XXXX@ep-something.ap-south-1.aws.neon.tech/neondb?sslmode=require
   ```
   This is your **owner** connection. Keep it — it is `MIGRATION_DATABASE_URL`.
4. Open the **SQL Editor** in the Neon sidebar and run:
   ```sql
   CREATE EXTENSION IF NOT EXISTS postgis;
   ```
   If this errors, PostGIS is not available on your plan and you must switch
   provider — everything downstream depends on it.

### 1b. Create the restricted role — do not skip this

**This is the single most consequential step in the deployment, and it fails
silently.** Postgres skips row-level security entirely for a superuser or owner.
If the API connects as the owner, all 21 policies still exist, still review
cleanly, and **enforce nothing**.

From your machine, with the repo checked out:

```bash
cd backend
python -m scripts.create_app_role --password 'YOUR_APP_DB_PASSWORD'
```

Point it at Neon first by setting `MIGRATION_DATABASE_URL` and `DB_*` in
`backend/.env` to the Neon values, or export them for the one command. This
creates `jaldrishti_app` — `NOSUPERUSER`, `NOBYPASSRLS`, DML only, no ownership,
so it cannot drop a policy that constrains it.

Your **application** connection string is the Neon one with the user and
password swapped:

```
postgresql+asyncpg://jaldrishti_app:YOUR_APP_DB_PASSWORD@ep-something.ap-south-1.aws.neon.tech/neondb?sslmode=require
```

### 1c. Create the schema and load the data

Still locally, still pointed at Neon:

```bash
cd backend
alembic upgrade head          # head is 0022_regulator_single_admin
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

1. Open **<https://render.com>** and sign in with GitHub.
2. **New → Web Service**, and connect your JalDrishti repository.
3. Fill in:

   | Field | Value |
   |---|---|
   | Name | `jaldrishti-api` |
   | Region | the one nearest your Neon region |
   | Branch | `main` |
   | Runtime | **Docker** |
   | Dockerfile Path | `backend/Dockerfile` |
   | Docker Build Context Directory | `.` *(the repo root — not `backend/`)* |
   | Instance Type | `Free` to try, `Starter` ($7/mo) to stay awake |

   > **The build context must be the repo root.** The engine (`ml_pipeline/`)
   > and the data it reads (`Datasets/`) live above `backend/`, and the adapter
   > resolves them three levels up from itself. Building from `backend/`
   > produces an image where every simulation fails with *"ml_pipeline is not
   > importable"*.

4. **Environment → Add Environment Variable**, and add these:

   | Key | Value |
   |---|---|
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | the **`jaldrishti_app`** URL from step 1b |
   | `JWT_SECRET` | the 64-char secret you generated |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` |
   | `RATE_LIMIT_PER_MINUTE` | `300` |
   | `AUTH_RATE_LIMIT_PER_MINUTE` | `10` |
   | `DOCS_ENABLED` | `false` |
   | `HSTS_ENABLED` | `true` |
   | `CORS_ORIGINS` | your final portal origin, e.g. `https://jaldrishti.pages.dev` |

   Do **not** set `MIGRATION_DATABASE_URL` here. The running API has no DDL to
   do, and withholding it means a compromised process cannot drop a policy that
   constrains it. Do **not** set `REDIS_URL`, `CELERY_*`, `ML_SERVICE_URL`,
   `S3_*` or `SENTRY_DSN` — there is no Celery, Redis or task queue in this
   codebase; they are leftovers from an earlier architecture.

5. **Create Web Service.** The first build takes 5–10 minutes (GDAL and
   geopandas are large).

6. **Read the startup log.** You are looking for exactly this line:

   ```
   Row-level security active: 21 policies, connected as 'jaldrishti_app' (no bypass).
   ```

   If you instead see **`ROW-LEVEL SECURITY IS INERT`**, `DATABASE_URL` is
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
   ```bash
   curl -o /dev/null -w "%{http_code}\n" https://jaldrishti-api.onrender.com/openapi.json
   ```
   Expect **404**. A 200 means `DOCS_ENABLED` is not false.

---

## Step 3 — The portal (Cloudflare Pages)

1. Open **<https://dash.cloudflare.com>** → **Workers & Pages** → **Create** →
   **Pages** → **Connect to Git**, and pick the repository.
2. Build settings:

   | Field | Value |
   |---|---|
   | Framework preset | `Vite` |
   | Build command | `npm ci && npm run build` |
   | Build output directory | `frontend/portal/dist` |
   | Root directory | `frontend/portal` |

   The build runs `tsc -b && vite build` and then a guard that greps `dist/` for
   credentials and **fails the build** if any are found. If the build fails on
   `no-credentials-in-bundle`, do not work around it — something secret reached
   the bundle.

3. **Save and Deploy.** You get `https://<project>.pages.dev`.

4. **Route `/api/*` to Render.** Create `frontend/portal/public/_redirects`:

   ```
   /api/*  https://jaldrishti-api.onrender.com/api/:splat  200
   /*      /index.html                                     200
   ```

   The first line is the proxy that makes this one origin — status `200`, not
   `301`, so it rewrites rather than redirects. The second is the SPA fallback:
   without it a refresh on `/report/:siteId` returns 404, because that route
   exists only in the browser.

   Commit it and let Pages rebuild.

5. Confirm the rewrite works:

   ```bash
   curl -o /dev/null -w "%{http_code}\n" https://<project>.pages.dev/api/v1/public/risk/districts
   ```
   Expect **200**. This endpoint is deliberately public, so it is the right one
   to test the routing with.

---

## Step 4 — Lock it down

- [ ] **Delete the four demo accounts.** They are weak and public
      (`analyst123`, `regulator123`, `field123`, `citizen123`). In Neon's SQL
      Editor:
      ```sql
      DELETE FROM users WHERE email LIKE '%@jaldrishti.local';
      ```
      Confirm your real admin survives:
      ```sql
      SELECT email, role FROM users;
      ```
- [ ] Sign in as your real admin and confirm you can reach Administration.
- [ ] **Confirm the login limiter.** Eleven wrong passwords in a minute should
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
- [ ] Open the portal as a **citizen** account and confirm no ISR site, no
      coordinates and no model internals appear anywhere.

---

## Step 5 — Backups, before you need them

`LIMITATIONS.md` §4c records that backups were undefined and no restore had ever
been tested. Neon gives you point-in-time restore on the free tier
(**Branches → Restore**), which covers the database. Take one manual dump now so
you have something outside the vendor:

```bash
cd backend && python -m scripts.backup --verify
```

`--verify` is the flag that matters: it takes the backup **and then restores it
into a scratch database and counts rows**, so the procedure is exercised rather
than assumed. An untested backup is a hypothesis. Run it with `--verify` at
least once, and record that you did.

It backs up two things that cannot be regenerated: `Datasets/` (only the
`original` rows are recoverable from git — every `added` row came from an
approved field submission and exists nowhere else) and PostgreSQL (the audit log
above all, which is append-only by design and therefore has no second copy
anywhere).

The output lands in `backups/`, which is gitignored and **must stay that way**:
it contains every argon2 password hash, the entire audit log and every account.
It is the most sensitive artifact this project can produce.

To bring one back: `python -m scripts.backup --restore <dir>`.

---

## What will go wrong, and what it means

| Symptom | Cause |
|---|---|
| Build fails on `gdal-config not found` | Build context is `backend/`, not the repo root — Docker never saw the Dockerfile's system-deps layer as intended. Recheck step 2.3 |
| Every simulation fails, `ml_pipeline is not importable` | Same cause: the image has no `/app/ml_pipeline` |
| `ROW-LEVEL SECURITY IS INERT` in the log | `DATABASE_URL` is the owner, not `jaldrishti_app`. Step 1b |
| Service exits with `Refusing to start with APP_ENV=production` | A secret is missing or is still a placeholder. The log lists which |
| First request after idle takes 40 s then works | Free-tier cold start plus artifact load. Upgrade to Starter, or accept it |
| Portal loads, every API call 404s | `_redirects` missing or output directory wrong. Step 3.4 |
| Refresh on `/report/...` 404s | The SPA fallback line is missing from `_redirects` |
| Lifecycle chart times out, everything else fine | Gateway read timeout below 60 s |
| `429` during ordinary use | `RATE_LIMIT_PER_MINUTE` too low — the Console loads ~14 map layers per navigation. 300 is the tested default |

---

## The sentence to keep saying

No ISR uranium mine operates in Jharkhand. Every site in this system is
hypothetical, and every plume output means *"if ISR-strength lixiviant entered
this aquifer"* — never feasibility, never a permit. The water-quality and
groundwater-level screens are the exception: those are **real measurements** from
government sampling, and they are labelled as such on every page.
