"""
ml_pipeline.physics.transport  (PHASE 2a -- analytical engine)
============================================================
Vectorized analytical advection-dispersion (ADE) plume model. This is the
"ground truth" physics the surrogate is trained to imitate; it is fast enough
(milliseconds per field) to (a) generate thousands of synthetic training
samples and (b) recompute live in the Streamlit dashboard.

Core solution -- Domenico (1987) continuous-source, plan-view 2D:

    C(x,y) = C0 * A_long(x) * A_tran(x,y)
    A_long = 1/2 * erfc[ (x - Xc) / (2*sqrt(aL*Xc)) ]
    A_tran = 1/2 * [ erf((y+W/2)/(2*sqrt(aT*x))) - erf((y-W/2)/(2*sqrt(aT*x))) ]

  flow is along +x; W is the source (wellfield) width; Xc is the effective
  advective travel distance of the retarded contaminant front.

Physics layered on top of the textbook solution (all documented):
  * Retardation        -> contaminant velocity vc = v/Rd (front moves at vc).
  * Hydraulic control  -> during operation the cone of depression suppresses net
                          outward advection by the capture fraction eta; after
                          closure the regional gradient restores and the plume
                          drifts. Encoded in the two-phase travel distance Xc.
  * Dual porosity      -> fractured zones get extra apparent longitudinal
                          spreading from rate-limited matrix diffusion
                          (aL_eff = aL*(1 + k*beta)). [Goltz & Roberts 1986]
  * Anisotropy         -> aT/aL set by regime (fractured << porous) so fractured
                          plumes are long & narrow (channeled), porous ones round.

Frame: solved in flow-aligned coordinates. The dashboard rotates the field to
the local gradient/fracture-strike azimuth for display (rotation-invariant
metrics, so area/distance are unaffected).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy.special import erfc, erf

# Extra-dispersion coefficient for matrix-diffusion tailing in fractured rock.
# aL_eff = aL * (1 + DUAL_DISP_K * beta). Calibratable; documented approximation.
DUAL_DISP_K = 0.15

# Beyond this advective reach the gridded area/distance is censored (the plume
# has effectively swept the local domain). The compliance-point breach is still
# evaluated at the TRUE reach, so excursion logic stays correct. Fast fractured
# channels (high K, tiny porosity) can exceed this; that is flagged, not hidden.
MAX_GRID_REACH_M = 15000.0


@dataclass
class PlumeResult:
    C: np.ndarray            # concentration field (same units as C0)
    X: np.ndarray            # x meshgrid [m]
    Y: np.ndarray            # y meshgrid [m]
    Xc: float                # effective advective travel distance [m]
    cell_area_m2: float
    metrics: dict


def effective_travel_distance(vc_m_day: float, eta: float, t_days: float,
                              t_op_days: float) -> float:
    """Two-phase advective distance of the contaminant front [m].

    Operational phase [0, min(t,t_op)]: net velocity vc*(1-eta) (contained).
    Post-closure phase (t_op, t]:        net velocity vc        (drifts).
    """
    t_contained = min(t_days, t_op_days)
    t_drift = max(0.0, t_days - t_op_days)
    return vc_m_day * (1.0 - eta) * t_contained + vc_m_day * t_drift


def domenico_plume(X: np.ndarray, Y: np.ndarray, *, Xc: float, aL: float,
                   aT: float, C0: float, source_width: float) -> np.ndarray:
    """Evaluate the Domenico 2D field on meshgrids X, Y. Returns C >= 0."""
    Xc = max(Xc, 1e-3)
    aL = max(aL, 1e-3)
    aT = max(aT, 1e-4)
    # Longitudinal: error-function front centered at Xc, spread ~ sqrt(aL*Xc).
    long_spread = 2.0 * np.sqrt(aL * Xc)
    A_long = 0.5 * erfc((X - Xc) / long_spread)
    # Transverse: only defined for x>0; guard x<=0 with tiny epsilon.
    Xpos = np.where(X > 0.1, X, 0.1)
    tw = 2.0 * np.sqrt(aT * Xpos)
    A_tran = 0.5 * (erf((Y + source_width / 2.0) / tw) - erf((Y - source_width / 2.0) / tw))
    C = C0 * A_long * A_tran
    return np.clip(C, 0.0, C0)


def concentration_at(x: float, y: float, *, Xc: float, aL: float, aT: float,
                     C0: float, source_width: float) -> float:
    """Scalar Domenico evaluation at a single point -- used for fast Monte Carlo
    excursion probability at a compliance boundary (no full grid needed)."""
    xa = np.array([[x]], dtype=float)
    ya = np.array([[y]], dtype=float)
    return float(domenico_plume(xa, ya, Xc=Xc, aL=aL, aT=aT, C0=C0,
                                source_width=source_width)[0, 0])


def _auto_grid(Xc: float, aL: float, source_width: float, n: int = 220):
    """Build a meshgrid sized to comfortably contain the plume."""
    reach = Xc + 4.0 * np.sqrt(aL * max(Xc, 1.0)) + source_width
    reach = max(reach, source_width * 2.0, 50.0)
    x = np.linspace(-0.25 * reach, reach, n)
    y = np.linspace(-0.6 * reach, 0.6 * reach, n)
    X, Y = np.meshgrid(x, y)
    return X, Y


def plume_metrics(C: np.ndarray, X: np.ndarray, Y: np.ndarray, *,
                  threshold: float, background: float, cell_area_m2: float) -> dict:
    """Derive decision metrics from a concentration field.

    threshold   -- regulatory breach level (BIS) in the SAME units as C/C0.
    background  -- ambient concentration (added so absolute conc = plume + bg).
    """
    C_abs = C + background
    mask = C_abs >= threshold
    area_m2 = float(mask.sum()) * cell_area_m2
    if mask.any():
        r = np.sqrt(X[mask] ** 2 + Y[mask] ** 2)
        max_dist = float(r.max())
        max_down = float(X[mask].max())          # downgradient reach
        plume_halfwidth = float(np.abs(Y[mask]).max())
    else:
        max_dist = max_down = plume_halfwidth = 0.0
    return {
        "affected_area_ha": area_m2 / 1e4,
        "affected_area_m2": area_m2,
        "max_migration_distance_m": max_dist,
        "max_downgradient_m": max_down,
        "plume_halfwidth_m": plume_halfwidth,
        "peak_conc": float(C_abs.max()),
        "breaches_threshold": bool(C_abs.max() >= threshold),
        # mass proxy (sum of exceedance over area) -- for mass-balance checks
        "exceedance_mass_proxy": float(np.clip(C_abs - threshold, 0, None).sum() * cell_area_m2),
    }


def simulate_plume(feat: dict, *, species_C0: float, background: float,
                   threshold: float, t_days: float, operation_days: float,
                   grid_n: int = 220, compliance_x: float | None = None) -> PlumeResult:
    """High-level: from a Phase-1 feature row -> plume field + metrics.

    `feat` must contain the private carry-throughs from build_feature_row:
    contaminant_velocity_vc, containment_eta, alpha_L, alpha_T, _regime,
    dual_porosity_beta, wellfield_width_m.

    compliance_x: if given, also evaluate the (deterministic) breach at the
    downgradient compliance ring (x=compliance_x, y=0) -- this is the meaningful
    binary the Monte-Carlo excursion probability estimates.
    """
    vc = feat["contaminant_velocity_vc"]
    eta = feat["containment_eta"]
    aL = feat["alpha_L"]
    aT = feat["alpha_T"]
    beta = feat.get("dual_porosity_beta", 0.0)
    regime = feat.get("_regime", "porous")
    # effective (throughput-widened) contaminated source; falls back to raw width
    W = feat.get("_source_width_m", feat["wellfield_width_m"])

    # Fractured zones: matrix diffusion enhances apparent longitudinal spreading.
    if regime == "fractured":
        aL = aL * (1.0 + DUAL_DISP_K * beta)

    Xc = effective_travel_distance(vc, eta, t_days, operation_days)
    off_scale = Xc > MAX_GRID_REACH_M
    Xc_grid = min(Xc, MAX_GRID_REACH_M)        # keep grid resolution sane
    X, Y = _auto_grid(Xc_grid, aL, W, n=grid_n)
    C = domenico_plume(X, Y, Xc=Xc_grid, aL=aL, aT=aT, C0=species_C0, source_width=W)

    dx = X[0, 1] - X[0, 0]
    dy = Y[1, 0] - Y[0, 0]
    cell_area = float(abs(dx * dy))
    metrics = plume_metrics(C, X, Y, threshold=threshold, background=background,
                            cell_area_m2=cell_area)
    metrics["Xc_m"] = Xc
    metrics["off_scale"] = bool(off_scale)

    if compliance_x is not None:
        # evaluate at the TRUE reach Xc (cheap scalar) -> correct even off-scale
        c_comp = concentration_at(compliance_x, 0.0, Xc=Xc, aL=aL, aT=aT,
                                  C0=species_C0, source_width=W)
        metrics["compliance_conc"] = c_comp + background
        metrics["breaches_at_compliance"] = bool((c_comp + background) >= threshold)

    return PlumeResult(C=C, X=X, Y=Y, Xc=Xc, cell_area_m2=cell_area, metrics=metrics)


if __name__ == "__main__":
    from ml_pipeline.data_prep.feature_engineering import build_feature_row
    from ml_pipeline.config.parameters import EXCURSION_THRESHOLDS

    scenarios = {
        "Fractured shear (JH)": dict(regime="fractured", K_m_day=1.12, phi_mobile=0.008,
                                     n_total=0.03, grain_density=2750, beta=8.0,
                                     thickness_m=37.5),
        "Weathered/porous (JH)": dict(regime="porous", K_m_day=2.345, phi_mobile=0.08,
                                      n_total=0.30, grain_density=2650, beta=0.0,
                                      thickness_m=85),
    }
    for name, hg in scenarios.items():
        feat = build_feature_row(
            domain_is_texas=False, gradient_i=0.006, kd_L_kg=1.0,
            Q_in_m3_day=2500, bleed_fraction=0.02, operation_days=365 * 8,
            wellfield_width_m=300, source_conc_C0=15000, background_conc_Cb=2.0,
            **hg)
        res = simulate_plume(feat, species_C0=15000, background=2.0,
                             threshold=EXCURSION_THRESHOLDS["uranium_ppb"],
                             t_days=365 * 10, operation_days=365 * 8)
        m = res.metrics
        print(f"\n{name}")
        print(f"  vc={feat['contaminant_velocity_vc']:.4f} m/day  eta={feat['containment_eta']:.3f}"
              f"  aniso={feat['anisotropy_ratio']:.0f}  Xc={m['Xc_m']:.0f} m")
        print(f"  U plume: area={m['affected_area_ha']:.2f} ha  max_dist={m['max_migration_distance_m']:.0f} m"
              f"  half-width={m['plume_halfwidth_m']:.0f} m  peak={m['peak_conc']:.0f} ppb"
              f"  breach={m['breaches_threshold']}")
