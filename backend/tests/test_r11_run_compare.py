"""Diffing two runs, and attributing the difference.

`diff` is pure, so the attribution logic is tested directly. The property that
matters most is the one a reviewer relies on: when the model changed between two
runs, the page must say so rather than presenting a metric delta as if the inputs
caused it.
"""
import uuid

import pytest

from app.services import run_compare as rc


class _Run:
    """Minimal stand-in for a SimulationRun row."""

    def __init__(self, **kw):
        self.id = kw.get("id", uuid.uuid4())
        self.isr_point_id = kw.get("isr_point_id", uuid.uuid4())
        self.species = kw.get("species", "uranium")
        self.status = "completed"
        self.request = kw.get("request", {})
        self.metrics = kw.get("metrics", {})
        self.extrapolation = kw.get("extrapolation")
        self.artifacts_sha = kw.get("artifacts_sha", "AAA")
        self.model_card_sha = kw.get("model_card_sha", "CARD")
        self.code_version = kw.get("code_version", "v1")


def test_same_inputs_and_model_says_so():
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, request={"t": 10}, metrics={"analytical": {"area_ha": 9.8}})
    b = _Run(isr_point_id=site, request={"t": 10}, metrics={"analytical": {"area_ha": 9.8}})
    d = rc.diff(a, b)
    assert d["cause"] == "identical inputs, model and code"
    assert d["metric_delta"] == {}
    assert d["same_site"] is True


def test_a_changed_model_is_called_out_even_when_inputs_match():
    """The failure this exists to prevent.

    Same inputs, different artifact bundle: the delta is the model's doing, and
    reporting it without saying so would let a reviewer attribute it to a site
    parameter nobody touched.
    """
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, request={"t": 10}, artifacts_sha="AAA",
             metrics={"analytical": {"area_ha": 9.8}})
    b = _Run(isr_point_id=site, request={"t": 10}, artifacts_sha="BBB",
             metrics={"analytical": {"area_ha": 11.2}})
    d = rc.diff(a, b)
    assert d["same_model"] is False
    assert "MODEL ARTIFACTS changed" in d["cause"]
    assert d["metric_delta"]["analytical.area_ha"]["change_pct"] == pytest.approx(14.29, abs=0.01)


def test_both_changed_refuses_to_attribute():
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, request={"t": 10}, artifacts_sha="AAA")
    b = _Run(isr_point_id=site, request={"t": 20}, artifacts_sha="BBB")
    d = rc.diff(a, b)
    assert "cannot be attributed" in d["cause"]


def test_two_different_sites_are_labelled_as_two_operations():
    """Cross-site input differences are expected, not a warning."""
    a = _Run(request={"t": 10, "injection_rate_m3_day": 2500})
    b = _Run(request={"t": 10, "injection_rate_m3_day": 4000})
    d = rc.diff(a, b)
    assert d["same_site"] is False
    assert "two different sites" in d["cause"]
    assert "two distinct hypothetical" in d["cause"]
    assert "injection_rate_m3_day" in d["input_delta"]


def test_a_rise_from_zero_reports_no_percentage():
    """A plume that did not exist and now does is not 'infinitely larger'."""
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 0.0}})
    b = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 5.0}})
    d = rc.diff(a, b)
    cell = d["metric_delta"]["analytical.area_ha"]
    assert cell["change_pct"] is None
    assert cell["a"] == 0.0 and cell["b"] == 5.0


def test_metrics_present_on_one_side_only_are_still_listed():
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 5.0}})
    b = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 5.0,
                                                        "migration_m": 12.7}})
    d = rc.diff(a, b)
    assert d["metric_delta"]["analytical.migration_m"]["a"] is None
    assert d["metric_delta"]["analytical.migration_m"]["b"] == 12.7


def test_both_engines_are_kept_separate():
    """The analytical engine is the authority; merging the two would hide that."""
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 9.8},
                                          "ml": {"area_ha": 9.1}})
    b = _Run(isr_point_id=site, metrics={"analytical": {"area_ha": 10.0},
                                          "ml": {"area_ha": 9.4}})
    d = rc.diff(a, b)
    assert "analytical.area_ha" in d["metric_delta"]
    assert "ml.area_ha" in d["metric_delta"]


def test_booleans_are_not_treated_as_metrics():
    """`isinstance(True, int)` is True in Python; a flag is not a measurement."""
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, metrics={"analytical": {"suppressed": True, "area_ha": 1.0}})
    b = _Run(isr_point_id=site, metrics={"analytical": {"suppressed": False, "area_ha": 2.0}})
    d = rc.diff(a, b)
    assert "analytical.suppressed" not in d["metric_delta"]
    assert "analytical.area_ha" in d["metric_delta"]


def test_the_note_carries_the_hypothetical_premise():
    d = rc.diff(_Run(), _Run())
    assert "No ISR uranium mine operates in Jharkhand" in d["note"]


@pytest.mark.asyncio
async def test_compare_endpoint_rejects_the_same_run_twice(client, admin_token):
    rid = str(uuid.uuid4())
    r = await client.post("/api/v1/simulations/compare",
                          json={"run_a": rid, "run_b": rid},
                          headers={"Authorization": f"Bearer {admin_token}"})
    # 404 (no such run) or 400 (same run) — never a diff of a run with itself.
    assert r.status_code in (400, 404), r.text


@pytest.mark.asyncio
async def test_compare_endpoint_is_staff_only(client):
    r = await client.post("/api/v1/simulations/compare",
                          json={"run_a": str(uuid.uuid4()), "run_b": str(uuid.uuid4())})
    assert r.status_code in (401, 403), r.text


def test_a_code_change_alone_is_reported_as_an_engine_change():
    """The gap the real data exposed.

    Two runs shared an artifact bundle and model card but had different
    `code_version` — and the original check called that "same model". The
    analytical engine is CODE, not a pickled model: a change to transport.py
    moves every analytical number while artifacts_sha stays identical. Claiming
    "same model" there attributes a code-driven delta to the inputs, which is
    the one thing this function exists to prevent.
    """
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, request={"t": 10}, code_version="9d7b60e7",
             metrics={"analytical": {"area_ha": 9.8}})
    b = _Run(isr_point_id=site, request={"t": 10}, code_version="9b881655",
             metrics={"analytical": {"area_ha": 11.2}})
    d = rc.diff(a, b)
    assert d["same_model"] is True, "artifacts really are identical"
    assert d["same_code"] is False
    assert d["same_engine"] is False
    assert "ENGINE CODE changed" in d["cause"]


def test_artifacts_and_code_both_changing_is_named_as_such():
    site = uuid.uuid4()
    a = _Run(isr_point_id=site, request={"t": 10}, artifacts_sha="AAA", code_version="v1")
    b = _Run(isr_point_id=site, request={"t": 10}, artifacts_sha="BBB", code_version="v2")
    d = rc.diff(a, b)
    assert "both the model artifacts and the engine code changed" in d["cause"]
