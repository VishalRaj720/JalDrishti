# E1 — Radial/anisotropic plume geometry (design contract)

**Status:** Stage D (design, hand-checked at real pins). Implemented by Stage E
(physics), Stage F/G (generator v3 + the ONE retrain, M1), Stage H (atomic cutover).
**No new ML features. No new source model.** All four pieces reuse quantities the
engine already computes. Direction/aspect stay strictly separated:
flow (D1) = travel direction; fracture strike (D2) = elongation + a display-only
flux rotation.

Notation: solver frame has x = flow (down-gradient) axis, source plane at x=0 =
down-gradient wellfield edge, W = full transverse wellfield width, W_eff = the
throughput-widened source width (existing `effective_source_width`), Xc = retarded
front distance, V = D2 circular variance (orientation dispersion), C0 = source
conc, C_res = residual_fraction·C0.

---

## 1. Leach-zone disc member (adds source-footprint area)

The Domenico product only paints the plume down-gradient of the source plane, so a
CONTAINED / low-drift scenario reports ~0 affected area even though the leached
well-field footprint is contaminated by construction. Add the source footprint as
a disc and take the conservative union:

    C(x,y) = max( C_disc(x,y), C_Domenico(x,y) )

    C_disc(x,y) = C_src · 1[ (x - x_c)^2 + y^2 <= R_disc^2 ]
        x_c    = -W/2            # well-field CENTRE in solver frame (map pin)
        R_disc = W_eff/2         # throughput-widened footprint radius
        C_src  = C_res  if (restoration_days>0 and t > t_op+t_rest) else C0

* No advection of the disc: the leached ROCK is fixed; the dissolved front (its
  down-gradient migration) is already carried by the Domenico term. The source-zone
  strength now decays post-closure (polish #4): `disc_flush_factor()` applies an
  exponential decay with a 30 yr half-life (anchored to EPA's 30 yr post-restoration
  monitoring horizon; see `parameters.DISC_FLUSH_HALFLIFE_YEARS`). During operations
  the disc is held at full strength.
* Threshold gate is automatic: area counts cells with C >= thr_inc, so a clamped
  non-ore uranium disc (C0 = trace < thr) contributes nothing — correct.
* `max()` never double-counts; near x=0 both members are ~C0 (no seam). XGBoost is
  piecewise-constant so the ridge is harmless (the Tang `max` already puts one in
  the labels).
* Area added ≈ π(W_eff/2)^2 (W=300 → ~7 ha; W=800, widened → ~50 ha). This is the
  single largest label shift in the retrain — PILOT before the full bake.

## 2. Λ radial↔directional — DIAGNOSTIC ONLY (not a feature, not a switch)

    Λ = Xc / (W_eff/2)      # front reach vs source half-width
    Λ < 1  -> disc dominates -> "radial-dominated" (blob at the well-field)
    Λ >= 1 -> Domenico cigar dominates -> "drift-dominated"

The `max()` composition performs the blend automatically — there is NO explicit Λ
switch in the field. Λ is reported (UI/response) for interpretation only. Both Xc_m
and wellfield_width_m are already MODEL_FEATURES, so the surrogate recovers the
regime without a new input.

## 3. Anisotropy from V (re-anchored) — FRACTURED ONLY

Replaces the flat regime constant `TRANSVERSE_ANISOTROPY` (fractured 0.02) with a
per-cell value anchored so the FIELD MEDIAN reproduces the current value:

    aT/aL (fractured) = clip( 0.02 · exp( (V - 0.63) / 0.20 ),  0.01, 0.10 )
    aT/aL (porous)    = 0.10          # saprolite is NOT fabric-controlled — flat

Hand-checked spread over the field's own V range: V=0.36→0.010, 0.50→0.010(clip),
0.63→0.020 (== current), 0.78→0.042. So D2 is a PERTURBATION around the regime
value (strong channeling when aligned, modest rounding when dispersed, always ≤
porous), grounded where the data lives (V∈[0.36,0.78]) — NOT the theoretical-0/1
mapping that fattened every fractured plume 10-20×.

`alpha_T` / `anisotropy_ratio` are ALREADY features → no new feature. The generator
(M1) must sample V and derive aT from it so training spans the continuous aT range
(see §5).

## 4. Tensor-rotated DISPLAY azimuth (display only; labels unchanged)

In anisotropic fractured rock the Darcy flux is not parallel to -∇h; it rotates
toward the high-K fracture-strike direction. Rotate the DISPLAYED plume azimuth
(arrow + contours) from the D1 flow bearing θ_f toward the D2 strike θ_s. Vector
form (singularity-free, undirected-strike-safe):

    ê_s = (sinθ_s, cosθ_s),  ê_p = (cosθ_s, -sinθ_s)     # strike / cross-strike (E,N)
    f   = (sinθ_f, cosθ_f)
    f'  = (f·ê_s)·ê_s + (f·ê_p)/λ · ê_p                  # shrink cross-strike comp
    θ_flux = atan2(f'_E, f'_N)

    λ (fractured) = clip( 1 + 5·(1 - V), 1, 6 )          # perm anisotropy K∥/K⊥
    λ (porous)    = 1                                     # no rotation

Hand-checked: flow∥strike → ~0° (Ranchi −2.5°); oblique+aligned → up to ~20-30°
toward strike (Jaduguda −20°); near-perpendicular → small (correct: max rotation is
at ~45° obliquity). This is the ONLY way D2 affects DIRECTION (small); its main
effect is elongation via §3. λ is a PERMEABILITY ratio (2-6), independent of the
dispersivity ratio in §3. Reach magnitude is orientation-invariant → migration/area
labels unaffected; the solve stays flow-aligned and is merely rendered along θ_flux.

---

## 5. What M1 (generator v3 + retrain) changes — and ONLY this

* Field computation (`concentration_field` + `_stack_field`) gains the §1 disc.
* Generator samples V per scenario and sets aT = aL·aniso_from_V(V) for fractured
  (replaces the 2-value constant). MIXTURE sampling for coverage + realism:
  ~60% V = strike_at(jittered pin) (real fabric), ~40% V ~ U(0.35, 0.80).
* Grid (`_auto_grid`) fixes (do BEFORE regen):
  - x must extend up-gradient to cover the disc: x_min <= -(W/2 + W_eff/2).
  - y-span sized to the PLUME, not ±0.6·reach: y_half = W_eff/2 + 4·√(aT·reach) +
    margin (narrow plumes were starved to ~3-5 transverse cells → band noise).
* NO new columns: MODEL_FEATURES, the 6 Mondrian cells, and the monotone maps are
  unchanged. θ_flux and Λ are serve-time only.

## 6. Validation gates (Stage F pilot, then Stage G full bake)

1. PILOT 100 scenarios first; diff every label distribution vs v2.
2. Re-run `test_physics_laws.py` on v3 labels — especially the disc × restoration ×
   time_years monotonicity (disc drops to C_res at t_op+t_rest; check area stays
   monotone or free the edge).
3. breach base rate stays 30-60%; band-order violations = 0; censor rate ~ v2.
4. Report disc-area fraction per regime.
5. FIELD-RESAMPLED coverage batch: ~100 scenarios pinned to real grid cells with
   real V/gradient/amp; scenario coverage must hold ≥0.80 THERE (the generator's
   own gradient sampling is 2-3× steeper than the field median — passing on the
   generator distribution is not enough).
6. Deploy E1 physics + v3 artifacts ATOMICALLY (Stage H); reset the drift monitor.

## Deferred (noted, not in E1)
Precise plume-polygon × river-polyline intersection alert; per-deposit ore-depth
slider defaults; drawing the district fracture band on the depth schematic.
