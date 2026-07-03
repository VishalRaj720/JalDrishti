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
# ---------------------------------------------------------------------------
DUAL_POROSITY = {
    "enabled_for": ("fractured",),
    "beta_range": (2.0, 8.0, 20.0),   # (low, central, high) capacity ratio
    "mass_transfer_omega": 1e-3,      # first-order rate [1/day], slow matrix diffusion
}

# ---------------------------------------------------------------------------
# 6. Operational envelope for the synthetic loop (Phase 2) -- realistic ISR ranges.
#    Q_in injection, bleed fraction (Q_out = Q_in*(1+bleed)), operation years.
#    Texas bleed is typically 0.5-3 % to hold the cone of depression. [ISRGOL]
# ---------------------------------------------------------------------------
OPERATIONAL_RANGES = {
    "injection_rate_m3_day": (200.0, 5000.0),   # wellfield-scale Q_in
    "bleed_fraction":        (0.005, 0.030),    # (Q_out - Q_in)/Q_in
    "operation_years":       (1.0, 12.0),       # active mining duration
    "horizon_years":         (0.0, 20.0),       # total sim time incl. post-closure
    "hydraulic_gradient":    (0.0005, 0.02),    # dimensionless i (dashboard slider)
    "wellfield_width_m":     (100.0, 800.0),    # source half-width proxy
}

# Lixiviant-contacted SOURCE zone grows (capped) with gross pore-volume
# throughput PV: injecting more solution over more time flushes/contacts a
# larger rock volume, enlarging the contaminated source. This makes the
# hydrogeology law "higher injection -> larger plume" hold in the physics itself
# (so the Phase-3 monotone +1 on Q_in is faithful, not forced), while BLEED /
# containment still governs downgradient excursion. tanh-saturating so the
# source can never blow up beyond (1 + SOURCE_PV_GAIN) x the permitted width.
SOURCE_PV_GAIN = 0.40    # max +40% effective source width at high throughput
SOURCE_PV_REF = 8.0      # pore-volume scale at which widening half-saturates

# Source-term signatures (end-of-mining minus baseline) are derived at runtime
# from the Texas sheets; these are only fallbacks if those rows are unusable.
FALLBACK_SOURCE_CONC = {
    "uranium_ppb":  (500.0, 5000.0),   # alkaline ISR pregnant fluid is U-rich
    "sulfate_mg_l": (500.0, 3000.0),
    "tds_mg_l":     (1500.0, 8000.0),
}

# Geographic bounds of Jharkhand (for validating dropped pins / dashboard map).
JHARKHAND_BOUNDS = {"lon_min": 83.3, "lon_max": 88.0, "lat_min": 21.9, "lat_max": 25.5}

# Reproducibility
RANDOM_SEED = 42
