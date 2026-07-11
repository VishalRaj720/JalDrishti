"""
ml_pipeline.config.parameters
===========================
Single source of truth for every physical constant, lithology mapping,
distribution coefficient (Kd), dispersivity relation and regulatory limit
used by the JalDrishti "approach 2" physics-informed surrogate.

DESIGN RULE (per project brief): nothing is silently hard-coded. Every value
that is NOT present in the user's own data files carries an inline citation and
is exposed as a tunable default so the dashboard / training loop can override it.

Values that ARE present in the data files are derived at runtime by the loaders
(porosity from AquiferExemptions.OrePorosity, transmissivity from
Aquifers_Jharkhand.geojson.m2_perday, etc.) and are NOT duplicated here.

References
----------
[BIS]   IS 10500:2012 Indian Standard, Drinking Water - Specification
        (acceptable / permissible limits). Uranium not in base standard;
        WHO (2017) provisional guideline 30 ug/L used, consistent with the
        BIS amendment alignment widely cited in Indian groundwater studies.
[WHO]   WHO (2017) Guidelines for Drinking-water Quality, 4th ed. + 1st add.
[EPA99] EPA 402-R-99-004B (1999) "Understanding Variation in Partition (Kd)
        Coefficient Values, Vol. II: Uranium". Kd(U) spans <1 to >10^4 L/kg,
        controlled by pH and carbonate.
[DAVIS] Davis & Curtis / USGS Naturita studies; in-situ U(VI) Kd 0.5-10.6 L/kg,
        decreasing with alkalinity (uranyl-carbonate complexation).
[SHEP]  Sheppard & Thibault (1990) Health Phys. 59:471 - soil/sediment Kd geometric means.
[GELHAR]Gelhar, Welty & Rehfeldt (1992) WRR 28(7):1955 - field dispersivity review.
[XU]    Xu & Eckstein (1995) Ground Water 33(6):905 - alpha_L = 0.83*(log10 L)^2.414.
[DOM]   Domenico (1987) J. Hydrol. 91:49 - analytical multidimensional transport.
[GOLTZ] Goltz & Roberts (1986) WRR 22(7):1139 - mobile/immobile (dual-porosity).
[FREEZE]Freeze & Cherry (1979) "Groundwater" - K, porosity, bulk density ranges.
[ISRGOL]Jung et al. (2022) Minerals 12(3):369 - ISR environmental footprint, Goliad Sand.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 0. Physical constants (water at ~20 C) for the milliDarcy -> K conversion
# ---------------------------------------------------------------------------
WATER_DENSITY = 1000.0          # rho   [kg/m3]
GRAVITY = 9.81                  # g     [m/s2]
WATER_DYN_VISCOSITY = 1.002e-3  # mu    [Pa.s] at 20 C
DARCY_TO_M2 = 9.869233e-13      # 1 darcy in m^2 (intrinsic permeability)
SECONDS_PER_DAY = 86400.0

def millidarcy_to_m_per_day(k_mD: float) -> float:
    """Convert intrinsic permeability (milliDarcy) to hydraulic conductivity K
    (m/day) for water at 20 C, via K = k * rho * g / mu.  [Freeze & Cherry 1979]

    1 mD ~= 8.36e-4 m/day -> Texas FormPerm=5000 mD ~= 4.2 m/day (productive sand).
    """
    k_m2 = k_mD * 1e-3 * DARCY_TO_M2            # mD -> m^2
    K_m_s = k_m2 * WATER_DENSITY * GRAVITY / WATER_DYN_VISCOSITY
    return K_m_s * SECONDS_PER_DAY

# ---------------------------------------------------------------------------
# 1. Regulatory limits -- targets for Excursion Probability (P_ex)
#    Units chosen to match the user's own columns:
#      U -> ppb (waterQuality_jharkhand.csv "U (ppb)")
#      SO4, TDS -> mg/L
# ---------------------------------------------------------------------------
BIS_LIMITS = {
    # species: (acceptable, permissible, unit, citation)
    "uranium_ppb": (30.0, 30.0, "ppb", "WHO 2017 provisional 30 ug/L; BIS-aligned"),
    "sulfate_mg_l": (200.0, 400.0, "mg/L", "BIS IS 10500:2012"),
    "tds_mg_l": (500.0, 2000.0, "mg/L", "BIS IS 10500:2012"),
    "ph": (6.5, 8.5, "pH units", "BIS IS 10500:2012 (no relaxation)"),
    "nitrate_mg_l": (45.0, 45.0, "mg/L", "BIS IS 10500:2012"),
    "fluoride_mg_l": (1.0, 1.5, "mg/L", "BIS IS 10500:2012"),
}

# Which limit to use when scoring an excursion: "permissible" is the legal
# breach threshold "in the absence of an alternate source".
EXCURSION_THRESHOLDS = {
    "uranium_ppb": BIS_LIMITS["uranium_ppb"][1],
    "sulfate_mg_l": BIS_LIMITS["sulfate_mg_l"][1],
    "tds_mg_l": BIS_LIMITS["tds_mg_l"][1],
}

# Monitoring/compliance ring distance DOWNGRADIENT OF THE WELLFIELD EDGE.
# The Domenico source plane sits at the downgradient edge (conservative areal-
# source convention), so the ring is at x = COMPLIANCE_BUFFER_M in solver
# coordinates and at (W/2 + COMPLIANCE_BUFFER_M) from the wellfield centre pin.
# Single source of truth -- generate.py / predict.py / server.py import this.
COMPLIANCE_BUFFER_M = 100.0

# Excursions are scored on the MINING-ATTRIBUTABLE (incremental) concentration:
#   breach if C_plume >= max(threshold - background, INCREMENTAL_FLOOR*threshold)
# The floor keeps the criterion meaningful when the ambient baseline already
# sits at/above the limit (otherwise any pin in naturally poor water would
# "breach" over the whole grid regardless of the mine).
INCREMENTAL_FLOOR = 0.10

# EC (uS/cm) -> TDS (mg/L). waterQuality_jharkhand.csv has EC but not TDS.
# Factor 0.55-0.75 typical; 0.64 standard for mixed groundwater. [Freeze & Cherry]
EC_TO_TDS_FACTOR = 0.64

# ---------------------------------------------------------------------------
# 2. Jharkhand lithology -> transport regime mapping
#    Drives whether the user's chosen pin behaves as an anisotropic fractured
#    medium (directional channeling) or an isotropic porous/weathered medium.
#    Keys are the values found in Aquifers_Jharkhand.geojson "aquifer" column.
# ---------------------------------------------------------------------------
# regime: "fractured" (hard-rock / crystalline / shear) vs "porous" (granular)
LITHOLOGY_REGIME = {
    "Schist": "fractured",
    "Gneiss": "fractured",
    "Granite": "fractured",
    "Quartzite": "fractured",
    "Charnockite": "fractured",
    "Basement Gneissic Complex": "fractured",
    "Basalt": "fractured",
    "Intrusive": "fractured",
    "Limestone": "porous",      # karstic in places; treat as high-K porous/dual
    "Sandstone": "porous",
    "Laterite": "porous",       # weathered mantle
    "Alluvium": "porous",
}

# Default effective (kinematic) porosity by lithology when the data's specific
# yield ("yeild__") is missing or "-".  These are TRANSPORT (mobile) porosities,
# deliberately small for hard rock (flow in fractures only). [Freeze & Cherry 1979]
DEFAULT_EFFECTIVE_POROSITY = {
    "Schist": 0.010,
    "Gneiss": 0.008,
    "Granite": 0.005,
    "Quartzite": 0.008,
    "Charnockite": 0.006,
    "Basement Gneissic Complex": 0.008,
    "Basalt": 0.010,
    "Intrusive": 0.007,
    "Limestone": 0.080,
    "Sandstone": 0.250,
    "Laterite": 0.120,
    "Alluvium": 0.200,
}

# TOTAL (matrix) porosity by lithology -- used for the retardation factor
# Rd = 1 + (rho_b/n_total)*Kd, which depends on sorption per unit water VOLUME,
# i.e. the whole connected pore space, NOT the small mobile fracture porosity.
# Keeping this separate from DEFAULT_EFFECTIVE_POROSITY (the advective/kinematic
# porosity) is what stops fractured rock from being absurdly over-retarded.
# [Freeze & Cherry 1979 typical total porosities]
TOTAL_POROSITY = {
    "Schist": 0.03, "Gneiss": 0.02, "Granite": 0.01, "Quartzite": 0.02,
    "Charnockite": 0.02, "Basement Gneissic Complex": 0.03, "Basalt": 0.05,
    "Intrusive": 0.02, "Limestone": 0.20, "Sandstone": 0.30,
    "Laterite": 0.35, "Alluvium": 0.30,
}
DEFAULT_TOTAL_POROSITY = 0.20

# Grain / matrix density by lithology (kg/m3) for dry bulk density
#   rho_bulk = (1 - total_porosity) * rho_solid   -> used in Rd = 1 + (rho_b/phi)*Kd
GRAIN_DENSITY = {  # [Freeze & Cherry 1979; typical petrophysics]
    "Schist": 2750.0, "Gneiss": 2700.0, "Granite": 2650.0, "Quartzite": 2650.0,
    "Charnockite": 2800.0, "Basement Gneissic Complex": 2700.0, "Basalt": 2900.0,
    "Intrusive": 2750.0, "Limestone": 2710.0, "Sandstone": 2650.0,
    "Laterite": 2400.0, "Alluvium": 2650.0,
}
DEFAULT_GRAIN_DENSITY = 2700.0

# ---------------------------------------------------------------------------
# 3. Dispersivity model (NOT in any data file -> literature relation)
#    Longitudinal dispersivity scales with transport distance L.
#    Xu & Eckstein (1995):  alpha_L = 0.83 * (log10 L)^2.414   [L, alpha_L in m]
#    Anisotropy ratios alpha_L:alpha_T differ porous vs fractured.
# ---------------------------------------------------------------------------
def longitudinal_dispersivity(L_m: float) -> float:
    """Scale-dependent alpha_L (m) from transport distance L (m). [Xu & Eckstein 1995]"""
    import math
    L_m = max(L_m, 1.0)
    return 0.83 * (math.log10(L_m) ** 2.414)

# alpha_T / alpha_L  (transverse-to-longitudinal). Fractured/shear zones channel
# flow -> very low transverse spreading -> strong anisotropy. [Gelhar et al. 1992]
TRANSVERSE_ANISOTROPY = {
    "fractured": 0.02,   # alpha_T = 0.02 * alpha_L  -> long, narrow, directional plume
    "porous":    0.10,   # alpha_T = 0.10 * alpha_L  -> rounder plume
}

# ---------------------------------------------------------------------------
# 4. Distribution coefficient Kd (L/kg) per species x regime, ALKALINE ISR.
#    Uranium: LOW under alkaline/carbonate conditions (uranyl-carbonate
#    complexes are weakly sorbing) -> low Rd -> mobile. [EPA99, DAVIS]
#    Sulfate & TDS: effectively conservative tracers. [SHEP]
#    Given as (low, central, high) so the synthetic loop can sample uncertainty.
# ---------------------------------------------------------------------------
KD_RANGES = {  # L/kg
    "uranium_ppb": {
        # fractured hard rock: low surface area; alkaline U is mobile -> low Kd.
        # Apparent retardation here comes mostly from matrix diffusion (beta).
        "fractured": (0.3, 1.0, 3.0),
        # weathered/alluvial: more clay + Fe/Mn oxides -> moderate retardation,
        # but still suppressed by uranyl-carbonate complexation. [DAVIS, EPA99]
        "porous":    (0.5, 2.5, 8.0),
    },
    "sulfate_mg_l": {  # near-conservative anion
        "fractured": (0.0, 0.05, 0.3),
        "porous":    (0.0, 0.10, 0.5),
    },
    "tds_mg_l": {      # bulk salinity proxy -> conservative
        "fractured": (0.0, 0.0, 0.0),
        "porous":    (0.0, 0.0, 0.0),
    },
}

# ---------------------------------------------------------------------------
# 5. Dual-porosity (mobile/immobile) parameters for fractured/shear zones.
#    beta = theta_immobile / theta_mobile  (capacity ratio). Matrix diffusion
#    stores solute -> extra retardation + tailing. [Goltz & Roberts 1986]
#    Only applied when regime == "fractured" (toggle in dashboard).
#    mass_transfer_omega drives the TIME-DEPENDENT apparent retardation
#    R_app(t) = 1 + beta*(1 - exp(-omega*t*(1+beta)/beta)): the front travels
#    unretarded at early time (matrix uptake immature) and approaches the
#    asymptotic 1+beta at late time. [Goltz & Roberts 1986 first-order model]
# ---------------------------------------------------------------------------
DUAL_POROSITY = {
    "enabled_for": ("fractured",),
    "beta_range": (2.0, 8.0, 20.0),   # (low, central, high) capacity ratio
    "mass_transfer_omega": 1e-3,      # first-order rate [1/day], slow matrix diffusion
}

# ---------------------------------------------------------------------------
# 5b. Discrete-fracture matrix-diffusion kernel (fractured regime).
#     Tang, Frind & Sudicky (1981) / Neretnieks (1980) zero-fracture-dispersion
#     solution: C/C0 = erfc[ sigma * t_w / (2*sqrt(t - t_w)) ], with the
#     matrix-diffusion group
#         sigma = theta_m * sqrt(R_m * De) / b_half        [1/sqrt(day)]
#     (theta_m matrix porosity, R_m matrix retardation -- where Kd finally
#     acts in fractured rock -- De effective matrix diffusion, b_half the
#     fracture HALF-aperture). Small aperture => huge flow-wetted surface =>
#     strong attenuation; open fractures => early far breakthrough.
# ---------------------------------------------------------------------------
FRACTURE = {
    # full hydraulic aperture 2b (m): (low, central, high). Crystalline-rock
    # apertures 50-500 um. [Neretnieks 1980; Tang et al. 1981; Freeze & Cherry]
    "full_aperture_m": (1.0e-4, 2.5e-4, 5.0e-4),
    # effective matrix diffusion coefficient De = tau * D0 (m2/day);
    # D0 ~ 5-7e-10 m2/s, tortuosity ~0.1 => ~5e-6 m2/day. [Neretnieks 1980]
    "De_m2_day": 5.0e-6,
}

# ---------------------------------------------------------------------------
# 5c. Alkalinity control on uranium Kd (CORRECTED 2026-07 regime audit).
#     Uranyl-carbonate complexation suppresses U sorption -> higher carbonate
#     lowers Kd. CRITICAL CONTEXT: this surrogate models an ALKALINE-ISR plume,
#     which CARRIES its own lixiviant carbonate (NaHCO3, 500-1000+ mg/L). So in
#     the near/mid field the carbonate that controls Kd is lixiviant-dominated
#     and HIGH regardless of the AMBIENT bicarbonate. The KD_RANGES values above
#     already encode this alkaline suppression (that is why porous U Kd is
#     0.5-2.5, not the 10+ of neutral groundwater).
#
#     Therefore ambient HCO3 may only push Kd DOWN further (extra suppression in
#     already-carbonate-rich groundwater) -- it must NEVER amplify Kd above the
#     central alkaline value. The pre-audit version amplified at low ambient HCO3
#     (scale > 1), which -- stacked on a mismatched porosity from the regime
#     toggle -- produced an unphysical Rd ~ 635 and a frozen plume.
#
#     NOTE: the plume Kd used by the transport engine is sampled from KD_RANGES
#     directly (train == serve). This helper is retained for OPTIONAL ambient
#     far-field context only; it is not applied to the near-field plume Kd.
# ---------------------------------------------------------------------------
KD_ALKALINITY = {"ref_hco3_mg_l": 300.0, "exponent": 1.3}

def alkalinity_adjusted_kd(kd_central: float, hco3_mg_l: float | None,
                           kd_lo: float, kd_hi: float) -> float:
    """Ambient-alkalinity Kd modifier, SUPPRESSION-ONLY. Returns kd_central when
    HCO3 is unknown or low; only high ambient carbonate lowers Kd. Never exceeds
    kd_central (the alkaline-ISR plume already carries suppressing carbonate)."""
    if hco3_mg_l is None or not (hco3_mg_l == hco3_mg_l) or hco3_mg_l <= 0:
        return kd_central
    scale = (hco3_mg_l / KD_ALKALINITY["ref_hco3_mg_l"]) ** (-KD_ALKALINITY["exponent"])
    scale = min(scale, 1.0)                      # suppression-only: never amplify
    return float(min(max(kd_central * scale, kd_lo), kd_hi))

# ---------------------------------------------------------------------------
# 5c-bis. Regime material archetypes (2026-07 regime audit fix).
#     The dashboard's regime toggle asks "what if this site behaved as
#     fractured / weathered-porous instead?". Transport style then depends on
#     the MATERIAL (mobile & total porosity, grain density), not just the
#     equation branch. Reusing the pin's crystalline materials under the porous
#     branch built a physics chimera (schist porosity n_total=0.03 into porous
#     bulk sorption -> Rd ~ 635). When the user overrides the regime AWAY from
#     the pin's natural regime, substitute these regime-typical materials so the
#     hypothetical rock is internally consistent. K (measured T/b) and thickness
#     stay from the pin -- they are the location's data. [Freeze & Cherry 1979]
# ---------------------------------------------------------------------------
#     Values are chosen to be REPRESENTATIVE of, and INSIDE, each regime's
#     training support (so the ML surrogate stays valid under the toggle rather
#     than always tripping the OOD guard). Porous phi_mobile 0.06 sits in the
#     training porous range [0.01, 0.08]; n_total from TOTAL_POROSITY typicals.
REGIME_ARCHETYPE = {
    "fractured": {"phi_mobile": 0.008, "n_total": 0.03, "grain_density": 2700.0},
    "porous":    {"phi_mobile": 0.060, "n_total": 0.30, "grain_density": 2650.0},
}

# ---------------------------------------------------------------------------
# 5d. Restoration (aquifer clean-up) phase. Texas practice: multi-pore-volume
#     sweep with strong net extraction after mining stops. Modelled as:
#     front HELD during restoration (active hydraulic control), source strength
#     stepped down to residual_fraction * C0 at the end of restoration, and a
#     clean-water replacement front launched from the source plane (Domenico
#     superposition). residual_fraction is derived at runtime from the Texas
#     'Final Post-restoration' / 'End of Mining' sheets; these are fallbacks.
# ---------------------------------------------------------------------------
RESTORATION_FALLBACK_RESIDUAL = {
    "uranium_ppb": 0.30, "sulfate_mg_l": 0.50, "tds_mg_l": 0.50,
}

# ---------------------------------------------------------------------------
# 6. Operational envelope for the synthetic loop (Phase 2) -- realistic ISR ranges,
#    WIDENED (2026-07 review) to cover the dashboard sliders so served inputs
#    stay inside training support. Q_in injection, bleed fraction
#    (Q_out = Q_in*(1+bleed)), operation years. Texas *production* bleed is
#    typically 0.5-3 %; the range extends to 0-8 % to cover no-bleed failure
#    states and aggressive containment. [ISRGOL]
# ---------------------------------------------------------------------------
OPERATIONAL_RANGES = {
    "injection_rate_m3_day": (200.0, 8000.0),   # wellfield-scale Q_in
    # DECOUPLED containment knob (Phase-2 v2): net extraction Q_net = Q_out-Q_in
    # is sampled INDEPENDENTLY of Q_in (clipped to <= 10% of Q_in), so the model
    # can separate "more throughput" from "more capture". bleed_fraction is the
    # derived diagnostic Q_net/Q_in and its envelope is the clip bound.
    "net_extraction_m3_day": (0.0, 400.0),
    "bleed_fraction":        (0.0, 0.10),       # derived: Q_net/Q_in (clip bound)
    "operation_years":       (1.0, 20.0),       # active mining duration
    "horizon_years":         (0.0, 20.0),       # total sim time incl. post-closure
    "hydraulic_gradient":    (0.0005, 0.02),    # dimensionless i (dashboard slider)
    "wellfield_width_m":     (100.0, 800.0),    # source full-width
    "restoration_years":     (0.0, 10.0),       # post-mining clean-up sweep
}

# Operational irregularities (Phase-2 v2): industrial reality injected into the
# synthetic loop. Downtime episodes suspend hydraulic capture (eta -> 0 while
# the pumps are down => effective eta = eta*(1 - downtime_fraction)); the
# seasonal gradient amplitude and bleed drift enter the parameter-uncertainty
# Monte Carlo (they widen the outcome distribution rather than shift the mean).
# Placeholder ranges -- to be re-fit from TCEQ excursion records + the CGWB
# water-level seasonality (plan Phase 5).
IRREGULARITY = {
    "downtime_episodes_per_year": (0.0, 2.0),
    "downtime_days_per_episode":  (5.0, 30.0),
    "downtime_fraction_max":      0.30,
    "gradient_seasonal_amp":      (0.0, 0.40),   # relative seasonal swing of i
    "qnet_drift_mult":            (0.6, 1.3),    # bleed-stream drift (MC)
    "restoration_prob":           0.5,           # scenarios with a restoration phase
    "residual_noise_mult":        (0.7, 1.5),    # spread around Texas residuals
}

# Lixiviant-contacted SOURCE zone grows (capped) with cumulative throughput.
# Driver = BULK volumes injected, BV = Q_in * min(t, t_op) / V_pattern_bulk
# (pattern bulk volume pi*(W/2)^2*b) -- porosity-independent by design, so the
# coupling stays LIVE in fractured rock (tiny phi) instead of saturating, and
# time-consistent: at t < t_op only the volume injected SO FAR widens the source.
#   W_eff(t) = W * (1 + SOURCE_BV_GAIN * tanh(BV(t) / SOURCE_BV_REF))
# tanh-saturating so the source never exceeds (1 + gain) x the permitted width.
SOURCE_BV_GAIN = 0.40    # max +40% effective source width at high throughput
SOURCE_BV_REF = 2.0      # bulk pattern volumes at which widening half-saturates

# Source-term signatures (end-of-mining minus baseline) are derived at runtime
# from the Texas sheets; these are only fallbacks if those rows are unusable.
FALLBACK_SOURCE_CONC = {
    "uranium_ppb":  (500.0, 5000.0),   # alkaline ISR pregnant fluid is U-rich
    "sulfate_mg_l": (500.0, 3000.0),
    "tds_mg_l":     (1500.0, 8000.0),
}

# Geographic bounds of Jharkhand (for validating dropped pins / dashboard map).
JHARKHAND_BOUNDS = {"lon_min": 83.3, "lon_max": 88.0, "lat_min": 21.9, "lat_max": 25.5}

# Far-field drainage context (Stage B). GLO-30 flow-accumulation analysis
# (data_prep.drainage) found perennial drainage (>=120 km2 contributing area) is
# typically within ~6 km (median) / ~13 km (P90) across Jharkhand's dissected
# terrain. A predicted plume reach beyond this scale is physically overstated by
# the unbounded down-gradient geometry -- the plume would meet a stream and
# discharge. Used for a QUALITATIVE note only (per-pin channel placement from the
# coarse DEM is unreliable -- see data_prep.drainage), never to cap a label.
FARFIELD_DRAINAGE_MEDIAN_KM = 6.0
FARFIELD_DRAINAGE_P90_KM = 13.0

# ---------------------------------------------------------------------------
# 7. Ore-body masking (Module 2). ISR leaches uranium only where uranium ore
#    exists; elsewhere the lixiviant perturbs non-radiological chemistry only.
#    The 3-tier source-term policy for the URANIUM species:
#      deposit -> full Texas-derived C0 (real ore)
#      belt    -> BELT_C0_FRACTION x C0  (Singhbhum envelope = low-confidence,
#                 explicitly hypothetical ore)
#      none    -> trace only: max(NON_ORE_U_TRACE_MULT x ambient, floor). An
#                 oxygenated alkaline lixiviant mobilizes a little U from ordinary
#                 crustal rock (~2-4 ppm U), so "a few x ambient" is more honest
#                 than exactly-baseline, and stays FAR below the BIS 30 ppb limit
#                 -> the incremental uranium plume is ~zero by construction.
#    Sulfate / TDS are untouched by tier (reagent chemistry exists wherever
#    fluid is injected). The name below must match the CSV's envelope row.
# ---------------------------------------------------------------------------
ORE_BELT_NAME = "Singhbhum Thrust Belt (regional envelope)"
ORE_DEPOSIT_BUFFER_DEG = 0.0045      # ~500 m halo around each surveyed deposit
BELT_C0_FRACTION = 0.30              # prospective-belt hypothetical source strength
NON_ORE_U_TRACE_MULT = 3.0          # trace-leach uranium = 3 x ambient background
NON_ORE_U_TRACE_FLOOR_PPB = 5.0     # absolute floor for the trace term

# D4: grade-scaled deposit C0. The Texas-derived uranium C0 encodes the Texas ISR
# reference ore grade; each surveyed deposit's C0 is rescaled by its IAEA-UDEPO
# grade relative to this. Texas roll-front ISR ore ~0.05-0.10% U3O8 = 0.04-0.08%
# U -> 0.05% U as the representative the C0 midpoint sits in (both sides %U).
URANIUM_GRADE_REF_PCT = 0.05        # %U; deposit grade == this -> C0 unchanged

# ---------------------------------------------------------------------------
# 8. Vertical stratification (Module 5A -- 2.5D). Hard-rock Jharkhand profile:
#    Layer 1 (0-30 m)     weathered / saprolite PHREATIC aquifer -> village wells.
#    Layer 2 (30 m..ore)  fractured bedrock, SEMI-confining -- anisotropic K, NOT
#                         impermeable. Vertical fracture connectivity is exactly
#                         the excursion pathway; there is rarely a clean aquitard.
#    Layer 3 (ore_depth)  mineralized shear zone = hypothetical ISR target.
#    The deep horizontal plume (2D area/migration/compliance) is UNCHANGED by
#    this module: the plan-view solve is depth-integrated and the vertical factor
#    is used ONLY in the shallow-impact screening below -- so those metrics keep
#    their existing trained surrogate (no retraining). This adds a SCREENING
#    estimate of how much could reach Layer 1 (transparent index, not calibrated).
#    Defaults are chosen so the estimate DISCRIMINATES by depth / anisotropy /
#    gradient rather than pinning at 0 or 1. Re-fit later from CGWB NAQUIM +
#    UCIL/AMD vertical-excursion records (plan Phase 5/6).
# ---------------------------------------------------------------------------
VERTICAL = {
    "layer1_base_m": 30.0,           # base of the shallow drinking-water aquifer
    "alpha_V_ratio": 0.025,          # alpha_V / alpha_L (Gelhar 1992: 0.01-0.05)
    # The confining Layer 2 is fractured HARD ROCK in both regime interpretations
    # (it is the bedrock between saprolite and ore), so its mobile porosity is
    # FIXED at the fractured value. Toggling the ORE-zone regime must not change
    # the barrier's porosity -- feeding the ore regime's phi into the confining
    # leakage was a conflation (fixed 2026-07-06): it made "porous" spuriously
    # safer via a porosity that does not belong to the confining layer.
    "phi_confining": 0.008,          # Layer-2 fractured-bedrock mobile porosity
    # Vertical anisotropy Kv/Kh is where the regime DOES belong: fractured rock's
    # sub-vertical joint sets raise vertical conductivity; weathered/porous is more
    # layered (Kv << Kh). This is the physically-correct channel for "fractured is
    # riskier vertically". [screening values -- re-fit from GSI Bhukosh structure]
    "Kv_Kh_by_regime": {"fractured": 0.03, "porous": 0.008},
    "upward_gradient": 0.005,        # net upward head gradient (injection driven)
    "wellbore_failure_prob": 0.05,   # base rate: casing / legacy-borehole shortcut
    "ore_depth_default_m": 150.0,
    "ore_thickness_default_m": 20.0,
    "ore_depth_range_m": (50.0, 600.0),
    "ore_thickness_range_m": (2.0, 100.0),
}

# Reproducibility
RANDOM_SEED = 42
