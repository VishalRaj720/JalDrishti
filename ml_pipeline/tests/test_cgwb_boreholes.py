"""
2026-09-25 -- CGWB exploratory boreholes of the Singhbhum belt
(data_prep/cgwb_boreholes.py, the two Datasets/cgwb_exploratory_wells_* CSVs)
and their place in the 3-D site block.

Pinned: the transcription is internally consistent (zones inside the hole,
casing above the bottom, positions in the belt districts), the facts the
LIMITATIONS text quotes are the ones on file, and the block shows a borehole
only where one actually is.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ml_pipeline.dashboard.server import app
from ml_pipeline.data_prep.cgwb_boreholes import (
    load_boreholes, nearest_boreholes, placed)

client = TestClient(app)
JADUGUDA = (86.347, 22.652)
TURAMDIH = (86.186, 22.729)


def _by_id():
    return {w["well_id"]: w for w in load_boreholes()}


def test_every_row_is_sourced_and_internally_consistent():
    ws = load_boreholes()
    assert len(ws) >= 40
    assert len({w["well_id"] for w in ws}) == len(ws)
    for w in ws:
        assert w["sources"], w["well_id"]
        d, c = w["depth_m"], w["casing_m"]
        if d is not None and c is not None:
            assert c < d, w["well_id"]
        for z in w["zones"]:
            assert z["top_m"] <= z["bottom_m"], w["well_id"]
            if d is not None:
                assert z["bottom_m"] <= d, w["well_id"]
        if w["transmissivity_m2day"] is not None:
            assert 0 < w["transmissivity_m2day"] < 1000


def test_positions_are_in_the_belt_districts_or_left_out():
    for w in placed():
        assert 85.2 < w["lon"] < 86.9 and 22.2 < w["lat"] < 23.1, w["well_id"]
    unplaced = {w["well_id"] for w in load_boreholes() if w["lon"] is None}
    # the misprinted AMD position and the four tests with no published position
    assert {"amd_jamshedpur_ew", "mahulbera_ew", "kandra_ew", "uliyan_ew"} <= unplaced


def test_the_facts_the_limitations_text_quotes():
    b = _by_id()
    k = b["kudada_ew"]
    assert k["flowing"] and k["transmissivity_m2day"] == 19 and k["swl_mbgl"] == 2.42
    # the three transmissivities the D5 shear-zone value was taken from are
    # CGWB's TERTIARY-sediment wells, far east of the deposits
    for wid, t in (("manusmuria_ew", 209), ("baharagora_ew", 570.8), ("kalapathar_ew", 207)):
        assert b[wid]["formation"] == "Tertiary" and b[wid]["transmissivity_m2day"] == t
        assert b[wid]["lon"] > 86.7
    # hard-rock tests in the same tables
    hard = [w["transmissivity_m2day"] for w in load_boreholes()
            if w["transmissivity_m2day"] is not None and w["formation"] != "Tertiary"]
    assert max(hard) <= 101 and min(hard) >= 2
    assert b["hesel_ew2"]["zones"][-1]["bottom_m"] == 232    # deepest fracture on file


def test_the_turamdih_block_holds_kudada_and_jaduguda_says_what_is_nearest():
    t = client.get("/api/site_block", params={"lon": TURAMDIH[0], "lat": TURAMDIH[1],
                                              "half_km": 3.0}).json()
    ids = {b["well_id"] for b in t["boreholes"]}
    assert "kudada_ew" in ids
    kud = next(b for b in t["boreholes"] if b["well_id"] == "kudada_ew")
    assert kud["ground_m"] is not None and kud["zones"]
    (s, w), (n, e) = t["bounds"]
    for bh in t["boreholes"]:
        assert w <= bh["lon"] <= e and s <= bh["lat"] <= n

    j = client.get("/api/site_block", params={"lon": JADUGUDA[0], "lat": JADUGUDA[1],
                                              "half_km": 1.5}).json()
    assert j["boreholes"] == []
    near = j["nearest_boreholes"]
    assert near and near[0]["km"] < 10
    assert all(a["km"] <= b["km"] for a, b in zip(near, near[1:]))
    assert "P3" in j["boreholes_source"]


def test_nearest_excludes_what_is_already_inside():
    inside = {"kudada_ew"}
    near = nearest_boreholes(*TURAMDIH, n=5, exclude=inside)
    assert "kudada_ew" not in {r["well_id"] for r in near}
    assert all(0 <= r["bearing_deg"] < 360 for r in near)
