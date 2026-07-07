"""Module 5A -- 2.5D vertical stratification + shallow-aquifer impact screening."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ml_pipeline.physics.transport import (
    vertical_attenuation, shallow_impact_screening,
)
from ml_pipeline.dashboard.server import app
from ml_pipeline.config import parameters as P

client = TestClient(app)
JADUGUDA = (86.347, 22.652)


def test_vertical_attenuation_decays_with_height():
    # deep above the source band -> almost nothing gets up by dispersion
    near = vertical_attenuation(z_m=5.0, H_m=20.0, alpha_V=1.0, x_m=500.0)
    far = vertical_attenuation(z_m=200.0, H_m=20.0, alpha_V=1.0, x_m=500.0)
    assert 0.0 <= far < near <= 1.0
    assert far < 1e-3            # a 200 m confined separation is effectively sealed


def _vert(**over):
    base = dict(C0=15000.0, background=2.0, threshold=P.EXCURSION_THRESHOLDS["uranium_ppb"],
                Xc_m=400.0, source_width_m=300.0, alpha_L=25.0, alpha_V=0.6,
                ore_depth_m=150.0, ore_thickness_m=20.0, layer1_base_m=30.0,
                K_m_day=1.0, phi_confining=0.01, Kv_Kh_ratio=0.01,
                upward_gradient=0.005, t_days=3650.0, wellbore_failure_prob=0.05)
    base.update(over)
    return shallow_impact_screening(**base)


def test_deeper_ore_is_safer():
    shallow = _vert(ore_depth_m=80.0)["shallow_impact_probability"]
    deep = _vert(ore_depth_m=500.0)["shallow_impact_probability"]
    assert shallow > deep                       # monotone: depth protects Layer 1


def test_thicker_ore_shortens_barrier_and_raises_risk():
    # a thicker ore body has its TOP nearer the surface -> shorter confining
    # barrier -> higher advective risk (2026-07-06 fix; previously inert)
    thin = _vert(ore_depth_m=250.0, ore_thickness_m=2.0)
    thick = _vert(ore_depth_m=250.0, ore_thickness_m=100.0)
    assert thick["separation_m"] < thin["separation_m"]
    assert thick["shallow_impact_probability"] > thin["shallow_impact_probability"]


def test_sub_threshold_source_is_contained():
    # a trace source (below the incremental limit) cannot breach via advection
    v = _vert(C0=5.0)
    assert v["pathways"]["advective_leakage"] == 0.0
    assert v["pathways"]["wellbore"] == 0.0
    assert v["risk_band"] == "contained"


def test_higher_anisotropy_raises_risk():
    low = _vert(Kv_Kh_ratio=0.005)["shallow_impact_probability"]
    high = _vert(Kv_Kh_ratio=0.10)["shallow_impact_probability"]
    assert high > low


def test_predict_returns_vertical_block_without_changing_horizontal():
    a = client.post("/api/predict", json={"lon": JADUGUDA[0], "lat": JADUGUDA[1],
                                          "ore_depth_m": 150}).json()
    b = client.post("/api/predict", json={"lon": JADUGUDA[0], "lat": JADUGUDA[1],
                                          "ore_depth_m": 400}).json()
    assert "vertical" in a and "shallow_impact_probability" in a["vertical"]
    # depth must NOT alter the horizontal (deep-layer) metrics
    assert a["metrics"]["analytical"]["area_ha"] == b["metrics"]["analytical"]["area_ha"]
    assert a["metrics"]["analytical"]["migration_m"] == b["metrics"]["analytical"]["migration_m"]
    # but it MUST alter the vertical screening
    assert a["vertical"]["shallow_impact_probability"] != b["vertical"]["shallow_impact_probability"]
