"""Where-to-sample-next ranking — proposal deliverable, open finding O-1.

`score_block` is pure, so the weighting is tested directly rather than inferred
from an endpoint's output. The properties asserted here are the ones that make
the list *safe to act on*: it must never rank by predicted risk, must never
double-count a blank block, and must put the cheapest closable gap — wells that
exist but were never analysed for uranium — near the top.
"""
import pytest

from app.services import monitoring_gaps as mg


def test_weights_sum_to_100():
    """The score is presented as 0-100 on screen; it has to actually be that."""
    assert sum(w["weight"] for w in mg.WEIGHTS.values()) == 100


def test_every_weight_states_a_rationale():
    """A policy number without its reasoning is indistinguishable from a guess."""
    for name, w in mg.WEIGHTS.items():
        assert w["why"].strip(), f"{name} has no stated rationale"
        assert len(w["why"]) > 40, f"{name}'s rationale is too thin to argue with"


def test_a_block_with_no_wells_scores_highest():
    blank = mg.score_block({"wells": 0, "samples": 0, "uranium_tests": 0,
                            "area_km2": 300, "km_to_tested_well": 40})
    covered = mg.score_block({"wells": 20, "samples": 60, "uranium_tests": 60,
                              "area_km2": 300, "km_to_tested_well": 0.5})
    assert blank["score"] > covered["score"]
    assert blank["factors"]["never_sampled"] == 1.0


def test_blank_block_is_not_double_counted():
    """`sampled_not_analysed` must not also fire for a block with no wells.

    Both describe a missing uranium result, and scoring both would push blank
    blocks above their honest ceiling and distort every comparison below them.
    """
    blank = mg.score_block({"wells": 0, "samples": 0, "uranium_tests": 0,
                            "area_km2": 100, "km_to_tested_well": 40})
    assert blank["factors"]["sampled_not_analysed"] == 0.0


def test_sampled_but_never_analysed_scores_high_and_above_a_tested_block():
    """The R10 finding, turned into an action.

    These are the cheapest gaps in the state to close: the well is drilled and
    the sampling round already happens, so only the determination is missing.
    """
    untested = mg.score_block({"wells": 2, "samples": 2, "uranium_tests": 0,
                               "area_km2": 200, "km_to_tested_well": 20})
    tested = mg.score_block({"wells": 2, "samples": 2, "uranium_tests": 2,
                             "area_km2": 200, "km_to_tested_well": 20})
    assert untested["factors"]["sampled_not_analysed"] == 1.0
    assert tested["factors"]["sampled_not_analysed"] == 0.0
    assert untested["score"] > tested["score"]


def test_thin_coverage_beats_dense_coverage():
    thin = mg.score_block({"wells": 1, "samples": 1, "uranium_tests": 1,
                           "area_km2": 900, "km_to_tested_well": 1})
    dense = mg.score_block({"wells": 30, "samples": 30, "uranium_tests": 30,
                            "area_km2": 90, "km_to_tested_well": 1})
    assert thin["factors"]["coverage"] > dense["factors"]["coverage"]


def test_the_hypothetical_site_factor_cannot_dominate():
    """No ISR mine exists. A speculative location must not drive a real plan.

    A well-observed block next to a registered site must still rank below a
    blank block far from one.
    """
    near_site_well_observed = mg.score_block({
        "wells": 20, "samples": 60, "uranium_tests": 60, "area_km2": 100,
        "km_to_tested_well": 0.5, "km_to_isr": 0.0})
    blank_far = mg.score_block({
        "wells": 0, "samples": 0, "uranium_tests": 0, "area_km2": 100,
        "km_to_tested_well": 40, "km_to_isr": 500.0})
    assert blank_far["score"] > near_site_well_observed["score"]
    assert mg.WEIGHTS["near_hypothetical_site"]["weight"] <= 5


def test_missing_distances_do_not_crash_and_fail_toward_more_monitoring():
    """No tested well anywhere, and no registered site: both must be handled.

    An unknown distance to a measurement is treated as far — the conservative
    direction, because the alternative is quietly ranking an unmeasured place as
    if it were well observed.
    """
    s = mg.score_block({"wells": 0, "samples": 0, "uranium_tests": 0,
                        "area_km2": 100, "km_to_tested_well": None,
                        "km_to_isr": None})
    assert s["factors"]["distance_to_tested_well"] == 1.0
    assert s["factors"]["near_hypothetical_site"] == 0.0


def test_factors_stay_in_range_for_absurd_inputs():
    s = mg.score_block({"wells": 9999, "samples": 9999, "uranium_tests": 9999,
                        "area_km2": 0, "km_to_tested_well": -5, "km_to_isr": -5})
    for k, v in s["factors"].items():
        assert 0.0 <= v <= 1.0, f"{k} escaped 0-1: {v}"
    assert 0.0 <= s["score"] <= 100.0


@pytest.mark.asyncio
async def test_endpoint_returns_its_own_weights(client, admin_token):
    """The judgement travels with the answer, not buried in source."""
    r = await client.get("/api/v1/data-gaps/recommendations?limit=5",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert set(b["weights"]) == set(mg.WEIGHTS)
    assert "not a prediction of contamination" in b["what_this_is"]
    assert "tie_break" in b


@pytest.mark.asyncio
async def test_endpoint_carries_no_model_output(client, admin_token):
    """Observation, not prediction. Pairing the two invites reading one as other."""
    r = await client.get("/api/v1/data-gaps/recommendations?limit=5",
                         headers={"Authorization": f"Bearer {admin_token}"})
    for rec in r.json()["recommendations"]:
        leaked = {"band", "plume", "migration_m", "affected_area_ha",
                  "excursion_probability"} & set(rec)
        assert not leaked, f"recommendation leaked model fields: {leaked}"


@pytest.mark.asyncio
async def test_endpoint_is_staff_only(client):
    r = await client.get("/api/v1/data-gaps/recommendations")
    assert r.status_code in (401, 403), r.text
