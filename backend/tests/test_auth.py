"""Auth endpoint tests."""
import pytest


@pytest.mark.asyncio
async def test_login_success(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "admin123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


# These two used to POST /auth/signup anonymously. That endpoint was a
# privilege-escalation hole and was deleted in P2, so the same behaviour is
# tested where it now legitimately lives: behind require_admin on POST /users.
# See tests/test_auth_hardening.py for the guards that keep it deleted.


@pytest.mark.asyncio
async def test_admin_can_create_a_user(client, admin_token):
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "pass1234",
            "role": "citizen",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "newuser@example.com"
    assert resp.json()["role"] == "citizen"


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client, admin_token, admin_user):
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "anothername",
            "email": "admin@test.com",
            "password": "pass1234",
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_logout(client):
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
