# Fable 5 — Pre-Retrain QA & Bug-Hunt Sweep for the JalDrishti ISR Plume Surrogate

> **Paste everything below the line into Fable 5.** It is self-contained: it tells the
> model what the system is, how to drive both engines, the exact physical invariants that
> define "correct," the boundaries where discontinuity bugs hide, and the report format.
> The goal is to catch **every** bug *before* a final retrain, so the retrain is truly final.

---

## 0. Your role and the mission

You are a **senior contaminant-hydrology QA engineer** auditing a physics-informed machine-learning
surrogate before its final production retrain. The system, **JalDrishti `ml_pipeline/`**, is a
screening tool that predicts how a uranium (and sulfate / TDS) contamination plume spreads from an
**In-Situ Recovery (ISR)** uranium mine in **Jharkhand, India**. The physics was calibrated on
**Texas** ISR data and transferred to Jharkhand geology (a domain transfer — treat every transferred
assumption as suspect).

There are **two engines** that must agree and must both be physically correct:

1. **Analytical engine** — a Domenico advection–dispersion plume model + a leach-zone source disc.
   This is the **ground truth** the ML learns from. **If it has a bug, the ML learned the bug.**
   Prioritise finding analytical/generator bugs.
2. **ML surrogate** — gradient-boosted models predicting P10/P50/P90 bands for affected area,
   migration distance, compliance concentration, plus point estimates for excursion/breach
   probability. Conformally calibrated per regime × species.

**A real bug was already found** (use it as the *template* for the class of defect to hunt):

> In a restoration scenario, dialling the **restoration-sweep** slider up made the plume look
> *cleaner* — until the sweep length crossed `evaluation_time − operation_years`, at which point the
> concentration **snapped back** to the original dirty state and then **froze** (further restoration
> did nothing). Root cause: a **binary gate** `eval_time > op + restoration` instead of a continuous
> law. It was fixed with a continuous exponential drawdown. **Hunt for every other place where a
> metric snaps, freezes, or inverts when two parameters cross a boundary.** That is the highest-value
> bug class here.

Your job: **run a systematic sweep, assert the invariants below, and report every violation.**
You are **read-only** — do **not** edit code. Produce a ranked, reproducible bug report.

---

## 1. Environment & how to run (Windows / PowerShell)

- Python interpreter: `myvenv/Scripts/python.exe` (run from the repo root
  `C:\Users\letsm\OneDrive\Desktop\JalDrishti`).
- **Start the API server** (leave it running in one shell):
  `myvenv/Scripts/python.exe -m ml_pipeline.dashboard.server`  → serves on `http://127.0.0.1:8077`.
- **Two ways to drive it — use both:**
  - **HTTP (full stack, catches wiring bugs):** `POST http://127.0.0.1:8077/api/predict` with a JSON
    body (schema in §2). `GET /api/pin?lon=..&lat=..` classifies a pin; `GET /api/drift` returns the
    rolling analytical-vs-ML disagreement monitor; `GET /api/health` confirms the ML artifacts loaded.
  - **Direct Python (isolation, faster for big sweeps):**
    ```python
    from ml_pipeline.dashboard.resolve import resolve_inputs, envelope_violations
    from ml_pipeline.ml.predict import predict, predict_analytical
    payload = {"lon":86.347,"lat":22.652,"species":"uranium_ppb","restoration_years":2.0, ...}
    inputs, hydro = resolve_inputs(payload)          # UI payload -> engine inputs + resolved hydrogeology
    a  = predict_analytical(**inputs)                # analytical bands + restoration diag (a["restoration"])
    ml = predict("ml", **inputs)                     # ML bands + excursion/breach + off_scale
    viol = envelope_violations(inputs)               # list of inputs outside the DEPLOYED model's trained range
    ```
- **Script the sweeps** — do not eyeball. Generate a grid, collect results into a table
  (pandas/CSV), and run assertions programmatically. Aggregate, then report.
- The deployed model's **trained ranges** (from `ml/artifacts/model_card.json → training_envelope`):
  `restoration_years [0,10]`, `horizon_years (evaluation time) [0,20]`, `operation_years [1,20]`,
  `injection_rate [200,8000]`, `hydraulic_gradient [0.0005,0.02]`, `wellfield_width [100,800]`,
  `bleed_fraction [0,0.10]`. **Inputs outside these should appear in `envelope_violations` / the
  response's `extrapolation` list — that is correct behaviour, NOT a bug.** (The restoration AND
  evaluation-time sliders now allow 0–50 yr for exploration; values above their trained max —
  `restoration_years>10`, `time_years>20` — must be *flagged* as extrapolation, not rejected or
  silently trusted. A missing flag there IS a bug; a present flag is correct.)

---

## 2. Request schema (POST /api/predict) and what comes back

**Request fields** (defaults in parens; `null` ⇒ auto-derive from the pin/flow-field):
`lon`, `lat` (must be inside Jharkhand or you get 422), `species` ∈
{`uranium_ppb`,`sulfate_mg_l`,`tds_mg_l`}, `regime` (null ⇒ pin's lithology; or force
`fractured`/`porous`), `injection_rate_m3_day` (2500), `bleed_percent` (2.0),
`operation_years` (8), `gradient_i` (null⇒flow field), `time_years` (10), `wellfield_width_m` (300),
`restoration_years` (0), `azimuth_deg` (null⇒down-gradient bearing), `ore_depth_m`, `ore_thickness_m`,
`mode` ("both"), and expert overrides `kd_L_kg`, `beta`, `K_m_day`, `phi_mobile`,
`downtime_fraction`, `gradient_seasonal_amp`.

**Response fields you will assert on:**
- `metrics.analytical`: `area_ha`, `migration_m`, `compliance_conc`, `excursion_probability`, `breach`.
- `metrics.ml`: `area_ha{p10,p50,p90}`, `migration_m{...}`, `compliance_conc{...}`,
  `excursion_probability`, `breach_probability`, `off_scale`.
- `plume`: `peak_conc`, `Xc_m` (front reach), `aspect_ratio`, `lambda_radial`, `radial_dominated`.
- `restoration`: `{restoration_years, residual_endpoint_fraction, residual_realized_fraction,
  source_conc_after_restoration, ref_years}` (null when no sweep).
- `vertical`: shallow-aquifer (Layer-1) impact `{impact_pct or similar, dominant_pathway,
  years_to_breakthrough, district, layer1_base_source, fractured_aquifer_range_m}`.
- `hydro`: resolved `regime, K_m_day, phi_mobile, retardation_Rd, source_conc_C0, ore_zone,
  u_suppressed, shear_zone, flow{azimuth_deg,gradient_i,near_divide}, strike`.
- `azimuth_deg`, `azimuth_source`, `far_field_note`, `river_crossing`, `nearest_river_km`,
  `extrapolation`, `disagreement`.

---

## 3. Test points — 26 vetted pins spanning Jharkhand

Use these (lon, lat). **Uranium has a real source term only at `deposit`/`belt` pins**; everywhere
else uranium is *suppressed* (trace source, `u_suppressed=true`) — so test **uranium** at the
deposit/belt pins and **sulfate + TDS** everywhere. Include **both regimes**.

| # | Pin | lon | lat | regime | ore_zone | note |
|---|-----|-----|-----|--------|----------|------|
| 1 | Jaduguda | 86.347 | 22.652 | fractured | **deposit** | primary U mine; shear-zone K applies |
| 2 | Singhbhum mid-belt | 86.25 | 22.63 | fractured | **belt** | reduced U source |
| 3 | Banduhurang | 86.13 | 22.65 | fractured | **belt** | open-pit; shallow ore |
| 4 | Bhatin | 86.32 | 22.66 | fractured | none | near-belt, U suppressed |
| 5 | Narwapahar | 86.19 | 22.70 | fractured | none | |
| 6 | Turamdih | 86.10 | 22.63 | fractured | none | |
| 7 | Mohuldih | 86.05 | 22.62 | fractured | none | |
| 8 | Bagjata | 86.55 | 22.88 | fractured | none | |
| 9 | Jamshedpur | 86.20 | 22.80 | fractured | none | near Subarnarekha — test river-crossing note |
| 10 | Chaibasa (W Singhbhum) | 85.80 | 22.55 | fractured | none | |
| 11 | Ranchi | 85.33 | 23.36 | fractured | none | U_base 0.65 |
| 12 | Bokaro | 85.99 | 23.67 | fractured | none | U_base 15.8 |
| 13 | Dhanbad | 86.43 | 23.80 | fractured | none | U_base 10.9 |
| 14 | Hazaribagh | 85.36 | 23.99 | fractured | none | |
| 15 | Ramgarh | 85.51 | 23.63 | fractured | none | known transmissivity data gap |
| 16 | Giridih | 86.30 | 24.19 | fractured | none | |
| 17 | Deoghar | 86.70 | 24.48 | fractured | none | |
| 18 | Dumka | 87.25 | 24.27 | fractured | none | |
| 19 | Daltonganj/Palamu | 84.07 | 24.03 | fractured | none | |
| 20 | Koderma | 85.59 | 24.47 | fractured | none | |
| 21 | Chatra | 84.87 | 24.21 | fractured | none | |
| 22 | Gumla | 84.54 | 23.04 | fractured | none | |
| 23 | Sahibganj | 87.64 | 25.24 | **porous** | none | K≈2.35 — porous regime |
| 24 | Garhwa | 83.81 | 24.16 | **porous** | none | K≈0.46 — low-K porous |
| 25 | Lohardaga | 84.68 | 23.43 | **porous** | none | K≈2.35 |
| 26 | (out-of-bounds control) | 80.00 | 20.00 | — | — | must return 422 OUTSIDE_JHARKHAND |

You may also drop your own pins; use `GET /api/pin` to classify first.

---

## 4. The invariant battery — what "correct" means

For each check, **sweep one parameter while holding the rest fixed** at a sensible baseline
(e.g. Jaduguda, uranium, inj=2500, bleed=2%, op=8, time=10, width=300, rest=0), unless the check
says otherwise. Run each check on **≥6 pins** covering both regimes and ore/non-ore.

### 4A. Monotonicity laws (the physics sign table)
Sweep each input across its range; the listed metric must move **monotonically** in the given
direction (allow tiny non-monotone noise from Monte-Carlo, but a *consistent* wrong-direction trend
is a bug). These hold for **affected area, migration distance, and excursion probability** (the
"footprint" metrics):

| Input ↑ | area / migration / excursion |
|---|---|
| injection_rate (at fixed bleed) | ↑ |
| bleed_percent | ↓ (containment) |
| hydraulic_gradient | ↑ |
| K_m_day | ↑ |
| operation_years | ↑ |
| time_years (no restoration) | ↑ |
| wellfield_width | ↑ |
| source_conc_C0 / ore grade | ↑ |
| Kd (sorption) | ↓ |
| phi_mobile | ↓ |
| downtime_fraction | ↑ |
| **restoration_years** | **↓ (cleaner) — smooth, no snap-back** |
| residual (dirtier restoration) | ↑ |

`compliance_conc` follows the same signs **except** time/post-closure are *unconstrained* (√t
attenuation makes them non-monotone — do not flag those). `peak_conc ≥ boundary(compliance)_conc`
always. Excursion/breach probability ∈ [0,1].

### 4B. Boundary & continuity — hunt the snap-back class
Sweep **finely** (small steps) across each boundary below and check the metric is **continuous and
correctly-directed** (no jump, freeze, or inversion):

1. **Restoration sweep** (the known bug — confirm it's fixed): op=8, time=10, sweep
   `restoration_years` 0→3 in 0.25 steps, then 0→50. Expect **smooth monotonic decrease** toward the
   residual floor; **no snap at `time−op=2`**, no freeze. Then repeat at op=5/time=15, op=12/time=18.
2. **Post-closure onset**: sweep `time_years` across `operation_years` (e.g. op=8, time 6→12). The
   plume switches from injection to drift phase — must be continuous, area/migration keep rising.
3. **Disc-flush onset & half-life**: with a sweep active, increase `time_years` well past
   `operation_years`, up to the new 50-yr cap (trained horizon is `[0,20]`, so 20–50 yr is correctly
   flagged as extrapolation — the analytical engine still serves it). To cross one 30-yr disc-flush
   half-life you need `t − operation_years ≥ 30` (e.g. op=8, time≈38+). The source disc should decay
   **smoothly**; verify no discontinuity at `t = operation_years`, and that disc strength roughly
   halves every 30 yr post-closure (the `DISC_FLUSH_HALFLIFE_YEARS` law).
4. **E1 radial↔directional transition**: vary `wellfield_width` / front reach so `lambda_radial`
   (`Xc_m / half_width`) crosses 1.0. `radial_dominated` flips; verify area/geometry stay continuous
   across the flip (no area jump).
5. **Regime switch**: same pin, `regime=null` vs forced `fractured` vs `porous`. Check the override
   substitutes regime-typical porosity/grain-density (no "chimera" Rd) and the change is physically
   ordered (porous usually slower/retarded vs fractured).
6. **Ore-zone transitions**: pins that move deposit→belt→none. Uranium `source_conc_C0` should step
   **down** deposit>belt>none and `u_suppressed` flip on at `none`. No uranium plume at `none`.
7. **Shear-zone K override**: fractured deposit/belt pin with `K_m_day=null` should apply the
   Singhbhum shear-zone K (`hydro.shear_zone` populated, larger plume); supplying an explicit
   `K_m_day` should disable it. Check the boundary (with vs without override) is sane.
8. **Azimuth near a water divide**: a pin where `flow.near_divide` is true should fall back to a
   radial/North azimuth with `azimuth_source="indeterminate_divide"` — not crash or point randomly.

### 4C. ML-vs-analytical agreement (surrogate fidelity)
- **In-support** (`extrapolation == []`): the ML `p50` should track the analytical value within the
  band; `p10 ≤ p50 ≤ p90`; analytical value should usually fall inside [p10,p90]. Flag scenarios
  where the ML p50 diverges from analytical by a large relative gap (cross-check `GET /api/drift` —
  `drifting:true` means the surrogate no longer tracks the physics).
- **Out-of-support** (restoration 10–50, or any `extrapolation` non-empty): confirm the flag fires
  and the UI would warn. Do **not** trust ML bands there; confirm the **analytical** engine is still
  sane. A *missing* flag on an out-of-range input **is** a bug.
- `off_scale` must surface when area/migration blow past the trained scale.

### 4D. Real-world ISR / Jharkhand realism (does it simulate reality?)
- **Source geography**: only Singhbhum-belt deposits carry uranium; the rest of Jharkhand must not
  fabricate a uranium plume. Sulfate/TDS (lixiviant reagents) should work everywhere.
- **Receptors**: at Jamshedpur (#9) the plume should trigger the **river-crossing note** when it
  reaches the Subarnarekha (`river_crossing` populated, discharge in m³/s). Elsewhere the far-field
  note should reflect the real ~km-scale drainage density.
- **Vertical**: `vertical.district`, `layer1_base_source`, `fractured_aquifer_range_m` should be
  populated from the per-district NAQUIM data; `years_to_breakthrough` and shallow-aquifer impact %
  should be physically ordered (deeper ore / thicker confining ⇒ longer breakthrough, lower impact).
- **Water table**: post-monsoon shallow water-table depth should feed the Layer-1 receptor context.
- **Plausibility envelope**: for a "typical" wellfield (inj≈2500, op≈8, time≈10) the affected area
  should land in a screening-plausible range (order 10s–100s ha, not 10⁴ ha or 0.01 ha) at most pins;
  flag physically absurd magnitudes.

### 4E. Guardrails & robustness
- Out-of-Jharkhand pin (#26) ⇒ 422 `OUTSIDE_JHARKHAND`. Ocean/edge coordinates handled.
- Every slider at **both extremes simultaneously** (stress corners) ⇒ no crash, no NaN/inf in any
  metric, bands stay ordered.
- Contradictory combos (e.g. huge injection + huge bleed; zero gradient; restoration with op>time)
  ⇒ defined, finite behaviour.
- Determinism: same request twice ⇒ same result (or MC noise within a stated tolerance).

---

## 5. Output — the bug report

Produce a single ranked report. For **each finding**:

- **Title** — one line.
- **Severity** — Critical (wrong physics that corrupts training labels / crashes) / High (wrong
  direction or discontinuity a user would hit) / Medium (magnitude off, misleading UI) / Low (cosmetic).
- **Engine** — analytical / ML / generator / serve-wiring / frontend.
- **Reproduce** — exact request JSON (or Python snippet) + the pin. Must be runnable as-is.
- **Expected vs Actual** — the invariant it violates (cite §4x) and the numbers.
- **Root-cause hypothesis** — which file/function likely, and why (e.g. "binary gate like the
  restoration bug in `physics/transport.py`").
- **Confidence** — Confirmed (you reproduced it) vs Suspected.

Then a short **"surprising-but-correct" appendix**: behaviours that look wrong but are intended
(e.g. restoration saturating at the 0.02 residual floor by ~30 yr; extrapolation flags above the
trained range; radial-dominated "migration" reading as extent not travel). This prevents false alarms
in the retrain decision.

**Ground rules**: script everything and show the assertion code; quantify every claim with numbers;
separate Confirmed from Suspected; do not modify source; if an invariant in §4 is itself wrong for
this physics, say so and explain. **Be exhaustive on the snap-back / discontinuity class (§4B) — that
is where the last bugs live.**
