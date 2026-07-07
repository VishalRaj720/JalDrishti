"""Module 2 -- 3-tier ore masking + ML-bypass for non-ore uranium."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ml_pipeline.data_prep.ore_loader import ore_zone_at
from ml_pipeline.dashboard.server import app

client = TestClient(app)

JADUGUDA = (86.347, 22.652)     # inside a surveyed deposit
MID_BELT = (86.25, 22.63)       # inside the Singhbhum envelope, outside deposits
RANCHI = (85.33, 23.36)         # clean, ~113 km from nearest deposit


def test_zone_classification():
    assert ore_zone_at(*JADUGUDA)["zone"] == "deposit"
    assert ore_zone_at(*MID_BELT)["zone"] == "belt"
    assert ore_zone_at(*RANCHI)["zone"] == "none"


def _predict(lon, lat, species="uranium_ppb"):
    return client.post("/api/predict",
                       json={"lon": lon, "lat": lat, "species": species}).json()


def test_deposit_uranium_full_source_and_ml():
    b = _predict(*JADUGUDA)
    assert b["ore_zone"]["zone"] == "deposit"
    assert b["notice"] is None
    assert b["hydro"]["source_conc_C0"] > 1000    # full Texas-derived source


def test_belt_uranium_reduced_source():
    b = _predict(*MID_BELT)
    dep = _predict(*JADUGUDA)
    assert b["ore_zone"]["zone"] == "belt"
    assert "Prospective Belt" in b["notice"]
    # belt source is a fraction of the deposit's full source term
    assert b["hydro"]["source_conc_C0"] < dep["hydro"]["source_conc_C0"]


def test_non_ore_uranium_suppressed_zero_plume():
    b = _predict(*RANCHI)
    assert b["ore_zone"]["zone"] == "none"
    assert b["hydro"]["u_suppressed"] is True
    assert b["ml_status"].startswith("suppressed")
    assert b["metrics"]["ml"] is None
    assert b["hydro"]["source_conc_C0"] <= 20      # trace only
    assert b["metrics"]["analytical"]["area_ha"] == 0.0   # no uranium plume


def test_non_ore_sulfate_still_simulated():
    b = _predict(*RANCHI, species="sulfate_mg_l")
    # lixiviant reagents perturb non-radiological chemistry anywhere fluid is injected
    assert b["notice"] is None
    assert b["hydro"]["u_suppressed"] is False
    assert b["hydro"]["source_conc_C0"] > 100
