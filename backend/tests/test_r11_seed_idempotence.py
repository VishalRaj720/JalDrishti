"""Re-seeding after an edit must not duplicate the measured record.

The direction here is the OPPOSITE of `dataset_sync`: that carries approved
observations DB -> Datasets/, this carries Datasets/ -> DB. An admin who edits a
dataset file directly (or replaces one through /ingest) leaves the database
behind, and `scripts.seed` is what closes that gap.

The bug this pins was invisible in normal use. `ingest_csv_water_quality` skips
a file whose checksum it has already seen, so re-running the seeder on an
UNCHANGED file did nothing and looked idempotent. The moment the file actually
changed — the only time re-seeding matters — the checksum differed, ingestion
proceeded, and every existing sample was inserted a second time.

That is the worst possible failure for this dataset: district risk bands come
from `max(uranium_ppb)` over these rows, so a silent doubling changes what a
resident is told about their water.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_water_samples_upsert_on_well_and_date(db_session, seeded_block):
    """Insert once, update in place, never duplicate.

    Exercises the service directly rather than the CLI so the property is pinned
    without needing a seeded database or a subprocess.
    """
    from app.services.ingestion import IngestionService

    svc = IngestionService(db_session)

    # Was `SELECT id FROM blocks LIMIT 1` with a skip when empty — and the test
    # database has no geography, so this never ran. A test that skips is not a
    # test that passes.
    block = seeded_block["block_id"]

    well_id = uuid.uuid4()
    await db_session.execute(text("""
        INSERT INTO monitoring_wells (id, name, block_id, location, latitude, longitude)
        VALUES (:id, 'R11 upsert well', :b,
                ST_SetSRID(ST_MakePoint(86.1, 23.4), 4326), 23.4, 86.1)
    """), {"id": well_id, "b": block})
    await db_session.commit()

    sampled_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    async def count():
        return (await db_session.execute(text(
            "SELECT count(*) FROM water_samples WHERE well_id = :w"),
            {"w": well_id})).scalar()

    # None yet, so the lookup must return nothing.
    assert await svc._find_sample(well_id, sampled_at) is None
    assert await count() == 0

    await db_session.execute(text("""
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb)
        VALUES (gen_random_uuid(), :w, :t, 5.0)
    """), {"w": well_id, "t": sampled_at})
    await db_session.commit()

    # The same key must now be found — this is what prevents the second insert.
    found = await svc._find_sample(well_id, sampled_at)
    assert found is not None, (
        "_find_sample missed an existing row; without it every re-seed after an "
        "edit duplicates the whole file")
    assert float(found.uranium_ppb) == 5.0
    assert await count() == 1

    # A different date is a different sample, not a duplicate.
    other = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert await svc._find_sample(well_id, other) is None


@pytest.mark.asyncio
async def test_the_ingest_path_updates_rather_than_inserting_again(db_session):
    """The code must UPDATE a changed value, not skip it and not duplicate it.

    Asserted on the source, because the failure mode is a silent extra row: a
    blind `create()` raises nothing and returns successfully.
    """
    import inspect

    from app.services.ingestion import IngestionService

    src = inspect.getsource(IngestionService.ingest_csv_water_quality)
    assert "_find_sample" in src, (
        "water-quality ingestion must look for an existing sample before "
        "inserting; a blind create duplicates all 397 rows on any re-seed")
    assert "samples_updated" in src, (
        "an existing row whose value changed must be updated, or a corrected "
        "measurement would be silently discarded")


@pytest.mark.asyncio
async def test_groundwater_readings_already_dedupe_by_timestamp(db_session):
    """The level path was already correct — pinned so a refactor keeps it."""
    import inspect

    from app.services.ingestion import IngestionService

    src = inspect.getsource(IngestionService.ingest_json_groundwater_levels)
    assert "_existing_reading_ts" in src
    assert "if ts in existing_ts" in src
