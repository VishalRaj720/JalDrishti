"""Phase-2 D2 -- fracture-strike field (loads the committed .npz, no geojson needed)."""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.data_prep.strike_field import (
    load_strike_field, strike_at, anisotropy_from_variance, anisotropy_lambda,
    flux_azimuth, STRIKE_NPZ, ANISO_BASE, ANISO_V_MED, ANISO_CLIP,
)

pytestmark = pytest.mark.skipif(not STRIKE_NPZ.exists(),
                                reason="strike_field.npz not built (run -m ml_pipeline.data_prep.strike_field)")


def test_strike_at_ranges():
    s = strike_at(86.347, 22.652)                      # Jaduguda
    assert 0.0 <= s["mean_strike_deg"] < 180.0
    assert 0.0 <= s["circular_variance"] <= 1.0
    assert ANISO_CLIP[0] <= s["aniso_ratio"] <= ANISO_CLIP[1]
    assert s["dispersion"] in {"aligned", "intermediate", "dispersed"}


def test_resultant_is_bounded():
    sf = load_strike_field()
    R = np.hypot(sf["res_x"], sf["res_y"])[sf["in_jh"]]
    assert np.all(R <= 1.0 + 1e-9) and np.all(R >= -1e-9)


def test_majority_supported():
    sf = load_strike_field()
    frac = (sf["n_segments"][sf["in_jh"]] >= 20).mean()
    assert frac > 0.5


def test_anisotropy_reanchored_and_monotone():
    # E1 (Stage D): field-median V reproduces the current fractured 0.02, clipped
    # to a physical band, monotone, and aligned fabric is MORE channeled than median
    assert anisotropy_from_variance(ANISO_V_MED) == pytest.approx(ANISO_BASE, abs=1e-6)
    assert anisotropy_from_variance(0.0) == pytest.approx(ANISO_CLIP[0])   # aligned floor
    assert anisotropy_from_variance(1.0) == pytest.approx(ANISO_CLIP[1])   # dispersed ceiling
    assert anisotropy_from_variance(0.4) < anisotropy_from_variance(0.8)
    assert anisotropy_from_variance(0.40) < ANISO_BASE                     # the fix


def test_flux_azimuth_tensor_rotation():
    # flow parallel to strike -> no rotation; oblique+aligned -> rotates toward strike
    assert flux_azimuth(80.0, 80.0, 0.4) == pytest.approx(80.0, abs=1.0)
    fx = flux_azimuth(80.0, 50.0, 0.4)
    assert 50.0 < fx < 80.0                                   # between flow and strike
    assert flux_azimuth(80.0, 50.0, 0.4, fractured=False) == pytest.approx(80.0)  # porous: none
    # aligned fabric -> higher permeability anisotropy than dispersed
    assert anisotropy_lambda(0.3) > anisotropy_lambda(0.8)
    assert 1.0 <= anisotropy_lambda(0.0) <= 6.0


def test_regional_grain_is_ENE():
    # Jharkhand's dominant structural grain (Singhbhum/Chotanagpur) is ~E-W to ENE.
    # The length-weighted state-wide mean strike must land in that band.
    sf = load_strike_field()
    rx = float(np.sum(sf["res_x"][sf["in_jh"]]))
    ry = float(np.sum(sf["res_y"][sf["in_jh"]]))
    strike = (np.degrees(np.arctan2(ry, rx)) / 2.0) % 180.0
    assert 55.0 <= strike <= 105.0, f"regional strike {strike:.1f} not ENE-ish"


def test_out_of_grid_clamped():
    s = strike_at(200.0, 200.0)
    assert 0.0 <= s["mean_strike_deg"] < 180.0


def test_border_pin_is_finite_and_bounded():
    # Stage A: validity-weighted bilinear must keep a border pin sane even when
    # most bilinear corners are out-of-Jharkhand cells (global fallback there)
    s = strike_at(83.5, 25.4)
    assert 0.0 <= s["mean_strike_deg"] < 180.0
    assert 0.0 <= s["circular_variance"] <= 1.0
