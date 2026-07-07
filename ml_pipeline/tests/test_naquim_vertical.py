"""Phase-2 D3 -- per-district vertical model (district PIP + naquim_vertical.csv)."""
from __future__ import annotations

import pytest

from ml_pipeline.data_prep.naquim_vertical import (
    district_at, vertical_params_at, load_naquim_vertical, _districts,
    DEFAULT_LAYER1_BASE_M,
)


def test_district_resolution():
    assert district_at(86.347, 22.652) == "East Singhbum"    # Jaduguda (ore belt)
    assert district_at(85.33, 23.36) == "Ranchi"
    assert district_at(86.43, 23.80) == "Dhanbad"


def test_all_24_districts_have_a_row():
    # every district polygon must have a curated row -> no silent state-wide default
    table = load_naquim_vertical()
    for name, _ in _districts():
        assert name.lower() in table, f"{name} missing from naquim_vertical.csv"


def test_layer1_base_is_float_in_range():
    for lon, lat in [(86.347, 22.652), (85.33, 23.36), (83.8, 24.15), (86.7, 24.48)]:
        v = vertical_params_at(lon, lat)
        assert isinstance(v["layer1_base_m"], float)
        assert 5.0 <= v["layer1_base_m"] <= 40.0        # hard-rock weathered base


def test_fracture_range_ordered():
    table = load_naquim_vertical()
    for key, row in table.items():
        fmin, fmax = float(row["fracture_min_m"]), float(row["fracture_max_m"])
        assert 0 < fmin < fmax, f"{key}: fracture range {fmin}-{fmax} not ordered"


def test_ore_belt_districts_are_confined():
    for lon, lat in [(86.347, 22.652), (85.6, 22.4)]:      # East / West Singhbhum
        assert vertical_params_at(lon, lat)["aq2_confined"] == "yes"


def test_belt_base_below_statewide_default():
    # the whole hard-rock belt weathers shallower than the old flat 30 m default
    v = vertical_params_at(86.347, 22.652)
    assert v["layer1_base_m"] < DEFAULT_LAYER1_BASE_M


def test_report_and_estimate_confidence_flags():
    table = load_naquim_vertical()
    confs = {r["confidence"] for r in table.values()}
    assert "high" in confs and "regional_estimate" in confs
