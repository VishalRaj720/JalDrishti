"""Audit trail: writes, denials, and access control on reading it."""
import pytest
import pytest_asyncio
from sqlalchemy import select, delete

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.services.auth import hash_password, create_access_token


@pytest_asyncio.fixture()
async def citizen_token(db_session):
    user = User(
        username="acitizen", email="citizen@example.com",
        hashed_password=hash_password("pass1234"), role=UserRole.citizen,
    )
    db_session.add(user)
    await db_session.commit()
    return create_access_token(str(user.id), user.role)


async def _entries(db, **filters):
    stmt = select(AuditLog)
    for k, v in filters.items():
        stmt = stmt.where(getattr(AuditLog, k) == v)
    return list((await db.execute(stmt)).scalars().all())


@pytest.mark.asyncio
async def test_successful_login_is_audited(client, db_session, admin_user):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login",
                             json={"email": "admin@test.com", "password": "admin123"})
    assert resp.status_code == 200

    rows = await _entries(db_session, action="login")
    assert len(rows) == 1
    assert rows[0].actor_label == "admin@test.com"
    assert rows[0].detail["role"] == "admin"


@pytest.mark.asyncio
async def test_failed_login_is_audited_with_the_attempted_identity(
        client, db_session, admin_user):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.post("/api/v1/auth/login",
                             json={"email": "admin@test.com", "password": "wrong"})
    assert resp.status_code == 401

    rows = await _entries(db_session, action="login_failed")
    assert len(rows) == 1
    # The attempted email is retained even though no user was authenticated —
    # repeated failures against one account are the signal worth keeping.
    assert rows[0].actor_label == "admin@test.com"
    assert rows[0].actor_id is None


@pytest.mark.asyncio
async def test_authorisation_denial_is_audited(client, db_session, citizen_token):
    """A 403 never reaches a handler; the middleware must still record it."""
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.get("/api/v1/users",
                            headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == 403

    rows = await _entries(db_session, action="access_denied")
    assert len(rows) == 1
    assert rows[0].actor_label == "citizen@example.com"
    assert rows[0].detail["denied"]["role"] == "citizen"


@pytest.mark.asyncio
async def test_mutating_request_is_audited_with_actor(client, db_session, admin_token):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    resp = await client.post(
        "/api/v1/isr-points",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Audited Site", "injection_rate": 100.0,
              "location": {"type": "Point", "coordinates": [85.3, 23.5]}},
    )
    assert resp.status_code == 201

    rows = await _entries(db_session, entity_type="isr-points")
    assert len(rows) == 1
    assert rows[0].action == "post:isr-points"
    assert rows[0].detail["status"] == 201


@pytest.mark.asyncio
async def test_reads_are_not_audited(client, db_session, admin_token):
    """Read traffic would bury the entries that matter."""
    await db_session.execute(delete(AuditLog))
    await db_session.commit()

    await client.get("/api/v1/districts",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert await _entries(db_session) == []


@pytest.mark.asyncio
async def test_health_is_exempt(client, db_session):
    await db_session.execute(delete(AuditLog))
    await db_session.commit()
    await client.get("/health")
    assert await _entries(db_session) == []


@pytest.mark.asyncio
async def test_audit_is_readable_by_admin(client, admin_token, admin_user):
    await client.post("/api/v1/auth/login",
                      json={"email": "admin@test.com", "password": "admin123"})
    resp = await client.get("/api/v1/audit",
                            headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert any(e["action"] == "login" for e in resp.json())


@pytest.mark.asyncio
async def test_audit_is_not_readable_by_citizen(client, citizen_token):
    resp = await client.get("/api/v1/audit",
                            headers={"Authorization": f"Bearer {citizen_token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_audit_has_no_write_or_delete_routes():
    from app.main import app
    for r in app.routes:
        if getattr(r, "path", "").startswith("/api/v1/audit"):
            assert r.methods - {"HEAD", "OPTIONS"} == {"GET"}, (
                "the audit log must not expose a write or delete route"
            )
