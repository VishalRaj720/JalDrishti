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
    f = feat_row(k_atten=0.2)
    assert f["u_attenuation_k"] == pytest.approx(0.2)
    vc = f["contaminant_velocity_vc"]
    assert f["_atten_per_m"] == pytest.approx((0.2 / 365.0) / vc)
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
def test_plume_reaches_equilibrium_extent():
    """With redox trapping the migration distance saturates: the late-time
    growth rate collapses vs the early rate (was ~linear forever)."""
    m10 = label(t_years=10.0, k_atten=0.2)["max_migration_distance_m"]
    m30 = label(t_years=30.0, k_atten=0.2)["max_migration_distance_m"]
    m50 = label(t_years=50.0, k_atten=0.2)["max_migration_distance_m"]
    early = (m30 - m10) / 20.0            # m/yr
    late = (m50 - m30) / 20.0
    assert late < 0.35 * max(early, 1e-9), (m10, m30, m50)
    # and against the k=0 counterfactual the 50-yr plume is much shorter
    m50_free = label(t_years=50.0, k_atten=0.0)["max_migration_distance_m"]
    assert m50 < 0.7 * m50_free, (m50, m50_free)


# --------------------------------------------------------------------------- #
# B -- natural post-closure source flush (scenario 2's endgame)
# --------------------------------------------------------------------------- #
def test_natural_flush_cleans_source_zone_without_restoration():
    """Post-closure, the near-source cell must decay with the 30-yr half-life
    flush even with NO restoration sweep (was frozen at C0 forever)."""
    f = feat_row(t_years=30.0, k_atten=0.0)
    p = params_from_features(f, species_C0=15000.0, t_days=30 * 365.0,
                             operation_days=8 * 365.0)
    c_near = concentration_point(10.0, 0.0, p)
    flush = 0.5 ** ((30.0 - 8.0) / P.DISC_FLUSH_HALFLIFE_YEARS)
    # the wave wipes the wake toward C_res = flush*C0 (within a few %)
    assert c_near == pytest.approx(15000.0 * flush, rel=0.05)
    # during operations: untouched (flush factor = 1, no wave)
    f_op = feat_row(t_years=5.0, k_atten=0.0)
    p_op = params_from_features(f_op, species_C0=15000.0, t_days=5 * 365.0,
                                operation_days=8 * 365.0)
    assert concentration_point(10.0, 0.0, p_op) == pytest.approx(15000.0, rel=0.02)


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
