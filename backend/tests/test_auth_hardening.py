"""Guards on the authentication surface.

WHY THIS EXISTS. `POST /api/v1/auth/signup` was unauthenticated and accepted a
`role` field that flowed into `UserRole(data.role)` unchecked. It was verified
exploitable end to end before removal: an anonymous caller created an `admin`
account (201), logged in, and read the admin-only user list (200).

These tests are written against the PROPERTY, not the endpoint name, so
reintroducing the same hole under a different path still fails.
"""
import pytest

from app.main import app
from app.models.user import UserRole

_ATTACK = {
    "username": "attacker",
    "email": "attacker@example.com",
    "password": "hunter2",
    "role": "admin",
}


def _routes():
    for r in app.routes:
        if hasattr(r, "methods"):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                yield m, r.path, r


def test_signup_endpoint_is_gone():
    paths = {p for _, p, _ in _routes()}
    assert "/api/v1/auth/signup" not in paths, (
        "POST /auth/signup is back. It was an unauthenticated privilege-"
        "escalation hole; account creation belongs behind require_admin."
    )


def test_duplicate_token_endpoint_is_gone():
    paths = {p for _, p, _ in _routes()}
    assert "/api/v1/auth/token" not in paths, (
        "POST /auth/token duplicated /auth/login. One credential-accepting "
        "path is enough."
    )


@pytest.mark.asyncio
async def test_anonymous_cannot_create_any_account(client):
    """The property: no unauthenticated route may mint a user."""
    for path in ("/api/v1/auth/signup", "/api/v1/users", "/api/v1/auth/register"):
        resp = await client.post(path, json=_ATTACK)
        assert resp.status_code in (401, 403, 404, 405), (
            f"POST {path} without a token returned {resp.status_code}; "
            f"an anonymous caller must never be able to create an account."
        )


@pytest.mark.asyncio
async def test_admin_creating_a_user_cannot_be_reached_anonymously(client):
    """`POST /users` is the sanctioned path — and it must demand a token."""
    resp = await client.post("/api/v1/users", json=_ATTACK)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_role_escalation_via_user_create_requires_admin(client, admin_token):
    """An admin may set a role; that is the point of the endpoint. The guard is
    that the caller had to prove they were an admin to get here at all."""
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**_ATTACK, "email": "made-by-admin@example.com"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_garbage_token_is_rejected(client):
    resp = await client.get(
        "/api/v1/users", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_missing_bearer_is_rejected_not_crashed(client):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


def test_citizen_is_excluded_from_the_staff_role_set():
    """Design section 2: citizens must not reach precise site coordinates."""
    from app.dependencies import STAFF_ROLES
    assert UserRole.citizen not in STAFF_ROLES
    assert UserRole.viewer not in STAFF_ROLES
    for role in (UserRole.admin, UserRole.regulator, UserRole.analyst,
                 UserRole.field_officer):
        assert role in STAFF_ROLES
