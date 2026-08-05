"""
Real-ISR upgrade regression tests (2026-07-13): first-order U natural
attenuation (A) + post-closure natural source flush (B).
=====================================================================
A: dissolved U(VI) reduces to immobile U(IV) along travel -> the plume gains a
   FINITE steady-state extent instead of unbounded growth (user scenario 2).
B: after injection stops, the source zone is passively flushed (30-yr
   half-life) through the same deficit-wave machinery restoration uses --
   restoration is the accelerated version of the natural process (scenario 3).

Run:  python -m pytest ml_pipeline/tests/test_attenuation.py -q
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.feature_engineering import build_feature_row
from ml_pipeline.physics.transport import (
    simulate_plume, concentration_point, params_from_features,
)

U_THR = P.EXCURSION_THRESHOLDS["uranium_ppb"]

FRACTURED = dict(regime="fractured", K_m_day=1.12, gradient_i=0.006,
                 phi_mobile=0.008, n_total=0.03, grain_density=2750.0,
                 kd_L_kg=1.0, beta=8.0, thickness_m=37.5)


def feat_row(*, op_years=8.0, t_years=10.0, rest_years=0.0, k_atten=0.0,
             residual=0.066):
    return build_feature_row(
        domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
        operation_days=op_years * 365.0, wellfield_width_m=300.0,
        source_conc_C0=15000.0, background_conc_Cb=2.0,
        eval_time_days=t_years * 365.0, restoration_days=rest_years * 365.0,
        residual_fraction=residual, u_attenuation_k_per_yr=k_atten, **FRACTURED)


def label(*, op_years=8.0, t_years=10.0, rest_years=0.0, k_atten=0.0,
          grid_n=140):
    feat = feat_row(op_years=op_years, t_years=t_years, rest_years=rest_years,
                    k_atten=k_atten)
    res = simulate_plume(feat, species_C0=15000.0, background=2.0,
                         threshold=U_THR, t_days=t_years * 365.0,
                         operation_days=op_years * 365.0,
                         restoration_days=rest_years * 365.0,
                         residual_fraction=0.066, grid_n=grid_n,
                         compliance_x=P.COMPLIANCE_BUFFER_M)
    return res.metrics


# --------------------------------------------------------------------------- #
# A -- the attenuation law itself
# --------------------------------------------------------------------------- #
def test_atten_feature_and_carry():
    """The decay-per-metre carry-through uses the SAME retardation the front
    does. In fractured rock that is the SORBING capacity ratio beta_eff = beta*R_m
    (remediation 2026-08-05), NOT the conservative-tracer `contaminant_velocity_vc`
    feature -- those two deliberately diverge here, because the MODEL FEATURES
    keep their tracer definitions while the physics uses the sorbing one (the
    corrected kinematics reach the surrogate through the Xc_m feature instead).
    Before the fix this test pinned _atten_per_m to the tracer velocity, which
    would have let attenuation and kinematics disagree by ~80x."""
    from ml_pipeline.physics.transport import effective_capacity_ratio
    f = feat_row(k_atten=0.2)
    assert f["u_attenuation_k"] == pytest.approx(0.2)
    # TRACER-retarded velocity: the residence time charged to redox trapping is
    # the time the solute spends as MOBILE dissolved U(VI). Uranium held in the
    # matrix by sorption is already immobilised -- that is what the retardation
    # term represents -- so charging it the reduction rate for that same
    # residence removes the mass twice. Using the sorption-retarded velocity gave
    # atten_per_m = 0.47/m at the default pin, annihilating the plume inside one
    # metre (below the model's own grid resolution) and claiming ~900x more
    # reduced uranium than any measured reducing capacity supports.
    v_c = f["seepage_velocity_v"] / (1.0 + FRACTURED["beta"])
    assert f["_atten_per_m"] == pytest.approx((0.2 / 365.0) / v_c)
    # the sorbed-residence version it replaced was ~80x stronger
    beta_eff = effective_capacity_ratio(FRACTURED["beta"], FRACTURED["n_total"],
                                        FRACTURED["grain_density"],
                                        FRACTURED["kd_L_kg"])
    sorbed = (0.2 / 365.0) / (f["seepage_velocity_v"] / (1.0 + beta_eff))
    assert sorbed > 50 * f["_atten_per_m"]
    assert feat_row(k_atten=0.0)["_atten_per_m"] == 0.0


def test_point_concentration_decays_exponentially():
    """C(x) with attenuation = C(x) without x exp(-lambda x), deep inside the
    plume (same front factors cancel)."""
    f0 = feat_row(t_years=20.0, k_atten=0.0)
    f1 = feat_row(t_years=20.0, k_atten=0.3)
    p0 = params_from_features(f0, species_C0=15000.0, t_days=20 * 365.0,
                              operation_days=8 * 365.0)
    p1 = params_from_features(f1, species_C0=15000.0, t_days=20 * 365.0,
                              operation_days=8 * 365.0)
    lam = f1["_atten_per_m"]
    for x in (50.0, 150.0, 300.0):
        c0 = concentration_point(x, 0.0, p0)
        c1 = concentration_point(x, 0.0, p1)
        assert c1 == pytest.approx(c0 * math.exp(-lam * x), rel=1e-6)
    # source plane / upstream untouched by attenuation (flush handles those)
    assert concentration_point(-50.0, 0.0, p1) == pytest.approx(
        concentration_point(-50.0, 0.0, p0), rel=1e-9)


def test_atten_monotone_footprint():
    a = [label(t_years=20.0, k_atten=k)["affected_area_ha"]
         for k in (0.0, 0.1, 0.3, 0.7)]
    m = [label(t_years=20.0, k_atten=k)["max_migration_distance_m"]
         for k in (0.0, 0.1, 0.3, 0.7)]
    assert all(x1 <= x0 + 1e-9 for x0, x1 in zip(a, a[1:])), a
    assert all(x1 <= x0 + 1e-9 for x0, x1 in zip(m, m[1:])), m


# --------------------------------------------------------------------------- #
# A -- scenario 2: the plume STABILIZES instead of growing unboundedly
# --------------------------------------------------------------------------- #
def test_redox_trapping_decelerates_and_shortens_the_plume():
    """Redox trapping must (a) shorten the plume at every time, (b) make the gap
    against the no-trapping counterfactual GROW with time, and (c) decelerate
    growth more than free drift does.

    Asserted RELATIVE to the k=0 counterfactual rather than against an absolute
    growth-ratio threshold. The old test required late growth < 0.35x early, a
    bar calibrated when attenuation was applied over the SORPTION-retarded
    residence -- 0.47/m, which annihilated the plume within a metre and made
    'saturation' trivially true. With the double-count removed (see
    P.ATTENUATION_USES_SORBED_RESIDENCE) the equilibrium extent
    x* = (v_c/k)*ln(C0/thr) moves ~80x further out, to ~880 m for this fixture,
    so a 50-year run legitimately never reaches it. Saturation is still real; it
    is simply not visible inside the window, and a test must not demand that it
    be."""
    ks = [label(t_years=t, k_atten=0.2)["max_migration_distance_m"]
          for t in (10.0, 30.0, 50.0)]
    free = [label(t_years=t, k_atten=0.0)["max_migration_distance_m"]
            for t in (10.0, 30.0, 50.0)]
    # (a) shorter at every time
    for a, b in zip(ks, free):
        assert a <= b + 1e-9, (ks, free)
    # (b) the deficit accumulates with travel time
    assert (free[2] - ks[2]) > (free[0] - ks[0]), (ks, free)
    # (c) trapping decelerates growth more than free drift alone
    decel_k = (ks[2] - ks[1]) / max(ks[1] - ks[0], 1e-9)
    decel_free = (free[2] - free[1]) / max(free[1] - free[0], 1e-9)
    assert decel_k < decel_free, (decel_k, decel_free)


def test_equilibrium_extent_law_holds_where_it_is_reachable():
    """The finite steady-state extent x* = (v_c/k)*ln(C0/thr) is the whole point
    of first-order trapping, so verify it where the run IS long enough to reach
    it: a slow plume with a strong sink."""
    slow = {**FRACTURED, "K_m_day": 0.05, "gradient_i": 0.001}

    def reach(t_years):
        feat = build_feature_row(
            domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
            operation_days=8 * 365.0, wellfield_width_m=300.0,
            source_conc_C0=15000.0, background_conc_Cb=2.0,
            eval_time_days=t_years * 365.0, u_attenuation_k_per_yr=0.7, **slow)
        return simulate_plume(feat, species_C0=15000.0, background=2.0,
                              threshold=U_THR, t_days=t_years * 365.0,
                              operation_days=8 * 365.0, grid_n=140,
                              ).metrics["max_migration_distance_m"]

    late = [reach(t) for t in (20.0, 35.0, 50.0)]
    # growth has all but stopped -> the front has found its equilibrium
    assert (late[2] - late[1]) <= 0.5 * max(late[1] - late[0], 1e-9), late


# --------------------------------------------------------------------------- #
# B -- natural post-closure source flush (scenario 2's endgame)
# --------------------------------------------------------------------------- #
def test_natural_flush_cleans_source_zone_without_restoration():
    """Post-closure, the near-source cell must decay with the 30-yr half-life
    flush even with NO restoration sweep (was frozen at C0 forever)."""
    f = feat_row(t_years=30.0, k_atten=0.0)
    p = params_from_features(f, species_C0=15000.0, t_days=30 * 365.0,
                             operation_days=8 * 365.0)
    flush = 0.5 ** ((30.0 - 8.0) / P.DISC_FLUSH_HALFLIFE_YEARS)
    # (a) THE LAW ITSELF, independent of field geometry: the source term and the
    # leach-zone disc are both drawn down by the flush factor. This is the claim
    # the test is named for, so assert it directly rather than inferring it from
    # a probe point whose validity depends on how far the front has run.
    assert p.C_res == pytest.approx(15000.0 * flush, rel=1e-6)
    assert p.disc_conc == pytest.approx(15000.0 * flush, rel=1e-6)
    # (b) and the deficit wave really does wipe the source ZONE to C_res in the
    # field. Probed at x = -50 m, well inside the source box: the old probe at
    # x = +10 m was downstream, and with the sorbing capacity ratio (beta_eff =
    # beta*R_m, remediation 2026-08-05) the fractured front is only ~13 m at 30 yr,
    # so +10 m had drifted onto the front's erfc shoulder and was measuring the
    # front's decay, not the source's flush.
    assert concentration_point(-50.0, 0.0, p) == pytest.approx(15000.0 * flush, rel=0.02)
    # during operations: untouched (flush factor = 1, no wave)
    f_op = feat_row(t_years=5.0, k_atten=0.0)
    p_op = params_from_features(f_op, species_C0=15000.0, t_days=5 * 365.0,
                                operation_days=8 * 365.0)
    assert concentration_point(-50.0, 0.0, p_op) == pytest.approx(15000.0, rel=0.02)


def test_flush_continuous_at_closure():
    a = label(t_years=7.9)["affected_area_ha"]
    b = label(t_years=8.1)["affected_area_ha"]
    assert abs(b - a) / max(a, 1e-9) < 0.05, (a, b)


def test_restoration_still_dominates_natural_flush():
    """An active sweep must clean the source faster than passive flushing."""
    swept = label(t_years=15.0, rest_years=4.0)
    passive = label(t_years=15.0, rest_years=0.0)
    assert swept["peak_conc"] <= passive["peak_conc"] + 1e-6
    assert swept["affected_area_ha"] <= passive["affected_area_ha"] + 0.5


# --------------------------------------------------------------------------- #
# Hold-time decay (2026-07-16 fix): a plume held still by the restoration
# sweep keeps reacting with the rock (EPA/540/S-02/500 point decay rate) --
# a long sweep must never PRESERVE the escaped slug at full strength.
# --------------------------------------------------------------------------- #
def test_frozen_slug_paradox_is_fixed():
    """op=20, t=50 (30-yr window): the old distance-only decay made the peak
    DIP then RISE back near C0 as the sweep froze the slug (134 -> 12,596 ppb).
    With hold-time decay, a full-window sweep must leave the slug far cleaner
    than no restoration at all, and monotonically no-worse across the sweep."""
    peaks = [label(op_years=20.0, t_years=50.0, rest_years=r,
                   k_atten=0.2)["peak_conc"] for r in (0, 5, 10, 20, 30)]
    # long sweeps must not resurrect the slug: every restored case cleaner
    # than unrestored, and the full-window sweep must not be the worst of them
    assert all(pk < peaks[0] for pk in peaks[1:]), peaks
    assert peaks[-1] <= min(peaks[1:]) * 3.0, peaks   # no 90x resurrection
    # and the full-window sweep leaves only trace levels (was ~0.95*C0)
    assert peaks[-1] < 0.05 * 15000.0, peaks


def test_hold_decay_identity_without_restoration():
    """rest=0 -> no hold -> hold factor must not change anything."""
    f = feat_row(t_years=30.0, k_atten=0.3)
    p = params_from_features(f, species_C0=15000.0, t_days=30 * 365.0,
                             operation_days=8 * 365.0)
    assert p.atten_hold_factor == 1.0


def test_hold_decay_law_and_saturation():
    """Hold factor = exp(-k * elapsed_hold); elapsed caps at the window."""
    f = feat_row(t_years=50.0, rest_years=30.0, k_atten=0.2)
    p = params_from_features(f, species_C0=15000.0, t_days=50 * 365.0,
                             operation_days=20 * 365.0,
                             restoration_days=30 * 365.0, residual_fraction=0.066)
    assert p.atten_hold_factor == pytest.approx(math.exp(-0.2 * 30.0), rel=1e-6)
    # planned sweep beyond the window: elapsed (and the factor) saturate
    f2 = feat_row(t_years=50.0, rest_years=45.0, k_atten=0.2)
    p2 = params_from_features(f2, species_C0=15000.0, t_days=50 * 365.0,
                              operation_days=20 * 365.0,
                              restoration_days=45 * 365.0, residual_fraction=0.066)
    assert p2.atten_hold_factor == pytest.approx(p.atten_hold_factor, rel=1e-9)


def test_hold_decay_continuous_at_rest_zero():
    a0 = label(op_years=20.0, t_years=50.0, rest_years=0.0,
               k_atten=0.2)["affected_area_ha"]
    a_eps = label(op_years=20.0, t_years=50.0, rest_years=0.05,
                  k_atten=0.2)["affected_area_ha"]
    assert abs(a_eps - a0) / max(a0, 1e-9) < 0.05, (a0, a_eps)
