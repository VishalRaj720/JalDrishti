"""GET /public/risk/at — the citizen tap.

Two things this must never do, both checked here rather than trusted:

  * leak model output or ISR geometry onto a public, unauthenticated surface;
  * report "sampled but never analysed for uranium" as a clean result.

The second is the defect R10 fixed on the citizen block list. A new endpoint
computing its own band from the same NULL is exactly how that regresses.
"""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_point_outside_every_block_is_reported_not_errored(client):
    """Tapping the sea must say so, not 404 and not silently return nothing."""
    r = await client.get("/api/v1/public/risk/at?lon=0&lat=0")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["inside_jharkhand"] is False
    assert "outside" in b["message"].lower()
    assert "No uranium mine" in b["what_this_is"]


@pytest.mark.asyncio
async def test_the_endpoint_is_public(client):
    """No Authorization header at all. This is the resident-facing surface."""
    r = await client.get("/api/v1/public/risk/at?lon=85.33&lat=23.36")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_bad_coordinates_are_rejected(client):
    for qs in ("lon=999&lat=0", "lon=0&lat=999", "lon=abc&lat=0", ""):
        r = await client.get(f"/api/v1/public/risk/at?{qs}")
        assert r.status_code == 422, f"{qs} -> {r.status_code}"


@pytest.mark.asyncio
async def test_response_carries_no_model_output_or_site_geometry(client):
    """The public contract: measurements only."""
    r = await client.get("/api/v1/public/risk/at?lon=86.35&lat=22.78")
    assert r.status_code == 200, r.text
    body = r.json()
    forbidden = {
        "isr_point_id", "isr_points", "plume", "geometry", "footprint",
        "migration_m", "affected_area_ha", "compliance_conc", "p10", "p90",
        "excursion_probability", "model_card_sha", "run_id",
    }
    leaked = forbidden & set(body)
    assert not leaked, f"citizen tap leaked model/site fields: {leaked}"
    assert body["what_this_is"].startswith("No uranium mine")


@pytest.mark.asyncio
async def test_sampled_but_untested_is_a_gap_not_a_clean_result(
        client, db_session, seeded_block):
    """Seed a block whose wells were sampled with uranium NULL, then tap it."""
    # This used to look for any block with geometry and skip when it found none
    # — which, in a database built from ORM metadata, was always. One of the
    # project's load-bearing rules ("no data is a monitoring gap, never a clean
    # result") was being checked by a test that never executed.
    row = (await db_session.execute(text("""
        SELECT b.id::text AS bid,
               ST_X(ST_Centroid(b.geometry)) AS lon,
               ST_Y(ST_Centroid(b.geometry)) AS lat
        FROM blocks b
        WHERE b.id = CAST(:bid AS uuid)
    """), {"bid": seeded_block["block_id"]})).mappings().first()
    assert row is not None, "the seeded_block fixture did not produce a block"

    await db_session.execute(text("""
        INSERT INTO monitoring_wells (id, name, block_id, location, latitude, longitude)
        VALUES (gen_random_uuid(), 'R11 untested well', CAST(:bid AS uuid),
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :lat, :lon)
    """), dict(row))
    well = (await db_session.execute(text(
        "SELECT id::text FROM monitoring_wells WHERE name = 'R11 untested well'"
    ))).scalar()
    # sampled, but uranium_ppb left NULL — the exact ambiguous case
    await db_session.execute(text("""
        INSERT INTO water_samples (id, well_id, sampled_at, ph)
        VALUES (gen_random_uuid(), CAST(:w AS uuid), now(), 7.1)
    """), {"w": well})
    await db_session.commit()

    r = await client.get(
        f"/api/v1/public/risk/at?lon={row['lon']}&lat={row['lat']}")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["inside_jharkhand"] is True
    assert b["samples"] >= 1
    assert b["uranium_tests"] == 0
    # R14 widened the band from uranium alone to every measured HEALTH
    # determinand, so the label for this case is now "Not tested" rather than
    # "Not tested for uranium" — this fixture analyses NOTHING (only pH), so
    # naming uranium specifically would understate the gap. The guarantee the
    # test exists for is unchanged and is asserted below it: whatever the label
    # says, it must never read as a clean result.
    assert b["band"] == "Not tested", (
        f"band was {b['band']!r} — a sampled-but-unanalysed block must never "
        f"read as a clean result")
    assert b["band"] not in ("Low concern", "No data")
    assert "not a clean result" in b["what_it_means"]
    # and the specific substances nobody looked for are named
    assert "uranium" in b["untested_health"]
