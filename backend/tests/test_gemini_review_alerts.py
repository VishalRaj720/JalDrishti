"""2026-09-27 -- what the alerts read after the Gemini-review build.

Owner decisions (ml_pipeline config section 9, docs/LIMITATIONS.md section 1l):

  * the published-screening tier reads `metrics.alerting` -- max(continuum,
    preferential-pathway channel) -- where the run recorded it, and the plain
    continuum for every run stored before;
  * the possible-reach alert draws the run's ALERTING envelope (the largest
    valid P90) where it stored one, and the ML envelope otherwise;
  * the aquifer explanations carry the upward-gradient setting and its sign
    record;
  * the new high-alkalinity hypothetical, like the ISR-feasibility one, is read
    by nothing that alerts (tests/test_hypotheticals_passthrough.py).
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.models.advisory import Advisory
from app.models.simulation_run import SimulationRun
from app.models.user import UserRole
from app.services import alert_tiers as tiers
from app.services.alerts import AlertService
from app.services.simulation_run import _plume_geometry
from tests.test_p5_citizen import _user, a_block  # noqa: F401  (fixture re-export)
from tests.test_r17_alert_tiers import _published, _square


async def _objects(db, adv_id, run_id):
    adv = (await db.execute(select(Advisory).where(Advisory.id == uuid.UUID(adv_id)))).scalar_one()
    run = (await db.execute(select(SimulationRun).where(SimulationRun.id == uuid.UUID(run_id)))).scalar_one()
    return adv, run


@pytest.mark.asyncio
async def test_the_tier_reads_the_alerting_max_when_the_run_has_one(db_session, a_block):
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    adv_id, run_id = await _published(
        db_session, a_block["id"], str(aid), plume={},
        metrics={"analytical": {"excursion_probability": 0.0},
                 "alerting": {"excursion_probability": 1.0, "migration_m": 950.0,
                              "rule": "max(continuum, channel)",
                              "basis": {"excursion_probability": "channel"}}})
    adv, run = await _objects(db_session, adv_id, run_id)
    assert await AlertService(db_session).announce_advisory(adv, run) == 1
    row = (await db_session.execute(text("""
        SELECT tier, explanation FROM alerts
        WHERE advisory_id = :a AND kind = 'published_screening'"""),
        {"a": adv_id})).mappings().one()
    assert row["tier"] == "alert"                      # 1.0 >= 0.5, from the channel
    conf = row["explanation"]["confidence"]
    assert conf["excursion_probability"] == 1.0
    assert conf["alerting_rule"] == "max(continuum, channel)"
    assert conf["alerting_basis"]["excursion_probability"] == "channel"


@pytest.mark.asyncio
async def test_a_run_stored_before_reads_the_continuum_as_before(db_session, a_block):
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    adv_id, run_id = await _published(
        db_session, a_block["id"], str(aid), plume={},
        metrics={"analytical": {"excursion_probability": 0.1}})
    adv, run = await _objects(db_session, adv_id, run_id)
    await AlertService(db_session).announce_advisory(adv, run)
    tier = (await db_session.execute(text("""
        SELECT tier FROM alerts WHERE advisory_id = :a AND kind = 'published_screening'"""),
        {"a": adv_id})).scalar_one()
    assert tier == "notice"


@pytest.mark.asyncio
async def test_possible_reach_draws_the_alerting_envelope(db_session, a_block):
    """The run's ML P90 stays inside the footprint block; its ALERTING envelope
    (here set by the channel) crosses into the next block -- which is warned."""
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    other = (await db_session.execute(text("""
        INSERT INTO blocks (id, name, district_id, geometry)
        SELECT gen_random_uuid(), 'Next Block', district_id,
               ST_Multi(ST_MakeEnvelope(86.60, 22.40, 86.80, 22.90, 4326))
        FROM blocks WHERE id = :bid RETURNING id::text
    """), {"bid": a_block["id"]})).first()[0]
    await db_session.commit()
    adv_id, run_id = await _published(
        db_session, a_block["id"], str(aid),
        plume={"ml_envelope": {"p90": _square(86.30, 22.70, 0.002)},
               "alert_envelope": {"p90": _square(86.60, 22.70, 0.05),
                                  "basis": "channel", "p90_m": 5200.0}},
        metrics={"analytical": {"excursion_probability": 0.0}})
    adv, run = await _objects(db_session, adv_id, run_id)
    svc = AlertService(db_session)
    await svc.announce_advisory(adv, run)
    out = await svc.announce_possible_reach(adv, run)
    assert out["reason"] == "raised"
    assert [b["id"] for b in out["blocks"]] == [other]


@pytest.mark.asyncio
async def test_without_an_alerting_envelope_the_ml_envelope_is_used(db_session, a_block):
    aid, _ = await _user(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    adv_id, run_id = await _published(
        db_session, a_block["id"], str(aid),
        plume={"ml_envelope": {"p90": _square(86.30, 22.70, 0.002)}},
        metrics={"analytical": {"excursion_probability": 0.0}})
    adv, run = await _objects(db_session, adv_id, run_id)
    out = await AlertService(db_session).announce_possible_reach(adv, run)
    # the small ML ring stays inside the footprint block: nobody new to tell
    assert out["alerts"] == 0 and out["reason"] == "p90_within_footprint_blocks"


def test_the_stored_plume_keeps_the_alerting_envelope():
    env = {"p90": _square(86.3, 22.7, 0.01), "basis": "engine_mc", "p90_m": 60.0}
    geo = _plume_geometry({"plume": {"contours": [{"polygons": []}]},
                           "alert_envelope": env})
    assert geo["alert_envelope"] == env
    assert _plume_geometry({"plume": {"contours": [{"polygons": []}]}})["alert_envelope"] is None


def test_aquifer_explanations_carry_the_gradient_and_its_sign_record():
    setting = {"served": 0.0831, "magnitude_range": [0.03, 0.23],
               "basis": "P50 of log-uniform draws",
               "sign_note": "upward at 2 of 4 measured belt sites"}
    x = tiers.explain_modelled(
        kind="aquifer_pathway", tier="warning", rule="r", block="B", district="D",
        species="tds_mg_l", overlap_ha=None, footprint_ha=None, horizon_years=20,
        engine="both", metrics={}, extrapolation=[], data_confidence=None,
        years_to_breakthrough=10.6, breakthrough_probability=1.0,
        upward_gradient=setting)
    g = x["confidence"]["upward_gradient"]
    assert g["value"] == 0.0831 and g["range"] == [0.03, 0.23]
    assert "2 of 4" in g["sign_note"]
