"""Named scenarios and run comparison — the last P3 slice."""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import User, UserRole
from app.services.auth import hash_password, create_access_token

LON, LAT = 86.36, 22.65


async def _mk(db, u, e, role):
    user = User(username=u, email=e, hashed_password=hash_password("pass1234"),
                role=role)
    db.add(user)
    await db.commit()
    return user


def _tok(u):
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role)}"}


@pytest_asyncio.fixture()
async def isr_id(db_session):
    rid = (await db_session.execute(text("""
        INSERT INTO isr_points (id, name, location, injection_rate_m3_day)
        VALUES (gen_random_uuid(), 'Scenario Site',
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 1000)
        RETURNING id
    """), {"lon": LON, "lat": LAT})).scalar_one()
    await db_session.commit()
    return rid


@pytest_asyncio.fixture()
async def analyst(db_session):
    return await _mk(db_session, "scana", "scana@example.com", UserRole.analyst)


@pytest_asyncio.fixture()
async def officer(db_session):
    return await _mk(db_session, "scoff", "scoff@example.com",
                     UserRole.field_officer)


@pytest.mark.asyncio
async def test_analyst_can_save_and_run_a_scenario(client, analyst, isr_id):
    c = await client.post("/api/v1/scenarios", headers=_tok(analyst),
                          json={"name": "Baseline 20yr", "isr_point_id": str(isr_id),
                                "description": "default evaluation case",
                                # P2: a scenario names RUN inputs against a fixed
                                # site. `operation_years` describes the operation
                                # and belongs to the site, so it is refused here.
                                "params": {"time_years": 20, "restoration_years": 5}})
    assert c.status_code == 201, c.text
    sid = c.json()["id"]

    r = await client.post(f"/api/v1/scenarios/{sid}/run", headers=_tok(analyst))
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    run = (await client.get(f"/api/v1/simulations/runs/{run_id}",
                            headers=_tok(analyst))).json()
    assert run["status"] == "completed", run.get("error_message")
    assert run["request"]["time_years"] == 20
    assert run["request"]["restoration_years"] == 5


@pytest.mark.asyncio
async def test_scenario_params_are_validated_at_save_time(client, analyst, isr_id):
    """A scenario that cannot run is worse than one that is refused — it looks
    saved."""
    r = await client.post("/api/v1/scenarios", headers=_tok(analyst),
                          json={"name": "Bad", "isr_point_id": str(isr_id),
                                "params": {"uranium_ppb": 500}})
    assert r.status_code == 422
    assert "uranium_ppb" in r.text


@pytest.mark.asyncio
async def test_scenario_names_are_unique_per_site(client, analyst, isr_id):
    body = {"name": "Dup", "isr_point_id": str(isr_id), "params": {}}
    assert (await client.post("/api/v1/scenarios", headers=_tok(analyst),
                              json=body)).status_code == 201
    again = await client.post("/api/v1/scenarios", headers=_tok(analyst), json=body)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_field_officer_cannot_create_scenarios(client, officer, isr_id):
    r = await client.post("/api/v1/scenarios", headers=_tok(officer),
                          json={"name": "Nope", "isr_point_id": str(isr_id),
                                "params": {}})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_compare_attributes_the_difference_to_inputs(
        client, analyst, isr_id):
    """Two runs, same model, different inputs — the cause must say so.

    P2 changed WHICH input varies here. This used to compare two
    `operation_years`, but a run can no longer set that: the operation belongs
    to the site (migration 0015), and letting a run override it meant two people
    running one site were not running the same thing. The evaluation horizon is
    a genuine run variable, and it exercises the same comparison logic.
    """
    sid = (await client.post(
        "/api/v1/scenarios", headers=_tok(analyst),
        json={"name": "Cmp", "isr_point_id": str(isr_id),
              "params": {"time_years": 4}})).json()["id"]

    a = (await client.post(f"/api/v1/scenarios/{sid}/run",
                           headers=_tok(analyst))).json()["run_id"]
    b = (await client.post(f"/api/v1/simulations/{isr_id}", headers=_tok(analyst),
                           json={"time_years": 20})).json()["id"]

    cmp_ = await client.post(f"/api/v1/scenarios/{sid}/compare",
                             headers=_tok(analyst),
                             json={"run_a": a, "run_b": b})
    assert cmp_.status_code == 200, cmp_.text
    body = cmp_.json()
    assert body["same_model"] is True
    # R11 widened this from "same model" to "same model and code": two runs can
    # share an artifact bundle and still have been computed by different physics,
    # because the analytical engine is code rather than a pickled model.
    assert body["cause"] == "inputs differ; same model and code"
    assert body["input_delta"]["time_years"] == {"a": 4, "b": 20}
    # a longer evaluation horizon should move at least one metric
    assert body["metric_delta"], "identical metrics for different horizons"


@pytest.mark.asyncio
async def test_compare_reports_identical_when_nothing_changed(
        client, analyst, isr_id):
    sid = (await client.post(
        "/api/v1/scenarios", headers=_tok(analyst),
        json={"name": "Same", "isr_point_id": str(isr_id),
              "params": {"time_years": 8}})).json()["id"]
    a = (await client.post(f"/api/v1/scenarios/{sid}/run",
                           headers=_tok(analyst))).json()["run_id"]
    b = (await client.post(f"/api/v1/scenarios/{sid}/run",
                           headers=_tok(analyst))).json()["run_id"]
    body = (await client.post(f"/api/v1/scenarios/{sid}/compare",
                              headers=_tok(analyst),
                              json={"run_a": a, "run_b": b})).json()
    assert body["cause"] == "identical inputs, model and code"
    assert body["metric_delta"] == {}


@pytest.mark.asyncio
async def test_compare_refuses_an_incomplete_run(client, analyst, isr_id,
                                                 db_session):
    sid = (await client.post(
        "/api/v1/scenarios", headers=_tok(analyst),
        json={"name": "Incomplete", "isr_point_id": str(isr_id),
              "params": {}})).json()["id"]
    a = (await client.post(f"/api/v1/scenarios/{sid}/run",
                           headers=_tok(analyst))).json()["run_id"]
    queued = (await db_session.execute(text("""
        INSERT INTO simulation_runs (id, isr_point_id, status, species, request)
        VALUES (gen_random_uuid(), :i, 'queued', 'uranium_ppb', '{}'::jsonb)
        RETURNING id
    """), {"i": str(isr_id)})).scalar_one()
    await db_session.commit()

    r = await client.post(f"/api/v1/scenarios/{sid}/compare",
                          headers=_tok(analyst),
                          json={"run_a": a, "run_b": str(queued)})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_archive_keeps_the_scenario_for_its_runs(client, analyst, isr_id):
    """Runs reference the scenario that produced them, so it is archived, not
    deleted."""
    sid = (await client.post(
        "/api/v1/scenarios", headers=_tok(analyst),
        json={"name": "ToArchive", "isr_point_id": str(isr_id),
              "params": {}})).json()["id"]
    assert (await client.delete(f"/api/v1/scenarios/{sid}",
                                headers=_tok(analyst))).status_code == 204

    listed = (await client.get("/api/v1/scenarios", headers=_tok(analyst))).json()
    assert sid not in [s["id"] for s in listed]
    still = await client.get(f"/api/v1/scenarios/{sid}", headers=_tok(analyst))
    assert still.status_code == 200
    assert still.json()["archived_at"] is not None
