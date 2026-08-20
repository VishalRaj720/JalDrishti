"""The field-observation submit/review workflow.

Covers the nine acceptance checks for the workflow, plus the boundary that makes
it meaningful: a pending proposal must be invisible to anything that reads the
authoritative dataset.
"""

# R7 retired the `regulator` role; migration 0019 merged those accounts
# into `admin`, which now holds the reviewer powers this exercises.
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text, delete

from app.models.audit_log import AuditLog
from app.models.field_observation import FieldObservation
from app.models.user import User, UserRole
from app.models.monitoring_well import MonitoringWell
from app.services.auth import hash_password, create_access_token


async def _mk_user(db, username, email, role):
    u = User(username=username, email=email,
             hashed_password=hash_password("pass1234"), role=role)
    db.add(u)
    await db.commit()
    return u


@pytest_asyncio.fixture()
async def officer(db_session):
    return await _mk_user(db_session, "officer1", "officer1@example.com",
                          UserRole.field_officer)


@pytest_asyncio.fixture()
async def officer2(db_session):
    return await _mk_user(db_session, "officer2", "officer2@example.com",
                          UserRole.field_officer)


@pytest_asyncio.fixture()
async def reviewer(db_session):
    return await _mk_user(db_session, "reg1", "reg1@example.com",
                          UserRole.admin)


@pytest_asyncio.fixture()
async def analyst(db_session):
    return await _mk_user(db_session, "ana1", "ana1@example.com",
                          UserRole.analyst)


def _tok(u):
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role)}"}


@pytest_asyncio.fixture()
async def well(db_session):
    w = MonitoringWell(name="Test Well", location="SRID=4326;POINT(86.3 22.6)",
                       latitude=22.6, longitude=86.3)
    db_session.add(w)
    await db_session.commit()
    return w


ORE = {
    "observation_type": "ore_presence",
    "operation": "create",
    "payload": {
        "name": "Field sighting A", "longitude": 86.36, "latitude": 22.65,
        "ore_zone": "deposit", "uranium_grade_pct": 0.05,
        "observed_at": "2026-08-12T00:00:00Z", "notes": "surface outcrop",
    },
    "note": "spotted during survey",
}


# ── 1. field officer can submit ──────────────────────────────────────

@pytest.mark.asyncio
async def test_field_officer_can_submit(client, officer):
    r = await client.post("/api/v1/field-observations", headers=_tok(officer),
                          json=ORE)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["submitted_by"] == str(officer.id)
    assert body["applied_id"] is None


@pytest.mark.asyncio
async def test_field_officer_still_cannot_write_authoritative_tables(
        client, officer, well):
    """The submission endpoint is the ONLY write path they have."""
    r = await client.post("/api/v1/water-samples/bulk", headers=_tok(officer),
                          json={"well_id": str(well.id), "samples": []})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_payload_allowlist_rejects_unknown_fields(client, officer):
    bad = {**ORE, "payload": {**ORE["payload"], "synthetic": True}}
    r = await client.post("/api/v1/field-observations", headers=_tok(officer),
                          json=bad)
    assert r.status_code == 422
    assert "synthetic" in r.text


# ── 2. admin / reviewer can approve and reject ──────────────────────

@pytest.mark.asyncio
async def test_regulator_can_approve(client, officer, reviewer, db_session):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    r = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                          headers=_tok(reviewer), json={"review_note": "verified"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == str(reviewer.id)
    assert body["applied_id"] is not None

    n = (await db_session.execute(
        text("SELECT count(*) FROM ore_observations WHERE name = :n"),
        {"n": "Field sighting A"})).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_admin_can_reject_and_nothing_is_applied(
        client, officer, admin_token, db_session):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    r = await client.post(f"/api/v1/field-observations/{obs_id}/reject",
                          headers={"Authorization": f"Bearer {admin_token}"},
                          json={"review_note": "cannot corroborate"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["applied_id"] is None

    n = (await db_session.execute(
        text("SELECT count(*) FROM ore_observations"))).scalar_one()
    assert n == 0, "a rejected proposal must not reach the authoritative table"


@pytest.mark.asyncio
async def test_a_decided_proposal_cannot_be_reviewed_again(
        client, officer, reviewer):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                      headers=_tok(reviewer), json={})
    again = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                              headers=_tok(reviewer), json={})
    assert again.status_code == 409, "double-approval must not re-apply"


# ── 3. analyst cannot approve ────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyst_cannot_approve_or_reject(client, officer, analyst):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    for verb in ("approve", "reject"):
        r = await client.post(f"/api/v1/field-observations/{obs_id}/{verb}",
                              headers=_tok(analyst), json={})
        assert r.status_code == 403, f"analyst reached {verb}"


@pytest.mark.asyncio
async def test_field_officer_cannot_approve_anything(client, officer, officer2):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    r = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                          headers=_tok(officer2), json={})
    assert r.status_code == 403


# ── 4. a submitter cannot approve their own change ───────────────────

@pytest.mark.asyncio
async def test_submitter_cannot_approve_own_submission(client, admin_token):
    """`admin` is the one role that can both submit and review, so it is the
    only way to reach this case through the API — and it must still be refused."""
    H = {"Authorization": f"Bearer {admin_token}"}
    submitted = await client.post("/api/v1/field-observations", headers=H,
                                  json=ORE)
    assert submitted.status_code == 201, submitted.text
    obs_id = submitted.json()["id"]

    r = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                          headers=H, json={})
    assert r.status_code == 403
    assert "own" in r.text.lower()


@pytest.mark.asyncio
async def test_a_reviewer_who_submits_still_cannot_approve_their_own(
        client, reviewer):
    """R7 CHANGED THIS PROPERTY, and the change is worth stating plainly.

    This test used to assert that a reviewer could not submit at all -- keeping
    submission off the reviewer roles was what made "cannot approve your own"
    hard to reach by accident. Retiring `regulator` merged reviewers into
    `admin`, and admin has always been able to submit, so that separation by
    ROLE is gone.

    What is NOT gone is the separation that actually matters, and it never
    depended on the role split: `ck_field_obs_no_self_review` makes a row whose
    reviewer equals its submitter unrepresentable in the database. A reviewer
    can now file an observation, and still cannot be the one who accepts it.

    That is the honest post-merge invariant, so it is what is asserted.
    """
    created = await client.post("/api/v1/field-observations",
                                headers=_tok(reviewer), json=ORE)
    assert created.status_code == 201, created.text

    denied = await client.post(
        f"/api/v1/field-observations/{created.json()['id']}/approve",
        headers=_tok(reviewer), json={})
    assert denied.status_code == 403, (
        "a reviewer approved their own submission; the role merge must not have "
        "collapsed the submitter and the approver into one person")
    assert "own" in denied.text.lower()


@pytest.mark.asyncio
async def test_self_review_is_impossible_at_the_database(db_session, officer):
    """Separation of duties survives a service bug: the CHECK constraint makes
    the row unrepresentable."""
    obs = FieldObservation(
        observation_type="ore_presence", operation="create",
        target_table="ore_observations", proposed={"name": "x"},
        status="approved", submitted_by=officer.id,
        reviewed_by=officer.id, reviewed_at=datetime.now(timezone.utc),
    )
    db_session.add(obs)
    with pytest.raises(Exception) as exc:
        await db_session.commit()
    assert "ck_field_obs_no_self_review" in str(exc.value)
    await db_session.rollback()


# ── 5 + 6. pending does not affect data; approved does ───────────────

@pytest.mark.asyncio
async def test_pending_water_sample_is_absent_then_present_after_approval(
        client, officer, reviewer, db_session, well):
    async def count():
        return (await db_session.execute(
            text("SELECT count(*) FROM water_samples WHERE well_id = :w"),
            {"w": str(well.id)})).scalar_one()

    before = await count()

    submission = {
        "observation_type": "water_sample", "operation": "create",
        "payload": {"well_id": str(well.id),
                    "sampled_at": "2026-08-12T00:00:00Z",
                    "uranium_ppb": 91.5},
    }
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer),
                                json=submission)).json()["id"]

    # PENDING: the authoritative table is untouched, so nothing reading it —
    # any aggregate, report or calculation — can see this value.
    assert await count() == before
    leaked = (await db_session.execute(
        text("SELECT count(*) FROM water_samples WHERE uranium_ppb = 91.5"))
    ).scalar_one()
    assert leaked == 0, "pending field data reached the authoritative table"

    await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                      headers=_tok(reviewer), json={})

    # APPROVED: now it is authoritative.
    assert await count() == before + 1
    present = (await db_session.execute(
        text("SELECT count(*) FROM water_samples WHERE uranium_ppb = 91.5"))
    ).scalar_one()
    assert present == 1


@pytest.mark.asyncio
async def test_update_records_old_and_new_and_applies_on_approval(
        client, officer, reviewer, db_session, well):
    row_id = (await db_session.execute(text("""
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb,
                                   tds_derived, synthetic)
        VALUES (gen_random_uuid(), :w, now(), 10.0, false, false) RETURNING id
    """), {"w": str(well.id)})).scalar_one()
    await db_session.commit()

    obs = (await client.post("/api/v1/field-observations", headers=_tok(officer),
                             json={"observation_type": "water_sample",
                                   "operation": "update",
                                   "target_id": str(row_id),
                                   "payload": {"uranium_ppb": 42.0}})).json()
    assert obs["previous"]["uranium_ppb"] == 10.0
    assert obs["proposed"]["uranium_ppb"] == 42.0

    still = (await db_session.execute(
        text("SELECT uranium_ppb FROM water_samples WHERE id = :i"),
        {"i": str(row_id)})).scalar_one()
    assert still == 10.0, "a pending update changed the authoritative row"

    await client.post(f"/api/v1/field-observations/{obs['id']}/approve",
                      headers=_tok(reviewer), json={})
    now = (await db_session.execute(
        text("SELECT uranium_ppb FROM water_samples WHERE id = :i"),
        {"i": str(row_id)})).scalar_one()
    assert now == 42.0


@pytest.mark.asyncio
async def test_stale_proposal_is_refused_rather_than_clobbering(
        client, officer, reviewer, db_session, well):
    """If the target moved after submission, approving must not overwrite it."""
    row_id = (await db_session.execute(text("""
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb,
                                   tds_derived, synthetic)
        VALUES (gen_random_uuid(), :w, now(), 10.0, false, false) RETURNING id
    """), {"w": str(well.id)})).scalar_one()
    await db_session.commit()

    obs_id = (await client.post("/api/v1/field-observations", headers=_tok(officer),
                                json={"observation_type": "water_sample",
                                      "operation": "update",
                                      "target_id": str(row_id),
                                      "payload": {"uranium_ppb": 42.0}})).json()["id"]

    # somebody else edits the row in the meantime
    await db_session.execute(
        text("UPDATE water_samples SET uranium_ppb = 33.0 WHERE id = :i"),
        {"i": str(row_id)})
    await db_session.commit()

    r = await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                          headers=_tok(reviewer), json={})
    assert r.status_code == 409
    kept = (await db_session.execute(
        text("SELECT uranium_ppb FROM water_samples WHERE id = :i"),
        {"i": str(row_id)})).scalar_one()
    assert kept == 33.0, "the newer value was overwritten by a stale proposal"


# ── 7. everything is audited, with old and new values ────────────────

@pytest.mark.asyncio
async def test_submit_and_approve_are_audited_with_old_and_new(
        client, officer, reviewer, db_session, well):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    row_id = (await db_session.execute(text("""
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb,
                                   tds_derived, synthetic)
        VALUES (gen_random_uuid(), :w, now(), 7.0, false, false) RETURNING id
    """), {"w": str(well.id)})).scalar_one()
    await db_session.commit()

    obs_id = (await client.post("/api/v1/field-observations", headers=_tok(officer),
                                json={"observation_type": "water_sample",
                                      "operation": "update",
                                      "target_id": str(row_id),
                                      "payload": {"uranium_ppb": 55.0}})).json()["id"]
    await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                      headers=_tok(reviewer), json={"review_note": "ok"})

    rows = list((await db_session.execute(
        select(AuditLog).where(AuditLog.entity_id == obs_id)
        .order_by(AuditLog.id))).scalars().all())
    actions = [r.action for r in rows]
    assert "field_observation.submit" in actions
    assert "field_observation.approve" in actions

    sub = next(r for r in rows if r.action == "field_observation.submit")
    assert sub.actor_label == "officer1@example.com"
    assert sub.detail["old"]["uranium_ppb"] == 7.0
    assert sub.detail["new"]["uranium_ppb"] == 55.0

    app_ = next(r for r in rows if r.action == "field_observation.approve")
    assert app_.actor_label == "reg1@example.com"
    assert app_.detail["applied"] is True
    assert app_.detail["submitted_by"] == str(officer.id)


@pytest.mark.asyncio
async def test_rejection_is_audited_as_not_applied(
        client, officer, reviewer, db_session):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    await client.post(f"/api/v1/field-observations/{obs_id}/reject",
                      headers=_tok(reviewer), json={"review_note": "no"})
    row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "field_observation.reject")
    )).scalars().first()
    assert row is not None
    assert row.detail["applied"] is False
    assert row.detail["review_note"] == "no"


@pytest.mark.asyncio
async def test_denied_approval_attempt_is_audited(client, officer, analyst,
                                                  db_session):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    await client.post(f"/api/v1/field-observations/{obs_id}/approve",
                      headers=_tok(analyst), json={})
    denied = list((await db_session.execute(
        select(AuditLog).where(AuditLog.action == "access_denied"))).scalars().all())
    assert denied, "a refused approval attempt must appear in the audit trail"
    assert denied[0].detail["denied"]["role"] == "analyst"


# ── 8. withdrawal, and the submitter boundary ────────────────────────

@pytest.mark.asyncio
async def test_only_the_submitter_may_withdraw(client, officer, officer2):
    obs_id = (await client.post("/api/v1/field-observations",
                                headers=_tok(officer), json=ORE)).json()["id"]
    r = await client.post(f"/api/v1/field-observations/{obs_id}/withdraw",
                          headers=_tok(officer2), json={})
    assert r.status_code in (403, 404)
    ok = await client.post(f"/api/v1/field-observations/{obs_id}/withdraw",
                           headers=_tok(officer), json={})
    assert ok.status_code == 200
    assert ok.json()["status"] == "withdrawn"


@pytest.mark.asyncio
async def test_map_keeps_the_three_states_separate(client, officer, reviewer):
    """Three collections, not one list with a flag — a merged list invites a
    client to draw unreviewed or unsynced input as though it were in the model."""
    obs = await client.post("/api/v1/field-observations", headers=_tok(officer),
                            json=ORE)
    r = await client.get("/api/v1/field-observations/map", headers=_tok(reviewer))
    assert r.status_code == 200
    body = r.json()
    assert set(body["counts"]) == {"pending_review", "approved_pending_sync",
                                   "approved_in_model"}

    # red: submitted, not reviewed
    assert body["counts"]["pending_review"] == 1
    assert body["counts"]["approved_pending_sync"] == 0
    assert body["counts"]["approved_in_model"] == 0

    await client.post(f"/api/v1/field-observations/{obs.json()['id']}/approve",
                      headers=_tok(reviewer), json={})

    # amber: authoritative here, but Datasets/ has not been synced, so the
    # engine still does not see it
    body = (await client.get("/api/v1/field-observations/map",
                             headers=_tok(reviewer))).json()
    assert body["counts"]["pending_review"] == 0
    assert body["counts"]["approved_pending_sync"] == 1
    assert body["counts"]["approved_in_model"] == 0
