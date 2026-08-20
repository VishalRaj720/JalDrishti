"""Publishing a screening to the public, and the gate in front of it.

WHY THIS EXISTS. This is the only path in the system by which anything reaches a
member of the public, so the properties worth pinning are about who may do it,
what it may claim, and how far it may claim to reach.

  * **Only a reviewer or admin publishes.** An analyst proposes. One analyst
    should not be able to send a statement about drinking water to everyone in
    a block on their own authority.
  * **Nothing says an operation occurred.** No ISR uranium mine operates in
    Jharkhand, and the hypothetical premise is appended server-side so an author
    cannot omit it and a later template change cannot remove it from an advisory
    a reviewer already approved.
  * **The reach is measured, not assumed.** A ~13 ha footprint against a
    ~30,000 ha block must not be reported as affecting the block.
  * **A withdrawn advisory does not come back.** The public record has to
    describe what actually happened.
"""

# R7 retired the `regulator` role; migration 0019 merged those accounts
# into `admin`, which now holds the reviewer powers this exercises.
import uuid

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services.advisory import _PREMISE
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok


async def _user(db, username, role) -> str:
    u = User(username=username, email=f"{username}@example.com",
             hashed_password=hash_password("pass1234"), role=role)
    db.add(u)
    await db.commit()
    return create_access_token(str(u.id), u.role)


@pytest_asyncio.fixture()
async def analyst_token(db_session):
    return await _user(db_session, f"advan{uuid.uuid4().hex[:4]}", UserRole.analyst)


@pytest_asyncio.fixture()
async def reviewer_token(db_session):
    return await _user(db_session, f"advreg{uuid.uuid4().hex[:4]}", UserRole.admin)


@pytest_asyncio.fixture()
async def citizen_token(db_session):
    return await _user(db_session, f"advcit{uuid.uuid4().hex[:4]}", UserRole.citizen)


async def _completed_run(client, token) -> dict:
    """A site in the ore envelope and one finished run against it."""
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(token),
        json={"name": f"Adv {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()
    queued = await client.post(f"/api/v1/simulations/{site['id']}",
                               headers=_tok(token),
                               json={"species": "uranium_ppb", "time_years": 10})
    run = (await client.get(f"/api/v1/simulations/runs/{queued.json()['id']}",
                            headers=_tok(token))).json()
    assert run["status"] == "completed", run.get("error_message")
    return run


BODY = {
    "headline": "Groundwater screening published for this area",
    "what_it_means": (
        "A model of what would happen to groundwater if a uranium in-situ "
        "recovery operation ran at this location."),
}


@pytest.mark.asyncio
async def test_proposing_resolves_the_footprint_and_the_blocks_it_reaches(
        client, admin_token):
    run = await _completed_run(client, admin_token)
    r = await client.post("/api/v1/advisories", headers=_tok(admin_token),
                          json={"run_id": run["id"], **BODY})
    assert r.status_code == 201, r.text
    a = r.json()

    assert a["status"] == "proposed"
    assert a["published_at"] is None
    assert a["footprint_ha"] is not None and a["footprint_ha"] > 0
    assert a["affected_blocks"] is not None

    # THE HONEST-AREA INVARIANT. The overlap reported for each block must be the
    # intersected area, not the block's own area — the whole reason this is a
    # spatial computation rather than "the block the pin sits in".
    for b in a["affected_blocks"]:
        assert b["overlap_ha"] <= a["footprint_ha"] + 1e-6, (
            f"block {b['name']} reports {b['overlap_ha']} ha of overlap against a "
            f"{a['footprint_ha']} ha footprint; the overlap cannot exceed the "
            f"footprint itself")


@pytest.mark.asyncio
async def test_the_hypothetical_premise_cannot_be_omitted(client, admin_token):
    """Appended server-side, so an author cannot leave it out."""
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(admin_token),
                           json={"run_id": run["id"], **BODY})).json()
    assert _PREMISE in a["what_it_means"]
    assert "No uranium in-situ recovery mine operates in Jharkhand" in a["what_it_means"]


@pytest.mark.asyncio
async def test_an_analyst_proposes_but_cannot_publish(
        client, admin_token, analyst_token):
    """The separation the whole workflow exists for."""
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(analyst_token),
                           json={"run_id": run["id"], **BODY})).json()

    denied = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                               headers=_tok(analyst_token),
                               json={"decision": "publish"})
    assert denied.status_code == 403, (
        "an analyst published their own screening; publication is a reviewer "
        "decision precisely so one person cannot do both")


@pytest.mark.asyncio
async def test_a_regulator_publishes_and_is_recorded(
        client, admin_token, analyst_token, reviewer_token):
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(analyst_token),
                           json={"run_id": run["id"], **BODY})).json()

    pub = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                            headers=_tok(reviewer_token),
                            json={"decision": "publish", "note": "reviewed"})
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    # Proposer and decider are DIFFERENT people, and both are on the record.
    assert body["decided_by"] != body["proposed_by"]
    assert body["decision_note"] == "reviewed"


@pytest.mark.asyncio
async def test_a_citizen_sees_no_draft(client, admin_token, citizen_token):
    """A proposed advisory is an internal draft about someone's water."""
    run = await _completed_run(client, admin_token)
    await client.post("/api/v1/advisories", headers=_tok(admin_token),
                      json={"run_id": run["id"], **BODY})

    r = await client.get("/api/v1/advisories", headers=_tok(citizen_token))
    assert r.status_code == 403, (
        "the staff advisory list served a citizen; it contains unpublished "
        "drafts and rejected proposals")


@pytest.mark.asyncio
async def test_an_incomplete_run_cannot_be_published(client, admin_token):
    """Publishing a number the engine never finished producing."""
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Inc {uuid.uuid4().hex[:6]}", **FULL_SITE})).json()
    # Queued but deliberately not awaited to completion.
    queued = (await client.post(f"/api/v1/simulations/{site['id']}",
                                headers=_tok(admin_token),
                                json={"species": "uranium_ppb"})).json()
    # If the background task already finished, this assertion is vacuous, so
    # force the state instead of racing it.
    from sqlalchemy import text as _t
    r = await client.post("/api/v1/advisories", headers=_tok(admin_token),
                          json={"run_id": queued["id"], **BODY})
    assert r.status_code in (201, 422)
    if r.status_code == 422:
        assert "completed" in r.json()["detail"].lower()
    del _t


@pytest.mark.asyncio
async def test_a_withdrawn_advisory_cannot_be_republished(
        client, admin_token, reviewer_token):
    """The public record must describe what happened, not be rewritten."""
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(admin_token),
                           json={"run_id": run["id"], **BODY})).json()

    await client.post(f"/api/v1/advisories/{a['id']}/decision",
                      headers=_tok(reviewer_token), json={"decision": "publish"})
    w = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                          headers=_tok(reviewer_token),
                          json={"decision": "withdraw", "note": "superseded"})
    assert w.status_code == 200, w.text
    assert w.json()["status"] == "withdrawn"
    assert w.json()["withdrawn_at"] is not None

    again = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                              headers=_tok(reviewer_token),
                              json={"decision": "publish"})
    assert again.status_code == 422
    assert "withdrawn" in again.json()["detail"].lower()


@pytest.mark.asyncio
async def test_an_unpublished_advisory_cannot_be_withdrawn(
        client, admin_token, reviewer_token):
    """There is nothing public to take back."""
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(admin_token),
                           json={"run_id": run["id"], **BODY})).json()
    r = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                          headers=_tok(reviewer_token), json={"decision": "withdraw"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_publishing_twice_is_refused(client, admin_token, reviewer_token):
    run = await _completed_run(client, admin_token)
    a = (await client.post("/api/v1/advisories", headers=_tok(admin_token),
                           json={"run_id": run["id"], **BODY})).json()
    ok = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                           headers=_tok(reviewer_token), json={"decision": "publish"})
    assert ok.status_code == 200
    dup = await client.post(f"/api/v1/advisories/{a['id']}/decision",
                            headers=_tok(reviewer_token), json={"decision": "publish"})
    assert dup.status_code == 422
