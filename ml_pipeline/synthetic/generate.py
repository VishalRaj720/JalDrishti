"""
ml_pipeline.synthetic.generate  (PHASE 2b -- statewide synthetic loop)
====================================================================
Generate a robust, physics-labelled training set by sweeping the operational and
hydrogeological envelope across BOTH Jharkhand transport regimes, anchored to the
23 real aquifer polygons and the 397 real water-quality baselines.

For each sampled scenario x time x species we emit:
  * the Phase-1 scale-independent feature vector, and
  * physics labels from the analytical engine:
        affected_area_ha, max_migration_distance_m, peak_conc, delta_peak,
        breaches_bis (bool), excursion_probability P_ex.

P_ex is a genuine probability: per scenario we Monte-Carlo the *uncertain* inputs
(Kd, dual-porosity beta, gradient, dispersivity multiplier) and measure the
fraction of realizations whose concentration at a downgradient compliance ring
(wellfield edge + COMPLIANCE_BUFFER_M) breaches the BIS limit.

Long format (one row per scenario x time x species) so a single physics-guided
model can predict all three contaminants through the Kd/Rd mechanism.

CLI:
  python -m ml_pipeline.synthetic.generate                      # default quick run
  python -m ml_pipeline.synthetic.generate --scenarios 4000 --mc 32   # full run
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.feature_engineering import build_feature_row, FEATURE_COLUMNS
from ml_pipeline.data_prep.jharkhand_loader import (
    load_jharkhand_aquifers, load_jharkhand_water_quality,
)
from ml_pipeline.data_prep.texas_loader import texas_source_signature
from ml_pipeline.physics.transport import (
    simulate_plume, effective_travel_distance, concentration_at, domenico_plume,
)
from ml_pipeline.data_prep.feature_engineering import (
    seepage_velocity, retardation_factor, dispersivities, containment_efficiency,
    pore_volumes, effective_source_width,
)

OUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
COMPLIANCE_BUFFER_M = 100.0   # monitoring ring set back from the wellfield edge
SPECIES = ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")
DEFAULT_TIMES_YEARS = (2.0, 5.0, 8.0, 12.0, 20.0)


# --------------------------------------------------------------------------- #
# Scenario sampling -- anchored to real Jharkhand polygons
# --------------------------------------------------------------------------- #
def _representative_point(geom):
    """A guaranteed-interior lon/lat for an aquifer polygon (for the map / pin)."""
    p = geom.representative_point()
    return float(p.x), float(p.y)


def sample_scenario(rng: np.random.Generator, aquifers, wq, source_sig) -> dict:
    """Draw one physically-consistent scenario from a real aquifer polygon."""
    arow = aquifers.iloc[rng.integers(len(aquifers))]
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

    lon, lat = _representative_point(arow.geometry)

    # Operational envelope
    OR = P.OPERATIONAL_RANGES
    Q_in = float(rng.uniform(*OR["injection_rate_m3_day"]))
    bleed = float(rng.uniform(*OR["bleed_fraction"]))
    op_years = float(rng.uniform(*OR["operation_years"]))
    gradient = float(rng.uniform(*OR["hydraulic_gradient"]))
    width = float(rng.uniform(*OR["wellfield_width_m"]))

    # Dual-porosity capacity ratio (fractured only)
    if regime in P.DUAL_POROSITY["enabled_for"]:
        beta = float(rng.uniform(P.DUAL_POROSITY["beta_range"][0], P.DUAL_POROSITY["beta_range"][2]))
    else:
        beta = 0.0

    # Source signature (Texas-derived) and background (nearest JH well)
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

    return dict(lithology=litho, regime=regime, K=K, phi_mobile=phi_mobile,
                n_total=n_total, grain_density=grain_density, thickness=thickness,
                lon=lon, lat=lat, Q_in=Q_in, bleed=bleed, op_years=op_years,
                gradient=gradient, width=width, beta=beta, C0=C0, Cb=Cb, Kd=Kd)


# --------------------------------------------------------------------------- #
# Excursion probability via parameter-uncertainty Monte Carlo
# --------------------------------------------------------------------------- #
def excursion_probability(scn: dict, species: str, t_days: float, op_days: float,
                          rng: np.random.Generator, n_mc: int) -> float:
    """Fraction of MC realizations breaching BIS at the compliance ring."""
    threshold = P.EXCURSION_THRESHOLDS[species]
    x_comp = scn["width"] / 2.0 + COMPLIANCE_BUFFER_M   # ring at RAW permitted edge
    # throughput-widened source (PV independent of MC-sampled params -> compute once)
    pv = pore_volumes(scn["Q_in"], op_days, scn["phi_mobile"],
                      math.pi * scn["width"] ** 2 * scn["thickness"])
    w_eff = effective_source_width(scn["width"], pv)
    lo, _, hi = P.KD_RANGES[species][scn["regime"]]
    breaches = 0
    for _ in range(n_mc):
        kd = rng.uniform(lo, hi)
        beta = scn["beta"] * rng.uniform(0.6, 1.4) if scn["regime"] == "fractured" else 0.0
        grad = scn["gradient"] * rng.uniform(0.7, 1.3)
        disp_mult = rng.uniform(0.7, 1.5)

        v = seepage_velocity(scn["K"], grad, scn["phi_mobile"])
        Rd = retardation_factor(kd, scn["n_total"], scn["grain_density"], scn["regime"], beta)
        vc = v / Rd
        aL, aT = dispersivities(max(vc * op_days, scn["width"]), scn["regime"])
        aL *= disp_mult
        if scn["regime"] == "fractured":
            from ml_pipeline.physics.transport import DUAL_DISP_K
            aL *= (1.0 + DUAL_DISP_K * beta)
        q = scn["K"] * grad
        Q_net = scn["Q_in"] * scn["bleed"]
        eta = containment_efficiency(q, scn["thickness"], scn["width"], Q_net)
        Xc = effective_travel_distance(vc, eta, t_days, op_days)
        c = concentration_at(x_comp, 0.0, Xc=Xc, aL=aL, aT=aT,
                             C0=scn["C0"][species], source_width=w_eff)
        if (c + scn["Cb"][species]) >= threshold:
            breaches += 1
    return breaches / max(n_mc, 1)


# --------------------------------------------------------------------------- #
# Label one scenario at one time, one species
# --------------------------------------------------------------------------- #
def label_row(scn: dict, t_years: float, species: str, rng: np.random.Generator,
              n_mc: int, scenario_id: int) -> dict:
    t_days = t_years * 365.0
    op_days = scn["op_years"] * 365.0
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
    )
    x_comp = scn["width"] / 2.0 + COMPLIANCE_BUFFER_M
    res = simulate_plume(feat, species_C0=scn["C0"][species],
                         background=scn["Cb"][species], threshold=threshold,
                         t_days=t_days, operation_days=op_days, grid_n=160,
                         compliance_x=x_comp)
    m = res.metrics
    p_ex = excursion_probability(scn, species, t_days, op_days, rng, n_mc)

    row = {k: feat[k] for k in FEATURE_COLUMNS}
    row.update({
        # GROUPING KEY: every (time x species) row of one sampled scenario shares
        # this id, so GroupKFold in Phase 3 keeps a scenario wholly in train OR
        # test -> no temporal/scenario leakage.
        "scenario_id": scenario_id,
        "lithology": scn["lithology"], "regime": scn["regime"],
        "lon": scn["lon"], "lat": scn["lat"],
        "species": species, "time_years": t_years,
        # evaluation-time feature: is the plume in post-closure drift at time t?
        "is_post_closure": int(t_days > op_days),
        # ---- TARGETS ----
        "affected_area_ha": m["affected_area_ha"],
        "max_migration_distance_m": m["max_migration_distance_m"],
        "max_downgradient_m": m["max_downgradient_m"],
        "peak_conc": m["peak_conc"],
        "delta_peak": m["peak_conc"] - scn["Cb"][species],
        "compliance_conc": m["compliance_conc"],
        # meaningful binary: contaminant breaches BIS at the monitoring ring
        "breaches_bis": int(m["breaches_at_compliance"]),
        "excursion_probability": p_ex,
        "Xc_m": m["Xc_m"],
        "off_scale": int(m["off_scale"]),
    })
    return row


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def generate(n_scenarios: int = 350, times_years=DEFAULT_TIMES_YEARS,
             n_mc: int = 12, seed: int = P.RANDOM_SEED,
             out_csv: Path | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    aquifers = load_jharkhand_aquifers()
    wq = load_jharkhand_water_quality()
    source_sig = texas_source_signature()

    rows = []
    for s in range(n_scenarios):
        scn = sample_scenario(rng, aquifers, wq, source_sig)
        for t in times_years:
            for sp in SPECIES:
                rows.append(label_row(scn, t, sp, rng, n_mc, scenario_id=s))
        if (s + 1) % max(1, n_scenarios // 10) == 0:
            print(f"  ...{s + 1}/{n_scenarios} scenarios "
                  f"({len(rows)} rows)")
    df = pd.DataFrame(rows)

    out_csv = out_csv or (OUT_DIR / "synthetic_training.csv")
    OUT_DIR.mkdir(exist_ok=True)
    df.to_csv(out_csv, index=False)

    meta = {
        "n_scenarios": n_scenarios, "n_rows": len(df), "n_mc": n_mc,
        "times_years": list(times_years), "species": list(SPECIES),
        "feature_columns": FEATURE_COLUMNS,
        "targets": ["affected_area_ha", "max_migration_distance_m", "peak_conc",
                    "delta_peak", "breaches_bis", "excursion_probability"],
        "regime_counts": df["regime"].value_counts().to_dict(),
        "breach_rate_by_species": df.groupby("species")["breaches_bis"].mean().round(3).to_dict(),
        "compliance_buffer_m": COMPLIANCE_BUFFER_M,
        "bis_thresholds": P.EXCURSION_THRESHOLDS,
    }
    (OUT_DIR / "synthetic_meta.json").write_text(json.dumps(meta, indent=2))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", type=int, default=350)
    ap.add_argument("--mc", type=int, default=12)
    ap.add_argument("--seed", type=int, default=P.RANDOM_SEED)
    args = ap.parse_args()

    print(f"Generating synthetic training data: {args.scenarios} scenarios "
          f"x {len(DEFAULT_TIMES_YEARS)} times x {len(SPECIES)} species, MC={args.mc}")
    df = generate(n_scenarios=args.scenarios, n_mc=args.mc, seed=args.seed)
    print(f"\nDONE -> {OUT_DIR / 'synthetic_training.csv'}  shape={df.shape}")
    print("\nBreach rate by species:")
    print(df.groupby("species")["breaches_bis"].mean().round(3).to_string())
    print("\nAffected area (ha) by regime:")
    print(df.groupby("regime")["affected_area_ha"].describe()[["mean", "50%", "max"]].round(2).to_string())
    print("\nMean excursion probability by species:")
    print(df.groupby("species")["excursion_probability"].mean().round(3).to_string())
