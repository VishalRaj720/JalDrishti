"""Dataset sync: the three states, and the ore export.

The sync writes to real files under `Datasets/`, so every test that exercises it
works on a copy and restores the originals. A test suite that mutates tracked
data files is a test suite nobody can run twice.
"""

# R7 retired the `regulator` role; migration 0019 merged those accounts
# into `admin`, which now holds the reviewer powers this exercises.
import shutil
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import User, UserRole
from app.services import dataset_sync as ds
from app.services.auth import hash_password, create_access_token

ORE = {
    "observation_type": "ore_presence", "operation": "create",
    "payload": {"name": "Sync Test Deposit", "longitude": 85.90,
                "latitude": 23.40, "ore_zone": "deposit",
                "uranium_grade_pct": 0.042,
                "observed_at": "2026-08-12T00:00:00Z",
                "notes": "outcrop seen during survey"},
}


async def _mk(db, u, e, role):
    user = User(username=u, email=e, hashed_password=hash_password("pass1234"),
                role=role)
    db.add(user)
    await db.commit()
    return user


def _tok(u):
    return {"Authorization": f"Bearer {create_access_token(str(u.id), u.role)}"}


@pytest_asyncio.fixture()
async def officer(db_session):
    return await _mk(db_session, "syncoff", "syncoff@example.com",
                     UserRole.field_officer)


@pytest_asyncio.fixture()
async def reviewer(db_session):
    return await _mk(db_session, "syncreg", "syncreg@example.com",
                     UserRole.admin)


@pytest_asyncio.fixture()
async def analyst(db_session):
    return await _mk(db_session, "syncana", "syncana@example.com",
                     UserRole.analyst)


@pytest.fixture()
def datasets_restored():
    """Snapshot both ore files and put them back afterwards."""
    originals = {p: p.read_bytes() for p in (ds.ORE_CSV, ds.UDEPO_XLSX)
                 if p.exists()}
    yield
    for p, data in originals.items():
        p.write_bytes(data)
    for p in (ds.ORE_CSV, ds.UDEPO_XLSX):
        for bak in p.parent.glob(p.name + ".*.bak"):
            bak.unlink()
    ds.invalidate_ml_caches()


async def _approved_ore(client, officer, reviewer):
    obs = await client.post("/api/v1/field-observations", headers=_tok(officer),
                            json=ORE)
    assert obs.status_code == 201, obs.text
    oid = obs.json()["id"]
    ok = await client.post(f"/api/v1/field-observations/{oid}/approve",
                           headers=_tok(reviewer), json={})
    assert ok.status_code == 200, ok.text
    return oid


# ── the three states ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_states_progress_red_amber_green(
        client, db_session, officer, reviewer, admin_token, datasets_restored):
    H = {"Authorization": f"Bearer {admin_token}"}

    obs = await client.post("/api/v1/field-observations", headers=_tok(officer),
                            json=ORE)
    oid = obs.json()["id"]

    # RED — pending review
    s = (await client.get("/api/v1/dataset-sync/status", headers=H)).json()
    assert s["pending_review"] == 1
    assert s["approved_pending_sync"] == 0

    await client.post(f"/api/v1/field-observations/{oid}/approve",
                      headers=_tok(reviewer), json={})

    # AMBER — approved, authoritative here, not in the model
    s = (await client.get("/api/v1/dataset-sync/status", headers=H)).json()
    assert s["pending_review"] == 0
    assert s["approved_pending_sync"] == 1
    assert s["approved_in_model"] == 0
    assert "1 approved observation(s) are not yet in the model." in s["message"]

    r = await client.post("/api/v1/dataset-sync/ore", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["synced"] == 1

    # GREEN — synced
    s = (await client.get("/api/v1/dataset-sync/status", headers=H)).json()
    assert s["approved_pending_sync"] == 0
    assert s["approved_in_model"] == 1
    assert s["message"] == "All approved observations are reflected in the model."


@pytest.mark.asyncio
async def test_map_separates_the_three_states(
        client, officer, reviewer, admin_token, datasets_restored):
    H = {"Authorization": f"Bearer {admin_token}"}
    await _approved_ore(client, officer, reviewer)

    m = (await client.get("/api/v1/field-observations/map", headers=H)).json()
    assert m["counts"]["approved_pending_sync"] == 1
    assert m["counts"]["approved_in_model"] == 0

    await client.post("/api/v1/dataset-sync/ore", headers=H)
    m = (await client.get("/api/v1/field-observations/map", headers=H)).json()
    assert m["counts"]["approved_pending_sync"] == 0
    assert m["counts"]["approved_in_model"] == 1


@pytest.mark.asyncio
async def test_unapproved_rows_can_never_claim_to_be_synced(db_session, officer):
    """`ck_field_obs_synced_only_when_approved` keeps amber/green meaningful."""
    with pytest.raises(Exception) as exc:
        await db_session.execute(text("""
            INSERT INTO field_observations
                (id, observation_type, operation, target_table, proposed,
                 status, submitted_by, synced_to_dataset_at)
            VALUES (gen_random_uuid(), 'ore_presence', 'create',
                    'ore_observations', '{}'::jsonb, 'pending', :u, now())
        """), {"u": str(officer.id)})
        await db_session.commit()
    assert "ck_field_obs_synced_only_when_approved" in str(exc.value)
    await db_session.rollback()


# ── the ore export ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_appends_tagged_rows_to_both_files(
        client, officer, reviewer, admin_token, datasets_restored):
    import pandas as pd
    H = {"Authorization": f"Bearer {admin_token}"}
    _pre = pd.read_csv(ds.ORE_CSV)
    before_csv = len(_pre)
    before_sources = (list(_pre[ds.ORIGIN_COL])
                      if ds.ORIGIN_COL in _pre.columns
                      else [ds.ORIGIN_ORIGINAL] * before_csv)
    await _approved_ore(client, officer, reviewer)
    r = (await client.post("/api/v1/dataset-sync/ore", headers=H)).json()
    assert r["synced"] == 1

    csv = pd.read_csv(ds.ORE_CSV)
    assert len(csv) == before_csv + 1
    assert ds.ORIGIN_COL in csv.columns
    # existing rows are backfilled, the new one is tagged
    # Asserted as "the rows that were there are unchanged", not "they are all
    # original": a real field observation may already have been synced into this
    # file, and a test that assumes a pristine checkout fails on a working
    # database for a reason that has nothing to do with what it is testing.
    assert list(csv[ds.ORIGIN_COL].head(before_csv)) == before_sources
    assert csv[ds.ORIGIN_COL].iloc[-1] == ds.ORIGIN_ADDED
    added = csv[csv[ds.ORIGIN_COL] == ds.ORIGIN_ADDED]
    assert len(added) == before_sources.count(ds.ORIGIN_ADDED) + 1
    assert "Sync Test Deposit" in set(added["name"])
    mine_csv = added[added["name"] == "Sync Test Deposit"].iloc[0]
    assert mine_csv["geometry_wkt"].startswith("POLYGON((")

    xl = pd.read_excel(ds.UDEPO_XLSX, header=ds.UDEPO_HEADER_ROW).dropna(how="all")
    assert ds.ORIGIN_COL in xl.columns
    mine = xl[xl["Deposit Name"] == "Sync Test Deposit"]
    assert len(mine) == 1
    assert mine.iloc[0][ds.ORIGIN_COL] == ds.ORIGIN_ADDED
    assert str(mine.iloc[0]["Grade Range"]).startswith("0.042")


@pytest.mark.asyncio
async def test_sync_says_no_retrain_is_required(
        client, officer, reviewer, admin_token, datasets_restored):
    H = {"Authorization": f"Bearer {admin_token}"}
    await _approved_ore(client, officer, reviewer)
    r = (await client.post("/api/v1/dataset-sync/ore", headers=H)).json()
    assert r["retrain_required"] is False
    assert "RESOLVED INPUT" in r["note"]


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(
        client, officer, reviewer, admin_token, datasets_restored):
    import pandas as pd
    H = {"Authorization": f"Bearer {admin_token}"}
    before = ds.ORE_CSV.read_bytes()
    await _approved_ore(client, officer, reviewer)
    r = (await client.post("/api/v1/dataset-sync/ore?dry_run=true",
                           headers=H)).json()
    assert r["dry_run"] is True and r["count"] == 1
    assert ds.ORE_CSV.read_bytes() == before

    s = (await client.get("/api/v1/dataset-sync/status", headers=H)).json()
    assert s["approved_pending_sync"] == 1, "a dry run must not mark rows synced"


@pytest.mark.asyncio
async def test_sync_is_idempotent(
        client, officer, reviewer, admin_token, datasets_restored):
    import pandas as pd
    H = {"Authorization": f"Bearer {admin_token}"}
    await _approved_ore(client, officer, reviewer)
    await client.post("/api/v1/dataset-sync/ore", headers=H)
    n = len(pd.read_csv(ds.ORE_CSV))
    second = (await client.post("/api/v1/dataset-sync/ore", headers=H)).json()
    assert second["count"] == 0
    assert len(pd.read_csv(ds.ORE_CSV)) == n


@pytest.mark.asyncio
async def test_only_admin_can_sync(client, analyst, officer,
                                   datasets_restored):
    # The `reviewer` fixture is an ADMIN since R7, so it belongs on the allowed
    # side of this test rather than the denied side. Syncing the datasets the
    # engine reads has always been an admin-only act.
    for user in (analyst, officer):
        r = await client.post("/api/v1/dataset-sync/ore", headers=_tok(user))
        assert r.status_code == 403, f"{user.role} reached the sync"


@pytest.mark.asyncio
async def test_sync_is_audited(client, db_session, officer, reviewer,
                               admin_token, datasets_restored):
    from app.models.audit_log import AuditLog
    from sqlalchemy import select, delete
    await db_session.execute(delete(AuditLog))
    await db_session.commit()
    H = {"Authorization": f"Bearer {admin_token}"}
    await _approved_ore(client, officer, reviewer)
    await client.post("/api/v1/dataset-sync/ore", headers=H)

    row = (await db_session.execute(
        select(AuditLog).where(AuditLog.action == "dataset.sync_ore")
    )).scalars().first()
    assert row is not None
    assert row.detail["synced"] == 1
    assert row.detail["retrain_required"] is False
    assert any("jharkhand_uranium_deposits.csv" in f for f in row.detail["files"])


@pytest.mark.asyncio
async def test_every_observation_type_is_syncable(client, admin_token):
    """R11 replaced the ore-only export.

    This test previously asserted `syncable_types == ["ore_presence"]` and that
    chemistry was "applied by hand from the audit log". That was the honest
    description of a gap, not a design: approved chemistry and level readings
    accumulated in the database and never reached the files the engine reads, so
    the portal reported a backlog it gave nobody a way to clear. All three types
    now have an automated, audited, reversible path.
    """
    H = {"Authorization": f"Bearer {admin_token}"}
    s = (await client.get("/api/v1/dataset-sync/status", headers=H)).json()
    assert set(s["syncable_types"]) == {
        "ore_presence", "water_sample", "groundwater_level"}


@pytest.mark.asyncio
async def test_derived_syncs_report_what_they_made_stale(client, admin_token):
    """Appending a row is not the same as the engine using it.

    Chemistry and levels feed derived artifacts, so their responses must name
    what still needs rebuilding. Without this an admin sees "synced" and
    reasonably concludes the model changed, when it has not yet.
    """
    H = {"Authorization": f"Bearer {admin_token}"}

    r = await client.post("/api/v1/dataset-sync/water-quality?dry_run=true", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["stale_marks"] == ["excursion_baselines"]

    r = await client.post(
        "/api/v1/dataset-sync/groundwater-levels?dry_run=true", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["stale_marks"] == ["flow_field"]


@pytest.mark.asyncio
async def test_sync_endpoints_are_admin_only(client, analyst):
    """An analyst runs the model; they do not rewrite what it reads."""
    H = _tok(analyst)
    for path in ("/api/v1/dataset-sync/water-quality",
                 "/api/v1/dataset-sync/groundwater-levels",
                 "/api/v1/dataset-sync/all"):
        r = await client.post(f"{path}?dry_run=true", headers=H)
        assert r.status_code == 403, f"{path} -> {r.status_code}"
