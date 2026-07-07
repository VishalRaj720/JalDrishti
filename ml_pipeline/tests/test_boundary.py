"""Module 1 -- hard geographic boundary + data-confidence telemetry."""
from __future__ import annotations

from fastapi.testclient import TestClient

from ml_pipeline.data_prep.boundary import in_jharkhand
from ml_pipeline.dashboard.server import app

client = TestClient(app)

# (name, lon, lat, inside?)
CASES = [
    ("Ranchi", 85.33, 23.36, True),
    ("Jaduguda ore belt", 86.35, 22.65, True),
    ("Dhanbad", 86.43, 23.80, True),
    ("Patna (Bihar)", 85.14, 25.61, False),
    ("Kolkata (WB)", 88.36, 22.57, False),
    ("Bay of Bengal", 87.0, 20.5, False),
    ("just across W border", 83.10, 23.60, False),
]


def test_point_in_polygon():
    for name, lon, lat, inside in CASES:
        assert in_jharkhand(lon, lat) is inside, f"{name} PIP wrong"


def test_border_pin_passes_via_tolerance():
    # a pin on the dissolved boundary must not be rejected (covers + tolerance)
    from ml_pipeline.data_prep.boundary import _boundary
    union, _ = _boundary()
    px, py = union.exterior.coords[0] if union.geom_type == "Polygon" \
        else list(union.geoms)[0].exterior.coords[0]
    assert in_jharkhand(px, py) is True


def test_api_pin_rejects_outside_with_422():
    r = client.get("/api/pin", params={"lon": 85.14, "lat": 25.61})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "OUTSIDE_JHARKHAND"


def test_api_predict_rejects_outside_with_422():
    r = client.post("/api/predict", json={"lon": 88.36, "lat": 22.57})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "OUTSIDE_JHARKHAND"


def test_api_pin_inside_returns_hydro_and_confidence():
    r = client.get("/api/pin", params={"lon": 85.33, "lat": 23.36})
    assert r.status_code == 200
    body = r.json()
    assert "data_confidence" in body
    assert body["data_confidence"]["level"] in {"ok", "low"}


def test_api_boundary_serves_geometry():
    r = client.get("/api/boundary")
    assert r.status_code == 200
    geom = r.json()
    assert geom["type"] in {"Polygon", "MultiPolygon"}
    assert geom["coordinates"]
