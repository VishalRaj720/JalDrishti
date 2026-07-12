"""
ml_pipeline.synthetic.generate  (PHASE 2b v2 -- statewide synthetic loop)
=======================================================================
Generate a physics-labelled training set by sweeping the operational and
hydrogeological envelope across BOTH Jharkhand transport regimes, anchored to
the 23 real aquifer polygons and the 397 real water-quality baselines.

v2 (2026-07 remediation plan, Phase 2):
  * DECOUPLED CONTAINMENT: net extraction Q_net is sampled independently of
    Q_in (clipped to <= 10% of Q_in); bleed_fraction is the derived diagnostic.
    This lets the surrogate separate "more throughput" from "more capture" --
    at fixed bleed FRACTION the two are confounded and the Q_in law inverts.
  * JITTERED PINS: each scenario gets a uniform random point INSIDE its aquifer
    polygon (not the deterministic representative point), with the baseline
    chemistry of the well nearest to THAT point; `polygon_id` is recorded so
    Phase 3 can run leave-aquifer-out stress CV.
  * OPERATIONAL IRREGULARITIES: pump-downtime episodes degrade effective
    containment (eta_eff = eta*(1-f)); seasonal gradient amplitude and bleed
    drift widen the parameter-uncertainty Monte Carlo.
  * RESTORATION: ~half the scenarios include a post-mining clean-up sweep;
    the residual source fraction comes from the real Texas post-restoration
    sheets (x noise).
  * DISTRIBUTIONAL LABELS: every (scenario, time, species) row carries MC
    P10/P50/P90 labels for area / migration / compliance concentration, from a
    COMMON-RANDOM-NUMBERS draw matrix shared by the whole run. The bands the
    surrogate learns therefore mean PARAMETER UNCERTAINTY, not emulator error.
    `excursion_probability` is the breach fraction of the SAME draws (the old
    separate breach classifier is retired -- one coherent uncertainty model).

Geometry/scoring conventions (see physics.transport): source plane at the
downgradient wellfield edge; compliance ring at COMPLIANCE_BUFFER_M beyond it;
breach scored on the MINING-ATTRIBUTABLE (incremental) concentration.

CLI:
  python -m ml_pipeline.synthetic.generate --scenarios 900 --mc 48
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.feature_engineering import (
    build_feature_row, FEATURE_COLUMNS,
    seepage_velocity, retardation_factor, dispersivities, containment_efficiency,
    effective_source_width,
)
from ml_pipeline.data_prep.jharkhand_loader import (
    load_jharkhand_aquifers, load_jharkhand_water_quality,
)
from ml_pipeline.data_prep.flow_field import flow_at
from ml_pipeline.data_prep.strike_field import strike_at, anisotropy_from_variance
from ml_pipeline.data_prep.texas_loader import (
    texas_source_signature, texas_restoration_residual,
)
from ml_pipeline.physics.transport import (
    simulate_plume, front_position, matrix_sigma, TransportParams,
    concentration_point, mc_field_metrics,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
DEFAULT_TIMES_YEARS = (2.0, 5.0, 8.0, 12.0, 20.0)
BAND_TARGETS = ("affected_area_ha", "max_migration_distance_m", "compliance_conc")

# Within-scenario local heterogeneity of K (log-normal multiplier, clipped) --
# the dominant uncertainty in crystalline rock. sigma_lnK = 0.45 (~x1.6 at 1s).
MC_LNK_SIGMA = 0.45
MC_K_CLIP = (1.0 / 3.0, 3.0)

# E1 v3 field-informed sampling: fraction of scenarios whose gradient / seasonal
# amplitude / fracture-dispersion V are drawn from the REAL field at the jittered
# pin (the rest uniform-envelope for support). The plain uniform sampler sat 2-3x
# steeper than the field-median gradient -> coverage was on an unseen distribution.
FIELD_MIX_FRAC = 0.60
V_SAMPLE_RANGE = (0.35, 0.80)    # observed field circular-variance span


# --------------------------------------------------------------------------- #
# Scenario sampling -- anchored to real Jharkhand polygons
# --------------------------------------------------------------------------- #
def _jittered_point(geom, rng: np.random.Generator, max_tries: int = 200):
    """Uniform random lon/lat INSIDE the polygon (rejection sampling); falls
    back to representative_point if the polygon is pathologically thin."""
    from shapely.geometry import Point
    minx, miny, maxx, maxy = geom.bounds
    for _ in range(max_tries):
        p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
        if geom.contains(p):
            return float(p.x), float(p.y)
    p = geom.representative_point()
    return float(p.x), float(p.y)


def sample_scenario(rng: np.random.Generator, aquifers, wq, source_sig,
                    rest_residual: dict, field_mix: float = FIELD_MIX_FRAC) -> dict:
    """Draw one physically-consistent scenario from a real aquifer polygon."""
    aq_idx = int(rng.integers(len(aquifers)))
    arow = aquifers.iloc[aq_idx]
    regime = arow["regime"]

    # K within the polygon's own [min,max] (log-uniform), guarded
    k_lo = max(arow["K_min_m_day"], 0.01) if not np.isnan(arow["K_min_m_day"]) else arow["K_m_day"] * 0.3
    k_hi = max(arow["K_max_m_day"], k_lo * 1.1) if not np.isnan(arow["K_max_m_day"]) else arow["K_m_day"] * 3.0
    K = float(np.exp(rng.uniform(math.log(max(k_lo, 0.01)), math.log(max(k_hi, 0.02)))))

    phi_mobile = float(arow["eff_porosity"])
    litho = arow["lithology"]
    n_total = P.TOTAL_POROSITY.get(litho, P.DEFAULT_TOTAL_POROSITY)
    grain_density = float(arow["grain_density"])
    thickness = float(arow["thickness_m"])

    lon, lat = _jittered_point(arow.geometry, rng)
    polygon_id = arow.get("objectid")
    polygon_id = int(polygon_id) if polygon_id == polygon_id else aq_idx

    # E1 v3: sample gradient / seasonal amp / fracture-dispersion V from the REAL
    # field at this pin FIELD_MIX_FRAC of the time, uniform-envelope otherwise.
    fl, sk = flow_at(lon, lat), strike_at(lon, lat)

    def _mix(field_val, lo, hi):
        if field_val is not None and rng.uniform() < field_mix:
            return float(np.clip(field_val, lo, hi))
        return float(rng.uniform(lo, hi))

    # Operational envelope -- Q_in and Q_net sampled INDEPENDENTLY (decoupled)
    OR = P.OPERATIONAL_RANGES
    Q_in = float(rng.uniform(*OR["injection_rate_m3_day"]))
    Q_net = float(rng.uniform(*OR["net_extraction_m3_day"]))
    Q_net = min(Q_net, 0.10 * Q_in)              # keep bleed physical (<=10%)
    bleed = Q_net / Q_in
    op_years = float(rng.uniform(*OR["operation_years"]))
    gradient = _mix(fl["gradient_i"], *OR["hydraulic_gradient"])
    width = float(rng.uniform(*OR["wellfield_width_m"]))

    # operational irregularities
    IR = P.IRREGULARITY
    lam = rng.uniform(*IR["downtime_episodes_per_year"])
    dur = rng.uniform(*IR["downtime_days_per_episode"])
    downtime = float(min(lam * dur / 365.0, IR["downtime_fraction_max"]))
    seasonal_amp = _mix(fl["seasonal_amp_effective"], *IR["gradient_seasonal_amp"])
    # orientation dispersion V -> transverse anisotropy (fractured only)
    V = _mix(sk["circular_variance"], *V_SAMPLE_RANGE)
    aniso_ratio = anisotropy_from_variance(V) if regime == "fractured" else None

    # restoration phase (residuals from the real Texas post-restoration data)
    if rng.uniform() < IR["restoration_prob"]:
        rest_years = float(rng.uniform(1.0, OR["restoration_years"][1]))
        residual = {sp: float(np.clip(rest_residual[sp]
                                      * rng.uniform(*IR["residual_noise_mult"]),
                                      0.02, 1.0)) for sp in SPECIES}
    else:
        rest_years = 0.0
        residual = {sp: 1.0 for sp in SPECIES}

    # Dual-porosity capacity ratio (fractured only)
    if regime in P.DUAL_POROSITY["enabled_for"]:
        beta = float(rng.uniform(P.DUAL_POROSITY["beta_range"][0], P.DUAL_POROSITY["beta_range"][2]))
    else:
        beta = 0.0

    # Source signature (Texas-derived) and background (nearest JH well to the pin)
    C0 = {sp: float(rng.uniform(*source_sig[sp])) for sp in SPECIES}
    d2 = (wq["longitude"] - lon) ** 2 + (wq["latitude"] - lat) ** 2
    base = wq.loc[d2.idxmin()]
    Cb = {
        "uranium_ppb": float(base["uranium_ppb"]) if pd.notna(base["uranium_ppb"]) else 1.0,
        "sulfate_mg_l": float(base["sulfate_mg_l"]) if pd.notna(base["sulfate_mg_l"]) else 20.0,
        "tds_mg_l": float(base["tds_mg_l"]) if pd.notna(base["tds_mg_l"]) else 300.0,
    }

    # Kd per species sampled from its regime range (low..high)
    Kd = {}
    for sp in SPECIES:
        lo, _, hi = P.KD_RANGES[sp][regime]
        Kd[sp] = float(rng.uniform(lo, hi))

    return dict(lithology=litho, regime=regime, polygon_id=polygon_id,
                K=K, phi_mobile=phi_mobile,
                n_total=n_total, grain_density=grain_density, thickness=thickness,
                lon=lon, lat=lat, Q_in=Q_in, Q_net=Q_net, bleed=bleed,
                op_years=op_years, gradient=gradient, width=width, beta=beta,
                downtime=downtime, seasonal_amp=seasonal_amp,
                rest_years=rest_years, residual=residual,
                C0=C0, Cb=Cb, Kd=Kd, V=V, aniso_ratio=aniso_ratio)


# --------------------------------------------------------------------------- #
# Parameter-uncertainty Monte Carlo (common random numbers)
# --------------------------------------------------------------------------- #
def mc_draws(n_mc: int, seed: int) -> dict[str, np.ndarray]:
    """Common-random-number draw matrix, generated ONCE per run and shared by
    every scenario/time/species so labels are smooth across the design space."""
    rng = np.random.default_rng(seed)
    return {
        "u_kd": rng.uniform(size=n_mc),
        "z_K": rng.standard_normal(n_mc),
        "u_beta": rng.uniform(size=n_mc),
        "u_grad": rng.uniform(size=n_mc),
        "u_disp": rng.uniform(size=n_mc),
        "u_qnet": rng.uniform(size=n_mc),
    }


def _triangular(u: float, lo: float, mode: float, hi: float) -> float:
    """Inverse-CDF triangular sample from a uniform u (KD_RANGES carry a
    central value -- uniform(lo,hi) over-weighted the tails)."""
    if hi <= lo:
        return mode
    Fc = (mode - lo) / (hi - lo)
    if u < Fc:
        return lo + math.sqrt(u * (hi - lo) * (mode - lo))
    return hi - math.sqrt((1.0 - u) * (hi - lo) * (hi - mode))


def _draw_params(scn: dict, species: str, t_days: float, op_days: float,
                 draws: dict, i: int, w_eff: float,
                 rest_days: float, residual_fraction: float) -> TransportParams:
    """TransportParams for MC draw i: local K heterogeneity (log-normal),
    triangular Kd, beta/gradient/dispersivity multipliers, bleed drift, with
    the scenario's seasonal amplitude widening the gradient range and pump
    downtime degrading effective containment."""
    fractured = scn["regime"] == "fractured"
    lo, mid, hi = P.KD_RANGES[species][scn["regime"]]
    kd = _triangular(float(draws["u_kd"][i]), lo, mid, hi)
    K = scn["K"] * float(np.clip(math.exp(MC_LNK_SIGMA * draws["z_K"][i]), *MC_K_CLIP))
    beta = scn["beta"] * (0.6 + 0.8 * float(draws["u_beta"][i])) if fractured else 0.0
    amp = scn.get("seasonal_amp", 0.0)
    g_lo, g_hi = max(0.3, 0.7 - amp), 1.3 + amp
    grad = scn["gradient"] * (g_lo + (g_hi - g_lo) * float(draws["u_grad"][i]))
    disp_mult = 0.7 + 0.8 * float(draws["u_disp"][i])
    qm_lo, qm_hi = P.IRREGULARITY["qnet_drift_mult"]
    Q_net = scn["Q_net"] * (qm_lo + (qm_hi - qm_lo) * float(draws["u_qnet"][i]))

    v = seepage_velocity(K, grad, scn["phi_mobile"])
    q = K * grad
    eta = containment_efficiency(q, scn["thickness"], scn["width"], Q_net)
    eta *= (1.0 - scn.get("downtime", 0.0))
    if fractured:
        v_base, beta_k = v, beta
        sigma = matrix_sigma(scn["n_total"], scn["grain_density"], kd)
    else:
        Rd = retardation_factor(kd, scn["n_total"], scn["grain_density"], "porous", 0.0)
        v_base, beta_k, sigma = v / Rd, 0.0, 0.0

    Xc = front_position(v_base, eta, t_days, op_days, rest_days, beta_k)
    Xw = front_position(v, eta, t_days, op_days, rest_days, 0.0) if fractured else Xc
    aL, aT = dispersivities(max(Xc, scn["width"]), scn["regime"])
    aL *= disp_mult
    if fractured and P.E1_ENABLED and scn.get("aniso_ratio") is not None:
        aT = aL * scn["aniso_ratio"]         # E1: V-derived transverse anisotropy

    Xc_clean, C_res = None, 0.0
    if rest_days > 0.0 and t_days > op_days + rest_days:
        Xc_clean = front_position(v_base, 1.0, t_days, op_days, rest_days, beta_k)
        C_res = residual_fraction * scn["C0"][species]

    # E1 leach-zone disc, gated by P.E1_ENABLED like the served path (OFF -> pre-E1
    # labels, so the non-generator callers/tests are unchanged).
    disc_r = disc_cx = disc_c = 0.0
    if P.E1_ENABLED:
        disc_c = C_res if (Xc_clean is not None and C_res > 0.0) else scn["C0"][species]
        disc_r, disc_cx = w_eff / 2.0, -scn["width"] / 2.0
    return TransportParams(C0=scn["C0"][species], aL=aL, aT=aT,
                           source_width_m=w_eff, Xc=Xc, Xw=Xw, sigma=sigma,
                           t_days=t_days, Xc_clean=Xc_clean, C_res=C_res,
                           disc_radius_m=disc_r, disc_center_x_m=disc_cx, disc_conc=disc_c)


def _throughput_width(scn: dict, t_days: float, op_days: float) -> float:
    """Throughput-widened source width at the evaluation time (CRN-independent)."""
    swept_bulk = math.pi * (scn["width"] / 2.0) ** 2 * scn["thickness"]
    BV = scn["Q_in"] * min(t_days, op_days) / max(swept_bulk, 1e-6)
    return effective_source_width(scn["width"], BV)


def excursion_probability(scn: dict, species: str, t_days: float, op_days: float,
                          draws: dict[str, np.ndarray],
                          rest_days: float = 0.0,
                          residual_fraction: float = 1.0) -> float:
    """Fraction of MC realizations whose MINING-ATTRIBUTABLE concentration at
    the compliance ring exceeds the incremental threshold. (Serving path --
    the training loop gets this from mc_band_labels for coherence.)"""
    threshold = P.EXCURSION_THRESHOLDS[species]
    thr_inc = max(threshold - scn["Cb"][species], P.INCREMENTAL_FLOOR * threshold)
    w_eff = _throughput_width(scn, t_days, op_days)
    n = len(draws["u_kd"])
    breaches = 0
    for i in range(n):
        p = _draw_params(scn, species, t_days, op_days, draws, i, w_eff,
                         rest_days, residual_fraction)
        if concentration_point(P.COMPLIANCE_BUFFER_M, 0.0, p) >= thr_inc:
            breaches += 1
    return breaches / max(n, 1)


def mc_band_labels(scn: dict, species: str, t_days: float, op_days: float,
                   draws: dict[str, np.ndarray]) -> dict:
    """Distributional labels: P10/P50/P90 of area / migration / compliance
    concentration over the parameter-uncertainty draws, plus the breach
    fraction (excursion probability) from the SAME draws."""
    threshold = P.EXCURSION_THRESHOLDS[species]
    Cb = scn["Cb"][species]
    rest_days = scn["rest_years"] * 365.0
    residual = scn["residual"][species]
    w_eff = _throughput_width(scn, t_days, op_days)
    plist = [_draw_params(scn, species, t_days, op_days, draws, i, w_eff,
                          rest_days, residual)
             for i in range(len(draws["u_kd"]))]
    m = mc_field_metrics(plist, threshold=threshold, background=Cb,
                         grid_n=100, compliance_x=P.COMPLIANCE_BUFFER_M)
    q = lambda a: np.quantile(a, (0.10, 0.50, 0.90))          # noqa: E731
    area = q(m["area_ha"])
    dist = q(m["max_dist_m"])
    comp = q(m["compliance_plume"] + Cb)                       # absolute
    out = {}
    for name, vals in (("affected_area_ha", area),
                       ("max_migration_distance_m", dist),
                       ("compliance_conc", comp)):
        for band, v in zip(("p10", "p50", "p90"), vals):
            out[f"{name}_{band}"] = float(v)
    out["excursion_probability"] = float(np.mean(m["compliance_plume"] >= m["thr_inc"]))
    out["off_scale_frac"] = float(np.mean(m["off_scale"]))
    return out


# --------------------------------------------------------------------------- #
# Label one scenario at one time, one species
# --------------------------------------------------------------------------- #
def label_row(scn: dict, t_years: float, species: str,
              draws: dict[str, np.ndarray], scenario_id: int) -> dict:
    t_days = t_years * 365.0
    op_days = scn["op_years"] * 365.0
    rest_days = scn["rest_years"] * 365.0
    threshold = P.EXCURSION_THRESHOLDS[species]

    feat = build_feature_row(
        regime=scn["regime"], domain_is_texas=False,
        K_m_day=scn["K"], gradient_i=scn["gradient"],
        phi_mobile=scn["phi_mobile"], n_total=scn["n_total"],
        grain_density=scn["grain_density"], kd_L_kg=scn["Kd"][species],
        beta=scn["beta"], Q_in_m3_day=scn["Q_in"], bleed_fraction=scn["bleed"],
        operation_days=op_days, wellfield_width_m=scn["width"],
        thickness_m=scn["thickness"],
        source_conc_C0=scn["C0"][species], background_conc_Cb=scn["Cb"][species],
        eval_time_days=t_days, restoration_days=rest_days,
        downtime_fraction=scn["downtime"],
        gradient_seasonal_amp=scn["seasonal_amp"],
        residual_fraction=scn["residual"][species],
        aniso_ratio=scn["aniso_ratio"],          # E1: V-derived (None for porous)
    )
    # deterministic central run (reference + served analytical path)
    res = simulate_plume(feat, species_C0=scn["C0"][species],
                         background=scn["Cb"][species], threshold=threshold,
                         t_days=t_days, operation_days=op_days,
                         restoration_days=rest_days,
                         residual_fraction=scn["residual"][species],
                         grid_n=160, compliance_x=P.COMPLIANCE_BUFFER_M)
    m = res.metrics
    bands = mc_band_labels(scn, species, t_days, op_days, draws)

    row = {k: feat[k] for k in FEATURE_COLUMNS}
    row.update({
        # GROUPING KEYS: scenario_id for the primary leakage-safe CV;
        # polygon_id for leave-aquifer-out stress CV.
        "scenario_id": scenario_id,
        "polygon_id": scn["polygon_id"],
        "lithology": scn["lithology"], "regime": scn["regime"],
        "lon": scn["lon"], "lat": scn["lat"],
        "species": species, "time_years": t_years,
        "is_post_closure": int(t_days > op_days),
        # analytic front positions (recomputable at inference)
        "Xc_m": m["Xc_m"],
        "Xc_clean_m": feat["_Xc_clean_m"],
        # ---- deterministic central labels (reference) ----
        "affected_area_ha": m["affected_area_ha"],
        "max_migration_distance_m": m["max_migration_distance_m"],
        "max_downgradient_m": m["max_downgradient_m"],
        "peak_conc": m["peak_conc"],
        "delta_peak": m["peak_conc"] - scn["Cb"][species],
        "compliance_conc": m["compliance_conc"],
        "breaches_bis": int(m["breaches_at_compliance"]),
        "off_scale": int(m["off_scale"]),
    })
    # ---- distributional targets (what Phase 3 trains on) ----
    row.update(bands)
    return row


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def generate(n_scenarios: int = 900, times_years=DEFAULT_TIMES_YEARS,
             n_mc: int = 48, seed: int = P.RANDOM_SEED,
             out_csv: Path | None = None, field_mix: float = FIELD_MIX_FRAC) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    draws = mc_draws(n_mc, seed + 1)          # CRN: one matrix for the whole run
    aquifers = load_jharkhand_aquifers()
    wq = load_jharkhand_water_quality()
    source_sig = texas_source_signature()
    rest_residual = texas_restoration_residual()

    # v3 is the E1 generator: the leach-zone disc must be ON for the central
    # reference run (params_from_features is flag-gated); the MC draws set the disc
    # explicitly. Restored in `finally` so generation never leaks the flag.
    _e1_prev = P.E1_ENABLED
    P.E1_ENABLED = True
    try:
        rows = []
        for s in range(n_scenarios):
            scn = sample_scenario(rng, aquifers, wq, source_sig, rest_residual,
                                  field_mix=field_mix)
            for t in times_years:
                for sp in SPECIES:
                    rows.append(label_row(scn, t, sp, draws, scenario_id=s))
            if (s + 1) % max(1, n_scenarios // 20) == 0:
                print(f"  ...{s + 1}/{n_scenarios} scenarios ({len(rows)} rows)",
                      flush=True)
    finally:
        P.E1_ENABLED = _e1_prev
    df = pd.DataFrame(rows)

    default_csv = OUT_DIR / "synthetic_training.csv"
    out_csv = Path(out_csv) if out_csv else default_csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    meta = {
        "version": 3, "n_scenarios": n_scenarios, "n_rows": len(df), "n_mc": n_mc,
        "e1_geometry": True, "field_mix_frac": field_mix,
        "times_years": list(times_years), "species": list(SPECIES),
        "feature_columns": FEATURE_COLUMNS,
        "band_targets": [f"{t}_{b}" for t in BAND_TARGETS
                         for b in ("p10", "p50", "p90")],
        "point_target": "excursion_probability",
        "regime_counts": df["regime"].value_counts().to_dict(),
        "n_polygons": int(df["polygon_id"].nunique()),
        "mean_pex_by_species": df.groupby("species")["excursion_probability"].mean().round(3).to_dict(),
        "restoration_share": float((df["restoration_years"] > 0).mean()),
        "compliance_buffer_m": P.COMPLIANCE_BUFFER_M,
        "incremental_floor": P.INCREMENTAL_FLOOR,
        "bis_thresholds": P.EXCURSION_THRESHOLDS,
    }
    meta_path = (OUT_DIR / "synthetic_meta.json" if out_csv == default_csv
                 else out_csv.with_name(out_csv.stem + "_meta.json"))
    meta_path.write_text(json.dumps(meta, indent=2))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=900)
    ap.add_argument("--mc", type=int, default=48)
    ap.add_argument("--seed", type=int, default=P.RANDOM_SEED)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    print(f"Generating synthetic training data v2: {args.scenarios} scenarios "
          f"x {len(DEFAULT_TIMES_YEARS)} times x {len(SPECIES)} species, MC={args.mc}")
    df = generate(n_scenarios=args.scenarios, n_mc=args.mc, seed=args.seed,
                  out_csv=Path(args.out) if args.out else None)
    print(f"\nDONE -> shape={df.shape}")
    print("\nMean excursion probability by species:")
    print(df.groupby("species")["excursion_probability"].mean().round(3).to_string())
    print("\nMC-P50 affected area (ha) by regime:")
    print(df.groupby("regime")["affected_area_ha_p50"].describe()[["mean", "50%", "max"]].round(2).to_string())
    print("\nBand sanity (P10<=P50<=P90 violations):",
          int(((df["affected_area_ha_p10"] > df["affected_area_ha_p50"])
               | (df["affected_area_ha_p50"] > df["affected_area_ha_p90"])).sum()))
