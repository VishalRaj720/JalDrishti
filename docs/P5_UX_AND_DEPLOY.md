# P5 — UI overhaul and ml_pipeline feature parity

> Rewritten from a free-form request, 2026-08-17; decisions folded in after a
> round of questions. This is the spec to work from. Nothing here is built yet.
> **Deployment is explicitly deferred** — see §7.

## 0. Objective

Two goals, in order:

1. **Bring the portal to full parity with the `ml_pipeline` dashboard** — its
   data-layer colours, its map behaviour, and every quantity it reports — while
   keeping the five-role model, the review workflow and the provenance spine
   the portal adds on top.
2. **Then** make it look clean, modern and spacious rather than like a 2010
   government portal.

The visual redesign is second, not first: restyling a screen and then adding six
new panels to it means styling twice.

---

## 1. What I verified before writing this

Four facts that change what the work actually is.

### 1.1 The colour tokens are already identical — the *data layer* colours are not

`frontend/ml_pipeline/styles.css` and `frontend/portal/src/styles/theme.css`
declare the same `--bg --panel --card --card2 --line --text --muted --accent
--danger --warn --ok --frac --porous` values, byte for byte. So "use the
ml_pipeline colour scheme" is not about the palette. The real divergences are in
what gets drawn **on the map**:

| Layer | ml_pipeline | portal today | action |
|---|---|---|---|
| Ore deposit | `#ff2d2d` red, fill .22 | `#ffd166` yellow | **adopt ml_pipeline** |
| Prospective belt | `#e8833a` orange, dashed, fill .05 | `#b08d3a` | **adopt ml_pipeline** |
| Aquifer — fractured | `--frac` `#e8833a` | `#7fd1ae` | **adopt ml_pipeline** |
| Aquifer — porous | `--porous` `#3f8cff` | `#d8b46a` | **adopt ml_pipeline** |
| Jharkhand outline | `#6fd1ff` @ .7 | `#c9d4e2` | **adopt ml_pipeline** |
| Outside-state mask | present, `fillOpacity .55` | **absent** | port at **.30** |
| Rivers / flow / strike | `#3aa0ff` / `#37d39b`+`#7f8a99` / variance-coloured | same | already correct |
| Plume ramp | `#ffcdd2 → #b71c1c`, log-scaled | same | already correct |

**DECIDED:** all three basemaps stay (Map / Dark / Satellite), **light remains
the default**, and every legend and overlay colour matches the ml_pipeline
dashboard.

> **Contrast — DECIDED: same hues, raise opacity on light.** Those overlay
> colours were chosen against a *dark* basemap. On light, the palest plume band
> (`#ffcdd2` at `fillOpacity 0.12`) is effectively invisible and the `#6fd1ff`
> outline is weak on pale ground. So the **hues are identical on every
> basemap** — the legend always matches what is drawn — while the fill-opacity
> floor and stroke weight step up on the light basemap only, alongside the white
> casing already used for reference lines. The adjustment is a function of the
> active basemap, applied in one place, not a second palette.

### 1.2 Chloride cannot be a modelled species

`ml_pipeline/config/parameters.py`:

```
SPECIES     = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")
ML_SPECIES  = (same four)
EXCURSION_ONLY_SPECIES = ("chloride_mg_l",)
```

Chloride is solved on the **analytical path only**, in
`dashboard/isr_excursion.py`, which never calls the surrogate. That separation
is deliberate — it is what lets excursion indicators be added without
retraining. Moving chloride into `SPECIES` requires a full synthetic re-bake and
retrain plus a re-run of the field coverage gate (`PRODUCT_DESIGN.md` §4.6
rule 9). **Not in scope.**

So "show all species including chloride" resolves to:

- **uranium, sulfate, TDS, radium-226** — full treatment: analytical value, ML
  P10–P90 band, plume contours.
- **chloride** — ring concentration, baseline, UCL, over/under only, labelled an
  excursion indicator. No band, no contour, no plume.

Chloride is **already on screen** in the excursion table. What is missing is
per-species plumes and metrics for the other four.

Also frozen: **uranium and radium are never excursion indicators** (NUREG-1569
p.137 — retarded and strongly sorbing). The excursion panel stays chloride /
TDS / sulfate.

### 1.3 "% of drinking water affected" is a probability, not a share

The metric wanted is ml_pipeline's **Shallow Aquifer Impact (Layer 1 · village
wells)**. The engine returns:

```json
"vertical": {
  "shallow_impact_probability": 0.355,
  "risk_band": "moderate",
  "advective_breakthrough_fraction": 0.321,
  "years_to_vertical_breakthrough": 31.1,
  "dominant_pathway": "advective_leakage",
  "pathways": {"dispersive": 0.0, "advective_leakage": 0.321, "wellbore": 0.05},
  "separation_m": 120.0, "water_table_m": 1.6, ...
}
```

`shallow_impact_probability` is **the probability that contamination reaches the
shallow aquifer village wells draw from** — not "35% of drinking water will be
affected". Labelling it that way on a government screen would be a material
misstatement. It ships as **"Shallow aquifer impact — 36% probability
(moderate)"**, with dominant pathway and years-to-breakthrough beside it.

### 1.4 The ISR point cannot currently hold the parameters

`IsrPoint` has `name`, `location`, `injection_rate`, `injection_start_date`,
`injection_end_date`, `owner_org_id` — and `injection_rate` is the only engine
input among them. Everything else has to be added.

---

## 2. Workstream A — map and visual behaviour

| # | Requirement | Notes |
|---|---|---|
| A1 | Adopt every ml_pipeline **overlay / legend colour** (§1.1 table); keep all three basemaps with **light as default** | Legend swatches must match what is drawn, on every basemap |
| A2 | Place names legible at every zoom | Already true on all three; verify at z12+ where CARTO labels thin out, and that the new mask does not grey out labels *inside* Jharkhand |
| A3 | **Dim outside Jharkhand ~30%** when the Jharkhand-outline layer is on | Port the inverse mask from `app.js:283` — a world rectangle with the state rings punched out — at `fillOpacity 0.30` instead of its 0.55, bound to the layer toggle, `interactive: false`, in a pane below the data overlays |
| A4 | **Dynamic 1:X scale** at the bottom | Keep Leaflet's distance bar, add the ratio beside it. A representative fraction depends on display DPI; computed at the 96-dpi CSS-pixel standard, so it is nominal. Label it so rather than implying a calibrated scale |
| A5 | **Collapsible side rail — manual only, available everywhere** | See A5 below |

### A5 — the collapsible rail, in detail

**DECIDED: the user collapses and expands it themselves, always. Nothing
collapses it automatically — not the timelapse, not registration, not anything.**

- A collapse control in the rail header; when collapsed, a thin persistent strip
  along the map edge expands it again. Tapping the rail body is *not* the
  trigger — it is full of toggles, sliders and a district list, and a
  tap-anywhere target would fire every time someone reaches for a control.
- **Available on every screen that has a rail**, in every state: Map Console,
  citizen map, and the Studio. Including — specifically — while the right-hand
  drawer is open.
- **The registration case is the one that motivated this.** Setting a dozen ISR
  parameters happens in the floating right drawer; the user must be able to
  retract the left rail at that moment so the map is wide and the drawer has
  room. Rail state and drawer state are independent — neither drives the other.
- The state persists across navigation within a session, so it does not have to
  be re-collapsed on every screen.
- The map calls `invalidateSize()` after the transition, or Leaflet keeps
  serving tiles for the old width.

## 3. Workstream B — ml_pipeline feature parity

Everything the ml_pipeline left rail shows, in the portal. **No backend change
needed** — `/api/v1/ml/predict` already returns all of it.

| ml_pipeline panel | Portal status |
|---|---|
| ① Pin — hydrogeology, data confidence, ore notice | **done** |
| ② Contaminant + aquifer regime | species done; **regime override missing** |
| ③ Operational sliders | **hydraulic gradient and travel azimuth missing** |
| ④ Timeline & ISR lifecycle — start date, play/pause/reset, pace, phase bar | **missing entirely** → Workstream C |
| ⑤ Prediction engine — ML vs analytical | done; **`ml_status`, far-field note, drift badge missing** |
| ⑥ Depth & vertical stratification — ore depth/thickness + **depth schematic SVG** | **missing entirely** |
| Metrics — 7 cards | **3 of 7.** Missing: excursion probability, BIS breach badge, peak concentration, boundary concentration, **shallow aquifer impact** (§1.3) |
| Legend + disclaimers | partial |

## 4. Workstream C — the ISR point as a fully configured site

**DECIDED: the site carries everything; the Studio varies only evaluation year.**

An ISR point stops being a bare coordinate and becomes a fully specified
hypothetical operation.

### C1 — migration `0015`, adding to `isr_points`

Every engine input except `time_years` (the Studio variable) and the withheld
expert overrides:

| Column | Engine field | Range | Default |
|---|---|---|---|
| `injection_rate_m3_day` | same | 200–8000 | 2500 |
| `bleed_percent` | same | 0–8 | 2.0 |
| `operation_years` | same | 1–20 | 8 |
| `restoration_years` | same | 0–30 UI, 0–10 trained | **0** — see C3; left at 0 whenever registration does not set it, so "no remediation sweep" is the explicit default rather than an unanswered field |
| `wellfield_width_m` | same | 100–800 | 300 |
| `monitor_ring_m` | same | `P.MONITOR_RING_RANGE_M` | `P.COMPLIANCE_BUFFER_M` |
| `ore_depth_m` | same | `P.VERTICAL[...]` | 150 |
| `ore_thickness_m` | same | `P.VERTICAL[...]` | 20 |
| `regime_override` | `regime` | null / fractured / porous | null (auto from pin) |
| `gradient_i` | same | 0.0005–0.02 | null (from flow field) |
| `azimuth_deg` | same | 0–360 | null (from flow field) |
| `start_date` | same | ISO date | null |

Bounds come from `ml_pipeline` at import rather than being retyped, so a
parameter range cannot drift between the engine and the form.

**Two schema notes.** `injection_rate` (existing) and `injection_rate_m3_day`
are the same quantity — migrate the old column rather than adding a second.
`injection_start_date` / `injection_end_date` overlap with `start_date` +
`operation_years`; keep `start_date` and `operation_years` as the engine's
inputs and derive the end date rather than storing a third source of truth.

**Backfill:** the seeded Jaduguda point has none of these. Backfill with the
defaults above and mark them as defaults in the UI, so nobody reads an
unreviewed default as a chosen parameter.

### C2 — registration form, in the right-hand drawer

**DECIDED: clicking an unregistered spot resolves the hydrogeology and offers
registration. It does not run anything ad hoc.** Every result therefore traces
to a named, parameterised operation — there is no way to produce a number whose
inputs nobody chose. This replaces today's "click and run on defaults".

So a map click gives: resolved lithology, regime, K, thickness, flow azimuth,
gradient, nearest-well distance and ore proximity — then a **register a site
here** action.

The form lives in the **floating right drawer** and captures the full §C1 set,
grouped: **operation** (injection rate, bleed, operation years, restoration
years) · **geometry** (well-pattern footprint, monitor ring) · **vertical** (ore
depth, thickness, with the depth schematic live beside them) · **advanced**
(regime override, gradient, azimuth, start date), collapsed by default and each
showing the value the pin resolved, so overriding is a deliberate act.

Bounds come from `ml_pipeline` at import, never retyped. The left rail is
collapsible while this drawer is open (A5).

### C3 — the Studio becomes a timelapse, with two live controls

Pick site → pick species to draw → scrub or play **evaluation year** → watch the
plume grow, peak and flush. Plus the ml_pipeline lifecycle furniture: start
date, play/pause/reset, pace selector, phase bar, readout.

**Two parameters stay editable here, not just one:**

| Control | Why it is live in the Studio |
|---|---|
| **Evaluation year** | The timelapse axis |
| **Restoration years** | The one *decision* a reviewer needs to test against a fixed site. "What if we sweep for 5 years instead of 0?" is a remediation question, not a change to the operation being assessed |

Everything else comes from the registered site and is read-only here, shown as
a summary strip so the reader can see what is fixed.

Restoration years **defaults to 0** — an operation with no remediation sweep —
whenever registration left it unanswered. It is editable in the Studio
regardless, so a site registered without one can still be tested with a sweep.
Changing it re-runs; it is not a redraw, because the source-zone flush term
depends on it.

> Note for the build: `restoration_years` has a UI exploration bound of 0–30 that
> is deliberately **decoupled** from the trained envelope (the model card's max
> is currently 10). Beyond that the analytical engine serves and the ML band is
> flagged, not refused. The Studio must surface that flag when the slider goes
> past the trained max rather than quietly serving a band that no longer means
> 80%.

### C4 — interactive vs auditable

Frames call `/ml/predict` and are **not persisted**. A separate **"capture this
frame as a run"** writes one `simulations` row with its provenance triple.
Playing 50 frames must not write 50 rows.

### C5 — scenarios

Named scenarios keep working, now as *site + year* rather than a full parameter
set.

## 5. Workstream D — all species in one result

**DECIDED: animate one species, tabulate all four.**

- **D1** The map draws the plume for **one selected species at a time** — four
  overlapping contour sets are unreadable — and the species switcher redraws
  without re-running the engine where the result is cached.
- **D2** A table beside it shows **all four ML species at the current year**:
  area, migration, compliance concentration, each with its P10–P90 band. Plus
  chloride as an excursion-indicator row (§1.2).
- **D3** One frame therefore costs one engine call for the animated species;
  the other three are fetched for the *current* year only, not per frame.
- **D4** Per-species extrapolation flags stay per-species — one species outside
  trained support must not mark the others.

## 6. Workstream E — visual redesign

Only after A–D, so it is styled once.

**DECIDED: a modern data tool** — the Linear / Vercel / Grafana register, not a
brochure and not a 2010 government portal. Concretely:

- **Colour is reserved for data and state.** Chrome goes neutral; the only
  saturated colour on screen should mean something — a band, a risk level, a
  role, a plume. Today the chrome competes with the map.
- **Hierarchy through typography and spacing, not boxes.** Fewer filled cards
  and heavy borders; one consistent spacing scale; section headings that
  actually rank. Most of the current `.card` chrome can go.
- **Tabular numerals everywhere a number can change** — metrics, bands, the
  timelapse readout — so digits stop jittering as values update.
- **Dense but not cramped.** This is an instrument: a regulator should see the
  decision queue, the bands and the map without scrolling. Whitespace buys
  legibility, not emptiness.
- **Motion only where it carries meaning** — the timelapse, the rail collapse,
  state transitions. No decorative animation.
- **The map is the subject.** With the rail collapsed the map should feel like
  the application, not a panel inside it.

**Constraint that does not bend:** the honesty furniture stays. The
`HYPOTHETICAL` framing, extrapolation banners, the NUREG "not
regulatory-compliant" note, uncertainty bands, the 🔴/🟡/🟢 sync states, "no
measurable migration" instead of `0`. Restyle them — elegant instead of shouty —
but removing them to look cleaner would make the product dishonest. That is the
one place where "cleaner" and "better" diverge here.

## 7. Deployment — deferred

**Out of scope for this round.** Retained as a checklist for when it comes up:
secrets out of `.env` and rotated · demo passwords hardened or gated · managed
Postgres **with PostGIS** and the `jaldrishti_app` role so RLS stays live ·
`ml/artifacts/` and `Datasets/` shipped with the image · frontend built to
static and served same-origin · compose extended past db+backend · HTTPS,
domain, `CORS_ORIGINS` · `slowapi` needs a shared store behind >1 worker.

---

## 8. Constraints inherited — must not be violated

From `PRODUCT_DESIGN.md` §4.5/§4.6 and `CLAUDE.md`:

1. The analytical engine is the authority; ML supplies bands only
2. Uranium and radium are never excursion indicators
3. Non-ore zones show no uranium plume — the tool cannot invent contamination
4. No bare point estimates; every predicted quantity carries its band or an
   explicit "deterministic" label
5. Extrapolation is loud
6. Migration below map resolution reads "no measurable migration", never `0`
7. The hypothetical premise is never more than one glance away
8. Field data carries its 🔴/🟡/🟢 state
9. No new datasets, species or modelling approaches without a re-bake, retrain
   and coverage-gate re-run
10. Citizens get no ISR coordinate, ore polygon or model output
11. No database value crosses into the engine as chemistry or hydrogeology

---

## 9. Decisions taken

| Question | Decision |
|---|---|
| Basemaps | All three kept, **light default**; overlay and legend colours match ml_pipeline exactly (§1.1) |
| Light-basemap contrast | **Same hues everywhere**, opacity floor and stroke weight raised on light only (§1.1) |
| Timelapse | **Animate one species, tabulate all four** (§5) |
| Site parameters | **The site carries everything**; the Studio varies **evaluation year and restoration years** only (§4, C3) |
| Restoration years | Defaults to **0** when registration leaves it unset; always editable in the Studio (§C3) |
| Click-to-run | **Removed.** A click resolves the pin and offers registration; every run goes through a configured site (§C2) |
| Rail collapse | **Manual only, never automatic**, available on every screen and in every state — including while the registration drawer is open (§A5) |
| Visual direction | **Modern data tool** — Linear / Vercel / Grafana register (§6) |
| Deployment | **Deferred** (§7) |

No open questions. Ready to build on request.

## 10. Suggested build order

1. **A1 + A3 + §1.1 contrast** — overlay colours and the Jharkhand mask. Small,
   visible, and settles the palette before anything else is styled.
2. **A5** — the collapsible rail. Everything after this is easier to look at.
3. **A4** — the 1:X scale.
4. **C1** — migration `0015` and the backfill. Blocks C2 and C3.
5. **C2** — the registration drawer, and removing ad-hoc click-to-run.
6. **B** — the missing panels and the 4 missing metric cards, against the
   already-complete `/ml/predict` payload.
7. **C3 + C4 + D** — the timelapse Studio and the all-species table.
8. **E** — the redesign, once nothing new is going to be added.
