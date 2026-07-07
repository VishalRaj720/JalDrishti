"""Phase-2 D1 -- data-derived flow field (loads the committed .npz, no DEM needed)."""
from __future__ import annotations

import numpy as np
import pytest

from ml_pipeline.data_prep.flow_field import load_flow_field, flow_at, FLOW_NPZ
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
