"""The admin / regulator boundary.

R7 retired `regulator` on the reasoning that `admin` already held all four of
its powers. R12 restores it, because that reasoning had it backwards: the powers
should never have been the same. Accepting a field officer's evidence into the
record and operating the pipeline that consumes it are different jobs, and
collapsing them meant the only person who could approve a submission was also
the only person who could rewrite the file it lands in.

    regulator   review the queue, approve, reject. Many of them.
    admin       everything else, including every dataset and model operation.
                Exactly one.

WHAT THIS FILE USED TO ASSERT. That `regulator` was retired and nothing could
mint one. Those three tests are gone because the product deliberately reversed
that decision — not because they were inconvenient. Everything here that was
still true was kept, in particular `test_an_analyst_still_cannot_publish`: the
separation that actually mattered was never the label, it is that the person who
PROPOSES a public screening is not the person who PUBLISHES it.

THE FAILURE MODE THIS FILE EXISTS TO CATCH. A role that passes a FastAPI guard
but is missing from the row-level policies gets an empty result, not an error.
A regulator would load the review queue, see nothing, and have `approve` report
success while updating zero rows — the same shape as the bug that left this
product with eight published advisories and an empty `alerts` table. So the
boundary is asserted over HTTP, against the database, not by reading guards.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.dependencies import (STAFF_ROLES, require_admin, require_field_reviewer,
                              require_reviewer)
from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok


async def _user(db_session, role: UserRole, prefix="r12") -> User:
    u = User(username=f"{prefix}{uuid.uuid4().hex[:6]}",
             email=f"{prefix}{uuid.uuid4().hex[:6]}@example.com",
             hashed_password=hash_password("pass1234"), role=role)
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture()
async def analyst_token(db_session):
    return create_access_token(*_id_role(await _user(db_session, UserRole.analyst)))


@pytest_asyncio.fixture()
async def regulator_token(db_session):
    return create_access_token(*_id_role(await _user(db_session, UserRole.regulator)))


@pytest_asyncio.fixture()
async def officer_token(db_session):
    return create_access_token(
        *_id_role(await _user(db_session, UserRole.field_officer)))


def _id_role(u: User):
    return str(u.id), u.role


# ── the vocabulary ───────────────────────────────────────────────────


def test_regulator_is_a_staff_role_again():
    """Staff because the review queue lives behind `require_staff`. A regulator
    that is not staff cannot see the thing it exists to decide on."""
    assert UserRole.regulator in STAFF_ROLES
    assert set(STAFF_ROLES) == {UserRole.admin, UserRole.analyst,
                                UserRole.field_officer, UserRole.regulator}


def test_deciding_on_a_submission_admits_the_regulator():
    assert require_field_reviewer.allowed_roles == frozenset(
        {UserRole.admin, UserRole.regulator})


def test_publishing_to_residents_stays_admin_only():
    """Deliberately NOT given to the regulator.

    Accepting evidence into the record and announcing a modelled result to a
    village are different decisions. R12 restored the first and left the second
    where it was.
    """
    assert require_reviewer.allowed_roles == frozenset({UserRole.admin})
    assert require_admin.allowed_roles == frozenset({UserRole.admin})


# ── what a regulator may do ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_regulator_can_see_the_queue_and_approve(
        client, db_session, officer_token, regulator_token, seeded_block):
    """The whole purpose of the role, end to end over HTTP.

    Asserted on the DATABASE as well as the response, because the interesting
    failure here is not a 403 — it is a 200 that changed nothing because RLS
    quietly refused the UPDATE.
    """
    sub = await client.post("/api/v1/field-observations", headers=_tok(officer_token),
                            json={"observation_type": "ore_presence",
                                  "operation": "create", "note": "R12 probe",
                                  "payload": {"name": f"R12 {uuid.uuid4().hex[:5]}",
                                              "longitude": 86.35, "latitude": 22.65,
                                              "ore_zone": "deposit",
                                              "observed_at": "2026-08-20T09:00:00Z"}})
    assert sub.status_code == 201, sub.text
    obs_id = sub.json()["id"]

    listed = await client.get("/api/v1/field-observations?limit=50",
                              headers=_tok(regulator_token))
    assert listed.status_code == 200, listed.text
    assert any(o["id"] == obs_id for o in listed.json()), (
        "the regulator could not see the submission it is meant to decide on — "
        "check `field_obs_read`; an RLS policy that omits the role returns an "
        "empty list rather than an error")

    ok = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                           headers=_tok(regulator_token),
                           json={"review_note": "accepted by a regulator"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"

    row = (await db_session.execute(text(
        "SELECT status, reviewed_by FROM field_observations WHERE id = :i"),
        {"i": obs_id})).first()
    assert row[0] == "approved", (
        "the API said approved and the row did not change — the UPDATE was "
        "refused by row-level security and reported success")
    assert row[1] is not None, "the decision recorded no reviewer"


@pytest.mark.asyncio
async def test_a_regulator_can_reject(
        client, db_session, officer_token, regulator_token, seeded_block):
    sub = await client.post("/api/v1/field-observations", headers=_tok(officer_token),
                            json={"observation_type": "ore_presence",
                                  "operation": "create",
                                  "payload": {"name": f"R12r {uuid.uuid4().hex[:5]}",
                                              "longitude": 86.36, "latitude": 22.66,
                                              "ore_zone": "deposit",
                                              "observed_at": "2026-08-20T09:00:00Z"}})
    obs_id = sub.json()["id"]

    r = await client.post(f"/api/v1/field-observations/{obs_id}/reject",
                          headers=_tok(regulator_token),
                          json={"review_note": "insufficient evidence"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_the_regulators_decision_reaches_the_audit_trail(
        client, db_session, officer_token, regulator_token, seeded_block):
    """Required by the role's definition: the decision is recorded.

    The regulator cannot READ the audit log — that is an operator power — but
    their decisions are written to it by the service, like everyone else's.
    """
    sub = await client.post("/api/v1/field-observations", headers=_tok(officer_token),
                            json={"observation_type": "ore_presence",
                                  "operation": "create",
                                  "payload": {"name": f"R12a {uuid.uuid4().hex[:5]}",
                                              "longitude": 86.37, "latitude": 22.67,
                                              "ore_zone": "deposit",
                                              "observed_at": "2026-08-20T09:00:00Z"}})
    obs_id = sub.json()["id"]
    await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                      headers=_tok(regulator_token), json={"review_note": "ok"})

    await db_session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    n = (await db_session.execute(text("""
        SELECT count(*) FROM audit_log
        WHERE entity_id = :i AND action LIKE 'field_observation%'
    """), {"i": obs_id})).scalar()
    assert n and n > 0, "the regulatory decision left no audit entry"


# ── what a regulator may NOT do ──────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/v1/dataset-sync/ore", {}),
    ("POST", "/api/v1/dataset-sync/water-quality", {}),
    ("POST", "/api/v1/dataset-sync/groundwater-levels", {}),
    ("POST", "/api/v1/dataset-sync/all", {}),
    ("POST", "/api/v1/model-ops/seed-database", {}),
    ("POST", "/api/v1/model-ops/factory-reset", {"confirm": "RESET"}),
    ("POST", "/api/v1/model-ops/recompute-baselines", {}),
    ("POST", "/api/v1/model-ops/rebuild-flow-field", {}),
    ("POST", "/api/v1/model-ops/model-backups", {}),
    ("GET", "/api/v1/audit?limit=5", None),
    ("GET", "/api/v1/users", None),
    ("POST", "/api/v1/users", {"username": "x", "email": "x@y.com",
                               "password": "pass1234", "role": "admin"}),
])
async def test_a_regulator_is_refused_every_admin_operation(
        client, regulator_token, method, path, body):
    """The boundary that makes the split worth having.

    A regulator accepts evidence. Writing that evidence into `Datasets/`, seeding
    it back into the database, resetting either, or minting another operator are
    all admin work — and a regulator hits the same 403 a citizen would.
    """
    h = _tok(regulator_token)
    r = (await client.get(path, headers=h) if method == "GET"
         else await client.post(path, headers=h, json=body))
    assert r.status_code == 403, (
        f"{method} {path} answered {r.status_code} for a regulator; it must be "
        f"403 — dataset and account operations are admin-only")


@pytest.mark.asyncio
async def test_approval_does_not_touch_the_datasets(
        client, db_session, officer_token, regulator_token, seeded_block):
    """The most important guarantee in this change.

    Approval records a decision. It must not write into `Datasets/`, sync, or
    trigger any admin-only dataset operation — those stay a separate, deliberate
    act by an admin. Verified by the observation's own sync marker: approved and
    NOT synced is the correct state immediately after a regulatory decision.
    """
    sub = await client.post("/api/v1/field-observations", headers=_tok(officer_token),
                            json={"observation_type": "ore_presence",
                                  "operation": "create",
                                  "payload": {"name": f"R12s {uuid.uuid4().hex[:5]}",
                                              "longitude": 86.38, "latitude": 22.68,
                                              "ore_zone": "deposit",
                                              "observed_at": "2026-08-20T09:00:00Z"}})
    obs_id = sub.json()["id"]

    approved = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                                 headers=_tok(regulator_token), json={})
    assert approved.status_code == 200, approved.text

    body = approved.json()
    assert body["status"] == "approved"
    assert body["synced_to_dataset_at"] is None, (
        "approving a submission marked it as written into Datasets/. Approval "
        "and dataset synchronisation are deliberately separate operations, and "
        "sync is admin-only")
    assert body["dataset_sync_ref"] is None


# ── exactly one admin ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_second_admin_cannot_be_created(client, admin_token):
    """One admin, by design.

    A second admin is not a convenience — it is a second person who can rewrite
    the evidence base and reset the model. The role for a second operator is
    `regulator`, and there may be as many of those as needed.
    """
    r = await client.post("/api/v1/users", headers=_tok(admin_token), json={
        "username": f"second{uuid.uuid4().hex[:5]}",
        "email": f"second{uuid.uuid4().hex[:5]}@example.com",
        "password": "pass1234", "role": "admin"})
    assert r.status_code == 422, r.text
    assert "regulator" in r.json()["detail"].lower(), (
        "the refusal should point at the role that IS available")


@pytest.mark.asyncio
async def test_an_existing_user_cannot_be_promoted_to_admin(
        client, admin_token, db_session):
    """The other door, and the one a UI makes easy: pick a user, change the
    dropdown, save."""
    victim = await _user(db_session, UserRole.analyst, prefix="promote")
    r = await client.put(f"/api/v1/users/{victim.id}", headers=_tok(admin_token),
                         json={"role": "admin"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_many_regulators_are_allowed(client, admin_token, db_session):
    """The counterpart: the role that is meant to scale, does."""
    made = []
    for _ in range(3):
        r = await client.post("/api/v1/users", headers=_tok(admin_token), json={
            "username": f"reg{uuid.uuid4().hex[:6]}",
            "email": f"reg{uuid.uuid4().hex[:6]}@example.com",
            "password": "pass1234", "role": "regulator"})
        assert r.status_code == 201, r.text
        made.append(r.json()["id"])
    assert len(made) == 3

    n = (await db_session.execute(text(
        "SELECT count(*) FROM users WHERE role = 'regulator'"))).scalar()
    assert n >= 3


# ── the separation that predates all of this, and must survive it ────


@pytest.mark.asyncio
async def test_an_analyst_still_cannot_publish(client, admin_token, analyst_token):
    """Kept verbatim from the R7 version.

    Restoring the regulator must not disturb the older, more important rule:
    the person who proposes a public screening is not the person who publishes
    it. Asserted end to end rather than by reading the guard, because the guard
    is exactly what a refactor would get wrong.
    """
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"R12 {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()

    adv = await client.post("/api/v1/advisories", headers=_tok(analyst_token), json={
        "run_id": run["id"], "headline": "Screening published for this area",
        "what_it_means": "A model of what would happen if an ISR operation ran here."})
    assert adv.status_code == 201, adv.text

    denied = await client.post(f"/api/v1/advisories/{adv.json()['id']}/decision",
                               headers=_tok(analyst_token), json={"decision": "publish"})
    assert denied.status_code == 403, (
        "an analyst published their own screening; the proposer and the decider "
        "must not collapse into one person")


@pytest.mark.asyncio
async def test_a_regulator_cannot_publish_an_advisory(
        client, admin_token, regulator_token):
    """Restoring the role must not hand it publication either."""
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"R12p {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()
    adv = (await client.post("/api/v1/advisories", headers=_tok(admin_token), json={
        "run_id": run["id"], "headline": "Screening published for this area",
        "what_it_means": "A model of what would happen if an ISR operation ran here."
    })).json()

    denied = await client.post(f"/api/v1/advisories/{adv['id']}/decision",
                               headers=_tok(regulator_token),
                               json={"decision": "publish"})
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_citizen_copy_credits_the_authority_not_a_named_role(
        client, admin_token):
    """A regulator exists again but does not publish, so crediting one would
    still be false. The copy names the institution, which is true either way."""
    from app.api.v1.citizen import _WHAT_THIS_IS
    assert "regulator" not in _WHAT_THIS_IS.lower()
    assert "authority" in _WHAT_THIS_IS.lower()


# ── reading is allowed; only ADMIN writes ────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/datasets",
    "/api/v1/dataset-sync/status",
    "/api/v1/model-ops/status",
    "/api/v1/model-ops/model",
])
async def test_a_regulator_may_READ_the_dataset_and_model_state(
        client, regulator_token, path):
    """The rule is "only admin WRITES", not "only admin looks".

    R12 first blocked these for the regulator and that was wrong. A reviewer
    deciding whether a finding is plausible needs to see what the model and the
    datasets currently hold; a role that can see nothing but a queue cannot
    judge what it is deciding about. Blocking reads never protected the data —
    every sync, seed and reset is a POST behind `require_admin` — it only made
    the role harder to use.
    """
    r = await client.get(path, headers=_tok(regulator_token))
    assert r.status_code == 200, (
        f"{path} answered {r.status_code} for a regulator; reading dataset and "
        f"model state is allowed for every staff role — only writes are "
        f"admin-only")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/datasets",
    "/api/v1/dataset-sync/status",
    "/api/v1/model-ops/status",
])
async def test_analyst_and_officer_keep_the_access_they_had(
        client, analyst_token, officer_token, path):
    """Unchanged by R12, and asserted so it stays that way."""
    for tok, who in ((analyst_token, "analyst"), (officer_token, "field_officer")):
        r = await client.get(path, headers=_tok(tok))
        assert r.status_code == 200, (
            f"{path} answered {r.status_code} for {who}; R12 must not change "
            f"what analysts and field officers can reach")
