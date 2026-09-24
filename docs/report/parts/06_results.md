\newpage

# 6. Results

## 6.0 What kind of result each subsection reports

**[M]** measured — a laboratory value or a station reading compared with a published limit; nothing modelled. **[S]** modelled scenario — the engine or surrogate evaluated for the hypothetical operation of §3.6; conditional, never a forecast. **[V]** model-internal validation — the surrogate against the engine, or the engine against an exact solution. Every figure caption repeats the tag. Every number in this section was re-derived on the report date from the artefact named in Appendix H; where an earlier value is quoted for comparison it carries its date.

## 6.1 Exploratory data analysis of the measured record [M]

**Exceedances against IS 10500:2012.** Table 3.2 is the descriptive record. The health-significant findings, re-derived from `waterQuality_jharkhand.csv`: uranium is within its 30 ppb limit at all 342 analysed wells (maximum 28.5 ppb at Sukurhutu, Ranchi; median 0.78 ppb); nitrate exceeds 45 mg/L at **22** wells, peaking at 121 mg/L at Biru (Simdega) and 99 mg/L at Lowadih (Ranchi) — 2.7× and 2.2× the limit; fluoride exceeds the 1.0 mg/L acceptable limit at **32** wells and the 1.5 mg/L permissible limit at **11** (maximum 1.91 mg/L at Baresad, Latehar). One well, Gidhaur (Chatra), exceeds both the nitrate and the fluoride permissible limits. In all, **32 wells** carry a health exceedance at the alert-triggering bar and **14 of 24 districts** contain at least one — Bokaro, Chatra, Dhanbad, Garhwa, Godda, Gumla, Hazaribagh, Koderma, Latehar, Lohardaga, Palamu, Ramgarh, Ranchi and Simdega. By contrast 71 % of wells exceed *some* IS 10500 limit, most of it hardness, calcium, magnesium and TDS — hard-rock aquifer chemistry rather than contamination — which is why that figure is never reported first.

**What was not measured.** Iron and arsenic: zero of 397. Manganese, temperature, turbidity, dissolved oxygen: no column (temperature and turbidity exist in the NWDP physical file, 2000–2021). Uranium: 55 wells in East Singhbhum (28), Saraikela-Kharsawan (11) and West Singhbhum (16) sampled and not analysed.

**Hydrochemical QA.** Of 397 analyses, 393 have a complete major-ion set. All 393 balance within ±3.2 % (median |CBE| 0.56 %); none is questionable or suspect. Sodium re-derived from the other ions reproduces the reported value to a median 1.6 mg/L (65 % within 2 mg/L); total hardness equals 2.497 Ca + 4.118 Mg within 5 % for 99 % of samples. The ion-sum/EC ratio has a median of 0.70, inside the expected 0.55–0.75. Conclusion: the 2023 file's charge balance is a consistency of construction and is not evidence of laboratory quality (§3.5). On the 2000–2021 file the balance is genuine — 127 of 753 computable analyses are suspect at 10 %.

**Level trends (Theil–Sen / Mann–Kendall), 2013–2021.** Of 415 stations in the database record, 331 are testable and 84 are not (fewer than 8 readings or under 3 years). **5 stations are declining, 20 recovering, 306 stable.** The fastest decline is 0.785 m/yr at Chapodia (Dumka). The median seasonal swing is 2.38 m. The result is undramatic, and that is the finding: there is no statewide level crisis in this record, and a station with too short a record is reported as such, never as stable.

**Chemistry trends, 2000–2021.** 244 of the platform's wells have two or more sampling years in the NWDP record; 175 clear the trend threshold for electrical conductivity, of which **13 are rising and 6 falling**, the rest without a significant trend. No health determinand can be trended, because none is in the file.

![Figure 6.1 [M] — The public map: districts coloured by the worst measured health determinand (uranium, nitrate or fluoride) against IS 10500:2012 [25], from the 2023 CGWB record [39]; 14 of 24 districts are High concern, driven by nitrate and fluoride, and grey (`Not tested`) is never green. Screenshot from the deployed portal, August 2026. Basemap © OpenStreetMap contributors, available under the Open Database Licence; rendered with Leaflet.](figures/fig_public_map.png)

## 6.2 Machine-learning model performance [V]

**Table 6.1 — v5 surrogate, GroupKFold(5) on scenario (18,000 rows, 900 scenarios, 23 polygons). Log-space R² of the P50 head; conformal coverage at α = 0.20; baselines on the same folds. Source: `ml_pipeline/ml/artifacts/metrics.json`, 21 Sep 2026.**

| Target | R²(log) P50 | R² (raw, P50) | MAE (P50, physical units) | Scenario coverage (gate ≥ 0.80) | Rows coverage | Mean baseline R²(log) | Ridge R²(log) | Stump R²(log) |
|---|---|---|---|---|---|---|---|---|
| `affected_area_ha` | **0.893** | 0.783 | 6.91 ha | **0.863** | 0.955 | −0.001 | 0.561 | 0.384 |
| `max_migration_distance_m` | **0.926** | 0.504 | 68.8 m | **0.878** | 0.952 | −0.002 | 0.773 | 0.515 |
| `compliance_conc` | **0.947** | −4.48 | 498 (mixed units) | **0.866** | 0.948 | −0.001 | 0.744 | 0.499 |
| `excursion_probability` (point) | R² 0.915 | — | MAE 0.049 | — | — | — | — | — |

The surrogate beats every baseline on every target in log space. The raw-unit R² of the compliance head is strongly negative because the pooled figure mixes ppb, mg/L and mBq/L and its denominator is set by the species mix, not model quality; the per-species figures are the ones to judge.

**Table 6.2 — Per-species R²(log) of the P50 head. Gate ≥ 0.60.**

| Target | Uranium | Sulphate | TDS | Radium-226 |
|---|---|---|---|---|
| `affected_area_ha` | 0.943 | 0.789 | 0.820 | 0.892 |
| `max_migration_distance_m` | 0.930 | 0.878 | 0.884 | **0.500 (fails)** |
| `compliance_conc` | 0.847 | 0.917 | 0.962 | **0.235 (fails)** |

**The radium gate failure, reported not moved.** Radium's migration label is 81.8 % exact zeros and its compliance label 95.8 % pinned at the 23 mBq/L background: a squared-error regressor on `log1p` cannot fit a point mass, and R² divides by a near-zero total sum of squares. The R17 β retrain left migration unchanged (0.516 → 0.515) and *worsened* compliance (0.431 → 0.227) because the wider prior moved a few more scenarios off the background pin; v5 is 0.500 / 0.235. The remedy — a zero-inflated two-stage head — is a new ML approach and was not authorised in the final month. The conformal bands on those cells still cover (0.927–0.951 rows in cross-validation; 0.94–0.965 field-resampled), and the analytical engine serves the authoritative radium value, so the failure is in the surrogate's point estimate, not in its uncertainty guarantee. If the gate is read as binding for release, the pipeline is not ready for radium.

**Leave-aquifer-out (23 polygons held out in turn).** R²(log) 0.890 / 0.921 / 0.941 for area / migration / compliance (raw P50 0.803 / 0.394 / −3.63; MAE 6.97 ha / 73.1 m / 447) — within a few hundredths of the scenario-grouped figures, so spatial generalisation to unseen aquifer polygons costs little.

**Table 6.3 — Conformal coverage per Mondrian cell (rows, cross-validation) and field-resampled coverage (120 scenarios pinned to the real flow and strike fields, held out; gate ≥ 0.80 on scenarios).**

| Target | Cross-validation, worst cell | Field-resampled scenarios | Field-resampled rows | Weakest field cell |
|---|---|---|---|---|
| `affected_area_ha` | fractured\|radium 0.933 | **0.885** PASS | 0.965 | fractured\|sulphate 0.944 |
| `max_migration_distance_m` | fractured\|radium 0.927 | **0.875** PASS | 0.949 | fractured\|TDS 0.874 |
| `compliance_conc` | porous\|radium 0.921 | **0.881** PASS | 0.950 | fractured\|sulphate 0.909 |

Band-order violations (P10 ≤ P50 ≤ P90) in the training set: 0 of 18,000. On-manifold physics laws hold on the surrogate's own output: area rises with Q_in at fixed Q_net (12.1 → 16.4 ha) and falls with bleed at fixed Q_in (16.8 → 15.4 ha).

**The transport kernel against an exact solution.** The second review round hypothesised, citing West et al. [10], that the Domenico product approximation could corrupt results by up to 80 %. The benchmark (`physics/exact_reference.py`, 240 parameter sets drawn from the training distribution; the reference collapses onto Ogata–Banks to 1.1 × 10⁻¹⁶ as W → ∞) disproved it and found the real error elsewhere:

**Table 6.4 — Centreline error of the transport kernel, (model − exact)/exact, August 2026.**

| Position | Product approximation only (full Ogata–Banks retained) | Truncated Ogata–Banks (as then served) p50 | Truncated, p5–p95 |
|---|---|---|---|
| x = 0.5 X_c | 0.00 % | −16.9 % | −39.8 % to −0.0 % |
| x = 1.0 X_c | 0.00 % | −22.4 % | −40.4 % to −5.3 % |
| x = 1.2 X_c | −0.10 % to 0.00 % | −24.3 % | −40.6 % to −11.3 % |
| Down-gradient reach (the migration metric) | — | −3.6 % | −6.5 % to −0.3 % |

The product decoupling costs nothing in this model's parameter box (α_T/α_L 0.01–0.10, sources 147–763 m wide); the dropped second Ogata–Banks term biased every concentration 17–42 % *low* — the opposite of the conservative posture the tool claims — while the threshold-crossing metrics moved only a few per cent. The term was restored (commit `5fb3fe6`) and the surrogate retrained on the exact kernel.

**Retraining history.** Migration R² moved 0.719 → 0.896 across the July label corrections (down-gradient travel, analytical centreline reach, Kd-dependent fractured front), then to 0.929 (v3), 0.927 (v4) and 0.926 (v5). The end-to-end audit on the report commit: **43 of 44 checks pass**; the one failure is the radium gate above.

## 6.3 Feature importance and explainability [V]

Mean absolute SHAP values on the P50 heads (`ml/artifacts/shap_top_*.json`, v5) rank the features the surrogate relies on:

**Table 6.5 — Top SHAP features per head (mean |SHAP|, log-space output).**

| Rank | Footprint area (P50) | Migration (P50) | Excursion probability |
|---|---|---|---|
| 1 | `source_conc_C0` 0.72 | `Xc_m` 1.33 | `Xc_m` 0.230 |
| 2 | `alpha_L` 0.31 | `source_conc_C0` 0.57 | `source_conc_C0` 0.051 |
| 3 | `wellfield_width_m` 0.25 | `residual_fraction` 0.31 | `residual_fraction` 0.028 |
| 4 | `residual_fraction` 0.22 | `is_radium_226_mbq_l` 0.29 | `is_tds_mg_l` 0.027 |
| 5 | `is_radium_226_mbq_l` 0.15 | `is_tds_mg_l` 0.22 | `D_T` 0.019 |
| 6 | `is_tds_mg_l` 0.14 | `containment_eta` 0.15 | `containment_eta` 0.015 |
| 7 | `Kd_L_kg` 0.13 | `is_sulfate_mg_l` 0.12 | `dimensionless_time_tau` 0.015 |
| 8 | `Xc_m` 0.11 | `background_conc_Cb` 0.09 | `background_conc_Cb` 0.014 |

The ranking agrees with the physics it should reflect. The analytical front position X_c — which already folds velocity, containment and the retarded clock — dominates migration and excursion probability, as it must (eq. 4.6); the source concentration and the wellfield width dominate the footprint, which is 76–97 % leach disc (§4.5); the realized restoration fraction and the species one-hots (radium and TDS at the two ends of the retardation range) carry the rest. Containment η appears with the expected sign. No spatial coordinate can appear, because none is a feature.

![Figure 6.2 [V] — SHAP feature attributions for the excursion-probability head (v5). Source: `ml/artifacts/shap_excursion_probability.png`.](figures/fig_shap_pex.png)

## 6.4 Spatial results at three reference sites [S]

**Table 6.6 — Reference-case runs at 20 years (operation 8 yr, Q_in 2,500 m³/day, bleed 2 %, W 300 m, no restoration, ring 100 m), analytical engine with the v5 surrogate band. Re-derived on the report date.**

| Pin (ore zone) | Species | K (m/day) | β | C₀ | Background | Footprint (ha) | Migration (m) | At the ring | p_ex | ML migration P10–P50–P90 (m) |
|---|---|---|---|---|---|---|---|---|---|---|
| Jaduguda deposit (86.347, 22.652), fractured, shear zone | uranium | 0.563 | 3.00 | 15,180 ppb | 1.0 ppb | 9.60 | **20.5** | 1.0 ppb | 0.00 | 2.7 – 18.6 – 100 |
| | sulphate | | | 1,624.5 mg/L | 227 | 11.25 | **73.1** | 244 mg/L | 0.27 | 3.5 – 42 – 467 |
| | TDS | | | 3,655.5 mg/L | 1,779 | 17.62 | **254** | 4,428 mg/L | 0.96 | 10.5 – 235 – 3,043 |
| | radium-226 | | | 1,706 mBq/L | 23 | 9.06 | 0.6 | 23 mBq/L | 0.00 | 0.0 – 0.5 – 2.3 |
| Mid-belt (86.25, 22.63), fractured, belt tier | uranium | 0.429 | 2.00 | 7,590 ppb | 1.0 | 12.53 | 19.5 | 1.0 | 0.00 | 2.6 – 16 – 80 |
| | sulphate | | | 1,624.5 | 46 | 13.66 | 60.7 | 63 | 0.10 | 4.3 – 36 – 333 |
| | TDS | | | 3,655.5 | 669 | 17.94 | 171 | 3,243 | 0.79 | 9.0 – 133 – 1,752 |
| | radium-226 | | | 512 | 23 | 0.00 | 0.0 | 23 | 0.00 | 0 – 0 – 0.4 |
| Ranchi (85.33, 23.36), fractured, non-ore | uranium (suppressed) | 0.094 | 2.00 | 5 (trace) | 0.65 | 0.00 | 0.0 | 0.65 | 0.00 | surrogate bypassed |
| | sulphate | | | 1,624.5 | 31 | 12.66 | 25.3 | 31 | 0.00 | 1.8 – 19 – 142 |
| | TDS | | | 3,655.5 | 463 | 13.64 | 55.6 | 639 | 0.12 | 3.1 – 44 – 553 |
| | radium-226 (suppressed) | | | 23 | 23 | 0.00 | 0.0 | 23 | 0.00 | — |

Resolved hydrogeology at Jaduguda: fractured regime, gradient 0.00205 (flow field), mobile porosity 0.0075 and productive thickness 150 m (shear-zone override), K 0.563 m/day at 150 m after depth decay, R_eff 271 (uranium), 17.3 (sulphate), 4.0 (TDS), ~3,500 (radium). Three readings of this table: the **ordering** uranium ≪ sulphate < TDS in extent, set by R_eff, is the physical reason NUREG rejects uranium as an excursion indicator, and the engine reproduces it without being told; at a **non-ore pin** the uranium source is suppressed and no uranium plume is drawn, while the lixiviant reagents still spread (a lixiviant carries sulphate wherever it is injected); and the **P90 band** for TDS at Jaduguda reaches three kilometres, which is what the `possible_reach` alert exists to tell.

Extrapolation flags: none at 20 years and 0–10 years of restoration; beyond those the sweep chart draws hollow points and the response lists the offending input.

![Figure 6.3 [S] — The console result panel for a Jaduguda-belt pin (uranium, 20 yr, 3 yr sweep), July 2026 build (β = 10, pre-R17): each metric shows the analytical value as the authority with the surrogate's band beside it, the "analytical is the authority" statement, and the NUREG 2-of-3 panel. The migration reads 11.7 m here; the same pin reads ~20 m after the R17 β correction (Table 6.7).](figures/fig_console_result_july.png)

## 6.5 Plume simulation and temporal evolution — the Jaduguda case study [S]

**The registered site.** The site registered on the deployed system sits at 86.36° E 22.65° N, 0.35 km outside the deposit polygon — a *belt* pin (uranium C₀ 14,294.5 ppb: 0.30 × the deposit value ramped over the 3 km taper) — with Q_in 1,500 m³/day, bleed 2 %, 8 years of operation, W 300 m, ore depth 150 m and thickness 20 m, ring 100 m.

**Table 6.7 — Lifecycle at the registered Jaduguda site, no restoration, analytical engine (values at each horizon; the NUREG panel is judged on Cl / TDS / SO₄ at the ring).**

| Year | Phase | Uranium source (ppb) | Footprint (ha) | Uranium migration (m) | Uranium at ring (ppb) | Shallow-aquifer index | Excursion declared | Indicators over UCL |
|---|---|---|---|---|---|---|---|---|
| 0 | operation | 14,294 | 0.00 | 0.0 | 1.0 | 0.05 | no | — |
| 4 | operation | 14,294 | 8.13 | 11.1 | 1.0 | 0.16 | no | — |
| 8 | closure | 14,294 | 8.65 | 12.5 | 1.0 | 0.28 | no | — |
| 12 | post-closure | 13,033 | 8.82 | 16.6 | 1.0 | 0.39 | **yes** | Cl, TDS |
| 16 | post-closure | 11,882 | 8.82 | 19.9 | 1.0 | 0.51 | yes | Cl, TDS |
| 20 | post-closure | 10,833 | 8.99 | 22.7 | 1.0 | 0.62 | yes | Cl, TDS |
| 30 | post-closure (extrapolating) | 8,598 | 9.16 | 28.5 | 1.0 | 0.91 | yes | Cl, TDS, SO₄ |
| 50 | post-closure (extrapolating) | 5,417 | 9.51 | 37.8 | 1.0 | 1.00 | yes | Cl, TDS, SO₄ |

The source is held at strength during injection (that is what injection is), then declines under the 30-year passive flush; the footprint grows during operation and barely afterwards (it is the leach disc); uranium migration grows after closure once containment stops but never reaches the 100 m ring within 50 years (R_eff ≈ 271); the ring nevertheless reads an excursion from the 12-year frame, because chloride (862 vs baseline 192 mg/L at 20 yr) and TDS (4,605 vs 1,779) have arrived — the conservative reagents warn first, as NUREG intends, and sulphate joins the panel by year 30. First exceedance at the ring by species: TDS between the 8- and 12-year frames, sulphate between 20 and 30, uranium never.

**The restoration sweep.** Holding the horizon at 20 years and varying the sweep length: 0 yr → migration 26.4 m at the registered site, excursion declared; 6 yr → 4.2 m, one indicator over (chloride), not declared; 12 yr and beyond → 0 m, source at its ~290 ppb rebound floor, not declared, flagged as extrapolating beyond the trained 10 years. "Zero migration" here means nowhere beyond the wellfield edge is above the 30 ppb limit, not that nothing moved.

**Table 6.8 — Before and after the R17 β correction (default operation, 20 yr, analytical engine; ML migration band from the v3 and v4 surrogates; `ml_pipeline/outputs/snapshot_{pre,post}_r17.json`).**

| Pin · species | β | Migration (m) | Footprint (ha) | At the ring | ML band (m) |
|---|---|---|---|---|---|
| Jaduguda · uranium | 10 → 3.0 | 10.6 → **20.5** | 9.3 → 9.6 | 1 → 1 ppb | 2–61 → 2–102 |
| Jaduguda · sulphate | 10 → 3.0 | 31.7 → **73.1** | 10.0 → 11.3 | 227 → 244 mg/L | 2–189 → 3–468 |
| Jaduguda · TDS | 10 → 3.0 | 114 → **254** | 12.7 → 17.6 | 2,253 → 4,428 mg/L | 5–848 → 15–2,136 |
| Jaduguda · radium | 10 → 3.0 | 0.3 → 0.6 | 9.1 → 9.1 | 23 → 23 mBq/L | 0–1 → 0–2 |
| Mid-belt · sulphate | 10 → 2.0 | 19.0 → 60.7 | 12.4 → 13.7 | 46 → 63 mg/L | 2–114 → 4–345 |
| Ranchi · sulphate | 10 → 2.0 | 8.8 → 25.3 | 12.3 → 12.7 | 31 → 31 mg/L | 1–42 → 2–172 |

Uranium roughly doubled and stayed within tens of metres (R_m ≈ 90 still dominates β·R_m); the reagents moved two to three times as far and their bands reached hundreds of metres. The published Jaduguda advisory's footprint is unchanged in kind — block intersection is done on the central contour, so the alert count did not inflate — and the P90 envelope now raises a separate `possible_reach` alert. The v5 retrain (background floor) left these unrestored 20-year values unchanged and widened the TDS P90 to 3,043 m.

## 6.6 Vertical (2.5-D) screening results [S]

At the registered site (ore top at 140 m, Layer-1 base at 20 m from the East Singhbhum profile, separation 120 m, water table 1.6 m): the dispersive pathway contributes 0.00, the advective-leakage pathway 0.60 (breakthrough fraction 0.602 at 20 years) and the wellbore base rate 0.05, for a combined index of **0.62** — band *high*, dominant pathway advective leakage — with a **duty-cycle breakthrough of 18.7 years** against a dry-season end member of 6.8 years and a wet-season end member of "not expected" (the pathway is open about 58 % of the year). Before the R11 correction the headline read 54.4 years at the mean gradient, outside its own seasonal band and understating the hazard by about 1.9×. The concentration reaching Layer 1 by dispersion is 0.0 — the index is a *pathway-existence* screen, not a concentration.

**Why no 3-D volume is presented.** Table 6.9 is the data the question turns on.

**Table 6.9 — What vertical information exists (from the pre-report audit, §4.1).**

| Quantity | Present? | Resolution | Usable for a vertical axis? |
|---|---|---|---|
| Well depth / screen interval of the chemistry wells | **No** | — | the decisive absence |
| Depth to water | yes, 9,583 readings | point, shallow phreatic | water-table surface only |
| Hydraulic head at depth | **No** | — | the vertical gradient is bracketed by the monsoon swing, not measured |
| Geological layering | yes | district (24 rows) | a 3-layer conceptual column |
| Ore depth / thickness | partly | per deposit, 60–250 m | point estimates |
| K with depth | modelled | a law | assumption |
| Contaminant concentration | model output only | — | no measured plume, no depth |

Any voxel volume rendered from this would be a picture of the erf factor in `vertical_attenuation` presented with the visual authority of a measurement. The system stays 2.5-D, draws the column to scale on the report page, and says so.

## 6.7 Vulnerability assessment [S + M]

**Measured bands [M].** With the three-determinand rule, 14 of 24 districts are *High concern*, several from wells where uranium is essentially absent (Lohardaga: 0.5 ppb uranium, 48 mg/L nitrate; Gumla: 2.1 and 53). Under the earlier uranium-only rule no district could ever have reached High concern, because the statewide maximum is 28.5 ppb against a 30 ppb limit — the public map could not show a high-concern district at all, and the resident's own page disagreed with it for a day (R15). The three Singhbhum districts band on nitrate and fluoride with uranium listed under `untested_health`; every band lists arsenic and iron there unconditionally.

**Modelled excursion and vertical bands [S].** At the Jaduguda reference pin, p_ex is 0.00 for uranium, 0.27 for sulphate and 0.96 for TDS at 20 years; the NUREG panel declares from the 12-year frame; the vertical band is *high* (§6.6). At the non-ore Ranchi pin, uranium is suppressed and the only bands drawn are for the reagents.

**Where the two meet.** The published Jaduguda screening's footprint intersects blocks of East Singhbhum whose measured band is *Low concern* on nitrate and fluoride and *Not tested* for uranium — the product shows both, labelled, and never lets the modelled result colour the measured band.

## 6.8 The alert system [M + S]

**Records on the local seed (report commit).** The measured-exceedance scan raises **53** alerts from the 2023 record: **3 critical** — Biru (Simdega, nitrate 121 mg/L, 2.7× the limit), Lowadih (Ranchi, nitrate 99 mg/L, 2.2×) and Gidhaur (Chatra, over both the nitrate and the fluoride limits) — **29 alert** (the remaining wells above a permissible or no-relaxation limit) and **21 warning** (fluoride between 1.0 and 1.5 mg/L). Before R14 the same scan matched zero rows every time it ran (it queried `uranium_ppb > 30`), and before R17 the 21 warning wells were unreachable (it selected on the permissible limit only).

**Records on the deployed database (21 September 2026, Administration screen):** 55 alerts raised; 4 residents following 7 blocks; email delivery configured that day through the Brevo relay after three connectivity findings — the hosting tier silently drops outbound port 587 (a 20-second timeout with nothing in the relay's log; port 2525 connects), the relay's login is a machine identifier rather than the account address, and the relay's IP allow-list rejected the host's changing egress address until it was opened — and one defect found while doing it: a `failed` delivery was permanent and never retried, because `pending_deliveries` excluded any pair with an existing row and the insert was `ON CONFLICT DO NOTHING` (fixed and pinned, commit `47ab713`).

**Table 6.10 — One alert per basis, as the seven-field record (values from the local seed; the modelled record from the published Jaduguda screening).**

| Field | Observed: Biru, Simdega | Modelled: Jaduguda screening, an East Singhbhum block |
|---|---|---|
| `basis` | observed | modelled |
| `driver` | nitrate 121 mg/L; limit 45 mg/L (no relaxation); 2.7× | uranium; modelled P50 footprint intersects the block; ring p_ex 0.00 at the run's horizon |
| `where` | Biru block, Simdega district; well "Biru" | block, East Singhbhum district; footprint ~9 ha |
| `tier` | **critical** (≥ 2× — project-defined rule, labelled) | **notice** (never critical: `ck_modelled_never_critical`) |
| `confidence` | laboratory result, sampled 2023 (year-only date); charge balance within ±3.2 % (consistency of construction, so not independent) | analytical P50 20.5 m; surrogate band 2.7–100 m; extrapolation: none; nearest chemistry well and its distance |
| `next_action` | re-sample; nitrate is not removed by boiling (boiling concentrates it); test for the un-analysed determinands (Fe, As, Mn); consider an alternate supply | no monitoring well lies inside the P90 reach — none exists to sample; the ring is first predicted to exceed on the indicator panel at the 12-year frame |
| `what_happened` | a government monitoring well in this block was tested and found nitrate 2.7 times the drinking-water limit | a hypothetical screening was published for a block the modelled footprint touches; no mine exists |

**Kinds that fire on nobody, reported as results.** `aquifer_pathway` adds no block at any registered site: shallow groundwater in the state's hard rock moves ~1.5 m/yr (phyllite: K 0.08 m/day, φ 0.04, i 0.0021 → 27 m in 20 years), so every block within the advective reach was already told by the footprint. `aquifer_breach_due` correctly fires on nobody: the two originally published advisories predate vertical-screening persistence, and a Potka run sits at 22 elapsed years against a 29.4-year modelled breakthrough — due in 7.4 years, reported rather than raised.

![Figure 6.4 [S] — The ISR site report for the published Jaduguda screening as a resident or officer downloads it (deployed portal, August 2026; pre-R17 extent).](figures/fig_site_report.png)

## 6.9 Data gaps, monitoring recommendation and sensitivity [M + V]

**The gap matrix, statewide [M]:** 264 blocks; **53 blocks with no monitoring well**; **83 blocks with no level station**; **55 wells never analysed for uranium**; **397 of 397 wells with a single sample**, all stale by the record's own age (2023).

**The ranking [M].** Table 6.11 is the top of the observation-based ranking re-derived from the local database on the report date. The scores sit in a narrow band (61.8–65.2 of 100) because the top blocks share the same two saturated factors; the ordering within the band is the tie-break by area. The finding is not the numbers but the geography: **every one of the top 25 blocks is in East Singhbhum, West Singhbhum, Saraikela-Kharsawan or neighbouring Khunti** — the uranium belt itself is the least-observed part of the state for the one contaminant the tool screens for. Sixteen of the 25 have no well at all; the other nine have wells that were sampled and never analysed for uranium — the cheapest gap in the list to close, because the wells and the sampling round already exist.

**Table 6.11 — Observation-based monitoring priority, top 25 of 264 blocks (weights 30 / 30 / 20 / 15 / 5, a stated policy; area is the tie-break).**

| Rank | Block | District | Score | Wells | U tests | km to nearest U-tested well | Area (km²) |
|---|---|---|---|---|---|---|---|
| 1 | Ghatshila | East Singhbhum | 65.2 | 1 | 0 | 77.7 | 345 |
| 2 | Manoharpur | West Singhbhum | 65.0 | 0 | 0 | 46.1 | 966 |
| 3 | Tonto | West Singhbhum | 65.0 | 0 | 0 | 68.2 | 633 |
| 4 | Goilkera | West Singhbhum | 65.0 | 0 | 0 | 45.5 | 577 |
| 5 | Manjhari | West Singhbhum | 65.0 | 0 | 0 | 74.4 | 319 |
| 6 | Dumaria | East Singhbhum | 65.0 | 0 | 0 | 86.0 | 318 |
| 7 | Anandpur | West Singhbhum | 65.0 | 0 | 0 | 28.8 | 317 |
| 8 | Kumardungi | West Singhbhum | 65.0 | 0 | 0 | 90.2 | 296 |
| 9 | Majhgaon | West Singhbhum | 65.0 | 0 | 0 | 103.4 | 284 |
| 10 | Boram | East Singhbhum | 65.0 | 0 | 0 | 46.5 | 264 |
| 11 | Patamda | East Singhbhum | 65.0 | 0 | 0 | 60.1 | 246 |
| 12 | Sonua | West Singhbhum | 65.0 | 0 | 0 | 44.4 | 224 |
| 13 | Gurbandha | East Singhbhum | 65.0 | 0 | 0 | 102.5 | 222 |
| 14 | Potka | East Singhbhum | 64.8 | 4 | 0 | 60.8 | 615 |
| 15 | Gudri | West Singhbhum | 63.6 | 0 | 0 | 22.7 | 472 |
| 16 | Chakradharpur | West Singhbhum | 63.2 | 1 | 0 | 36.8 | 379 |
| 17 | Kukru | Saraikela-Kharsawan | 62.8 | 0 | 0 | 21.4 | 139 |
| 18 | Hat Gamharia | West Singhbhum | 62.7 | 1 | 0 | 83.0 | 293 |
| 19 | Saraikela | Saraikela-Kharsawan | 62.3 | 1 | 0 | 28.6 | 249 |
| 20 | Musabani | East Singhbhum | 62.1 | 2 | 0 | 77.4 | 249 |
| 21 | Noamundi | West Singhbhum | 61.9 | 3 | 0 | 70.2 | 645 |
| 22 | Erki (Tamar II) | Khunti | 61.8 | 0 | 0 | 19.7 | 519 |
| 23 | Kuchai | Saraikela-Kharsawan | 61.8 | 0 | 0 | 19.7 | 389 |
| 24 | Tantnagar | West Singhbhum | 61.8 | 1 | 0 | 63.4 | 210 |
| 25 | Chaibasa | West Singhbhum | 61.8 | 1 | 0 | 48.9 | 209 |

**Global sensitivity [V].** Table 6.12 gives the Sobol total-order indices (S_T) of the three plan-view outputs to the thirteen inputs at the three reference sites; the full first-order and one-at-a-time tables are Appendix J and the figures in `ml/artifacts/sensitivity_*.png`. Group A is the registered ungrounded constants; group B the resolved hydrogeology with its Monte-Carlo ranges.

**Table 6.12 — Sobol total-order indices, top inputs per output (Saltelli N = 256; 20 yr, 8 yr operation, 3 yr sweep; `ml/artifacts/sensitivity.json`).**

| Site · species | Output | 1st | 2nd | 3rd | 4th | Share carried by group A |
|---|---|---|---|---|---|---|
| Jaduguda · U | migration | **K 0.42** | **β 0.21** | gradient 0.16 | ω 0.10 | 0.32 |
| Jaduguda · U | footprint | SOURCE_BV_REF 0.27 | SOURCE_BV_GAIN 0.22 | β 0.16 | gradient 0.15 | 0.64 |
| Jaduguda · U | ring concentration | K 0.53 | β 0.45 | gradient 0.33 | ω 0.21 | 0.37 |
| Jaduguda · SO₄ | migration | K 0.39 | β 0.24 | Kd 0.17 | gradient 0.13 | 0.28 |
| Jaduguda · SO₄ | footprint | K 0.42 | β 0.21 | gradient 0.17 | Kd 0.15 | 0.34 |
| Jaduguda · SO₄ | ring concentration | K 0.71 | gradient 0.33 | β 0.32 | Kd 0.31 | 0.22 |
| Belt · U | migration | **β 0.29** | K 0.26 | ω 0.18 | gradient 0.14 | 0.49 |
| Belt · U | footprint | SOURCE_BV_GAIN 0.55 | SOURCE_BV_REF 0.37 | gradient 0.07 | K 0.06 | 0.84 |
| Belt · U | ring concentration | K 0.65 | Kd 0.27 | β 0.27 | — | — |
| Belt · SO₄ | migration | β 0.34 | K 0.25 | Kd 0.23 | — | — |
| Ranchi · U | all three | **degenerate** — the source is suppressed at a non-ore pin; the output is constant over the whole design and the indices are undefined, reported as such | | | | |
| Ranchi · SO₄ | footprint | C₀ 0.78 | SOURCE_BV_GAIN 0.25 | SOURCE_BV_REF 0.10 | — | — |

The pattern: hydraulic conductivity first, then β, then the gradient and Kd for the transport outputs; the leach-disc growth constants govern the footprint area (which is the disc); the fracture aperture, D_e and — except for belt uranium — ω contribute approximately nothing at 20 years. Of the parameters that decide the extent, K is a measured polygon value depth-decayed by a law, and β is derived from typical porosities; **neither is a local measurement at ore depth in the shear zone**. The registered ungrounded constants carry 22–49 % of the migration variance, almost all of it β.

![Figure 6.5 [V] — Sobol total-order indices for uranium at the Jaduguda deposit pin, three outputs (`ml/artifacts/sensitivity_jaduguda_deposit_uranium.png`).](figures/fig_sens_jaduguda_uranium.png)

![Figure 6.6 [V] — The same for uranium at the belt pin, where β overtakes K for migration (`ml/artifacts/sensitivity_belt_point_uranium.png`).](figures/fig_sens_belt_uranium.png)

## 6.10 The prototype system

**Screens per role (final build).** All 22 screens exist; each role sees a filtered set. `admin`: everything, including Administration (accounts, dataset sync and restore points, model operations, the alert scans and delivery panel, tier counts), Datasets, Ingest and Audit. `regulator`: the review queue and decisions, plus the console, report, compare, scenarios, publications and data screens. `analyst`: console, report, compare, scenarios, publications (propose), field data, water quality, groundwater, data & gaps, network plan, methods. `field_officer`: field data (submit, withdraw), plus reads. `citizen`: front page, my area, the citizen map (tap anywhere), alerts, published screenings, methods — nothing with a coordinate or a model internal.

**Authorization sweep.** The generated matrix covers **152 endpoints × 5 roles** (`docs/roles.md`); the test that regenerates it fails on drift. Row-level security is verified on the live connection as `jaldrishti_app` (no superuser, no bypass); the `alerts` table carries SELECT, INSERT and UPDATE policies; the audit log carries no UPDATE or DELETE policy for any role. The security-hardening tests measure rather than assert: 10 logins accepted, then 429s.

**The publication workflow, end to end.** An analyst runs the engine at a registered site and saves the run (runs are ephemeral by default; saving is a deliberate act); proposes a screening from the completed run; the single admin decides; publication raises `published_screening` alerts for every block the central footprint touches and `possible_reach` for the P90 envelope, in its own session under the system context; delivery emails each subscriber; the resident sees the advisory, its operating parameters, the modelled spread and whether shallow water was expected to be reached — but never the coordinate. A withdrawn advisory is withdrawn everywhere, including the email channel.

![Figure 6.7 — The deployed front page; every figure is read live from the database (August 2026).](figures/fig_front_page.png)

## 6.11 Performance and deployment

| Measure | Value | Basis |
|---|---|---|
| Analytical engine, one evaluation with the 48-draw Monte Carlo | ~0.2 s locally; ~4 s on the Render free tier | `PROJECT_FREEZE.md` §0; the lifecycle endpoint issues 8–15 evaluations per request and was split per species after a 48-evaluation request was dropped by the gateway in production |
| Bake (900 scenarios × 48 draws) | ~1.5–2 h on the development machine | 21 Sep 2026 run: 11:52 → 13:26 including train, SHAP, the 120-scenario batch, gates, sensitivity and audit |
| Surrogate training | 202 s | v5 trainer log |
| Sensitivity (N = 256, 3 sites × 2 species) | ~2.5 min (≈ 22,000 evaluations) | v5 pipeline log |
| Engine test suite | 373 tests, 32–113 s | report commit |
| Backend test suite (real PostGIS) | 522 tests, 10–17 min | report commit |
| Deployed API cold start | 53 s (free tier sleeps) | probe, 20 Sep 2026 |
| Repository | 173 commits; 26 migrations; 152 endpoints; 22 screens | report commit |

The deployed API runs whichever commit was last deployed; `docs/PROJECT_FREEZE.md` §8 lists the steps that bring the deployment to the report commit (migrate to `0026`, deploy the v5 artifacts, rebuild alert explanations once, re-run one simulation per published site so the advisory has frames).
