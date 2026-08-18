"""Sweeping one axis against a fixed site.

WHY THIS EXISTS. "How many years of restoration is enough?" is not answerable
one run at a time — a single sweep length yields one number with nothing to
compare it against, and the reader draws a conclusion from whichever run they
happened to look at last. The answer is the shape of the curve and the point it
crosses the screening limit.

Affordable because the physics is fast: a warm engine call is ~0.26 s, so six
points is ~1.6 s and fits in a request. The "5–15 s per run" figure quoted
elsewhere is the queue, background-task and provenance cost of a *stored* run.

The invariants worth pinning are about honesty, not arithmetic:
  * a sweep is NOT stored, and says so — otherwise twelve diagnostic rows bury
    the runs a regulator is meant to read
  * the value held fixed on the other axis is REPORTED, because restoration
    adequacy is conditional on when you look
  * one failed point must not lose the other five
  * a site parameter cannot be smuggled in through the sweep body
"""
import uuid

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok


@pytest_asyncio.fixture()
async def field_token(db_session):
    """A field officer collects evidence; they do not run the model."""
    user = User(username="sweepoff", email="sweepoff@example.com",
                hashed_password=hash_password("pass1234"),
                role=UserRole.field_officer)
    db_session.add(user)
    await db_session.commit()
    return create_access_token(str(user.id), user.role)


async def _site(client, token, name="Sweep") -> dict:
    r = await client.post("/api/v1/isr-points", headers=_tok(token),
                          json={"name": f"{name} {uuid.uuid4().hex[:6]}", **FULL_SITE})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_restoration_sweep_returns_a_curve(client, admin_token):
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                          headers=_tok(admin_token),
                          json={"axis": "restoration", "species": "uranium_ppb",
                                "points": 4, "time_years": 20})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["axis"] == "restoration"
    assert len(body["points"]) == 4
    # Endpoints included, ascending, spanning the engine's UI exploration range.
    values = [p["value"] for p in body["points"]]
    assert values == sorted(values)
    assert values[0] == 0

    solved = [p for p in body["points"] if p["error"] is None]
    assert solved, "every point failed to solve"
    assert all(p["area_ha"] is not None for p in solved)


@pytest.mark.asyncio
async def test_a_sweep_is_not_stored_and_says_so(client, admin_token):
    """A diagnostic over a site, not a result about it."""
    site = await _site(client, admin_token)
    before = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                               headers=_tok(admin_token))).json()

    r = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                          headers=_tok(admin_token),
                          json={"axis": "restoration", "points": 3})
    assert r.status_code == 200, r.text
    assert r.json()["persisted"] is False
    assert "not stored" in r.json()["persistence_note"].lower()

    after = (await client.get(f"/api/v1/simulations/runs?isr_id={site['id']}",
                              headers=_tok(admin_token))).json()
    assert len(after) == len(before), (
        "the sweep wrote rows into simulation_runs; twelve diagnostic rows per "
        "question would bury the runs a regulator is meant to read")


@pytest.mark.asyncio
async def test_the_held_value_is_reported_not_assumed(client, admin_token):
    """Restoration adequacy is conditional on the evaluation horizon.

    A curve that does not state where it was read is a curve whose conclusion
    cannot be checked.
    """
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                          headers=_tok(admin_token),
                          json={"axis": "restoration", "points": 3, "time_years": 35})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["held"]["time_years"] == 35
    assert "35" in body["crossing_note"]

    # And the other axis holds the sweep length.
    r2 = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                           headers=_tok(admin_token),
                           json={"axis": "evaluation", "points": 3,
                                 "restoration_years": 7})
    assert r2.status_code == 200, r2.text
    assert r2.json()["held"]["restoration_years"] == 7


@pytest.mark.asyncio
async def test_a_sweep_cannot_change_the_sites_operation(client, admin_token):
    """The P2 rule holds on this path too.

    A sweep runs against a REGISTERED site, so it is subject to the same rule as
    a run: the operation is the site's. `payload_from_site` builds from the site
    row and the allowlist filters the overrides, so an injected parameter is
    dropped rather than honoured — the assertion is that the answer does not
    change, which is what a caller would be trying to achieve.
    """
    site = await _site(client, admin_token)
    args = {"axis": "restoration", "points": 3, "time_years": 20}

    plain = (await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                               headers=_tok(admin_token), json=args)).json()
    spiked = (await client.post(
        f"/api/v1/simulations/{site['id']}/sweep", headers=_tok(admin_token),
        json={**args, "injection_rate_m3_day": 8000, "wellfield_width_m": 800})).json()

    assert [p["area_ha"] for p in plain["points"]] == \
           [p["area_ha"] for p in spiked["points"]], (
        "injecting operating parameters into the sweep body changed the result; "
        "the operation must come from the registered site")


@pytest.mark.asyncio
async def test_point_count_is_capped(client, admin_token):
    """The cost is bounded, because each point is a real engine solve."""
    site = await _site(client, admin_token)
    r = await client.post(f"/api/v1/simulations/{site['id']}/sweep",
                          headers=_tok(admin_token),
                          json={"axis": "restoration", "points": 500})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_field_officer_cannot_sweep(client, field_token):
    """Sweeping runs the model, so it sits with the roles that may run it."""
    r = await client.post(f"/api/v1/simulations/{uuid.uuid4()}/sweep",
                          headers=_tok(field_token),
                          json={"axis": "restoration", "points": 3})
    assert r.status_code == 403
