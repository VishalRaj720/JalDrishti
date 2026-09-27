"""
ml_pipeline.physics.channel  --  the preferential-pathway (fast-track channel) branch
====================================================================================
2026-09-27 (P.CHANNEL; docs/GEMINI_REVIEW_ASSESSMENT.md Issue 2; LIMITATIONS 1l).

The continuum answer moves water at v = K*i/phi_mobile, with phi_mobile the
aquifer polygon's specific yield. For the SAME served K, the cubic law says the
water that carries that K moves in a few discrete fractures, 150-3,900x faster.
This module computes what those fractures would carry, from the belt's own
borehole logs:

  1. conductive fractures = the logged water-bearing zones of a belt borehole
     (depth interval + yield); the served T = K * b is split over them in
     proportion to their yields -- T_i = T * y_i / sum(y);
  2. hydraulic aperture 2b_h = (12 mu T_i / rho g)^(1/3)       [cubic law];
     transport aperture 2b_t = c * 2b_h, c sampled (Tsang 1992);
  3. channel water velocity v_i = T_i * i / 2b_t, through the SAME three-phase
     kinematics (bleed containment, restoration hold, drift) as the continuum;
  4. matrix diffusion from each channel wall by the Tang, Frind & Sudicky (1981)
     kernel the engine already carries (`tang_attenuation`, `matrix_sigma`),
     restoration by superposing the clean-water step, uranium redox trapping
     over the channel's own mobile residence time;
  5. the MONITORING-WELL reading = the flux-weighted mix sum(T_i/T * C_i): what a
     ring well open across the ore zone samples. The peak inside one fracture is
     not something any well measures, and alerting on it would over-claim.

It is an UPPER-BOUND pathway: each logged zone is treated as a planar fracture
that stays connected down-gradient; no persistence data exist for the SSZ.
Porous pins get no channel answer (there are no fractures to channel through).

Analytical and closed-form, served beside the continuum; nothing here touches a
trained feature or label.
"""
from __future__ import annotations

import functools
import math
from pathlib import Path

import numpy as np

from ml_pipeline.config import parameters as P
from ml_pipeline.physics.transport import (
    MAX_GRID_REACH_M, front_position, matrix_sigma, source_strength_fraction,
    tang_attenuation,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "Datasets"
_N_SCAN = 4096


# --------------------------------------------------------------------------- #
# The belt's logged fracture sets
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def fracture_sets() -> tuple[dict, ...]:
    """One entry per belt borehole with at least one yielded fractured zone:
    {well_id, name, formation, zones: ((top_m, bottom_m, share), ...)}.
    Shares are the zone's fraction of the well's total logged yield."""
    import pandas as pd
    cfg = P.CHANNEL
    zones = pd.read_csv(DATA_DIR / cfg["zones_csv"])
    wells = pd.read_csv(DATA_DIR / cfg["wells_csv"]).set_index("well_id")
    zones = zones[zones["kind"].isin(cfg["zone_kinds"])
                  & zones["yield_lps"].notna() & (zones["yield_lps"] > 0)]
    out = []
    for wid, g in zones.groupby("well_id", sort=True):
        formation = (str(wells.at[wid, "formation"])
                     if wid in wells.index and wells.at[wid, "formation"] == wells.at[wid, "formation"]
                     else None)
        if formation in cfg["exclude_formations"]:
            continue
        y = g["yield_lps"].to_numpy(float)
        shares = y / y.sum()
        out.append({
            "well_id": wid,
            "name": (str(wells.at[wid, "name"]) if wid in wells.index else wid),
            "formation": formation,
            "zones": tuple((float(t), float(b), float(s)) for t, b, s in
                           zip(g["top_m"], g["bottom_m"], shares)),
        })
    if not out:
        raise RuntimeError("no yielded fractured zones in the borehole table")
    return tuple(out)


def central_set() -> dict:
    """The served fracture set: the well whose pumping test sets the served
    shear-zone T (P.CHANNEL['central_well'])."""
    for s in fracture_sets():
        if s["well_id"] == P.CHANNEL["central_well"]:
            return s
    return fracture_sets()[0]


def hydraulic_aperture_m(T_m2_day: float) -> float:
    """Cubic-law hydraulic aperture 2b [m] of a single fracture of transmissivity T."""
    c = P.CHANNEL
    T_s = max(float(T_m2_day), 0.0) / 86400.0
    return float((12.0 * c["water_viscosity_pa_s"] * T_s
                  / (c["water_density_kg_m3"] * c["gravity_m_s2"])) ** (1.0 / 3.0))


def cubic_law_consistency(K_m_day: float, phi_mobile: float,
                          full_aperture_m: float | None = None) -> dict:
    """What the cubic law says about the continuum's own K and aperture: the
    fracture spacing that K implies, and the flowing porosity that goes with it,
    against the phi_mobile the continuum runs on. A diagnostic -- it moves no
    number -- surfaced because the gap is the reason the channel branch exists."""
    c = P.CHANNEL
    ap = float(full_aperture_m if full_aperture_m is not None
               else P.FRACTURE["full_aperture_m"][1])
    K_s = max(float(K_m_day), 1e-12) / 86400.0
    k_frac = c["water_density_kg_m3"] * c["gravity_m_s2"] * ap ** 2 / (
        12.0 * c["water_viscosity_pa_s"])                     # fracture K [m/s]
    spacing = k_frac * ap / K_s
    phi_flow = ap / spacing
    ratio = float(phi_mobile) / phi_flow if phi_flow > 0 else float("inf")
    return {
        "full_aperture_um": round(ap * 1e6, 1),
        "implied_spacing_m": round(spacing, 2),
        "implied_flowing_porosity": float(f"{phi_flow:.3g}"),
        "continuum_phi_mobile": round(float(phi_mobile), 5),
        "continuum_over_cubic_law": round(ratio, 1),
        "inconsistent": bool(ratio > 10.0),
        "note": ("The continuum's mobile porosity is the aquifer's specific yield. "
                 "For the served K and a fracture of this aperture, the cubic law "
                 "allows a far smaller flowing porosity, i.e. faster water in fewer "
                 "fractures -- which is what the preferential-pathway answer "
                 "computes."),
    }


# --------------------------------------------------------------------------- #
# One deterministic evaluation
# --------------------------------------------------------------------------- #
def _channel_conc(x: np.ndarray, *, C0: float, C_res: float, f_src: float,
                  v: float, eta: float, sigma: float, t_days: float,
                  op_days: float, rest_days: float, atten_k_yr: float) -> np.ndarray:
    """Plume-attributable concentration along one channel (no background)."""
    Xw = front_position(v, eta, t_days, op_days, rest_days, 0.0)
    C = C0 * tang_attenuation(x, t_days, Xw, sigma)
    if f_src < 1.0 and t_days > op_days:
        # clean water enters the source zone when the sweep begins (end of
        # operations) and drifts from there -- the continuum's own convention
        # (params_from_features); a linear kernel, so superposition is exact
        tau = t_days - op_days
        Xw_c = front_position(v, 1.0, t_days, op_days, 0.0, 0.0)
        C = C - (C0 - C_res) * tang_attenuation(x, tau, Xw_c, sigma)
    if atten_k_yr > 0.0:
        # redox trapping over the channel's own MOBILE residence time (the
        # engine's rule: ATTENUATION_USES_SORBED_RESIDENCE = False), plus the
        # years the plume was held still by the restoration sweep
        decay = np.exp(-(atten_k_yr / 365.0) * np.clip(x, 0.0, None) / max(v, 1e-9))
        if rest_days > 0.0:
            hold = min(max(t_days - op_days, 0.0), rest_days)
            decay = decay * math.exp(-(atten_k_yr / 365.0) * hold)
        C = C * decay
    return np.clip(C, 0.0, C0)


def evaluate(*, T_m2_day: float, gradient_i: float, eta: float, n_total: float,
             grain_density: float, kd_L_kg: float, zones: tuple, c_factor: float,
             C0: float, background: float, threshold: float, ring_x: float,
             t_days: float, op_days: float, rest_days: float,
             residual_ref: float, atten_k_yr: float) -> dict:
    """The channel answer for one parameter set.

    Returns the flux-weighted ring reading (plume increment and absolute), the
    reach (farthest distance at which the flux-weighted reading exceeds the
    incremental threshold) and the per-channel velocity/aperture table."""
    thr_inc = max(threshold - background, P.INCREMENTAL_FLOOR * threshold)
    f_src = source_strength_fraction(float(residual_ref), t_days, op_days, rest_days)
    C_res = (max(f_src * C0, background) if f_src < 1.0 else C0)
    channels, fronts = [], []
    for (top, bottom, share) in zones:
        T_i = T_m2_day * share
        ap_h = hydraulic_aperture_m(T_i)
        ap_t = c_factor * ap_h
        v = T_i * gradient_i / max(ap_t, 1e-12)                # m/day
        sigma = matrix_sigma(n_total, grain_density, kd_L_kg,
                             half_aperture_m=ap_t / 2.0)
        channels.append(dict(share=share, v=v, sigma=sigma, top=top,
                             bottom=bottom, ap_h=ap_h, ap_t=ap_t))
        fronts.append(front_position(v, eta, t_days, op_days, rest_days, 0.0))

    def reading(x):
        C = np.zeros_like(np.asarray(x, dtype=float))
        for ch in channels:
            C = C + ch["share"] * _channel_conc(
                x, C0=C0, C_res=C_res, f_src=f_src, v=ch["v"], eta=eta,
                sigma=ch["sigma"], t_days=t_days, op_days=op_days,
                rest_days=rest_days, atten_k_yr=atten_k_yr)
        return C

    ring_inc = float(reading(np.array([float(ring_x)]))[0]) if t_days > 0 else 0.0
    reach = 0.0
    x_max = min(max(fronts + [1.0]), MAX_GRID_REACH_M)
    if t_days > 0 and C0 > 0 and x_max > 0.1:
        xs = np.geomspace(0.1, x_max, _N_SCAN)
        hit = np.nonzero(reading(xs) >= thr_inc)[0]
        reach = float(xs[hit[-1]]) if hit.size else 0.0
    return {
        "ring_increment": ring_inc,
        "ring_conc": ring_inc + background,
        "reach_m": reach,
        "breach_at_ring": bool(ring_inc >= thr_inc),
        "off_scale": bool(reach >= MAX_GRID_REACH_M * 0.999),
        "incremental_threshold": thr_inc,
        "channels": channels,
    }


# --------------------------------------------------------------------------- #
# The served answer: central value + Monte-Carlo band
# --------------------------------------------------------------------------- #
def channel_answer(inputs: dict, feat: dict, *, threshold: float, ring_x: float,
                   kd_range: tuple | None = None, n_mc: int = 48,
                   seed: int = 0) -> dict:
    """Preferential-pathway answer for a resolved run (`resolve_inputs` inputs,
    `features_from_inputs` feature row). Fractured pins only."""
    cfg = P.CHANNEL
    base = {"hypothetical_upper_bound": True, "label": cfg["label"],
            "citation": cfg["citation"]}
    if not cfg.get("enabled", True):
        return {**base, "applies": False, "reason": "disabled in config"}
    if inputs["regime"] != "fractured":
        return {**base, "applies": False,
                "reason": ("porous (weathered / sedimentary) rock: flow is not "
                           "channelled through discrete fractures here")}

    from ml_pipeline.synthetic.generate import (MC_LNK_SIGMA, MC_K_CLIP, mc_draws,
                                                _kd_sample)
    from ml_pipeline.data_prep.feature_engineering import containment_efficiency

    species = inputs["species"]
    Cb = float(inputs["background_conc_Cb"])
    C0 = float(inputs["source_conc_C0"])
    op_days = float(inputs["operation_years"]) * 365.0
    t_days = float(inputs["time_years"]) * 365.0
    rest_days = float(inputs.get("restoration_years", 0.0) or 0.0) * 365.0
    residual_ref = float(feat.get("_residual_endpoint", feat["residual_fraction"]))
    b = float(inputs["thickness_m"])
    k_yr = float(feat.get("u_attenuation_k", 0.0))
    common = dict(n_total=float(inputs["n_total"]),
                  grain_density=float(inputs["grain_density"]),
                  C0=C0, background=Cb, threshold=threshold, ring_x=ring_x,
                  t_days=t_days, op_days=op_days, rest_days=rest_days,
                  residual_ref=residual_ref)

    cset = central_set()
    central = evaluate(T_m2_day=float(inputs["K_m_day"]) * b,
                       gradient_i=float(inputs["gradient_i"]),
                       eta=float(feat.get("_eta_eff", feat["containment_eta"])),
                       kd_L_kg=float(inputs["kd_L_kg"]), zones=cset["zones"],
                       c_factor=cfg["transport_aperture_factor_central"],
                       atten_k_yr=k_yr, **common)

    # Monte Carlo: the continuum's own K / gradient / bleed / Kd draws (same
    # common-random-number matrix), plus the two channel unknowns -- WHICH
    # belt borehole's fracture set, and the transport-aperture factor c.
    draws = mc_draws(n_mc, seed)
    rng = np.random.default_rng(seed + 9127)
    sets = fracture_sets()
    set_idx = rng.integers(len(sets), size=n_mc)
    c_lo, c_hi = cfg["transport_aperture_factor_range"]
    c_draw = c_lo * (c_hi / c_lo) ** rng.uniform(size=n_mc)
    lo, mid, hi = kd_range if kd_range is not None else P.kd_range_for(
        species, "fractured")
    amp = float(inputs.get("gradient_seasonal_amp", 0.0) or 0.0)
    g_lo, g_hi = max(0.3, 0.7 - amp), 1.3 + amp
    qm_lo, qm_hi = P.IRREGULARITY["qnet_drift_mult"]
    Q_net0 = float(inputs["Q_in_m3_day"]) * float(inputs["bleed_fraction"])
    down = float(inputs.get("downtime_fraction", 0.0) or 0.0)
    reach, ring, breach = [], [], 0
    for i in range(n_mc):
        K = float(inputs["K_m_day"]) * float(np.clip(
            math.exp(MC_LNK_SIGMA * draws["z_K"][i]), *MC_K_CLIP))
        grad = float(inputs["gradient_i"]) * (g_lo + (g_hi - g_lo) * float(draws["u_grad"][i]))
        kd = _kd_sample(float(draws["u_kd"][i]), lo, mid, hi)
        Q_net = Q_net0 * (qm_lo + (qm_hi - qm_lo) * float(draws["u_qnet"][i]))
        eta = containment_efficiency(K * grad, b, float(inputs["wellfield_width_m"]),
                                     Q_net) * (1.0 - down)
        k_i = 0.0
        if k_yr > 0.0:
            m_lo, m_hi = P.U_ATTENUATION_MC_MULT
            k_i = k_yr * m_lo * (m_hi / m_lo) ** float(draws["u_att"][i])
        r = evaluate(T_m2_day=K * b, gradient_i=grad, eta=eta, kd_L_kg=kd,
                     zones=sets[int(set_idx[i])]["zones"], c_factor=float(c_draw[i]),
                     atten_k_yr=k_i, **common)
        reach.append(r["reach_m"])
        ring.append(r["ring_conc"])
        breach += int(r["breach_at_ring"])
    q = lambda a: [float(v) for v in np.quantile(a, (0.10, 0.50, 0.90))]  # noqa: E731
    rq, cq = q(reach), q(ring)

    top = max(central["channels"], key=lambda c: c["share"])
    return {
        **base,
        "applies": True,
        "reach_m": round(central["reach_m"], 1),
        "ring_conc": round(central["ring_conc"], 3),
        "breach_at_ring": central["breach_at_ring"],
        "off_scale": central["off_scale"],
        "reach_band_m": {"p10": round(rq[0], 1), "p50": round(rq[1], 1),
                         "p90": round(rq[2], 1)},
        "ring_conc_band": {"p10": round(cq[0], 3), "p50": round(cq[1], 3),
                           "p90": round(cq[2], 3)},
        "excursion_probability": round(breach / max(n_mc, 1), 3),
        "incremental_threshold": round(central["incremental_threshold"], 4),
        "fracture_set": {
            "well": cset["name"], "well_id": cset["well_id"],
            "formation": cset["formation"],
            "zones": [{"depth_m": [c["top"], c["bottom"]],
                       "flow_share": round(c["share"], 3),
                       "hydraulic_aperture_um": round(c["ap_h"] * 1e6, 1),
                       "velocity_m_day": round(c["v"], 3)}
                      for c in central["channels"]],
            "dominant_share": round(top["share"], 3),
            "n_sets_sampled": len(sets),
            "transport_aperture_factor": cfg["transport_aperture_factor_central"],
            "transport_aperture_factor_range": list(cfg["transport_aperture_factor_range"]),
        },
        "monitoring_well_reading": ("flux-weighted mix over the logged zones -- what "
                                    "a ring well open across the ore zone samples"),
    }


def alerting_metrics(continuum: dict, channel: dict | None) -> dict:
    """max(continuum, channel) -- the owner's rule for what alerts read
    (P.CHANNEL['drives_alerts']). Reach, ring concentration and excursion
    probability each take the larger of the two answers; `basis` names which
    answer set each number, so an alert can say why it fired."""
    out = {"migration_m": float(continuum["migration_m"]),
           "compliance_conc": float(continuum["compliance_conc"]),
           "excursion_probability": float(continuum["excursion_probability"]),
           "basis": {"migration_m": "continuum", "compliance_conc": "continuum",
                     "excursion_probability": "continuum"},
           "rule": "continuum only"}
    if not (P.CHANNEL.get("drives_alerts") and channel and channel.get("applies")):
        return out
    out["rule"] = "max(continuum, channel)"
    for key, ch_val in (("migration_m", channel["reach_m"]),
                        ("compliance_conc", channel["ring_conc"]),
                        ("excursion_probability", channel["excursion_probability"])):
        if float(ch_val) > out[key]:
            out[key] = float(ch_val)
            out["basis"][key] = "channel"
    return out


def central_ring_reading(inputs: dict, feat: dict, ring_x: float) -> float | None:
    """Absolute monitoring-well reading at the ring from the CENTRAL channel set
    (no Monte Carlo) -- what the NUREG indicator panel compares with its control
    limits. None for porous pins or when the branch is off."""
    if not P.CHANNEL.get("enabled", True) or inputs.get("regime") != "fractured":
        return None
    Cb = float(inputs["background_conc_Cb"])
    r = evaluate(
        T_m2_day=float(inputs["K_m_day"]) * float(inputs["thickness_m"]),
        gradient_i=float(inputs["gradient_i"]),
        eta=float(feat.get("_eta_eff", feat["containment_eta"])),
        n_total=float(inputs["n_total"]), grain_density=float(inputs["grain_density"]),
        kd_L_kg=float(inputs["kd_L_kg"]), zones=central_set()["zones"],
        c_factor=P.CHANNEL["transport_aperture_factor_central"],
        C0=float(inputs["source_conc_C0"]), background=Cb,
        threshold=float("inf"), ring_x=float(ring_x),
        t_days=float(inputs["time_years"]) * 365.0,
        op_days=float(inputs["operation_years"]) * 365.0,
        rest_days=float(inputs.get("restoration_years", 0.0) or 0.0) * 365.0,
        residual_ref=float(feat.get("_residual_endpoint", feat["residual_fraction"])),
        atten_k_yr=float(feat.get("u_attenuation_k", 0.0)))
    return float(r["ring_conc"])
