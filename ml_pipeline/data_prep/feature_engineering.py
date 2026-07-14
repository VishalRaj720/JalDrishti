"""
ml_pipeline.data_prep.feature_engineering  (PHASE 1)
==================================================
Physics-based domain adaptation. Texas (uniform porous sandstone) and Jharkhand
(12 lithologies, fractured or weathered) cannot share *absolute* coordinates or
velocities. They CAN share dimensionless transport groups. This module turns any
(hydrogeology, operating point, species, evaluation time) tuple into that
shared, scale-independent feature vector.

The hydrogeological chain (each link documented):

  Darcy flux          q   = K * i                         [m/day]
  Seepage velocity    v   = K * i / phi_mobile            [m/day]   <-- advection
  Retardation         Rd  = 1 + (rho_b / n_total) * Kd    [-]       <-- chemistry
                            (fractured: asymptotic 1+beta; the TRANSPORT front
                             uses the time-dependent R_app(t) clock in
                             physics.transport)
  Contaminant vel.    vc  = v / Rd                        [-> feature]
  Front position      Xc(t) = three-phase retarded front  [m]  (physics.transport)
  Dispersivity        aL  = 0.83*(log10 L)^2.414 at L=max(Xc(t), W)  [Xu&Eckstein]
  Dispersion          DL  = aL*v ; DT = aT*v              [m2/day]
  Peclet number       Pe  = L / aL                        [-]       <-- adv/disp balance
  Pore volumes        PV(t) = Q_in*min(t,t_op) / (n_mobile * V_swept)  [-]
  Bulk volumes        BV(t) = Q_in*min(t,t_op) / V_swept  [-]  (drives source growth)
  Containment         eta = min(1, Q_net / (q*b*W))       [-]  capture fraction
  Dimensionless time  tau = vc * t / W                    [-]  front-lengths per
                                                               source width

GEOMETRY: `wellfield_width_m` is the FULL width W everywhere; the pattern
footprint is a circle of radius W/2, so V_swept = pi*(W/2)^2*b. The Domenico
source plane sits at the downgradient wellfield edge (see physics.transport).

TIME CONSISTENCY (2026-07 review): PV, BV, W_eff and the dispersivity length
scale are functions of the EVALUATION time t, not of the total operation
duration -- an early time slice only carries the source widening its injected
volume has actually caused.

Anisotropy (aL/aT) is high for fractured (directional channeling along strike)
and low for porous (rounder plume) -- exactly the feature the model uses to
switch between the two transport styles.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P
from ml_pipeline.physics.transport import front_position, restoration_source_fraction

# Canonical, ORDERED feature list. Phase 2 (synthetic) and Phase 3 (training)
# must emit/consume exactly these columns so Texas and Jharkhand rows align.
FEATURE_COLUMNS = [
    # --- regime / source domain -------------------------------------------
    "regime_is_fractured",          # 1 = fractured/hard-rock, 0 = porous/weathered
    "domain_is_texas",              # 1 = real Texas row, 0 = synthetic Jharkhand
    # --- intrinsic hydrogeology -------------------------------------------
    "K_m_day", "gradient_i", "phi_mobile", "phi_total",
    "darcy_flux_q", "seepage_velocity_v",
    # --- chemistry / retardation ------------------------------------------
    "Kd_L_kg", "retardation_Rd", "contaminant_velocity_vc",
    # --- dispersion / anisotropy ------------------------------------------
    "alpha_L", "alpha_T", "anisotropy_ratio", "D_L", "D_T",
    # --- dimensionless transport groups (the transferable core) -----------
    "peclet_L", "pore_volumes_PV", "dimensionless_time_tau",
    "dual_porosity_beta",
    # --- operations -------------------------------------------------------
    "Q_in_m3_day", "Q_out_m3_day", "bleed_fraction", "Q_net_m3_day",
    "containment_eta", "operation_days", "wellfield_width_m",
    # --- source term ------------------------------------------------------
    "source_conc_C0", "background_conc_Cb",
    # --- operational irregularities & restoration (Phase-2 v2) -------------
    "downtime_fraction",            # capture outage share: eta_eff = eta*(1-f)
    "gradient_seasonal_amp",        # relative seasonal swing of i (MC widening)
    "restoration_years",            # post-mining clean-up sweep duration
    "residual_fraction",            # C_rest/C0 after restoration (1 = none)
]


# --------------------------------------------------------------------------- #
# Elementary physics (each is independently unit-tested in __main__ / tests)
# --------------------------------------------------------------------------- #
def darcy_flux(K_m_day: float, gradient_i: float) -> float:
    """q = K * i   [m/day]  (Darcy's law specific discharge)."""
    return K_m_day * gradient_i


def seepage_velocity(K_m_day: float, gradient_i: float, phi_mobile: float) -> float:
    """v = K*i/phi  [m/day]  (linear/average pore-water velocity).
    Uses the MOBILE (kinematic) porosity -- the only pore space that conducts flow.
    """
    phi_mobile = max(phi_mobile, 1e-4)
    return darcy_flux(K_m_day, gradient_i) / phi_mobile


def retardation_factor(kd_L_kg: float, n_total: float, grain_density: float,
                       regime: str, beta: float = 0.0) -> float:
    """Species retardation Rd [-] (ASYMPTOTIC value; used as a model feature).

    Porous: classic linear-equilibrium  Rd = 1 + (rho_b/n_total)*Kd, with
            rho_b = (1 - n_total)*rho_solid  and Kd converted L/kg -> m3/kg.
    Fractured: bulk-rho retardation is physically wrong (solute only contacts
            fracture walls). The late-time apparent retardation from matrix
            diffusion is 1+beta [Goltz & Roberts 1986]; the transport engine
            applies the TIME-DEPENDENT R_app(t) via its retarded clock, and Kd
            acts inside the matrix-diffusion group sigma (physics.transport).
    """
    if regime == "fractured":
        return 1.0 * (1.0 + max(beta, 0.0))
    n_total = float(np.clip(n_total, 0.02, 0.45))
    rho_b = (1.0 - n_total) * grain_density           # kg/m3
    return 1.0 + (rho_b * (kd_L_kg * 1e-3)) / n_total  # Kd L/kg -> m3/kg


def dispersivities(L_m: float, regime: str) -> tuple[float, float]:
    """(alpha_L, alpha_T) [m]. alpha_L scale-dependent (Xu&Eckstein 1995),
    alpha_T via regime anisotropy ratio (fractured -> very small aT)."""
    aL = P.longitudinal_dispersivity(L_m)
    aT = aL * P.TRANSVERSE_ANISOTROPY[regime]
    return aL, aT


def containment_efficiency(q_m_day: float, thickness_m: float, width_m: float,
                           Q_net_m3_day: float) -> float:
    """Hydraulic-capture fraction eta in [0, 1] -- mass-balance capture.

    Regional groundwater flux through the wellfield cross-section:
        Q_regional = q * b * W           [m3/day]
    Net extraction Q_net = Q_out - Q_in pulls water inward. Capture-zone
    theory: the wellfield intercepts a capture width W_c = Q_net/(q*b);
    the captured fraction of its own footprint is
        eta = min(1, Q_net / Q_regional)
    COMPLETE capture (eta = 1, no outward advection) is achieved when net
    extraction exceeds the regional throughflow -- a properly-bled ISR
    wellfield contains; excursions come from insufficient bleed / failures.
    """
    Q_regional = max(q_m_day * thickness_m * width_m, 1e-9)
    return float(min(1.0, max(Q_net_m3_day, 0.0) / Q_regional))


def pore_volumes(Q_in_m3_day: float, t_days: float, phi_mobile: float,
                 swept_volume_m3: float) -> float:
    """Dimensionless throughput PV = injected volume / mobile pore volume swept."""
    pv_water = max(phi_mobile * swept_volume_m3, 1e-6)
    return (Q_in_m3_day * t_days) / pv_water


def peclet(L_m: float, alpha_L: float) -> float:
    """Grid Peclet number Pe = L/alpha_L (advection vs dispersion dominance)."""
    return L_m / max(alpha_L, 1e-6)


def effective_source_width(wellfield_width_m: float, bulk_volumes_BV: float) -> float:
    """Lixiviant-contacted source width [m], widening (capped) with cumulative
    BULK throughput BV = V_injected / V_pattern_bulk:
        W_eff = W * (1 + gain * tanh(BV / BV_ref))
    Porosity-independent driver -> stays live in fractured rock instead of
    saturating; time-consistent when BV uses min(t, t_op). Bounded at (1+gain)W.
    """
    return wellfield_width_m * (1.0 + P.SOURCE_BV_GAIN
                                * math.tanh(bulk_volumes_BV / P.SOURCE_BV_REF))


# --------------------------------------------------------------------------- #
# Feature-row assembly  (used by Phase 2 generator AND the live dashboard)
# --------------------------------------------------------------------------- #
def build_feature_row(*, regime: str, domain_is_texas: bool,
                      K_m_day: float, gradient_i: float,
                      phi_mobile: float, n_total: float, grain_density: float,
                      kd_L_kg: float, beta: float,
                      Q_in_m3_day: float, bleed_fraction: float,
                      operation_days: float, wellfield_width_m: float,
                      thickness_m: float,
                      source_conc_C0: float, background_conc_Cb: float,
                      eval_time_days: float | None = None,
                      restoration_days: float = 0.0,
                      downtime_fraction: float = 0.0,
                      gradient_seasonal_amp: float = 0.0,
                      residual_fraction: float = 1.0,
                      aniso_ratio: float | None = None) -> dict:
    """Assemble one fully-featured, scale-independent training/inference row.

    eval_time_days: the time slice being evaluated. Throughput (PV/BV), the
    source width and the dispersivity length scale are computed AT this time.
    Defaults to operation_days (end-of-operation state) for standalone use.
    downtime_fraction: share of the operating period with capture down
    (pump failures) -> effective containment eta_eff = eta*(1 - f).
    """
    t_eval = float(eval_time_days) if eval_time_days is not None else float(operation_days)
    q = darcy_flux(K_m_day, gradient_i)
    v = seepage_velocity(K_m_day, gradient_i, phi_mobile)
    Rd = retardation_factor(kd_L_kg, n_total, grain_density, regime, beta)
    vc = v / Rd

    Q_out = Q_in_m3_day * (1.0 + bleed_fraction)
    Q_net = Q_out - Q_in_m3_day
    eta = containment_efficiency(q, thickness_m, wellfield_width_m, Q_net)
    f_down = float(np.clip(downtime_fraction, 0.0, 1.0))
    eta_eff = eta * (1.0 - f_down)

    # Apparent front position at the evaluation time (three-phase kinematics;
    # fractured uses the matrix-uptake clock on the water velocity). Kinematics
    # use the downtime-degraded EFFECTIVE containment.
    fractured = (regime == "fractured")
    v_base = v if fractured else vc
    beta_k = beta if fractured else 0.0
    Xc_eval = front_position(v_base, eta_eff, t_eval,
                             operation_days, restoration_days, beta_k)
    # clean-water replacement front -- model feature. 2026-07-13: launched whenever
    # a restoration sweep exists (no binary completion gate); front_position keeps
    # it at ~0 until regional drift resumes, so it grows continuously rather than
    # snapping on at eval_time == op + restoration. MUST mirror the physics
    # (params_from_features / generate._draw_params) so train == serve.
    Xc_clean = 0.0
    if restoration_days > 0.0:
        Xc_clean = front_position(v_base, 1.0, t_eval, operation_days,
                                  restoration_days, beta_k)

    # Throughput accrued BY the evaluation time (pumping stops at t_op).
    pumping_days = min(t_eval, operation_days)
    swept_bulk = math.pi * (wellfield_width_m / 2.0) ** 2 * thickness_m
    PV = pore_volumes(Q_in_m3_day, pumping_days, phi_mobile, swept_bulk)
    BV = (Q_in_m3_day * pumping_days) / max(swept_bulk, 1e-6)
    W_eff = effective_source_width(wellfield_width_m, BV)

    # Dispersivity scale = how far the front has actually travelled (>= source).
    L_disp = max(Xc_eval, wellfield_width_m, 1.0)
    aL, aT = dispersivities(L_disp, regime)
    # E1: transverse anisotropy from the fracture-strike dispersion V (fractured);
    # None -> regime default (pre-E1 serve path + porous, unchanged). The FEATURE
    # alpha_T must carry V so the surrogate can learn the elongation it produces.
    if aniso_ratio is not None:
        aT = aL * float(aniso_ratio)
    DL, DT = aL * v, aT * v

    tau = vc * t_eval / max(wellfield_width_m, 1.0)   # front-lengths per source width

    return {
        "regime_is_fractured": 1 if fractured else 0,
        "domain_is_texas": 1 if domain_is_texas else 0,
        "K_m_day": K_m_day, "gradient_i": gradient_i,
        "phi_mobile": phi_mobile, "phi_total": n_total,
        "darcy_flux_q": q, "seepage_velocity_v": v,
        "Kd_L_kg": kd_L_kg, "retardation_Rd": Rd, "contaminant_velocity_vc": vc,
        "alpha_L": aL, "alpha_T": aT, "anisotropy_ratio": aL / max(aT, 1e-9),
        "D_L": DL, "D_T": DT,
        "peclet_L": peclet(L_disp, aL), "pore_volumes_PV": PV,
        "dimensionless_time_tau": tau, "dual_porosity_beta": beta,
        "Q_in_m3_day": Q_in_m3_day, "Q_out_m3_day": Q_out,
        "bleed_fraction": bleed_fraction, "Q_net_m3_day": Q_net,
        "containment_eta": eta, "operation_days": operation_days,
        "wellfield_width_m": wellfield_width_m,
        "source_conc_C0": source_conc_C0, "background_conc_Cb": background_conc_Cb,
        "downtime_fraction": f_down,
        "gradient_seasonal_amp": float(gradient_seasonal_amp),
        "restoration_years": restoration_days / 365.0,
        # QA F-2 (2026-07-13): the MODEL FEATURE is the source fraction REALIZED
        # at eval time (elapsed-sweep drawdown) -- continuous at rest -> 0+
        # (-> 1.0, matching the no-restoration rows) and it distinguishes
        # mid-sweep states. The raw Texas endpoint stays available to physics
        # callers as _residual_endpoint (feeding the realized value back into
        # the drawdown law would double-apply it).
        "residual_fraction": float(restoration_source_fraction(
            float(residual_fraction), t_eval, operation_days, restoration_days)),
        # carried for transport solver / labelling (not model features):
        "_L_ref_m": L_disp, "_thickness_m": thickness_m, "_regime": regime,
        "_source_width_m": W_eff, "_grain_density": grain_density,
        "_Xc_eval_m": Xc_eval, "_Xc_clean_m": Xc_clean, "_eta_eff": eta_eff,
        "_eval_time_days": t_eval, "_restoration_days": restoration_days,
        "_residual_endpoint": float(residual_fraction),
    }


if __name__ == "__main__":
    # Sanity: a fractured Jharkhand pin vs a Texas-like porous case, U species.
    frac = build_feature_row(
        regime="fractured", domain_is_texas=False,
        K_m_day=1.12, gradient_i=0.005, phi_mobile=0.008, n_total=0.03,
        grain_density=2750, kd_L_kg=1.0, beta=8.0,
        Q_in_m3_day=2000, bleed_fraction=0.02, operation_days=365 * 8,
        wellfield_width_m=300, thickness_m=37.5,
        source_conc_C0=15000, background_conc_Cb=2.0, eval_time_days=365 * 10)
    por = build_feature_row(
        regime="porous", domain_is_texas=True,
        K_m_day=3.21, gradient_i=0.005, phi_mobile=0.28, n_total=0.30,
        grain_density=2650, kd_L_kg=2.5, beta=0.0,
        Q_in_m3_day=2000, bleed_fraction=0.02, operation_days=365 * 8,
        wellfield_width_m=300, thickness_m=120,
        source_conc_C0=15000, background_conc_Cb=2.0, eval_time_days=365 * 10)
    df = pd.DataFrame([frac, por], index=["fractured(JH)", "porous(TX)"])
    cols = ["seepage_velocity_v", "retardation_Rd", "contaminant_velocity_vc",
            "anisotropy_ratio", "peclet_L", "pore_volumes_PV", "containment_eta",
            "dimensionless_time_tau"]
    print(df[cols].T.round(3).to_string())
    assert df.loc["fractured(JH)", "anisotropy_ratio"] > df.loc["porous(TX)", "anisotropy_ratio"]
    assert all(c in FEATURE_COLUMNS for c in cols)
    # time consistency: source width grows with elapsed pumping time, then freezes
    w2 = build_feature_row(regime="porous", domain_is_texas=False, K_m_day=2.0,
                           gradient_i=0.005, phi_mobile=0.2, n_total=0.3,
                           grain_density=2650, kd_L_kg=1.0, beta=0.0,
                           Q_in_m3_day=3000, bleed_fraction=0.02,
                           operation_days=365 * 8, wellfield_width_m=300,
                           thickness_m=60, source_conc_C0=1e4,
                           background_conc_Cb=2.0, eval_time_days=365 * 2)["_source_width_m"]
    w8 = build_feature_row(regime="porous", domain_is_texas=False, K_m_day=2.0,
                           gradient_i=0.005, phi_mobile=0.2, n_total=0.3,
                           grain_density=2650, kd_L_kg=1.0, beta=0.0,
                           Q_in_m3_day=3000, bleed_fraction=0.02,
                           operation_days=365 * 8, wellfield_width_m=300,
                           thickness_m=60, source_conc_C0=1e4,
                           background_conc_Cb=2.0, eval_time_days=365 * 12)["_source_width_m"]
    assert w2 < w8, "source width must accrue with pumping time"
    print("\nPhase-1 feature builder OK. n_features =", len(FEATURE_COLUMNS))
