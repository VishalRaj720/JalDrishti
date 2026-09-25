"""
2026-09-25 -- the plume as a continuous raster and as an exceedance-probability
map (dashboard/plume_geometry.py: raster_grid / concentration_layer /
exceedance_layer / plume_rasters).

What is pinned: the raster is the engine's own field evaluated per pixel (no
interpolation, same display rules as the contours), and the probability map is
the engine's own Monte Carlo (the draws its excursion probability already
scores) drawn in space -- so at the monitoring ring it must reproduce the served
excursion probability. Neither may move a metric.
"""
from __future__ import annotations

import base64
import json
import math

import numpy as np
import pytest

from ml_pipeline.config import parameters as P
from ml_pipeline.dashboard.plume_geometry import (
    exceedance_layer, local_to_lonlat, lonlat_to_local)
from ml_pipeline.physics.transport import concentration_field

JADUGUDA = (86.347, 22.652)


def _serve(**over):
    from ml_pipeline.dashboard.server import api_predict, PredictRequest
    kw = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], mode="analytical", time_years=20,
              species="tds_mg_l")
    kw.update(over)
    return api_predict(PredictRequest(**kw))


def _decode(layer: dict, rs: dict) -> np.ndarray:
    return np.frombuffer(base64.b64decode(layer["data"]), dtype=np.uint8).reshape(
        rs["height"], rs["width"])


def test_lonlat_to_local_inverts_local_to_lonlat():
    for az in (0.0, 37.5, 81.0, 200.0, 359.0):
        for x, y in ((0.0, 0.0), (350.0, -120.0), (-150.0, 40.0), (2400.0, 900.0)):
            lon, lat = local_to_lonlat(x, y, *JADUGUDA, az)
            xb, yb = lonlat_to_local(lon, lat, *JADUGUDA, az)
            assert xb == pytest.approx(x, abs=1e-6) and yb == pytest.approx(y, abs=1e-6)


def test_every_pixel_is_the_engine_field_itself():
    """No interpolation: decode a pixel, and it must equal concentration_field
    evaluated at that pixel's own centre, to the 8-bit quantisation."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import features_from_inputs
    from ml_pipeline.physics.transport import params_from_features
    r = _serve()
    rs = r["plume"]["raster"]
    conc = rs["concentration"]
    q = _decode(conc, rs)
    payload = dict(lon=JADUGUDA[0], lat=JADUGUDA[1], species="tds_mg_l", time_years=20)
    inputs, _ = resolve_inputs(payload)
    feat = features_from_inputs(**inputs)[1]
    prm = params_from_features(
        feat, species_C0=inputs["source_conc_C0"], t_days=20 * 365.0,
        operation_days=inputs["operation_years"] * 365.0, restoration_days=0.0,
        residual_fraction=feat.get("_residual_endpoint", 1.0),
        background=inputs["background_conc_Cb"], floor_source_at_background=True)
    (lat_s, lon_w), (lat_n, lon_e) = rs["bounds"]
    lo, hi = conc["log10_min"], conc["log10_max"]
    checked = 0
    for (j, i) in zip(*np.nonzero(q > 0)):
        if checked >= 40:
            break
        lon = lon_w + (i + 0.5) / rs["width"] * (lon_e - lon_w)
        lat = lat_n - (j + 0.5) / rs["height"] * (lat_n - lat_s)
        x, y = lonlat_to_local(lon, lat, *JADUGUDA, r["azimuth_deg"])
        x -= r["wellfield_geometry"]["pattern_footprint_radius_m"]
        c = float(concentration_field(np.array([[x]]), np.array([[y]]), prm,
                                      include_disc=False)[0, 0]) + inputs["background_conc_Cb"]
        expect = 1 + round((math.log10(c) - lo) / (hi - lo) * 254)
        assert abs(int(q[j, i]) - expect) <= 1, (j, i, q[j, i], expect)
        checked += 1
    assert checked >= 20


def test_nothing_is_painted_up_gradient_of_the_source_plane():
    r = _serve()
    rs = r["plume"]["raster"]
    q = _decode(rs["concentration"], rs)
    # rebuild the served grid's own pixel frame from its bounds
    (lat_s, lon_w), (lat_n, lon_e) = rs["bounds"]
    lons = lon_w + (np.arange(rs["width"]) + 0.5) / rs["width"] * (lon_e - lon_w)
    lats = lat_n - (np.arange(rs["height"]) + 0.5) / rs["height"] * (lat_n - lat_s)
    LON, LAT = np.meshgrid(lons, lats)
    X, _Y = lonlat_to_local(LON, LAT, *JADUGUDA, r["azimuth_deg"])
    X -= r["wellfield_geometry"]["pattern_footprint_radius_m"]
    assert np.any(q > 0)
    assert not np.any(q[X <= 0.0]), "the Domenico up-gradient half-plane was painted"


def test_the_probability_map_reproduces_the_served_excursion_probability():
    """The exceedance layer is the engine's own Monte Carlo drawn in space, so at
    the monitoring ring it must equal the served excursion probability."""
    from ml_pipeline.dashboard.resolve import resolve_inputs
    from ml_pipeline.ml.predict import mc_param_draws
    r = _serve()
    served = r["metrics"]["analytical"]["excursion_probability"]
    inputs, _ = resolve_inputs(dict(lon=JADUGUDA[0], lat=JADUGUDA[1],
                                    species="tds_mg_l", time_years=20))
    draws = mc_param_draws(inputs)
    threshold = P.EXCURSION_THRESHOLDS["tds_mg_l"]
    thr_inc = max(threshold - inputs["background_conc_Cb"], P.INCREMENTAL_FLOOR * threshold)
    ring = {"X": np.array([[P.COMPLIANCE_BUFFER_M]]), "Y": np.array([[0.0]])}
    layer = exceedance_layer(ring, draws, thr_inc=thr_inc)
    frac = 0.0 if layer is None else np.frombuffer(
        base64.b64decode(layer["data"]), dtype=np.uint8)[0] / 255.0
    assert frac == pytest.approx(served, abs=1.0 / 255 + 1e-9)


def test_the_map_covers_every_draw_not_just_the_central_run():
    """A long P90 front must not be clipped at the edge of the central picture."""
    r = _serve()
    rs = r["plume"]["raster"]
    q = _decode(rs["exceedance"], rs)
    # nothing may be touching the grid edge except where the grid starts at the
    # wellfield (the box grows to cover the farthest-reaching draw)
    edge = np.concatenate([q[0, :], q[-1, :], q[:, 0], q[:, -1]])
    assert edge.max() <= 3, "the exceedance map is clipped at its own boundary"


def test_display_extras_off_moves_no_number():
    full, lean = _serve(), _serve(display_extras=False)
    assert lean["plume"]["raster"] is None
    assert lean["vertical"]["indicators_computed"] is False
    assert json.dumps(full["metrics"], sort_keys=True) == json.dumps(lean["metrics"], sort_keys=True)
    assert full["plume"]["contours"] == lean["plume"]["contours"]
    assert (full["vertical"]["years_to_vertical_breakthrough"]
            == lean["vertical"]["years_to_vertical_breakthrough"])


def test_a_suppressed_source_does_not_break_the_response():
    """Outside an ore zone the uranium source is clamped to trace: there may be
    nothing above the floor, and that must come back as None, not an error."""
    r = _serve(lon=85.33, lat=23.36, species="uranium_ppb")
    rs = r["plume"]["raster"]
    assert rs is None or rs.get("concentration") is None or rs["width"] > 0
