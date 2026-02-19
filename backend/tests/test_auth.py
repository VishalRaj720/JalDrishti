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
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_signup(client):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "username": "newuser",
            "email": "newuser@test.com",
            "password": "pass1234",
            "role": "viewer",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "newuser@test.com"


@pytest.mark.asyncio
async def test_signup_duplicate_email(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "username": "anothername",
            "email": "admin@test.com",
            "password": "pass1234",
        },
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_refresh_token(client, admin_user):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.com", "password": "admin123"},
    )
    refresh_token = login_resp.json()["refresh_token"]
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_logout(client):
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
