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
    at late time. [Goltz & Roberts 1986 first-order mobile/immobile model]

    !! OMEGA CONVENTION -- READ BEFORE CHANGING HOW omega IS SUPPLIED. !!
    Writing the first-order exchange as theta_m dC_m/dt = -alpha(C_m - C_im) and
    theta_im dC_im/dt = +alpha(C_m - C_im), the non-zero eigenvalue of the pair is
        a = alpha*(1/theta_m + 1/theta_im)
    which equals the `omega*(1+beta)/beta` used here ONLY under the MOBILE-side
    convention  omega == alpha/theta_mobile.  Under the immobile-side convention
    (omega == alpha/theta_immobile, which is what the standard slab approximation
    omega ~ 3*De/(R_m*L^2) actually returns) the correct constant is a = omega*(1+beta).

    The two differ by a factor of beta -- 2 to 20 in this model. `DUAL_POROSITY
    ["mass_transfer_omega"]` is a pinned literature scalar with no stated
    convention, so nothing served or trained today is affected; but
    `matrix_transfer_omega()` DOES derive the immobile-side rate, and feeding it
    here without converting would introduce exactly that factor-beta error. That
    path is gated off (P.OMEGA_FROM_GEOMETRY = False) and the gate carries the
    same warning. Documented 2026-08-10 (review3.md D-4) so the flag cannot be
    flipped on into a silent error.
    """
    if beta <= 0.0 or omega <= 0.0:
        return 1.0
    a = omega * (1.0 + beta) / beta
    return 1.0 + beta * (1.0 - math.exp(-a * max(t_days, 0.0)))


def retarded_clock(t_days: float, beta: float, omega: float) -> float:
    """Closed-form I(t) = int_0^t dt'/R_app(t')  [days]. A front moving at base
    velocity v with time-dependent retardation covers  x(t) = v * I(t).
    I(t) ~ t early (unretarded), slope -> 1/(1+beta) late.

    NUMERICS: the log term is written as log1p(-beta*expm1(-a*t)), which is the
    algebraic identity of log((1+beta) - beta*exp(-a*t)) but exact for LARGE
    beta. With the sorbing capacity ratio (effective_capacity_ratio below) beta
    reaches ~1e6 for radium, where the naive difference (1+beta) - beta*exp(-a*t)
    cancels catastrophically at small a*t."""
    t = max(t_days, 0.0)
    if beta <= 0.0 or omega <= 0.0:
        return t
    a = omega * (1.0 + beta) / beta
    I = t / (1.0 + beta) + math.log1p(-beta * math.expm1(-a * t)) / (a * (1.0 + beta))
    if not math.isfinite(I) or I < 0.0:                # unreachable by construction
        raise ValueError(f"retarded_clock non-finite: t={t}, beta={beta}, omega={omega}")
    return I


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
def matrix_retardation(phi_total: float, grain_density: float,
                       kd_L_kg: float) -> float:
    """MATRIX retardation R_m = 1 + rho_b*Kd/theta_m [-] -- sorption onto the
    pore walls of the rock matrix between the fractures. This is the ONE place
    Kd physically acts in fractured rock (bulk-density retardation of the
    fracture water would be wrong: the solute contacts fracture walls, not the
    whole rock volume).

    Single source of truth for BOTH consumers, which must never drift apart:
      * matrix_sigma()             -- the Tang diffusion group (attenuation);
      * effective_capacity_ratio() -- the dual-porosity storage term (kinematics).
    """
    theta_m = float(np.clip(phi_total, 1e-3, 0.45))
    rho_b = (1.0 - theta_m) * grain_density                    # kg/m3
    return 1.0 + rho_b * (max(kd_L_kg, 0.0) * 1e-3) / theta_m  # Kd L/kg -> m3/kg


def effective_capacity_ratio(beta: float, phi_total: float, grain_density: float,
                             kd_L_kg: float,
                             strength: float = None) -> float:
    """SORBING dual-porosity capacity ratio  beta_eff = beta * R_m  [-].

    beta = theta_immobile/theta_mobile is the capacity ratio for a CONSERVATIVE
    tracer: how much dissolved mass the immobile (matrix) water can hold per unit
    of mobile (fracture) water. A sorbing solute also loads the matrix GRAIN
    surfaces, so the immobile zone's capacity is larger by exactly the matrix
    retardation R_m [Goltz & Roberts 1986 mobile/immobile with sorption; the
    same scaling every crystalline-repository safety case uses]:

        beta_eff = (theta_im * R_im) / (theta_m * R_mobile) ~= beta * R_m

    (R_mobile ~ 1: an open fracture has negligible sorptive surface per unit
    water volume compared with the matrix.)

    WHY THIS MATTERS: before this correction the fractured front was SPECIES-
    BLIND -- Kd entered only the Tang term, which is unioned with `max()` and can
    therefore only EXTEND the plume, never retard it. Radium (Kd 500 L/kg,
    R_m ~ 4.4e4) travelled exactly as fast as sulfate. See review.md finding #2.

    NOT double-counting the Tang kernel: Tang describes diffusive ATTENUATION of
    the front into the matrix, this describes the front's RETARDATION by matrix
    storage. They are two facets of the same process represented in the two
    branches of the `max()` union, and both must respond to Kd or the union's
    weaker branch silently governs.

    RESIDUAL LIMITATION (deliberate, documented -- fidelity matrix row 3.4):
    the first-order transfer rate omega (DUAL_POROSITY["mass_transfer_omega"]) is
    held FIXED while beta_eff scales with sorption. Physically omega should also
    fall as matrix retardation rises (slower diffusive equilibration), so this is
    a PARTIAL correction that still under-retards strongly sorbing species at
    early time. Grounding omega needs the same unpublished SSZ tracer test as
    beta itself.

    `strength` (default P.BETA_SORPTION_STRENGTH) damps the correction as
    beta_eff = beta * R_m**strength; 1.0 = the full physically-indicated value,
    0.0 = the pre-correction species-blind behaviour.
    """
    if beta <= 0.0:
        return 0.0
    s = P.BETA_SORPTION_STRENGTH if strength is None else float(strength)
    Rm = matrix_retardation(phi_total, grain_density, kd_L_kg)
    return float(beta * (Rm ** s))


def matrix_transfer_omega(phi_mobile: float, phi_total: float,
                          grain_density: float, kd_L_kg: float,
                          De_m2_day: float | None = None,
                          half_aperture_m: float | None = None) -> float:
    """First-order mobile/immobile transfer rate omega [1/day], DERIVED from the
    fracture geometry the rest of the model already assumes.

    WHY THIS IS NOT A CONSTANT (remediation 2026-08-05, round 2)
    ------------------------------------------------------------
    omega sets how fast the immobile (matrix) capacity is actually reached; the
    retarded clock approaches its asymptotic 1+beta on a timescale 1/omega. It
    was pinned at 1e-3/day -- about 2.7 years -- for EVERY species. But the time
    to load a matrix block is t ~ L^2*R_m/De, which depends strongly on sorption,
    so one constant is wrong in both directions at once. Using the model's own
    aperture and mobile porosity (parallel-plate: phi_mobile = b_half/L, so
    L = b_half/phi_mobile ~ 1.7 cm here):

        species   R_m      t_eq          omega_physical vs the pinned 1e-3
        TDS         1.0    0.2 yr        54x   FASTER  (model over-retarded it)
        sulfate     5.4    0.8 yr        10x   faster
        uranium    89.9   13.7 yr        0.6x  slower
        radium   44459   6767   yr      826x   SLOWER  (model let it equilibrate
                                                 in 2.7 yr when the physics needs
                                                 millennia)

    So the constant made conservative tracers look MORE retarded than they are
    and strongly sorbing species reach a full matrix-equilibrated retardation
    they cannot physically reach inside this tool's 0-50 year horizon.

    Standard slab approximation to Fickian matrix diffusion [van Genuchten &
    Wierenga 1976; Parker & Valocchi 1986]:  omega ~ 3*D_a/L^2, D_a = De/R_m.
    Introduces NO new parameter -- L comes from the aperture and mobile porosity
    already in the feature row.

    !! UNIT-CONVENTION WARNING (2026-08-10, review3.md D-4). !! The value this
    function returns is the IMMOBILE-side rate alpha/theta_immobile, but
    `apparent_retardation` / `retarded_clock` expect the MOBILE-side convention
    alpha/theta_mobile (they use a = omega*(1+beta)/beta, not omega*(1+beta)).
    Enabling P.OMEGA_FROM_GEOMETRY without multiplying this result by beta would
    therefore under-state the clock constant by a factor of beta (2-20). The flag
    is OFF and the branch is documented-and-rejected for an independent reason
    (see the config note: geometry-derived omega makes early-time retardation
    species-blind because R_m cancels in beta_eff*omega). Fix BOTH before ever
    turning it on.

    HONEST LIMITATION: a first-order model cannot reproduce the sqrt(t)
    early-time behaviour of true diffusion at all; it relaxes exponentially. The
    Tang kernel (matrix_sigma / tang_attenuation) is the exact solution and is
    unioned with this branch precisely so the exact one can govern. This makes
    the approximate branch consistent with the geometry rather than correct.
    """
    De = De_m2_day if De_m2_day is not None else P.FRACTURE["De_m2_day"]
    b_half = (half_aperture_m if half_aperture_m is not None
              else P.FRACTURE["full_aperture_m"][1] / 2.0)
    if not P.OMEGA_FROM_GEOMETRY:
        return float(P.DUAL_POROSITY["mass_transfer_omega"])
    Rm = matrix_retardation(phi_total, grain_density, kd_L_kg)
    L = max(b_half / max(phi_mobile, 1e-4), 1e-4)      # matrix half-spacing [m]
    Da = De / Rm
    om = 3.0 * Da / (L * L)
    # keep it inside a sane band: below the floor the clock never matures within
    # the horizon (harmless but pointless), above the ceiling it matures
    # instantly and the dual-porosity branch degenerates to a constant Rd.
    return float(min(max(om, P.OMEGA_BOUNDS[0]), P.OMEGA_BOUNDS[1]))


def disc_growth_factor(pore_volumes: float) -> float:
    """Radius multiplier for the E1 leach-zone disc, from cumulative throughput.

    The disc is "the rock the lixiviant deliberately swept". At t = 0 nothing has
    been injected, so nothing has been swept -- yet the disc was drawn at FULL
    radius and FULL C0 from the first instant, reporting 7.07 ha of "vulnerable
    area" (pi*(W/2)^2 for W=300 m) at zero pore volumes injected. That is
    contamination reported before the mine has operated for a single day.

    AREA is what the user reads, so the AREA is scaled linearly with the pattern
    pore volumes flushed, i.e. the radius by sqrt: f_r = sqrt(min(1, PV)).
    Saturates at PV = 1 (the pattern's mobile pore water fully displaced once),
    which at realistic ISR injection rates happens within weeks -- so this
    changes the first moments of the run and nothing else.
    """
    return float(math.sqrt(min(max(pore_volumes, 0.0), 1.0)))


def matrix_sigma(phi_total: float, grain_density: float, kd_L_kg: float,
                 De_m2_day: float | None = None,
                 half_aperture_m: float | None = None) -> float:
    """Matrix-diffusion group sigma = theta_m * sqrt(R_m * De) / b_half
    [1/sqrt(day)]. R_m is the MATRIX retardation (see matrix_retardation) --
    the physical channel through which Kd acts in fractured rock.

    half_aperture_m: the fracture HALF-aperture. None -> the central literature
    value; the Monte-Carlo (synthetic.generate._draw_params) passes a SAMPLED
    value drawn from P.FRACTURE["full_aperture_m"] so the aperture's factor-5
    literature range reaches the P10-P90 bands instead of being served as a point
    value (review.md finding #4). sigma ~ 1/b_half, so this is a first-order
    control on the Tang envelope."""
    De = De_m2_day if De_m2_day is not None else P.FRACTURE["De_m2_day"]
    b_half = (half_aperture_m if half_aperture_m is not None
              else P.FRACTURE["full_aperture_m"][1] / 2.0)
    theta_m = float(np.clip(phi_total, 1e-3, 0.45))
    Rm = matrix_retardation(phi_total, grain_density, kd_L_kg)
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
    # First-order natural attenuation (uranium redox trapping) on the TRAVELING
    # plume terms; never on the disc (the leach zone's reductants were consumed
    # by the lixiviant). Two components of the parcel AGE (EPA/540/S-02/500
    # distinguishes the conc-vs-DISTANCE bulk rate from the conc-vs-TIME point
    # rate -- both are the same reaction, so both must act):
    atten_per_m: float = 0.0        # travel-time part: (k_per_yr/365)/v_c [1/m]
    # hold part: exp(-k * elapsed_hold) for the years the plume sat STILL under
    # restoration hydraulic control -- a frozen slug keeps reacting with the
    # rock (fixes the "long sweep preserves the slug at full strength" paradox,
    # user-observed 2026-07-16). 1.0 = no hold / off.
    atten_hold_factor: float = 1.0


def _ogata_banks_second_term(X, Xc, aL):
    """Second Ogata-Banks (1961) term. vt=Xc and D_L*t=aL*Xc, so v/D_L = 1/aL and
    the term is 1/2 exp(x/aL) erfc[(x+Xc)/(2 sqrt(aL Xc))]. exp overflows long
    before erfc underflows and inf*0 is NaN, so it is evaluated only where the
    exponent is representable; beyond that the product is provably negligible.

    Restored 2026-08-05: DOMENICO_ERROR_ENVELOPE.md measured the truncation
    UNDER-predicting centreline concentration by a median 17-24% (max 42%; 23.6%
    at the 100 m ring) against an exact convolution self-validated to 1.1e-16.
    Asymptotically this term is a Gaussian bump centred on x = Xc, which is why
    the deficit wave had to be re-launched with it (see params_from_features).
    Upstream is unaffected: exp(x/aL) -> 0 for x < 0."""
    expo = X / aL
    # DOMAIN GATE: Ogata-Banks is derived for a SEMI-INFINITE domain x >= 0 with
    # C(0,t) = C0. Upstream the second term is meaningless and drives the sum
    # ABOVE 1 -- measured F_long = 1.18 at x = -9.9 m, i.e. concentration above
    # the source, which then defeated the restoration deficit wave (the wave is
    # pinned to full strength for x <= 0, so an unbounded base term left
    # 2,207 ppb behind and made longer sweeps look dirtier). The truncated form
    # was accidentally bounded (0.5*erfc <= 1), which is why this never showed
    # before. The upstream half-plane remains the documented artifact zone,
    # carried by the E1 disc.
    safe = (expo < 700.0) & (X > 0.0)
    arg2 = (X + Xc) / (2.0 * np.sqrt(aL * Xc))
    return np.where(safe, 0.5 * np.exp(np.where(safe, expo, 0.0)) * erfc(arg2), 0.0)


def _long_factor(X: np.ndarray, Xc: float, aL: float) -> np.ndarray:
    Xc = max(Xc, 1e-3)
    aL = max(aL, 1e-3)
    return np.clip(0.5 * erfc((X - Xc) / (2.0 * np.sqrt(aL * Xc)))
                   + _ogata_banks_second_term(X, Xc, aL), 0.0, 1.0)


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


def source_strength_fraction(residual_ref: float, t_days: float, op_days: float,
                             rest_days: float) -> float:
    """C_src(t)/C0 -- the SINGLE definition of source strength at evaluation time.

    Combines the two effects that weaken the source after mining stops:
      * `restoration_source_fraction` -- the ELAPSED-sweep clean-up credit
        (causal; a planned-but-unexecuted sweep has cleaned nothing);
      * `disc_flush_factor` -- passive flushing of the leach zone by regional
        flow once injection stops (30-yr half-life, EPA monitoring horizon).

    REBOUND FLOOR (P.RESTORATION_REBOUND_FLOOR, 2026-08-10). Multiplying the two
    let a restored source decay indefinitely, passing BELOW the empirical Texas
    restoration endpoint -- 0.023xC0 at op 8 / t 50 yr against a measured 0.060.
    That endpoint is measured on post-restoration STABILITY samples, i.e. after
    the aquifer demonstrably stopped changing, so any rebound is already inside
    it and further decay is unsupported. Once a sweep has run, the flush may not
    take the source below the realized restoration credit. Unrestored scenarios
    are untouched and keep the full flush.

    EXISTS AS A SHARED HELPER ON PURPOSE. This expression previously lived
    verbatim in BOTH physics.params_from_features and generate._draw_params, and
    divergence between mirrored sites is this project's most repeated defect
    (radium residual, species tuple, Cb defaults). One definition, two callers.
    """
    credit = restoration_source_fraction(residual_ref, t_days, op_days, rest_days)
    f = credit * disc_flush_factor(t_days, op_days)
    if P.RESTORATION_REBOUND_FLOOR and rest_days > 0.0:
        f = max(f, credit)
    return float(min(max(f, 0.0), 1.0))


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
    # t = 0: NOTHING HAS BEEN INJECTED, so the plume is identically zero.
    # (review2.md V-8, fixed 2026-08-10.) Domenico is a CONTINUOUS-source
    # solution and its t -> 0+ limit is C -> 0 for every x > 0; the served answer
    # was 0.336 m of "migration" purely because _long_factor clamps Xc to 1e-3 m,
    # turning the degenerate front into a narrow step that dispersion then smears.
    # The area metric already read 0.00 ha at t = 0 (the E1 disc scales with
    # injected pore volumes), so the two headline numbers contradicted each other
    # at the origin. Same class of error as the 7.07 ha t = 0 disc bug.
    # Training times start at t = 2 yr, so no label moves -- this is serve-only.
    if p.t_days <= 0.0:
        return np.zeros_like(np.asarray(X, dtype=float))
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
        # clean-up slow -- conservative. The SOURCE ZONE (x <= 0) always takes
        # the FULL deficit: its concentration is C_src by definition; the erfc
        # profile applies downstream only (2026-07-16 -- with the front barely
        # downstream, the erfc's upstream bleed left the box only ~90% wiped,
        # a transient partial-C0 strip the user saw as 'the dark red center
        # disc coming back').
        F_c = _long_factor(X, p.Xc_clean, p.aL)
        F_c = np.where(X <= 0.0, 1.0, F_c)
        C = C - (p.C0 - p.C_res) * F_c * A_tran
    # First-order natural attenuation (uranium redox trapping): dissolved U(VI)
    # reduces to immobile U(IV) wherever it contacts reducing rock. The decay
    # follows the parcel AGE = plug-flow travel time (x/v_c, the conc-vs-
    # distance form) + the years the plume was HELD by restoration hydraulic
    # control (the conc-vs-time form; the escaped plume was emitted during
    # operations, so it sits through the sweep). Applied to the WHOLE traveling
    # expression (base plume AND deficit wave share the factor -- else the wave
    # could subtract more than exists at distance x), only for x > 0 so the
    # source plane / upstream box are untouched (their decline is the
    # flush/restoration, not down-gradient redox).
    if p.atten_per_m > 0.0 or p.atten_hold_factor < 1.0:
        decay = np.exp(-p.atten_per_m * np.clip(X, 0.0, None))
        if p.atten_hold_factor < 1.0:
            decay = decay * np.where(X > 0.0, p.atten_hold_factor, 1.0)
        C = C * decay
    # E1: leach-zone disc -- the well-field footprint is contaminated by
    # construction. Unioned only for display + AREA (include_disc); the plume-
    # travel metrics exclude it so a wide source footprint reaching the ring is
    # not mistaken for a plume excursion. NO attenuation on the disc: its
    # reductants were deliberately oxidized by the lixiviant.
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


def _advective_leakage(i_up: float, *, Kv: float, phi_confining: float,
                       dz_adv: float, t_days: float, conc_factor: float) -> dict:
    """Upward Darcy leakage through the confining zone at vertical gradient i_up.

    Split out of shallow_impact_screening (3.7) so the SAME pathway can be
    re-evaluated at the wet- and dry-season gradients without duplicating the
    law. A non-positive gradient closes the pathway (no upward flow) -- it never
    produces a negative risk, so i_up is floored at 0 by the caller."""
    v_up = Kv * max(i_up, 0.0) / max(phi_confining, 1e-3)          # m/day
    barrier = float(np.clip(v_up * max(t_days, 0.0) / dz_adv, 0.0, 1.0))
    yrs = (dz_adv / v_up / 365.0) if v_up > 1e-9 else float("inf")
    return {"gradient": round(float(i_up), 5),
            "v_up_m_day": round(float(v_up), 6),
            "barrier_crossed": round(barrier, 3),
            "p_advective": round(barrier * conc_factor, 3),
            "years_to_breakthrough": (None if not np.isfinite(yrs) else round(yrs, 1))}


def shallow_impact_screening(*, C0: float, background: float, threshold: float,
                             Xc_m: float, source_width_m: float, alpha_L: float,
                             alpha_V: float, ore_depth_m: float,
                             ore_thickness_m: float, layer1_base_m: float,
                             K_m_day: float, phi_confining: float,
                             Kv_Kh_ratio: float, upward_gradient: float,
                             t_days: float, wellbore_failure_prob: float,
                             water_table_m: float | None = None,
                             water_table_wet_m: float | None = None,
                             water_table_dry_m: float | None = None,
                             water_table_now_m: float | None = None) -> dict:
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
    _leak = lambda i: _advective_leakage(                              # noqa: E731
        i, Kv=Kv, phi_confining=phi_confining, dz_adv=dz_adv,
        t_days=t_days, conc_factor=conc_factor)
    base = _leak(upward_gradient)
    barrier_crossed = base["barrier_crossed"]
    p_adv = base["p_advective"]
    yrs_break = (float("inf") if base["years_to_breakthrough"] is None
                 else base["years_to_breakthrough"])

    # (3) wellbore/legacy-borehole shortcut -- base rate, concentration-gated
    p_well = (float(wellbore_failure_prob) * conc_factor
              if C0 > background else 0.0)

    p_shallow = 1.0 - (1.0 - p_disp) * (1.0 - p_adv) * (1.0 - p_well)
    pathways = {"dispersive": p_disp, "advective_leakage": p_adv, "wellbore": p_well}
    dominant = (max(pathways, key=pathways.get) if p_shallow >= 0.05 else "contained")

    # ---- 3.7 SEASONAL BAND ------------------------------------------------- #
    # The monsoon does not push the plume sideways (measured: horizontal gradient
    # swings ~5%); it raises and lowers the shallow head that sits ON TOP of the
    # confining zone, opening and closing the upward pathway. dtw is DEPTH to
    # water, so a LARGER dtw (dry/May) = lower head = LESS downward push = the
    # upward gradient is ENHANCED; a smaller dtw (wet/Aug) suppresses it.
    # Reported as a two-end-member band because the DEEP head's seasonal response
    # is unmeasured -- see P.VERTICAL_SEASONAL for the full derivation.
    seasonal = None
    _SEA = P.VERTICAL_SEASONAL
    if _SEA.get("enabled", False):
        wet = float(water_table_wet_m if water_table_wet_m is not None
                    else _SEA["water_table_wet_m"])
        dry = float(water_table_dry_m if water_table_dry_m is not None
                    else _SEA["water_table_dry_m"])
        per_pin = (water_table_wet_m is not None and water_table_dry_m is not None)
        if dry < wet:                       # the dry-season table is the DEEPER one
            wet, dry = dry, wet
        wt_mean = 0.5 * (wet + dry)

        def _combine(pa: float) -> float:
            return 1.0 - (1.0 - p_disp) * (1.0 - pa) * (1.0 - p_well)

        def _state(d_i: float) -> dict:
            lk = _leak(upward_gradient + d_i)
            ps = _combine(lk["p_advective"])
            return {**lk, "shallow_impact_probability": round(ps, 3),
                    "risk_band": _vertical_risk_band(ps)}

        # UPPER BOUND -- deep head seasonally flat: the whole swing lands on i_v
        static = {"wet_season": _state((wet - wt_mean) / dz_adv),
                  "dry_season": _state((dry - wt_mean) / dz_adv)}
        # LOWER BOUND -- deep head in phase: differential unchanged = today
        in_phase = {"wet_season": _state(0.0), "dry_season": _state(0.0)}

        states = [static["wet_season"], static["dry_season"], in_phase["wet_season"]]
        yrs = [s["years_to_breakthrough"] for s in states
               if s["years_to_breakthrough"] is not None]
        bands = [s["risk_band"] for s in states]
        _ORDER = ["contained", "low", "moderate", "high"]
        seasonal = {
            "water_table_wet_m": round(wet, 2),
            "water_table_dry_m": round(dry, 2),
            "seasonal_swing_m": round(dry - wet, 2),
            "water_table_source": "pin" if per_pin else "state_median",
            "separation_m": round(dz_adv, 1),
            "baseline_gradient": round(float(upward_gradient), 5),
            "gradient_swing": round((dry - wet) / dz_adv, 5),
            "static_deep_head": static,
            "in_phase_deep_head": in_phase,
            # the honest headline: the interval, never a single number
            "breakthrough_years_range": ([min(yrs), max(yrs)] if yrs else None),
            "breakthrough_never_possible": len(yrs) < len(states),
            "risk_band_range": [min(bands, key=_ORDER.index),
                                max(bands, key=_ORDER.index)],
            # Sensitivity must NOT be judged on the band label alone: a pin can
            # stay "contained" in both seasons while breakthrough moves 5x (e.g.
            # Jaduguda, 11.5 -> 56.8 yr). Either a band change OR a materially
            # different arrival time makes the season decision-relevant.
            "seasonally_sensitive": bool(
                bands[0] != bands[1]
                or len(yrs) < len(states)                    # one season never breaks
                or (yrs and max(yrs) > 1.5 * min(yrs))),
            "deep_head_caveat": _SEA["deep_head_caveat"],
            "source_citation": _SEA["source_citation"],
        }
        # TIMELINE: the state at the animation's CURRENT calendar month. Same
        # two end members, evaluated at this month's interpolated water table
        # instead of the seasonal extremes -- so the timeline reads out a point
        # ON the band that the band itself already brackets, never outside it.
        if water_table_now_m is not None:
            now = float(water_table_now_m)
            seasonal["water_table_now_m"] = round(now, 2)
            seasonal["now"] = {
                "static_deep_head": _state((now - wt_mean) / dz_adv),
                "in_phase_deep_head": _state(0.0),
            }
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
        "seasonal": seasonal,
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


def _centreline_x_max(p: TransportParams) -> float:
    """Generous upper bound for the centreline scan: the front (or the water
    front, which bounds the Tang envelope) plus a dispersion margin."""
    base = max(p.Xc, p.Xw, p.source_width_m, 1.0)
    return float(min(base + 8.0 * math.sqrt(max(p.aL, 1e-3) * base) + 10.0,
                     MAX_GRID_REACH_M))


def centreline_reach(p: TransportParams, thr_inc: float, n: int = 4096) -> float:
    """Greatest DOWN-GRADIENT distance at which the plume still exceeds the
    incremental threshold, evaluated ANALYTICALLY along the centreline (y = 0).

    WHY NOT READ IT OFF THE GRID (remediation 2026-08-05, Gate-3 finding)
    --------------------------------------------------------------------
    The 2-D grid is sized to contain the SOURCE DISC, so its cell size is set by
    the wellfield width (dx ~ 5-13 m), not by the plume. That is fine for area --
    measured stable at 9.06 ha across grid_n 200..6000 -- but it quantises travel
    to nothing whenever the plume is short, which in fractured rock is the normal
    case. Measured over 60 scenarios spanning the generator's envelope: 29 of 60
    returned EXACTLY 0 m on the MC grid while the analytic extent was > 0.05 m,
    and NONE were genuinely immobile. Surviving labels were biased low too
    (2.93 m gridded vs 17.7 m analytic). This was invisible before the migration
    metric was re-based, because the upstream-artifact reading (~420 m) is large
    compared with a 6 m cell -- fixing finding #1 exposed a pre-existing defect.

    Left uncorrected it would have poisoned the retrain: 75% of fractured uranium
    and 99% of fractured radium migration labels were the single value 0.0.

    y = 0 is the correct place to measure: the transverse factor is maximal on the
    centreline, so the farthest exceeding cell anywhere is the farthest exceeding
    point there. A SCAN rather than a bisection because C(x, 0) is not always
    monotone -- once a restoration/flush deficit wave detaches, concentration can
    rise with x (that is the 'dark band migrates down-gradient' signature).
    The source disc is excluded: this is plume travel, not source extent."""
    if p.C0 <= 0.0 or thr_inc <= 0.0:
        return 0.0
    x_max = _centreline_x_max(p)
    xs = np.linspace(x_max / n, x_max, n)
    C = concentration_field(xs[None, :], np.zeros((1, n)), p, include_disc=False)[0]
    hit = np.nonzero(C >= thr_inc)[0]
    return float(xs[hit[-1]]) if hit.size else 0.0


def plume_metrics(C_plume: np.ndarray, X: np.ndarray, Y: np.ndarray, *,
                  threshold: float, background: float, cell_area_m2: float,
                  disc_mask: np.ndarray | None = None) -> dict:
    """Decision metrics from a PLUME-ATTRIBUTABLE (disc-free) concentration field.

    Exceedance is incremental: C_plume >= max(threshold - background,
    INCREMENTAL_FLOOR*threshold). Reported concentrations are absolute. The E1
    source-zone disc (disc_mask) is unioned into the AREA only -- migration /
    downgradient / compliance track the migrating front, never the source zone.

    MIGRATION IS DOWN-GRADIENT TRAVEL (remediation 2026-08-05, review.md #1)
    -----------------------------------------------------------------------
    `max_migration_distance_m` is the greatest DOWN-GRADIENT distance the
    incremental-exceedance contour reaches (max x over the exceeding cells).
    It replaces a radial max, sqrt(x^2 + y^2), taken over the WHOLE grid, which
    was not a travel distance at all and failed in two independent ways:

      1. The Domenico simplification drops the second Ogata-Banks term and so
         paints the ENTIRE upstream half-plane at C0 (ARCHITECTURE section 10) --
         a solution artifact, not a plume. The radial argmax therefore landed on
         the artifact box's upstream CORNER, whose position is set by _auto_grid's
         margins rather than by any physics. At Jaduguda defaults the argmax sat
         at x = -387.8 m and "migration" read 422.8 m while the true down-gradient
         reach was 35.9 m -- identical for every species, because C0 cancels.
      2. Even restricted to x > 0, a radial max is dominated by the SOURCE
         HALF-WIDTH whenever the plume is short and wide (the normal contained
         case): measured on the attenuation fixture, radial 201.5 m against a
         down-gradient reach of 5.0 m and a half-width of 201.4 m -- i.e. it was
         reporting the wellfield's own transverse extent as travel, at a distance
         where the attenuation factor is e^-94.

    The transverse extent is still reported, separately and honestly, as
    `plume_halfwidth_m`; `max_downgradient_m` is retained as an explicit alias so
    existing callers keep working. Both are now scored on the SAME down-gradient
    mask, so the aspect ratio derived from them describes the migrating plume.

    The contaminated SOURCE FOOTPRINT keeps its own representation -- the E1
    leach-zone disc (E1_geometry_design.md section 1), a deliberate member with a
    physically-argued radius -- so restricting the plume mask to x > 0 removes the
    artifact WITHOUT losing the source zone from the area, and stops the artifact
    box and the disc double-counting the same ground.
    """
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    mask = (C_plume >= thr_inc) & (X > 0.0)      # migrating plume only
    if mask.any():
        max_down = float(X[mask].max())          # downgradient reach beyond edge
        plume_halfwidth = float(np.abs(Y[mask]).max())
    else:
        max_down = plume_halfwidth = 0.0
    max_dist = max_down                          # migration == down-gradient travel
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
    # SORBING capacity ratio: beta scaled by the matrix retardation, so the
    # fractured front finally responds to Kd (review.md finding #2). Mirrored in
    # generate._draw_params and feature_engineering.build_feature_row -- all
    # three must agree or train != serve.
    beta_k = (effective_capacity_ratio(beta, feat["phi_total"],
                                       feat.get("_grain_density", 2700.0),
                                       feat["Kd_L_kg"])
              if fractured else 0.0)
    # transfer rate derived from the fracture geometry, not a pinned constant --
    # a single omega is 54x too slow for a tracer and 826x too fast for radium
    om = (matrix_transfer_omega(feat["phi_mobile"], feat["phi_total"],
                                feat.get("_grain_density", 2700.0),
                                feat["Kd_L_kg"])
          if fractured else P.DUAL_POROSITY["mass_transfer_omega"])

    Xc = front_position(v_base, eta, t_days, operation_days, restoration_days,
                        beta_k, omega=om)
    Xw = (front_position(v, eta, t_days, operation_days, restoration_days, 0.0)
          if fractured else Xc)
    sigma = (matrix_sigma(feat["phi_total"], feat.get("_grain_density", 2700.0),
                          feat["Kd_L_kg"]) if fractured else 0.0)

    # Source draw-down (2026-07-13, QA F-1 fix + real-ISR upgrade): the source
    # concentration at eval time is
    #     C_src(t) = C0 x restoration credit x natural post-closure flush
    # - restoration_source_fraction: ELAPSED-sweep credit (causal, continuous);
    # - disc_flush_factor: after injection stops the source zone is passively
    #   flushed by regional flow (30 yr half-life, EPA monitoring horizon) --
    #   restoration is just the ACCELERATED version of this same process.
    # The deficit wave (concentration_field) activates whenever C_src < C0:
    # mid-sweep / early post-closure its front sits AT the source plane (a wall
    # wiping the upstream source-zone box to C_res) and it advances with
    # regional drift -- the ESCAPED plume keeps its history until clean water
    # overtakes it (the "dark band migrates downgradient" signature).
    f_src = source_strength_fraction(float(residual_fraction), t_days,
                                     operation_days, restoration_days)
    Xc_clean, C_res = None, 0.0
    if f_src < 1.0:
        C_res = f_src * species_C0
        # DEFICIT WAVE LAUNCHED AT THE START OF THE SWEEP (2026-08-05).
        # It used to be held for the sweep's whole duration (restoration_days
        # passed here), so a LONGER sweep delayed the clean water further and
        # left MORE contamination: peak conc rose 955 -> 2209 ppb across rest
        # 10 -> 30 yr, violating MONOTONE_MAPS["restoration_years"] = -1, the
        # very law the trainer enforces. Harmless while the longitudinal factor
        # was truncated; exposed the moment the second Ogata-Banks term (a
        # Gaussian bump at x = Xc) was restored to the BASE plume, because the
        # wave's own bump sat at Xc_clean ~ 0 and could no longer cancel it.
        # Clean water enters the source zone when the sweep BEGINS, so the
        # replacement front is released at end-of-operations and drifts from
        # there (rest_days = 0 in its own kinematics).
        Xc_clean = front_position(v_base, 1.0, t_days, operation_days,
                                  0.0, beta_k)

    # E1 leach-zone disc (Stage E): OFF unless P.E1_ENABLED, so the served path
    # stays byte-identical to the deployed-ML geometry until the atomic cutover.
    disc_r = disc_cx = disc_c = 0.0
    if P.E1_ENABLED:
        W = feat["wellfield_width_m"]
        W_eff = feat.get("_source_width_m", W)
        # the swept zone grows with what has actually been injected: at t = 0 the
        # disc was drawn full-size at full C0, reporting ~7 ha contaminated
        # before a single pore volume existed
        disc_r = (W_eff / 2.0) * disc_growth_factor(feat.get("pore_volumes_PV", 1.0))
        disc_cx = -W / 2.0
        # C_res already folds restoration credit x post-closure flush
        disc_c = C_res if Xc_clean is not None else species_C0
    # Hold-time decay: the escaped plume keeps reacting while hydraulic control
    # holds it still during the sweep (elapsed hold = the elapsed sweep).
    atten_hold = 1.0
    k_yr = float(feat.get("u_attenuation_k", 0.0))
    if k_yr > 0.0 and restoration_days > 0.0:
        hold_days = min(max(t_days - operation_days, 0.0), restoration_days)
        atten_hold = math.exp(-(k_yr / 365.0) * hold_days)
    return TransportParams(C0=species_C0, aL=feat["alpha_L"], aT=feat["alpha_T"],
                           source_width_m=feat.get("_source_width_m",
                                                   feat["wellfield_width_m"]),
                           Xc=Xc, Xw=Xw, sigma=sigma, t_days=t_days,
                           Xc_clean=Xc_clean, C_res=C_res,
                           disc_radius_m=disc_r, disc_center_x_m=disc_cx, disc_conc=disc_c,
                           atten_per_m=float(feat.get("_atten_per_m", 0.0)),
                           atten_hold_factor=atten_hold)


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
    # Travel is measured ANALYTICALLY on the centreline, not read off the grid
    # (see centreline_reach): the grid's cell size is set by the source disc, so
    # it quantises short plumes to zero and biases the rest low. Area keeps the
    # gridded value -- it needs the 2-D integration and is grid-stable.
    reach = centreline_reach(params, thr_inc)
    metrics["max_migration_distance_m"] = reach
    metrics["max_downgradient_m"] = reach
    metrics["Xc_m"] = params.Xc
    metrics["off_scale"] = bool(off_scale)
    # Source-zone state, so the UI can EXPLAIN rather than just show a bare 0.
    # The leach disc is uniform-concentration by construction, so when its single
    # value crosses the incremental threshold the whole footprint leaves the
    # exceedance area at once (radium at Jaduguda: 9.06 ha -> 0.00 ha between
    # t = 32 and t = 33 yr, as the 30-yr flush takes disc_conc 979.8 -> 957.5
    # against thr_inc 977). That is arithmetically correct for a uniform disc,
    # but it reads as a fault unless the surface says what happened.
    metrics["source_zone_conc"] = float(params.disc_conc)
    metrics["source_zone_above_threshold"] = bool(params.disc_conc >= thr_inc)
    metrics["source_zone_radius_m"] = float(params.disc_radius_m)

    if compliance_x is not None:
        c_comp = concentration_point(compliance_x, 0.0, params)   # plume-only, true reach
        metrics["compliance_conc"] = c_comp + background          # absolute
        metrics["breaches_at_compliance"] = bool(c_comp >= metrics["incremental_threshold"])

    # ---- DISPLAY FIELD (metrics above are already final -- nothing here can
    # change a label) ------------------------------------------------------
    # DROP THE UPSTREAM ARTIFACT BOX FROM THE MAP (2026-08-05, user-reported).
    # The Domenico simplification paints the whole upstream half-plane at C0
    # (ARCHITECTURE section 10). The METRICS have excluded x <= 0 since the
    # migration re-base, but the DISPLAY field still carried it, so the map drew
    # a solid rectangle of "contamination" upstream of the wellfield -- 4.58 ha
    # of it at t = 0 while the area metric correctly read 0.00 ha. Users saw a
    # rectangle appear before injection started and double within a month.
    # Display and metric must agree; the source footprint is the E1 disc's job.
    C = np.where(X > 0.0, C, 0.0)
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
                 Xc_clean, C_res, rest_active=None, atten_per_m=None,
                 atten_hold=None, disc_radius=None, disc_center_x=None,
                 disc_conc=None, include_disc=True) -> np.ndarray:
    """concentration_field broadcast over draws: X3/Y3 are (ny,nx,1) grids,
    parameter arrays are (nd,). Returns C of shape (ny, nx, nd).

    rest_active: (nd,) bool -- draws with a restoration sweep. Needed because a
    MID-SWEEP draw has Xc_clean == 0.0 (wave wall at the source, QA F-1) which
    the old `Xc_clean > 0` test cannot distinguish from no-restoration."""
    # t = 0 -> nothing injected -> zero plume. Mirrors concentration_field so the
    # two engines cannot disagree at the origin (review2.md V-8).
    if t_days <= 0.0:
        return np.zeros(np.broadcast(X3, Y3, np.asarray(C0)).shape, dtype=float)
    Xc = np.maximum(Xc, 1e-3)
    aL = np.maximum(aL, 1e-3)
    aT = np.maximum(aT, 1e-4)
    A_long = np.clip(0.5 * erfc((X3 - Xc) / (2.0 * np.sqrt(aL * Xc)))
                     + _ogata_banks_second_term(X3, Xc, aL), 0.0, 1.0)
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
        A_c = np.clip(0.5 * erfc((X3 - Xcc) / (2.0 * np.sqrt(aL * Xcc)))
                      + _ogata_banks_second_term(X3, Xcc, aL), 0.0, 1.0)
        A_c = np.where(X3 <= 0.0, 1.0, A_c)       # source zone fully at C_res
        C = C - np.where(active, C0 - C_res, 0.0) * A_c * A_tran
    # first-order U natural attenuation: travel-time + hold-time parts
    # (see concentration_field)
    has_dist = atten_per_m is not None and bool(np.any(atten_per_m > 0.0))
    has_hold = atten_hold is not None and bool(np.any(atten_hold < 1.0))
    if has_dist or has_hold:
        decay = np.exp(-(atten_per_m if atten_per_m is not None else 0.0)
                       * np.clip(X3, 0.0, None))
        if has_hold:
            decay = decay * np.where(X3 > 0.0, atten_hold, 1.0)
        C = C * decay
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
            atten_per_m=arr(lambda p: p.atten_per_m),
            atten_hold=arr(lambda p: p.atten_hold_factor),
            include_disc=False)
        # DOWN-GRADIENT ONLY -- must mirror plume_metrics exactly (see its
        # docstring). THIS is the path that produces the ML training labels, so
        # fixing only the scalar engine would have left the upstream-artifact
        # migration baked into every trained band. test_physics_laws.py's
        # central-vs-MC parity test pins the two implementations together.
        plume_mask = (C >= thr_inc) & (X3 > 0.0)
        cell = float(abs((X[0, 1] - X[0, 0]) * (Y[1, 0] - Y[0, 0])))
        # AREA also counts the source-zone disc; MIGRATION is the plume front only
        if bool(np.any(dr > 0.0)):
            disc3 = ((X3 - dcx) ** 2 + Y3 ** 2 <= dr ** 2) & (dc >= thr_inc)
            area_mask = plume_mask | disc3
        else:
            area_mask = plume_mask
        area[bucket] = area_mask.sum(axis=(0, 1)) * cell / 1e4
        # MIGRATION: analytic centreline scan, NOT the grid (see centreline_reach).
        # The 2-D cell size here is set by the source disc, so reading travel off
        # it returned exactly 0.0 for 29 of 60 sampled scenarios that were not
        # immobile at all -- 75% of fractured uranium training labels would have
        # been the same degenerate value. Vectorised over draws: a 1-D centreline
        # is cheap next to the 2-D field it replaces.
        # PER-DRAW scan scale: each draw gets its own x_max (the same
        # _centreline_x_max the scalar engine uses), so a small plume sharing a
        # bucket with a large one keeps full resolution, and a single-draw bucket
        # reproduces solve_plume EXACTLY rather than to within a scan step.
        n1 = 4096
        xm = arr(_centreline_x_max)                       # (nd,)
        frac = np.linspace(1.0 / n1, 1.0, n1)             # (n1,)
        x1m = (frac[:, None] * xm[None, :])[None, :, :]   # (1, n1, nd)
        C1 = _stack_field(
            x1m, np.zeros_like(x1m),
            C0=arr(lambda p: p.C0), aL=arr(lambda p: p.aL), aT=arr(lambda p: p.aT),
            W=arr(lambda p: p.source_width_m), Xc=arr(lambda p: p.Xc),
            Xw=arr(lambda p: p.Xw), sigma=arr(lambda p: p.sigma),
            t_days=plist[bucket[0]].t_days,
            Xc_clean=arr(lambda p: p.Xc_clean if p.Xc_clean is not None else 0.0),
            C_res=arr(lambda p: p.C_res),
            rest_active=np.array([plist[i].Xc_clean is not None for i in bucket]),
            atten_per_m=arr(lambda p: p.atten_per_m),
            atten_hold=arr(lambda p: p.atten_hold_factor),
            include_disc=False)[0]                       # (n1, nd)
        over = C1 >= thr_inc                              # (n1, nd)
        idx = np.where(over.any(axis=0),
                       (over.shape[0] - 1) - np.argmax(over[::-1], axis=0), -1)
        x1_2d = x1m[0]                                    # (n1, nd)
        dist[bucket] = np.where(
            idx >= 0,
            x1_2d[np.clip(idx, 0, None), np.arange(len(bucket))], 0.0)

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
