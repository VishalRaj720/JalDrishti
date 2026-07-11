"""Stage-B2 -- perennial-river receptor context (loads the committed .npz/geojson)."""
from __future__ import annotations

import pytest

from ml_pipeline.data_prep.rivers import (
    river_distance_at, load_river_field, RIVER_NPZ, PERENNIAL_DIS_CMS,
)

pytestmark = pytest.mark.skipif(
    not RIVER_NPZ.exists(),
    reason="river_field.npz not built (run -m ml_pipeline.data_prep.rivers)")


def test_distance_is_positive_and_sane():
    d = river_distance_at(86.347, 22.652)                 # Jaduguda
    assert d is not None and 0.0 <= d < 60.0


def test_known_river_towns_are_close():
    # each of these sits on / beside a perennial river -> distance must be small
    assert river_distance_at(86.20, 22.80) < 4.0          # Subarnarekha @ Jamshedpur
    assert river_distance_at(85.99, 23.78) < 5.0          # Damodar @ Bermo
    assert river_distance_at(87.64, 25.25) < 5.0          # Ganga @ Sahibganj


def test_upland_divide_is_farther_than_river_towns():
    # the Ranchi plateau is a water DIVIDE -- it must be farther from a perennial
    # river than the river towns (the exact ordering the DEM D8 network inverted)
    ranchi = river_distance_at(85.33, 23.36)
    for lon, lat in [(86.20, 22.80), (85.99, 23.78), (87.64, 25.25)]:
        assert ranchi > river_distance_at(lon, lat)


def test_field_grid_matches_flow_field():
    # B2 shares the 5 km grid so one pin resolves flow_at + strike_at + rivers
    from ml_pipeline.data_prep.flow_field import load_flow_field
    rf, ff = load_river_field(), load_flow_field()
    assert rf["distance_km"].shape == ff["gradient_i"].shape


def test_out_of_grid_clamped_not_crashed():
    assert river_distance_at(200.0, 200.0) is not None     # clamps to grid edge


def test_perennial_threshold_is_discharge_based():
    assert PERENNIAL_DIS_CMS >= 0.5     # >= ~1 cumec = genuine year-round stream
