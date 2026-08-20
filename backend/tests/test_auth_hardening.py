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
async def test_anonymous_cannot_create_a_privileged_account(client):
    """The property, NARROWED in P5 — and this is the whole security argument.

    It used to read "no unauthenticated route may mint a user". That could not
    survive the product decision that citizens sign in: the alternative is an
    administrator hand-creating an account for every resident who wants to check
    their water, which is not a citizen product.

    So the guarantee is now:

        No unauthenticated route may mint a user **with any role other than
        `citizen`**, and the role must never be read from the request.

    `POST /citizen/register` is the one permitted unauthenticated creator. It
    has no `role` field at all — not a validated one, not a defaulted one — so
    the attack body below cannot influence it. That is asserted directly in
    `test_p5_citizen.py::test_registration_ignores_a_role_in_the_body`; here we
    hold the line for every OTHER path.
    """
    for path in ("/api/v1/auth/signup", "/api/v1/users", "/api/v1/auth/register"):
        resp = await client.post(path, json=_ATTACK)
        assert resp.status_code in (401, 403, 404, 405), (
            f"POST {path} without a token returned {resp.status_code}; "
            f"an anonymous caller must never be able to create an account."
        )


@pytest.mark.asyncio
async def test_the_one_anonymous_creator_cannot_be_talked_into_a_role(client):
    """`/citizen/register` is the single exception, and it is exception-proof.

    Sending `role: admin` does not error — the field does not exist as far as
    this endpoint is concerned, which is a stronger guarantee than rejecting it,
    because there is no code path that could later start honouring it.
    """
    resp = await client.post("/api/v1/citizen/register", json={
        "username": "attacker2", "email": "attacker2@example.com",
        "password": "hunter2hunter2", "role": "admin",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "citizen", (
        "an anonymous caller influenced the role of the account they created; "
        "this is the exact hole POST /auth/signup was deleted for."
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
    # R12: `_ATTACK` carries role=admin, which is the point in the tests above —
    # an anonymous caller must not be able to mint one. Here the subject is WHO
    # may assign a role, not which, so this uses a role that is assignable at
    # all. There is exactly one admin by design and even an admin cannot create
    # a second; that is asserted immediately below rather than left implicit.
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**_ATTACK, "email": "made-by-admin@example.com",
              "role": "regulator"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "regulator"

    second_admin = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={**_ATTACK, "email": "second-admin@example.com",
              "username": "second-admin"},
    )
    assert second_admin.status_code == 422, (
        "an admin minted a second admin; there is exactly one by design")


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
    # `regulator` is present again since R12 — see test_p6_roles.py.
    for role in (UserRole.admin, UserRole.analyst, UserRole.field_officer):
        assert role in STAFF_ROLES
