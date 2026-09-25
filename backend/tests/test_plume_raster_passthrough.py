"""2026-09-25 -- the engine's display rasters reach storage, and the loop callers
opt out of them (ml_pipeline dashboard/plume_geometry.py; adapter METRICS_ONLY).

A stored run must paint what the live one did, so `_plume_geometry` has to copy
the raster; and the callers that evaluate the engine dozens of times per request
(lifecycle, sweep, timeline frames) must be able to skip ~250 ms of display work
per call -- which only happens if the flag survives the adapter's allowlist.
"""
from app.services import ml_pipeline_adapter as mlp
from app.services.simulation_run import _plume_geometry


def test_a_stored_run_keeps_the_raster():
    raster = {"bounds": [[22.6, 86.3], [22.7, 86.4]], "width": 2, "height": 1,
              "concentration": {"data": "AAE="}, "exceedance": None}
    geo = _plume_geometry({"plume": {"contours": [{"level": 1, "polygons": []}],
                                     "raster": raster}})
    assert geo["raster"] == raster


def test_a_run_before_the_raster_stores_none():
    geo = _plume_geometry({"plume": {"contours": [{"level": 1, "polygons": []}]}})
    assert geo["raster"] is None


def test_the_metrics_only_flag_crosses_the_boundary():
    payload = mlp.build_payload(lon=86.3, lat=22.6, params=dict(mlp.METRICS_ONLY))
    assert payload["display_extras"] is False
