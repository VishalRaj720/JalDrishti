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

Dark Leaflet canvas, no raster basemap — the risk ramp is the information, and tiles
would fight it.

- **Districts** choropleth by measured exceedance, click → drawer
- **ISR sites** as amber **diamonds** (shape, not colour — amber is reserved for the
  pending-sync state)
- **Field observations** in three deliberately separate layers: 🔴 dashed hollow (pending
  review) · 🟡 solid amber (approved, not in model) · 🟢 solid green (in model)
- **Monitoring network** — stations and wells, the CPS sensing layer
- Left rail: search → layer toggles → entity list with badges. Right: detail drawer.
- Persistent `HYPOTHETICAL` ribbon (design §4.5 rule 6).

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
| Plume contour rendering | **Planned (P5)** — the run API persists metrics, excursion and hydrogeology, *not* geometry |
| Alerts & subscriptions | **Planned (P7)** — no alert endpoints exist |
| Signed PDF reports | **Planned (P8)** |
| Live sensor feeds | **Not built** — the sensing layer is a 415-station manual network (§7) |
| Downstream receptors | **Planned** — `/sites/{id}/downstream` does not exist |

Each appears as a disabled control with a "planned" chip and the phase, so a reviewer can
see the intended shape without being misled about what runs today.
