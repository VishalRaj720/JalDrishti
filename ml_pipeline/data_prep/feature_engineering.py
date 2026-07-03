"""
ml_pipeline.data_prep.feature_engineering  (PHASE 1)
==================================================
Physics-based domain adaptation. Texas (uniform porous sandstone) and Jharkhand
(12 lithologies, fractured or weathered) cannot share *absolute* coordinates or
velocities. They CAN share dimensionless transport groups. This module turns any
(hydrogeology, operating point, species) triple into that shared, scale-
independent feature vector.

The hydrogeological chain (each link documented):

  Darcy flux          q   = K * i                         [m/day]
  Seepage velocity    v   = K * i / phi_mobile            [m/day]   <-- advection
  Retardation         Rd  = 1 + (rho_b / n_total) * Kd    [-]       <-- chemistry
                            (fractured: Rd~1, apparent R via dual-porosity beta)
  Contaminant vel.    vc  = v / Rd                        [m/day]
  Dispersivity        aL  = 0.83*(log10 L)^2.414 ; aT = r*aL        [Xu&Eckstein]
  Dispersion          DL  = aL*v ; DT = aT*v              [m2/day]
  Peclet number       Pe  = L / aL  (= v*L / DL)          [-]       <-- adv/disp balance
  Pore volumes        PV  = Q_in * t / (n_mobile * V_swept)         [-]  throughput
  Containment         eta = Q_net / (q*b*W + Q_net)       [-]       capture fraction
  Dimensionless time  tau = vc * t / L_ref                [-]

Anisotropy (aL/aT) is high for fractured (directional channeling along strike)
and low for porous (rounder plume) -- this is exactly the feature the model uses
to switch between the two transport styles the brief asks for.
"""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P

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
]


# --------------------------------------------------------------------------- #
# Elementary physics (each is independently unit-tested in __main__)
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
    """Species retardation Rd [-].

    Porous: classic linear-equilibrium  Rd = 1 + (rho_b/n_total)*Kd, with
            rho_b = (1 - n_total)*rho_solid  and Kd converted L/kg -> m3/kg.
    Fractured: bulk-rho retardation is physically wrong (solute only contacts
            fracture walls, not the whole rock mass). Under alkaline ISR uranium
            is mobile, so fracture-flow Rd ~ 1; the *apparent* retardation/tailing
            is supplied by matrix diffusion via the dual-porosity capacity ratio
            beta -> R_apparent = 1*(1 + beta).   [Goltz & Roberts 1986]
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
    """Hydraulic-capture fraction eta in [0,1).

    Regional groundwater flux intercepted by the wellfield footprint:
        Q_regional = q * b * W           [m3/day]
    Net extraction Q_net = Q_out - Q_in pulls water inward. Capture fraction:
        eta = Q_net / (Q_regional + Q_net)
    eta -> 1 when net extraction dominates regional throughflow (plume contained,
    no net outward migration), eta -> 0 with no bleed. A simple, mass-balance-
    style estimate of cone-of-depression control (cf. capture-zone theory).
    """
    Q_regional = max(q_m_day * thickness_m * width_m, 1e-9)
    Q_net = max(Q_net_m3_day, 0.0)
    return Q_net / (Q_regional + Q_net)


def pore_volumes(Q_in_m3_day: float, t_days: float, phi_mobile: float,
                 swept_volume_m3: float) -> float:
    """Dimensionless throughput PV = injected volume / mobile pore volume swept."""
    pv_water = max(phi_mobile * swept_volume_m3, 1e-6)
    return (Q_in_m3_day * t_days) / pv_water


def peclet(L_m: float, alpha_L: float) -> float:
    """Grid Peclet number Pe = L/alpha_L (advection vs dispersion dominance)."""
    return L_m / max(alpha_L, 1e-6)


def effective_source_width(wellfield_width_m: float, pore_volumes_PV: float) -> float:
    """Lixiviant-contacted source width [m], widening (capped) with throughput.
    W_eff = W * (1 + gain * tanh(PV / PV_ref)).  Encodes "more injection/time ->
    larger contaminated source" without letting the source diverge."""
    return wellfield_width_m * (1.0 + P.SOURCE_PV_GAIN * math.tanh(pore_volumes_PV / P.SOURCE_PV_REF))


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
                      L_ref_m: float | None = None) -> dict:
    """Assemble one fully-featured, scale-independent training/inference row."""
    q = darcy_flux(K_m_day, gradient_i)
    v = seepage_velocity(K_m_day, gradient_i, phi_mobile)
    Rd = retardation_factor(kd_L_kg, n_total, grain_density, regime, beta)
    vc = v / Rd

    # Characteristic transport length: how far the (retarded) front would advect
    # over the operating period -- the natural scale for Pe / tau (>= wellfield).
    L_ref = L_ref_m if L_ref_m else max(vc * operation_days, wellfield_width_m, 1.0)
    aL, aT = dispersivities(L_ref, regime)
    DL, DT = aL * v, aT * v

    Q_out = Q_in_m3_day * (1.0 + bleed_fraction)
    Q_net = Q_out - Q_in_m3_day

    # Swept volume ~ wellfield footprint x mobile-zone thickness (cylinder approx)
    swept_volume = math.pi * (wellfield_width_m ** 2) * thickness_m
    PV = pore_volumes(Q_in_m3_day, operation_days, phi_mobile, swept_volume)
    eta = containment_efficiency(q, thickness_m, wellfield_width_m, Q_net)
    tau = vc * operation_days / max(L_ref, 1.0)
    # Throughput-coupled contaminated source width (uses RAW wellfield width for
    # PV -> no circularity). The compliance ring stays at the raw permitted edge.
    W_eff = effective_source_width(wellfield_width_m, PV)

    return {
        "regime_is_fractured": 1 if regime == "fractured" else 0,
        "domain_is_texas": 1 if domain_is_texas else 0,
        "K_m_day": K_m_day, "gradient_i": gradient_i,
        "phi_mobile": phi_mobile, "phi_total": n_total,
        "darcy_flux_q": q, "seepage_velocity_v": v,
        "Kd_L_kg": kd_L_kg, "retardation_Rd": Rd, "contaminant_velocity_vc": vc,
        "alpha_L": aL, "alpha_T": aT, "anisotropy_ratio": aL / max(aT, 1e-9),
        "D_L": DL, "D_T": DT,
        "peclet_L": peclet(L_ref, aL), "pore_volumes_PV": PV,
        "dimensionless_time_tau": tau, "dual_porosity_beta": beta,
        "Q_in_m3_day": Q_in_m3_day, "Q_out_m3_day": Q_out,
        "bleed_fraction": bleed_fraction, "Q_net_m3_day": Q_net,
        "containment_eta": eta, "operation_days": operation_days,
        "wellfield_width_m": wellfield_width_m,
        "source_conc_C0": source_conc_C0, "background_conc_Cb": background_conc_Cb,
        # carried for transport solver / labelling (not model features):
        "_L_ref_m": L_ref, "_thickness_m": thickness_m, "_regime": regime,
        "_source_width_m": W_eff,
    }


if __name__ == "__main__":
    # Sanity: a fractured Jharkhand pin vs a Texas-like porous case, U species.
    frac = build_feature_row(
        regime="fractured", domain_is_texas=False,
        K_m_day=1.12, gradient_i=0.005, phi_mobile=0.008, n_total=0.03,
        grain_density=2750, kd_L_kg=1.0, beta=8.0,
        Q_in_m3_day=2000, bleed_fraction=0.02, operation_days=365 * 8,
        wellfield_width_m=300, thickness_m=37.5,
        source_conc_C0=15000, background_conc_Cb=2.0)
    por = build_feature_row(
        regime="porous", domain_is_texas=True,
        K_m_day=3.21, gradient_i=0.005, phi_mobile=0.28, n_total=0.30,
        grain_density=2650, kd_L_kg=2.5, beta=0.0,
        Q_in_m3_day=2000, bleed_fraction=0.02, operation_days=365 * 8,
        wellfield_width_m=300, thickness_m=120,
        source_conc_C0=15000, background_conc_Cb=2.0)
    df = pd.DataFrame([frac, por], index=["fractured(JH)", "porous(TX)"])
    cols = ["seepage_velocity_v", "retardation_Rd", "contaminant_velocity_vc",
            "anisotropy_ratio", "peclet_L", "pore_volumes_PV", "containment_eta",
            "dimensionless_time_tau"]
    print(df[cols].T.round(3).to_string())
    assert df.loc["fractured(JH)", "anisotropy_ratio"] > df.loc["porous(TX)", "anisotropy_ratio"]
    assert all(c in FEATURE_COLUMNS for c in cols)
    print("\nPhase-1 feature builder OK. n_features =", len(FEATURE_COLUMNS))
