"""Simulation workflow tests."""
import pytest
import uuid
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_trigger_simulation_requires_auth(client):
    """Unauthenticated requests should be rejected."""
    isr_id = str(uuid.uuid4())
    resp = await client.post(f"/api/v1/simulations/{isr_id}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trigger_simulation_missing_isr(client, admin_token):
    """Unknown ISR point should return 404."""
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/simulations/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Service raises ResourceNotFoundError → 404
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_get_simulation_not_found(client, admin_token):
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/simulations/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_isr_point_and_list(client, admin_token):
    """Full lifecycle: create ISR point, verify it appears in list."""
    create_resp = await client.post(
        "/api/v1/isr-points",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Test ISR Site Alpha",
            "injection_rate": 150.0,
            "location": {"type": "Point", "coordinates": [85.3, 23.5]},
        },
    )
    assert create_resp.status_code == 201
    isr_id = create_resp.json()["id"]

    list_resp = await client.get(
        "/api/v1/isr-points",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    ids = [item["id"] for item in list_resp.json()]
    assert isr_id in ids
