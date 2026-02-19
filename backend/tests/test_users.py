"""User management endpoint tests."""
import pytest


@pytest.mark.asyncio
async def test_list_users_as_admin(client, admin_user, admin_token):
    resp = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_user_as_admin(client, admin_token):
    resp = await client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "username": "analystuser",
            "email": "analyst2@test.com",
            "password": "analyst123",
            "role": "analyst",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "analyst"


@pytest.mark.asyncio
async def test_get_user(client, admin_user, admin_token):
    resp = await client.get(
        f"/api/v1/users/{admin_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_delete_user_as_admin(client, db_session, admin_token):
    # Create a user to delete
    from app.models.user import User, UserRole
    from app.services.auth import hash_password
    import uuid
    u = User(
        id=uuid.uuid4(),
        username="todelete",
        email="delete@test.com",
        hashed_password=hash_password("pass"),
        role=UserRole.viewer,
    )
    db_session.add(u)
    await db_session.commit()
    resp = await client.delete(
        f"/api/v1/users/{u.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204
