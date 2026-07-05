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


def _long_factor(X: np.ndarray, Xc: float, aL: float) -> np.ndarray:
    Xc = max(Xc, 1e-3)
    aL = max(aL, 1e-3)
    return 0.5 * erfc((X - Xc) / (2.0 * np.sqrt(aL * Xc)))


def _tran_factor(X: np.ndarray, Y: np.ndarray, aT: float, W: float) -> np.ndarray:
    aT = max(aT, 1e-4)
    Xpos = np.where(X > 0.1, X, 0.1)
    tw = 2.0 * np.sqrt(aT * Xpos)
    return 0.5 * (erf((Y + W / 2.0) / tw) - erf((Y - W / 2.0) / tw))


def concentration_field(X: np.ndarray, Y: np.ndarray, p: TransportParams) -> np.ndarray:
    """Plume-attributable concentration (NO background) on meshgrids X, Y."""
    A_tran = _tran_factor(X, Y, p.aT, p.source_width_m)
    A_long = _long_factor(X, p.Xc, p.aL)
    if p.sigma > 0.0 and p.Xw > p.Xc:
        # early-arrival envelope: union of retarded-continuum front and the
        # matrix-attenuated discrete-fracture solution (conservative max)
        A_long = np.maximum(A_long, tang_attenuation(X, p.t_days, p.Xw, p.sigma))
    C = p.C0 * A_long * A_tran
    if p.Xc_clean is not None and p.Xc_clean > 0.0 and p.C_res < p.C0:
        # restoration: clean-water replacement wave subtracts (C0 - C_res).
        # The clean front uses the RETARDED kinematics only (no Tang boost):
        # matrix back-diffusion makes clean-up slow -- conservative.
        C = C - (p.C0 - p.C_res) * _long_factor(X, p.Xc_clean, p.aL) * A_tran
    return np.clip(C, 0.0, p.C0)


def concentration_point(x: float, y: float, p: TransportParams) -> float:
    """Scalar evaluation (compliance ring / Monte Carlo) -- no grid needed."""
    xa = np.array([[float(x)]])
    ya = np.array([[float(y)]])
    return float(concentration_field(xa, ya, p)[0, 0])


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


def _auto_grid(reach_m: float, aL: float, source_width: float, n: int = 220):
    """Build a meshgrid sized to comfortably contain the plume."""
    reach = reach_m + 4.0 * np.sqrt(max(aL, 1e-3) * max(reach_m, 1.0)) + source_width
    reach = max(reach, source_width * 2.0, 50.0)
    x = np.linspace(-0.25 * reach, reach, n)
    y = np.linspace(-0.6 * reach, 0.6 * reach, n)
    X, Y = np.meshgrid(x, y)
    return X, Y


def plume_metrics(C_plume: np.ndarray, X: np.ndarray, Y: np.ndarray, *,
                  threshold: float, background: float, cell_area_m2: float) -> dict:
    """Decision metrics from a PLUME-ATTRIBUTABLE concentration field.

    Exceedance is incremental: C_plume >= max(threshold - background,
    INCREMENTAL_FLOOR*threshold). Reported concentrations are absolute.
    """
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    mask = C_plume >= thr_inc
    area_m2 = float(mask.sum()) * cell_area_m2
    if mask.any():
        r = np.sqrt(X[mask] ** 2 + Y[mask] ** 2)
        max_dist = float(r.max())
        max_down = float(X[mask].max())          # downgradient reach beyond edge
        plume_halfwidth = float(np.abs(Y[mask]).max())
    else:
        max_dist = max_down = plume_halfwidth = 0.0
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

    Xc_clean, C_res = None, 0.0
    t_rest_end = operation_days + max(restoration_days, 0.0)
    if restoration_days > 0.0 and t_days > t_rest_end:
        Xc_clean = front_position(v_base, 1.0, t_days, operation_days,
                                  restoration_days, beta_k)
        C_res = float(residual_fraction) * species_C0

    return TransportParams(C0=species_C0, aL=feat["alpha_L"], aT=feat["alpha_T"],
                           source_width_m=feat.get("_source_width_m",
                                                   feat["wellfield_width_m"]),
                           Xc=Xc, Xw=Xw, sigma=sigma, t_days=t_days,
                           Xc_clean=Xc_clean, C_res=C_res)


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
                      params.source_width_m, n=grid_n)
    C = concentration_field(X, Y, params)

    dx = X[0, 1] - X[0, 0]
    dy = Y[1, 0] - Y[0, 0]
    cell_area = float(abs(dx * dy))
    metrics = plume_metrics(C, X, Y, threshold=threshold, background=background,
                            cell_area_m2=cell_area)
    metrics["Xc_m"] = params.Xc
    metrics["off_scale"] = bool(off_scale)

    if compliance_x is not None:
        c_comp = concentration_point(compliance_x, 0.0, params)   # true reach
        metrics["compliance_conc"] = c_comp + background          # absolute
        metrics["breaches_at_compliance"] = bool(c_comp >= metrics["incremental_threshold"])

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
                 Xc_clean, C_res) -> np.ndarray:
    """concentration_field broadcast over draws: X3/Y3 are (ny,nx,1) grids,
    parameter arrays are (nd,). Returns C of shape (ny, nx, nd)."""
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
    active = Xc_clean > 0.0
    if bool(np.any(active)):
        Xcc = np.maximum(Xc_clean, 1e-3)
        A_c = 0.5 * erfc((X3 - Xcc) / (2.0 * np.sqrt(aL * Xcc)))
        C = C - np.where(active, C0 - C_res, 0.0) * A_c * A_tran
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
        X, Y = _auto_grid(reach_b, aL_b, W_b, n=grid_n)
        X3, Y3 = X[:, :, None], Y[:, :, None]
        C = _stack_field(
            X3, Y3,
            C0=arr(lambda p: p.C0), aL=arr(lambda p: p.aL), aT=arr(lambda p: p.aT),
            W=arr(lambda p: p.source_width_m), Xc=arr(lambda p: p.Xc),
            Xw=arr(lambda p: p.Xw), sigma=arr(lambda p: p.sigma),
            t_days=plist[bucket[0]].t_days,
            Xc_clean=arr(lambda p: p.Xc_clean if p.Xc_clean is not None else 0.0),
            C_res=arr(lambda p: p.C_res))
        mask = C >= thr_inc
        cell = float(abs((X[0, 1] - X[0, 0]) * (Y[1, 0] - Y[0, 0])))
        area[bucket] = mask.sum(axis=(0, 1)) * cell / 1e4
        R3 = np.sqrt(X ** 2 + Y ** 2)[:, :, None]
        dist[bucket] = np.where(mask, R3, 0.0).max(axis=(0, 1))

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
