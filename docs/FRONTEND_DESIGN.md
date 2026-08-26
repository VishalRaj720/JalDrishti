# JalDrishti Portal — Frontend & UX Design

**Date:** 2026-08-12 · **Scope:** the government-facing SPA (`frontend/portal/`)
**Inputs:** `PRODUCT_DESIGN.md`, the `ml_pipeline` dashboard (map + side panel),
`frontend/JalDrishti.html` (navigation patterns), and the TEXMiN–BIT Sindri fellowship
proposal.

---

## 1. What the portal is for

The proposal names three deliverables this UI has to carry, and they are not the same
screen:

1. **Prediction** — forecast contamination spread and aquifer vulnerability.
2. **Data-gap analysis** — find where monitoring is too thin to trust, and say so.
3. **Decision support** — give regulators, technical staff and communities something
   they can act on.

A single "dashboard" cannot serve all three, and it certainly cannot serve a district
officer and a villager with the same screen. The portal is therefore organised by
**role-specific work**, not by data type.

## 2. Visual language

Taken from the `ml_pipeline` dashboard, because that is the working scientific instrument
and the Simulation Studio has to sit inside the portal without looking bolted on:

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0e1116` | app background |
| `--panel` | `#161b22` | rails, headers |
| `--card` / `--card2` | `#1b222c` / `#212a36` | surfaces |
| `--line` | `#2b3441` | borders |
| `--accent` | `#3fb6ff` | primary, section titles |
| `--ok` / `--warn` / `--danger` | `#37d39b` / `#ffb84d` / `#ff5a5a` | the state ramp |
| `--frac` / `--porous` | `#e8833a` / `#3f8cff` | aquifer regime |

Dark is the right call here: this is an operations console read for long stretches beside
a dark map canvas, not a marketing page. The numbered-card side panel (① … ⑥), segmented
buttons, sliders and metric cards with uncertainty bands all carry over.

**From `JalDrishti.html`** the portal keeps the role-filtered top navigation, the role
badge with per-role colour, the avatar menu, and the right-hand detail **drawer** over a
full-bleed map.

## 3. Navigation

One top bar, filtered by role — the `roleReq` pattern from the prototype.

| Section | Purpose | Roles |
|---|---|---|
| **Overview** | Role-specific landing: what needs *my* attention today | all |
| **Map Console** | Operational map — districts, sites, monitoring network, field observations | staff |
| **Simulation Studio** | The ISR plume engine: configure, run, read bands and excursion | admin, regulator, analyst |
| **Field Data** | Submit observations; review and decide on them | admin, regulator, field officer |
| **Data & Gaps** | Coverage, data-quality report, dataset sync, provenance | staff |
| **Audit** | Who did what, when | admin, regulator |
| **Administration** | Accounts and roles | admin |
| **Public View** | The citizen surface — what the public sees | citizen (+ staff, read-only preview) |

Persistent in the header: the **dataset-sync badge** (🟢/🟡 with the count), the role chip,
and the account menu. The sync badge is global because the portal–model lag applies to
every screen that shows a number.

## 4. What each role actually does

**Admin — operate the platform.** Landing shows system health (API, RLS posture, ML
artifact hash), the sync backlog with the one-click ore sync, account inventory, and the
live audit stream. Owns ingest.

**Regulator — decide.** Landing is a decision queue: field observations awaiting
approval, runs that reported an excursion, runs flagged as extrapolating, and districts
ranked by measured exceedance. Can read everything, approve/reject, and read the audit
log. Cannot run ingest or create sites — a regulator signs off on work, they do not
produce it.

**Analyst — investigate.** Landing is scenario-centric: saved scenarios, recent runs with
their provenance, and anything outside trained support. The Studio is their main screen.
They create sites and scenarios, run them, and compare two runs — where the comparison
says *why* the numbers differ (inputs vs model).

**Field Officer — validate on the ground.** Landing is their own submission ledger split
by state: 🔴 awaiting review, 🟡 approved but not yet in the model, 🟢 in the model, plus
rejected with the reviewer's note. One prominent action: submit an observation (ore
sighting, water sample, groundwater level). They can never approve, and they see only
their own submissions.

**Citizen — understand.** No map of sites, no coordinates, no simulation. A district
picker and a plain-language answer: the band, what was measured, how many wells, when
last sampled, and the standing statement that no such mine exists. This is the only
screen written for someone who has never heard the word "conformal".

## 5. Map experience

The `ml_pipeline` dashboard's map, rebuilt in React and given the portal's data and
role model. Three keyless basemaps — **Map (light, default)**, **Dark**, **Satellite**
— all with place names, because a monitoring portal asks people to locate themselves
and "Bundu" is not a shape. Satellite imagery carries no labels of its own, so a
boundaries-and-places overlay rides above it on a dedicated pane.

Light is the default: the majority use is reading a pale choropleth of measured
groundwater on an office monitor, and a dark ground makes that harder, not easier.
Dark remains for the control-room case where a plume is the subject.

**Every layer toggles live, in two groups.**

*Portal data* — districts (choropleth by measured exceedance) · blocks · monitoring
wells · ISR sites as amber **diamonds** (shape, not colour — amber is reserved for the
pending-sync state) · field observations in three deliberately separate layers:
🔴 dashed hollow (pending review) · 🟡 solid amber (approved, not in model) ·
🟢 solid green (in model).

*Reference geography, served by the engine* — Jharkhand outline · uranium deposits and
the Singhbhum belt envelope · aquifer regime · perennial rivers · groundwater-flow
arrows · fracture-strike ticks. Each is fetched only when switched on; rivers alone is
~1.9 MB and a map that stalls on load is a map people stop opening.

**Clicking the map is the primary interaction** for admin, regulator and analyst. A
click drops a pin, resolves what the engine knows there — lithology, regime, K,
thickness, flow azimuth, gradient, distance to the nearest sampled well — and offers a
run whose plume is drawn live. Outside Jharkhand the pin says so plainly rather than
failing. A field officer gets the same map and layers with no pin and no engine: they
collect evidence, they do not model. A citizen gets their own map (§4).

Left rail: search → basemap → layer groups → district list with bands. Right: a detail
drawer, or the engine panel when a pin is down.

## 5b. Plume drawing rules, inherited not reinvented

Ported from `frontend/ml_pipeline/app.js` because those rules encode decisions whose
reasons would be lost in a rewrite:

- **Colour always encodes concentration**, log-scaled and normalised within the species
  shown. Darker = higher. The contour levels are geometric, so equal ratios get equal
  colour steps.
- **The BIS limit contour is distinguished by weight and a dark casing, never by hue** —
  recolouring it would invert the ramp's meaning at the level a regulator reads first.
- **Low levels draw first**, so a pale outer band cannot paint over the dark core.
- **Reference lines get a white casing.** A 2 px cyan ring is invisible over a dark
  plume fill and nearly invisible over a pale basemap; a halo fixes both at once.
- **The leach zone is its own long-dashed layer** under the contours — ground the
  lixiviant deliberately swept, not a prediction.
- **ML envelope lobes are anchored down-gradient**, never centred on the pin, which
  would draw contamination in the one direction the model says has none.

## 5c. What the map refuses to imply

- A **non-ore pin returns "none above the limit"** and **"no measurable migration"**,
  with the engine's own notice explaining that it will not invent a uranium source term
  (§4.6 rule 3, §4.5 rule 5). A bare `0 ha` would read as a measurement of safety.
- **ML bands are replaced by the engine's `ml_status`** when the surrogate is
  suppressed, so an absent band is explained rather than blank.
- **Extrapolation is loud** — an amber banner naming the offending input.
- An interactive run is labelled **not stored**; only registering the pin as an ISR
  point and running it in the Studio produces an auditable record.

## 6. Simulation Studio

The `ml_pipeline` side panel, rebuilt in React against the **backend** run API — never the
pipeline directly (design §6: the engine is an internal service).

Left rail ① site → ② contaminant → ③ operational sliders → ④ run.
Right: metric cards with **P10–P90 always visible**, the NUREG-1569 excursion panel, a
loud extrapolation banner, and a provenance footer showing the model card hash, artifact
bundle hash and git SHA that produced the number.

A run takes 5–15 s and is queued, polled and persisted — so this is *configure then run*,
not live-drag. That is a consequence of the architecture being honest (every result is
reproducible and audited), and the UI says so rather than pretending to be instant.

## 7. Deliberately marked as not built

The portal must not imply capability it lacks:

| Feature | Status shown in UI |
|---|---|
| Plume contours on a **stored** run | **Planned (P5)** — the Map Console draws contours live from `POST /ml/predict`, but `POST /simulations/{id}` still persists metrics, excursion and hydrogeology *without* geometry, so a past run cannot be redrawn |
| Alerts & subscriptions | **Planned (P7)** — no alert endpoints exist |
| Signed PDF reports | **Planned (P8)** |
| Live sensor feeds | **Not built** — the sensing layer is a 415-station manual network (§7) |
| Downstream receptors | **Planned** — `/sites/{id}/downstream` does not exist |

Each appears as a disabled control with a "planned" chip and the phase, so a reviewer can
see the intended shape without being misled about what runs today.

---

## 8. R15 — instrument readouts, and what §§1–7 above got wrong

**Date:** 2026-08-26. Everything above this line was written 2026-08-12 and parts of it
have been stale for months. Corrections first, because a reader trusting §§3–7 will
otherwise look for screens that no longer exist:

- **There is no "Simulation Studio".** P2 merged it and the Map Console into one
  `/console` with two modes on one canvas (pin, site). §3 and §6 still describe two.
- **Alerts are not "Planned · P7".** They ship: `/alerts`, the header bell, and
  `/citizen/alerts/*`. §7's table is wrong about this.
- **`regulator` was not retired.** §4 describes a regulator landing screen, §2's token
  table omitted the role, and `auth.tsx` restored it. Migration `0019` retired it;
  migration `0022` brought it back with a narrower job — accept or reject what a data
  submitter files, plus (from 2026-08-25) run a screening. It may not publish, ingest,
  administer, or read the audit log.

### What R15 changed

Every screen had converged on two shapes: a `grid-4` of tiles, and a long table. Both are
correct and neither answers a question at a glance. Three shared readouts now carry that
work, defined in `components/instruments.tsx` with `styles/instruments.css`:

| Readout | Replaces | Rule it encodes |
|---|---|---|
| **Determinand scale** | a row in a parameter table | draws the IS 10500 acceptable/permissible marks the value is judged against; the track ends at 2× the governing limit and off-scale values pin to the end rather than clamping silently; `not_tested` renders a dashed empty channel with NO marker, because a marker at zero is a reading |
| **Composition bar** | a `grid-4` of counts | proportion, with the never-analysed share HATCHED so an unmeasured share reads as a different kind of thing from a measured one |
| **Statement** | the tile wall at the top of a screen | one sentence naming what the screen is for, with the figures beneath it as a reading rather than eight equally-weighted boxes |

Plus a work queue, a ranked bar, a coverage grid (four steps, per-column scaling, counts
still printed), a freshness chip, and the citizen verdict block.

Screens restructured: **Overview** (five role variants, `regulator` split out into its
own), **My Area**, **Water Quality**, **Data & Gaps**. `/console` was deliberately left
alone — it was already map-first and its rules are §§5–5c above.

### Four defects found by pulling the screens apart

1. **`--role-regulator` was undefined** while `auth.tsx` referenced it. An undefined
   custom property is invalid at computed-value time, which resolves per property: the
   role pill (inherited `color`) fell back to `--text`, and the avatar (non-inherited
   `background`) fell back to `transparent`, putting `--on-accent` near-black text on the
   near-black panel. A regulator's account button was invisible. Token added at `#a78bfa`
   — measured in-browser at 6.5:1 as text on `--panel` and 7.0:1 as a fill behind
   `--on-accent`.
2. **`regulator` rendered the admin screen**, issuing `GET /users` (403 on every sign-in)
   and offering a tile routing to `/admin`, which the guard then refused.
3. **The `/health` chip could never have worked.** It fetched a bare `/health`, but the
   API is same-origin only under `/api/*` — the Vite proxy and `run_worker_first` both
   route that prefix and nothing else — so it received the SPA's own index.html and
   `.json()` threw. It had always shown an amber "API unknown": a reported fault that did
   not exist. Replaced with model state from `/model-ops/model`.
4. **A stale `Planned` card** on Data & Gaps claimed the monitoring-plan optimisation was
   not implemented, directly below the section that implements it.

### Two API inconsistencies the UI first worked around, then had fixed

Both were named on screen in the first pass rather than smoothed over, and both
were fixed in the backend the same day. Recorded here because the workaround and
the fix are different states and the code comments reference both.

- **`GET /citizen/my-area` banded on uranium ALONE**, while `/public/risk/*` had
  banded on uranium, nitrate and fluoride since 2026-08-25. The same block could
  read "Low concern" in My Area and "High concern" on the public map, correctly,
  on one dataset. The UI's first response was to state which determinand its
  verdict rested on. The rule now lives once in
  `app/services/health_bands.py`, both endpoints apply it, and My Area draws all
  three determinands against their published limits instead of one. See
  `docs/LIMITATIONS.md` §4f.
- **`iron` was missing `health=True`** in `water_quality.py`'s `STANDARD`, though
  the interpretation string the same module returns names it in the health set.
  Fixed; iron now groups with the other four health determinands on the
  water-quality screen.

While fixing the first, two further copies of the same split surfaced: `_explain`
was uranium-only prose captioning a multi-determinand band on three handlers
(deleted), and the `Not tested` band was unreachable in the SQL ladder because
`health_tests = 0` already implied `max_u IS NULL` (now tested on `samples = 0`).

### One frontend rule that came out of the fix

`undefined` and `null` are different findings on a citizen surface and the code
distinguishes them. `null` means the server looked and nothing was analysed —
draw the gap. `undefined` means the response never carried the field, which is
what an older API returns, and drawing "Not tested" for it would **invent** a
monitoring gap. A fabricated gap is a false statement even though it errs toward
caution, so My Area renders a determinand's scale only when the field is present.
