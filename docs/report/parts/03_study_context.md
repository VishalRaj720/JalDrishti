\newpage

# 3. Study context and data sources

## 3.1 Problem context — the hypothetical ISR scenario

Everything modelled in this report is conditional on a premise that must be stated first: **no ISR uranium mine operates in Jharkhand, and none is planned.** The seven UCIL mines of the Singhbhum Shear Zone are conventional operations in fractured metamorphic rock; every commercial ISR operation on Earth is in unconsolidated or weakly consolidated sandstone, and commercial ISR is not physically plausible in schist-hosted uraninite ore. The project's fidelity matrix records this as its first-ranked disconnect (`ml_pipeline/JHARKHAND_FIDELITY_MATRIX.md`, row 3.1), and the user interface was retitled in August 2026 from a mining-feasibility framing to "ISR Contaminant Excursion Screening — not a mining feasibility tool". Every modelled output therefore means *"if ISR-strength lixiviant entered this aquifer at this point"* — a contamination question, never a feasibility judgement, a plan or a permit.

Two consequences follow for how the Texas ISR records are used. They supply what a Jharkhand record cannot: the **source signature** (what an alkaline lixiviant does to groundwater chemistry at the end of mining — uranium, sulphate, TDS, chloride) and the **restoration behaviour** (what fraction of the end-of-mining concentration remains after a real restoration programme, and how long such programmes run). They are *not* used for hydrogeology: every hydraulic property, flow direction, fracture orientation, layer depth and background concentration in the engine is Jharkhand's own (§3.3). The transfer is made in dimensionless form — Péclet number, retardation factor, pore volumes, containment efficiency — so that the physics travels between regions even though the absolute values do not (§4.2–§4.3).

A second premise: **no field validation is possible.** No ISR plume has ever been measured in Jharkhand, and the Texas records are per-mine point chemistry, not plume maps. The engine is benchmarked against exact analytical solutions (§6.2) and its surrogate is validated against the engine; neither has been compared with a real plume, because none exists to compare with. The conformal bands quantify parameter uncertainty inside the model's assumptions; nothing in the system quantifies structural model error, and §5 says so.

## 3.2 Geographic and environmental context

**Terrain and aquifers.** Jharkhand (79,714 km²) is dominated by Precambrian crystalline rock — the Chotanagpur Gneissic Complex in the north and centre, the Singhbhum craton and its shear zone in the south-east — with Gondwana sandstones in the Damodar and other coal basins, Rajmahal basalts in the east, laterite caps and alluvium along the major rivers. The CGWB aquifer polygons used here classify the state into 12 lithologies, of which eight (schist, gneiss, granite, quartzite, charnockite, Basement Gneissic Complex, basalt, intrusive) are treated as *fractured* aquifers and four (limestone, sandstone, laterite, alluvium) as *porous* (`config/parameters.py`, `LITHOLOGY_REGIME`). The Basement Gneissic Complex alone covers 48,047 km², more than half the state — which is why "alert every block on the same aquifer" was rejected as a notification rule (§4.8).

**The vertical column.** The NAQUIM reports for 21 districts, the CGWB district profile for East Singhbhum and regional estimates for the remaining three give a three-layer column per district (`Datasets/naquim_reference/naquim_vertical.csv`): the base of the weathered shallow aquifer (Layer 1) at 13–22 m; productive fractures from about 8–30 m down to a *fracture-death depth* that ranges from 90 m (Khunti) and 100 m (Godda) through 121 m (Ranchi) and 181 m (Dhanbad) to 258 m (East Singhbhum); and the deeper aquifer recorded as confined in the three Singhbhum districts and semi-confined elsewhere. Ore in the Singhbhum deposits lies at 60–250 m (Banduhurang open-pit at the shallow end, Jaduguda's deeper levels at the other) — i.e. inside or at the base of the productive fractured zone, and 100–200 m below the drinking-water aquifer. That separation is what the vertical screening of §4.5 evaluates.

**Regional flow.** The plateau is a divergence: the Subarnarekha drains the south-east past the uranium belt, the Damodar the north-east, the North Koel and Son the north-west. The project's flow field (§4.2) is built from 398 CGWB level stations on a 5 km grid; its hydraulic gradient has a statewide median of 0.0030 (10th–90th percentile 0.0012–0.0076), and at the Jaduguda reference pin resolves to 0.00205 (`ml_pipeline/data_prep/artifacts/flow_field_meta.json`; §6.4).

**Monsoon.** Groundwater in the shallow aquifer is recharged by the June–September monsoon, and the CGWB campaign record shows it: bucketed into the four campaigns, the statewide median depth to water is 7.20 m in May and 3.22 m in August (5.25 m in January, 3.78 m in November), a swing of 3.9 m; the per-station median seasonal swing is 2.38 m and at the Jaduguda pin 4.7 m. The project measured (August 2026) what this does to the *horizontal* gradient — very little: the direction rotates by a median 2.5° (90th percentile 11°, no cell reverses) and the magnitude ratio is 1.05 (p50) — and to the *vertical* gradient across the ore-to-shallow separation — a great deal (§4.5, §6.6). The monsoon is represented statistically (a widened Monte-Carlo gradient range) in the horizontal solve and explicitly (a duty-cycle upward gradient) in the vertical screening; there is no transient recharge model.

## 3.3 Dataset sources

Table 3.1 lists every dataset the delivered system reads, with provider, extent, use and location in the repository. Row counts are those pinned by `ml_pipeline/validation/end_to_end_audit.py` and by the backend seed, re-checked on the report commit. The survey from which these were selected (`docs/local/datasets_source.md`) catalogued twenty candidate sources across five categories; the selection rule was local-first (CGWB and GSI over global grids), provenance over convenience, and refusal to import anything that would make a claim the engine could not support (§3.5 and §7.1 give the rejections).

**Table 3.1 — Datasets read by the delivered system.**

| # | Dataset | Provider / citation | Rows / extent | Used for | Repository path |
|---|---|---|---|---|---|
| 1 | Groundwater chemistry, 2023 | CGWB [39] | 397 wells, 24 districts, 20 determinands; **one sample per well**; U analysed at 342; Fe, As 0 % | IS 10500 assessment, citizen band, measured alerts, engine background concentrations, hydrochemical QA, monitoring-gap ranking | `Datasets/waterQuality_jharkhand.csv` |
| 2 | Groundwater chemistry, 2000–2021 | CGWB via National Water Data Portal, NWIC [41] | 1,632 analyses, 366 stations, 2000–2021; pH/EC 100 %, HCO₃/Cl/Ca/Mg/Na 92 %, hardness 81 %, SO₄ 46 %; **no F, NO₃, Fe, As, Mn**; 2 uranium values | per-station baseline mean/sd and Theil–Sen trend of the general chemistry; read-only | `Datasets/cgwb_gwq_chemical_jharkhand_2000_2021.csv` (+ physical file: temperature, turbidity) |
| 3 | Groundwater levels, 2013–2021 | CGWB / India-WRIS [40] | 9,583 readings, 398 stations, all months (campaign-bucketed) | flow field (head = DEM − depth), seasonal amplitude, level trends | `Datasets/cgwb_waterlevel_jharkhand.csv` |
| 4 | Aquifer polygons | CGWB / NAQUIM-derived | 24 polygons statewide: lithology, K, specific yield, thickness, transmissivity | regime, K, porosities (with literature fill where a field is "-") | `Datasets/Aquifers_Jharkhand.geojson` |
| 5 | District and sub-district boundaries | Government of India | 24 districts; 264 blocks used for ranking (275 sub-districts loaded) | block resolution, alert targeting, public map | `Datasets/*Boundary_JH.geojson` |
| 6 | Lineaments | GSI / NRSC Bhuvan [42] | 1,889 features; 1,826 structural segments used (799 joint/fracture, 39 dyke, 15 shear zone, 9 fault, 8 fold axis) | strike field → transverse anisotropy and display azimuth | `Datasets/jharkhand_lineaments.geojson` |
| 7 | Perennial rivers | HydroRIVERS v1.0, Lehner & Grill [45], clipped | 4,577 reaches with discharge | receptor distance; plume–river crossing test | `Datasets/jharkhand_rivers.geojson` |
| 8 | NAQUIM vertical table | CGWB NAQUIM district reports [37] + E-Singhbhum profile [38]; 3 regional estimates | 24 rows: Layer-1 base, fracture range, confined flag, confidence | vertical screening; per-district depth-decay length | `Datasets/naquim_reference/naquim_vertical.csv` |
| 9 | Uranium deposits | UCIL deposit outlines (project-digitised) + IAEA UDEPO grades [43] | 7 deposit polygons + a belt envelope; 9 UDEPO Indian deposits | ore-zone gating of the uranium source term; grade scaling; per-deposit ore depth | `Datasets/Jharkhand Ore/`, `Datasets/udepo_uranium_deposits.xlsx` |
| 10 | Texas ISR groundwater quality | USGS data release [15] (Dataset 1) | `TX_ISR_Final.xlsx`: Baseline 86, End-of-Mining 9, Final Post-restoration 86 rows after parsing | source signature (C₀ envelope), paired restoration residuals, porosity | `Datasets/Real_dataset/Dataset_1/` |
| 11 | Texas ISR operations | USGS data release [16] (Dataset 2) | `Restoration.csv` (13 production areas), `TexasISROperations.csv`, `AquiferExemptions.csv`, `MinePermits.csv`, `DisposalVolumes.csv`, `AreaInformation.csv`, `CitationsSources.csv` | restoration reference duration (median 5.0 yr), operating ranges | `Datasets/Real_dataset/Dataset 2/` |
| 12 | Digital elevation model | Copernicus GLO-30 [44] | statewide, 30 m (703 MB, not in git) | flow-field bake only (station head, DEM fallback) | regenerable via `fetch_data/` |
| 13 | Synthetic training set | this project (v5 bake) | 900 scenarios × 5 horizons × 4 species = 18,000 rows; 48 MC draws each; SHA-256 `8ac61f2d…` in the model card | surrogate training; regenerable by seed 42 | `ml_pipeline/outputs/` (not in git) |

Three datasets that were loaded into the database in early 2026 but do not feed the delivered system are noted for completeness: the monitoring-station table of December 2025 (superseded by the level record), the synthetic water-sample rows of March 2026 (flagged `synthetic = TRUE`, later dropped with the `DataGen_ModelMVP` pipeline), and the `Datasets/phase1_sources/` archive of PDFs (EPA and IAEA Kd compendia, the Sethy and Giri papers, the NAQUIM depth evidence) which are literature, not data.

## 3.4 Dataset characteristics

**The measured chemistry record [M].** Table 3.2 gives, per determinand, the count of analysed wells, the minimum, median and maximum, and the number of wells above the IS 10500:2012 acceptable and permissible limits, re-derived from `waterQuality_jharkhand.csv` on the report date (the full table with all columns is Appendix A). Three things stand out. Uranium is below its 30 ppb limit at every one of the 342 wells where it was analysed (maximum 28.5 ppb, median 0.78 ppb); nitrate exceeds its 45 mg/L limit — a "no relaxation" limit — at 22 wells, peaking at 121 mg/L; fluoride exceeds the 1.0 mg/L acceptable limit at 32 wells and the 1.5 mg/L permissible limit at 11. Hardness, calcium and magnesium exceed their acceptable limits at a third to two-thirds of wells, which is hard-rock aquifer chemistry rather than contamination and is reported separately from the health determinands for exactly that reason (§4.7). The carbonate column is zero at all 397 wells, a reporting convention rather than a measurement. The three Singhbhum districts — East Singhbhum (28 wells), Saraikela-Kharsawan (11) and West Singhbhum (16) — were sampled but not analysed for uranium: the uranium belt itself has no uranium result in the record.

**Table 3.2 — Descriptive statistics of the 2023 CGWB chemistry record [M] (397 wells; limits are IS 10500:2012 acceptable / permissible; uranium per WHO 30 µg/L).**

| Determinand | n analysed | Min | Median | Max | Acceptable / permissible limit | n above acceptable | n above permissible |
|---|---|---|---|---|---|---|---|
| pH | 397 | 6.53 | 7.80 | 8.28 | 6.5–8.5 (no relaxation) | 0 | 0 |
| EC (µS/cm) | 393 | 153 | 766 | 2,780 | — | — | — |
| HCO₃ (mg/L) | 393 | 18 | 250 | 1,050 | — | — | — |
| Cl (mg/L) | 397 | 7 | 78 | 430 | 250 / 1,000 | 9 | 0 |
| F (mg/L) | 397 | 0 | 0.42 | 1.91 | 1.0 / 1.5 | **32** | **11** |
| SO₄ (mg/L) | 393 | 2 | 38 | 234 | 200 / 400 | 2 | 0 |
| NO₃ (mg/L) | 393 | 0 | 18 | 121 | 45 (no relaxation) | **22** | **22** |
| Total hardness (mg/L) | 393 | 50 | 260 | 1,060 | 200 / 600 | 264 | 11 |
| Ca (mg/L) | 397 | 6 | 60 | 312 | 75 / 200 | 135 | 5 |
| Mg (mg/L) | 397 | 4 | 26 | 130 | 30 / 100 | 137 | 4 |
| Na (mg/L) | 397 | 1 | 42 | 423 | — | — | — |
| K (mg/L) | 397 | 0 | 6 | 55 | — | — | — |
| PO₄ (mg/L) | 393 | 0 | 0 | 1.3 | — | — | — |
| Fe (ppm) | **0** | — | — | — | 1.0 (no relaxation) | not tested | not tested |
| As (ppb) | **0** | — | — | — | 10 / 50 | not tested | not tested |
| U (ppb) | 342 | 0 | 0.78 | 28.5 | 30 (no relaxation) | **0** | **0** |
| CO₃ (mg/L) | 397 | 0 | 0 | 0 | — | (all zero) | — |

Wells above any health limit at the alert-triggering bar (U > 30 ppb, NO₃ > 45 mg/L or F > 1.5 mg/L): **32** (22 nitrate, 11 fluoride, one well on both). Wells with fluoride between 1.0 and 1.5 mg/L (the warning band, §4.8): **21**. Together these are the 53 measured alerts the deployed scan raises (§6.8).

**The level record [M].** 9,583 readings at 398 stations in 24 districts, 2013–2021, taken in all twelve months but concentrated in the four CGWB campaigns. Bucketed as January (Dec–Feb), May (Mar–May), August (Jun–Aug) and November (Sep–Nov), the statewide campaign medians of depth to water are 5.25, 7.20, 3.22 and 3.78 m. After the Theil–Sen/Mann–Kendall screening of §4.9, 331 stations have a testable record and 84 do not (fewer than 8 readings or under 3 years).

**The 2000–2021 chemistry record [M].** Downloaded from the National Water Data Portal on 20 September 2026 after a profiling decision (§7.1): 1,632 analyses at 366 stations, of which 244 can be matched to the platform's wells with two or more sampling years. It carries the general chemistry (pH, EC, TDS, carbonate, bicarbonate, alkalinity, chloride, nitrate-N at low coverage, sulphate at 46 %, major cations, silica) and *none* of the health determinands the platform bands or alerts on. Its use is therefore restricted to per-station baselines and trends of the excursion-indicator chemistry (§4.9).

**Spatial density.** 397 chemistry wells over 79,714 km² is one well per ~200 km²; 264 blocks have a median of one well each. This is far too sparse to interpolate a concentration field, and the project never does — the engine's background concentration at a pin is the nearest well's value, reported with the distance to that well as part of the data-confidence block.

**The Texas source signature [M].** From the End-of-Mining sheet, per-mine means over nine production-area measurements at seven mines give uranium 9,027–41,595 ppb, sulphate 274–2,976 mg/L and TDS in the same proportion (`config/parameters.py`, `TRAINED_SPECIES_SUPPORT`); the full observed per-mine range is served as the envelope after the second review round rejected a P25–P95 window that narrowed the evidence (`docs/local/audit-record/review2.md` V-2). Paired per-mine restoration ratios (Final Post-restoration / End-of-Mining, median over the seven common mines) are 0.060 for uranium, 0.138 for sulphate, 0.337 for TDS and 0.531 for chloride; the per-mine uranium ratios span 0.023–0.248, an order of magnitude the single served value used to hide. The Texas restoration durations across 13 production areas have a median of 5.0 years (IQR 3.8–6.5; median 18.6 pore volumes), which anchors the restoration draw-down law.

## 3.5 Data quality

The data-quality findings are results in their own right (O2), and are collected here.

1. **One sample per well, in one year.** The 2023 record has no temporal replicates: no trend, no per-well variance, no upper control limit of the mean-plus-five-standard-deviations kind that NUREG-1569 prefers. Substituting the regional spatial spread was tested and rejected — sd(TDS) = 286.5 mg/L gives a control limit of 1,965 mg/L, next to the permissible limit itself (`docs/LIMITATIONS.md` §3). The 2000–2021 record partly closes this for the general chemistry only.
2. **No well depths.** No chemistry sample carries a depth or screen interval; all vertical information is at the district scale. This is the decisive absence behind the 2.5-D decision (§4.5, §7).
3. **Fe, As, Mn never measured.** Iron and arsenic are 0 % populated in the 2023 file; manganese has no column; the 2000–2021 file has none of the three. The proposal named all three. They are reported as `not_tested` on every well rather than passed over, and the alert scanner already reads them so that the first laboratory result to arrive raises an alert without anyone having to remember to add it.
4. **Sampled ≠ analysed for uranium.** 55 wells in the three Singhbhum districts have samples and no uranium result. Both citizen surfaces distinguish *never sampled* from *not tested for uranium*, and neither ever reads as clean.
5. **The 2023 charge balance is a consistency of construction.** The R17 hydrochemical QA (§4.9) found that 393 of 393 computable analyses balance within ±3.2 % (median |CBE| 0.56 %) — a result no routine laboratory batch produces — and that sodium is reproduced from the other ions to a median 1.6 mg/L (65 % within 2 mg/L) and hardness from Ca and Mg within 5 % for 99 % of samples. Sodium was computed by difference; the charge balance is therefore not an independent check on that file, and a count of zero suspect analyses is not evidence of laboratory quality. The independent ion-sum/EC check (median ratio 0.70) passes. On the 2000–2021 file the balance is real: 127 of 753 computable analyses are suspect at the 10 % criterion, and the flag travels with each sample without excluding it.
6. **Year-only sample dates.** The 2023 samples carry a year and no date; `sampled_at` is set to 1 January of that year and is labelled as such.
7. **A demo field observation is in the tracked ore dataset.** During the R11 test of the field-observation workflow (19 August 2026) a submission named `jharia` ("lots of Uranium") was approved and synced into `Datasets/Jharkhand Ore/jharkhand_uranium_deposits.csv` as an *added* record with a 400 m radius at 23.39° N 86.28° E, near Dhanbad, where no uranium deposit is known. The R11 fix `0533caa` stopped the belt envelope spreading from it, but the record itself remains, and on the report commit the engine resolves a *deposit-tier* uranium source term (25,300 ppb) at that point. **Found during the writing of this report; recorded here as a data-hygiene defect to be removed through the dataset manager before any further use, and listed in §8 and Appendix H.**

## 3.6 The scenario, precisely

Every modelled result in §6 is conditional on the operating scenario in Table 3.3. Each value carries its provenance; the twelve constants the assumption register names as ungrounded are marked ⚑ and appear in full in Appendix E. Where the console or a registered site overrides a default (the registered Jaduguda site uses Q_in = 1,500 m³/day, W = 300 m, ore depth 150 m, ore thickness 20 m, ring 100 m), the override is stated with the result.

**Table 3.3 — The reference ISR scenario and the transport parameters that govern it.**

| Quantity | Reference value | Trained / allowed range | Provenance |
|---|---|---|---|
| Lixiviant | alkaline (carbonate + oxidant) | — | the only ISR chemistry with public records [12], [15] |
| Uranium source C₀ | 9,027–41,595 ppb envelope; grade-scaled per deposit (Jaduguda deposit pin 15,180 ppb; belt ×0.30 with a 3 km taper; non-ore: trace, suppressed) | as envelope | Texas End-of-Mining per-mine means, n = 9 at 7 mines [15]; UDEPO grade class midpoint / 0.05 % U [43] |
| Sulphate C₀ / TDS C₀ | 1,624.5 mg/L / 3,655.5 mg/L (Texas per-mine means) | 274–2,976 / trained support | [15] |
| Radium-226 C₀ | 1,706 mBq/L (measured maximum, served as the conservative value; GM 371.3) | 23–1,706 | Jaduguda mine-water effluent [22] |
| Background | nearest CGWB well (U median 0.78 ppb; SO₄ 38; TDS from EC × 0.64; Ra 23 mBq/L) | per well | [39]; Ra regional value [24] |
| Injection rate Q_in | 2,500 m³/day (console default); 1,500 at the registered site | 200–8,000 | Texas operations [16] |
| Bleed (net extraction) | 2 % of Q_in | 0–10 % (Q_net 0–400 m³/day) | ISR practice 0.5–3 % [12] |
| Wellfield width W | 300 m (diameter of the circular pattern footprint) | 100–800 m | scenario |
| Operation years | 8 (a multi-wellfield mine unit compressed onto one footprint) | 1–20 | scenario; a single wellfield runs 1–3 yr |
| Restoration sweep | 0 by default; reference 5.0 yr | 0–10 trained; 0–30 served (flagged beyond 10) | Texas median duration [16] |
| Evaluation horizon | 20 yr | 0–20 trained; 0–50 served (flagged beyond 20) | EPA ≥ 30 yr monitoring [20] |
| Monitoring ring | 100 m beyond the wellfield edge | 75–180 m | NUREG-1569 §5.7.8.3 [12] |
| Hydraulic conductivity K | polygon value, blended across contacts, depth-decayed: 0.563 m/day at Jaduguda (T = 370 m²/day over 150 m at the shear zone) | fractured 0.044–10.6; porous 0.096–29.7 | CGWB polygons; E-Singhbhum NAQUIM/profile [38]; K(z) law calibrated per district |
| Gradient i | flow field: 0.00205 at Jaduguda; statewide median 0.0030 | 0.0005–0.02 | 398 CGWB stations + GLO-30 [40], [44] |
| Mobile / total porosity | fractured 0.005–0.010 / 0.01–0.05 (Jaduguda 0.0075 / 0.03) | fractured φ_m 0.006–0.025 | Freeze & Cherry [1]; polygon specific yield where present |
| Dual-porosity capacity ratio β ⚑ | derived: (n_total − φ_m)/φ_m = 3.0 at Jaduguda; 1.0–4.0 across lithologies | prior log-U[0.3, 20]; MC band ×4 | definition; prior and band are foreign-analogue judgements |
| Matrix transfer rate ω ⚑ | 10⁻³ /day | pinned | generic literature |
| Fracture aperture ⚑ / D_e ⚑ | 250 µm (100–500 sampled) / 5×10⁻⁶ m²/day (not sampled) | — | [5], [6] |
| Kd (L/kg) | U fractured 0.3–1.0–3.0, porous 0.5–2.5–8.0; SO₄ 0–0.05–0.3; TDS 0; Ra per regime from [47] | triangular, MC-sampled | [46]–[49] |
| Dispersivity | α_L = 0.83 (log₁₀ L)^2.414; α_T/α_L = 0.02 fractured (0.01–0.10 from strike variance), 0.10 porous | — | [9], [8] |
| Uranium attenuation k | log-triangular (0.05, 0.20, 0.70) /yr; mode by ore zone 0.35 / 0.28 / 0.12 | 0–0.70 | [18]; mineralogy tilt |
| Leach-disc growth ⚑ | gain 0.40, reference 2 bulk volumes | — | scenario |
| Vertical: Kv/Kh ⚑, upward gradient ⚑, wellbore probability ⚑ | 0.03 (fractured) / 0.008 (porous); 0.005; 0.05 | — | scenario; NUREG/CR-6733 context [13] |
| Attribution floor ⚑ | 10 % of the limit | — | modelling policy |
| Excursion control limit ⚑ | baseline × 1.20, bracketed | — | NUREG-1569 "simple percentage" rule [12] |
| Thresholds | U 30 ppb; SO₄ 400 mg/L; TDS 2,000 mg/L; Ra 1,000 mBq/L (WHO); Cl, NO₃, F, hardness per IS 10500 | — | [25], [26] |
