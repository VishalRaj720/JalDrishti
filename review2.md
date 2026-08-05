# Independent Validation — Adversarial Re-Audit

**Date:** 2026-08-05 · **Method:** first-principles re-derivation and runtime probing, treating every
prior decision (including my own remediation) as unproven. **Scope:** evidence quality, physics
validity, ML statistics, security, robustness.
**Baseline:** 221 tests pass. Companion to `review.md` (pre-remediation audit, left untouched as the
historical record).

**Framing:** the previous audit asked "does the code do what the docs claim?" This one asks "is what
the code does *defensible*, and does the evidence exist?" Those are different questions, and the
system scores differently on them.

---

## Findings, ranked

### V-1 · CRITICAL · The core analytical solution has a documented error of up to 80%, and it is nowhere quantified or disclosed

**The problem.** The entire physics engine — and therefore every ML training label — rests on the
Domenico (1987) approximation. That approximation has a peer-reviewed error characterisation the
project never cites:

> West, Kueper & Ungs (2007), *Groundwater* 45(2): errors range **2 % to 80 %** depending on
> parameter values; the solution **underpredicts centreline concentrations by as much as 80 %**.
> It is exact only when longitudinal dispersivity is zero; error grows with dispersivity, time and
> dimensionality.

Two things make this acute here rather than academic:

1. The remediation re-based `max_migration_distance_m` onto the **plume centreline** (`centreline_reach`,
   `transport.py`) — precisely the location where West et al. measure the largest underprediction.
2. The model runs with **α_L = 4.43 – 43.17 m** (measured across the 18,000 training rows) and
   Péclet `L/α_L` median 52.5, with **96.6 % of rows below Pe = 100**. This is not the zero-dispersivity
   limit where Domenico is exact.

**What I did and did not establish.** I did *not* measure the error for this parameter range — no
exact-solution benchmark exists in the repo to compare against. That absence *is* the finding: a
screening tool whose ground truth carries a literature-documented 2–80 % error band has never
bounded that error, and reports a centreline metric without it. `ARCHITECTURE.md` §4.4 describes
Domenico as "an approximate product solution used across the entire screening-model industry" and
lists only the dropped upstream term as a consequence — the centreline underprediction is not
mentioned anywhere.

**Recommendation.** Benchmark `concentration_field` against an exact solution over the model's own
parameter box and publish the error envelope. Two options, in order of preference:
- Sagar/Wexler exact 3-D solutions (Wexler 1992, USGS TWRI 3-B7) — the standard reference implementation.
- The corrected formulation in *Improved Domenico solution for three-dimensional contaminant
  transport* (J. Contam. Hydrol., 2021), which repairs the specific approximation West et al. identify.

**Expected impact.** Either the error is small in this box — in which case a one-off benchmark
converts an unbounded risk into a stated, defensible tolerance — or it is large, in which case every
compliance concentration and breach probability the tool has ever reported is biased low, and the
"conservative screening" claim inverts. You cannot currently tell which, and that is the point.

---

### V-2 · HIGH · The uranium source term — the single most influential parameter — rests on nine measurements

**The problem.** `texas_source_signature()` derives the served C0 envelope from the "End of Mining"
sheet. That sheet contains **9 usable uranium rows from 7 mines**:

```
Benavides 41.6 · El Mesquite 12.3 · Holiday 6.8 · Holiday 16.0 · O'Hern 9.0
Pawnee 9.8 · Rosita 17.4 · Rosita 23.7 · West Cole 10.0        (mg/L)
```

From these nine numbers the model serves **C0 ∈ (9,800 – 34,440) ppb**, taken as the **P25 to P95**
quantiles. The full observed span is 6,800 – 41,600 ppb.

Three separate objections:
1. **n = 9.** C0 scales the entire concentration field linearly; every area, compliance concentration
   and breach probability is proportional to it.
2. **The P25–P95 window is arbitrary and asymmetric.** No justification appears in the code, the
   config, or `ARCHITECTURE.md`. It discards the lower quartile of real observations while retaining
   almost the entire upper tail — a choice that biases the tool conservative, which may be intended,
   but is undocumented and therefore untestable.
3. **Two of the seven mines contribute two rows each**, so the quantiles are computed over
   pseudo-replicated, non-independent samples.

**Recommendation.** State n = 9 wherever C0 provenance is reported (`source_term_context` already
reports the Jaduguda comparison — add the sample size). Replace the arbitrary quantile window with
either the full observed range or a documented tolerance interval, and weight by mine rather than by
row. If the conservative bias is deliberate, say so in config next to the choice.

**Expected impact.** No change to physics; a large change to how much confidence a reader should
place in the absolute numbers. Currently a user sees "13,272 ppb" with four significant figures.

---

### V-3 · HIGH · The restoration residual uses a statistically invalid unpaired estimator

**The problem.** `texas_restoration_residual()` computes

```python
residual = median(Final Post-restoration) / median(End of Mining)
```

These are **different, unpaired samples of different sizes**: 9 EOM rows against 92 post-restoration
rows, of which only **7 mines are common to both sheets**. A ratio of medians across non-matched
groups does not estimate the per-site restoration efficiency it is used as; it conflates
restoration performance with differences in which mines appear in which sheet.

**Evidence.** I computed the correct paired statistic — the median of per-mine ratios:

| species | served (ratio of medians) | paired (median of ratios) | n pairs | paired spread |
|---|---|---|---|---|
| uranium | 0.0659 | **0.0600** | 7 | 0.023 – 0.248 |
| sulfate | 0.1460 | **0.1381** | 7 | 0.075 – 0.299 |
| TDS | 0.3673 | **0.3370** | 6 | 0.124 – 0.623 |

**Numerical impact is small (≈9 %)** — the estimator is wrong but happens to land close. The real
cost is the hidden variance: the paired uranium ratios span **0.023 to 0.248, an order of magnitude**,
and the model serves a single point value with no uncertainty. `RESTORATION_REF_YEARS = 5.0` is
described as grounded in "13 Texas production areas", but the residual it anchors is built on 7.

**Recommendation.** Switch to the paired median, and sample the residual across the observed
per-mine spread in the MC rather than serving a point value (the machinery already exists —
`IRREGULARITY["residual_noise_mult"]` applies a ×0.7–1.5 jitter that is *narrower* than the real
0.023–0.248 spread and is not derived from it).

**Expected impact.** Restoration bands widen to reflect the real between-site variability. The
current bands understate how uncertain post-restoration source strength is.

---

### V-4 · MEDIUM · The Excel parser ingests footnotes and repeated headers as data rows

**The problem.** `_load_geochem_sheet()` detects the header row by searching for `Sulfate` + `Uranium`,
then treats every subsequent non-empty row as data. The "Final Post-restoration" sheet has 92 such
rows, of which **5 are not data**:

```
'Post-restoration groundwater composition - Average composition of groundwater achieved after…'
'Mine'                                                    <- a repeated header row
'1 Lixiviant type from U.S. Environmental Protection Agency (2007).'
'2  The post-restoration average for Rosita PAAs 1 and 2 are averages of only 2 stability samples…'
'3  Tweeton (1981)'
```

**Currently harmless** — these rows carry no parseable numbers, so `pd.to_numeric(...).dropna()`
removes them from every constituent column. But the sparsity guards that decide whether to fall back
to config values (`if len(e) >= 2 and len(p) >= 2`) count them, and any future column whose footnote
happens to contain a number would be silently ingested. This is a latent, not an active, defect.

**Recommendation.** Terminate the data block at the first row whose label column fails a plausibility
test (length > 40 chars, or equal to the header token), and assert the surviving row count against a
pinned expectation so a re-import that changes the sheet layout fails loudly.

---

### V-5 · MEDIUM · The conformal 80 % guarantee is calibrated on a distribution the serve path does not produce

**The problem.** Split-conformal prediction guarantees coverage **only under exchangeability** between
calibration and test data. Calibration here is a random half of the *generator's* scenarios. The
generator does not sample the distribution users actually query:

| | generator | real flow field | ratio |
|---|---|---|---|
| gradient p10 | 0.00165 | 0.00121 | 1.36× |
| gradient p50 | 0.00400 | 0.00297 | **1.35×** |
| gradient p90 | 0.01540 | 0.00764 | **2.02×** |

The generator's median hydraulic gradient is **1.35× the real field median**, and its p90 is **2×**.
`E1_geometry_design.md` §6 gate 5 anticipated exactly this and mandated a "FIELD-RESAMPLED coverage
batch: ~100 scenarios pinned to real grid cells with real V/gradient/amp; scenario coverage must hold
≥ 0.80 THERE". **I found no artifact, test, or metrics field recording that this gate was ever run
against the current model.** `FIELD_MIX_FRAC = 0.60` mitigates but does not eliminate the mismatch —
40 % of scenarios still draw gradient uniformly from the envelope.

Meanwhile the UI states, without qualification: *"parameter uncertainty · 80% conformal"*.

**Recommendation.** Implement the field-resampled coverage batch as a test, report its coverage in
`metrics.json` alongside the generator-distribution coverage, and qualify the UI string when the two
disagree. If field coverage is below 0.80, the honest fix is to widen the Mondrian deltas until it holds.

**Expected impact.** Converts a guarantee that is currently true-of-the-generator into one that is
true-of-the-tool, or exposes that it is not.

---

### V-6 · MEDIUM · No authentication, no rate limiting, on any endpoint

**The problem.** 12 FastAPI endpoints, **zero with auth or rate limiting**. `POST /api/predict` runs a
200² grid solve plus a 48-draw Monte Carlo per call (~0.1 s CPU). `GET /api/aquifers` returns
**0.48 MB uncached** per request. The frontend's timeline animation issues one request per simulated
month by design, so sustained request rates are a *normal* traffic pattern, not an attack signature.

CORS is correctly defaulted to localhost with explicit opt-in for `*` — that part is well handled.
Pydantic `Field` bounds validate every numeric input, and I could not construct a crashing payload
(see V-8). So the exposure is availability, not integrity.

**Recommendation.** Before any deployment beyond localhost: add rate limiting (`slowapi` or a reverse
proxy), cache the static GeoJSON endpoints (`/api/aquifers`, `/api/ore`, `/api/rivers`, `/api/boundary`
are all deterministic — an `ETag`/`Cache-Control` header is sufficient), and put the whole app behind
auth if the deployment is not public by intent.

---

### V-7 · MEDIUM · β is the most leveraged parameter in the model, is ungrounded, and is user-settable

**The problem.** Measured at the default Jaduguda pin, uranium:

| β | migration | excursion probability |
|---|---|---|
| 10 (default) | 7.1 m | 0.00 |
| 0 (API override) | **232.4 m** | **0.98** |

A single API parameter moves migration **33×** and flips excursion probability from 0 to 98 %. β is
one of the values fidelity row 3.4 flags as having **zero Singhbhum measurements** behind it, and
`PredictRequest` exposes it directly (`beta: float | None = Field(None, ge=0, le=50)`).

**In mitigation, and this is a genuine strength:** the envelope guard correctly fires — β = 0 and
β = 50 both raise `hydro:retardation_Rd`, as does K = 50. The guard rails work.

**Recommendation.** Keep the override (expert use is legitimate) but surface the sensitivity: when β
is user-supplied, return the default-β answer alongside it so the user sees what their override cost.

---

### V-8 · LOW · Residual t = 0 inconsistency

At `time_years = 0` the served answer is `area = 0.00 ha` but `migration = 0.34 m`. The disc-growth
fix removed the source footprint at t = 0, but the Domenico term still paints C0 at the source plane
at t = 0, and dispersion smears it 0.34 m past the threshold. Physically nothing has been injected,
so both should be zero. Minor in magnitude, but it is the same class of error as the 7.07 ha bug and
makes the two metrics mutually inconsistent at the origin.

---

## What survived the audit

Stated once, because it is evidence too:

- **Robustness is genuinely good.** 15 adversarial edge cases (slider extremes, `t < op`,
  `rest > t`, ore thickness exceeding depth, φ = 0.001, K = 500): **no crash, no NaN, no negative,
  no infinite** result anywhere.
- **The out-of-distribution guard works** on both operational and hydrogeological inputs.
- **CORS and input validation are correctly implemented.**
- **The train/serve feature path is genuinely single-sourced** after the registry consolidation, and
  the central-vs-MC parity test pins the two engines to 1e-9.

---

## Ranked recommendations

**Do before any external use:**
1. **V-1** — benchmark Domenico against an exact solution and publish the error envelope. This is the
   only finding that can invalidate the tool's outputs wholesale rather than widen their error bars.
2. **V-6** — rate limiting and caching, if this ever leaves localhost.
3. **V-5** — run and record the field-resampled coverage gate the E1 design already mandated.

**Do next:**
4. **V-3** — paired restoration estimator, and sample its real 0.023–0.248 spread.
5. **V-2** — disclose n = 9 and justify or replace the P25–P95 window.
6. **V-4** — harden the Excel parser with a pinned row-count assertion.

**Lower priority:** V-7 (comparative answer on β override), V-8 (t = 0 consistency).

---

## Honest limits of this audit

- I did **not** benchmark Domenico numerically (V-1) — that requires implementing an exact solution,
  which is the recommendation itself, not something to do inside the audit.
- I did **not** re-derive the Tang, Goltz–Roberts, or Xu & Eckstein formulations from their source
  papers; I verified their *implementation* is internally consistent and correctly wired, not that
  each transcription matches the original publication line for line.
- The Kd, aperture, D_e, ω and β values remain foreign-analogue literature values with no Singhbhum
  measurements (fidelity row 3.4). I re-confirmed the labelling is complete; I could not improve the
  grounding, and no public data exists that would.
- Coverage figures quoted are from the committed `metrics.json`; I did not re-run training to
  reproduce them independently.
