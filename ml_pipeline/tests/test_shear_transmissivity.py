"""D5 -- Singhbhum shear-zone transmissivity: the measured-maximum baseline.

2026-09-26: the value is Kudada EW's pumping test (T = 19 m2/day, CGWB), not the
retired 370 m2/day from Tertiary sediments 51-58 km away (LIMITATIONS 1j/1k).
The reference-depth K is derived so the engine's own K(z) law, integrated over
the interval the test measured, gives back the measured T
(resolve.shear_zone_reference)."""
from __future__ import annotations

import pytest

from ml_pipeline.dashboard.resolve import resolve_inputs, shear_zone_reference
from ml_pipeline.config import parameters as P

_K_SHEAR = shear_zone_reference()["K_reference_m_day"]
JADUGUDA = dict(lon=86.347, lat=22.652, species="uranium_ppb")   # fractured deposit


def test_shear_zone_applies_at_fractured_deposit():
    """The shear-zone K is the starting point and the SERVED K is that value
    after the depth decay K(z) (Phase-1 fix 3.3). Both are checked."""
    inp, h = resolve_inputs(dict(**JADUGUDA))
    assert h["shear_zone"] is not None
    assert h["shear_zone"]["K_m_day"] == pytest.approx(_K_SHEAR, rel=1e-3)
    assert h["shear_zone"]["T_m2day"] == P.SHEAR_ZONE_T_M2DAY
    assert h["shear_zone"]["source_well"] == "kudada_ew"
    assert inp["thickness_m"] == pytest.approx(P.SHEAR_ZONE_THICKNESS_M)
    # 2026-09-26: the MEASURED shear zone is TIGHTER than the generic schist
    # polygon (K_ref ~0.23 vs 1.12). The old assertion "more transmissive than
    # the polygon" encoded the retired Tertiary value; the correction is kept
    # because it is measured here, whichever way it points.
    assert _K_SHEAR < h["shear_zone"]["polygon_K_m_day"]
    kd = h["k_depth"]
    assert kd is not None
    assert kd["K_shallow_m_day"] == pytest.approx(_K_SHEAR, rel=1e-3)
    assert inp["K_m_day"] == pytest.approx(_K_SHEAR * kd["decay_factor"], rel=1e-3)
    assert inp["K_m_day"] < _K_SHEAR          # depth makes it tighter


def test_reference_K_reproduces_the_measured_T_over_the_tested_interval():
    """K_ref integrated with the engine's K(z) law over Kudada's open hole must
    give back T = 19 m2/day -- the conversion's whole point."""
    import numpy as np
    szr = shear_zone_reference()
    top, bottom = szr["tested_interval_m"]
    zs = np.linspace(top, bottom, 4001)
    fz = np.array([P.depth_decay_factor(z, szr["fracture_base_at_test_m"]) for z in zs])
    T = szr["K_reference_m_day"] * float(np.sum(0.5 * (fz[1:] + fz[:-1]) * np.diff(zs)))
    assert T == pytest.approx(P.SHEAR_ZONE_T_M2DAY, rel=1e-3)
    # and it is NOT the naive T / b, which would decay the tested interval twice
    assert szr["K_reference_m_day"] > P.SHEAR_ZONE_T_M2DAY / P.SHEAR_ZONE_THICKNESS_M


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


def test_measured_shear_zone_shrinks_the_ore_belt_plume():
    # INVERTED 2026-09-26. With the retired T = 370 the shear zone was MORE
    # transmissive than the schist polygon and enlarged the plume. The measured
    # value (Kudada, 19) is less transmissive, so the same comparison now goes
    # the other way -- which is the point of grounding it: the direction of the
    # correction is the data's, not the model's. Compare against an explicit
    # polygon-K run at the same location.
    from ml_pipeline.ml.predict import predict_analytical
    base = dict(regime="fractured", gradient_i=0.003, phi_mobile=0.008,
                n_total=0.03, grain_density=2750.0, kd_L_kg=1.0, beta=8.0,
                Q_in_m3_day=2500.0, bleed_fraction=0.02, operation_years=8.0,
                wellfield_width_m=300.0, source_conc_C0=13000.0,
                background_conc_Cb=2.0, species="uranium_ppb", time_years=10.0)
    shear = predict_analytical(**base, K_m_day=_K_SHEAR, thickness_m=P.SHEAR_ZONE_THICKNESS_M)
    poly = predict_analytical(**base, K_m_day=1.12, thickness_m=37.5)
    # ASSERT ON TRAVEL, NOT AREA (corrected 2026-08-05, independent validation).
    # `area_ha` is 76-97% leach-zone DISC, and the disc shrinks with aquifer
    # thickness (thicker b -> larger swept volume -> fewer bulk volumes -> less
    # tanh source widening), so area tests the wellfield footprint, not
    # transport. Travel follows seepage velocity K*i/phi: the measured shear
    # zone's K is ~5x below the polygon's, so its front is shorter.
    assert shear["migration_m"]["p50"] < poly["migration_m"]["p50"]
