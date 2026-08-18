# JalDrishti — next build prompt

**For:** a fresh Claude Code session on this repo
**Written:** 2026-08-18
**Status:** not started. Read §0 before touching anything.

This is the working brief for the next round. It covers five things, in this
order: **Console/map fixes → the report → visual language → full audit and test
→ deployment**. Do them in that order; the audit is worth much less before the
UI work lands, and deployment is worth nothing before the audit.

---

## 0. Orientation — read this before you start

You are picking up a project that is near completion and has strong opinions
baked into it. Violating them will look like a bug to the owner.

### What exists

| Part | State |
|---|---|
| `ml_pipeline/` | The physics + ML engine. **332 tests, frozen.** Do not change it. |
| `backend/` | FastAPI + PostgreSQL/PostGIS. **203 tests passing.** Alembic head is `0019_retire_regulator`. |
| `frontend/portal/` | Vite + React 18 + TS + Leaflet. Typechecks and builds clean. |

Dev loop: API on `:8000` (`uvicorn app.main:app`), Vite on `:5173` proxying
`/api` → `:8000`. Postgres is live locally; tests use a separate
`groundwater_test_db` built **from ORM metadata, not migrations** — so any
`server_default` you rely on in raw SQL must be on the model too.

### The four roles

`admin` (operates *and* decides — publishes advisories, reviews field evidence,
reads audit) · `analyst` (registers sites, runs the engine, proposes
publications) · `field_officer` — labelled **Data Submitter** (submits uranium-ore
occurrences only) · `citizen` — labelled **Resident**.

`regulator` was retired in R7 (migration `0019`). The enum label still exists in
Postgres because a value cannot be dropped transactionally; it is retired from
the *application* vocabulary. `tests/test_p6_roles.py` enforces that. **Do not
reintroduce it.**

### Non-negotiable product rules

These are not style preferences. Each one exists because breaking it produces a
confidently wrong statement about someone's drinking water.

1. **No ISR uranium mine operates in Jharkhand.** Every site is hypothetical.
   The premise appears on every model-output surface, and in the *first*
   paragraph of anything a resident reads.
2. **The analytical engine is the authority.** The ML surrogate was trained on
   that engine's own output, so it cannot be more accurate — it supplies
   calibrated uncertainty bands only. Every number says which engine produced it.
3. **A registered site IS the operation.** Only `species`, `time_years` and
   `restoration_years` may vary per run (`RUN_VARIABLE` in
   `ml_pipeline_adapter.py`, enforced at three call sites).
4. **Never inflate reach.** A ~13 ha footprint inside a ~30,000 ha block is
   reported as what it is. Affected blocks come from real PostGIS intersection.
5. **"No data" is a monitoring gap, never a clean result.**
6. **Extrapolation is loud.** Outside trained support the conformal guarantee is
   void and the UI says so.
7. **Runs are ephemeral until saved.** `POST /simulations/{id}/preview` stores
   nothing; `POST /simulations/{id}` is the deliberate act of keeping one.

### The lifecycle physics — do not "fix" this to match intuition

Measured on a 10 yr operation / 2 yr restoration / 20 yr horizon run:

- **Source strength is FLAT during injection** (14,294 ppb, unchanging). That is
  what injection is. What grows during operation is the **affected area**
  (0 → 9.8 ha).
- **Restoration drops it** (14,294 → 4,639).
- **After closure it is HELD**, not decayed — residual uranium can re-oxidise.
  Meanwhile **migration keeps growing** (0.2 m → 12.7 m at 50 yr) because
  hydraulic containment stops with the operation.

`tests/test_p6_preview_lifecycle.py` pins all three shapes. If a chart change
makes source strength rise during operation or decay after closure, the chart is
wrong, not the engine.

---

## 1. Console and map fixes

### 1.1 Clicking outside the Singhbhum belt — the drawer conflict

**Reported:** clicking anywhere outside the belt shows *map block/district
details* instead of resolving hydrogeology, and two columns appear at once.

**Root cause to verify first:** `Console.tsx` has three mutually exclusive
drawer modes (`"none" | "pin" | "site"`), but a district click sets `sel` and
forces `mode = "none"`, so the district drawer wins and the pin drawer never
opens. Confirm before changing.

**Required behaviour:**

- **One drawer at a time, never two columns.** If both a district and a pin are
  selected, ISR pin mode wins.
- **ISR pin mode is the default.** A click anywhere in Jharkhand drops a pin and
  resolves hydrogeology. Reaching district/block detail should be a deliberate
  second action (a tab or a toggle inside the same drawer), not the default.
- **Any point in Jharkhand must be usable as an ISR location** — inside the ore
  belt or not.

**Already true, verify rather than rebuild:** the engine is *not* the limit here.
At Ranchi (85.33, 23.36) uranium correctly returns 0 ha with a non-ore notice,
while **sulfate and TDS return 12.2 ha with real migration**. R1 already added
non-ore messaging and dimmed suppressed species. Check whether that is actually
reaching the screen before adding more.

### 1.2 Floating, draggable legend

Make the map legend a floating panel the user can **click and drag anywhere on
screen**. Keep it inside the viewport, remember its position for the session,
and keep it collapsible (it already is). Pointer events, not mouse-only — the
portal is responsive and used on tablets.

### 1.3 Resizable and hideable panels

Both the left rail and the right drawer must be:

- **resizable** by dragging their inner edge, within sensible min/max widths;
- **fully hideable**, with an obvious way to bring them back.

`useRail.ts` already collapses the rail by *unmounting* it — read the comment in
`layout.css` explaining why a width-based collapse failed before (flex items
resolve `min-width: auto` to content size). Do not re-litigate that; build the
resize on top of the existing collapse.

Persist widths in `sessionStorage`, matching the existing rail convention (and
its stated reason: a preference surviving sign-out on a shared machine is a
preference nobody set).

---

## 2. The report (`/report/:siteId`)

### 2.1 Fix the duplicate image — root cause identified

`IsrReport.tsx` renders `<VerticalPanel>` directly **and** renders
`<RunResult>`, which renders `<VerticalPanel>` again when not `compact`. That is
the "two similar images which have no point". Render the depth schematic **once**.

### 2.2 Layout

- The vertical-stratification schematic should take **half the width**, not the
  full width.
- Fill the other half with the numbers that belong beside it — shallow-aquifer
  impact probability, breakthrough years, dominant pathway, the wet/dry seasonal
  split, ore depth and confining separation. Most of this is already computed and
  displayed underneath; move it alongside.

### 2.3 Charts

- **Phase backgrounds** (this is a visual-encoding change only — the phase
  boundaries already come from the engine):
  - active mining → slight **red** wash
  - restoration → slight **green** wash
  - remaining evaluation → **neutral light** wash
  Current `LifecycleChart.tsx` uses red/blue/grey; change to red/green/neutral
  and keep the contrast legible in both themes.
- **Point labels on the plot itself.** Today hovering a point writes its value
  into a row *below* the chart. Move it to a tooltip/callout anchored to the
  point, on **tap as well as hover** (touch has no hover).
- Review whether every plotted series earns its place, and add any that are
  missing. Use judgement — but state your reasoning in the response, and do not
  invent series the engine does not return.

### 2.4 Make it a real document

The report currently reads as a debug dump. It should read as a **publication-grade
assessment document**: clear title block, site identity, an executive summary a
non-specialist can read, then the technical sections, then provenance.

> The original brief said "premium lead generation thing". Translate that as
> *visual quality and polish*, not as marketing language. This is a government
> screening tool; sales framing would undercut its credibility. Keep the tone
> factual and the hypothetical premise prominent.

### 2.5 PDF export

Add a **Download PDF** button that exports the full report for any ISR point.

**Decide and state your choice before building:** client-side (print stylesheet
via `window.print()`, or `html2pdf`/`jspdf`) versus server-side (a rendering
service). Client-side print CSS is strongly preferred — no new backend
dependency, no headless browser to deploy, and it keeps working when the API is
behind a gateway. The trade-off is less exact pagination control.

The PDF must carry the hypothetical premise and the provenance block. A PDF
escapes the portal and will be read without context.

### 2.6 The missing map

**Ambiguous in the original brief — clarify with the owner before building.**
"There is no map in the folder that is shown to the citizen. Also generate that."

Two plausible readings:

1. The **report** has no map figure — add a static map of the site and its
   modelled footprint to the report and the PDF; or
2. The **citizen-facing published screening** needs its own map view.

Note that (2) partly exists: `CitizenMap.tsx` already draws published advisory
footprints in hatched violet from `GET /citizen/advisories/geojson`. Verify what
is actually missing before building either.

---

## 3. Visual language

Rework the whole UI to be **minimal and classic, in the spirit of the Cursor
editor, on a different blue**.

- Work through the existing token layer in `styles/theme.css`. It already has a
  type scale, spacing scale, breakpoints and risk-band tokens. **Change the
  tokens, not the call sites.**
- Keep the accessibility work: risk bands carry a glyph and border treatment as
  well as colour, and Leaflet geometry carries band via `dashArray`/`weight`.
  A restyle must not reduce the ramp to colour alone.
- Keep the responsive contract (rail → off-canvas sheet, drawer → bottom sheet
  under 768px, no horizontal page scroll).
- Restraint over decoration: fewer borders, calmer surfaces, tighter type,
  generous spacing. Dense where the console needs density, roomy where a
  resident is reading prose.

---

## 4. Full audit and test

The owner asked for a complete review "code by code, line by line". Be honest
about what that can mean in one session: **do not claim to have read every line
if you have not.** Prioritise, state your coverage, and report what you did not
reach.

### 4.1 Audit against the objective

The objective is in `docs/local/My_Proposal.pdf` — a TEXMiN/BIT Sindri
fellowship project: *ML-based prediction of groundwater degradation and aquifer
vulnerability near uranium ISR operations, with a decision-support prototype for
regulators, operators and local communities.*

For each stated deliverable, report **met / partly met / not met**, with
evidence. The named deliverables include: predictive models, **identification of
data gaps and monitoring recommendations**, a decision-support prototype,
a visualisation dashboard, and alerts.

### 4.2 API surface sweep

There are ~103 endpoints. Establish for each: is it reachable from the UI, is it
covered by a test, does it still serve a purpose.

Known dead or unreachable as of this writing — re-verify, do not assume:
`/aquifers`, block/monitoring-station CRUD, `/districts/{id}/blocks`,
`/monitoring-stations`, `/water-samples`, legacy `/simulations/{sim_id}`,
`/ml/drift`, `/ml/health`, the five `/ingest/*` upload endpoints, and the
scenario endpoints (`/scenarios/*`, which have **no UI** since the Console
merge — the owner chose to repurpose them as "saved runs"; that is **not yet
built**).

The owner previously chose **"surface only, delete nothing"** for cleanup.
Respect that unless they say otherwise.

### 4.3 Click every button

Exercise every screen for every role: admin, analyst, data submitter, resident.

**A known harness limitation:** in previous sessions the in-app browser pane did
not composite, so React synthetic events did not fire from tool-driven clicks
and interactive verification was inconclusive. If that recurs, say so plainly
rather than reporting an untested UI as tested. Fall back to API-level checks
and DOM/computed-style assertions, and **label them as such**.

### 4.4 Known open defect

The staff district list shows e.g. *"East Singhbum · 28 wells · 28 samples ·
**No data**"* — the same sampled-but-not-analysed-for-uranium contradiction that
was fixed on the citizen surface in `citizen.py`. The band comes from
`bandOf(max_uranium_ppb)`, which is null when wells were sampled but never
analysed for uranium. Fixing it properly needs sample counts plumbed into the
district list. **Not yet fixed.**

---

## 5. Deployment

The owner's stated plan, to be confirmed or corrected:

> "I will deploy the backend individually. I will deploy the frontend
> individually. I will change the frontend to attach the backend endpoint. Is
> that right, or is it one thing?"

**Answer that question directly**, then produce a deployment guide covering:

1. **Architecture** — separate backend and frontend services is correct and is
   what the repo is already shaped for. Explain the one thing that changes: in
   dev, Vite proxies `/api` → `:8000` (so the browser makes same-origin
   requests). In production, either put both behind one gateway/reverse proxy and
   keep the paths identical, or point the frontend at an absolute API URL and
   configure CORS. **State the trade-off** — the gateway approach needs no code
   change and no CORS; the split-origin approach needs a build-time env var
   (`VITE_API_BASE`) and a CORS allowlist.
2. **Database** — Postgres 16 + PostGIS. Cover: provisioning, running
   `alembic upgrade head`, the **two-role setup** (`MIGRATION_DATABASE_URL` for
   the owner role that can DDL, and `jaldrishti_app` which is `NOSUPERUSER
   NOBYPASSRLS` so row-level security actually applies — see
   `scripts/create_app_role.py` and the startup guard). Getting this wrong makes
   RLS silently inert, which the codebase already warns about at length.
3. **Secrets and `.env`** — what belongs in each environment, what must never be
   committed, how `SECRET_KEY`/JWT signing and `DATABASE_URL` are supplied in
   production. `backend/.env` is gitignored; confirm nothing sensitive is
   tracked before shipping.
4. **Datasets** — `Datasets/` and `ml_pipeline/ml/artifacts/` must ship with the
   backend; the engine reads them from disk. Note the size implications.
5. **Seeding** — `scripts/init_db.py` and `scripts/seed.py`, and what the demo
   accounts mean for a real deployment (**they must not survive into
   production** — the login screen currently lists four demo logins with weak
   passwords).
6. **A pre-deployment checklist** — migrations applied, app role in use and RLS
   verified active, demo users removed, secrets rotated, CORS/gateway configured,
   `docs/roles.md` regenerated, full test suite green.

Recommend concrete hosting options suited to a fellowship project (managed
Postgres + a container host for the API + static hosting for the built frontend),
with rough cost and the simplest path first.

---

## 6. Decisions to confirm before building

Ask these together, early, and do not guess:

1. **The two-column / drawer behaviour (§1.1)** — confirm the interpretation:
   one drawer, ISR pin mode default, district detail as a deliberate secondary
   action.
2. **The missing map (§2.6)** — report figure, citizen map, or both?
3. **PDF approach (§2.5)** — client-side print CSS (recommended) or a
   server-side renderer?
4. **Blue palette (§3)** — one specific blue, or your choice with a preview?

---

## 7. Acceptance criteria

- [ ] A click anywhere in Jharkhand opens exactly one drawer, in ISR pin mode,
      and resolves hydrogeology — inside or outside the ore belt.
- [ ] Legend floats and is draggable; position survives navigation within the session.
- [ ] Rail and drawer are resizable and fully hideable, on desktop and mobile.
- [ ] The depth schematic renders **once**, at half width, with its numbers beside it.
- [ ] Lifecycle chart uses red/green/neutral phase washes and labels points on the
      plot on tap and hover.
- [ ] The report reads as a finished document and exports to PDF with the
      hypothetical premise and provenance intact.
- [ ] The UI is visibly minimal/classic on a blue palette, with band glyphs and
      the responsive contract preserved.
- [ ] `npx tsc --noEmit` clean, `npm run build` clean.
- [ ] `python -m pytest tests -q` green in `backend/` (203+ tests).
- [ ] `python -m pytest ml_pipeline/tests -q` still green (332 tests) — the
      engine must be untouched.
- [ ] `python -m scripts.authz_matrix` run if any route or guard changed.
- [ ] Audit report delivered, with coverage honestly stated.
- [ ] Deployment guide delivered, answering the one-service-or-two question directly.

---

## 8. How to work

- **Verify before you fix.** Several items above already have partial
  implementations. Check the current behaviour first and say what you found.
- **Report failures faithfully.** If a test fails or a check is inconclusive,
  say so with the output. Do not describe an untested surface as tested.
- **Do not weaken a safety rule to satisfy a UI request.** If a request conflicts
  with §0, raise it in a sentence and propose the nearest thing that preserves
  the rule.
- **Do not touch `ml_pipeline/`.** If something appears wrong in the engine,
  report it rather than editing it.
- **Commit only when asked.**
