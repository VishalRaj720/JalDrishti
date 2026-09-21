\newpage

# 5. Assumptions and limitations

Each row states an assumption, where it enters the system, the consequence if it is wrong, and how the product discloses it. The source is the live register `docs/LIMITATIONS.md` and the `UNGROUNDED_PARAMETERS` register, reorganised rather than copied; the tables are the reason the results in §6 can be read without over-reading them.

## 5.1 Scientific assumptions

| Assumption | Where it enters | Consequence if wrong | How it is disclosed |
|---|---|---|---|
| No ISR mine exists in Jharkhand; commercial ISR is not plausible in schist-hosted ore; every output means "if ISR-strength lixiviant entered this aquifer" | the premise of every run | every modelled number would be read as a feasibility finding or a forecast | the UI title and disclaimer; `LIMITATIONS.md` §0; this report's conventions |
| Porous-medium ISR physics (Domenico) transfers to fractured schist with a dual-porosity + matrix-diffusion overlay | §4.5 | a real shear-zone plume would be narrow fingers along shears, not a smooth ellipse; extents could be wrong in either direction | fidelity matrix Q1; "screening-grade, indefensible for prediction" |
| Analytical, steady, uniform, single-layer transport | §4.5 | no channelling, no transients, no true 3-D | §4.5 limitations paragraph; the 2.5-D decision |
| Linear equilibrium sorption with literature Kd ranges; alkaline chemistry suppresses uranium sorption | eqs. 4.3, 4.8, 4.13 | retardation wrong by the Kd error; the fractured front is species-dependent only through R_m | Kd sampled into the bands; register entries |
| First-order, infinite-sink uranium attenuation with a Wyoming-calibrated ceiling | eq. 4.17 | long-horizon attenuation overstated where reducing capacity is exhausted, understated where fresh | k sampled over a 14× range; mode tilted by mineralogy; sulphate/TDS carry none |
| β derived from lithology-typical porosities; a log-uniform [0.3, 20] prior; a ×4 band | eq. 4.9; every fractured label | the plume extent scales with β (β = 0.5 → 61 m; β = 0 → 938 m at Jaduguda uranium, 20 yr); the band expresses uncertainty *inside* the prior | `hydro.beta_basis`; §6.9 sensitivity; "a Singhbhum tracer test is the only thing that retires this" |
| Fixed matrix transfer rate ω; foreign-analogue aperture and D_e | eqs. 4.7, 4.13 | early-time over-retardation of uranium in the continuum branch (bounded by the Tang union) | register; sensitivity ≈ 0 at 20 yr except belt uranium |
| Texas source term (n = 9 at 7 mines), grade-scaled, applied to uraninite-in-schist | C₀ | the served C₀ is ~40× the measured Jaduguda passive mine water (GM 357 ppb [22]); leach kinetics of massive uraninite with sulphides differ from roll-front coffinite | `source_term_context` in every response reports the ratio to the measured value |
| Texas restoration endpoints (paired per-mine ratios) | eq. 4.15 | per-mine ratios span an order of magnitude; the single median hides it | the spread is sampled into the bands; the floor at the endpoint is explained |
| Vertical: Kv/Kh, an upward gradient of 0.005, a wellbore probability of 0.05 | §4.5 vertical screening | the shallow-impact index is "violently sensitive" to the gradient (0.005 → moderate, 0.020 → high) | bracketed by the measured monsoon swing as a two-end-member band; register |

## 5.2 Data assumptions and limitations

| Limitation | Where it bites | Consequence | Disclosure |
|---|---|---|---|
| One chemistry sample per well, one year (2023) | trends, control limits, alerts on rate of change | no measured-quality forecast is possible; no per-well UCL of the mean + 5σ kind | §3.5; the 2000–2021 record read for general chemistry only |
| No well depths or screen intervals | any vertical claim | 3-D is unsupported; the vertical column is a district table | §4.5, §7 |
| Fe, As, Mn never measured; CO₃ all zero | health band, alerts, the proposal's input list | no block can be cleared for arsenic or iron | `untested_health` on every band; `not_tested` on every well |
| 55 wells in the three Singhbhum districts un-analysed for uranium | the uranium belt itself | the belt is untested for the one contaminant the tool screens for | `Not tested` band; ranking factor with weight 30 |
| Spatial density ~1 well per 200 km² | background at a pin | the nearest well may be tens of km away | `data_confidence.nearest_well_km` |
| NAQUIM at district scale; three districts on regional estimates | vertical screening, K(z) | a per-district λ and layer base applied to every pin in the district | confidence column in the layer table |
| CGWB values characterise the shallow aquifer, applied at ore depth through a modelled K(z) | every fractured run | the deep K is a law, not a measurement | `extrapolation` reports `hydro:K_m_day` below trained support |
| The 2023 charge balance is a consistency of construction (Na by difference) | QA | zero suspect analyses is not evidence of laboratory quality | `independence_check` reported with the QA summary |
| The 2000–2021 record carries no health determinand | D1 "forecast trends" | trend forecasting for any banded or alerted determinand remains undemonstrated | §7; no band or alert uses the record |
| A demo field observation (`jharia`) sits in the tracked ore dataset | uranium source term near Dhanbad | a deposit-tier hypothetical source where no deposit exists | found during this report; §3.5 item 7; to be removed via the dataset manager |

## 5.3 Modelling (surrogate) limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| The surrogate is trained on the engine's output and cannot exceed it | its accuracy is fidelity to the engine, not to reality | every UI number names its engine; "analytical is the authority" |
| Conformal coverage is guaranteed inside trained support and for parameter uncertainty only | outside support the band no longer means 80 %; structural error is uncovered by any band | `extrapolation` flags; §4.9 |
| Radium labels are point masses (81.8 % exact zeros for migration; 95.8 % pinned at background for compliance) | R²(log) 0.500 / 0.235, below the project's 0.60 gate; a squared-error learner on `log1p` cannot fit a point mass | reported as a miss in the generated metrics block; the analytical engine serves the central value; the conformal band on those cells still covers |
| Hyper-parameters fixed, no search; no ANN/deep families | possibly sub-optimal heads; nothing to learn that XGBoost has not on 18,000 synthetic rows | stated in §4.6.3 and the audit's D-list |
| Tree quantisation seams (~17 % migration across rest 0 → 0.5 yr; ~0.6 ha at the restoration boundary) | step changes in the surrogate where the engine is smooth | measured; the engine stays inside the band at every probed seam (6/6) |
| Pooled back-transformed R² mixes ppb, mg/L and mBq/L (compliance R²(P50) = −4.48) | the pooled number depends on the species mix, not model quality | judged on per-species and log figures |

## 5.4 Simulation (scenario) limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| Every result is conditional on the scenario of §3.6 | changing Q_in, W, operation years or the ring changes every number | the scenario is stated before any result; the registered site's overrides are printed with its report |
| Depth-integrated plan view; 2.5-D vertical screening only | no depth-resolved concentration; no shallow plume after breakthrough | §4.5; "the radius decides who is told, not a predicted extent" |
| Uniform flow direction per run from a 5 km field | a pin between stations takes the interpolated direction; divides are flagged | `flow_field.source`, `near_divide` |
| Horizon ≤ 50 yr, trained to 20; restoration trained to 10 | beyond the trained range the surrogate extrapolates and is flagged; the engine still serves | hollow points on the sweep chart; `extrapolation` |
| Operation years up to 20 represent a multi-wellfield unit on one footprint | a single wellfield runs 1–3 yr | §3.6 |
| The front is held, not reversed, during restoration | conservative: the model cleans slower than a real sweep | §4.5 |

## 5.5 System and engineering limitations

| Limitation | Consequence | Disclosure |
|---|---|---|
| No sensors, no telemetry | not real-time; CPS-ready decision support, never a live loop | §4.10; the words "real-time" avoided |
| Email only; no SMS; the SMTP provider is the operator's; the free tier sleeps the API and with it the scheduler | a resident without email is reached only through the portal; alerts wait while the API sleeps | the Administration screen counts the backlog |
| The test database has no RLS policies | RLS-after-COMMIT defects are not runtime-testable in the suite | source-level guards, and tests that say so |
| No frontend unit tests; PDF pagination hand-checked | regressions in the portal are caught by hand | build guard only |
| No run reaper for jobs orphaned by a restart; engine rate limit per host; backups defined but a restore run once | operational, not scientific | `DEPLOYMENT.md` §8c, §9 |
| Deployed API runs the committed artifacts of whichever commit was last deployed | the report's numbers are from `476a4a9`; the deployment must be redeployed to match | §8 of `PROJECT_FREEZE.md` |

## 5.6 Generalisation limits

| Claim | Status |
|---|---|
| Jharkhand only | the datasets end at the state boundary; a pin outside is a 422, because a prediction there would be fabricated |
| Other commodities (coal, rare earth, heavy metals) | *designed for* through the species registry (`SPECIES` / `ML_SPECIES` / `EXCURSION_ONLY_SPECIES`; chloride was added without a retrain as the proof) — **not demonstrated** |
| Any modelled result | a conditional statement about a hypothetical operation, never a forecast of real contamination |
| "Validated" | benchmarked against exact solutions and internally gated — never validated against a real plume, because none exists to validate against |
