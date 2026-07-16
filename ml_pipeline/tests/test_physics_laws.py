"""
Physics-law regression tests (2026-07 review, Phase 0/1).
========================================================
These assert hydrogeological laws on the PHYSICS LABELS themselves -- the
transport engine's outputs when the RAW OPERATING POINT is swept (all coupled
quantities move together). This is the honest version of what
train.verify_monotonicity used to claim: a constrained-model partial-dependence
sweep can only ever confirm the constraint, not the law.

Run:  python -m pytest ml_pipeline/tests/test_physics_laws.py -q
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.feature_engineering import (
    build_feature_row, containment_efficiency, effective_source_width,
)
from ml_pipeline.physics.transport import (
    simulate_plume, apparent_retardation, retarded_clock, front_position,
    matrix_sigma, tang_attenuation,
)

U_THR = P.EXCURSION_THRESHOLDS["uranium_ppb"]

FRACTURED = dict(regime="fractured", K_m_day=1.12, gradient_i=0.006,
                 phi_mobile=0.008, n_total=0.03, grain_density=2750.0,
                 kd_L_kg=1.0, beta=8.0, thickness_m=37.5)
POROUS = dict(regime="porous", K_m_day=2.345, gradient_i=0.006,
              phi_mobile=0.08, n_total=0.30, grain_density=2650.0,
              kd_L_kg=2.5, beta=0.0, thickness_m=85.0)


def label(hg: dict, *, Q_in=2500.0, bleed=0.02, width=300.0, op_years=8.0,
          t_years=5.0, C0=15000.0, Cb=2.0, rest_years=0.0, residual=1.0,
          downtime=0.0, grid_n=140) -> dict:
    """Raw operating point -> physics labels (the generate.label_row path)."""
    feat = build_feature_row(
        domain_is_texas=False, Q_in_m3_day=Q_in, bleed_fraction=bleed,
        operation_days=op_years * 365.0, wellfield_width_m=width,
        source_conc_C0=C0, background_conc_Cb=Cb,
        eval_time_days=t_years * 365.0, restoration_days=rest_years * 365.0,
        downtime_fraction=downtime, residual_fraction=residual,
        **hg)
    res = simulate_plume(feat, species_C0=C0, background=Cb, threshold=U_THR,
                         t_days=t_years * 365.0, operation_days=op_years * 365.0,
                         restoration_days=rest_years * 365.0,
                         residual_fraction=residual, grid_n=grid_n,
                         compliance_x=P.COMPLIANCE_BUFFER_M)
    return res.metrics


def _nondecreasing(vals, tol):
    return all(b >= a - tol for a, b in zip(vals, vals[1:]))


def _nonincreasing(vals, tol):
    return all(b <= a + tol for a, b in zip(vals, vals[1:]))


# --------------------------------------------------------------------------- #
# 1. THE USER LAW, stated honestly: at FIXED NET EXTRACTION, higher injection
#    -> larger contaminated footprint. (At fixed bleed FRACTION the law is
#    confounded: Q_net = Q_in*bleed rises too and containment can win --
#    the 2026-07 review measured exactly that inversion.)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hg", [FRACTURED, POROUS], ids=["fractured", "porous"])
@pytest.mark.parametrize("t_years", [5.0, 20.0], ids=["during-op", "post-closure"])
def test_qin_law_at_fixed_qnet(hg, t_years):
    Q_net = 40.0
    qs = [500.0, 1500.0, 3000.0, 5000.0]
    rows = [label(hg, Q_in=q, bleed=Q_net / q, t_years=t_years) for q in qs]
    areas = [r["affected_area_ha"] for r in rows]
    concs = [r["compliance_conc"] for r in rows]
    assert _nondecreasing(areas, tol=0.5), f"area vs Q_in @Qnet fixed: {areas}"
    assert areas[-1] > areas[0], f"area must strictly grow: {areas}"
    assert _nondecreasing(concs, tol=1e-6), f"ring conc vs Q_in: {concs}"


def test_bleed_containment_law():
    """At fixed Q_in, more net extraction -> smaller footprint, lower ring conc."""
    for hg in (FRACTURED, POROUS):
        bleeds = [0.0, 0.01, 0.03, 0.06]
        rows = [label(hg, bleed=b, t_years=5.0) for b in bleeds]
        areas = [r["affected_area_ha"] for r in rows]
        concs = [r["compliance_conc"] for r in rows]
        assert _nonincreasing(areas, tol=0.5), f"{hg['regime']}: area vs bleed {areas}"
        assert _nonincreasing(concs, tol=1e-6), f"{hg['regime']}: conc vs bleed {concs}"


def test_complete_capture_branch():
    """Capture-zone eta: Q_net >= q*b*W => eta == 1 and (during operation)
    essentially no downgradient excursion."""
    hg = FRACTURED
    q = hg["K_m_day"] * hg["gradient_i"]
    W, b = 300.0, hg["thickness_m"]
    Q_regional = q * b * W
    eta = containment_efficiency(q, b, W, Q_regional * 1.5)
    assert eta == 1.0
    m = label(hg, Q_in=2500.0, bleed=(Q_regional * 1.5) / 2500.0, t_years=5.0)
    assert m["max_downgradient_m"] <= 30.0, m["max_downgradient_m"]
    assert not m["breaches_at_compliance"]


def test_time_monotonic():
    """Later evaluation time -> footprint never shrinks (no restoration)."""
    for hg in (FRACTURED, POROUS):
        rows = [label(hg, t_years=t) for t in (2.0, 5.0, 8.0, 12.0, 20.0)]
        areas = [r["affected_area_ha"] for r in rows]
        dists = [r["max_migration_distance_m"] for r in rows]
        assert _nondecreasing(areas, tol=0.5), f"{hg['regime']}: area vs t {areas}"
        assert _nondecreasing(dists, tol=10.0), f"{hg['regime']}: dist vs t {dists}"


# --------------------------------------------------------------------------- #
# 2. tanh source coupling: time-consistent, live in BOTH regimes, bounded.
# --------------------------------------------------------------------------- #
def test_source_width_time_consistency():
    def w_eff(t_years, Q=3000.0, hg=FRACTURED, op=8.0):
        feat = build_feature_row(domain_is_texas=False, Q_in_m3_day=Q,
                                 bleed_fraction=0.02, operation_days=op * 365,
                                 wellfield_width_m=300.0, source_conc_C0=1e4,
                                 background_conc_Cb=2.0,
                                 eval_time_days=t_years * 365, **hg)
        return feat["_source_width_m"]
    # grows while pumping, frozen after closure, bounded by (1+gain)*W
    assert w_eff(2) < w_eff(5) < w_eff(8)
    assert math.isclose(w_eff(8), w_eff(15), rel_tol=1e-9)   # pumping stopped
    assert w_eff(20) <= 300.0 * (1 + P.SOURCE_BV_GAIN) + 1e-9
    # live dW/dQ in the FRACTURED regime (was tanh-saturated pre-review)
    def w_q(Q):
        feat = build_feature_row(domain_is_texas=False, Q_in_m3_day=Q,
                                 bleed_fraction=0.02, operation_days=8 * 365,
                                 wellfield_width_m=300.0, source_conc_C0=1e4,
                                 background_conc_Cb=2.0,
                                 eval_time_days=5 * 365, **FRACTURED)
        return feat["_source_width_m"]
    assert w_q(5000) - w_q(500) > 10.0, "source coupling must be live in fractured"
    # boundary conditions of the tanh form itself
    assert effective_source_width(300.0, 0.0) == pytest.approx(300.0)
    assert effective_source_width(300.0, 1e9) <= 300.0 * (1 + P.SOURCE_BV_GAIN) + 1e-6


# --------------------------------------------------------------------------- #
# 3. Restoration: sweep + residual source must reduce late-time impact.
# --------------------------------------------------------------------------- #
def test_restoration_reduces_impact():
    for hg in (FRACTURED, POROUS):
        no_rest = label(hg, t_years=20.0, op_years=8.0)
        rest = label(hg, t_years=20.0, op_years=8.0, rest_years=4.0, residual=0.2)
        assert rest["peak_conc"] <= no_rest["peak_conc"]
        assert rest["affected_area_ha"] <= no_rest["affected_area_ha"] + 0.5
    # near-source concentration relaxes toward the residual level (porous:
    # clean front clearly overtakes the source zone by late time)
    rest_p = label(POROUS, t_years=20.0, op_years=6.0, rest_years=2.0,
                   residual=0.2, C0=15000.0)
    assert rest_p["peak_conc"] < 0.6 * 15000.0


# --------------------------------------------------------------------------- #
# 4. Dual-porosity kinematics: closed-form clock == numerical integral;
#    early-unretarded / late-asymptote behavior.
# --------------------------------------------------------------------------- #
def test_apparent_retardation_limits():
    beta, omega = 8.0, 1e-3
    assert apparent_retardation(0.0, beta, omega) == pytest.approx(1.0)
    assert apparent_retardation(1e7, beta, omega) == pytest.approx(1.0 + beta, rel=1e-6)
    ts = np.linspace(0, 8000, 60)
    Rs = [apparent_retardation(t, beta, omega) for t in ts]
    assert _nondecreasing(Rs, tol=1e-12)


def test_retarded_clock_matches_quadrature():
    beta, omega = 8.0, 1e-3
    for t_end in (30.0, 365.0, 3650.0, 20000.0):
        tt = np.linspace(0, t_end, 20001)
        numeric = np.trapezoid(1.0 / np.array([apparent_retardation(t, beta, omega) for t in tt]), tt)
        closed = retarded_clock(t_end, beta, omega)
        assert closed == pytest.approx(numeric, rel=1e-4), t_end
    # early ~ unretarded, late slope ~ 1/(1+beta)
    assert retarded_clock(1.0, beta, omega) == pytest.approx(1.0, rel=0.05)
    late = (retarded_clock(50000, beta, omega) - retarded_clock(40000, beta, omega)) / 10000
    assert late == pytest.approx(1 / (1 + beta), rel=1e-3)


def test_front_three_phases():
    v, eta = 0.8, 0.6
    op, rest = 8 * 365.0, 4 * 365.0
    # held during restoration
    x_op_end = front_position(v, eta, op, op, rest)
    x_mid_rest = front_position(v, eta, op + rest / 2, op, rest)
    assert x_mid_rest == pytest.approx(x_op_end)
    # drifts after restoration
    assert front_position(v, eta, op + rest + 365, op, rest) > x_op_end
    # complete capture during operation
    assert front_position(v, 1.0, op / 2, op, 0.0) == 0.0


# --------------------------------------------------------------------------- #
# 5. Matrix diffusion (Tang kernel): Kd acts through sigma; attenuation
#    monotone in distance and sigma; zero beyond the water front.
# --------------------------------------------------------------------------- #
def test_matrix_sigma_and_tang():
    s_lo = matrix_sigma(0.03, 2750.0, 0.3)
    s_hi = matrix_sigma(0.03, 2750.0, 3.0)
    assert s_hi > s_lo > 0.0, "sigma must grow with Kd (matrix retardation)"
    X = np.array([50.0, 200.0, 500.0, 900.0, 1100.0])
    A = tang_attenuation(X, 365.0, Xw_m=1000.0, sigma=0.2)
    assert A[-1] == 0.0                      # beyond the water front
    assert _nonincreasing(list(A[:-1]), tol=1e-12)
    A_hi = tang_attenuation(X, 365.0, Xw_m=1000.0, sigma=1.0)
    assert np.all(A_hi[:-1] <= A[:-1] + 1e-12)   # more sigma -> more attenuation
    # early-arrival envelope: concentration can exist BEYOND the retarded
    # continuum front (open-fracture channel), attenuated but nonzero
    A_far = tang_attenuation(np.array([600.0]), 180.0, Xw_m=1000.0, sigma=0.05)
    assert 0.0 < float(A_far[0]) < 1.0


# --------------------------------------------------------------------------- #
# 6. Incremental exceedance: ambient water at/above the limit cannot flood
#    the grid ("whole-grid breach" pathology from the review).
# --------------------------------------------------------------------------- #
def test_incremental_exceedance_pathology():
    clean = label(POROUS, Cb=2.0, t_years=10.0)
    dirty = label(POROUS, Cb=35.0, t_years=10.0)      # ambient ALREADY > 30 ppb
    assert dirty["affected_area_ha"] < 10.0 * max(clean["affected_area_ha"], 1.0), \
        "background >= threshold must not mark the whole grid as affected"
    # incremental floor engaged
    assert dirty["incremental_threshold"] == pytest.approx(P.INCREMENTAL_FLOOR * U_THR)


# --------------------------------------------------------------------------- #
# 7. Parser / config helpers touched in Phase 0.
# --------------------------------------------------------------------------- #
def test_parse_numeric_range_scientific():
    from ml_pipeline.data_prep.texas_loader import parse_numeric_range
    assert parse_numeric_range("8.15E+10") == (8.15e10, 8.15e10, 8.15e10)
    assert parse_numeric_range("28-40") == (28.0, 34.0, 40.0)
    assert parse_numeric_range("870, 1000")[0] == 870.0
    assert all(np.isnan(v) for v in parse_numeric_range("-"))


# (superseded by test_alkalinity_suppression_only — the pre-audit amplify-at-low-
#  HCO3 behavior was the bug that helped freeze the porous-override plume)


def test_mc_triangular_and_crn():
    from ml_pipeline.synthetic.generate import _triangular, mc_draws
    us = np.linspace(0.001, 0.999, 200)
    xs = [_triangular(u, 0.3, 1.0, 3.0) for u in us]
    assert min(xs) >= 0.3 and max(xs) <= 3.0
    assert _nondecreasing(xs, tol=1e-12)          # inverse CDF is monotone
    d1, d2 = mc_draws(32, 7), mc_draws(32, 7)
    assert np.array_equal(d1["z_K"], d2["z_K"])   # common random numbers


# --------------------------------------------------------------------------- #
# 8. Phase-2 v2 laws: fixed-ring width law, downtime law, MC-label invariants.
# --------------------------------------------------------------------------- #
def test_width_law_fixed_ring():
    """v2 geometry: the ring sits a FIXED 100 m beyond the wellfield edge, so a
    wider wellfield (wider source + weaker relative capture) is monotone-more
    contamination -- this justifies the +1 width constraint that the OLD
    centre-referenced geometry violently violated (8301 -> 17)."""
    for hg in (FRACTURED, POROUS):
        rows = [label(hg, width=w, t_years=10.0) for w in (100.0, 300.0, 600.0, 800.0)]
        concs = [r["compliance_conc"] for r in rows]
        areas = [r["affected_area_ha"] for r in rows]
        # tol: the post-closure natural-flush wave (real-ISR upgrade) adds a
        # sub-0.1% ripple to the ring conc at t > op; the width LAW itself is
        # orders of magnitude larger (100 -> 300 m jumps the conc ~10x).
        assert _nondecreasing(concs, tol=60.0), f"{hg['regime']}: conc vs W {concs}"
        assert _nondecreasing(areas, tol=1.0), f"{hg['regime']}: area vs W {areas}"


def test_downtime_law():
    """Pump-downtime episodes degrade capture -> monotone-more contamination."""
    for hg in (FRACTURED, POROUS):
        rows = [label(hg, bleed=0.03, t_years=5.0, downtime=f)
                for f in (0.0, 0.1, 0.2, 0.3)]
        areas = [r["affected_area_ha"] for r in rows]
        concs = [r["compliance_conc"] for r in rows]
        assert _nondecreasing(areas, tol=0.5), f"{hg['regime']}: area vs downtime {areas}"
        assert _nondecreasing(concs, tol=1e-6), f"{hg['regime']}: conc vs downtime {concs}"


def _demo_scenario(regime="fractured"):
    hg = FRACTURED if regime == "fractured" else POROUS
    return dict(regime=regime, polygon_id=0, K=hg["K_m_day"],
                phi_mobile=hg["phi_mobile"], n_total=hg["n_total"],
                grain_density=hg["grain_density"], thickness=hg["thickness_m"],
                lon=86.0, lat=23.0, Q_in=2500.0, Q_net=50.0, bleed=0.02,
                op_years=8.0, gradient=hg["gradient_i"], width=300.0,
                beta=hg["beta"], downtime=0.0, seasonal_amp=0.0,
                rest_years=0.0,
                residual={sp: 1.0 for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")},
                C0={sp: 15000.0 for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")},
                Cb={sp: 2.0 for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")},
                Kd={sp: 1.0 for sp in ("uranium_ppb", "sulfate_mg_l", "tds_mg_l")})


def test_mc_band_labels_invariants():
    from ml_pipeline.synthetic.generate import mc_band_labels, mc_draws
    scn = _demo_scenario()
    out = mc_band_labels(scn, "uranium_ppb", 5 * 365.0, 8 * 365.0, mc_draws(32, 5))
    for t in ("affected_area_ha", "max_migration_distance_m", "compliance_conc"):
        p10, p50, p90 = (out[f"{t}_{b}"] for b in ("p10", "p50", "p90"))
        assert p10 <= p50 <= p90, (t, p10, p50, p90)
        assert p10 >= 0.0
    assert 0.0 <= out["excursion_probability"] <= 1.0
    assert 0.0 <= out["off_scale_frac"] <= 1.0


# --------------------------------------------------------------------------- #
# 9. Regime-toggle audit fixes (2026-07): no material chimera, alkalinity
#    suppression-only, train==serve Kd, porous override is alive.
# --------------------------------------------------------------------------- #
def test_alkalinity_suppression_only():
    """The ambient-alkalinity helper must NEVER amplify Kd above central (the
    ISR plume carries its own carbonate). Pre-audit it amplified at low HCO3."""
    lo, mid, hi = P.KD_RANGES["uranium_ppb"]["porous"]
    ref = P.KD_ALKALINITY["ref_hco3_mg_l"]
    assert P.alkalinity_adjusted_kd(mid, None, lo, hi) == pytest.approx(mid)
    assert P.alkalinity_adjusted_kd(mid, 50.0, lo, hi) == pytest.approx(mid), \
        "low ambient HCO3 must NOT amplify Kd (pre-audit bug)"
    assert P.alkalinity_adjusted_kd(mid, ref * 4, lo, hi) < mid, "high HCO3 suppresses"
    assert P.alkalinity_adjusted_kd(mid, 1e9, lo, hi) >= lo    # clipped to range


def test_regime_archetypes_present():
    for r in ("fractured", "porous"):
        a = P.REGIME_ARCHETYPE[r]
        assert {"phi_mobile", "n_total", "grain_density"} <= set(a)
    # porous archetype must have realistic (large) total porosity so bulk
    # sorption does not explode Rd
    assert P.REGIME_ARCHETYPE["porous"]["n_total"] >= 0.2


def test_regime_override_no_chimera():
    """Overriding a FRACTURED (schist) pin to 'porous' must substitute porous
    materials -> Rd stays physical (~tens), not the pre-audit Rd~635 that froze
    the plume. Uses the real dashboard resolve path."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    base = dict(lon=86.2, lat=22.8, species="uranium_ppb")
    nat, _ = resolve_inputs({**base, "regime": None})
    ov, hydro = resolve_inputs({**base, "regime": "porous"})
    assert nat["regime"] == "fractured", "test pin should be fractured schist"
    arch = P.REGIME_ARCHETYPE["porous"]
    assert ov["n_total"] == pytest.approx(arch["n_total"]), "archetype n_total not applied"
    assert ov["phi_mobile"] == pytest.approx(arch["phi_mobile"]), "archetype phi not applied"
    assert ov["phi_mobile"] != pytest.approx(nat["phi_mobile"]), "still using pin materials"
    assert hydro["regime_overridden"] is True
    from ml_pipeline.data_prep.feature_engineering import retardation_factor
    Rd = retardation_factor(ov["kd_L_kg"], ov["n_total"], ov["grain_density"],
                            "porous", ov["beta"])
    assert Rd < 100, f"regime override still produces a chimera Rd={Rd:.0f}"


def test_kd_train_equals_serve():
    """Serving Kd = KD_RANGES central (what the generator samples) -- NOT the
    alkalinity-amplified value that caused the train/serve skew."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    inputs, _ = resolve_inputs(dict(lon=86.2, lat=22.8, species="uranium_ppb",
                                    regime="porous"))
    assert inputs["kd_L_kg"] == pytest.approx(P.KD_RANGES["uranium_ppb"]["porous"][1])


def test_porous_override_is_alive():
    """After the fix the porous-override front is no longer frozen and responds
    to species: the conservative TDS front (Xc) runs far past the retarded
    uranium front. NOTE the honest probe is Xc, the front position -- at this
    low-K pin both `area` and `migration_m` are dominated by the wide source
    footprint (~400 m wellfield), so they barely differentiate species. That
    source-dominance is a real property, not a bug; it just means those two
    metrics are insensitive at low-velocity pins."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import features_from_inputs
    xc = {}
    for sp in ("uranium_ppb", "tds_mg_l"):
        # pin the gradient so this probes the regime-OVERRIDE physics, not the
        # (Stage B) data-derived flow default, which is pin-specific and lower.
        inputs, _ = resolve_inputs(dict(lon=86.2, lat=22.8, species=sp,
                                        regime="porous", gradient_i=0.005))
        _, feat, Xc = features_from_inputs(**inputs)
        xc[sp] = Xc
    assert xc["uranium_ppb"] > 2.0, "U front frozen at source (chimera not fixed)"
    assert xc["tds_mg_l"] > 5.0 * xc["uranium_ppb"], xc   # conservative outruns sorbing


def test_band_constraint_policy():
    """Phase 3.5: only the P50 central estimate is monotone-constrained; the
    P10/P90 uncertainty band edges are free (they can't represent the switch-
    like compliance tail under hard constraints)."""
    from ml_pipeline.ml.dataset import monotone_tuple, CONSTRAIN_BANDS, MODEL_FEATURES
    assert CONSTRAIN_BANDS == ("p50",)
    p50 = monotone_tuple("compliance_conc", "p50")
    p90 = monotone_tuple("compliance_conc", "p90")
    assert any(s != 0 for s in p50), "P50 must stay constrained (physics)"
    assert all(s == 0 for s in p90), "P10/P90 must be free"
    assert len(p50) == len(MODEL_FEATURES)


def test_mc_field_matches_single_solve():
    """The vectorized MC field evaluator must agree with solve_plume for a
    single parameter set on the same grid size."""
    from ml_pipeline.physics.transport import (params_from_features, solve_plume,
                                               mc_field_metrics)
    feat = build_feature_row(
        domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
        operation_days=8 * 365.0, wellfield_width_m=300.0,
        source_conc_C0=15000.0, background_conc_Cb=2.0,
        eval_time_days=5 * 365.0, **FRACTURED)
    p = params_from_features(feat, species_C0=15000.0, t_days=5 * 365.0,
                             operation_days=8 * 365.0)
    m1 = solve_plume(p, threshold=U_THR, background=2.0, grid_n=100,
                     compliance_x=P.COMPLIANCE_BUFFER_M).metrics
    m2 = mc_field_metrics([p], threshold=U_THR, background=2.0, grid_n=100,
                          compliance_x=P.COMPLIANCE_BUFFER_M)
    assert m2["area_ha"][0] == pytest.approx(m1["affected_area_ha"], rel=1e-6)
    assert m2["max_dist_m"][0] == pytest.approx(m1["max_migration_distance_m"], rel=1e-6)
    assert m2["compliance_plume"][0] + 2.0 == pytest.approx(m1["compliance_conc"], rel=1e-6)


def _e1_area(C0, e1_on):
    """Affected area for a contained fractured scenario with E1 disc on/off."""
    from ml_pipeline.physics.transport import simulate_plume
    P.E1_ENABLED = e1_on
    feat = build_feature_row(
        domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
        operation_days=8 * 365.0, wellfield_width_m=300.0,
        source_conc_C0=C0, background_conc_Cb=2.0, eval_time_days=5 * 365.0,
        **FRACTURED)
    return simulate_plume(feat, species_C0=C0, background=2.0, threshold=U_THR,
                          t_days=5 * 365.0, operation_days=8 * 365.0).metrics["affected_area_ha"]


def test_e1_disc_adds_footprint_and_gates_on_threshold():
    """E1 (Stage E): the leach-zone disc adds the well-field source footprint to
    the affected area for a REAL source, but a sub-threshold (clamped non-ore)
    source contributes NOTHING (threshold gate -> no ghost disc). Flag isolated."""
    try:
        off = _e1_area(13272.0, False)
        on = _e1_area(13272.0, True)
        trace = _e1_area(5.0, True)          # C0 < incremental BIS threshold
        assert on > off + 3.0                # disc ~ pi*(W_eff/2)^2 added
        assert trace == pytest.approx(0.0, abs=1e-6)
    finally:
        P.E1_ENABLED = False                 # never leak the flag to other tests


def test_e1_mc_matches_single_solve_with_disc():
    """solve_plume and the vectorized MC evaluator must still agree once the disc
    is active (both paths carry it)."""
    from ml_pipeline.physics.transport import (params_from_features, solve_plume,
                                               mc_field_metrics)
    try:
        P.E1_ENABLED = True
        feat = build_feature_row(
            domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
            operation_days=8 * 365.0, wellfield_width_m=300.0,
            source_conc_C0=15000.0, background_conc_Cb=2.0,
            eval_time_days=5 * 365.0, **FRACTURED)
        p = params_from_features(feat, species_C0=15000.0, t_days=5 * 365.0,
                                 operation_days=8 * 365.0)
        assert p.disc_radius_m > 0.0         # disc actually on
        m1 = solve_plume(p, threshold=U_THR, background=2.0, grid_n=100).metrics
        m2 = mc_field_metrics([p], threshold=U_THR, background=2.0, grid_n=100)
        assert m2["area_ha"][0] == pytest.approx(m1["affected_area_ha"], rel=1e-6)
        assert m2["max_dist_m"][0] == pytest.approx(m1["max_migration_distance_m"], rel=1e-6)
    finally:
        P.E1_ENABLED = False
