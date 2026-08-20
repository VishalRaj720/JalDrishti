"""The citizen surface: registration, subscriptions, alerts.

The properties worth pinning here are the ones that, if broken, either lock a
resident out of information about their own water or tell them something false
about it.

  * Registration cannot be talked into any role but `citizen`.
  * A subscription is private to its owner — it is a statement about where
    somebody lives, and it is the most personal row in this system.
  * The two alert channels stay distinguishable. A measured exceedance is a
    laboratory result and reads as one; a published screening is a model and
    says so in its own text.
  * Nothing unpublished reaches a citizen.
  * Alerts are idempotent — a citizen must not meet the same warning twice
    because somebody re-ran a scan.
"""

# R7 retired the `regulator` role; migration 0019 merged those accounts
# into `admin`, which now holds the reviewer powers this exercises.
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password
from tests.test_p2_site_is_the_operation import FULL_SITE, _tok


async def _user(db, username, role) -> tuple[uuid.UUID, str]:
    u = User(username=username, email=f"{username}@example.com",
             hashed_password=hash_password("pass1234"), role=role)
    db.add(u)
    await db.commit()
    return u.id, create_access_token(str(u.id), u.role)


@pytest_asyncio.fixture()
async def citizen(db_session):
    return await _user(db_session, f"cit{uuid.uuid4().hex[:5]}", UserRole.citizen)


@pytest_asyncio.fixture()
async def other_citizen(db_session):
    return await _user(db_session, f"cit{uuid.uuid4().hex[:5]}", UserRole.citizen)


@pytest_asyncio.fixture()
async def reviewer_token(db_session):
    _, tok = await _user(db_session, f"reg{uuid.uuid4().hex[:5]}", UserRole.admin)
    return tok


@pytest_asyncio.fixture()
async def a_block(db_session):
    """A block to subscribe to, created here rather than assumed.

    The test database is a bare `groundwater_test_db` — migrations only, none of
    the seeded Jharkhand geodata the development database carries. A fixture
    that reads whatever happens to be there passes or errors depending on which
    machine it runs on, which is not a test.

    The polygon is a real one-degree box over the Singhbhum area so that the
    spatial joins these tests exercise have something to intersect.
    """
    row = (await db_session.execute(text("""
        WITH d AS (
            INSERT INTO districts (id, name, geometry)
            VALUES (gen_random_uuid(), 'Test District',
                    ST_SetSRID(ST_GeomFromText(
                        'MULTIPOLYGON(((86.0 22.0, 87.0 22.0, 87.0 23.0,
                                        86.0 23.0, 86.0 22.0)))'), 4326))
            RETURNING id
        )
        INSERT INTO blocks (id, name, district_id, geometry)
        SELECT gen_random_uuid(), 'Test Block', d.id,
               ST_SetSRID(ST_GeomFromText(
                   'MULTIPOLYGON(((86.2 22.4, 86.6 22.4, 86.6 22.9,
                                   86.2 22.9, 86.2 22.4)))'), 4326)
        FROM d
        RETURNING id::text, name
    """))).first()
    await db_session.commit()
    return {"id": row[0], "name": row[1]}


@pytest_asyncio.fixture()
async def a_well_over_the_limit(db_session, a_block):
    """A monitoring well in that block with a uranium result above 30 ppb.

    Created rather than found, for the same reason as `a_block`: the measured
    channel is the half of this product that reports real laboratory results,
    and a test that skips when the database happens to be empty is not testing
    it at all.
    """
    row = (await db_session.execute(text("""
        WITH w AS (
            INSERT INTO monitoring_wells (id, name, block_id, location,
                                          longitude, latitude)
            VALUES (gen_random_uuid(), 'Test Well A', :bid,
                    ST_SetSRID(ST_MakePoint(86.36, 22.65), 4326),
                    86.36, 22.65)
            RETURNING id
        )
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb)
        SELECT gen_random_uuid(), w.id, now() - interval '30 days', 48.5 FROM w
        RETURNING id::text
    """), {"bid": a_block["id"]})).first()
    await db_session.commit()
    return row[0]


# ── registration ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_citizen_can_register_and_is_signed_in(client):
    email = f"newcit{uuid.uuid4().hex[:6]}@example.com"
    r = await client.post("/api/v1/citizen/register", json={
        "username": "New Resident", "email": email, "password": "a-good-password"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "citizen"
    assert body["access_token"]

    # The token works immediately — requiring a second sign-in step after
    # registering is a drop-off point for no security benefit.
    me = await client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "citizen"


@pytest.mark.asyncio
async def test_registration_ignores_a_role_in_the_body(client):
    """The narrowed hardening property, asserted directly."""
    r = await client.post("/api/v1/citizen/register", json={
        "username": "Sneaky", "email": f"sneak{uuid.uuid4().hex[:6]}@example.com",
        "password": "a-good-password", "role": "admin"})
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "citizen"


@pytest.mark.asyncio
async def test_duplicate_email_does_not_confirm_the_account_exists(client):
    """An unauthenticated endpoint that says 'that email is registered' is an
    account-existence oracle."""
    email = f"dup{uuid.uuid4().hex[:6]}@example.com"
    body = {"username": "First", "email": email, "password": "a-good-password"}
    assert (await client.post("/api/v1/citizen/register", json=body)).status_code == 201
    second = await client.post("/api/v1/citizen/register", json=body)
    assert second.status_code == 409
    assert "cannot be registered" in second.json()["detail"]
    assert "exists" not in second.json()["detail"].lower()


@pytest.mark.asyncio
async def test_a_short_password_is_refused(client):
    r = await client.post("/api/v1/citizen/register", json={
        "username": "Weak", "email": f"weak{uuid.uuid4().hex[:6]}@example.com",
        "password": "short"})
    assert r.status_code == 422


# ── subscriptions ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_subscribe_and_list_my_blocks(client, citizen, a_block):
    _, tok = citizen
    r = await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                          json={"block_id": a_block["id"]})
    assert r.status_code == 201, r.text

    subs = await client.get("/api/v1/citizen/subscriptions", headers=_tok(tok))
    assert subs.status_code == 200
    assert [s["id"] for s in subs.json()] == [a_block["id"]]


@pytest.mark.asyncio
async def test_subscribing_twice_is_harmless(client, citizen, a_block):
    _, tok = citizen
    for _ in range(2):
        r = await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                              json={"block_id": a_block["id"]})
        assert r.status_code == 201
    subs = (await client.get("/api/v1/citizen/subscriptions", headers=_tok(tok))).json()
    assert len(subs) == 1


@pytest.mark.asyncio
async def test_one_citizen_cannot_see_anothers_subscriptions(
        client, citizen, other_citizen, a_block):
    """Where somebody lives is the most personal thing this system stores."""
    _, mine = citizen
    _, theirs = other_citizen
    await client.post("/api/v1/citizen/subscriptions", headers=_tok(mine),
                      json={"block_id": a_block["id"]})

    subs = await client.get("/api/v1/citizen/subscriptions", headers=_tok(theirs))
    assert subs.status_code == 200
    assert subs.json() == [], (
        "a citizen saw another citizen's subscribed blocks")


@pytest.mark.asyncio
async def test_unsubscribe_removes_it(client, citizen, a_block):
    _, tok = citizen
    await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                      json={"block_id": a_block["id"]})
    r = await client.delete(f"/api/v1/citizen/subscriptions/{a_block['id']}",
                            headers=_tok(tok))
    assert r.status_code == 204
    assert (await client.get("/api/v1/citizen/subscriptions",
                             headers=_tok(tok))).json() == []


# ── the measured channel ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_measured_scan_is_admin_only(client, citizen):
    _, tok = citizen
    r = await client.post("/api/v1/citizen/alerts/scan-measured", headers=_tok(tok))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_measured_scan_is_idempotent(client, admin_token, a_well_over_the_limit):
    """A citizen must not meet the same warning twice because of a re-run."""
    first = await client.post("/api/v1/citizen/alerts/scan-measured",
                              headers=_tok(admin_token))
    assert first.status_code == 200, first.text
    second = await client.post("/api/v1/citizen/alerts/scan-measured",
                               headers=_tok(admin_token))
    assert second.status_code == 200
    assert second.json()["alerts_created"] == 0, (
        "re-running the scan created duplicate alerts")


@pytest.mark.asyncio
async def test_a_measured_alert_reads_as_a_measurement(
        client, admin_token, db_session, a_well_over_the_limit):
    """The real channel must not hedge — and must carry its reading."""
    await client.post("/api/v1/citizen/alerts/scan-measured", headers=_tok(admin_token))
    row = (await db_session.execute(text("""
        SELECT headline, body, measured_value, measured_unit, sampled_at
        FROM alerts WHERE kind = 'measured_exceedance' LIMIT 1
    """))).mappings().first()
    assert row is not None, "the scan did not raise an alert for a 48.5 ppb well"
    assert row["measured_value"] > 30
    assert row["measured_unit"] == "ppb"
    assert row["sampled_at"] is not None
    # It is a laboratory result and says so, rather than borrowing the
    # hypothetical framing that belongs to the screening channel.
    assert "real laboratory result" in row["body"]
    assert "not a prediction" in row["body"]


# ── the screening channel ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publishing_alerts_only_the_blocks_the_footprint_reaches(
        client, admin_token, reviewer_token, db_session):
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Alert {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()

    adv = (await client.post("/api/v1/advisories", headers=_tok(admin_token), json={
        "run_id": run["id"],
        "headline": "Groundwater screening published for this area",
        "what_it_means": "A model of what would happen if an ISR operation ran here."})).json()

    before = (await db_session.execute(
        text("SELECT count(*) FROM alerts WHERE kind='published_screening'"))).scalar_one()
    pub = await client.post(f"/api/v1/advisories/{adv['id']}/decision",
                            headers=_tok(reviewer_token), json={"decision": "publish"})
    assert pub.status_code == 200, pub.text

    after = (await db_session.execute(
        text("SELECT count(*) FROM alerts WHERE kind='published_screening'"))).scalar_one()
    # Exactly as many alerts as blocks the footprint intersects — no more.
    assert after - before == len(adv["affected_blocks"]), (
        f"published to {len(adv['affected_blocks'])} block(s) but raised "
        f"{after - before} alert(s)")


@pytest.mark.asyncio
async def test_a_screening_alert_carries_the_hypothetical_premise(
        client, admin_token, reviewer_token, db_session, a_block):
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Prem {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()
    adv = (await client.post("/api/v1/advisories", headers=_tok(admin_token), json={
        "run_id": run["id"], "headline": "Screening published for this area",
        "what_it_means": "A model of what would happen if an ISR operation ran here."})).json()
    await client.post(f"/api/v1/advisories/{adv['id']}/decision",
                      headers=_tok(reviewer_token), json={"decision": "publish"})

    # `a_block` covers 86.2–86.6 E / 22.4–22.9 N, which contains the pin at
    # (86.36, 22.65), so the footprint necessarily lands inside it. Without a
    # block to intersect this test would skip — and the premise it checks is the
    # single most important string in the citizen-facing product.
    row = (await db_session.execute(text("""
        SELECT body FROM alerts WHERE advisory_id = :aid LIMIT 1
    """), {"aid": adv["id"]})).mappings().first()
    assert row is not None, "the published screening raised no alert for its block"
    assert "No uranium in-situ recovery mine operates in Jharkhand" in row["body"]
    # And it states the real overlap rather than implying the whole block.
    assert "hectares" in row["body"]
    assert "not the whole area" in row["body"]


@pytest.mark.asyncio
async def test_a_citizen_sees_only_published_advisories(
        client, admin_token, citizen):
    """A proposed advisory is an internal draft about somebody's water."""
    _, tok = citizen
    site = (await client.post(
        "/api/v1/isr-points", headers=_tok(admin_token),
        json={"name": f"Draft {uuid.uuid4().hex[:5]}", **FULL_SITE})).json()
    q = (await client.post(f"/api/v1/simulations/{site['id']}", headers=_tok(admin_token),
                           json={"species": "uranium_ppb", "time_years": 10})).json()
    run = (await client.get(f"/api/v1/simulations/runs/{q['id']}",
                            headers=_tok(admin_token))).json()
    adv = (await client.post("/api/v1/advisories", headers=_tok(admin_token), json={
        "run_id": run["id"], "headline": "An unapproved draft headline",
        "what_it_means": "This has not been reviewed by a reviewer yet."})).json()

    pub = await client.get("/api/v1/citizen/advisories", headers=_tok(tok))
    assert pub.status_code == 200
    assert adv["id"] not in [a["id"] for a in pub.json()]


# ── the inbox ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_inbox_is_scoped_to_subscribed_blocks(
        client, admin_token, citizen, a_block, a_well_over_the_limit):
    _, tok = citizen
    await client.post("/api/v1/citizen/alerts/scan-measured", headers=_tok(admin_token))

    empty = await client.get("/api/v1/citizen/alerts", headers=_tok(tok))
    assert empty.status_code == 200
    assert empty.json()["alerts"] == [], (
        "an unsubscribed citizen received alerts for blocks they never chose")

    await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                      json={"block_id": a_block["id"]})
    after = await client.get("/api/v1/citizen/alerts", headers=_tok(tok))
    assert after.status_code == 200
    for a in after.json()["alerts"]:
        assert a["block_id"] == a_block["id"]


@pytest.mark.asyncio
async def test_marking_read_clears_the_unread_count(
        client, admin_token, citizen, a_block, a_well_over_the_limit):
    _, tok = citizen
    await client.post("/api/v1/citizen/alerts/scan-measured", headers=_tok(admin_token))
    blk = a_block["id"]
    await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                      json={"block_id": blk})
    box = (await client.get("/api/v1/citizen/alerts", headers=_tok(tok))).json()
    assert box["unread"] > 0

    r = await client.post("/api/v1/citizen/alerts/read-all", headers=_tok(tok))
    assert r.status_code == 200
    assert (await client.get("/api/v1/citizen/alerts/unread-count",
                             headers=_tok(tok))).json()["unread"] == 0


@pytest.mark.asyncio
async def test_my_area_explains_a_no_data_block_as_a_gap(
        client, citizen, db_session):
    """"No data" must never read as "clean" — that distinction is the whole
    reason the block map is worth drawing."""
    _, tok = citizen
    # A block with no monitoring well at all — the monitoring gap this message
    # exists to describe.
    blk = (await db_session.execute(text("""
        WITH d AS (
            INSERT INTO districts (id, name, geometry)
            VALUES (gen_random_uuid(), 'Unsampled District',
                    ST_SetSRID(ST_GeomFromText(
                        'MULTIPOLYGON(((84.0 23.0, 84.3 23.0, 84.3 23.3,
                                        84.0 23.3, 84.0 23.0)))'), 4326))
            RETURNING id
        )
        INSERT INTO blocks (id, name, district_id, geometry)
        SELECT gen_random_uuid(), 'Unsampled Block', d.id,
               ST_SetSRID(ST_GeomFromText(
                   'MULTIPOLYGON(((84.0 23.0, 84.2 23.0, 84.2 23.2,
                                   84.0 23.2, 84.0 23.0)))'), 4326)
        FROM d
        RETURNING id::text
    """))).scalar()
    await db_session.commit()

    await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                      json={"block_id": blk})
    area = (await client.get("/api/v1/citizen/my-area", headers=_tok(tok))).json()
    b = area["blocks"][0]
    assert b["band"] == "No data"
    assert "gap in monitoring" in b["what_it_means"]
    assert "not a clean result" in b["what_it_means"]


@pytest.mark.asyncio
async def test_sampled_but_not_for_uranium_is_not_called_unsampled(
        client, citizen, a_block, db_session):
    """A defect caught in browser verification, pinned so it cannot come back.

    The screen read “No groundwater sample from this block is in the government
    dataset” directly above “2 wells tested · 2 samples”. Both came from the same
    response. The band is driven by `max_uranium_ppb`, which is NULL when wells
    were sampled but never analysed for uranium — a real case in the CGWB data,
    which does not report every determinand at every well.

    Telling a resident nothing was sampled, when wells near them were sampled
    just not for this, is precisely the kind of confidently wrong public
    statement this product exists not to make.
    """
    _, tok = citizen
    await db_session.execute(text("""
        WITH w AS (
            INSERT INTO monitoring_wells (id, name, block_id, location,
                                          longitude, latitude)
            VALUES (gen_random_uuid(), 'No-Uranium Well', :bid,
                    ST_SetSRID(ST_MakePoint(86.3, 22.6), 4326), 86.3, 22.6)
            RETURNING id
        )
        INSERT INTO water_samples (id, well_id, sampled_at, uranium_ppb)
        SELECT gen_random_uuid(), w.id, now() - interval '10 days', NULL FROM w
    """), {"bid": a_block["id"]})
    await db_session.commit()

    await client.post("/api/v1/citizen/subscriptions", headers=_tok(tok),
                      json={"block_id": a_block["id"]})
    area = (await client.get("/api/v1/citizen/my-area", headers=_tok(tok))).json()
    b = next(x for x in area["blocks"] if x["id"] == a_block["id"])

    assert b["band"] == "No data"
    assert b["samples"] > 0, "fixture did not create a sample"
    # It must NOT claim the block is unsampled while reporting samples.
    assert "No groundwater sample from this block" not in b["what_it_means"], (
        "the block reports samples and simultaneously says none exist")
    assert "none was analysed for uranium" in b["what_it_means"]
    assert "not a clean result" in b["what_it_means"]
