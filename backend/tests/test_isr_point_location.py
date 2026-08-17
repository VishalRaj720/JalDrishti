"""`GET /isr-points` must return coordinates.

WHY THIS EXISTS. `IsrPointResponse` accepted `location` on create and update but
never declared it as an output field, so every read returned a site with no
coordinates. Nothing failed: the API answered 200, the registry rendered a dash,
and the Map Console silently plotted nothing. Found in P4 the first time a
client actually tried to draw a site.

Design §3.2 calls the site registry "the heart of the product". A site the
product cannot locate is not one.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture()
async def site(db_session):
    rid = (await db_session.execute(text("""
        INSERT INTO isr_points (id, name, location, injection_rate_m3_day)
        VALUES (gen_random_uuid(), 'Location Test Site',
                ST_SetSRID(ST_MakePoint(86.36, 22.65), 4326), 1000)
        RETURNING id
    """))).scalar_one()
    await db_session.commit()
    return rid


@pytest.mark.asyncio
async def test_list_returns_geojson_location(client, admin_token, site):
    r = await client.get("/api/v1/isr-points",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    row = next(s for s in r.json() if s["id"] == str(site))
    assert row["location"] is not None, "the registry returned a site with no coordinates"
    assert row["location"]["type"] == "Point"
    lon, lat = row["location"]["coordinates"]
    assert lon == pytest.approx(86.36)
    assert lat == pytest.approx(22.65)


@pytest.mark.asyncio
async def test_detail_returns_geojson_location(client, admin_token, site):
    r = await client.get(f"/api/v1/isr-points/{site}",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["location"]["coordinates"] == [pytest.approx(86.36),
                                                   pytest.approx(22.65)]


@pytest.mark.asyncio
async def test_created_site_round_trips_its_location(client, admin_token):
    """Create with a GeoJSON point, read it back unchanged."""
    created = await client.post(
        "/api/v1/isr-points",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": f"RoundTrip {uuid.uuid4().hex[:6]}", "injection_rate_m3_day": 500,
              "location": {"type": "Point", "coordinates": [85.9, 23.4]}})
    assert created.status_code == 201
    body = created.json()
    assert body["location"]["coordinates"] == [pytest.approx(85.9),
                                               pytest.approx(23.4)]


@pytest.mark.asyncio
async def test_a_site_without_a_location_is_null_not_an_error(client, admin_token,
                                                              db_session):
    """The column is nullable; the serializer must cope rather than 500."""
    rid = (await db_session.execute(text("""
        INSERT INTO isr_points (id, name, injection_rate_m3_day)
        VALUES (gen_random_uuid(), 'No Location Site', 100) RETURNING id
    """))).scalar_one()
    await db_session.commit()
    r = await client.get(f"/api/v1/isr-points/{rid}",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert r.json()["location"] is None
