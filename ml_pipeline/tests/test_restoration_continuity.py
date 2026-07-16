"""
Restoration continuity regression tests (QA sweep 2026-07-13, findings F-1/F-2/F-3).
====================================================================================
F-1: the restoration clean-up must be credited for the ELAPSED sweep and must be
continuous across every phase boundary -- the old planned-sweep credit plus the
`Xc_clean > 0` wave gate snapped the upstream source-zone box between C_res and
full C0 at rest = t - op (area stepped ~3x in a 0.02-yr increment, then froze).

Run:  python -m pytest ml_pipeline/tests/test_restoration_continuity.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.data_prep.feature_engineering import build_feature_row
from ml_pipeline.physics.transport import (
    simulate_plume, restoration_source_fraction, realized_residual,
)

U_THR = P.EXCURSION_THRESHOLDS["uranium_ppb"]

FRACTURED = dict(regime="fractured", K_m_day=1.12, gradient_i=0.006,
                 phi_mobile=0.008, n_total=0.03, grain_density=2750.0,
                 kd_L_kg=1.0, beta=8.0, thickness_m=37.5)
POROUS = dict(regime="porous", K_m_day=2.345, gradient_i=0.006,
              phi_mobile=0.08, n_total=0.30, grain_density=2650.0,
              kd_L_kg=2.5, beta=0.0, thickness_m=85.0)


def label(hg: dict, *, op_years=5.0, t_years=15.0, rest_years=0.0,
          residual=0.066, grid_n=140) -> dict:
    feat = build_feature_row(
        domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
        operation_days=op_years * 365.0, wellfield_width_m=300.0,
        source_conc_C0=15000.0, background_conc_Cb=2.0,
        eval_time_days=t_years * 365.0, restoration_days=rest_years * 365.0,
        residual_fraction=residual, **hg)
    res = simulate_plume(feat, species_C0=15000.0, background=2.0, threshold=U_THR,
                         t_days=t_years * 365.0, operation_days=op_years * 365.0,
                         restoration_days=rest_years * 365.0,
                         residual_fraction=residual, grid_n=grid_n,
                         compliance_x=P.COMPLIANCE_BUFFER_M)
    return res.metrics


# --------------------------------------------------------------------------- #
# The elapsed-sweep law itself
# --------------------------------------------------------------------------- #
def test_source_fraction_elapsed_credit():
    ref, op, rest = 0.066, 5 * 365.0, 8 * 365.0
    # before the sweep starts: no credit
    assert restoration_source_fraction(ref, 3 * 365.0, op, rest) == 1.0
    assert restoration_source_fraction(ref, op, op, rest) == 1.0
    # mid-sweep: credited for the elapsed years only
    mid = restoration_source_fraction(ref, op + 2 * 365.0, op, rest)
    assert mid == pytest.approx(realized_residual(ref, 2 * 365.0))
    assert mid < 1.0
    # complete: the full realized endpoint, constant thereafter
    done = restoration_source_fraction(ref, op + rest, op, rest)
    assert done == pytest.approx(realized_residual(ref, rest))
    assert restoration_source_fraction(ref, op + rest + 3650, op, rest) == done
    # no sweep: sentinel
    assert restoration_source_fraction(ref, 1e5, op, 0.0) == 1.0


# --------------------------------------------------------------------------- #
# F-1: no step across the completion boundary rest = t - op
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("hg", [FRACTURED, POROUS], ids=["fractured", "porous"])
def test_no_step_at_completion_boundary(hg):
    """Fine sweep of rest across t-op=10: consecutive area steps must stay a
    small fraction of the level (the bug was a 3x jump in one 0.02-yr step)."""
    rests = np.arange(9.5, 10.51, 0.1)
    areas = [label(hg, rest_years=r)["affected_area_ha"] for r in rests]
    for a0, a1 in zip(areas, areas[1:]):
        base = max(a0, a1, 0.5)
        assert abs(a1 - a0) / base < 0.10, (rests.tolist(), areas)


@pytest.mark.parametrize("hg", [FRACTURED, POROUS], ids=["fractured", "porous"])
def test_area_monotone_nonincreasing_in_restoration(hg):
    """More sweep never makes the aquifer dirtier (weakly monotone; the bug
    made area JUMP UP as rest crossed t-op)."""
    rests = [0.0, 0.5, 1, 2, 4, 6, 8, 10, 12, 14]
    areas = [label(hg, rest_years=r)["affected_area_ha"] for r in rests]
    for a0, a1 in zip(areas, areas[1:]):
        assert a1 <= a0 + max(0.03 * a0, 0.3), (rests, areas)


def test_rest_to_zero_continuity():
    """rest -> 0+ must converge to the no-restoration state (feature AND field)."""
    a0 = label(FRACTURED, rest_years=0.0)["affected_area_ha"]
    a_eps = label(FRACTURED, rest_years=0.05)["affected_area_ha"]
    assert abs(a_eps - a0) / max(a0, 1e-9) < 0.05, (a0, a_eps)


# --------------------------------------------------------------------------- #
# F-1: mid-sweep behaviour -- credited, and causal (planned future irrelevant)
# --------------------------------------------------------------------------- #
def test_midsweep_is_credited():
    """A sweep that has run for years must show clean-up even if unfinished
    (the bug held the source-zone box at full C0 until completion). The
    invariant is the SOURCE ZONE, not the global peak: with the natural
    post-closure flush (real-ISR upgrade) the no-restoration baseline also
    cleans up while its escaped slug drifts and dilutes, whereas mid-sweep the
    held slug legitimately keeps a high local max near the wellfield."""
    from ml_pipeline.data_prep.feature_engineering import build_feature_row
    from ml_pipeline.physics.transport import (params_from_features,
                                               concentration_point)

    def src_cell(rest_years):
        feat = build_feature_row(
            domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
            operation_days=5 * 365.0, wellfield_width_m=300.0,
            source_conc_C0=15000.0, background_conc_Cb=2.0,
            eval_time_days=15 * 365.0, restoration_days=rest_years * 365.0,
            residual_fraction=0.066, **FRACTURED)
        p = params_from_features(feat, species_C0=15000.0, t_days=15 * 365.0,
                                 operation_days=5 * 365.0,
                                 restoration_days=rest_years * 365.0,
                                 residual_fraction=0.066)
        return concentration_point(-50.0, 0.0, p, include_disc=True)

    dirty = label(FRACTURED, rest_years=0.0)
    mid = label(FRACTURED, rest_years=12.0)     # still running at t=15 (op=5)
    assert mid["affected_area_ha"] < dirty["affected_area_ha"] * 0.9
    # 10 elapsed sweep years must have drawn the source zone down far below
    # what passive flushing alone achieves
    assert src_cell(12.0) < 0.25 * src_cell(0.0), (src_cell(12.0), src_cell(0.0))


def test_midsweep_causality():
    """Two still-running sweeps with the same elapsed time are identical at
    eval time -- the planned future length cannot affect the present."""
    m12 = label(FRACTURED, rest_years=12.0)     # elapsed = min(10, 12) = 10
    m30 = label(FRACTURED, rest_years=30.0)     # elapsed = min(10, 30) = 10
    assert m12["affected_area_ha"] == pytest.approx(m30["affected_area_ha"])
    assert m12["peak_conc"] == pytest.approx(m30["peak_conc"])


# --------------------------------------------------------------------------- #
# F-2: the model feature is the realized fraction (continuous, elapsed-aware)
# --------------------------------------------------------------------------- #
def test_residual_feature_is_realized_and_continuous():
    def feat_row(rest_years, t_years=15.0, op_years=5.0, residual=0.066):
        return build_feature_row(
            domain_is_texas=False, Q_in_m3_day=2500.0, bleed_fraction=0.02,
            operation_days=op_years * 365.0, wellfield_width_m=300.0,
            source_conc_C0=15000.0, background_conc_Cb=2.0,
            eval_time_days=t_years * 365.0, restoration_days=rest_years * 365.0,
            residual_fraction=residual, **FRACTURED)
    assert feat_row(0.0)["residual_fraction"] == 1.0
    assert feat_row(0.05)["residual_fraction"] == pytest.approx(1.0, abs=0.05)
    # completed sweep: the realized endpoint for that duration
    assert feat_row(4.0)["residual_fraction"] == pytest.approx(
        realized_residual(0.066, 4 * 365.0))
    # mid-sweep: elapsed-credited, planned future irrelevant
    assert feat_row(12.0)["residual_fraction"] == pytest.approx(
        feat_row(30.0)["residual_fraction"])
    # the physics endpoint survives untouched for the solver
    assert feat_row(4.0)["_residual_endpoint"] == 0.066
