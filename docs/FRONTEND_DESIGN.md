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
