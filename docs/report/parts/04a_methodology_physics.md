\newpage

# 4. Methodology

The methodology is presented physics-first. The transport engine (§4.5) produces every label the surrogate (§4.6) is trained on, so the engine is the authority and the order of presentation says so; presenting the machine learning first would invite the reading that the surrogate "predicts reality", which it does not.

## 4.1 Overall system architecture

Figure 4.1 shows the delivered system as five layers and the data flow between them; Figure 4.2 the deployed topology. Three repository components implement it: `ml_pipeline/` (the engine, the synthetic-data factory, the surrogate and the engine's own diagnostic dashboard), `backend/` (the FastAPI service, PostgreSQL/PostGIS, the assessment, alert and data-gap services) and `frontend/portal/` (the React/TypeScript portal). The backend imports the engine's FastAPI application **in-process** through an ASGI transport rather than calling a separate service (`backend/app/services/ml_pipeline_adapter.py`): the adapter is the single seam at which the engine would become a network service, and it enforces an allow-list so that no measured chemistry can be passed into a model whose conformal calibration never saw it.

```
Figure 4.1 — Data flow through the delivered system.

  DATA LAYER ......... CGWB chemistry 2023 & 2000-2021 | CGWB levels 2013-21 | aquifer
                       polygons | NAQUIM layers | GSI lineaments | UDEPO grades |
                       HydroRIVERS | GLO-30 DEM | USGS Texas ISR records
        |  preprocessing (4.2): parse, resolve to blocks, bake flow/strike/river fields,
        |  Texas source signature & paired residuals
        v
  PHYSICS ENGINE ..... resolve_inputs(pin) -> feature row (4.3) -> Domenico/Ogata-Banks
  (ml_pipeline/)       plan solve + E1 disc + dual porosity + Tang + restoration wave +
                       attenuation (4.5) -> metrics, contours, NUREG excursion panel,
                       2.5-D vertical screening, 48-draw Monte Carlo
        |                                  ^
        |  900 scenarios x 5 horizons x 4 species = 18,000 physics-labelled rows
        v                                  |
  SURROGATE .......... XGBoost P10/P50/P90 heads + P_ex head, monotone constraints,
  (ml_pipeline/ml)     Mondrian split-conformal calibration (4.6) -> calibrated bands,
                       extrapolation flags, drift monitor
        |
        v
  DECISION LAYER ..... IS 10500 assessment & citizen band (4.7) | alert kinds, tiers,
  (backend/)           seven-field record, delivery ledger, scheduler (4.8) |
                       monitoring-gap ranking, hydrochemical QA, sensitivity (4.9)
        |
        v
  API + PORTAL ....... FastAPI, JWT + 5 roles, Postgres RLS, audit log (4.11) ->
                       22-screen portal: console, report, publications, alerts,
                       my area, data & gaps, network plan, administration
        |
        v
  ACTION ............. advisory published -> block alerts -> email -> acknowledgement;
                       field observation submitted -> regulator review -> dataset sync
```

```
Figure 4.2 — Deployed topology (single-origin, Option A of docs/DEPLOYMENT.md).

  Browser --> Cloudflare Worker (portal static build; proxies /api/* in code)
                    |
                    v
             Render web service (FastAPI + in-process ml_pipeline engine + v5
             artifacts; free tier: sleeps, ~53 s cold start; in-process
             scheduler for the measured scan and email delivery)
                    |
                    v
             Neon PostgreSQL 16 + PostGIS
             two roles: owner (migrations only) and jaldrishti_app
             (NOSUPERUSER, NOBYPASSRLS, DML only) -> row-level security in force
                    |
             SMTP relay (Brevo, port 2525) for alert email
```

## 4.2 Data preprocessing

**Chemistry (2023).** The CGWB table is parsed with `-` treated as missing; TDS is derived from EC where absent (TDS = 0.64 × EC, the mixed-groundwater factor [35]; the February 2026 ingest used 0.65, later aligned); each well is resolved to a block by `ST_Contains` with a nearest-block fallback for wells on a boundary; ingest is idempotent by file SHA-256; every row carries a `record_source` (original or added from an approved observation). The year-only date is set to 1 January and flagged.

**Chemistry (2000–2021).** Parsed from the NWDP CSV; station identity is matched to the platform's wells by name and coordinate proximity; units harmonised; the charge-balance QA of §4.9 doubles as its filter; per-station baseline mean and standard deviation are computed where two or more sampling years exist and a Theil–Sen trend where four or more analyses over three or more years exist.

**Levels → flow field (D1).** Each reading becomes a head, `h = DEM_elevation(station) − depth_to_water`. Readings are bucketed into the four CGWB campaigns (Dec–Feb, Mar–May, Jun–Aug, Sep–Nov), averaged per station per season, and the annual mean is the mean of the four season means so that the over-sampled January campaign does not dominate. On a 5 km grid (82 × 97 cells; 3,247 inside the state) each cell takes a distance-weighted least-squares plane `h ≈ aE + bN + c` through stations within 25 km (Gaussian weight scale 12 km, minimum five stations); the gradient vector is −(a, b), so the flow azimuth and the gradient magnitude come out of vector arithmetic and angles are never averaged. 2,416 cells are station-fitted (median weighted R² = 0.734); 831 sparse cells take direction from a 10 km-smoothed DEM and magnitude from half the topographic slope, flagged `source = 0`. The seasonal amplitude of the fitted gradient magnitude across the four seasons feeds the Monte-Carlo widening. Artefact: `flow_field.npz` (Figure 4.3).

![Figure 4.3 — The baked groundwater flow field: 5 km cells, arrows down-gradient, station-fitted cells and DEM-fallback cells distinguished; 398 CGWB stations [40], GLO-30 DEM [44]. Source: `ml_pipeline/data_prep/artifacts/flow_field.png`.](figures/fig_flow_field.png)

**Lineaments → strike field (D2/E1).** 1,826 structural segments are gridded on the same 5 km lattice (radius 30 km, minimum 20 segments): the mean strike uses doubled-angle axial statistics, `R̄ = |mean(e^{2iθ})|` [71], and the circular variance `V = 1 − R̄` measures alignment (statewide V = 0.676; per-cell p10–p90 0.36–0.78; mean strike 79.5°). V sets the transverse-to-longitudinal dispersivity ratio, and the display azimuth is rotated toward the strike by a transmissivity-tensor argument (§4.4). Artefact: `strike_field.npz` (Figure 4.4).

![Figure 4.4 — The fracture-strike field from 1,826 GSI–NRSC lineament segments: mean strike and circular variance per 5 km cell; lineaments from the GSI–NRSC 1:50,000 layer [42]. Source: `ml_pipeline/data_prep/artifacts/strike_field.png`.](figures/fig_strike_field.png)

**NAQUIM → layer table.** An automated keyword scan of the 22 NAQUIM PDFs (7 July 2026) extracted 410 evidence snippets, from the 18 that yielded matches, into `naquim_depth_evidence.md`, and the layer table of §3.2 was built from them by hand with a per-row confidence and page citation.

**Texas → source signature and residuals.** The three sheets of `TX_ISR_Final.xlsx` are parsed with their header rows located and their unit rows, footnotes and repeated headers rejected by rule (a pinned row-count assertion guards against the parser drifting — review2 V-4); detection-limit strings (`<.001`) and uncertainty notation (`1044±5`) are handled; one pH data-entry error (795) was corrected. Per-mine End-of-Mining means give the C₀ envelope; the paired per-mine ratio of Final-Post-restoration to End-of-Mining medians gives the restoration residual per species (§3.4). The 13 restoration durations in `Restoration.csv` give the 5.0-year reference sweep.

**Boundaries, ore, rivers.** District and sub-district boundaries were found in July 2026 to have been stored with latitude and longitude transposed since February; migration `0011` fixed the data and the loader. The seven deposit outlines were digitised by the project from published positions (two were corrected in July 2026 against independent coordinates); the belt envelope is the deposits' convex hull with a 3.5 km buffer, explicitly labelled as not a surveyed boundary. HydroRIVERS is clipped to the state and rasterised into a distance-to-perennial-river field with reach discharge.

## 4.3 Feature engineering

`build_feature_row` (`ml_pipeline/data_prep/feature_engineering.py`) turns a resolved operating point into the 40-feature row the surrogate is trained and served on. The same function is called by the synthetic generator and by the live server — the *train == serve* invariant that the project's own history (three silent divergences) made a design rule. Table 4.1 groups the features; the full list is in the model card.

**Table 4.1 — The 40 model features.**

| Group | Features | Why they exist |
|---|---|---|
| Regime | `regime_is_fractured` | selects the transport branch (§4.4) |
| Intrinsic hydrogeology | `K_m_day`, `gradient_i`, `phi_mobile`, `phi_total`, `darcy_flux_q = K·i`, `seepage_velocity_v = q/φ_m` | Darcy's law; trees cannot divide, so the ratios are pre-computed |
| Chemistry | `Kd_L_kg`, `retardation_Rd`, `contaminant_velocity_vc` | sorption and its effect on velocity (§4.4) |
| Dispersion | `alpha_L`, `alpha_T`, `anisotropy_ratio`, `D_L = α_L v`, `D_T = α_T v` | scale-dependent dispersivity (§4.4) |
| Dimensionless groups | `peclet_L`, `pore_volumes_PV`, `dimensionless_time_tau`, `dual_porosity_beta` | what transfers between Texas and Jharkhand |
| Operations | `Q_in_m3_day`, `bleed_fraction`, `Q_net_m3_day`, `containment_eta`, `operation_days`, `wellfield_width_m` | the scenario |
| Source | `source_conc_C0`, `background_conc_Cb` | per species; support recorded per species |
| Irregularities and restoration | `downtime_fraction`, `gradient_seasonal_amp`, `restoration_years`, `residual_fraction` (the *realized*, elapsed-credited fraction), `u_attenuation_k` | band width; causal restoration credit |
| Kinematics | `Xc_m`, `Xc_clean_m`, `time_years`, `is_post_closure` | front positions the engine computes analytically |
| Species one-hots | `is_uranium_ppb`, `is_sulfate_mg_l`, `is_tds_mg_l`, `is_radium_226_mbq_l` | one model, four species |

Two leakage controls shape the feature set. There are **no coordinates** among the features: space enters only through resolved physical parameters, so the surrogate cannot invent spatial artefacts of its own (the fidelity matrix's Q4 transect confirmed every step in the ML answer is co-located with a data boundary present in the engine too). And the physics carry-throughs the engine needs but the surrogate must not see (`_eta_eff`, `_source_width_m`, `_grain_density`, `_regime`, `_Xc_clean_m`) are private keys on the row, not features.

## 4.4 Hydrogeological framework

**Regime.** Each of the 12 lithologies is assigned *fractured* or *porous* (Table 3.3). The regime selects which velocity the front runs on, whether the dual-porosity clock and the Tang envelope apply, which Kd table is used, and which transverse anisotropy ratio and vertical Kv/Kh apply.

**Hydraulic properties by lithology.** K, specific yield and thickness come from the polygon where present; effective (mobile) porosity, total porosity and grain density are filled from lithology-typical values [1] where the polygon carries none (fractured mobile porosities 0.005–0.010, total 0.01–0.05; porous 0.08–0.25 and 0.20–0.35). These are drinking-water-aquifer values applied at ore depth, which is the reason for the next two corrections.

**Depth decay of K (fix 3.3, August 2026).** Crystalline-rock permeability falls with depth. The engine applies

$$K(z) = K_{\text{ref}}\,\exp\!\left(-\frac{z - 45}{\lambda}\right), \qquad \lambda = \frac{z_{\text{fb}} - 45}{\ln(1/0.05)} \tag{4.1}$$

where z is the ore depth, 45 m is the depth to which NAQUIM reports fractures as common, z_fb is the district's fracture-death depth from the layer table (258 m in East Singhbhum, 121 m in Ranchi), and K/K_ref = 0.05 at z_fb. Below z_fb the factor is *held*, not extrapolated: extrapolating gave a 23,000× reduction at 300 m for a shallow-fracture district, against about 440× from the global crustal trend of Manning & Ingebritsen [11] over the same interval — the local evidence stops at the fracture base and says "massive rock", not "impermeable". At Jaduguda (180 m) K falls from 2.47 to 0.37 m/day; at the 150 m registered-site depth, to 0.56 m/day.

**Shear-zone transmissivity (D5).** The E-Singhbhum NAQUIM profile records transmissivities of 207–570 m²/day exactly where the deposits lie, several times the generic schist polygon's; the engine applies T = 370 m²/day over a 150 m productive thickness at deposit and belt pins, tapered at the belt edge so the toggle is not a step.

**Seam blending (fix 3.6).** The CGWB layer is finely interleaved — a random in-polygon pin is a median 1.4 km from a contact — so K is blended across mapped contacts in log-K space with weight `w_own = 0.5 + 0.5·min(d/L, 1)`, L ≈ 2.2 km, and the per-district λ and the shear-zone toggle are blended the same way. Measured before/after: the worst single-step area jump on the Ranchi→Jaduguda transect fell from 16.5 ha to 4.75 ha; the district-λ step from 1.74× to 1.015×; the belt-edge shear-zone step from +37 % plume area to +1.7 %; and a regime-contact step of 2.16× that turned out to be caused by an ML-support clamp was removed by deleting the clamp (§7.5). The belt→none step in the uranium source term is deliberately *not* blended: "none" means no ore, and smearing a source into non-ore rock would break the guard that the tool cannot invent contamination.

**Anisotropy from fracture fabric (E1).** The transverse-to-longitudinal dispersivity ratio is set from the strike field's circular variance,

$$\frac{\alpha_T}{\alpha_L} = \operatorname{clip}\!\left(0.02\,\exp\!\frac{V - 0.63}{0.20},\; 0.01,\; 0.10\right) \tag{4.2}$$

anchored so that the state-median V ≈ 0.63 reproduces the literature default of 0.02 for fractured rock [8]; aligned fractures (low V) give a narrow, channelled plume. The plume's display azimuth is rotated from the flow direction toward the strike, blended by alignment strength (the Darcy flux vector rotates toward the high-K direction of a transmissivity tensor).

**Ore-zone gating and grade scaling (Module 2, D4).** The uranium (and radium) source term exists only where uranium ore exists. A pin resolves to *deposit* (inside a deposit polygon or its 500 m halo: C₀ = Texas envelope × grade_deposit / 0.05 % U, clipped to the envelope), *belt* (inside the Singhbhum envelope: 0.30 × the nearest deposit's value, ramped linearly over 3 km from the deposit outline so the tier step is 1.05× rather than 3.3×) or *none* (a trace term of 3 × background with a 5 ppb floor, and `u_suppressed = true` so the surrogate is bypassed and no uranium plume is drawn). Sulphate and TDS are not ore-gated: a lixiviant carries them wherever it is injected.

**Kd.** Distribution coefficients are triangular ranges per species × regime (Table 3.3), sampled per Monte-Carlo draw and served at the central value. Uranium's are low because alkaline-carbonate chemistry suppresses uranyl sorption; radium's are two to four orders of magnitude higher and were rebased in August 2026 from the Thibault soil compilation to measured groundwater values [47] and sampled in log space, which is what gave radium's labels enough variance to be scored at all (§6.2).

**Retardation.** In porous rock, linear equilibrium sorption gives the classical

$$R_d = 1 + \frac{\rho_b K_d}{n}, \qquad \rho_b = (1 - n)\,\rho_{\text{grain}}, \qquad v_c = \frac{v}{R_d} \tag{4.3}$$

with n the total porosity. In fractured rock the bulk-density form is wrong — the solute contacts fracture walls, not the rock volume — so the engine refuses it and applies retardation through two mechanisms: dual-porosity exchange and matrix diffusion (§4.5). The *matrix* retardation `R_m = 1 + ρ_b K_d / θ_m` (θ_m the matrix porosity) is the one place Kd physically acts in fractured rock, and it is the single source of truth for both the Tang attenuation group and the dual-porosity capacity ratio, which must never drift apart.

## 4.5 Contaminant plume simulation

The engine (`ml_pipeline/physics/transport.py`, ~1,500 lines) evaluates a closed-form plan-view concentration field on an auto-sized grid in about 0.2 s and derives its metrics analytically where the grid would quantise them. Its components, in the order they are applied:

**Darcy velocity.** `q = K·i`, `v = q/φ_m` (eq. 4.4). In fractured rock φ_m is under 1 %, which is why fractured plumes move fast per unit flux.

**Containment (the bleed).** From capture-zone theory [69], a wellfield with net extraction Q_net in regional Darcy flux q through thickness b and width W captures the fraction

$$\eta = \min\!\left(1,\; \frac{Q_{\text{net}}}{q\,b\,W}\right) \tag{4.5}$$

of its own footprint's throughflow; η = 1 is complete capture. Pump downtime degrades it (`η_eff = η(1 − downtime)`); the training generator samples Q_net independently of Q_in so that the surrogate can separate "more throughput" from "more capture".

**Three-phase front.** The leading edge of the plume is

$$X_c(t) = v\,(1-\eta)\,\mathcal{I}\!\big(\min(t, t_{\text{op}})\big) + v\,\big[\mathcal{I}(t) - \mathcal{I}(t_{\text{op}} + t_{\text{rest}})\big]^{+} \tag{4.6}$$

— operation at velocity v(1 − η), the restoration sweep with the front *held* (the conservative representation of a groundwater sweep that in reality pulls water back), and free post-closure drift at v. 𝓘 is the dual-porosity *retarded clock*, the closed-form integral of 1/R_app(t′) for the Goltz–Roberts first-order mobile/immobile model [7]:

$$R_{\text{app}}(t) = 1 + \beta_{\text{eff}}\big(1 - e^{-a t}\big), \quad a = \omega\,\frac{1+\beta_{\text{eff}}}{\beta_{\text{eff}}}, \qquad \mathcal{I}(t) = \int_0^t \frac{dt'}{R_{\text{app}}(t')} \tag{4.7}$$

so that the front moves at water speed early and at v/(1 + β_eff) late. The clock is the identity for porous rock, where v is already the Kd-retarded velocity of eq. 4.3.

**The sorption-scaled capacity ratio.** Until August 2026 the fractured front was species-blind: Kd entered only the Tang term, which is unioned by a maximum and can only extend a plume, so radium moved exactly as fast as sulphate (review finding #2). The correction, which is standard in crystalline-repository safety cases, scales the conservative-tracer capacity ratio by matrix sorption:

$$\beta_{\text{eff}} = \beta \cdot R_m, \qquad R_{\text{eff}} = 1 + \beta\,R_m \tag{4.8}$$

Since R17, β itself is not a served constant but is *derived* from the porosities the run already resolves with provenance:

$$\beta = \frac{n_{\text{total}} - \varphi_m}{\varphi_m} \tag{4.9}$$

(3.0 at Jaduguda with n_total = 0.03 and φ_m = 0.0075; 1.0–4.0 across the lithology table), replacing a literature mean of 10 that the tool's own porosities contradicted by a factor of three. At Jaduguda uranium, R_m ≈ 90 and R_eff ≈ 271; for radium R_eff ≈ 3,500; for TDS (Kd = 0) R_eff = 1 + β = 4. A diagnostic run before the R17 retrain compared this first-order clock with a √t diffusive clock at the three reference sites and found both reach the capacity cap within 3–6 years of a 20-year horizon: the front runs on the *capacity*, not the kinetics, so β is the lever and the clock is not (`docs/LIMITATIONS.md` §1d).

**The plan-view field.** With X_c known, the concentration is the Domenico product [2], [3] with the *full* Ogata–Banks longitudinal factor [4] (the second term was restored in August 2026 after the exact-solution benchmark showed its omission biased concentrations 17–42 % low — §6.2) and the finite-width transverse factor:

$$F_L(x) = \tfrac{1}{2}\operatorname{erfc}\!\frac{x - X_c}{2\sqrt{\alpha_L X_c}} + \tfrac{1}{2}\exp\!\Big(\frac{x}{\alpha_L}\Big)\operatorname{erfc}\!\frac{x + X_c}{2\sqrt{\alpha_L X_c}} \tag{4.10}$$

$$F_T(x, y) = \tfrac{1}{2}\left[\operatorname{erf}\frac{y + W/2}{2\sqrt{\alpha_T x}} - \operatorname{erf}\frac{y - W/2}{2\sqrt{\alpha_T x}}\right] \tag{4.11}$$

$$C_{\text{plume}}(x, y) = C_0\, F_L(x)\, F_T(x, y) \tag{4.12}$$

where x is down-gradient distance from the source plane at the wellfield's down-gradient edge, W is the effective source width, and dispersivities follow Xu & Eckstein [9] evaluated at the transport scale, `α_L = 0.83 (log₁₀ L)^2.414`, with α_T from eq. 4.2. The field is plume-attributable (no background); background is added back at the reporting step.

**Matrix diffusion (Tang envelope).** For fractured rock the engine also evaluates the zero-fracture-dispersion solution of Tang, Frind & Sudicky [5] for concentration along a fracture with diffusion into the matrix,

$$A(x) = \operatorname{erfc}\!\left[\frac{\sigma\sqrt{t}}{2}\cdot\frac{r}{\sqrt{1-r}}\right], \quad r = \frac{x}{X_w}, \qquad \sigma = \frac{\theta_m\sqrt{R_m D_e}}{b} \tag{4.13}$$

where X_w is the *water* front (eq. 4.6 with β = 0), D_e the effective matrix diffusion coefficient and b the fracture half-aperture, and takes the maximum of the retarded-continuum longitudinal factor and this envelope — a deliberately conservative union that can only extend the plume. The R17 diagnostic found the retarded-continuum branch governs at every reference site and species at 20 years; the Tang branch is retained as the early-arrival guard. The aperture is Monte-Carlo-sampled (100–500 µm); D_e is not, because no defensible range exists for it and inventing one would relabel an assumption as data.

**The leach-zone disc (E1).** The wellfield footprint is contaminated by construction. It is drawn as a uniform-concentration disc of radius W_eff/2 centred up-gradient of the source plane, where the effective width grows with throughput,

$$W_{\text{eff}} = W\left(1 + 0.40\tanh\frac{BV}{2}\right), \qquad BV = \frac{Q_{\text{in}}\,t}{\varphi_m\,V_{\text{pattern}}} \tag{4.14}$$

The gain (0.40) and the reference scale (2 bulk volumes) are project assumptions with no field grounding — marked ⚑ in Table 3.3 and listed in Appendix E.2. The disc radius scales with √min(1, PV) so that nothing is drawn before pore volumes have been injected (a July defect drew 7.07 ha at t = 0). The disc is unioned into the *area* metric only; migration and ring concentration track the migrating front and never the source footprint. Between 76 and 97 % of the reported affected area is the disc itself, which is why "footprint" is reported as *wellfield plus a migrating increment* and not as a transport metric.

**Restoration draw-down and the deficit wave.** Restoration exchanges pore volumes; equal fractional removal per pore volume gives exponential decay of the source concentration with *elapsed* sweep time, anchored so that the 5.0-year reference sweep reproduces the paired Texas endpoint [15], [16] and floored at 0.02 (the irreducible residual):

$$\frac{C_{\text{src}}}{C_0} = \max\!\Big(0.02,\; \text{endpoint}^{\,\text{elapsed}/5\,\text{yr}}\Big), \qquad \text{elapsed} = \operatorname{clip}(t - t_{\text{op}},\, 0,\, t_{\text{rest}}) \tag{4.15}$$

A planned-but-future sweep cleans nothing (the QA F-1 fix of July 2026, which removed a 3.3× area snap at the boundary). After closure a passive flush by regional flow continues with a 30-year half-life anchored to the EPA's ≥ 30-year post-restoration monitoring horizon [20]; once a sweep has run, the flush may not take the source below the measured Texas endpoint, because that endpoint is measured on post-restoration *stability* samples and any rebound is already inside it [19] (the R-3 fix, August 2026). The escaped plume keeps its history: a clean-water replacement wave of amplitude (C₀ − C_src) is subtracted with its own front X_clean, released at end of operations and drifting at v,

$$C = C_0\,F_L(x; X_c)\,F_T \;-\; (C_0 - C_{\text{src}})\,F_L(x; X_{\text{clean}})\,F_T \tag{4.16}$$

which is what makes the dark band detach and migrate down-gradient on the map. Two post-freeze corrections (21 September 2026): the source-zone reading is floored at the site's own background, because passive flushing is regional groundwater already at background and cannot dilute the source past it (at Jaduguda's high TDS background, 1,779 mg/L, an unfloored restored source read 1,232 mg/L); and the reading is carried consistently to the lifecycle diagnostic that had computed it independently.

**First-order uranium attenuation.** Down-gradient of the wellfield, dissolved U(VI) meets reducing rock and precipitates as immobile U(IV) — the redox trap that formed the ore. The screening form multiplies the travelling expression (base plume and deficit wave alike, so the wave cannot subtract more than exists) by

$$\exp(-k\,\text{age}), \qquad \text{age} = \frac{x}{v_c} + t_{\text{held}} \tag{4.17}$$

with the two rate-constant senses of Newell et al. [21] — distance (plug-flow travel at the *tracer-retarded* velocity, so that uranium already immobilised by sorption is not charged the reduction rate twice) and time (the years the sweep held the plume still). k is log-triangular (0.05, 0.20, 0.70)/yr per scenario, with the mode tilted by ore-zone mineralogy — the ore is sulphide-bearing [64], [65], so its reducing capacity is richer than the oxidised country rock's (deposit 0.35, belt 0.28, non-ore 0.12/yr) and a ×0.5–2 per-draw multiplier; the 0.70 ceiling is the intact-rock value from the Wyoming cross-hole test [18]. It applies to uranium only — sulphate, TDS and chloride are conservative — and never to the source disc, whose reductants the lixiviant deliberately oxidised. The consequence is a finite steady-state extent, `x* = (v_c/k) ln(C₀/threshold)`.

**Metrics.** From the plume field the engine reports: the affected area (cells at or above the *incremental* threshold, `max(threshold − background, 0.10 × threshold)`, unioned with the disc); the maximum migration distance, measured **analytically along the centreline** as the farthest down-gradient point at or above the incremental threshold (a grid read-off quantised short plumes to zero and, before August 2026, returned the distance to the upstream corner of the Domenico artefact box — 422.8 m at Jaduguda for a plume whose true reach was 35.9 m, identical for all species, and baked into the training labels; review finding #1); the concentration at the monitoring ring, `C_plume(ring) + background`; and the breach flag at that ring.

**The NUREG-1569 excursion test.** An excursion is declared when two or more of the three indicator species — chloride, TDS (the conductivity proxy) and sulphate — exceed their upper control limits at the ring, the control limit being baseline × 1.20 bracketed between the baseline and the lixiviant value (the "simple percentage over baseline" rule the review plan permits; its preferred mean-plus-5σ rule needs a per-well temporal series the record lacks). Uranium and radium are deliberately excluded as indicators, exactly as the review plan excludes them. Chloride is computed on the analytical path only (`EXCURSION_ONLY_SPECIES`), which is what let it be added in August 2026 without a retrain. The panel meets NUREG's minimum of three indicators; `compliance_status` states permanently that meeting the count is not regulatory compliance.

**Monte-Carlo bands and excursion probability.** For every scenario 48 draws vary K (log-normal heterogeneity), Kd (triangular), β (log-uniform over [β/4, 4β] clipped to the prior), the fracture aperture, the gradient (widened by the pin's measured seasonal amplitude, ±30 % minimum), dispersivity (×0.7–1.5), net extraction drift, and k. The P10/P50/P90 of area, migration and ring concentration across draws are the distributional labels, and

$$p_{\mathrm{ex}} = \frac{1}{N}\sum_{d=1}^{N} \mathbf{1}\left[ C_d(\mathrm{ring}) \ge \max\left(\mathrm{threshold} - \mathrm{background},\ 0.10\,\mathrm{threshold}\right) \right] \tag{4.18}$$

is the excursion probability — incremental, so that a naturally poor baseline is not blamed on the mine.

**Vertical (2.5-D) screening.** The plan-view solve is depth-integrated over the ore horizon. A separate screening asks whether contamination at ore depth can reach the shallow Layer-1 aquifer through three OR-combined pathways: (1) *dispersive* upward spreading, the Domenico vertical erf factor with α_V/α_L = 0.025 from the source centre to the Layer-1 base; (2) *advective leakage* through the semi-confining fractured zone, `v_up = K_v i_up / φ_conf`, K_v = (K_v/K_h) K_h, breakthrough when `v_up t ≥ Δz` over the gap from the ore *top* to the Layer-1 base (so a thicker ore body shortens the path); (3) a *wellbore* short-circuit at a base probability of 0.05, concentration-gated. The combined index is `p = 1 − (1 − p_disp)(1 − p_adv)(1 − p_well)`, reported as a transparent screening index and never as a calibrated probability, together with every component and the dominant pathway. Two corrections of August 2026 shape it: the upward gradient is bracketed by the measured monsoon swing (wet season suppresses it, possibly closing the pathway; dry season enhances it), reported as a two-end-member band because deep piezometry is unmeasured; and the headline breakthrough time is evaluated on the *duty-cycle* gradient, the annual mean of max(i(t), 0), after the earlier headline at the mean gradient was found to sit outside its own seasonal band and to *understate* the hazard by about 1.9× (`docs/LIMITATIONS.md` §1b). No shallow-aquifer plume after breakthrough is modelled; the radius decides who is told, not how far anything spreads.

**Limitations of the analytical family**, stated where the equations are: uniform steady flow per run; one homogeneous layer per polygon with heterogeneity only statistical; depth-integration (no true 3-D); the Domenico upstream half-plane painted at C₀ (managed by the disc and deficit-wave design and excluded from every travel metric since August 2026); a first-order infinite-sink attenuation where real reducing capacity is finite; the front held rather than reversed during restoration; and a fixed matrix transfer rate ω under a sorption-scaled capacity ratio, which over-retards uranium at early time — bounded by the Tang envelope, which carries the correct √t scaling and governs wherever the continuum branch over-retards. Deriving ω from fracture geometry was implemented, measured and rejected because β_eff·ω cancels R_m and makes early-time retardation species-blind again (`JHARKHAND_FIDELITY_MATRIX.md`, round-2 notes).

**Verification.** The transport kernel is benchmarked against an exact 2-D convolution (`physics/exact_reference.py`: the inverse-Gaussian first-passage density convolved with the transverse factor, self-validated against Ogata–Banks to 10⁻¹⁶ as W → ∞) over 240 parameter sets drawn from the training distribution (§6.2); the retarded clock's closed form is checked against numerical integration (621.1088 vs 621.1088 days in the end-to-end audit); and the physics laws are regression-tested on the *labels* — K↑ ⇒ larger, bleed↑ ⇒ smaller, more Q_in at fixed Q_net ⇒ larger, restoration ⇒ no worse, t = 0 ⇒ zero area and zero migration in both engines — in `tests/test_physics_laws.py`.

**Timeline frames (R17).** For every stored run the engine is re-evaluated at up to ~15 horizons (the base set within the horizon, the horizon itself, and the two phase boundaries), and each frame stores the screening-limit contour, area, migration, ring concentration, phase and the first-exceedance year at the ring. Nothing is interpolated: "first exceedance at the 8-year frame" means the crossing lies between the 5- and 8-year evaluations. The ML band is evaluated per frame but drawn only at the run's own horizon, because the band ellipses belong to that horizon.
