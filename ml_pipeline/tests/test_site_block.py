"""
2026-09-25 -- the measured context and the front series behind the 3-D site
block (data_prep/terrain.py, dashboard/site_block.py, vertical_path.front_series).

Pinned: the terrain is the committed DEM excerpt and says so outside it; the
wells are the CGWB stations actually inside the block; and the animated fronts
arrive exactly when the vertical headline says they do -- an animation that
disagreed with the number beside it would be worse than none.
"""
from __future__ import annotations

import base64
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ml_pipeline.dashboard.server import app
from ml_pipeline.data_prep.terrain import TERRAIN_NPZ, elevation_at, terrain_at

client = TestClient(app)
JADUGUDA = (86.347, 22.652)
RANCHI = (85.33, 23.36)          # outside the uranium belt


def test_the_terrain_artifact_is_committed_and_covers_the_deposits():
    assert TERRAIN_NPZ.exists(), "belt_terrain.npz must be committed -- the DEM is not deployed"
    for lon, lat in (JADUGUDA, (86.186, 22.729), (86.491, 22.470)):   # Jaduguda, Turamdih, Bagjata
        t = terrain_at(lon, lat, 1.5)
        assert t is not None
        z = t["elev_m"]
        assert 30 < z.shape[0] < 70 and 30 < z.shape[1] < 70     # ~62 m cells over 3 km
        assert 0 < float(z.min()) and float(z.max()) < 1000       # Chotanagpur plateau range


def test_outside_the_belt_there_is_no_terrain_and_no_guess():
    assert terrain_at(*RANCHI, 1.5) is None
    assert elevation_at(*RANCHI) is None


def test_elevation_is_the_bilinear_value_of_the_grid():
    t = terrain_at(*JADUGUDA, 0.5)
    # the first cell centre must return its own stored value
    z0 = elevation_at(t["lon_first"], t["lat_first"])
    assert z0 == pytest.approx(float(t["elev_m"][0, 0]), abs=1e-6)


def test_site_block_serves_terrain_wells_rivers_and_layers():
    r = client.get("/api/site_block", params={"lon": JADUGUDA[0], "lat": JADUGUDA[1],
                                              "half_km": 3.0})
    assert r.status_code == 200
    b = r.json()
    t = b["terrain"]
    z = np.frombuffer(base64.b64decode(t["elev_m"]), dtype="<i2")
    assert z.size == t["nx"] * t["ny"]
    assert b["ground_m"] == pytest.approx(elevation_at(*JADUGUDA), abs=0.1)
    (s, w), (n, e) = b["bounds"]
    for well in b["wells"]:                       # only stations actually inside
        assert w <= well["lon"] <= e and s <= well["lat"] <= n
    assert b["nearest_well"]["km"] >= 0
    assert b["layers"]["layer1_base_m"] > 0
    assert b["layers"]["fracture_max_m"] == pytest.approx(258.0)   # E. Singhbhum profile


def test_site_block_outside_the_belt_is_drawn_flat_and_says_so():
    b = client.get("/api/site_block", params={"lon": RANCHI[0], "lat": RANCHI[1]}).json()
    assert b["terrain"] is None and b["terrain_note"]


def test_site_block_refuses_outside_jharkhand():
    r = client.get("/api/site_block", params={"lon": 80.0, "lat": 20.0})
    assert r.status_code == 422


def test_the_animated_fronts_arrive_when_the_headline_says():
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    r = api_predict(PredictRequest(lon=JADUGUDA[0], lat=JADUGUDA[1], mode="analytical",
                                   time_years=20, species="uranium_ppb"))
    v = r["vertical"]
    fs = v["front_series"]
    years = np.array(fs["years"])
    dz = fs["separation_m"]

    def arrival(sp):
        z = np.array(fs["fronts_m_above_ore_top"][sp])
        k = int(np.argmax(z >= dz - 1e-6))
        return None if z[k] < dz - 1e-6 else years[k]

    step = years[1] - years[0]
    tds = {i["species"]: i for i in v["indicators"]}["tds_mg_l"]
    assert arrival("tds_mg_l") == pytest.approx(tds["years_to_breakthrough"], abs=step + 0.1)
    assert arrival("water") == pytest.approx(v["water_arrival_years"], abs=step + 0.1)
    # uranium arrives in centuries, so it must still be low in the rock at 50 yr
    assert arrival("uranium_ppb") is None
    assert fs["fronts_m_above_ore_top"]["uranium_ppb"][-1] < 0.25 * dz
    # every front is non-decreasing and capped at the separation
    for z in fs["fronts_m_above_ore_top"].values():
        assert np.all(np.diff(z) >= -1e-9) and max(z) <= dz + 1e-9


def test_metrics_only_calls_carry_no_front_series():
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    r = api_predict(PredictRequest(lon=JADUGUDA[0], lat=JADUGUDA[1], mode="analytical",
                                   time_years=20, display_extras=False))
    assert "front_series" not in r["vertical"]
    assert math.isfinite(r["vertical"]["years_to_vertical_breakthrough"])
