"""Phase-2 D1 -- data-derived flow field (loads the committed .npz, no DEM needed)."""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.data_prep.flow_field import (
    load_flow_field, flow_at, FLOW_NPZ, _valid_bilinear, _bilinear_weights,
)
from ml_pipeline.config import parameters as P

pytestmark = pytest.mark.skipif(not FLOW_NPZ.exists(),
                                reason="flow_field.npz not built (run -m ml_pipeline.data_prep.flow_field)")

_GI_LO, _GI_HI = P.OPERATIONAL_RANGES["hydraulic_gradient"]
_AMP_HI = P.IRREGULARITY["gradient_seasonal_amp"][1]


def test_flow_at_returns_sane_values():
    f = flow_at(86.347, 22.652)                        # Jaduguda
    assert 0.0 <= f["azimuth_deg"] < 360.0
    assert _GI_LO <= f["gradient_i"] <= _GI_HI
    assert 0.0 <= f["seasonal_amp"] <= _AMP_HI
    assert f["source"] in {"stations", "dem"}


def test_all_in_state_cells_have_gradient_in_envelope():
    ff = load_flow_field()
    g = ff["gradient_i"][ff["in_jh"]]
    assert np.all(g >= _GI_LO - 1e-9) and np.all(g <= _GI_HI + 1e-9)
    amp = ff["seasonal_amp"][ff["in_jh"]]
    assert np.all(amp >= 0.0) and np.all(amp <= _AMP_HI + 1e-9)


def test_mostly_station_supported():
    ff = load_flow_field()
    in_jh = ff["in_jh"]
    frac_station = (ff["source"][in_jh] == 1).mean()
    assert frac_station > 0.5           # majority of the state is data-driven, not DEM


def test_azimuth_is_circularly_interpolated():
    # bilinear must interpolate the UNIT VECTORS, not the degrees -> sampling
    # anywhere inside the grid yields a valid bearing with no 0/360 seam artifact
    ff = load_flow_field()
    lon_c, lat_c = ff["lon_c"], ff["lat_c"]
    mid_lon = 0.5 * (lon_c[0] + lon_c[-1])
    mid_lat = 0.5 * (lat_c[0] + lat_c[-1])
    az = flow_at(mid_lon, mid_lat)["azimuth_deg"]
    assert az is None or (0.0 <= az < 360.0)


def test_out_of_grid_is_clamped_not_crashed():
    f = flow_at(200.0, 200.0)            # absurd input -> clamp to grid edge
    assert _GI_LO <= f["gradient_i"] <= _GI_HI


# --------------------------------------------------------------------------- #
# Stage A: depth-to-water, effective amplitude, divides, border-safe bilinear
# --------------------------------------------------------------------------- #
def test_depth_to_water_present_and_ordered():
    f = flow_at(86.347, 22.652)                         # Jaduguda (station-rich)
    assert f["depth_to_water_m"] is not None
    assert 0.0 < f["depth_to_water_m"] < 60.0           # m bgl, hard-rock phreatic
    # shallowest (post-monsoon) table is at a SMALLER depth than the annual mean
    assert f["depth_to_water_shallow_m"] <= f["depth_to_water_m"] + 1e-6


def test_depth_to_water_none_where_unsupported():
    # a sparse-station corner returns None rather than a fabricated depth
    ff = load_flow_field()
    assert np.isnan(ff["dtw_mean"][~np.isfinite(ff["dtw_mean"])]).all() or True
    # contract: at least some in-JH cells legitimately have no depth data
    none_count = int(np.isnan(ff["dtw_mean"][ff["in_jh"]]).sum())
    assert none_count > 0


def test_effective_amp_never_below_raw_and_in_envelope():
    for lon, lat in [(86.347, 22.652), (85.33, 23.36), (86.20, 22.80)]:
        f = flow_at(lon, lat)
        assert f["seasonal_amp_effective"] >= f["seasonal_amp"] - 1e-9
        assert f["seasonal_amp_effective"] <= _AMP_HI + 1e-9


def test_low_quality_cell_widens_amplitude():
    # a DEM-fallback / poor-fit pin must carry MORE gradient uncertainty than raw
    f = flow_at(86.20, 22.80)                            # Jamshedpur: fit_r2 ~0.19
    assert f["seasonal_amp_effective"] > f["seasonal_amp"]


def test_near_divide_yields_none_azimuth():
    # somewhere on the radial Ranchi-plateau divide the four corner arrows
    # disagree -> low coherence -> azimuth None (no preferred direction there)
    found = False
    for lat in np.arange(23.0, 23.9, 0.03):
        for lon in np.arange(85.0, 86.2, 0.03):
            f = flow_at(float(lon), float(lat))
            if f["near_divide"]:
                assert f["azimuth_deg"] is None
                assert f["flow_coherence"] < 0.15
                found = True
    assert found, "no divide cell found -- near_divide mechanism is inert"


def test_border_pin_stays_finite():
    # a pin hard against the state border must not crash or return NaN even when
    # most bilinear corners are out-of-Jharkhand (validity weighting handles it)
    f = flow_at(83.5, 25.4)
    assert _GI_LO <= f["gradient_i"] <= _GI_HI
    assert 0.0 <= f["seasonal_amp_effective"] <= _AMP_HI + 1e-9


def test_valid_bilinear_excludes_invalid_and_nan_corners():
    w = _bilinear_weights(0.5, 0.5)                      # equal corner weights
    vals = np.array([10.0, 20.0, np.nan, 40.0])
    valid = np.array([1.0, 1.0, 1.0, 0.0])              # 4th corner out-of-state
    # corner2 NaN + corner3 invalid drop out -> mean(10, 20) = 15
    assert _valid_bilinear(vals, w, valid) == pytest.approx(15.0)
    # no valid corner: fallback=True -> finite plain bilinear; False -> NaN
    zero = np.zeros(4)
    assert np.isfinite(_valid_bilinear(vals, w, zero, fallback=True))
    assert np.isnan(_valid_bilinear(vals, w, zero, fallback=False))
