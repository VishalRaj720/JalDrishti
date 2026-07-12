"""D5 -- Singhbhum shear-zone transmissivity correction (serve-time, no retrain)."""
from __future__ import annotations

import pytest

from ml_pipeline.dashboard.resolve import resolve_inputs
from ml_pipeline.config import parameters as P

_K_SHEAR = P.SHEAR_ZONE_T_M2DAY / P.SHEAR_ZONE_THICKNESS_M
JADUGUDA = dict(lon=86.347, lat=22.652, species="uranium_ppb")   # fractured deposit


def test_shear_zone_applies_at_fractured_deposit():
    inp, h = resolve_inputs(dict(**JADUGUDA))
    assert h["shear_zone"] is not None
    assert inp["K_m_day"] == pytest.approx(_K_SHEAR, rel=1e-6)
    assert inp["thickness_m"] == pytest.approx(P.SHEAR_ZONE_THICKNESS_M)
    # the correction must make the aquifer MORE transmissive than the polygon
    assert _K_SHEAR > h["shear_zone"]["polygon_K_m_day"]


def test_shear_zone_off_the_belt_is_unchanged():
    inp, h = resolve_inputs(dict(lon=86.43, lat=23.80, species="uranium_ppb"))  # Dhanbad
    assert h["shear_zone"] is None
    assert inp["K_m_day"] != pytest.approx(_K_SHEAR)


def test_shear_zone_only_fractured():
    _, h = resolve_inputs(dict(regime="porous", **JADUGUDA))
    assert h["shear_zone"] is None      # shear zone is a fractured-aquifer property


def test_shear_zone_user_K_override_wins():
    inp, h = resolve_inputs(dict(K_m_day=1.5, **JADUGUDA))
    assert h["shear_zone"] is None
    assert inp["K_m_day"] == pytest.approx(1.5)


def test_shear_zone_enlarges_ore_belt_plume():
    # higher T -> lower containment -> larger plume than the same pin would give
    # with the (thin, low-K) schist polygon. Compare against an explicit polygon-K
    # run at the same location.
    from ml_pipeline.ml.predict import predict_analytical
    base = dict(regime="fractured", gradient_i=0.003, phi_mobile=0.008,
                n_total=0.03, grain_density=2750.0, kd_L_kg=1.0, beta=8.0,
                Q_in_m3_day=2500.0, bleed_fraction=0.02, operation_years=8.0,
                wellfield_width_m=300.0, source_conc_C0=13000.0,
                background_conc_Cb=2.0, species="uranium_ppb", time_years=10.0)
    shear = predict_analytical(**base, K_m_day=_K_SHEAR, thickness_m=P.SHEAR_ZONE_THICKNESS_M)
    poly = predict_analytical(**base, K_m_day=1.12, thickness_m=37.5)
    assert shear["area_ha"]["p50"] > poly["area_ha"]["p50"]
