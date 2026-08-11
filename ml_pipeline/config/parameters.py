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
    # Radium-226 (fix 3.9). BIS IS-10500 sets no Ra-226 limit; the applicable
    # value is the WHO guidance level for naturally occurring Ra-226 in drinking
    # water, 1 Bq/L = 1000 mBq/L. (India's AERB sets a radiological uranium
    # guideline of 60 ug/L but defers to WHO for radium.)
    "radium_226_mbq_l": 1000.0,
}

# ---------------------------------------------------------------------------
# 4b. RADIUM-226 as a modelled species   [fix 3.9, 2026-08-01]
# ---------------------------------------------------------------------------
# Ra-226 is the standard co-regulated ISR licensing metric alongside uranium.
# ANALYTICAL-ENGINE ONLY: the deployed ML surrogate was trained on a 3-species
# one-hot, so a Ra request is served by the physics engine and the ML head is
# bypassed with an explicit status (adding it to the surrogate is a deliberate
# retrain, not a silent extension).
#
# SOURCE TERM -- measured, local, and the reason this fix was buildable at all:
# Jaduguda untreated mine-water effluent Ra-226 = 40-1706 mBq/L, geometric mean
# 371.3, GSD 2.6 (Sethy et al. 2013, Radiat. Prot. Environ. 36(1):32-37,
# DOI 10.4103/0972-0464.121824; full text archived in Datasets/phase1_sources/).
# Same caveat as the uranium C0 (see JADUGUDA_MINE_WATER_U_PPB): this is passive
# mine water, not an engineered lixiviant, so it is a measured LOWER BOUND. It
# is used directly as the Ra source term because -- unlike uranium -- there is
# no Texas ISR radium series to transfer from, so the local measurement is the
# best available anchor rather than merely a cross-check.
RADIUM_SOURCE_MBQ_L = {"min": 40.0, "gm": 371.3, "max": 1706.0, "gsd": 2.6}
# Which statistic to serve as C0. The GEOMETRIC MEAN (371.3) sits BELOW the WHO
# 1000 mBq/L guidance level, so serving it makes every screening result exactly
# zero -- a true statement about that particular sample statistic, but an
# under-conservative and uninformative screen, because (a) the underlying data
# is passive mine water rather than an engineered lixiviant, i.e. already a
# lower bound, and (b) taking a central statistic of a lower bound compounds the
# optimism. The MEASURED MAXIMUM (1706 mBq/L) is therefore the screening default:
# it is still a real observed value at this ore body, and it does exceed the WHO
# level, so the tool answers "where could this plausibly matter" rather than
# always "nowhere". The full distribution is reported to the user either way.
# Countervailing evidence kept in view: Sethy et al. note only <1% of the ore's
# radium is leached during acid processing, so radium supply is genuinely poor
# -- which is why the max is used rather than scaling up by a uranium-like
# ISR factor.
RADIUM_SOURCE_STATISTIC = "max"
# Regional background: uranium-mine-area groundwater Ra-226 ~ 23 mBq/L, with
# potable wells spanning <3.5-208 mBq/L (BARC, J. Environ. Radioactivity 99
# (2008) 1245; Jaduguda ground-water ingestion-dose study).
RADIUM_BACKGROUND_MBQ_L = 23.0

# Kd (L/kg). Source: EPA 402-R-04-002C Vol III, archived at
# Datasets/phase1_sources/EPA_Kd_VolIII_As_Ra.pdf.
#
# WHICH NUMBERS IN THAT DOCUMENT -- this matters, and an earlier version of this
# block got it wrong (see the revision note inside RADIUM_KD_RANGES below).
# The document contains TWO very different radium datasets:
#   (a) p.95  MEASURED Kd for radium on a SANDY SEDIMENT IN GROUNDWATER
#             (6.7 / 12.6 / 26.3 / 26.3 mL/g at pH 6 / 7 / 8 / 9)  <-- USED HERE
#   (b) Table 5.28, the Thibault et al. (1990) SOIL compilation
#             (Sand 500, Silt 36,000, Clay 9,100, Organic 2,400)   <-- NOT the anchor
# This tool models a GROUNDWATER plume, so (a) is the applicable medium. The
# same EPA document warns of (b) at p.96 that those values "are unusually large,
# and orders of magnitude greater than those reported by most researchers".
# (b) is retained ONLY as the immobile upper end member of the sampled band, so
# the BARC (2008) tailings-pond observation stays reachable by a Monte-Carlo draw.
#
# Chemistry that justifies radium sorbing more strongly than alkaline uranium at
# all: Ra exists only as the uncomplexed divalent Ra2+ over pH 3-10 (ibid. p.90)
# and has the largest ionic radius / weakest hydration of the alkaline earths
# (ibid. p.91), whereas an alkaline lixiviant carries uranium as weakly-sorbing
# uranyl-carbonate. In THIS plume the margin is ~5x (porous) to ~13x (fractured)
# on the central values, NOT the three-to-four orders of magnitude the soil
# compilation would imply -- because the same document (p.90/p.94/p.95) records
# that radium sorption falls with ionic strength, and this plume carries
# TDS 1,500-8,000 mg/L by construction.
#   fractured -> quartz/silicate fracture-wall matrix, low CEC: sand-like.
#   porous    -> weathered saprolite with clay + Fe/Mn oxides: clay/organic-like.
RADIUM_KD_RANGES = {
    # (lo, mode, hi) L/kg -- REVISED 2026-08-06 after the served answer made
    # radium absolutely immobile (front 0.003 m at 50 yr, retardation 444,594),
    # a state no Monte-Carlo draw could escape because even the old LOWER bound
    # of 57 L/kg still gives ~50,000x retardation. A model whose bands cannot
    # express "radium moved" is asserting impossibility, not uncertainty.
    #
    # WHY THE OLD VALUES WERE WRONG FOR THIS PLUME. They came from the Thibault
    # et al. (1990) SOIL compilation (EPA 402-R-04-002C Vol III Table 5.28).
    # That same EPA document says of those numbers, p.96:
    #   "The Kd values reported by Nathwani and Phillips (1979b) are unusually
    #    large, and orders of magnitude greater than those reported by most
    #    researchers."
    # and this tool models a GROUNDWATER plume, not soil. Worse, it was applying
    # a freshwater Kd to a plume it simultaneously simulates as carrying
    # TDS 1,500-8,000 mg/L, while the same document states, p.90/p.94:
    #   "The adsorption of radium is strongly dependent on ionic strength and
    #    concentrations of other competing ions in that adsorption of radium
    #    decreases with increasing ionic strength."
    # with the alkaline-earth exchange affinity Ra2+ > Ba2+ > Sr2+ > Ca2+ > Mg2+,
    # so an alkaline-ISR lixiviant's own carbonate/Ca load displaces Ra.
    #
    # THE NEW NUMBERS -- every one from the already-cited EPA document:
    #   lo   6.7  L/kg  measured, radium on SANDY SEDIMENT IN GROUNDWATER, pH 6
    #                   (p.95: "6.7, 12.6, 26.3, and 26.3 ml/g at pH values of
    #                    6, 7, 8, and 9"). ml/g == L/kg.
    #   mode 13.2 L/kg  the pH 8-9 measured value (26.3) halved, because p.95
    #                   reports "Radium sorption in the high ionic strength
    #                   groundwater experiment was less than 50 percent of the
    #                   sorption measured in the lower ionic strength
    #                   groundwater solution." Alkaline ISR is the high-ionic-
    #                   strength case by construction.
    #   hi   the retained Thibault soil values -- so the IMMOBILE end member
    #                   stays inside the sampled range and the BARC (2008)
    #                   observation that radium does not migrate from the
    #                   Jaduguda tailings remains reachable by a draw.
    #
    # Net effect: the band now spans ~2.5 orders of magnitude and contains BOTH
    # hypotheses -- mobile radium in a high-TDS lixiviant, and the immobile
    # tailings-pond behaviour actually observed at Jaduguda. It no longer picks
    # one and hides the choice.
    "fractured": (6.7, 13.2, 2000.0),
    "porous":    (6.7, 13.2, 9100.0),
}

# Radioactive decay: Ra-226 half-life 1600 yr. Over this tool's 0-50 yr horizon
# that removes <3% of the activity, so decay is NOT modelled as a separate sink
# -- omitting it is conservative (over-predicts) and avoids implying a precision
# the rest of the model does not have. Recorded here so the omission is explicit.
RADIUM_HALFLIFE_YEARS = 1600.0

# ---------------------------------------------------------------------------
# Ra-226 INGROWTH from deposited uranium -- DELIBERATELY NOT MODELLED
# ---------------------------------------------------------------------------
# Reasonable question (user, 2026-08-06): the engine immobilises migrating U(VI)
# as U(IV) by redox trapping, and Ra-226 is a U-238 daughter -- so should radium
# not appear wherever uranium was deposited, even where dissolved radium never
# reached?
#
# In principle yes; on this tool's horizon, no, by FIVE orders of magnitude at
# 50 years. The chain is
#   U-238 -> Th-234 (24.1 d) -> Pa-234m (1.2 min) -> U-234 (245,500 yr)
#         -> Th-230 (75,380 yr) -> Ra-226 (1,600 yr)
# and freshly deposited natural uranium carries U-234 already near secular
# equilibrium, so the chain from there is TWO sequential steps, not one:
# Th-230 must itself grow in (rate-limited by its own 75,380 yr half-life)
# BEFORE it can feed Ra-226. Solving the Bateman pair for a constant U-234
# parent gives the fraction of secular-equilibrium Ra-226 activity:
#
#       A_Ra/A_U = 1 - [lambda_Ra*exp(-lambda_Th*t) - lambda_Th*exp(-lambda_Ra*t)]
#                      / (lambda_Ra - lambda_Th)
#
#       1 yr  2.0e-7 %      100 yr  2.0e-3 %
#      10 yr  2.0e-5 %    1,000 yr  0.173 %
#      50 yr  4.9e-4 %   10,000 yr  6.84 %
#
# CORRECTION 2026-08-10: an earlier version of this block tabulated
# 1 - exp(-lambda_Th230 * t) -- which is the ingrowth of Th-230, not of Ra-226 --
# and so overstated the radium by up to 4,600x (93x at the 50 yr horizon). The
# conclusion is unchanged and in fact STRENGTHENED, which is why the omission
# stands; only the arithmetic justifying it needed repair.
#
# So even if EVERY migrating uranium atom immobilised on day one, the radium it
# generates by year 50 sits ~2e5 x below the uranium activity that produced it,
# and then has to partition into water against a Kd of 6.7-2,000 L/kg (see
# RADIUM_KD_RANGES) before it could be measured. Modelling it would add
# machinery whose output is indistinguishable from zero at every time this tool
# can display.
#
# It is NOT negligible on geological timescales, which is precisely why the
# Singhbhum ore bodies carry Ra-226 in secular equilibrium today. If the horizon
# is ever extended past ~1,000 yr, this omission must be revisited.
RADIUM_INGROWTH_MODELLED = False
TH230_HALFLIFE_YEARS = 75380.0   # the bottleneck, recorded for that revisit

# ---------------------------------------------------------------------------
# Rn-222 -- DELIBERATELY NOT MODELLED, and NOT because the physics zeroes it
# ---------------------------------------------------------------------------
# Radon-222 is a standard ISR licensing metric and fidelity row 3.9 has carried
# it as an open item. Assessed properly 2026-08-10 rather than left open, and
# the first hypothesis tested here was WRONG, so both results are recorded.
#
# HYPOTHESIS TESTED: "a 3.82-day half-life means radon cannot survive transport
# to the compliance ring, so it is out of scope by physics." Measured against
# this model's OWN velocity envelope (18,000 training rows, seepage velocity v):
#       v p50  =  0.20 m/day -> 100 m in 507 d = 133 half-lives -> 1e-40 survives
#       v p99  = 14.33 m/day -> 100 m in 7.0 d = 1.8 half-lives -> 0.28 survives
#       v max  = 18.99 m/day -> 100 m in 5.3 d = 1.4 half-lives -> 0.38 survives
#   4.3% of the envelope retains >1% of the radon at 100 m.
# So the hypothesis holds for the MEDIAN case by forty orders of magnitude and
# FAILS for the fastest fractured channels. Radon is not universally immobile
# here, and claiming so would have been a convenient error.
#
# WHY IT IS STILL NOT MODELLED -- two blockers, both real:
#   (1) NO SOURCE TERM. The one local measurement set for this ore body (Sethy
#       et al. 2013, the same paper behind JADUGUDA_MINE_WATER_U_PPB and
#       RADIUM_SOURCE_MBQ_L) reports dissolved uranium and Ra-226 only; it
#       carries no Rn-222 column, and no Texas ISR radon series exists to
#       transfer from. This is the same wall as fidelity row 3.8: sorption and
#       decay behaviour are known, the ISR source strength is not.
#   (2) WRONG PATHWAY. Radon's governing exposure route at an ISR facility is
#       ATMOSPHERIC -- degassing at wellheads, header houses and the processing
#       circuit -- which a saturated-zone groundwater transport model cannot
#       represent at all. Adding a dissolved-radon plume would answer a question
#       that is not the one radon is regulated on.
# Recorded as a DATA + SCOPE limitation, not as a physics result.
RADON_222_HALFLIFE_DAYS = 3.8235
RADON_222_MODELLED = False

# Training C0 range for the synthetic generator (2026-08-02 retrain). Radium has
# no Texas ISR series to sample a source envelope from (see RADIUM_SOURCE_MBQ_L
# above), so the generator draws C0 uniformly over the FULL range the SERVE path
# can ever produce: background-only at a non-ore pin (23 mBq/L) up to the
# measured Jaduguda maximum used as the deposit ceiling (1706 mBq/L). This makes
# the trained feature support match the served input support exactly, rather
# than the model ever extrapolating on its own training range.
RADIUM_C0_TRAINING_RANGE_MBQ_L = (RADIUM_BACKGROUND_MBQ_L, RADIUM_SOURCE_MBQ_L["max"])

# Restoration endpoint residual for radium (C_rest/C0 after a reference sweep).
# There is NO Texas post-restoration radium series -- the sheets that give
# uranium 0.066, sulfate 0.146 and TDS 0.367 carry no radium column -- so this
# is DERIVED FROM THE SORPTION PHYSICS, not measured, and is flagged as such.
#
# Derivation: an aquifer sweep is a pore-volume flush, and removing a sorbed
# solute takes on the order of Rd pore volumes, so the fraction remaining after
# N pore volumes goes as exp(-N/Rd). Anchoring on uranium, whose PAIRED measured
# endpoint is 0.0600 (texas_loader.texas_restoration_residual):
#       N/Rd_U = ln(1/0.0600) = 2.813
# Applying the SAME sweep to radium with retardation Rd = 1 + rho_b*Kd/n_total
# (physics.transport.matrix_retardation, i.e. the same expression the transport
# engine uses -- not the "Rd scales with Kd" shortcut the previous version took):
#
#   regime      Kd_U   Kd_Ra   Rd_U     Rd_Ra     Rd_U/Rd_Ra   residual_Ra
#   fractured   1.00   13.2     89.9    1174.7      0.0765        0.806
#   porous      2.50   13.2     16.5      82.6      0.1992        0.571
#
# SERVED VALUE = 0.81, the FRACTURED result: every Singhbhum deposit pin resolves
# to fractured schist, and it is also the higher (dirtier, safety-conservative)
# of the two. A single scalar is consistent with how uranium/sulfate/TDS are
# handled -- their Texas endpoints are likewise one number applied to both regimes.
#
# !! CORRECTED 2026-08-10 -- THIS CONSTANT HAD GONE STALE AND WAS A TRAINING LABEL. !!
# It read 0.99, computed from Kd values this config no longer holds: the comment
# named "fractured: 500 vs 1.0" and "porous: 2400 vs 2.5", i.e. the Thibault SOIL
# compilation that the 2026-08-06 rebase (see RADIUM_KD_RANGES) replaced with
# measured groundwater values. Re-running the SAME derivation on the CURRENT
# constants gives 0.806/0.571, not 0.99 -- so the model was asserting that a
# hydraulic sweep removes 1% of the radium source while its own stated physics
# said 19-43%. The anchor was stale twice over: it also still used the
# pre-V-3 unpaired uranium endpoint 0.066 instead of the paired 0.0600.
# `restoration_endpoint_for()` feeds BOTH synthetic.generate and ml.predict, so
# this value is baked into the training labels and correcting it forces a re-bake.
#
# HONEST LIMITATION -- N IS AN EFFECTIVE PARAMETER, NOT A PORE-VOLUME COUNT.
# The uranium anchor implies N_eff = 2.813*Rd_U = 46 (porous) to 253 (fractured)
# pore volumes, against the 18.6 PV median actually extracted across the 13 Texas
# production areas. The gap is real and expected: commercial restoration is
# groundwater sweep PLUS reverse-osmosis permeate reinjection and reductant
# addition, which strips sorbed uranium chemically rather than by flushing alone.
# So N is a fitted sweep STRENGTH anchored on the measured uranium endpoint, and
# only the RATIO between species carries physical meaning here. Recorded rather
# than hidden: this is a scenario assumption, not a measurement.
#
# CONSEQUENCE, stated plainly: the restoration slider stays weak for radium (19%
# removal at the reference sweep, against 94% for uranium). That is the
# decision-relevant answer -- radium is poorly remediable by pumping -- but it is
# no longer the "essentially inert" control the stale 0.99 produced. (Surface
# treatment at Jaduguda removes >95% of Ra via BaCl2 co-precipitation, but that
# is an effluent-treatment plant, not aquifer restoration.)
RADIUM_RESTORATION_RESIDUAL = 0.81


# ---------------------------------------------------------------------------
# 1b. THE SPECIES REGISTRY -- one definition, imported everywhere
#     [remediation 2026-08-05, review.md finding #9]
# ---------------------------------------------------------------------------
# The species tuple used to be re-declared in six places (ml/dataset.py,
# ml/predict.py x2, dashboard/resolve.py x2, synthetic/generate.py) and the
# per-species background defaults in two. That duplication is not cosmetic --
# it is this project's recurring defect class, and it has caused real breakage
# more than once: a KeyError the first time radium was added to a species loop,
# and (found by the audit) the radium restoration endpoint diverging between the
# training generator and the serve path because each held its own view of what a
# species is. dashboard/resolve.py even carried an ML_SPECIES copy that nothing
# imported, free to drift from the one the server actually gated on.
#
# SPECIES     -- every species the ANALYTICAL engine can solve.
# ML_SPECIES  -- the subset the DEPLOYED surrogate was trained on. Kept as a
#                separate name (not an alias) so a future analytical-only
#                species, e.g. Rn-222, has the same safe bypass path radium used
#                before its retrain: the server checks membership and reports an
#                explicit status rather than feeding an unknown one-hot.
#                Currently equal; test_phase1_fixes pins this against the card.
SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")
ML_SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l")

# EXCURSION-ONLY CONSTITUENTS  [2026-08-11]
# ---------------------------------------------------------------------------
# Solved by the ANALYTICAL engine for the ISR excursion test only. Deliberately
# NOT in SPECIES, because SPECIES is what synthetic.generate iterates to bake
# training labels (900 scenarios x 5 times x len(SPECIES)) -- adding a member
# there would force a full re-bake and retrain for a constituent that is a
# TRACER, not a contaminant of concern, and that the surrogate has no reason to
# predict. Every registry below is read by the generator only as
# `d[sp] for sp in SPECIES`, so these extra keys are inert to training.
#
# WHY CHLORIDE, AND WHY ONLY CHLORIDE (measured, not assumed -- see review of
# 2026-08-11). Enrichment measured on this project's own paired Texas
# baseline/end-of-mining data (7 mines), then tested against JHARKHAND
# background rather than Texas background:
#
#   indicator      TX enrich   TX lixiviant   JH background   contrast   f_min*
#   sulfate           9.5x        1123 mg/L        38 mg/L      29.6x     0.7%
#   chloride          1.7x         776 mg/L        78 mg/L       9.9x     2.2%
#   TDS               3.1x        3710 mg/L       490 mg/L       7.6x     3.0%
#   bicarbonate       2.2x         625 mg/L       250 mg/L       2.5x    13.3%
#   * f_min = smallest fraction of the source that must reach the ring to trip
#     a +20% UCL. Lower is a more sensitive indicator.
#
# Two findings drove the choice, and both invert the naive assumption:
#  1. BICARBONATE/ALKALINITY -- the canonical alkaline-ISR lixiviant signature
#     and a member of the licensed US triad -- is the WEAKEST candidate HERE,
#     because Jharkhand hard-rock groundwater is already bicarbonate-dominated
#     (250 mg/L median). The property that makes it diagnostic in Texas makes it
#     nearly useless in Singhbhum. Deliberately NOT added.
#  2. CHLORIDE is the reverse: the weakest ENRICHER in Texas (its baseline there
#     is already 384 mg/L in coastal sediments) but an excellent indicator here,
#     where background is 78 mg/L. It is also the only PERFECTLY conservative
#     candidate (Kd = 0), so unlike sulfate it is immune to the sulfide-oxidation
#     false-alarm mechanism NUREG-1569 p.137 warns about -- a mechanism that is
#     ELEVATED in Singhbhum, a polymetallic sulphide province (see
#     U_ATTENUATION_MODE_BY_ZONE). That interference-independence is why a
#     2-of-2 panel of sulfate+TDS was fragile: both can be perturbed together.
EXCURSION_ONLY_SPECIES = ("chloride_mg_l",)

# One-hot column names, DERIVED from SPECIES so the two can never disagree.
SPECIES_ONEHOT = [f"is_{sp}" for sp in SPECIES]

# Fallback ambient background when the nearest CGWB well has no value for a
# species. Radium has no CGWB column at all, so it always takes its measured
# BARC regional value.
BACKGROUND_DEFAULTS = {
    "uranium_ppb": 1.0,
    "sulfate_mg_l": 20.0,
    "tds_mg_l": 300.0,
    "radium_226_mbq_l": RADIUM_BACKGROUND_MBQ_L,
    # excursion-only; CGWB median is 78 mg/L over 397/397 wells, so this
    # fallback is used only if a pin somehow resolves to a well without Cl
    "chloride_mg_l": 78.0,
}

# Display units, so the API/frontend cannot invent a different one per surface.
SPECIES_UNITS = {
    "uranium_ppb": "ppb", "sulfate_mg_l": "mg/L",
    "tds_mg_l": "mg/L", "radium_226_mbq_l": "mBq/L",
    "chloride_mg_l": "mg/L",              # excursion-only
}


def background_default_for(species: str) -> float:
    """Ambient background to use when the nearest well carries no measurement."""
    return float(BACKGROUND_DEFAULTS[species])


def kd_range_for(species: str, regime: str) -> tuple:
    """(lo, central, hi) Kd [L/kg] for a species x regime. Single source of
    truth so the serve path (resolve.py) and the Monte-Carlo draw
    (synthetic.generate._draw_params) cannot diverge -- radium lives in its own
    table because it sorbs orders of magnitude more strongly than alkaline U."""
    if species == "radium_226_mbq_l":
        return RADIUM_KD_RANGES[regime]
    return KD_RANGES[species][regime]

# Monitoring/compliance ring distance DOWNGRADIENT OF THE WELLFIELD EDGE.
# The Domenico source plane sits at the downgradient edge (conservative areal-
# source convention), so the ring is at x = COMPLIANCE_BUFFER_M in solver
# coordinates and at (W/2 + COMPLIANCE_BUFFER_M) from the wellfield centre pin.
# Single source of truth -- generate.py / predict.py / server.py import this.
#
# GROUNDED 2026-08-10 (was previously an uncited round number). US NRC
# NUREG-1569, "Standard Review Plan for In Situ Leach Uranium Extraction License
# Applications", Section 5.7.8.3, p.139:
#   "Previously approved in situ leach excursion monitoring systems used monitor
#    wells as far as 180 m [600 ft] and as near as 75 m [250 ft] from the well
#    field edge (NRC, 2001, Table 4-6). The licensee should be afforded some
#    discretion ... but should provide justification for distances greater than
#    about 150 m [500 ft]."
# 100 m therefore sits inside real licensed practice and below the threshold at
# which a regulator demands extra justification. The training envelope is built
# at this value, so changing it is a retrain -- but the SERVE path accepts a
# user-set ring anywhere in MONITOR_RING_RANGE_M and flags values outside it.
COMPLIANCE_BUFFER_M = 100.0
# Licensed range observed by NRC, used to bound the serve-time ring input and to
# tell a user when their ring would need regulatory justification.
MONITOR_RING_RANGE_M = (75.0, 180.0)
MONITOR_RING_JUSTIFY_BEYOND_M = 150.0
MONITOR_RING_CITATION = ("US NRC NUREG-1569 Sec. 5.7.8.3 p.139 (citing NRC 2001, "
                         "NUREG/CR-6733 Table 4-6): licensed perimeter monitor "
                         "wells 75-180 m from the well-field edge; justification "
                         "required beyond ~150 m")
# NUREG-1569 Sec. 5.7.8.3 p.140: "all monitor wells will be sampled for excursion
# indicators at least every 2 weeks during in situ leaching", and an acceptable
# technical basis for a wider ring is "a rigorous modeling demonstration that a
# theoretical excursion can be controlled at the monitor well locations within
# 60 days of detection" (p.139). Both are reported as detectability context.
MONITOR_SAMPLING_INTERVAL_DAYS = 14.0
EXCURSION_CONTROL_WINDOW_DAYS = 60.0

# Excursions are scored on the MINING-ATTRIBUTABLE (incremental) concentration:
#   breach if C_plume >= max(threshold - background, INCREMENTAL_FLOOR*threshold)
# The floor keeps the criterion meaningful when the ambient baseline already
# sits at/above the limit (otherwise any pin in naturally poor water would
# "breach" over the whole grid regardless of the mine).
# NOTE this is a MODELLING POLICY, not a physical constant -- it decides how much
# of a naturally-poor baseline the mine is held responsible for. Registered in
# UNGROUNDED_PARAMETERS as a policy choice so it is never mistaken for measured.
INCREMENTAL_FLOOR = 0.10

# ---------------------------------------------------------------------------
# 1c. ISR REGULATORY EXCURSION TEST (NUREG-1569)   [fix R-1, 2026-08-10]
# ---------------------------------------------------------------------------
# The health-limit breach above ("is the BIS/WHO limit exceeded at the ring")
# is NOT how a real ISR operation detects an excursion, and the difference is
# decision-relevant rather than cosmetic. US NRC NUREG-1569 Sec. 5.7.8.3:
#
#   p.138: "An excursion is defined to occur whenever TWO OR MORE excursion
#           indicators in a monitoring well exceed their upper control limits."
#   p.137: "A minimum of three excursion indicators should be proposed."
#          Indicators must be "parameters that are strong indicators of the in
#          situ leach process and that are NOT SIGNIFICANTLY ATTENUATED by
#          geochemical reactions in the aquifers."
#          "Conductivity, which is correlated to total dissolved solids, is also
#           [used]."
#   p.137: "URANIUM IS NOT CONSIDERED A GOOD EXCURSION INDICATOR because,
#           although it is mobilized by in situ leaching, IT MAY BE RETARDED by
#           reducing conditions in the aquifer."
#   p.137: "The use of SULFATE may give FALSE ALARMS because of induced
#           oxidation around a monitor well (Staub, 1986; Deutsch, 1985).
#           However, this should only be a problem if upper control limit values
#           are set too conservatively."
#   p.137: cations (Ca2+, Na+) are "generally not appropriate because they are
#           subject to ion exchange with the host rock".
#
# The regulator's own reason for excluding uranium is exactly what this model
# measures independently: fractured uranium carries beta_eff ~ 700 retardation
# plus redox trapping, and its excursion probability collapses to ~0.01 while
# TDS and sulfate retain meaningful values. So the tool was leading with the
# indicator the regulator explicitly rejects.
# THE PANEL: chloride + TDS(as conductivity) + sulfate, evaluated 2-of-3.
# Mirrors the STRUCTURE of the licensed US triad (chloride, conductivity, total
# alkalinity) with sulfate substituting for alkalinity, because in THIS aquifer
# sulfate is the most sensitive indicator (f_min 0.7%) while alkalinity is the
# least (13.3%) -- see EXCURSION_ONLY_SPECIES above for the measured basis.
ISR_EXCURSION_INDICATORS = ("chloride_mg_l", "tds_mg_l", "sulfate_mg_l")
# Why each member is here, surfaced to the user rather than left implicit.
ISR_INDICATOR_RATIONALE = {
    "chloride_mg_l": ("perfectly conservative (Kd = 0); the indicator licensed "
                      "US ISR programmes lead with. Immune to the sulfide-"
                      "oxidation false-alarm mechanism that affects sulfate"),
    "tds_mg_l": ("bulk salinity. NUREG-1569 p.137 names CONDUCTIVITY, 'which is "
                 "correlated to total dissolved solids' -- TDS is derived here "
                 "as EC x 0.64, so this IS the conductivity indicator"),
    "sulfate_mg_l": ("most sensitive indicator in this aquifer (Jharkhand "
                     "background is only 38 mg/L against a ~1123 mg/L "
                     "lixiviant). NUREG-1569 p.137 cautions that sulfate 'may "
                     "give false alarms because of induced oxidation around a "
                     "monitor well' -- a risk ELEVATED in the Singhbhum "
                     "polymetallic sulphide province, which is exactly why the "
                     "2-of-3 rule exists and why sulfate must never decide an "
                     "excursion alone"),
}
# Species that must NEVER be used as an ISR excursion indicator, with the reason.
ISR_NON_INDICATORS = {
    "uranium_ppb": "retarded by reducing conditions (NUREG-1569 p.137)",
    "radium_226_mbq_l": ("strongly sorbing alkaline earth; same retardation "
                         "objection as uranium, more so (NUREG-1569 p.137 "
                         "principle; Kd 6.7-2000 L/kg here)"),
}
ISR_EXCURSION_MIN_INDICATORS = 2      # "two or more" -- NUREG-1569 p.138
ISR_EXCURSION_REQUIRED_PANEL = 3      # "a minimum of three" -- NUREG-1569 p.137
# Candidate indicators DELIBERATELY EXCLUDED, with the measured reason. This
# replaced an earlier "not modelled" list that implied chloride and alkalinity
# were both missing gaps; the 2026-08-11 review found chloride was a real gap
# (now closed) and alkalinity was not a gap at all but a poor fit for this site.
ISR_INDICATORS_EXCLUDED = {
    "total_alkalinity_mg_l": (
        "WEAK IN THIS AQUIFER, not unavailable. HCO3 is present in both datasets "
        "(CGWB n=393; Texas End-of-Mining n=7 mines) and CO3 is 0.00 at every "
        "Jharkhand well, so total alkalinity ~ bicarbonate and could be built. "
        "It is excluded because Jharkhand groundwater is already bicarbonate-"
        "dominated (250 mg/L), giving a contrast of only 2.5x and requiring "
        "13.3% of the source to reach the ring before it trips -- 6x less "
        "sensitive than chloride and 19x less than sulfate. Adding it would "
        "enlarge the panel without improving detection."),
    "ph": ("moves the WRONG WAY -- measured 8.5 -> 7.0 across the Texas mines "
           "(0.85x). An upper-control-limit test cannot detect a decrease; it "
           "would need a separate lower-limit mechanism."),
    "calcium/magnesium/sodium/potassium": (
        "NUREG-1569 p.137 excludes cations as 'subject to ion exchange with the "
        "host rock'. They do enrich 2-5.7x in the Texas data, but that mobility "
        "is exactly what makes them unreliable as tracers."),
    "molybdenum/selenium/manganese/iron": (
        "contaminants of concern, not indicators: only 3 paired mines each and "
        "wildly inconsistent (Mo spans 0.4-144x; Fe DECREASES at one mine)."),
}

# UPPER CONTROL LIMIT rule. NUREG-1569 p.138 bounds the UCL from both sides:
#   "The upper control limit for each excursion indicator must generally be LESS
#    than the lowest concentration that typically occurs in the lixiviant while
#    the well field is in operation. Each upper control limit must also be
#    GREATER than the baseline concentration for its respective excursion
#    indicator."
# and permits, as one acceptable form, "the use of a simple percentage increase
# above baseline values".
#
# WHY THE PERCENTAGE FORM AND NOT THE STATISTICAL ONE. NUREG's preferred rules
# (mean + 5 standard deviations; student's t; ASTM D6312) all need a per-well
# TEMPORAL baseline distribution. Verified 2026-08-10 against the data on disk:
# waterQuality_jharkhand.csv holds 397 wells, ONE sample each, all from a single
# year -- zero repeat measurements at any site. There is no temporal variance to
# take 5 sigma of. Substituting the REGIONAL (spatial) spread was tested and
# rejected: sd(TDS) = 286.5 mg/L across the state gives mean + 5sd = 1,965 mg/L,
# an upper control limit near the BIS permissible limit itself, which would make
# the test fire only after the water was already unusable.
#
# !! SCENARIO ASSUMPTION -- the RULE is NUREG-sanctioned, the PERCENTAGE is not
# measured. !! Registered in UNGROUNDED_PARAMETERS. It is reported in the API
# response alongside the indicator ratios so a user can re-apply their own UCL.
ISR_UCL_BASELINE_INCREASE = 0.20      # UCL = baseline * (1 + this), then bracketed


def isr_upper_control_limit(baseline: float, lixiviant_c0: float,
                            increase: float | None = None) -> float:
    """Upper control limit for one ISR excursion indicator [same units as input].

    Implements the NUREG-1569 p.138 bracket exactly: a simple percentage
    increase above baseline, forced to stay strictly ABOVE the baseline and
    strictly BELOW the lixiviant concentration. If the source is so weak that
    the bracket collapses (C0 <= baseline), no UCL exists and the indicator
    cannot signal -- returned as +inf so the test can never fire on it.
    """
    inc = ISR_UCL_BASELINE_INCREASE if increase is None else float(increase)
    b = float(baseline)
    ucl = b * (1.0 + max(inc, 0.0))
    if not (lixiviant_c0 > b):
        return float("inf")
    # keep it inside the regulator's bracket: baseline < UCL < lixiviant
    return float(min(max(ucl, b * (1.0 + 1e-9)), lixiviant_c0 * (1.0 - 1e-9)))

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
    # EXCURSION-ONLY. Chloride is the archetypal conservative tracer: the Cl-
    # anion is excluded from the negatively-charged mineral surfaces that
    # dominate these aquifers, so Kd is 0 by definition, not by approximation.
    # That is precisely why NUREG-1569 licensees lead with it.
    "chloride_mg_l": {
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
#
# !! FIDELITY FLAW 3.4 -- beta AND omega ARE UNGROUNDED LOCALLY. !!
# The capacity ratio beta (2-20) and the mass-transfer rate omega are generic
# fractured-rock literature values, NOT Singhbhum measurements. beta sets the
# apparent retardation of every fractured plume this tool draws (Rd ~ 1+beta,
# which is where the UI's "Rd = 11" comes from), so it is one of the highest-
# leverage numbers in the model AND one of the least locally supported. A single
# local tracer test would anchor it. See the FRACTURE block above and
# JHARKHAND_FIDELITY_MATRIX.md row 3.4.
# ---------------------------------------------------------------------------
DUAL_POROSITY = {
    "enabled_for": ("fractured",),
    "beta_range": (2.0, 8.0, 20.0),   # (low, central, high) capacity ratio
    "mass_transfer_omega": 1e-3,      # first-order rate [1/day], slow matrix diffusion
}

# ---------------------------------------------------------------------------
# 5a-bis. SORBING dual-porosity capacity  [remediation 2026-08-05, review.md #2]
# ---------------------------------------------------------------------------
# beta above is the capacity ratio for a CONSERVATIVE tracer. A sorbing solute
# also loads the matrix grain surfaces, so the immobile zone holds R_m times more
# mass and the effective capacity ratio is
#       beta_eff = beta * R_m ** BETA_SORPTION_STRENGTH
# (see physics.transport.effective_capacity_ratio for the derivation).
#
# WHY THIS EXISTS AS A KNOB: before the correction the fractured front was
# species-blind -- Kd entered only the Tang term, which is unioned with max() and
# so can only EXTEND a plume, never retard it. Radium travelled exactly as fast
# as sulfate (review.md finding #2). Applying the full physically-indicated
# R_m is 1.0 and is the default.
#
# The exponent is exposed (same pattern as K_DEPTH_DECAY_STRENGTH) because it
# moves every fractured, sorbing result, and because omega is NOT co-scaled --
# physically the transfer rate should also fall as R_m rises, so the full
# correction is applied through an incompletely-parameterised kinetic model.
# 0.0 restores the pre-correction behaviour exactly; use it to bisect a label
# change, not as a way to soften an inconvenient answer.
BETA_SORPTION_STRENGTH = 1.0

# ---------------------------------------------------------------------------
# 5a-ter. GEOMETRY-DERIVED MATRIX TRANSFER RATE  [remediation 2026-08-05 r2]
# ---------------------------------------------------------------------------
# `mass_transfer_omega` above sets how fast the immobile matrix capacity is
# actually reached (the retarded clock approaches 1+beta on a timescale
# 1/omega). Pinning it at 1e-3/day -- 2.7 yr -- for every species is wrong in
# BOTH directions: measured against the model's own fracture geometry it is 54x
# too slow for a conservative tracer and 826x too fast for radium, which needs
# millennia to load its matrix. physics.matrix_transfer_omega derives it from
# the aperture and mobile porosity already in the feature row (no new parameter):
#       omega = 3*De/(R_m * L^2),   L = b_half/phi_mobile
# DEFAULT False -- IMPLEMENTED, MEASURED, AND REJECTED. Keep the code and this
# note: the reasoning is worth more than the switch.
#
# Deriving omega from geometry is self-defeating, for an algebraic reason. Early
# time expands the retarded clock as R_app ~ 1 + beta_eff*omega*t, and
#       beta_eff * omega = (beta*R_m) * 3*De/(R_m*L^2) = 3*beta*De/L^2
# R_m CANCELS. So a geometry-derived omega makes the early-time retardation
# SPECIES-BLIND -- precisely the defect beta_eff was introduced to remove.
# Measured with it on (Jaduguda, t=20 yr): radium's front rose to 9.50 m against
# uranium's 13.22 m, i.e. radium became as mobile as uranium again.
#
# The deeper reason: a first-order mobile/immobile model CANNOT reproduce
# early-time matrix diffusion at all. True diffusive uptake grows as
# sqrt(R_m*De*t), so apparent retardation scales as sqrt(R_m); the first-order
# form can only deliver R_m (pinned omega) or R_m^0 (geometry omega). Neither is
# sqrt(R_m).
#
# What is used instead: the TANG kernel already IS the exact solution for this
# geometry and already carries the correct sqrt(R_m * t) scaling through
# sigma = theta_m*sqrt(R_m*De)/b_half. It is unioned with the continuum branch by
# max(), so it governs wherever it is the less-retarded of the two -- which for
# every sorbing species it is. Letting Tang govern (by removing the attenuation
# inflation that was suppressing it, see ATTENUATION_USES_SORBED_RESIDENCE) is
# the correct fix and needs no new parameter.
#
# The rigorous upgrade, if the continuum branch is ever made authoritative, is to
# replace the Goltz-Roberts clock with the diffusive one:
#       R_app(t) = 1 + (2/sqrt(pi))*sigma*sqrt(t)
#       I(t) = (2/c)*sqrt(t) - (2/c^2)*ln(1 + c*sqrt(t)),   c = 2*sigma/sqrt(pi)
# which reduces to I(t) -> t as sigma -> 0 and gives the classic sqrt(t) front.
OMEGA_FROM_GEOMETRY = False
# Numerical band. Below the floor the clock never matures inside a 50 yr horizon
# (harmless, but the branch stops meaning anything); above the ceiling it matures
# instantly and dual porosity degenerates to a constant retardation 1+beta.
OMEGA_BOUNDS = (1e-8, 1.0)

# ---------------------------------------------------------------------------
# 5a-quater. ATTENUATION RESIDENCE TIME  [remediation 2026-08-05 r2]
# ---------------------------------------------------------------------------
# First-order U redox trapping is applied as exp(-k * age), age = x/v_c. Which
# v_c? Using the SORPTION-retarded velocity v/(1+beta*R_m) makes the age ~900x
# longer in fractured rock than the porous Wyoming test k was measured in, giving
# a decay of ~8.6 per METRE -- the plume is annihilated inside 1 m, below the
# tool's own grid resolution. Two things are wrong with that:
#   (1) DOUBLE COUNTING. Retardation and redox trapping both remove uranium from
#       the advancing front. Uranium held in the matrix by sorption is already
#       immobilised -- that IS what the retardation term represents -- so also
#       charging it the full reduction rate for that residence removes the same
#       mass twice.
#   (2) The measured k is a rate for dissolved U(VI) in MOBILE water contacting
#       reductants, and first-order decay assumes an INFINITE sink (a caveat this
#       config already records). Multiplying the residence time by ~900 claims
#       ~900x more reduced uranium than any measured reducing capacity supports.
# The age therefore uses the TRACER-retarded velocity (dual-porosity capacity
# only, no sorption multiplier) -- the time the solute actually spends as mobile
# dissolved U(VI). True = the previous behaviour.
ATTENUATION_USES_SORBED_RESIDENCE = False

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
#
# !! FIDELITY FLAW 3.4 -- FOREIGN-ANALOGUE VALUES, NOT LOCAL DATA. !!
# The aperture and De below are GENERIC CRYSTALLINE-ROCK literature values
# (Neretnieks 1980; Tang et al. 1981; Freeze & Cherry). NO packer test, tracer
# test or measured fracture aperture has ever been published for the Singhbhum
# Shear Zone -- verified by targeted search 2026-07-31 and 2026-08-01: the SSZ
# literature is extensive but entirely structural/economic geology, not
# hydrogeology. UCIL holds packer and mine-dewatering records institutionally
# and has not published them. The nearest usable analogues are foreign
# crystalline sites (SKB Aspo, Stripa, Nagra Grimsel) and NGRI Maheshwaram
# (Indian granite, different province).
# These values therefore carry the LOWEST confidence of any parameter in this
# config, and the ENTIRE fractured-transport overlay (Tang attenuation + the
# dual-porosity clock below) rests on them. Deliberately NOT replaced with a
# local-sounding number: that would relabel an assumption as data. See
# JHARKHAND_FIDELITY_MATRIX.md row 3.4.
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
#     drawn down CONTINUOUSLY with sweep duration toward residual*C0 (see the
#     drawdown law below), and a clean-water replacement front launched from the
#     source plane (Domenico superposition). The endpoint residual is derived at
#     runtime from the Texas 'Final Post-restoration' / 'End of Mining' sheets;
#     RESTORATION_FALLBACK_RESIDUAL is used only when a sheet is too sparse.
#
#     2026-07-13 fix: the source draw-down is now a CONTINUOUS function of sweep
#     duration, not a binary step gated on `eval_time > op + restoration`. That
#     gate made the clean-up VANISH (source snapped back to full C0, front frozen)
#     whenever restoration_years reached time_years - operation_years -- so
#     dialing restoration UP past that point made the aquifer look dirtier and
#     then flat. The drawdown law removes the discontinuity and makes a longer
#     sweep monotonically cleaner (see realized_residual in physics.transport).
# ---------------------------------------------------------------------------
RESTORATION_FALLBACK_RESIDUAL = {
    "uranium_ppb": 0.30, "sulfate_mg_l": 0.50, "tds_mg_l": 0.50,
    # excursion-only; conservative tracer, so it sweeps like TDS
    "chloride_mg_l": 0.50,
}


def restoration_endpoint_for(species: str, texas_residuals: dict | None = None) -> float:
    """Endpoint residual C_rest/C0 after a reference sweep, for ANY species.

    Single source of truth so the serve path (ml.predict) and the training
    generator (synthetic.generate) cannot disagree -- they did: radium has no
    column in the Texas post-restoration sheets, so the serve path's
    `texas_residuals.get(species, 1.0)` fell through to the no-restoration
    sentinel 1.0 while the generator applied RADIUM_RESTORATION_RESIDUAL (0.99).
    The served restoration machinery was therefore degenerate for radium (the
    exact outcome the 0.99 was chosen to avoid) and the surrogate had been
    trained on up to ~30% radium source clean-up the analytical engine denied.
    See review.md finding #3.
    """
    if species == "radium_226_mbq_l":
        return float(RADIUM_RESTORATION_RESIDUAL)
    if texas_residuals and species in texas_residuals:
        return float(texas_residuals[species])
    return float(RESTORATION_FALLBACK_RESIDUAL.get(species, 1.0))

# Restoration source-drawdown law. The empirical Texas endpoint residual
# (Final Post-restoration / End of Mining) is REACHED after a reference sweep of
# RESTORATION_REF_YEARS; the source fraction follows an exponential pore-volume
# drawdown  C_res/C0 = exp(-lambda * t_sweep),  lambda anchored so a sweep of
# RESTORATION_REF_YEARS reproduces that endpoint. Shorter sweeps clean less;
# longer sweeps approach RESTORATION_RESIDUAL_FLOOR (rebound / irreducible U).
# Grounded in Datasets/.../Dataset 2/Restoration.csv: across the 13 Texas
# production areas with a duration, the median active-restoration sweep is
# 5.0 yr (IQR 3.8-6.5 yr), median 18.6 pore volumes extracted.
RESTORATION_REF_YEARS = 5.0
RESTORATION_RESIDUAL_FLOOR = 0.02   # matches the texas_restoration_residual clip floor

# UI exploration ceiling for the restoration-sweep slider (dashboard + request
# validation), DECOUPLED from the training envelope (OPERATIONAL_RANGES["restoration
# _years"], currently 10 yr). Real active restoration is 1-6 yr (Texas median 5.0);
# the EPA post-restoration monitoring horizon is 30 yr, so 30 is already a generous
# exploration ceiling -- lowered from 50 (2026-07-16, user review): sweeps beyond the
# available post-closure window just saturate causally, so the extra range only
# added dead slider travel. The analytical engine serves any value; ML bands above
# the deployed model's trained max (10 yr) are flagged as extrapolation.
RESTORATION_SLIDER_MAX_YEARS = 30.0

# UI exploration ceiling for the EVALUATION-TIME slider, DECOUPLED from the trained
# horizon (OPERATIONAL_RANGES["horizon_years"], currently 20 yr) exactly like the
# restoration slider above. The 30 yr disc-flush half-life plays out over evaluation
# time (t - operation_years), NOT over the restoration-sweep duration, so a 20 yr cap
# cannot show even one half-life post-closure (op 8 yr + 20 = 12 yr of decay < 30).
# 50 yr lets a user watch the residual source zone decay past the half-life. The
# analytical engine serves any horizon; ML bands above the trained max are flagged as
# extrapolation. Widening the training horizon to match is a separate retrain decision.
HORIZON_SLIDER_MAX_YEARS = 50.0

# ---------------------------------------------------------------------------
# 5b. First-order natural attenuation of DISSOLVED URANIUM along travel
#     (pseudo-reactive transport, 2026-07-13 real-ISR upgrade).
# Down-gradient of an ISR wellfield, mobilized U(VI) is reduced to immobile
# U(IV) by residual reductants (pyrite, organic carbon) -- the same redox
# trapping that formed roll-front deposits. Screening form: the traveling-plume
# concentration is multiplied by exp(-k * tau), tau = x / v_c (plug-flow travel
# time at the retarded contaminant velocity). This gives the plume a FINITE
# steady-state extent x* = (v_c/k) * ln(C0/thr) instead of unbounded growth.
#
# Rate grounding (Wyoming ISR cross-hole field test, Johnson et al. 2019,
# ES&T 10.1021/acs.est.9b01572): ~50% of injected U(VI) reduced to U(IV) in
# ~1 yr where reducing capacity was INTACT -> k_max ~ 0.7/yr. Two honesty
# caveats bound the range DOWN: (1) that test conflates nothing with sorption
# (we already model retardation separately -- calibrating to the 39%-recovered-
# vs-chloride number would double-count Rd), and (2) reducing capacity is
# FINITE and partially consumed near a real wellfield (the same study reports
# the pathway's capacity nearly exhausted) -- first-order decay assumes an
# infinite sink, so the central value must sit well below the intact-rock max.
# k is SAMPLED per scenario (log-triangular over [lo, mode, hi]) so the
# reducing-capacity uncertainty flows into the conformal P10-P90 bands; the MC
# adds a per-draw x0.5-2 multiplier for local heterogeneity. Uranium only --
# sulfate/TDS are conservative tracers (k = 0).
U_ATTENUATION_K_PER_YR = (0.05, 0.20, 0.70)   # (lo, mode, hi), triangular in log10
U_ATTENUATION_MC_MULT = (0.5, 2.0)            # per-draw log-uniform multiplier

# Phase-1 fix 3.5 (2026-08-01): mineralogy tilt of the attenuation mode.
# The Singhbhum ore belt is a POLYMETALLIC SULPHIDE province -- uraninite occurs
# with abundant chalcopyrite, pyrite and pyrrhotite (Econ. Geol. 108:1499 (2013);
# J. Earth Syst. Sci. 120:475 (2011)) -- so the reducing capacity that immobilises
# U(VI) is genuinely richer inside the belt than in the surrounding weathered,
# oxidised granite-gneiss. The MODE of the sampled k is therefore shifted by
# ore zone instead of using one statewide value. The (lo, hi) envelope is
# UNCHANGED so every served k stays inside the trained support [0, 0.70]; only
# the central value moves, and the MC spread still carries the uncertainty.
U_ATTENUATION_MODE_BY_ZONE = {
    "deposit": 0.35,   # sulphide-rich ore body: strongest documented reductant load
    "belt":    0.28,   # Singhbhum shear-zone envelope: same province, less certain
    "none":    0.12,   # weathered/oxidised country rock: weakest reducing capacity
}

# ---------------------------------------------------------------------------
# 5d. DEPTH-DEPENDENT HYDRAULIC CONDUCTIVITY  K(z)   [Phase-1 fix 3.3, 2026-08-01]
# ---------------------------------------------------------------------------
# The CGWB aquifer polygons (and the NAQUIM transmissivities) characterise the
# DRINKING-WATER aquifer -- the weathered mantle plus the upper productive
# fracture zone, tens of metres deep. ISR ore sits at 140-600 m. In crystalline
# rock, fracture aperture and connectivity close with depth under lithostatic
# load, so applying a shallow K at ore depth over-states plume velocity and
# reach -- flaw 3.3 of the fidelity audit.
#
# The decay is grounded in the district NAQUIM reports already on disk
# (Datasets/naquim_reference/naquim_depth_evidence.md, auto-extracted 2026-07-31),
# which state the effect in almost identical language across the state:
#   "fractures generally die down with the depth and below 175 m"  (Deoghar p48)
#   "...below 163 m"  (Godda p57)      "...below 184 m"  (Latehar p49)
#   "none of the wells fractures have been encountered beyond 180 m" (W Singhbhum p43)
#   "fractures are common within a depth of 45 m, less frequent [beyond]" (W Singhbhum p43)
# and, for the ore belt specifically, a deeper-persisting fractured aquifer
#   "fractured aquifer persists to ~258 m then massive rock" (E Singhbhum profile).
#
# Model:  K(z) = K_ref * exp(-(z - z_ref) / lambda),   z > z_ref
#   z_ref  = depth the measured K represents = the "common fractures" zone that
#            supplies most of the tested yield (45 m, W Singhbhum wording).
#   lambda = calibrated per district so that K has fallen to
#            K_DEPTH_RESIDUAL_AT_FRACTURE_BASE of K_ref at that district's own
#            documented fracture-death depth (naquim_vertical.csv `fracture_max_m`,
#            e.g. E Singhbhum 258 m, W Singhbhum 200 m, Ranchi 121 m).
# The result is clamped into the deployed model's trained K support box, so this
# is a SERVE-TIME correction that needs no retrain.
K_DEPTH_DECAY_ENABLED = True
K_DEPTH_REF_M = 45.0                       # "fractures common within 45 m"
K_DEPTH_RESIDUAL_AT_FRACTURE_BASE = 0.05   # K/K_ref at the fracture-death depth
K_DEPTH_FRACTURE_BASE_DEFAULT_M = 180.0    # districts with no NAQUIM fracture_max
# 1.0 = the full physically-indicated correction (default; what the NAQUIM
# evidence supports). Lower values damp it -- 0.5 applies the square root of the
# factor -- for a deliberately conservative interim. Exposed because this single
# number moves every depth-sensitive output.
K_DEPTH_DECAY_STRENGTH = 1.0

# ---------------------------------------------------------------------------
# 5e. AQUIFER-BOUNDARY K SMOOTHING   [Phase-2 fix 3.6, 2026-08-01]
# ---------------------------------------------------------------------------
# The CGWB aquifer polygons are a CATEGORICAL map: every pin inside a polygon
# gets that polygon's single K. Crossing a mapped line therefore steps K
# discontinuously, and a QA transect (Ranchi -> Jaduguda, 2026-07) measured the
# consequence -- a ~16 ha jump in modelled plume area between two pins ~8 km
# apart, present in BOTH engines, purely because a polygon edge lay between
# them. Real lithological contacts are gradational at this scale, and a user
# who nudges a pin across an invisible line and sees the answer double will
# (rightly) stop trusting the tool.
#
# Fix: blend K across the contact instead of stepping it. For a pin at
# perpendicular distance d_in inside its own polygon, with the nearest OTHER
# polygon carrying K_other:
#     w_own = 0.5 + 0.5 * min(d_in / L, 1)          (L = blend half-width)
#     log K = w_own*log K_own + (1 - w_own)*log K_other
# At the contact d_in = 0 -> w_own = 0.5 from BOTH sides, so the two one-sided
# limits agree and K is continuous across every boundary. Deeper than L inside a
# polygon the blend vanishes and the mapped value is returned unchanged, so this
# only affects the immediate neighbourhood of a contact.
# Blending is done in LOG space because K is log-normally distributed (spanning
# orders of magnitude); a linear average would be dominated by the larger value.
# Set L = 0 to disable and restore the hard categorical lookup.
#
# SCOPE -- measured, not assumed (2026-08-01): the Jharkhand CGWB layer is only
# 23 polygons but they are long and interleaved, so a randomly sampled in-polygon
# pin sits a MEDIAN of just ~1.4 km from a lithological contact. At L = 0.02 deg
# about 60% of pins receive some blending. This is therefore closer to "replace a
# categorical map with a smoothly varying field" than to "patch a few edges" --
# which is the physically honest description anyway, since mapped contacts are
# interpretive lines through gradational rock, not step changes in permeability.
# The weight still reaches 1.0 (mapped value, untouched) at distance L, so the
# perturbation tapers to zero rather than washing the map out; L is kept at ~2 km
# so genuine lithological contrast at the 10 km+ scale survives intact.
K_BOUNDARY_BLEND_ENABLED = True
K_BOUNDARY_BLEND_HALFWIDTH_DEG = 0.02     # ~2.2 km at Jharkhand latitude

# ---------------------------------------------------------------------------
# 5e-bis. DISTRICT-BOUNDARY BLEND for the K(z) decay length
#         [remediation 2026-08-05, review.md finding #5]
# ---------------------------------------------------------------------------
# Fix 3.3 calibrates the depth-decay length per district from that district's own
# NAQUIM fracture-death depth. Those are per-district CONSTANTS, so 3.3 quietly
# introduced a SECOND categorical map on top of the aquifer polygons that 3.6 had
# just finished smoothing -- and with it a fresh set of hard steps at every
# district line. Measured on the Ranchi->Jaduguda transect: K stepped
# 0.147 -> 0.256 m/day (1.74x) across ~130 m, inside one aquifer polygon and one
# lithology, purely because fracture_max_m flips 200 -> 258 at the West/East
# Singhbhum border. Row 3.6's "K is provably continuous across every boundary"
# was therefore false in the deployed build.
#
# Same half-width and the same 0.5-at-the-border weighting as the aquifer blend,
# so the two smoothings compose instead of fighting. Blended LINEARLY (depths,
# not a log-normal conductivity). Set 0 to restore the hard district lookup.
DISTRICT_BLEND_HALFWIDTH_DEG = 0.02       # ~2.2 km at Jharkhand latitude


def depth_decay_factor(z_m: float, fracture_base_m: float | None = None,
                       strength: float | None = None) -> float:
    """K(z)/K_ref multiplier for crystalline rock. 1.0 at or above K_DEPTH_REF_M.

    fracture_base_m: the district's documented fracture-death depth (NAQUIM
    `fracture_max_m`); None -> K_DEPTH_FRACTURE_BASE_DEFAULT_M.

    THE EXPONENTIAL IS NOT EXTRAPOLATED PAST ITS EVIDENCE (fixed 2026-08-10).
    The decay length is calibrated on ONE interval -- from the tested shallow
    zone (45 m) down to the district's NAQUIM-documented fracture-death depth,
    where K has fallen to K_DEPTH_RESIDUAL_AT_FRACTURE_BASE. Running it further
    was unsupported and produced physically implausible numbers: for a district
    with a shallow fracture base (Ranchi, 121 m) the factor at 300 m came out at
    4.3e-5, a 23,000x reduction from 45 m.

    Two independent checks say that is too much:
      * LOCAL. The NAQUIM reports describe "massive rock" below the fracture
        base -- low permeability, not vanishing permeability. The evidence ends
        at the fracture base; it does not license a continued exponential.
      * GLOBAL. Manning & Ingebritsen (1999) / Ingebritsen & Manning (2010) give
        mean crustal permeability log k = -14 - 3.2 log z (k in m2, z in km),
        i.e. about 440x between 45 m and 300 m, and roughly 3-4 orders of
        magnitude over the whole upper 2 km. A 23,000x drop across 255 m exceeds
        the global crustal trend by ~50x.
    So below the fracture base the factor is HELD at its fracture-base value.
    Above it the district-calibrated exponential is unchanged. This is
    serve-time only (K is sampled directly from the polygon ranges when training
    labels are baked), so it needs no retrain.
    """
    import math
    if not K_DEPTH_DECAY_ENABLED:
        return 1.0
    z = float(z_m)
    if z <= K_DEPTH_REF_M:
        return 1.0
    base = float(fracture_base_m or K_DEPTH_FRACTURE_BASE_DEFAULT_M)
    # the base must sit below the reference zone for the calibration to mean
    # anything; if a district reports a very shallow fracture base, keep a
    # minimum span so lambda stays finite and positive.
    span = max(base - K_DEPTH_REF_M, 20.0)
    lam = span / math.log(1.0 / K_DEPTH_RESIDUAL_AT_FRACTURE_BASE)
    # clamp the depth at the calibration's lower limit rather than extrapolating
    z_eff = min(z, K_DEPTH_REF_M + span)
    f = math.exp(-(z_eff - K_DEPTH_REF_M) / lam)
    s = K_DEPTH_DECAY_STRENGTH if strength is None else float(strength)
    return float(min(1.0, max(f ** s, 1e-6)))

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
    # U natural-attenuation rate (recorded in the model card so serving can flag
    # an expert k override outside the trained support; 0 = non-uranium rows)
    "u_attenuation_k_per_yr": (0.0, 0.70),
}

# Operational irregularities (Phase-2 v2): industrial reality injected into the
# synthetic loop. Downtime episodes suspend hydraulic capture (eta -> 0 while
# the pumps are down => effective eta = eta*(1 - downtime_fraction)); the
# seasonal gradient amplitude and bleed drift enter the parameter-uncertainty
# Monte Carlo (they widen the outcome distribution rather than shift the mean).
#
# !! SCENARIO ASSUMPTIONS -- every range in this dict is a chosen envelope, not a
# measurement, EXCEPT `gradient_seasonal_amp`, whose upper bound 0.40 is now
# anchored by the CGWB seasonal analysis (see VERTICAL_SEASONAL) and which the
# flow field populates per pin. The original note said "to be re-fit from TCEQ
# excursion records"; those records were never obtained and this is recorded as a
# standing data gap rather than left as an aspiration. Registered in
# UNGROUNDED_PARAMETERS. These widen the P10-P90 bands, so the effect of getting
# them wrong is mis-sized uncertainty, not a biased central estimate.
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
#
# !! SCENARIO ASSUMPTION -- NO MEASUREMENT BEHIND EITHER NUMBER. !!
# See UNGROUNDED_PARAMETERS below. The FORM (monotone, saturating, throughput-
# driven) is defensible -- lixiviant does flare beyond the pattern and the flare
# does not grow without bound -- but the gain 0.40 and the half-saturation scale
# 2.0 BV are chosen, not measured. This is high-leverage: W_eff sets the E1 leach
# disc radius, and the disc is 76-97% of the reported `affected_area_ha`
# (DOMENICO_ERROR_ENVELOPE.md). Grounding it needs per-pattern lixiviant-flare or
# exempted-vs-pattern area data that the Texas sheets do not resolve.
SOURCE_BV_GAIN = 0.40    # max +40% effective source width at high throughput
SOURCE_BV_REF = 2.0      # bulk pattern volumes at which widening half-saturates

# Source-term signatures (end-of-mining minus baseline) are derived at runtime
# from the Texas sheets; these are only fallbacks if those rows are unusable.
FALLBACK_SOURCE_CONC = {
    "uranium_ppb":  (500.0, 5000.0),   # alkaline ISR pregnant fluid is U-rich
    "sulfate_mg_l": (500.0, 3000.0),
    "tds_mg_l":     (1500.0, 8000.0),
    # excursion-only; the real Texas End-of-Mining series carries 6 mines
    # (331-1402 mg/L), so this fallback should never be reached
    "chloride_mg_l": (330.0, 1400.0),
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
# E1 radial/anisotropic plume geometry (Phase 2, Stage E; see E1_geometry_design.md).
# MASTER SWITCH for the E1 leach-zone disc + V-anisotropy geometry. Flipped ON at
# the Stage-H cutover (2026-07-12): the deployed ML artifacts are E1-trained (model
# card v3), so the served analytical engine must use the same geometry. Tests that
# need the pre-E1 geometry set this False explicitly (try/finally).
E1_ENABLED = True

# Polish #4: the leach-zone disc (source-zone footprint) does not stay at full
# strength forever -- once injection stops, regional flow flushes the mobile pore
# water and the residual slowly re-dissolves. Model that net depletion as an
# exponential decay of the disc concentration starting at end-of-operations.
#
# Half-life basis (real ISR-restoration literature, not a guess):
#   * EPA's proposed 40 CFR 192 rule requires >=30 yr of post-restoration
#     groundwater monitoring, shortenable only after 3 consecutive stable years --
#     i.e. the regulator's own estimate of how long the source zone stays elevated.
#   * The leached zone is genuinely hard to deplete: field restorations pumped
#     >15-20 pore volumes and several parameters still did not reach background
#     (WISE; IAEA-TECDOC-1239).
#   * Uranium persists in the aquifer solids after ISR and concentrations can even
#     REBOUND post-restoration as residual U re-oxidises/re-dissolves
#     (Wyoming study, ScienceDirect S0883292715300342). So a *fast* flush is wrong.
#   * Full natural attenuation runs "decades" (US EPA 600/F-17/342; World Nuclear).
# A single exponential from closure is a screening simplification (it does not
# resolve the faster active-restoration phase or the rebound), but a 30 yr
# half-life anchors it to the regulatory 30 yr monitoring horizon: ~50% of source
# strength gone by +30 yr, ~25% by +60 yr. Conservative-leaning. My earlier 20 yr
# was an ungrounded pore-volume estimate and too fast; corrected to 30 (2026-07-13).
# NOTE the exact value is deep in the label noise -- flush changes area for only
# ~0.4% of scenarios (post-closure weak sources), all strong U-deposit sources stay
# above threshold regardless -- so 30 vs 20 barely moves the trained model; it is
# grounded here for defensibility, not sensitivity. Set 0 to disable (disc held at
# C0/residual indefinitely, the pre-#4 behaviour).
DISC_FLUSH_HALFLIFE_YEARS = 30.0

# ---------------------------------------------------------------------------
# POST-RESTORATION REBOUND FLOOR   [2026-08-10]
# ---------------------------------------------------------------------------
# Uranium rebound after ISR restoration has been an acknowledged, unmodelled gap
# since 2026-07-13: the source only ever decays here, while real leached zones
# can REBOUND as residual U(IV) re-oxidises and re-dissolves (Wyoming study,
# ScienceDirect S0883292715300342; the same evidence already cited to justify
# DISC_FLUSH_HALFLIFE_YEARS being slow rather than fast).
#
# The defect this creates is specific and was measurable: the served source
# fraction was  restoration_credit x disc_flush_factor,  compounding, so after an
# active restoration the source kept decaying exponentially FOREVER -- at op = 8,
# t = 50 yr it fell to 0.023 x C0, well BELOW the empirical restoration endpoint
# of 0.060. That asserts continued natural clean-up past the measured endpoint,
# in the exact direction the rebound literature says is wrong.
#
# WHY THE ENDPOINT IS THE RIGHT FLOOR -- verified in the source data 2026-08-10.
# The Texas endpoint is not a snapshot taken the day pumping stopped. The sheet
# it comes from is headed "Post-restoration groundwater composition - Average
# composition of groundwater achieved AFTER RESTORATION WAS COMPLETE", and its
# footnote 2 refers to "stability samples" (TCEQ 2009; Rosita PAAs 1 and 2). A
# post-restoration stability demonstration is precisely the regulatory test that
# the aquifer has stopped changing -- so whatever rebound occurred is already
# inside the measured 0.060 / 0.138 / 0.337 residuals.
#
# So rather than invent a rebound magnitude and timescale (no defensible local or
# Texas numbers exist for either), the model stops claiming clean-up the data does
# not show: once a restoration sweep has run, the passive flush may no longer take
# the source BELOW the demonstrated stable endpoint. Unrestored scenarios keep the
# full 30-yr flush, which is separately justified above.
# Set False to restore the pre-2026-08-10 compounding behaviour.
RESTORATION_REBOUND_FLOOR = True

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

# Fix 3.6b (2026-08-01): taper the DEPOSIT -> BELT source-strength step.
# The tiering above is categorical, so crossing a deposit outline stepped C0 by
# 1/BELT_C0_FRACTION (~3.3x) in one pixel -- the same class of artefact as the
# aquifer-polygon K seam (fix 3.6a), and just as distrust-inducing when a user
# nudges the pin. Ore bodies do not end at a mapped line: grade decays outward
# into the enclosing mineralised envelope. C0 is therefore ramped linearly from
# the deposit value at the outline to the belt value ORE_TAPER_KM away:
#     f(d) = BELT + (1 - BELT) * (1 - d/TAPER),  0 <= d <= TAPER
# which equals 1.0 at d = 0 and BELT at d = TAPER, so it is continuous at both
# ends. Beyond TAPER, and in the non-ore tier, nothing changes.
# 3 km is the order of the mapped deposit spacing in the belt (Jaduguda-Bhatin
# ~2 km, Narwapahar-Turamdih ~10 km), so the ramp stays inside the mineralised
# corridor rather than smearing ore strength across the whole state.
ORE_TAPER_KM = 3.0
NON_ORE_U_TRACE_MULT = 3.0          # trace-leach uranium = 3 x ambient background
NON_ORE_U_TRACE_FLOOR_PPB = 5.0     # absolute floor for the trace term

# D4: grade-scaled deposit C0. The Texas-derived uranium C0 encodes the Texas ISR
# reference ore grade; each surveyed deposit's C0 is rescaled by its IAEA-UDEPO
# grade relative to this. Texas roll-front ISR ore ~0.05-0.10% U3O8 = 0.04-0.08%
# U -> 0.05% U as the representative the C0 midpoint sits in (both sides %U).
URANIUM_GRADE_REF_PCT = 0.05        # %U; deposit grade == this -> C0 unchanged

# Phase-1 fix 3.2 (2026-08-01): REAL Jaduguda source-term anchor.
# Sethy, Jha, Sahoo, Ravi & Tripathi (2013), "Dissolved uranium, 226Ra in the
# mine water effluent: A case study in Jaduguda", Radiation Protection and
# Environment 36(1):32-37, DOI 10.4103/0972-0464.121824 (open access, CC-BY-NC-SA;
# full text archived at Datasets/phase1_sources/Jaduguda_mine_water_RPE2013_fulltext.md).
# Measured UNTREATED mine-water effluent at Jaduguda, 2011 sampling year:
#     uranium    94 - 843.3 ug/L (= ppb), geometric mean 357.4, GSD 1.9
#     Ra-226     40 - 1706 mBq/L,         geometric mean 371.3, GSD 2.6
# The paper also confirms the average ore grade as 0.05% U3O8, which independently
# validates URANIUM_GRADE_REF_PCT above.
#
# INTERPRETATION -- this is a LOWER BOUND, not a replacement for the ISR C0.
# Mine water is ambient groundwater that has passively contacted broken ore in the
# workings; an ISR lixiviant is an engineered oxidising carbonate solution designed
# to dissolve uranium, so it necessarily mobilises far more. The served C0 therefore
# stays Texas-ISR-derived (the only real ISR source chemistry that exists), and
# these numbers are surfaced alongside it as the measured local reality check.
# The gap between them is the honest size of the Texas->Singhbhum transplant
# assumption (flaw 3.2) -- reported to the user rather than hidden.
JADUGUDA_MINE_WATER_U_PPB = {"min": 94.0, "gm": 357.4, "max": 843.3, "gsd": 1.9}
JADUGUDA_MINE_WATER_RA226_MBQL = {"min": 40.0, "gm": 371.3, "max": 1706.0, "gsd": 2.6}
JADUGUDA_SOURCE_CITATION = ("Sethy et al. 2013, Radiat. Prot. Environ. 36(1):32-37, "
                            "DOI 10.4103/0972-0464.121824")

# D5: Singhbhum Shear Zone transmissivity correction (serve-time, no retrain).
# The ore-belt fractured aquifer is anomalously transmissive -- CGWB NAQUIM gives
# T = 207-570 m2/day for East Singhbhum (Jaduguda belt), vs the generic schist
# aquifer polygon's T ~ 42 (K = 1.12). The lithology K therefore under-states
# leakiness ~5-14x EXACTLY where ISR uranium mining happens. At fractured
# deposit/belt pins the served K + aquifer thickness are replaced with the
# measured shear-zone values (T and b corrected jointly so seepage velocity stays
# physical -- a high K in a thin layer would be unphysically fast). K is already a
# model feature spanning ~0.04-10.6, so K = T/b ~ 2.5 is in-support -> no retrain.
# Higher T -> lower containment eta ~ Q_net/(T*i*W) -> LARGER ore-belt plume
# (safety-conservative). Applies only to the fractured Singhbhum shear zone; the
# rest of the state keeps its lithology K (already within ~2x of district NAQUIM).
SHEAR_ZONE_T_M2DAY = 370.0          # representative fractured T (E-Singhbhum central)
SHEAR_ZONE_THICKNESS_M = 150.0      # productive fractured thickness (fractures 20-258 m)
# K = T/b = 2.47 m/day (vs the schist polygon's 1.12)

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
    # riskier vertically".
    # !! SCENARIO ASSUMPTION -- screening values, no Singhbhum measurement.
    #    The DIRECTION (fractured > porous) is standard hard-rock hydrogeology;
    #    the magnitudes are chosen. Registered in UNGROUNDED_PARAMETERS.
    "Kv_Kh_by_regime": {"fractured": 0.03, "porous": 0.008},
    # !! SCENARIO ASSUMPTION -- net upward head gradient (injection driven).
    #    Now BRACKETED by the measured monsoon swing (fix 3.7 / VERTICAL_SEASONAL
    #    reports a two-end-member band around it), but the baseline itself has no
    #    local piezometry behind it -- no deep confined-aquifer head record for
    #    Singhbhum is published (same wall as fidelity row 3.4).
    "upward_gradient": 0.005,
    # Base rate for a casing / legacy-borehole shortcut to the shallow aquifer.
    # !! SCENARIO ASSUMPTION, but no longer contextless (2026-08-10). NUREG-1569
    # Sec. 5.7.8.3 p.139, citing NUREG/CR-6733 (NRC 2001) Sec. 4.3.3, records that
    # "significant risks for vertical excursions may exist if monitor wells are
    # randomly located, given the typical criteria for spacing of vertical
    # excursion monitor wells at licensed in situ leach facilities {e.g., one well
    # per 1.6 ha [4 acres] for overlying aquifers; one well per 3.2 ha [8 acres]
    # for underlying aquifers}". So a non-trivial vertical-pathway rate is the
    # regulator's own working assumption; 0.05 is this model's screening stand-in
    # for it and is NOT a published failure frequency. Registered below.
    "wellbore_failure_prob": 0.05,
    # Licensed vertical-excursion monitor-well densities, reported as detectability
    # context next to the vertical screening index (NUREG/CR-6733 Sec. 4.3.3).
    "vertical_monitor_ha_per_well_overlying": 1.6,
    "vertical_monitor_ha_per_well_underlying": 3.2,
    "vertical_monitor_citation": ("US NRC NUREG-1569 Sec. 5.7.8.3 p.139 citing "
                                  "NUREG/CR-6733 (NRC 2001) Sec. 4.3.3"),
    "ore_depth_default_m": 150.0,
    "ore_thickness_default_m": 20.0,
    "ore_depth_range_m": (50.0, 600.0),
    "ore_thickness_range_m": (2.0, 100.0),
}

# ---------------------------------------------------------------------------
# FIDELITY FIX 3.7 -- SEASONAL (MONSOON) MODULATION OF THE VERTICAL PATHWAY
#
# WHAT THE DATA SHOWS (measured 2026-08-03 from Datasets/cgwb_waterlevel_
# jharkhand.csv -- 9,583 valid readings, 398 stations, 2013-2021):
#
#   depth-to-water by CGWB campaign, state-wide median [m bgl]:
#       Aug 3.22  (post-monsoon, table HIGHEST)   Nov 3.78
#       Jan 5.25                                  May 7.20  (pre-monsoon, LOWEST)
#   per-station seasonal swing: p10 2.17, p50 3.91, p90 6.19, max 9.98 m
#
# WHAT IT DOES *NOT* JUSTIFY -- the horizontal plume:
#   Seasonal swing of the HORIZONTAL gradient is negligible: direction p50 2.5
#   deg (p90 11, ZERO cells reverse), magnitude ratio p50 1.05 / p90 1.23. The
#   monsoon lifts every head together, so it barely rotates or steepens the
#   regional gradient. The MC already samples gradient over +/-30% MINIMUM, so
#   an alternating two-season advective front would add structure entirely
#   inside existing noise -- at the cost of a full 18k-row retrain. Deliberately
#   NOT built; this comment is the record of why.
#
# WHAT IT DOES JUSTIFY -- the VERTICAL pathway (this block):
#   A 3.91 m seasonal swing across the ~110 m ore-top -> Layer-1-base separation
#   is a vertical-gradient change of 3.91/110 = 0.0355 -- SEVEN TIMES the
#   injection-driven `VERTICAL["upward_gradient"]` = 0.005 the model pins. The
#   shallow-impact index is violently sensitive to it (measured):
#       i = 0.000 -> contained,  never
#       i = 0.005 -> moderate,   30.1 yr to breakthrough   <- what we reported
#       i = 0.010 -> high,       15.1 yr
#       i = 0.020 -> high,        7.5 yr
#   So the tool was reporting ONE number for a parameter whose seasonal range
#   spans contained -> high. The monsoon does not push the plume sideways; it
#   opens and closes the lid over the drinking-water aquifer.
#
# THE TWO END MEMBERS (why this is a BAND and not a curve):
#   The perturbation depends on the DEEP head staying put while the shallow one
#   swings. CGWB monitors shallow phreatic wells (median 3-7 m bgl) -- there is
#   NO public piezometry for a 150 m confined fractured aquifer in Singhbhum
#   (UCIL/AMD hold it, unpublished -- the same wall as fidelity row 3.4). So the
#   honest output is the interval, not a point:
#     STATIC_DEEP_HEAD  (upper bound) deep head seasonally flat -> the full
#           0.0355 swing lands on the vertical gradient. Physically expected for
#           a confined deep aquifer (seasonal signals damp sharply with depth),
#           but NOT locally measured.
#     IN_PHASE_DEEP_HEAD (lower bound) deep head swings synchronously with the
#           shallow one -> the differential is unchanged -> today's behaviour.
#   Truth lies between. The UI must show both; picking one and hiding the choice
#   is exactly the failure mode this project keeps auditing itself for.
# ---------------------------------------------------------------------------
VERTICAL_SEASONAL = {
    "enabled": True,
    # State-wide CGWB campaign medians [m bgl] -- fallback when a pin has too
    # few nearby stations for a per-cell value (flow_field returns None there).
    "water_table_wet_m": 3.22,        # Aug, post-monsoon (table highest)
    "water_table_dry_m": 7.20,        # May, pre-monsoon (table lowest)
    "water_table_mean_m": 4.86,       # mean of the four campaign medians
    "swing_percentiles_m": (2.17, 3.91, 6.19),   # p10 / p50 / p90 per station
    # A net DOWNWARD gradient closes the upward advective pathway; it does not
    # create a negative risk. The seasonal gradient is therefore floored at 0.
    "clamp_gradient_at_zero": True,
    "source_citation": (
        "CGWB national monitoring network, Jharkhand (Datasets/"
        "cgwb_waterlevel_jharkhand.csv): 9,583 readings, 398 stations, "
        "2013-2021, four campaigns/yr (Jan/May/Aug/Nov)."
    ),
    "deep_head_caveat": (
        "CGWB monitors SHALLOW phreatic wells (median 3-7 m bgl). No public "
        "piezometry exists for the confined fractured aquifer at ore depth in "
        "Singhbhum, so the deep-head seasonal response is UNMEASURED and the "
        "result is reported as a two-end-member band, not a single value."
    ),
}

# ---------------------------------------------------------------------------
# MONTHLY WATER-TABLE SHAPE (drives the timeline animation)
#
# The CGWB network samples FOUR campaigns a year, so four state-wide medians are
# all the direct evidence there is [m bgl]:
#       Jan 5.25    May 7.20 (deepest)    Aug 3.22 (shallowest)    Nov 3.78
#
# Those four points already encode the ASYMMETRY that matters -- a fast monsoon
# recovery (May->Aug: -3.98 m in 3 months) and a slow dry-season recession
# (Aug->Nov->Jan->May: +3.98 m over 9). Linear interpolation BETWEEN the
# campaign months therefore reproduces the real shape; it does not invent one.
# No rainfall series is used (none exists on disk) and none is needed: the
# water-table response IS the integrated rainfall signal, measured directly.
#
# SPLIT OF EVIDENCE -- state SHAPE, per-pin AMPLITUDE:
#   The normalised shape below is state-wide; the wet/dry ENDPOINTS come from
#   the pin (flow_field dtw_shallow/dtw_deep). Justification: Jharkhand is ~200
#   km across under a single monsoon system, so onset TIMING varies by days, not
#   months, while amplitude genuinely varies pin to pin (measured swing p10 2.17
#   -> p90 6.19 m). Storing a full per-cell monthly curve would need a flow-field
#   rebuild with four extra arrays; that is the honest upgrade path if the
#   timing assumption is ever challenged.
# ---------------------------------------------------------------------------
# month -> state-wide median depth to water [m bgl] at the CGWB campaigns
WATER_TABLE_CAMPAIGNS_M = {1: 5.25, 5: 7.20, 8: 3.22, 11: 3.78}

SEASON_LABELS = {12: "winter", 1: "winter", 2: "winter",
                 3: "pre-monsoon", 4: "pre-monsoon", 5: "pre-monsoon",
                 6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
                 10: "post-monsoon", 11: "post-monsoon"}


def water_table_shape(month: int) -> float:
    """Normalised depth-to-water for a calendar month: 0.0 = shallowest table of
    the year (Aug, monsoon peak), 1.0 = deepest (May, pre-monsoon trough).

    Cyclic piecewise-linear through the four CGWB campaign anchors. Returned as
    a SHAPE so a pin's own measured wet/dry endpoints supply the amplitude --
    see the block comment above for why timing is state-wide but amplitude is not.
    """
    lo = min(WATER_TABLE_CAMPAIGNS_M.values())
    hi = max(WATER_TABLE_CAMPAIGNS_M.values())
    anchors = sorted(WATER_TABLE_CAMPAIGNS_M)                  # [1, 5, 8, 11]
    m = ((int(month) - 1) % 12) + 1
    prev = max([a for a in anchors if a <= m], default=anchors[-1])
    nxt = min([a for a in anchors if a >= m], default=anchors[0])
    if prev == nxt:
        depth = WATER_TABLE_CAMPAIGNS_M[m]
    else:
        span = (nxt - prev) % 12 or 12                          # wrap Nov -> Jan
        step = (m - prev) % 12
        d0, d1 = WATER_TABLE_CAMPAIGNS_M[prev], WATER_TABLE_CAMPAIGNS_M[nxt]
        depth = d0 + (d1 - d0) * (step / span)
    return float((depth - lo) / (hi - lo)) if hi > lo else 0.0


def water_table_at_month(month: int, wet_m: float, dry_m: float) -> float:
    """Depth to water [m bgl] for a month, scaled to a pin's own wet/dry pair."""
    return float(wet_m + water_table_shape(month) * (dry_m - wet_m))

# ---------------------------------------------------------------------------
# SCENARIO-ASSUMPTION REGISTER   [2026-08-10]
# ---------------------------------------------------------------------------
# Every constant in this file is meant to be either (a) derived from a dataset on
# disk, (b) cited to a real source, or (c) an explicit scenario assumption. The
# third class used to live only in prose, which is how ungrounded numbers kept
# being discovered by audits instead of being declared. This register makes class
# (c) machine-readable: `tests/test_assumptions_register.py` fails if a listed
# constant changes value without its entry being updated, and the API exposes it
# so a reader can see what the answer rests on.
#
# `leverage`  what moves if the number is wrong.
# `grounding` what evidence would retire it from this list.
UNGROUNDED_PARAMETERS = {
    "SOURCE_BV_GAIN": {
        "value": SOURCE_BV_GAIN, "kind": "scenario_assumption",
        "leverage": ("sets the E1 leach-disc radius via W_eff; the disc is "
                     "76-97% of reported affected_area_ha"),
        "grounding": "per-pattern lixiviant flare or exempted-vs-pattern area data",
    },
    "SOURCE_BV_REF": {
        "value": SOURCE_BV_REF, "kind": "scenario_assumption",
        "leverage": "how fast the source-width growth saturates with throughput",
        "grounding": "as above",
    },
    "INCREMENTAL_FLOOR": {
        "value": INCREMENTAL_FLOOR, "kind": "modelling_policy",
        "leverage": ("how much of a naturally-poor baseline the mine is held "
                     "responsible for; sets every exceedance threshold"),
        "grounding": "a regulator's attribution rule, not a measurement",
    },
    "ISR_UCL_BASELINE_INCREASE": {
        "value": ISR_UCL_BASELINE_INCREASE, "kind": "scenario_assumption",
        "leverage": "when the NUREG 2-of-N indicator excursion test fires",
        "grounding": ("per-well TEMPORAL baseline series, which would enable "
                      "NUREG-1569's preferred mean+5sd / ASTM D6312 rules; the "
                      "CGWB file has one sample per well and cannot support them"),
    },
    "DUAL_POROSITY.beta_range": {
        "value": None, "kind": "foreign_analogue_literature",
        "leverage": "apparent retardation of every fractured plume (Rd ~ 1+beta)",
        "grounding": "a Singhbhum tracer test (fidelity row 3.4 -- none published)",
    },
    "DUAL_POROSITY.mass_transfer_omega": {
        "value": None, "kind": "foreign_analogue_literature",
        "leverage": "how fast the retarded clock matures toward 1+beta",
        "grounding": "as above",
    },
    "FRACTURE.full_aperture_m": {
        "value": None, "kind": "foreign_analogue_literature",
        "leverage": "Tang envelope (sigma ~ 1/b_half); IS MC-sampled into the bands",
        "grounding": "a Singhbhum packer test (fidelity row 3.4 -- none published)",
    },
    "FRACTURE.De_m2_day": {
        "value": None, "kind": "foreign_analogue_literature",
        "leverage": "Tang envelope; NOT sampled -- served and trained at one value",
        "grounding": ("a defensible range; P.FRACTURE carries none and inventing "
                      "one would relabel an assumption as data"),
    },
    "VERTICAL.Kv_Kh_by_regime": {
        "value": None, "kind": "scenario_assumption",
        "leverage": "advective upward leakage rate in the shallow-impact screen",
        "grounding": "GSI Bhukosh structural analysis or local packer data",
    },
    "VERTICAL.upward_gradient": {
        "value": None, "kind": "scenario_assumption",
        "leverage": ("shallow-impact index is violently sensitive to it "
                     "(0.005 -> moderate, 0.020 -> high); bracketed by fix 3.7"),
        "grounding": "deep confined-aquifer piezometry for Singhbhum (unpublished)",
    },
    "VERTICAL.wellbore_failure_prob": {
        "value": None, "kind": "scenario_assumption",
        "leverage": "floor on the shallow-impact index wherever C0 > threshold",
        "grounding": ("published ISR mechanical-integrity-test failure statistics; "
                      "NUREG/CR-6733 Sec. 4.3.3 establishes the risk is non-trivial "
                      "but gives no frequency"),
    },
    "IRREGULARITY": {
        "value": None, "kind": "scenario_assumption",
        "leverage": "width of the P10-P90 bands (not the central estimate)",
        "grounding": "TCEQ/NRC excursion and downtime records (never obtained)",
    },
}

# Reproducibility
RANDOM_SEED = 42
