# JalDrishti `ml_pipeline/` — The Complete Architecture Guide

*A ground-up explanation for someone new to both hydrogeology and machine learning.
Every formula is derived, every file is explained, every dataset is documented,
and every limitation is stated honestly.*

**Last updated:** 2026-07-13 (post QA sweep + restoration-continuity fix + final retrain)

---

## Table of contents

1. [What this system is](#1-what-this-system-is)
2. [The real-world process: ISR uranium mining in 10 minutes](#2-the-real-world-process)
3. [The big picture: five layers](#3-the-big-picture)
4. [Hydrogeology from zero — every formula, derived](#4-hydrogeology-from-zero)
5. [The datasets — what each one is and what it feeds](#5-the-datasets)
6. [The machine-learning layer for beginners](#6-the-ml-layer)
7. [The codebase, file by file](#7-the-codebase-file-by-file)
8. [The life of a request](#8-the-life-of-a-request)
9. [The test suite — what each file guards](#9-the-test-suite)
10. [Honest limitations — what is real, what is screening-grade, what is missing](#10-honest-limitations)
11. [Glossary](#11-glossary)

---

## 1. What this system is

JalDrishti's `ml_pipeline/` answers one question:

> *"If a hypothetical alkaline in-situ-recovery (ISR) uranium mine operated at
> this point in Jharkhand, India, how far and how wide would the groundwater
> contamination spread, and would it breach drinking-water standards?"*

You drop a pin on a map, set operational sliders (injection rate, bleed,
operation years, evaluation time, restoration sweep…), and get back:

- a **plume map** (concentration contours, BIS-standard breach outline),
- **decision metrics** (affected area in hectares, maximum migration distance,
  concentration at a compliance ring, probability of an "excursion"),
- **uncertainty bands** (P10–P90, conformally calibrated to 80% coverage),
- **context** (does the plume reach a river? does it threaten shallow village
  wells? is the model extrapolating beyond what it was trained on?).

Two engines produce these numbers and are shown side by side:

1. **The analytical (physics) engine** — closed-form contaminant-transport
   equations evaluated on a grid. This is the *authority*: it produces the plume
   geometry and, crucially, the labels the ML model is trained on.
2. **The ML surrogate** — gradient-boosted trees that learned the physics
   engine's outputs. Its value is not accuracy (the physics is right there) but
   **calibrated uncertainty**: it carries P10/P50/P90 bands that account for
   parameter uncertainty (how well do we actually know K, Kd, the gradient…?),
   with a statistical coverage guarantee.

⚠️ **This is an uncalibrated theoretical screening tool.** The physics was
shaped on Texas ISR data and *transferred* to Jharkhand geology. No Jharkhand
ISR mine exists to validate against. It is for screening and education — never
permitting.

---

## 2. The real-world process

### What is ISR mining?

Conventional uranium mining digs the ore out. **In-Situ Recovery (ISR)** never
excavates: it drills wells into the ore-bearing aquifer, injects a **lixiviant**
(in alkaline ISR: groundwater fortified with oxygen + carbonate, chemically like
soda water) that dissolves uranium off the rock, and pumps the uranium-laden
water back out through recovery wells. The uranium is stripped at the surface
(ion exchange) and the water is re-fortified and re-injected in a loop.

Key vocabulary, all of which appears in the code:

- **Wellfield**: the pattern of injection + recovery wells (5-spot/7-spot
  patterns, wells 15–50 m apart). Our `wellfield_width_m` slider is the
  footprint width of this pattern (100–800 m).
- **Bleed**: operators deliberately pump out slightly *more* water than they
  inject (typically 0.5–3%). This net extraction pulls groundwater *inward*
  from all sides, hydraulically containing the lixiviant. `bleed_percent`.
- **Excursion**: lixiviant escaping past the ring of monitoring wells around
  the wellfield. Detected when indicator chemistry (chloride, conductivity)
  exceeds control limits. Our `excursion_probability` estimates this.
- **Restoration**: after mining, the operator must clean the aquifer:
  **groundwater sweep** (pump without injecting — outside water flows in and
  flushes the zone), **reverse osmosis** treatment with re-injection of clean
  permeate, and sometimes chemical **reductants** to immobilize residual
  uranium. `restoration_years` is the length of this active sweep.
- **Stability monitoring**: after restoration, years of monitoring (the US EPA
  proposed ≥30 yr, shortenable after 3 consecutive stable years).

### Real timescales (from the literature, so you can sanity-check the sliders)

| Phase | Real-world duration | Our slider range |
|---|---|---|
| Production, single wellfield | 1–3 yr (most U in first 6 months) | `operation_years` 1–20 (default 8 ≈ a multi-wellfield mine unit, not one wellfield) |
| Active restoration | ~2 yr formal minimum; Texas median 5.0 yr (IQR 3.8–6.5), median 18.6 pore volumes | `restoration_years` 0–50 (values > 10 = ML extrapolation, flagged) |
| Post-closure monitoring | EPA ≥ 30 yr | `time_years` 0–50 (values > 20 = ML extrapolation, flagged) |

### Why Jharkhand?

The Singhbhum Shear Zone in East Singhbhum hosts India's oldest uranium mines
(Jaduguda, Bhatin, Narwapahar, Turamdih, Banduhurang, Mohuldih, Bagjata — all
conventional underground/open-pit, run by UCIL). No ISR exists there — the
geology is fractured metamorphic rock, not the porous sandstone ISR prefers —
which is exactly why this is a *hypothetical screening* exercise: "what if?"

---

## 3. The big picture

Five layers, each feeding the next:

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. DATA LAYER (data_prep/ + Datasets/)                               │
│    Real Jharkhand geology, water quality, rivers, DEM, ore bodies,   │
│    fracture lineaments + real Texas ISR operating records            │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 2. PHYSICS ENGINE (physics/transport.py)                             │
│    Domenico advection-dispersion plume + Tang fracture flow +        │
│    source-zone disc + restoration drawdown → concentration field     │
│    → metrics (area, migration, compliance conc, breach)              │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 3. SYNTHETIC DATA FACTORY (synthetic/generate.py)                    │
│    900 scenarios x 5 times x 3 species = 13,500 rows; each row =     │
│    39 features + physics labels + Monte-Carlo P10/P50/P90 bands      │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 4. ML TRAINING (ml/train.py → ml/artifacts/*.joblib)                 │
│    XGBoost quantile models with monotone constraints +               │
│    Mondrian split-conformal calibration (CQR) → 80% bands            │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│ 5. SERVING (dashboard/server.py + frontend/)                         │
│    FastAPI + vanilla-JS/Leaflet map. Every request runs BOTH         │
│    engines; a drift monitor watches their disagreement.              │
└──────────────────────────────────────────────────────────────────────┘
```

The **key design invariant** of the whole system: *train == serve*. The exact
same feature-building code (`data_prep/feature_engineering.py`) and the exact
same physics functions run inside the synthetic generator (layer 3) and inside
the live server (layer 5). Any drift between them silently corrupts the ML —
several of the project's historical bugs were exactly such drifts, which is why
the test suite pins them.

---

## 4. Hydrogeology from zero

This section derives every formula in `physics/transport.py` and
`data_prep/feature_engineering.py`, assuming you know basic calculus and
nothing about groundwater.

### 4.1 Darcy's law — how fast does groundwater move?

Henry Darcy (1856) ran water through sand columns and found the discharge per
unit area is proportional to the pressure drop per unit length:

```
q = K · i
```

- `q` = **Darcy flux** [m/day] — volume of water crossing a unit area per day.
- `K` = **hydraulic conductivity** [m/day] — how permeable the rock is.
  Gravel: 100s. Sandstone: 0.1–10. Fractured gneiss: 0.01–5 (flow only in the
  cracks). This is the single most important rock property in the model.
- `i` = **hydraulic gradient** [dimensionless] — the slope of the water table,
  e.g. 0.003 means the water level drops 3 m per km. Water flows "downhill"
  along this slope. In our model `i` comes from a real interpolated water-level
  surface (the D1 flow field) unless you override the slider.

But `q` is not the speed of a water molecule! Water only moves through the
pore space, which is a fraction `φ` (porosity) of the rock volume. The same
volume squeezed through less area moves faster:

```
v = q / φ = K · i / φ        ← seepage (linear) velocity [m/day]
```

`φ_mobile` (effective/mobile porosity) is the fraction of the rock volume where
water *actually flows* — in fractured rock this can be under 1% (φ ≈ 0.01),
which is why fractured plumes are *fast*: divide by a small number.

> **Code:** `build_feature_row` computes `darcy_flux_q = K*i` and
> `seepage_velocity_v = q/phi_mobile`. Both are ML features.

### 4.2 Retardation — why contaminants lag behind the water

Dissolved uranium sticks to mineral surfaces (adsorption) and un-sticks. At any
moment, a fraction of the contaminant mass rides in the water, and a fraction
sits on the solids. The plume front therefore moves slower than the water by
the **retardation factor** `Rd`.

**Derivation** (porous rock, linear equilibrium sorption): let `C` be the
water concentration [kg/m³] and `S` the sorbed mass per rock mass [kg/kg], with
the linear isotherm `S = Kd·C` (Kd = distribution coefficient [m³/kg], usually
quoted in L/kg). In one m³ of aquifer:

- mass in water = `n · C`             (n = total porosity)
- mass on solids = `ρb · S = ρb · Kd · C` (ρb = bulk dry density = (1−n)·ρ_grain)

Total mass = `(n + ρb·Kd)·C`. Only the water-borne fraction moves, so the
contaminant velocity is the water velocity times `n·C / [(n+ρb·Kd)·C]`, i.e.

```
v_c = v / Rd,     Rd = 1 + (ρb · Kd) / n
```

> **Code:** `retardation_factor()` in feature_engineering.py, with Kd converted
> L/kg → m³/kg (×10⁻³). For uranium under *alkaline* ISR chemistry, Kd is LOW
> (uranyl-carbonate complexes barely sorb) — that is the whole reason alkaline
> lixiviant works, and it is why the escaped uranium is mobile.

**Fractured rock is different.** The solute only touches fracture walls, not
the bulk rock, so the porous formula (which multiplies by bulk density) badly
over-predicts retardation. Instead, two mechanisms:

1. **Dual-porosity exchange**: the fracture water exchanges with (nearly)
   immobile matrix water. Late-time apparent retardation → `1 + β` where β is
   the immobile-to-mobile capacity ratio (Goltz & Roberts 1986). The engine
   applies this *time-dependently* through a "retarded clock" (`retarded_clock`)
   — early plume moves at water speed, late plume at speed/(1+β).
2. **Matrix diffusion** (next section) — where Kd actually acts in fractured rock.

### 4.3 Matrix diffusion — the Tang solution for fractured rock

In fractured rock, contaminant in a fracture leaks sideways into the porous
matrix by molecular diffusion, dramatically attenuating the front. Tang, Frind
& Sudicky (1981) solved a single fracture with matrix diffusion; the
zero-dispersion form used here gives concentration vs distance as an
**attenuation factor**:

```
A(x) = erfc[ (σ·√t / 2) · r / √(1−r) ],     r = x / X_w
```

where `X_w` is the *water* front position and σ collects the matrix
properties:

```
σ = θ_m · √(R_m · D_e) / b     [day^-1/2]
```

- `θ_m` = matrix porosity, `D_e` = effective diffusion coefficient in the
  matrix, `b` = fracture half-aperture,
- `R_m = 1 + ρb·Kd/θ_m` = *matrix* retardation — this is the physical channel
  through which Kd acts in fractured rock (sorption onto matrix pore walls).

Intuition: the deeper into the network you go (r → 1), the longer the water
took to get there, the more time it had to bleed mass into the matrix — the
erfc argument blows up and concentration collapses. The engine takes the
**maximum** of the retarded-continuum front and this Tang envelope
("early-arrival channel") — a deliberately conservative union.

> **Code:** `matrix_sigma()`, `tang_attenuation()`, `_tang_reach()` in
> transport.py. Fracture aperture and D_e defaults in `P.FRACTURE`.

### 4.4 The advection–dispersion equation and the Domenico plume

The governing PDE for a dissolved, sorbing, non-reacting contaminant:

```
Rd ∂C/∂t = -v ∂C/∂x + ∂/∂x(D_L ∂C/∂x) + ∂/∂y(D_T ∂C/∂y)
```

- advection: the plume rides the flow (−v ∂C/∂x),
- dispersion: mechanical mixing smears it, more along-flow (D_L = α_L·v) than
  across (D_T = α_T·v). α is **dispersivity** [m].

Solving this exactly in 2-D with a finite-width source is messy; **Domenico
(1987)** popularized an approximate product solution used across the entire
screening-model industry (BIOSCREEN, etc.). Our steady-source variant:

```
C(x,y) = C0 · F_long(x) · F_tran(x,y)

F_long(x)   = ½ · erfc[ (x − X_c) / (2·√(α_L · X_c)) ]
F_tran(x,y) = ½ · [ erf((y + W/2)/(2√(α_T·x))) − erf((y − W/2)/(2√(α_T·x))) ]
```

**Where these come from:**

- *F_long*: the 1-D advection–dispersion step response (Ogata–Banks 1961) is
  `½·erfc[(x−vt)/(2√(D_L t))]` — a smeared step centered on the front `x = vt`.
  Substituting the front position `X_c` for `vt` and noting
  `√(D_L·t) = √(α_L·v·t) = √(α_L·X_c)` gives our form. (The full Ogata–Banks
  has a second exponential term that matters only near x=0; dropping it is the
  standard Domenico simplification — one consequence: the *upstream* region is
  painted at C0, see §10.)
- *F_tran*: a source of width W is a line of point sources; integrating the
  Gaussian transverse spread `exp(−y²/4D_T·τ)` along the source width gives the
  difference of two error functions. The spread grows with travel distance
  (`√(α_T·x)`) because a parcel farther downstream has dispersed longer — this
  is why plumes are cigar-shaped: `α_T ≪ α_L`.

> **Code:** `_long_factor()`, `_tran_factor()`, `concentration_field()` in
> transport.py; the vectorized Monte-Carlo version is `_stack_field()`.

### 4.5 Scale-dependent dispersivity

Dispersivity is not a rock constant — it grows with the scale of observation
(bigger plumes sample more heterogeneity). The model uses the Xu & Eckstein
(1995) regression over hundreds of field tracer tests:

```
α_L = 0.83 · (log10 L)^2.414     [m],   L = transport distance
α_T = ratio · α_L,   ratio = 0.02 (fractured) or 0.10 (porous)  [Gelhar 1992]
```

The fractured ratio can also come from real fracture-orientation data (§4.10).

### 4.6 Hydraulic containment — the bleed

The wellfield's net extraction `Q_net = Q_out − Q_in` pulls water inward.
Capture-zone theory: a well pumping `Q_net` from an aquifer with regional Darcy
flux `q` and thickness `b` captures a strip of width `W_capture = Q_net/(q·b)`.
The regional flow *through* the wellfield's own cross-section is
`Q_regional = q·b·W`. So the fraction of its own footprint the wellfield
captures — the **containment efficiency** — is:

```
η = min(1, Q_net / (q · b · W))
```

η = 1 (complete capture, zero outward escape) when net extraction exceeds the
regional throughflow — a properly-bled ISR wellfield contains; excursions come
from insufficient bleed, pump downtime (`downtime_fraction` degrades η), or
seasonal gradient swings.

> **Code:** `containment_efficiency()` in feature_engineering.py.

### 4.7 The three-phase front position

Where is the plume's leading edge at evaluation time `t`?

```
Phase 1  [0, t_op]              velocity v·(1−η)   (operations: bleed holds most of it)
Phase 2  (t_op, t_op+t_rest]    velocity 0          (restoration sweep: pumping holds the front)
Phase 3  (t_op+t_rest, t]       velocity v          (post-closure: free drift)
```

```
X_c(t) = v·(1−η)·clock(min(t, t_op)) + v·[clock(t) − clock(t_op+t_rest)]⁺
```

where `clock()` is the dual-porosity retarded clock (§4.2) — identity for
porous rock (with v already retarded by Rd), and the Goltz–Roberts
time-dependent mapping for fractured rock.

Two non-obvious consequences you will see in the dashboard, **both physically
correct**:

- *At fixed evaluation time, more operation years ⇒ SHORTER migration* (when
  bleed > 0): more years spent in the contained phase, fewer in free drift.
- *At fixed evaluation time, a longer restoration sweep ⇒ the plume sits closer
  in*: more held years. In reality restoration pumping actually **reverses**
  the local gradient and pulls water back (groundwater sweep works by letting
  outside water flow in); holding the front at zero velocity is the
  conservative approximation of that pull-back.

> **Code:** `front_position()` in transport.py; regression-locked by
> `test_front_three_phases`.

### 4.8 The source zone: throughput widening, the E1 disc, and post-closure flush

**Throughput widening.** Years of injection push lixiviant beyond the well
pattern. The contacted width grows with cumulative *bulk volumes*
`BV = V_injected / V_pattern`:

```
W_eff = W · (1 + gain · tanh(BV / BV_ref))     (bounded at (1+gain)·W)
```

tanh gives fast early growth that saturates — you can't widen forever.

**The E1 disc.** The wellfield footprint itself (radius `W_eff/2`, centered
up-gradient of the source plane) is contaminated *by construction* — the rock
the lixiviant deliberately swept. It is drawn as a uniform-concentration disc
and unioned into the **area** metric only; migration and compliance metrics
track the *migrating front*, never the source footprint (else a wide wellfield
reads as an "excursion").

**Radial vs directional.** The diagnostic `λ = X_c / (W_eff/2)` says which
regime you are in: λ < 1 means the source disc dominates the picture
("migration" is really *extent*), λ > 1 means a true directional plume.

**Post-closure flush.** After operations stop, the disc does not stay at C0
forever — regional flow flushes it and residual uranium slowly re-dissolves:

```
disc_conc(t) = disc_conc · 0.5^((t − t_op)/H),   H = 30 yr
```

The 30-yr half-life is anchored to the US EPA's proposed ≥30-yr
post-restoration monitoring horizon (the regulator's own estimate of how long
source zones stay elevated; uranium persists in aquifer solids and can even
rebound). Set `DISC_FLUSH_HALFLIFE_YEARS = 0` to disable.

### 4.9 Restoration — the drawdown law and the deficit wave

Restoration physically works by exchanging pore volumes: each flush replaces a
fraction of the contaminated water. Equal fractional removal per pore volume ⇒
exponential decay of source concentration with sweep duration:

```
C_src/C0 = exp(−λ·t_sweep),  λ anchored so a 5.0-yr sweep reproduces the
                             empirical Texas endpoint residual
```

Equivalently `C_src/C0 = endpoint^(t_sweep/5yr)`, floored at 0.02 (rebound /
irreducible residual — real sites pumped >15–20 pore volumes without reaching
background). The 5.0-yr anchor is the *median actual restoration duration*
across the 13 Texas production areas in `Restoration.csv` (IQR 3.8–6.5 yr,
median 18.6 pore volumes) — real data, not a guess.

**Causality (the QA F-1 fix, 2026-07-13):** the sweep is credited only for the
**elapsed** time, `elapsed = clip(t − t_op, 0, t_rest)`:

```
C_src(t) = C0 · realized_residual(endpoint, elapsed)
```

A planned-but-future sweep cleans nothing; a sweep still running at evaluation
time is credited for the years it has actually run; once complete, the credit
is constant. This is why the dashboard **freezes** when you push
`restoration_years` past `t − t_op`: every still-running sweep with the same
elapsed time looks identical *at that evaluation time* — the planned future
cannot affect the present. That freeze is correct physics, not a bug (the bug —
a 3.3× area snap at the boundary — was found by the QA sweep and fixed).

**The deficit wave.** The *escaped* plume downstream keeps its dirty history —
cleaning the source doesn't teleport clean water forward. The model subtracts a
"clean-water replacement wave" from the base plume:

```
C = C0·F_long(x; X_c) · F_tran  −  (C0 − C_src)·F_long(x; X_clean) · F_tran
```

The wave's front `X_clean` sits at the source plane while pumping holds the
water (mid-sweep: it wipes the source zone only) and advances at drift velocity
after closure — so on the map you see the **dark band detach and migrate
down-gradient, shrinking as clean water overtakes it**. That is the real
signature of a restored ISR site.

### 4.10 Fracture-strike anisotropy from real lineament data (E1)

Fractures channel flow. The GSI lineament map of Jharkhand gives thousands of
mapped fracture traces; from these the pipeline builds a gridded
**strike field** using *axial* statistics (a fracture striking 10° is the same
as one striking 190°, so angles are doubled before averaging — the standard
trick for undirected data):

```
R̄ = |mean(e^{2iθ})|,   V = 1 − R̄   (circular variance, 0 = perfectly aligned)
```

- Aligned fractures (low V) ⇒ strongly channeled flow ⇒ very narrow plume:
  `α_T/α_L = clip(0.02·exp((V−0.63)/0.20), 0.01, 0.10)` — anchored so the
  state-median V ≈ 0.63 reproduces the literature default 0.02.
- The plume's *display* azimuth is also rotated toward the fracture strike (a
  transmissivity-tensor effect: the Darcy flux vector rotates toward the
  high-K direction), blended by alignment strength.

### 4.11 Vertical screening — will it hit the village wells?

The horizontal model is 2-D (one aquifer layer). A separate **screening**
module asks: can contamination at ore depth (Layer 3) reach the shallow
weathered aquifer (Layer 1, 0–20 m, where hand-pump wells draw)? Three
pathways are combined into a probability:

1. **Advective leakage** through the confining rock: vertical Darcy velocity
   `v_z = K_v·i_up/φ` with `K_v = (K_v/K_h ratio)·K_h` (fractured rock:
   ~0.05–0.1; intact: ~0.01), giving
   `t_breakthrough = separation / v_z` — compared against the evaluation time.
2. **Vertical dispersion** from the plume (α_V ≪ α_L).
3. **Wellbore failure** (a leaky abandoned borehole short-circuits the layers)
   — a fixed probability from the literature.

The separation uses **per-district NAQUIM/CGWB data** (real fracture-zone
depths, e.g. East Singhbhum's productive fractures at 20–258 m) and the real
post-monsoon water table from CGWB stations.

### 4.12 First-order natural attenuation — the equilibrium plume (real-ISR upgrade)

Down-gradient of the wellfield, dissolved U(VI) meets rock that is still
*reducing* (pyrite, organic carbon) and precipitates as immobile U(IV) — the
same redox trap that formed the ore deposit in the first place. A Wyoming ISR
cross-hole field test measured ~50% of injected U(VI) immobilized in ~1 year
where that capacity was intact. The screening representation (standard in
BIOSCREEN-class models) is a first-order sink along the travel path:

```
C(x) → C(x) · exp(−k · τ),   τ = x / v_c   (plug-flow travel time)
```

Consequence: the plume gains a **finite steady-state extent**. Behind the
front, `C(x) = C0·e^(−k x/v_c)`, so the BIS contour freezes at

```
x* = (v_c / k) · ln(C0 / threshold)
```

— growth, then equilibrium: exactly the real-world behavior (scenario 2).

Honesty rules baked into the implementation:
- **Uranium only** (k = 0 for sulfate/TDS — conservative tracers; their
  real-world brake is river discharge, handled by the far-field note).
- **k is uncertain and sampled**: log-triangular over [0.05, 0.20, 0.70]/yr
  per scenario + a ×0.5–2 per-draw multiplier, so reducing-capacity ignorance
  flows into the P10–P90 bands. The 0.70 ceiling is the intact-rock field
  value; the mode sits well below it because (a) capacity near a real
  wellfield is partially consumed and (b) first-order decay pretends the sink
  is infinite (it is not — the same field test nearly exhausted its pathway).
- **Never applied to the source disc** (its reductants were deliberately
  oxidized by the lixiviant) and **shared by the deficit wave** (else the wave
  could subtract more than exists at distance x).
- Expert override: `u_attenuation_k_per_yr` in the API; values above the
  trained 0.70 are served analytically and flagged as extrapolation.

Paired with it, the **natural post-closure source flush**: the 30-yr-half-life
flush (§4.8) now feeds the *whole* source term, not just the disc display —
`C_src(t) = C0 × restoration credit × flush(t−op)` drives the same deficit
wave restoration uses. Restoration is thereby the *accelerated* version of the
natural process (5-yr-anchored sweep vs 30-yr passive flush), which is exactly
how the real industry describes it. Net effect at a fixed pin (op = 8 yr,
no restoration): area 22 → 39 ha by year 30, **stabilizes, then recedes** to
~38 ha by year 50 while the peak flushes 13,270 → 5,030 ppb — versus the old
unbounded 85 ha at a frozen peak.

### 4.13 Monte-Carlo uncertainty — where the bands come from

We do not know K, Kd, gradient, or dispersivity exactly. For every scenario the
engine runs 48 draws: log-normal K heterogeneity, triangular Kd within the
literature range, gradient multipliers (widened by the real seasonal swing at
the pin), dispersivity multipliers, bleed drift. Each draw produces a full
plume; the **P10/P50/P90** of area/migration/compliance across draws are the
distributional labels, and the **excursion probability** is the fraction of
draws whose mining-attributable concentration at the compliance ring exceeds
the incremental threshold:

```
p_ex = (1/N) · Σ 1[ C_draw(ring) ≥ max(BIS_threshold − background, floor) ]
```

"Incremental" matters: in districts where the natural background already
flirts with the standard, only the *mining-attributable increment* counts.

---

## 5. The datasets

Everything in `Datasets/` (repo root). **Real** = measured/published data;
**derived** = computed by this pipeline from real inputs.

| Dataset | What it is | What it feeds |
|---|---|---|
| `Aquifers_Jharkhand.geojson` | CGWB aquifer polygons: lithology, K, porosity, thickness, transmissivity | Pin → hydrogeology (`jharkhand_loader.py`) |
| `waterQuality_jharkhand.csv` | CGWB water-quality wells: U, SO₄, TDS, HCO₃ baselines | Background concentrations at the pin |
| `cgwb_waterlevel_jharkhand.csv` | CGWB monitoring stations: seasonal water levels | D1 flow field (gradient, azimuth, seasonal amplitude, water table) |
| `jharkhand_glo30_dem.tif` | Copernicus GLO-30 digital elevation model | Flow-field fallback where stations are sparse (water table ≈ subdued topography) |
| `jharkhand_lineaments.geojson` | GSI mapped fracture lineaments | D2 strike field → plume anisotropy + azimuth rotation |
| `jharkhand_rivers.geojson` + `HydroRIVERS_v10_as_shp/` | River network; HydroRIVERS adds discharge (m³/s) | Perennial-river receptor: distance-to-river, plume-crossing alert |
| `Jharkhand Ore/jharkhand_uranium_deposits.csv` | The 7 UCIL deposits + Singhbhum belt envelope (WKT polygons) | Ore mask: uranium source term exists only here; per-deposit ore depths |
| `udepo_uranium_deposits.xlsx` | IAEA UDEPO world uranium-deposit database | D4: real ore grades scale the uranium source concentration per deposit |
| `naquim_reference/naquim_vertical.csv` | Per-district NAQUIM/CGWB vertical profiles (fracture-zone depths, weathered-zone base) | D3: vertical stratification per district |
| `District_Boundary_JH.geojson` | State/district boundaries | Hard Jharkhand boundary (422 outside), district lookup |
| `Real_dataset/Dataset 2/*.csv` | **Texas ISR operating records** (TexasISROperations, Restoration, AquiferExemptions, DisposalVolumes, MinePermits) | Source-term signature (C0 ranges), restoration endpoint residuals + the 5.0-yr sweep anchor |
| `Real_dataset/east_singhbhum.tif` | SRTM DEM tile (E. Singhbhum) | (spare; superseded by GLO-30) |

Derived artifacts in `ml_pipeline/data_prep/artifacts/`: `flow_field.npz`
(gridded gradient/azimuth/water-table from stations + DEM), `strike_field.npz`
(gridded fracture strike + circular variance), `river_field.npz` (distance to
perennial river + reach discharge).

---

## 6. The ML layer

### 6.1 Why a surrogate at all?

The physics engine takes ~0.1–1 s per scenario *with* the 48-draw Monte Carlo.
Fine for one pin — but the surrogate's real jobs are: (1) **instant calibrated
bands** without re-running MC, (2) a **health signal** (if the ML disagrees
with the physics on inputs it was trained on, something changed), and (3) the
groundwork for learning from *field* data later, which no closed-form physics
can absorb.

### 6.2 The features (39)

Groups (full list in `ml/dataset.py::MODEL_FEATURES`):

- **Intrinsic hydrogeology**: regime flag, K, gradient, porosities, Darcy flux,
  seepage velocity.
- **Chemistry**: Kd, retardation Rd, contaminant velocity.
- **Dispersion**: α_L, α_T, anisotropy ratio, D_L, D_T.
- **Dimensionless groups**: Péclet, pore volumes, dimensionless time τ, β.
- **Operations**: Q_in, bleed, Q_net, containment η, operation days, width.
- **Source**: C0, background Cb.
- **Irregularities & restoration**: downtime, seasonal amplitude,
  restoration years, *realized* residual fraction (elapsed-credited — QA F-2).
- **Kinematics**: front positions X_c and X_clean, time, post-closure flag.
- **Species one-hot** (uranium / sulfate / TDS).

Note the deliberate redundancy (v is derivable from K·i/φ): trees can't do
division, so we hand them the physically meaningful ratios pre-computed.

### 6.3 Quantile regression with monotone constraints

Each target (area, migration, compliance concentration) gets three XGBoost
models — P10, P50, P90 — trained with **pinball loss**: for quantile q and
error `u = y − ŷ`,

```
L_q(u) = q·u        if u ≥ 0     (under-prediction penalized by q)
       = (q−1)·u    if u < 0     (over-prediction penalized by 1−q)
```

Minimizing this loss makes the model's output converge to the q-th conditional
quantile (asymmetric penalties balance exactly at the quantile).

**Monotone constraints** are physics injected into the trees: XGBoost can
force "output never decreases when feature X increases." We constrain, e.g.,
`K: +1` (more conductive ⇒ bigger footprint), `bleed: −1`, `Kd: −1`,
`restoration_years: −1`. Every sign is *verified against the physics labels*
in `tests/test_physics_laws.py` — never assumed. Signs that are only
conditionally true (e.g. operation years, whose direction flips with bleed) are
left unconstrained.

### 6.4 Conformal calibration (the honesty machine)

Raw quantile models under-cover (P10–P90 catches less than 80% of the truth).
**Split-conformal CQR** (Romano et al. 2019) fixes this with a guarantee:

1. Split scenarios into train / calibration (grouped — see 6.5).
2. On calibration data compute *conformity scores*
   `s_i = max(q̂10(x_i) − y_i, y_i − q̂90(x_i))` — how far outside the band the
   truth fell (negative if inside).
3. Take the ⌈(n+1)(1−α)⌉-th smallest score `Q̂` and widen both edges by it:
   `[q̂10 − Q̂, q̂90 + Q̂]`.

The guarantee (exchangeability): the widened band covers ≥ 1−α = 80% of new
points from the same distribution — *regardless of how wrong the model is*.

**Mondrian** = do this separately per (regime × species) bucket so fractured
uranium gets its own correction rather than borrowing sulfate's.
**Scenario-level coverage** is the real gate: rows from one scenario are
correlated, so we require ≥80% of *scenarios* to have all their rows covered;
a finite-sample margin (`DELTA_INFLATE = 1.15`) widens the calibration quantile
to hold this stricter bar.

### 6.5 Leak-proof validation

- **GroupKFold by scenario**: all 15 rows of a scenario (5 times × 3 species)
  stay in the same fold — otherwise the model "predicts" a scenario it partly
  saw, inflating R².
- **Leave-aquifer-out**: hold out entire aquifer polygons to prove spatial
  generalization (reported next to scenario-CV in `metrics.json`).

Current metrics (2026-07-16, post real-ISR attenuation upgrade): area R² 0.875,
migration 0.788, compliance 0.763, excursion 0.944; scenario coverage
0.832/0.806/0.860 — all above the 0.80 gate. R² is *deliberately* lower than
the pre-attenuation model (0.931/0.835/0.783): the sampled attenuation rate k
injects genuine physical uncertainty the features cannot fully explain, so the
bands widened and the point predictions got harder — richer physics traded for
raw fit, with the coverage guarantee intact. Time-monotone constraints were
removed for the footprint targets (the plume now legitimately grows →
stabilizes → recedes), and `DELTA_INFLATE` rose 1.15 → 1.35 to hold the
scenario-coverage gate under the wider true bands.

### 6.6 The drift monitor

Every live request records the relative gap between analytical and ML answers.
`GET /api/drift` summarizes; `drifting: true` when the median gap exceeds a
threshold over a window — the signal that the surrogate is being queried where
it no longer tracks the physics (retrain or restrict inputs).

---

## 7. The codebase, file by file

```
ml_pipeline/
├── config/
│   └── parameters.py        The single source of truth for EVERY constant:
│                            Jharkhand bounds, BIS thresholds, Kd ranges,
│                            dispersivity law, operational envelope, E1 flag,
│                            restoration anchors, disc-flush half-life, slider
│                            ceilings, vertical-screening params. Every value
│                            carries a literature citation or an explicit
│                            "assumption" tag. Start reading here.
│
├── physics/
│   └── transport.py         The physics engine (~41 KB). Darcy/velocity math,
│                            retarded clock, front_position (3 phases),
│                            realized_residual + restoration_source_fraction
│                            (elapsed-credit drawdown), matrix_sigma +
│                            tang_attenuation (fractured), _long/_tran factors,
│                            concentration_field (Domenico + deficit wave +
│                            E1 disc), disc_flush_factor, _auto_grid,
│                            plume_metrics, solve_plume/simulate_plume,
│                            _stack_field + mc_field_metrics (vectorized MC),
│                            shallow_impact_screening (vertical 2.5-D).
│
├── data_prep/
│   ├── feature_engineering.py  build_feature_row(): raw operating point → the
│   │                        39-feature row + private physics carry-throughs.
│   │                        Owns retardation_factor, containment_efficiency,
│   │                        dispersivities, pore_volumes, effective_source_width.
│   │                        USED BY BOTH generator and server (train == serve).
│   ├── jharkhand_loader.py  Loads aquifer polygons + water-quality wells;
│   │                        aquifer_at_point / baseline_at_point (pin lookup).
│   ├── flow_field.py        D1: builds the gridded groundwater-flow field from
│   │                        CGWB stations (plane fit) with DEM fallback;
│   │                        flow_at(lon,lat) → azimuth, gradient, seasonal
│   │                        amplitude, depth-to-water, near_divide flag.
│   ├── strike_field.py      D2/E1: fracture-strike grid from GSI lineaments
│   │                        (axial doubled-angle stats); strike_at(),
│   │                        anisotropy_from_variance(V), flux_azimuth()
│   │                        (tensor rotation of the display azimuth).
│   ├── rivers.py            B2: HydroRIVERS clipped to Jharkhand; per-pin
│   │                        distance to perennial river; plume_river_discharge()
│   │                        (does the BIS plume polygon cross a river?).
│   ├── drainage.py          Statewide drainage-density statistics (fallback
│   │                        far-field context when the river field is absent).
│   ├── ore_loader.py        Module 2: uranium deposit/belt/none mask from the
│   │                        UCIL deposit polygons; per-deposit ore depths.
│   ├── ore_grades.py        D4: IAEA UDEPO ore grades → per-deposit C0 factor.
│   ├── naquim_vertical.py   D3: per-district vertical profile (fracture-zone
│   │                        depth range, weathered-zone base, confidence).
│   ├── boundary.py          Dissolved Jharkhand polygon; in_jharkhand() test.
│   └── texas_loader.py      Loads the Texas ISR records: source signature
│                            (C0 ranges per species) + restoration endpoint
│                            residuals (the empirical anchor).
│
├── synthetic/
│   └── generate.py          The data factory. _scenario(): samples a random
│                            operating point at a random Jharkhand pin (60%
│                            field-informed: gradient/V/seasonal drawn from the
│                            real fields). _draw_params(): per-MC-draw
│                            TransportParams (K heterogeneity, Kd triangles...).
│                            mc_band_labels(): P10/50/90 labels. Writes
│                            outputs/synthetic_training.csv (13,500 rows).
│
├── ml/
│   ├── dataset.py           MODEL_FEATURES (39), monotone sign maps
│   │                        (physics-verified), CSV loading/validation.
│   ├── train.py             XGBoost quantile heads + Mondrian split-CQR +
│   │                        GroupKFold + leave-aquifer-out + coverage gates +
│   │                        on-manifold sanity sweeps → artifacts/*.joblib,
│   │                        metrics.json, model_card.json (training envelope).
│   ├── predict.py           The unified serving API. features_from_inputs()
│   │                        (same builder as training), predict("ml") loads
│   │                        artifacts + applies conformal deltas,
│   │                        predict_analytical() runs the physics + MC +
│   │                        restoration diagnostic. Three-tier surrogate cache.
│   └── shap_analysis.py     SHAP feature importances for the trained heads.
│
├── dashboard/
│   ├── server.py            FastAPI app. /api/predict (both engines + all the
│   │                        context blocks), /api/pin, /api/boundary, /api/ore,
│   │                        /api/rivers, /api/flow_field, /api/strike_field,
│   │                        /api/aquifers, /api/drift, /api/health. Request
│   │                        bounds, extrapolation flags, drift recording.
│   ├── resolve.py           UI payload → engine inputs: pin hydrogeology,
│   │                        Kd defaults, ore-zone C0 clamp, shear-zone K
│   │                        override, flow/strike defaults, envelope_violations
│   │                        (reads the DEPLOYED model card, not the config).
│   ├── plume_geometry.py    Solver-frame field → lon/lat map polygons
│   │                        (marching squares, rotation, offset), compliance
│   │                        ring, ML envelope ellipses.
│   ├── drift.py             The rolling analytical-vs-ML disagreement monitor.
│   └── frontend/            Vanilla JS + Leaflet. index.html (sliders),
│                            app.js (map layers, plume rendering, depth
│                            schematic, auto-pilot azimuth/gradient), styles.css.
│
├── tests/                   See §9.
├── E1_geometry_design.md    Design contract for the radial/anisotropic geometry.
├── QA_SWEEP_REPORT.md       The 2026-07-13 pre-retrain QA findings (F-1..F-5).
├── FABLE5_QA_SWEEP_PROMPT.md The executable QA brief that produced the report.
└── README.md                Quick-start + phase history.
```

---

## 8. The life of a request

What happens when you drop a pin at Jaduguda and press *Run*:

1. **Frontend** (`app.js`) POSTs the slider payload to `/api/predict`.
2. **Boundary gate**: outside Jharkhand → 422 (predictions elsewhere would be
   fabricated — the datasets end at the border).
3. **`resolve_inputs`**: pin → aquifer polygon (K, φ, thickness, regime) →
   nearest water-quality well (backgrounds) → ore-zone mask (uranium C0 exists
   only on deposits/belt; grade-scaled by UDEPO; suppressed elsewhere) →
   Singhbhum shear-zone K override (fractured deposit pins are far more
   transmissive than the generic schist polygon) → flow field (default azimuth
   + gradient) → strike field (anisotropy) → Kd defaults from the same ranges
   training sampled.
4. **`envelope_violations`**: every input checked against the *deployed model
   card's* training envelope — anything outside is listed in `extrapolation`
   (the ML bands are unvalidated there; the analytical engine still serves).
5. **Analytical engine**: `features_from_inputs` → `simulate_plume` (Domenico +
   Tang + disc + restoration wave on a 200² grid) → metrics + contours; plus
   the 48-draw MC for excursion probability.
6. **ML surrogate** (skipped when uranium is suppressed): same feature row →
   9 quantile heads + conformal deltas → banded metrics + off-scale flag.
7. **Context blocks**: vertical screening (per-district NAQUIM), river
   crossing (`plume_river_discharge` on the BIS contour), far-field note,
   restoration diagnostic (elapsed-credited), λ radial flag, drift record.
8. **Frontend renders**: contour polygons + compliance ring + ML envelope on
   the map; metric cards; depth schematic with the district fracture band.

---

## 9. The test suite

| File | Guards |
|---|---|
| `test_physics_laws.py` | The monotone sign table against the *labels* (raw operating-point sweeps): K↑⇒bigger, bleed↑⇒smaller, Q_in law at fixed Q_net, front phases, retarded clock, Tang, restoration reduces impact. |
| `test_restoration_continuity.py` | The QA F-1/F-2 fixes: elapsed-credit law, no step at rest = t−op, monotone non-increase, rest→0⁺ continuity, mid-sweep credit, causality (planned future irrelevant), realized-fraction feature. |
| `test_polish.py` | Plume×river crossing (incl. invalid-ring healing), per-deposit ore depths, disc-flush half-life law. |
| `test_shear_transmissivity.py` | D5 shear-zone K override on/off. |
| `test_strike_field.py` | Axial statistics, anisotropy-from-V anchoring. |
| `test_flow_field.py` | D1 gradients/azimuths sane, divide handling. |
| `test_ore_mask.py` / `test_ore_grades.py` | Deposit/belt/none C0 ordering, grade clipping. |
| `test_naquim_vertical.py` / `test_vertical.py` | Per-district profiles, screening ordering. |
| `test_rivers.py` / `test_boundary.py` | River field, state boundary. |

107 tests; all green as of the final retrain.

---

## 10. Honest limitations

This section exists because the project's rule is *critique your own tool*.

### What is genuinely data-grounded

- Aquifer properties, water quality, water levels, fracture strikes, river
  network, deposit locations/grades/depths, district vertical profiles — all
  from real published Indian sources (CGWB, GSI, NAQUIM, UCIL, IAEA).
- Source-term concentration ranges and restoration endpoints/durations — real
  Texas ISR operating records.
- The physics formulas — standard published screening hydrogeology (Domenico,
  Ogata–Banks, Tang, Xu & Eckstein, Gelhar, Goltz & Roberts).

### What is screening-grade simplification

| Simplification | Consequence | Honest label |
|---|---|---|
| **First-order (infinite-sink) attenuation** for uranium redox trapping (§4.12) — real reducing capacity is finite and spatially variable | Very-long-horizon attenuation may be overstated where capacity is exhausted; understated where fresh. | Mitigated by sampling k over [0.05, 0.70]/yr into the bands and keeping the mode well below the intact-rock field value. Sulfate/TDS carry no decay at all (fully conservative). |
| **Plug-flow travel-time decay** (τ = x/v_c) rather than the full decay-modified Domenico front | Slightly simplified front shape near the toe. | Standard screening approximation; error is second-order vs the k uncertainty itself. |
| **Front held (v=0) during restoration** instead of reversed | Real groundwater sweep pulls near-field water *back* into the wellfield. | Conservative (model cleans slower than reality). |
| **2-D single layer** + separate vertical screening | No true 3-D plume. | Standard for screening tools (BIOSCREEN class). |
| **Homogeneous aquifer per polygon** (MC draws add heterogeneity statistically, not spatially) | No channeling along specific fractures/paleochannels. | Inherent to closed-form solutions. |
| **Domenico upstream half-plane at C0** (the dropped Ogata–Banks term) | The source-zone box is painted at C0; handled deliberately by the disc + deficit-wave design, but it is an artifact zone. | Documented; the QA F-1 fix made its behavior continuous. |
| **operation_years default 8** | A single wellfield runs 1–3 yr; 8+ yr represents a sequential multi-wellfield mine unit compressed onto one footprint. | Interpret long operations as mine-unit scale. |
| **Texas→Jharkhand transfer** | Source chemistry and restoration behavior from porous Texas sandstone applied to fractured Indian shear-zone rock. | The headline caveat on the UI. No field calibration exists or is possible without an actual ISR test. |

### Known ML seams (accepted, documented)

- Tree quantization steps (~17% migration at rest 0→0.5 yr; ~0.6 ha at the
  restoration boundary) — the analytical values stay inside the calibrated 80%
  bands at every checked seam (6/6).
- In-support soft spots: slight m_migr dip at very low gradients.
- Inputs beyond the trained envelope (rest > 10 yr, time > 20 yr) are served
  by the analytical engine and *flagged* (`extrapolation`) rather than trusted.

---

## 11. Glossary

| Term | Meaning |
|---|---|
| **Aquifer** | Rock/sediment layer that stores and transmits groundwater. |
| **Advection** | Transport by riding the bulk water flow. |
| **BIS threshold** | Bureau of Indian Standards drinking-water limit (U: 30 ppb; SO₄: 400 mg/L; TDS: 2000 mg/L as configured). |
| **Bleed** | Deliberate net over-extraction that hydraulically contains an ISR wellfield. |
| **CQR** | Conformalized Quantile Regression — the band-calibration method. |
| **Darcy flux (q)** | Water volume crossing unit area per time; q = K·i. |
| **Dispersivity (α)** | Length scale of mechanical mixing; grows with plume scale. |
| **Dual porosity (β)** | Immobile/mobile water capacity ratio in fractured rock. |
| **Excursion** | Lixiviant escaping past the monitoring-well ring. |
| **Hydraulic conductivity (K)** | Rock permeability to water [m/day]. |
| **Hydraulic gradient (i)** | Water-table slope; drives flow. |
| **Kd** | Distribution coefficient — sorption strength [L/kg]. |
| **Lixiviant** | The leaching solution (here: alkaline, carbonate + oxidant). |
| **Lineament** | Mapped surface trace of a fracture/fault. |
| **NAQUIM** | India's National Aquifer Mapping programme (CGWB). |
| **Péclet number** | Advection-to-dispersion dominance ratio, L/α_L. |
| **Pore volume (PV)** | One full exchange of the water in a rock volume. |
| **Retardation (Rd)** | How much slower the contaminant is than the water. |
| **Seepage velocity (v)** | Actual water speed through pores; q/φ. |
| **Transmissivity (T)** | K × aquifer thickness [m²/day]. |
| **UCIL** | Uranium Corporation of India Ltd (operates the Singhbhum mines). |
| **UDEPO** | IAEA World Uranium Deposits database. |
