"""
ml_pipeline.physics.transport  (PHASE 2a -- analytical engine)
============================================================
Vectorized analytical advection-dispersion (ADE) plume model. This is the
"ground truth" physics the surrogate is trained to imitate; it is fast enough
(milliseconds per field) to (a) generate thousands of synthetic training
samples and (b) recompute live in the dashboard.

Core solution -- Domenico (1987) continuous-source, plan-view 2D:

    C(x,y) = C0 * A_long(x) * A_tran(x,y)
    A_long = 1/2 * erfc[ (x - Xc) / (2*sqrt(aL*Xc)) ]
    A_tran = 1/2 * [ erf((y+W/2)/(2*sqrt(aT*x))) - erf((y-W/2)/(2*sqrt(aT*x))) ]

GEOMETRY CONVENTION (2026-07 review): the source plane x = 0 sits at the
DOWNGRADIENT EDGE of the wellfield (conservative areal-source screening
convention); `wellfield_width_m` is the FULL transverse width W. The
compliance ring is therefore at x = COMPLIANCE_BUFFER_M in solver coordinates
(= W/2 + buffer from the wellfield-centre pin on the map).

Physics layered on top of the textbook solution (all documented):
  * Retardation      -> porous: constant Rd (linear equilibrium). Fractured:
                        TIME-DEPENDENT apparent retardation from first-order
                        matrix uptake, R_app(t) = 1 + beta*(1 - e^(-at)),
                        a = omega*(1+beta)/beta [Goltz & Roberts 1986] -- the
                        front runs unretarded early and approaches 1+beta late.
                        Implemented exactly via the closed-form "retarded clock"
                        I(t) = int_0^t dt'/R_app(t').
  * Hydraulic control-> three phases: OPERATION (front at v*(1-eta), eta =
                        min(1, Q_net/(q*b*W)) mass-balance capture -- complete
                        capture is possible), RESTORATION (front held by the
                        clean-up sweep; source stepped down to residual*C0 at
                        the end), DRIFT (regional gradient restored).
  * Restoration      -> Domenico superposition: a clean-water replacement front
                        launched from the source plane at the end of restoration
                        subtracts (C0 - C_res); the far plume keeps its history.
  * Matrix diffusion -> fractured regime gets the Tang/Frind/Sudicky (1981) /
                        Neretnieks (1980) zero-fracture-dispersion kernel
                        A = erfc[ sigma*t_w / (2*sqrt(t - t_w)) ] as an
                        EARLY-ARRIVAL envelope (max with the retarded-continuum
                        front): open fractures -> early far breakthrough;
                        tight apertures -> strong attenuation. Kd acts in the
                        matrix retardation inside sigma.
  * Anisotropy       -> aT/aL set by regime (fractured << porous) so fractured
                        plumes are long & narrow (channeled), porous ones round.

METRICS CONVENTION: affected area / breach are scored on the MINING-
ATTRIBUTABLE (incremental) concentration, C_plume >= max(threshold - background,
INCREMENTAL_FLOOR*threshold) -- ambient water already at/above the limit cannot
"breach the whole grid". Reported peak/compliance concentrations stay ABSOLUTE
(plume + background).

Frame: solved in flow-aligned coordinates. The dashboard rotates the field to
the local gradient/fracture-strike azimuth for display.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np
from scipy.special import erfc, erf, erfcinv

from ml_pipeline.config import parameters as P

# Beyond this advective reach the gridded area/distance is censored (the plume
# has effectively swept the local domain). The compliance-point breach is still
# evaluated at the TRUE reach, so excursion logic stays correct. Fast fractured
# channels (high K, tiny porosity) can exceed this; that is flagged, not hidden.
MAX_GRID_REACH_M = 15000.0

# Tang tail level used to size the grid so the early-arrival zone is captured.
_TANG_GRID_LEVEL = 1e-2


# --------------------------------------------------------------------------- #
# Dual-porosity kinematics (fractured regime)
# --------------------------------------------------------------------------- #
def apparent_retardation(t_days: float, beta: float, omega: float) -> float:
    """Time-dependent apparent retardation R_app(t) = 1 + beta*(1 - e^(-a t)),
    a = omega*(1+beta)/beta. R_app(0)=1 (early unretarded front), -> 1+beta
    at late time. [Goltz & Roberts 1986 first-order mobile/immobile model]"""
    if beta <= 0.0 or omega <= 0.0:
        return 1.0
    a = omega * (1.0 + beta) / beta
    return 1.0 + beta * (1.0 - math.exp(-a * max(t_days, 0.0)))


def retarded_clock(t_days: float, beta: float, omega: float) -> float:
    """Closed-form I(t) = int_0^t dt'/R_app(t')  [days]. A front moving at base
    velocity v with time-dependent retardation covers  x(t) = v * I(t).
    I(t) ~ t early (unretarded), slope -> 1/(1+beta) late."""
    t = max(t_days, 0.0)
    if beta <= 0.0 or omega <= 0.0:
        return t
    a = omega * (1.0 + beta) / beta
    return t / (1.0 + beta) + math.log((1.0 + beta) - beta * math.exp(-a * t)) / (a * (1.0 + beta))


def realized_residual(residual_ref: float, rest_days: float,
                      ref_days: float = P.RESTORATION_REF_YEARS * 365.0,
                      floor: float = P.RESTORATION_RESIDUAL_FLOOR) -> float:
    """Source fraction C_res/C0 reached by a restoration sweep of `rest_days`.

    Exponential pore-volume drawdown anchored to the empirical Texas endpoint:
    a reference sweep of `ref_days` (Texas median ~5 yr) reaches `residual_ref`
    (the Final-Post-restoration / End-of-Mining ratio); shorter sweeps clean less,
    longer sweeps approach `floor` (rebound / irreducible residual).

    CONTINUOUS by construction: rest_days -> 0 gives 1.0 (no clean-up), so the
    restored and un-restored solutions agree at the boundary -- this is what
    replaced the old binary `eval_time > op + restoration` gate that made the
    clean-up snap on/off. `residual_ref >= 1` (the no-restoration sentinel) also
    returns 1.0. `rest_days` is the sweep DURATION credited; callers evaluating a
    field at time t must pass the ELAPSED sweep (see restoration_source_fraction),
    not the planned one -- crediting the planned sweep mid-restoration violated
    causality and produced the QA F-1 snap at rest = t - op (2026-07-13)."""
    if rest_days <= 0.0 or residual_ref >= 1.0:
        return 1.0
    lam = -math.log(max(residual_ref, floor)) / max(ref_days, 1.0)
    return float(min(1.0, max(floor, math.exp(-lam * max(rest_days, 0.0)))))


def restoration_source_fraction(residual_ref: float, t_days: float,
                                op_days: float, rest_days: float) -> float:
    """Source fraction C_src/C0 at EVALUATION time t under a restoration sweep,
    crediting only the ELAPSED sweep: elapsed = clip(t - op, 0, rest).

    Causality: a planned-but-not-yet-executed sweep cannot have cleaned anything
    (f = 1.0 at t <= op), a sweep in progress is credited for the years it has
    actually run, and a completed sweep is credited in full (f = realized
    endpoint, constant thereafter -- the deficit WAVE, not this fraction, models
    the post-sweep downgradient clean-up). Continuous in t, op and rest, which
    removes the QA F-1 discontinuity: the old planned-sweep credit + the
    `Xc_clean > 0` wave gate made the upstream source-zone box snap between
    C_res and full C0 as rest crossed t - op (area stepped ~3x in one 0.02-yr
    increment, then froze)."""
    if rest_days <= 0.0:
        return 1.0
    elapsed = min(max(t_days - op_days, 0.0), rest_days)
    return realized_residual(residual_ref, elapsed)


def front_position(v_base_m_day: float, eta: float, t_days: float,
                   op_days: float, rest_days: float = 0.0,
                   beta: float = 0.0,
                   omega: float = P.DUAL_POROSITY["mass_transfer_omega"]) -> float:
    """Three-phase advective front distance [m] from the source plane.

    v_base: POROUS -> pass the retarded velocity vc = v/Rd with beta=0.
            FRACTURED -> pass the fracture water velocity v with beta>0; the
            matrix-uptake clock applies the retardation (matures with ELAPSED
            time, regardless of phase).
    Phases:  [0, t_op]           operation, net velocity v*(1-eta)
             (t_op, t_op+t_rest] restoration sweep, front HELD (velocity 0)
             (t_op+t_rest, t]    post-closure drift, velocity v
    """
    clock = lambda t: retarded_clock(t, beta, omega)          # noqa: E731
    t1, t2 = op_days, op_days + max(rest_days, 0.0)
    x = v_base_m_day * (1.0 - eta) * clock(min(t_days, t1))
    if t_days > t2:
        x += v_base_m_day * (clock(t_days) - clock(t2))
    return max(x, 0.0)


# --------------------------------------------------------------------------- #
# Discrete-fracture matrix diffusion (Tang/Frind/Sudicky 1981; Neretnieks 1980)
# --------------------------------------------------------------------------- #
def matrix_sigma(phi_total: float, grain_density: float, kd_L_kg: float,
                 De_m2_day: float | None = None,
                 half_aperture_m: float | None = None) -> float:
    """Matrix-diffusion group sigma = theta_m * sqrt(R_m * De) / b_half
    [1/sqrt(day)]. R_m = 1 + rho_b*Kd/theta_m is the MATRIX retardation --
    the physical channel through which Kd acts in fractured rock."""
    De = De_m2_day if De_m2_day is not None else P.FRACTURE["De_m2_day"]
    b_half = (half_aperture_m if half_aperture_m is not None
              else P.FRACTURE["full_aperture_m"][1] / 2.0)
    theta_m = float(np.clip(phi_total, 1e-3, 0.45))
    rho_b = (1.0 - theta_m) * grain_density                    # kg/m3
    Rm = 1.0 + rho_b * (max(kd_L_kg, 0.0) * 1e-3) / theta_m    # Kd L/kg -> m3/kg
    return theta_m * math.sqrt(Rm * De) / max(b_half, 1e-6)


def tang_attenuation(X: np.ndarray, t_days: float, Xw_m: float,
                     sigma: float) -> np.ndarray:
    """Tang et al. (1981) zero-dispersion fracture solution as an attenuation
    factor vs distance, using the water-front scaling t_w = (x/Xw)*t:
        A(x) = erfc[ 0.5*sigma*sqrt(t) * r/sqrt(1-r) ],  r = x/Xw in (0,1)
    Zero beyond the water front and upgradient of the source plane."""
    if sigma <= 0.0 or Xw_m <= 0.0 or t_days <= 0.0:
        return np.zeros_like(np.asarray(X, dtype=float))
    r = np.clip(np.asarray(X, dtype=float) / Xw_m, 0.0, 0.999)
    arg = 0.5 * sigma * math.sqrt(t_days) * r / np.sqrt(1.0 - r)
    A = erfc(arg)
    return np.where((np.asarray(X) > 0.0) & (np.asarray(X) <= Xw_m), A, 0.0)


def _tang_reach(t_days: float, Xw_m: float, sigma: float,
                level: float = _TANG_GRID_LEVEL) -> float:
    """Distance where the Tang factor decays to `level` (closed form)."""
    if sigma <= 0.0 or Xw_m <= 0.0 or t_days <= 0.0:
        return 0.0
    c = 2.0 * float(erfcinv(level)) / (sigma * math.sqrt(t_days))
    r = 0.5 * (-c * c + c * math.sqrt(c * c + 4.0))            # r/sqrt(1-r)=c
    return float(np.clip(r, 0.0, 0.999)) * Xw_m


# --------------------------------------------------------------------------- #
# Concentration field (Domenico product + Tang envelope + restoration superposition)
# --------------------------------------------------------------------------- #
@dataclass
class TransportParams:
    C0: float                 # source concentration (same units as output)
    aL: float                 # longitudinal dispersivity [m]
    aT: float                 # transverse dispersivity [m]
    source_width_m: float     # effective (throughput-widened) source width
    Xc: float                 # retarded/apparent front distance [m]
    Xw: float                 # water front distance [m] (= Xc for porous)
    sigma: float              # matrix-diffusion group (0 => porous / off)
    t_days: float
    Xc_clean: float | None = None   # clean-water replacement front (restoration)
    C_res: float = 0.0              # residual source conc after restoration
    # E1 leach-zone disc (Stage E). radius 0 => OFF => pre-E1 geometry, unchanged.
    disc_radius_m: float = 0.0      # = W_eff/2 (throughput-widened footprint)
    disc_center_x_m: float = 0.0    # wellfield centre in solver frame (= -W/2)
    disc_conc: float = 0.0          # C0 (operations) or C_res (post-restoration)


def _long_factor(X: np.ndarray, Xc: float, aL: float) -> np.ndarray:
    Xc = max(Xc, 1e-3)
    aL = max(aL, 1e-3)
    return 0.5 * erfc((X - Xc) / (2.0 * np.sqrt(aL * Xc)))


def _tran_factor(X: np.ndarray, Y: np.ndarray, aT: float, W: float) -> np.ndarray:
    aT = max(aT, 1e-4)
    Xpos = np.where(X > 0.1, X, 0.1)
    tw = 2.0 * np.sqrt(aT * Xpos)
    return 0.5 * (erf((Y + W / 2.0) / tw) - erf((Y - W / 2.0) / tw))


def disc_flush_factor(t_days: float, op_days: float,
                      halflife_years: float = P.DISC_FLUSH_HALFLIFE_YEARS) -> float:
    """E1 polish #4: the leach-zone disc depletes after injection stops (mobile
    pore water flushed by regional flow + slow residual re-dissolution). Full
    strength during operations; exponential decay with `halflife_years` after.
    Returns a multiplier in (0, 1]. halflife_years <= 0 disables it (returns 1)."""
    if halflife_years <= 0.0 or t_days <= op_days:
        return 1.0
    return float(0.5 ** ((t_days - op_days) / (halflife_years * 365.0)))


def _disc_mask(X: np.ndarray, Y: np.ndarray, p: TransportParams,
               thr_inc: float = 0.0):
    """Boolean grid inside the E1 leach-zone disc whose (uniform) conc clears the
    incremental threshold. None if the disc is off / sub-threshold. The disc is
    the SOURCE ZONE -> it counts toward affected AREA, never toward plume travel
    (migration / compliance), which track the migrating front."""
    if p.disc_radius_m <= 0.0 or p.disc_conc < max(thr_inc, 1e-12):
        return None
    return (X - p.disc_center_x_m) ** 2 + Y ** 2 <= p.disc_radius_m ** 2


def concentration_field(X: np.ndarray, Y: np.ndarray, p: TransportParams,
                        include_disc: bool = True) -> np.ndarray:
    """Plume-attributable concentration (NO background) on meshgrids X, Y. The E1
    source-zone disc is unioned in only when include_disc (display + area); the
    plume-travel metrics pass include_disc=False."""
    A_tran = _tran_factor(X, Y, p.aT, p.source_width_m)
    A_long = _long_factor(X, p.Xc, p.aL)
    if p.sigma > 0.0 and p.Xw > p.Xc:
        # early-arrival envelope: union of retarded-continuum front and the
        # matrix-attenuated discrete-fracture solution (conservative max)
        A_long = np.maximum(A_long, tang_attenuation(X, p.t_days, p.Xw, p.sigma))
    C = p.C0 * A_long * A_tran
    if p.Xc_clean is not None and p.C_res < p.C0:
        # restoration: clean-water replacement wave subtracts (C0 - C_res).
        # Active whenever a sweep has credit (C_res < C0), INCLUDING mid-sweep
        # (QA F-1): with Xc_clean = 0 the wave is a wall at the source plane
        # (_long_factor clamps to 1e-3) wiping the upstream source-zone box --
        # gating on Xc_clean > 0 made that box snap back to full C0 the moment
        # the sweep was still running at eval time. The clean front uses the
        # RETARDED kinematics only (no Tang boost): matrix back-diffusion makes
        # clean-up slow -- conservative.
        C = C - (p.C0 - p.C_res) * _long_factor(X, p.Xc_clean, p.aL) * A_tran
    # E1: leach-zone disc -- the well-field footprint is contaminated by
    # construction. Unioned only for display + AREA (include_disc); the plume-
    # travel metrics exclude it so a wide source footprint reaching the ring is
    # not mistaken for a plume excursion.
    if include_disc and p.disc_radius_m > 0.0 and p.disc_conc > 0.0:
        inside = (X - p.disc_center_x_m) ** 2 + Y ** 2 <= p.disc_radius_m ** 2
        C = np.where(inside, np.maximum(C, p.disc_conc), C)
    return np.clip(C, 0.0, p.C0)


def concentration_point(x: float, y: float, p: TransportParams,
                        include_disc: bool = False) -> float:
    """Scalar evaluation (compliance ring / Monte Carlo). Excludes the source-zone
    disc by default -- compliance/excursion is a MIGRATING-plume concentration,
    not the source footprint reaching the ring."""
    xa = np.array([[float(x)]])
    ya = np.array([[float(y)]])
    return float(concentration_field(xa, ya, p, include_disc=include_disc)[0, 0])


# --------------------------------------------------------------------------- #
# Vertical stratification (Module 5A -- 2.5D). The deep (ore-zone) plume above
# is solved in plan view; these helpers estimate how much of it could reach the
# SHALLOW drinking-water aquifer (Layer 1), WITHOUT touching the horizontal
# metrics (A_vert at the plume centre is ~1, so area/migration are unchanged).
# --------------------------------------------------------------------------- #
def vertical_attenuation(z_m: float, H_m: float, alpha_V: float,
                         x_m: float) -> float:
    """Domenico vertical-dispersion factor for a source of vertical thickness H,
    at height z above the source centre and along-flow distance x:
        A_vert = 1/2 [ erf((z+H/2)/(2 sqrt(aV x))) - erf((z-H/2)/(2 sqrt(aV x))) ]
    Fraction (0..1) of source concentration reaching height z by vertical
    dispersion -- ~1 within the source band, decaying sharply above it. For a
    deep confined plume this is tiny, which is the physically correct 'the
    shallow aquifer is not immediately polluted' result."""
    tw = 2.0 * math.sqrt(max(alpha_V, 1e-4) * max(x_m, 1e-3))
    return float(0.5 * (erf((z_m + H_m / 2.0) / tw) - erf((z_m - H_m / 2.0) / tw)))


def _vertical_risk_band(p: float) -> str:
    if p < 0.05:
        return "contained"
    if p < 0.20:
        return "low"
    if p < 0.50:
        return "moderate"
    return "high"


def shallow_impact_screening(*, C0: float, background: float, threshold: float,
                             Xc_m: float, source_width_m: float, alpha_L: float,
                             alpha_V: float, ore_depth_m: float,
                             ore_thickness_m: float, layer1_base_m: float,
                             K_m_day: float, phi_confining: float,
                             Kv_Kh_ratio: float, upward_gradient: float,
                             t_days: float, wellbore_failure_prob: float,
                             water_table_m: float | None = None) -> dict:
    """SCREENING estimate of how much the deep plume could impact the Layer-1
    (shallow drinking-water) aquifer. Three independent pathways OR-combined:

      (1) dispersive  -- upward Domenico spreading; conc reaching Layer 1 vs the
                         incremental BIS threshold. Tiny for deep confined ore.
      (2) advective   -- upward Darcy leakage through the semi-confining fractured
                         zone: v_up = Kv*i / phi ; barrier crossed if v_up*t >= dz.
      (3) wellbore    -- casing / legacy-borehole shortcut (base rate; Singhbhum
                         has decades of AMD drilling).

    Returns the combined index AND every component so it stays interpretable.
    This is a transparent screening index, NOT a calibrated probability."""
    # Two separations: the dispersive factor is referenced to the source CENTRE
    # (its erf edges already carry the +/-H/2 half-thickness), while the advective
    # barrier is the intact confining rock from the ore TOP up to the shallow
    # aquifer base -- so a thicker ore body (top nearer the surface) shortens the
    # advective path. (Pre-2026-07-06 both used the centre, so thickness was inert.)
    dz_centre = max(ore_depth_m - layer1_base_m, 1.0)
    dz_adv = max(ore_depth_m - ore_thickness_m / 2.0 - layer1_base_m, 1.0)
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    # concentration gate for the ADVECTIVE / WELLBORE pathways: a shortcut
    # preserves concentration (~C0, minimal dilution), so it can only breach the
    # shallow limit if the source itself is above it. A sub-threshold source
    # (e.g. clamped non-ore uranium) therefore poses no vertical excursion.
    # The dispersive pathway dilutes, so it stays continuous (below).
    conc_factor = 1.0 if C0 >= thr_inc else 0.0

    # (1) dispersive: max over horizontal x of C0 * A_long(x) * A_vert(z, x).
    # z = dz_centre; A_vert's +/-H/2 edges make it top-aware for thickness.
    xs = np.linspace(max(source_width_m / 2.0, 1.0), max(Xc_m, source_width_m), 60)
    a_long = _long_factor(xs, Xc_m, alpha_L)
    a_vert = np.array([vertical_attenuation(dz_centre, ore_thickness_m, alpha_V, float(x))
                       for x in xs])
    conc_shallow = float(np.max(C0 * a_long * a_vert))
    p_disp = float(np.clip(conc_shallow / max(thr_inc, 1e-9), 0.0, 1.0))

    # (2) advective upward leakage through the confining fractured zone. The
    # barrier-crossed fraction is hydraulic (over the ore-top-to-shallow gap);
    # scale by conc_factor so a weak source that crosses is not a threshold breach.
    Kv = max(K_m_day, 0.0) * max(Kv_Kh_ratio, 0.0)
    v_up = Kv * max(upward_gradient, 0.0) / max(phi_confining, 1e-3)   # m/day
    d_up = v_up * max(t_days, 0.0)
    barrier_crossed = float(np.clip(d_up / dz_adv, 0.0, 1.0))
    p_adv = barrier_crossed * conc_factor
    yrs_break = (dz_adv / v_up / 365.0) if v_up > 1e-9 else float("inf")

    # (3) wellbore/legacy-borehole shortcut -- base rate, concentration-gated
    p_well = (float(wellbore_failure_prob) * conc_factor
              if C0 > background else 0.0)

    p_shallow = 1.0 - (1.0 - p_disp) * (1.0 - p_adv) * (1.0 - p_well)
    pathways = {"dispersive": p_disp, "advective_leakage": p_adv, "wellbore": p_well}
    dominant = (max(pathways, key=pathways.get) if p_shallow >= 0.05 else "contained")
    # D1 (Stage B): real depth-to-water CONTEXT. The risk barrier stays at
    # layer1_base_m (the aquifer BASE -- where the up-rising plume first enters
    # the resource, the conservative receptor). The water table (aquifer TOP)
    # only sets how much saturated drinking water actually sits above the barrier;
    # it does NOT shorten the separation (that would be anti-conservative here).
    water_table = None
    saturated_shallow_thickness_m = None
    if water_table_m is not None and water_table_m == water_table_m:
        water_table = round(float(water_table_m), 1)
        saturated_shallow_thickness_m = round(max(float(layer1_base_m)
                                                  - float(water_table_m), 0.0), 1)
    return {
        "separation_m": round(dz_adv, 1),   # intact confining rock: ore-top -> shallow base
        "layer1_base_m": round(float(layer1_base_m), 1),
        "water_table_m": water_table,
        "saturated_shallow_thickness_m": saturated_shallow_thickness_m,
        "ore_depth_m": round(float(ore_depth_m), 1),
        "ore_thickness_m": round(float(ore_thickness_m), 1),
        "conc_reaching_shallow": round(conc_shallow, 3),
        "a_vert_max": round(float(np.max(a_vert)), 6),
        "advective_breakthrough_fraction": round(barrier_crossed, 3),
        "years_to_vertical_breakthrough": (None if not np.isfinite(yrs_break)
                                           else round(yrs_break, 1)),
        "shallow_impact_probability": round(p_shallow, 3),
        "risk_band": _vertical_risk_band(p_shallow),
        "pathways": {k: round(v, 3) for k, v in pathways.items()},
        "dominant_pathway": dominant,
    }


# --------------------------------------------------------------------------- #
# Result container, grid, metrics
# --------------------------------------------------------------------------- #
@dataclass
class PlumeResult:
    C: np.ndarray            # plume-attributable concentration field
    X: np.ndarray            # x meshgrid [m] (x=0 at downgradient wellfield edge)
    Y: np.ndarray            # y meshgrid [m]
    Xc: float                # apparent front distance [m]
    cell_area_m2: float
    metrics: dict


def _auto_grid(reach_m: float, aL: float, source_width: float, n: int = 220,
               disc_radius: float = 0.0, disc_center_x: float = 0.0, aT: float = 0.0):
    """Build a meshgrid sized to comfortably contain the plume. With an E1 disc
    (disc_radius > 0) the domain extends up-gradient to cover the disc and the
    transverse span is sized to the PLUME (not a fixed fraction of reach, which
    starved narrow long-reach plumes to a few cells -> MC-label quantization)."""
    reach = reach_m + 4.0 * np.sqrt(max(aL, 1e-3) * max(reach_m, 1.0)) + source_width
    reach = max(reach, source_width * 2.0, 50.0)
    if disc_radius > 0.0:
        x_lo = min(-0.25 * reach, disc_center_x - disc_radius - 0.1 * reach)
        aT_eff = aT if aT > 0.0 else 0.1 * aL
        y_half = (disc_radius
                  + 4.0 * np.sqrt(max(aT_eff, 1e-4) * max(reach_m, source_width, 1.0))
                  + 0.15 * source_width)
        y_half = max(y_half, 0.6 * source_width)
        x = np.linspace(x_lo, reach, n)
        y = np.linspace(-y_half, y_half, n)
    else:
        x = np.linspace(-0.25 * reach, reach, n)          # pre-E1: unchanged
        y = np.linspace(-0.6 * reach, 0.6 * reach, n)
    X, Y = np.meshgrid(x, y)
    return X, Y


def plume_metrics(C_plume: np.ndarray, X: np.ndarray, Y: np.ndarray, *,
                  threshold: float, background: float, cell_area_m2: float,
                  disc_mask: np.ndarray | None = None) -> dict:
    """Decision metrics from a PLUME-ATTRIBUTABLE (disc-free) concentration field.

    Exceedance is incremental: C_plume >= max(threshold - background,
    INCREMENTAL_FLOOR*threshold). Reported concentrations are absolute. The E1
    source-zone disc (disc_mask) is unioned into the AREA only -- migration /
    downgradient / compliance track the migrating front, never the source zone.
    """
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    mask = C_plume >= thr_inc
    if mask.any():
        r = np.sqrt(X[mask] ** 2 + Y[mask] ** 2)
        max_dist = float(r.max())
        max_down = float(X[mask].max())          # downgradient reach beyond edge
        plume_halfwidth = float(np.abs(Y[mask]).max())
    else:
        max_dist = max_down = plume_halfwidth = 0.0
    area_mask = mask if disc_mask is None else (mask | disc_mask)
    area_m2 = float(area_mask.sum()) * cell_area_m2
    return {
        "affected_area_ha": area_m2 / 1e4,
        "affected_area_m2": area_m2,
        "max_migration_distance_m": max_dist,
        "max_downgradient_m": max_down,
        "plume_halfwidth_m": plume_halfwidth,
        "peak_conc": float(C_plume.max()) + background,       # absolute
        "breaches_threshold": bool(C_plume.max() >= thr_inc),
        "incremental_threshold": thr_inc,
        # mass proxy (sum of incremental exceedance over area)
        "exceedance_mass_proxy": float(np.clip(C_plume - thr_inc, 0, None).sum() * cell_area_m2),
    }


# --------------------------------------------------------------------------- #
# High-level: Phase-1 feature row -> plume field + metrics
# --------------------------------------------------------------------------- #
def params_from_features(feat: dict, *, species_C0: float, t_days: float,
                         operation_days: float, restoration_days: float = 0.0,
                         residual_fraction: float = 1.0) -> TransportParams:
    """Build TransportParams from a build_feature_row dict. Uses the EFFECTIVE
    containment `_eta_eff` (design eta degraded by pump-downtime episodes) when
    present, else the design eta."""
    regime = feat.get("_regime", "porous")
    beta = feat.get("dual_porosity_beta", 0.0)
    eta = feat.get("_eta_eff", feat["containment_eta"])
    v = feat["seepage_velocity_v"]

    fractured = (regime == "fractured")
    v_base = v if fractured else feat["contaminant_velocity_vc"]
    beta_k = beta if fractured else 0.0

    Xc = front_position(v_base, eta, t_days, operation_days, restoration_days, beta_k)
    Xw = front_position(v, eta, t_days, operation_days, restoration_days, 0.0) if fractured else Xc
    sigma = (matrix_sigma(feat["phi_total"], feat.get("_grain_density", 2700.0),
                          feat["Kd_L_kg"]) if fractured else 0.0)

    # Restoration clean-up (2026-07-13, QA F-1 fix): source drawn down
    # CONTINUOUSLY with the ELAPSED sweep (restoration_source_fraction), so a
    # sweep in progress is credited progressively and a planned-but-future sweep
    # not at all -- no completion gate, no snap at rest = t - op. The deficit
    # wave (concentration_field) is active whenever C_res < C0: mid-sweep its
    # front sits AT the source plane (Xc_clean = 0 -> a wall that wipes the
    # upstream source-zone box to C_res), and it advances down-gradient only
    # once regional drift resumes -- the ESCAPED plume keeps its history until
    # clean water overtakes it (the "dark band migrates downgradient" signature).
    Xc_clean, C_res = None, 0.0
    if restoration_days > 0.0:
        f_res = restoration_source_fraction(float(residual_fraction), t_days,
                                            operation_days, restoration_days)
        C_res = f_res * species_C0
        Xc_clean = front_position(v_base, 1.0, t_days, operation_days,
                                  restoration_days, beta_k)

    # E1 leach-zone disc (Stage E): OFF unless P.E1_ENABLED, so the served path
    # stays byte-identical to the deployed-ML geometry until the atomic cutover.
    disc_r = disc_cx = disc_c = 0.0
    if P.E1_ENABLED:
        W = feat["wellfield_width_m"]
        W_eff = feat.get("_source_width_m", W)
        disc_r = W_eff / 2.0
        disc_cx = -W / 2.0
        disc_c = C_res if (Xc_clean is not None and C_res > 0.0) else species_C0
        disc_c *= disc_flush_factor(t_days, operation_days)   # #4: post-closure decay
    return TransportParams(C0=species_C0, aL=feat["alpha_L"], aT=feat["alpha_T"],
                           source_width_m=feat.get("_source_width_m",
                                                   feat["wellfield_width_m"]),
                           Xc=Xc, Xw=Xw, sigma=sigma, t_days=t_days,
                           Xc_clean=Xc_clean, C_res=C_res,
                           disc_radius_m=disc_r, disc_center_x_m=disc_cx, disc_conc=disc_c)


def solve_plume(params: TransportParams, *, threshold: float, background: float,
                grid_n: int = 220, compliance_x: float | None = None) -> PlumeResult:
    """Solve one parameter set on an auto-sized grid -> PlumeResult."""
    # Size the grid to the level the exceedance mask actually needs (the
    # incremental threshold as a fraction of C0), not a fixed tail level --
    # otherwise the Tang early-arrival zone can hold above-threshold cells
    # beyond the grid edge.
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    tang_level = float(np.clip(thr_inc / max(params.C0, 1e-9), 1e-4, 0.5))
    reach_true = max(params.Xc, _tang_reach(params.t_days, params.Xw, params.sigma,
                                            level=tang_level))
    off_scale = reach_true > MAX_GRID_REACH_M
    X, Y = _auto_grid(min(reach_true, MAX_GRID_REACH_M), params.aL,
                      params.source_width_m, n=grid_n,
                      disc_radius=params.disc_radius_m,
                      disc_center_x=params.disc_center_x_m, aT=params.aT)
    C = concentration_field(X, Y, params, include_disc=False)     # plume (metrics base)

    dx = X[0, 1] - X[0, 0]
    dy = Y[1, 0] - Y[0, 0]
    cell_area = float(abs(dx * dy))
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    disc_mask = _disc_mask(X, Y, params, thr_inc)
    metrics = plume_metrics(C, X, Y, threshold=threshold, background=background,
                            cell_area_m2=cell_area, disc_mask=disc_mask)
    metrics["Xc_m"] = params.Xc
    metrics["off_scale"] = bool(off_scale)

    if compliance_x is not None:
        c_comp = concentration_point(compliance_x, 0.0, params)   # plume-only, true reach
        metrics["compliance_conc"] = c_comp + background          # absolute
        metrics["breaches_at_compliance"] = bool(c_comp >= metrics["incremental_threshold"])

    # display field: union the source-zone disc so the map shows it (metrics above
    # already separated plume-travel from the disc footprint)
    if disc_mask is not None:
        C = np.where(disc_mask, np.maximum(C, params.disc_conc), C)

    return PlumeResult(C=C, X=X, Y=Y, Xc=params.Xc, cell_area_m2=cell_area,
                       metrics=metrics)


def simulate_plume(feat: dict, *, species_C0: float, background: float,
                   threshold: float, t_days: float, operation_days: float,
                   restoration_days: float = 0.0, residual_fraction: float = 1.0,
                   grid_n: int = 220, compliance_x: float | None = None) -> PlumeResult:
    """From a Phase-1 feature row -> plume field + metrics.

    `feat` must contain the carry-throughs from build_feature_row:
    seepage_velocity_v, contaminant_velocity_vc, containment_eta, alpha_L,
    alpha_T, phi_total, Kd_L_kg, dual_porosity_beta, wellfield_width_m and the
    private _regime, _source_width_m, _grain_density (+ optional _eta_eff).

    compliance_x: solver-frame x of the monitoring ring (= COMPLIANCE_BUFFER_M
    from the wellfield edge). Evaluated at the TRUE front even when the grid is
    censored, so excursion logic stays correct off-scale.
    """
    params = params_from_features(feat, species_C0=species_C0, t_days=t_days,
                                  operation_days=operation_days,
                                  restoration_days=restoration_days,
                                  residual_fraction=residual_fraction)
    return solve_plume(params, threshold=threshold, background=background,
                       grid_n=grid_n, compliance_x=compliance_x)


# --------------------------------------------------------------------------- #
# Vectorized Monte-Carlo field metrics (Phase-2 v2 distributional labels).
# All draws of one (scenario, time, species) are evaluated in a single
# broadcast pass per reach-bucket -- ~50-100x faster than per-draw grids.
# --------------------------------------------------------------------------- #
def _stack_field(X3, Y3, *, C0, aL, aT, W, Xc, Xw, sigma, t_days,
                 Xc_clean, C_res, rest_active=None, disc_radius=None,
                 disc_center_x=None, disc_conc=None,
                 include_disc=True) -> np.ndarray:
    """concentration_field broadcast over draws: X3/Y3 are (ny,nx,1) grids,
    parameter arrays are (nd,). Returns C of shape (ny, nx, nd).

    rest_active: (nd,) bool -- draws with a restoration sweep. Needed because a
    MID-SWEEP draw has Xc_clean == 0.0 (wave wall at the source, QA F-1) which
    the old `Xc_clean > 0` test cannot distinguish from no-restoration."""
    Xc = np.maximum(Xc, 1e-3)
    aL = np.maximum(aL, 1e-3)
    aT = np.maximum(aT, 1e-4)
    A_long = 0.5 * erfc((X3 - Xc) / (2.0 * np.sqrt(aL * Xc)))
    Xpos = np.where(X3 > 0.1, X3, 0.1)
    tw = 2.0 * np.sqrt(aT * Xpos)
    A_tran = 0.5 * (erf((Y3 + W / 2.0) / tw) - erf((Y3 - W / 2.0) / tw))
    has_tang = (sigma > 0.0) & (Xw > Xc)
    if bool(np.any(has_tang)) and t_days > 0.0:
        r = np.clip(X3 / np.maximum(Xw, 1e-9), 0.0, 0.999)
        arg = 0.5 * sigma * math.sqrt(t_days) * r / np.sqrt(1.0 - r)
        A_t = np.where((X3 > 0.0) & (X3 <= Xw) & has_tang, erfc(arg), 0.0)
        A_long = np.maximum(A_long, A_t)
    C = C0 * A_long * A_tran
    if rest_active is None:                       # legacy callers: infer
        rest_active = Xc_clean > 0.0
    active = rest_active & (C_res < C0)           # sweep exists AND has credit
    if bool(np.any(active)):
        Xcc = np.maximum(Xc_clean, 1e-3)          # 0 -> wall at the source plane
        A_c = 0.5 * erfc((X3 - Xcc) / (2.0 * np.sqrt(aL * Xcc)))
        C = C - np.where(active, C0 - C_res, 0.0) * A_c * A_tran
    # E1 leach-zone disc, broadcast over draws (display/area only; excluded from
    # the plume-travel evaluation -- see mc_field_metrics)
    if include_disc and disc_radius is not None and bool(np.any(disc_radius > 0.0)):
        inside = (X3 - disc_center_x) ** 2 + Y3 ** 2 <= disc_radius ** 2
        C = np.where(inside, np.maximum(C, disc_conc), C)
    return np.clip(C, 0.0, C0)


def mc_field_metrics(plist: list[TransportParams], *, threshold: float,
                     background: float, grid_n: int = 100,
                     compliance_x: float | None = None) -> dict:
    """Per-draw (area_ha, max_dist_m, compliance_plume, off_scale) for a list
    of TransportParams sharing t_days. Draws are grouped into two reach
    buckets so small plumes keep grid resolution."""
    n = len(plist)
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    area = np.zeros(n)
    dist = np.zeros(n)
    comp = np.zeros(n)
    reaches = np.empty(n)
    for i, p in enumerate(plist):
        lvl = float(np.clip(thr_inc / max(p.C0, 1e-9), 1e-4, 0.5))
        reaches[i] = max(p.Xc, _tang_reach(p.t_days, p.Xw, p.sigma, level=lvl))
    off = reaches > MAX_GRID_REACH_M

    def arr(get):
        return np.array([get(plist[i]) for i in bucket], dtype=float)

    order = np.argsort(reaches)
    for bucket in (order[: n // 2], order[n // 2:]):
        if len(bucket) == 0:
            continue
        reach_b = min(float(reaches[bucket].max()), MAX_GRID_REACH_M)
        aL_b = max(plist[i].aL for i in bucket)
        W_b = max(plist[i].source_width_m for i in bucket)
        aT_b = max(plist[i].aT for i in bucket)
        disc_r_b = max(plist[i].disc_radius_m for i in bucket)
        disc_cx_b = min(plist[i].disc_center_x_m for i in bucket)   # most up-gradient
        X, Y = _auto_grid(reach_b, aL_b, W_b, n=grid_n,
                          disc_radius=disc_r_b, disc_center_x=disc_cx_b, aT=aT_b)
        X3, Y3 = X[:, :, None], Y[:, :, None]
        dr = arr(lambda p: p.disc_radius_m)
        dcx = arr(lambda p: p.disc_center_x_m)
        dc = arr(lambda p: p.disc_conc)
        C = _stack_field(                                    # PLUME only (no disc)
            X3, Y3,
            C0=arr(lambda p: p.C0), aL=arr(lambda p: p.aL), aT=arr(lambda p: p.aT),
            W=arr(lambda p: p.source_width_m), Xc=arr(lambda p: p.Xc),
            Xw=arr(lambda p: p.Xw), sigma=arr(lambda p: p.sigma),
            t_days=plist[bucket[0]].t_days,
            Xc_clean=arr(lambda p: p.Xc_clean if p.Xc_clean is not None else 0.0),
            C_res=arr(lambda p: p.C_res),
            rest_active=np.array([plist[i].Xc_clean is not None for i in bucket]),
            include_disc=False)
        plume_mask = C >= thr_inc
        cell = float(abs((X[0, 1] - X[0, 0]) * (Y[1, 0] - Y[0, 0])))
        # AREA also counts the source-zone disc; MIGRATION is the plume front only
        if bool(np.any(dr > 0.0)):
            disc3 = ((X3 - dcx) ** 2 + Y3 ** 2 <= dr ** 2) & (dc >= thr_inc)
            area_mask = plume_mask | disc3
        else:
            area_mask = plume_mask
        area[bucket] = area_mask.sum(axis=(0, 1)) * cell / 1e4
        R3 = np.sqrt(X ** 2 + Y ** 2)[:, :, None]
        dist[bucket] = np.where(plume_mask, R3, 0.0).max(axis=(0, 1))

    if compliance_x is not None:
        for i, p in enumerate(plist):
            comp[i] = concentration_point(compliance_x, 0.0, p)
    return {"area_ha": area, "max_dist_m": dist, "compliance_plume": comp,
            "off_scale": off, "thr_inc": thr_inc}


if __name__ == "__main__":
    from ml_pipeline.data_prep.feature_engineering import build_feature_row
    from ml_pipeline.config.parameters import EXCURSION_THRESHOLDS, COMPLIANCE_BUFFER_M

    scenarios = {
        "Fractured shear (JH)": dict(regime="fractured", K_m_day=1.12, phi_mobile=0.008,
                                     n_total=0.03, grain_density=2750, beta=8.0,
                                     thickness_m=37.5),
        "Weathered/porous (JH)": dict(regime="porous", K_m_day=2.345, phi_mobile=0.08,
                                      n_total=0.30, grain_density=2650, beta=0.0,
                                      thickness_m=85),
    }
    t_eval_days = 365 * 10
    for name, hg in scenarios.items():
        feat = build_feature_row(
            domain_is_texas=False, gradient_i=0.006, kd_L_kg=1.0,
            Q_in_m3_day=2500, bleed_fraction=0.02, operation_days=365 * 8,
            wellfield_width_m=300, source_conc_C0=15000, background_conc_Cb=2.0,
            eval_time_days=t_eval_days, **hg)
        res = simulate_plume(feat, species_C0=15000, background=2.0,
                             threshold=EXCURSION_THRESHOLDS["uranium_ppb"],
                             t_days=t_eval_days, operation_days=365 * 8,
                             compliance_x=COMPLIANCE_BUFFER_M)
        m = res.metrics
        print(f"\n{name}")
        print(f"  vc={feat['contaminant_velocity_vc']:.4f} m/day  eta={feat['containment_eta']:.3f}"
              f"  aniso={feat['anisotropy_ratio']:.0f}  Xc={m['Xc_m']:.0f} m")
        print(f"  U plume: area={m['affected_area_ha']:.2f} ha  max_dist={m['max_migration_distance_m']:.0f} m"
              f"  half-width={m['plume_halfwidth_m']:.0f} m  peak={m['peak_conc']:.0f} ppb"
              f"  breach@ring={m['breaches_at_compliance']}  comp={m['compliance_conc']:.1f}")

        # restoration demo: 4-year sweep to 20% residual, evaluated at 20 y
        res_r = simulate_plume(feat, species_C0=15000, background=2.0,
                               threshold=EXCURSION_THRESHOLDS["uranium_ppb"],
                               t_days=365 * 20, operation_days=365 * 8,
                               restoration_days=365 * 4, residual_fraction=0.2,
                               compliance_x=COMPLIANCE_BUFFER_M)
        res_n = simulate_plume(feat, species_C0=15000, background=2.0,
                               threshold=EXCURSION_THRESHOLDS["uranium_ppb"],
                               t_days=365 * 20, operation_days=365 * 8,
                               compliance_x=COMPLIANCE_BUFFER_M)
        print(f"  t=20y  no-restoration area={res_n.metrics['affected_area_ha']:.2f} ha"
              f"  vs restored area={res_r.metrics['affected_area_ha']:.2f} ha"
              f"  (peak {res_n.metrics['peak_conc']:.0f} -> {res_r.metrics['peak_conc']:.0f})")
