"""Phase-2 D2 -- fracture-strike field (loads the committed .npz, no geojson needed)."""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.data_prep.strike_field import (
    load_strike_field, strike_at, anisotropy_from_variance, STRIKE_NPZ,
    _ANISO_ALIGNED, _ANISO_DISPERSED,
)

pytestmark = pytest.mark.skipif(not STRIKE_NPZ.exists(),
                                reason="strike_field.npz not built (run -m ml_pipeline.data_prep.strike_field)")


def test_strike_at_ranges():
    s = strike_at(86.347, 22.652)                      # Jaduguda
    assert 0.0 <= s["mean_strike_deg"] < 180.0
    assert 0.0 <= s["circular_variance"] <= 1.0
    assert _ANISO_ALIGNED <= s["aniso_ratio"] <= _ANISO_DISPERSED
    assert s["dispersion"] in {"aligned", "intermediate", "dispersed"}


def test_resultant_is_bounded():
    sf = load_strike_field()
    R = np.hypot(sf["res_x"], sf["res_y"])[sf["in_jh"]]
    assert np.all(R <= 1.0 + 1e-9) and np.all(R >= -1e-9)


def test_majority_supported():
    sf = load_strike_field()
    frac = (sf["n_segments"][sf["in_jh"]] >= 20).mean()
    assert frac > 0.5


def test_anisotropy_mapping_monotone():
    assert anisotropy_from_variance(0.0) == pytest.approx(_ANISO_ALIGNED)
    assert anisotropy_from_variance(1.0) == pytest.approx(_ANISO_DISPERSED)
    assert anisotropy_from_variance(0.3) < anisotropy_from_variance(0.7)


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
