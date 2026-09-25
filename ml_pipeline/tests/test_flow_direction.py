"""
2026-09-25 -- how well the flow direction is known, and the fan it draws
(data_prep/flow_direction.py, plume_geometry.direction_offsets /
_rotate_about_pin, the direction-aware exceedance layer, resolve.request_memo).
"""
from __future__ import annotations

import base64
import json
import math

import numpy as np
import pytest

from ml_pipeline.data_prep.flow_direction import (
    DIR_META, DIR_NPZ, _circ_sd_deg, direction_uncertainty_at, plane_fit_with_se)
from ml_pipeline.dashboard.plume_geometry import (
    _rotate_about_pin, direction_offsets, exceedance_layer, raster_grid)

JADUGUDA = (86.347, 22.652)


def _serve(**over):
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    kw = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], mode="analytical", time_years=20,
              species="tds_mg_l")
    kw.update(over)
    return api_predict(PredictRequest(**kw))


# ── the statistics ──────────────────────────────────────────────────────


def test_the_refit_reproduces_the_served_flow_direction():
    """Same stations, heads, kernel -> the same direction as flow_field.npz;
    otherwise the uncertainty would describe a different estimate."""
    assert DIR_NPZ.exists()
    meta = json.loads(DIR_META.read_text(encoding="utf-8"))
    assert meta["max_abs_azimuth_diff_vs_flow_field_deg"] < 1e-6
    assert meta["cells_with_fit_se"] > 1000


def test_a_perfect_plane_has_no_direction_error_and_noise_adds_it():
    rng = np.random.default_rng(3)
    lons = 86.3 + rng.uniform(-0.2, 0.2, 40)
    lats = 22.6 + rng.uniform(-0.2, 0.2, 40)
    E = (lons - 86.3) * 111320 * math.cos(math.radians(22.6))
    N = (lats - 22.6) * 111320
    h = 200 + 0.002 * E - 0.003 * N                    # grad (0.002, -0.003)
    az, se, n = plane_fit_with_se(86.3, 22.6, lons, lats, h, 12000.0)
    # flow = -grad = (-0.002, +0.003): bearing atan2(-0.002, 0.003)
    assert az == pytest.approx(math.degrees(math.atan2(-0.002, 0.003)) % 360, abs=1e-6)
    assert se < 1e-6
    _, se_noisy, _ = plane_fit_with_se(86.3, 22.6, lons, lats,
                                       h + rng.normal(0, 3.0, 40), 12000.0)
    assert se_noisy > 1.0


def test_circular_sd_handles_the_wrap():
    assert _circ_sd_deg(np.array([359.0, 1.0])) == pytest.approx(1.0, abs=0.01)
    assert _circ_sd_deg(np.array([10.0, 10.0, 10.0])) == pytest.approx(0.0, abs=1e-6)


def test_served_uncertainty_is_the_larger_estimate_not_a_sum():
    d = direction_uncertainty_at(*JADUGUDA)
    assert d is not None
    of_mean = d["year_sd_of_mean_deg"] or 0.0
    assert d["served_sd_deg"] == pytest.approx(max(d["se_fit_deg"], of_mean), abs=0.01)


# ── the rotation and the fan ────────────────────────────────────────────


def test_a_clockwise_turn_moves_east_to_south():
    """Bearing +90 deg is clockwise: a feature due EAST of the pin must end up
    due SOUTH of it."""
    g = raster_grid((-500.0, 500.0), (-500.0, 500.0), lon0=JADUGUDA[0],
                    lat0=JADUGUDA[1], azimuth_deg=0.0, max_px=101)
    r0, c0 = g["pin_rc"]
    layer = np.zeros((g["height"], g["width"]))
    east = int(round(c0 + 300.0 / g["sx_m"]))
    layer[int(round(r0)), east] = 1.0
    out = _rotate_about_pin(layer, g, 90.0)
    rr, cc = np.unravel_index(np.argmax(out), out.shape)
    assert rr > r0 + 250.0 / g["sy_m"]               # moved south (rows increase)
    assert abs(cc - c0) < 3


def test_direction_offsets_are_symmetric_quantiles():
    o = direction_offsets(20.0)
    assert len(o) == 15 and sum(o) == pytest.approx(0.0, abs=1e-9)
    assert max(o) == pytest.approx(-min(o))
    assert direction_offsets(None) is None and direction_offsets(0.0) is None


def test_the_fan_widens_the_footprint_and_leaves_the_central_run_alone():
    r = _serve()
    e = r["plume"]["raster"]["exceedance"]
    assert e["direction_sd_deg"] == pytest.approx(
        r["hydro"]["flow"]["direction_uncertainty"]["served_sd_deg"])
    assert e["n_directions"] == 15
    # the central run's numbers do not see the fan
    lean = _serve(display_extras=False)
    assert json.dumps(r["metrics"], sort_keys=True) == json.dumps(lean["metrics"], sort_keys=True)


def test_without_direction_the_map_is_the_served_frame():
    """exceedance_layer with no direction must still reproduce the served
    excursion probability at the ring (the same check as before the fan)."""
    from ml_pipeline.config import parameters as P
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import mc_param_draws
    r = _serve()
    inputs, _ = resolve_inputs(dict(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                    species="tds_mg_l", time_years=20))
    thr = P.EXCURSION_THRESHOLDS["tds_mg_l"]
    thr_inc = max(thr - inputs["background_conc_Cb"], P.INCREMENTAL_FLOOR * thr)
    ring = {"X": np.array([[P.COMPLIANCE_BUFFER_M]]), "Y": np.array([[0.0]])}
    layer = exceedance_layer(ring, mc_param_draws(inputs), thr_inc=thr_inc)
    frac = np.frombuffer(base64.b64decode(layer["data"]), dtype=np.uint8)[0] / 255.0
    assert frac == pytest.approx(r["metrics"]["analytical"]["excursion_probability"],
                                 abs=1.0 / 255 + 1e-9)


def test_a_user_set_bearing_is_not_fanned():
    r = _serve(azimuth_deg=45.0)
    e = (r["plume"]["raster"] or {}).get("exceedance") or {}
    assert e.get("direction_sd_deg") is None
    assert r["hydro"]["flow"]["direction_uncertainty"] is None


# ── the per-request memo ───────────────────────────────────────────────


def test_the_memo_hands_out_independent_copies_and_does_not_outlive_the_request():
    from ml_pipeline.dashboard import resolve as R
    p = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], species="tds_mg_l", time_years=20)
    with R.request_memo():
        a_in, a_h = R.resolve_inputs(p)
        a_h["flow"]["mutated"] = True
        b_in, b_h = R.resolve_inputs(p)
        assert "mutated" not in b_h["flow"]
        assert a_in == b_in
    assert R._REQUEST_MEMO.get() is None
