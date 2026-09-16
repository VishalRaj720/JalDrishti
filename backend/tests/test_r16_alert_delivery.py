"""R16 (2026-09-16): an alert is not a row. It is a person being told.

Before this the alert system had every gate and no exit: publication raised
the right alerts for the right blocks and wrote them to a table a resident
could only read by signing in, opening the bell, and having earlier followed
the block that later turned out to be affected. The Alerts screen said so —
"this portal does not send SMS or email."

What is pinned here:

  * Registration records WHERE THE PERSON LIVES and follows that block for
    them, so the first alert about their own water does not depend on their
    having predicted it. A point is resolved to a block server-side; a point
    outside every block is a 422, not an account with no area.
  * Delivery is idempotent and recorded. A re-run sends nothing twice, a
    failure is a `failed` row rather than a lost message, and an unconfigured
    relay is a visible backlog rather than a silent no-op.
  * Demo addresses on reserved domains are never handed to a relay.
  * The two anonymous endpoints registration needs — block search and the
    published-advisory list — expose names and published text only.
  * The RLS-after-COMMIT hazard is guarded at the source: `deliver_pending`
    re-establishes the system context after every per-message commit. The
    test database has no policies (conftest), so this cannot be caught at
    runtime here — see LIMITATIONS.md §1c for the three times it bit.
"""
import inspect
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import UserRole
from app.services import notify
from app.services.alerts import AlertService
from tests.test_p5_citizen import _user, a_block  # noqa: F401  (fixture re-export)


class FakeMailer:
    """Records sends; optionally fails a given address."""
    configured = True
    host = "fake"
    from_email = "alerts@example.org"

    def __init__(self, fail_for: str = ""):
        self.sent: list[tuple[str, str, str]] = []
        self.fail_for = fail_for

    async def send(self, to, subject, body):
        if to == self.fail_for:
            raise RuntimeError("relay refused")
        self.sent.append((to, subject, body))


class UnconfiguredMailer(FakeMailer):
    configured = False
    host = ""
    from_email = ""


async def _measured_alert(db, block_id: str, *, well: str = "Well Z") -> str:
    row = (await db.execute(text("""
        INSERT INTO alerts (kind, block_id, headline, body, severity,
                            well_name, measured_value, measured_unit, sampled_at)
        VALUES ('measured_exceedance', :bid, 'Nitrate above the safe limit in a well near you',
                'A government monitoring well was tested and found: nitrate 121 mg/L.',
                'high', :well, 121, 'mg/L', now())
        RETURNING id::text
    """), {"bid": block_id, "well": well})).first()
    await db.commit()
    return row[0]


# ── registration knows where you live ────────────────────────────────

@pytest.mark.asyncio
async def test_registering_with_a_block_follows_it(client, db_session, a_block):
    email = f"home{uuid.uuid4().hex[:6]}@example.com"
    r = await client.post("/api/v1/citizen/register", json={
        "username": "Resident", "email": email, "password": "a-good-password",
        "home_block_id": a_block["id"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["home_block"]["name"] == "Test Block"

    tok = body["access_token"]
    subs = await client.get("/api/v1/citizen/subscriptions",
                            headers={"Authorization": f"Bearer {tok}"})
    assert [s["id"] for s in subs.json()] == [a_block["id"]]

    me = await client.get("/api/v1/citizen/me",
                          headers={"Authorization": f"Bearer {tok}"})
    assert me.json()["home_block"]["id"] == a_block["id"]
    assert me.json()["alert_email_opt_in"] is True


@pytest.mark.asyncio
async def test_registering_with_a_point_resolves_the_block(client, a_block):
    r = await client.post("/api/v1/citizen/register", json={
        "username": "Resident", "email": f"pt{uuid.uuid4().hex[:6]}@example.com",
        "password": "a-good-password", "lat": 22.65, "lon": 86.36})
    assert r.status_code == 201, r.text
    assert r.json()["home_block"]["id"] == a_block["id"]


@pytest.mark.asyncio
async def test_a_point_outside_every_block_is_refused_not_silently_dropped(client, a_block):
    r = await client.post("/api/v1/citizen/register", json={
        "username": "Resident", "email": f"out{uuid.uuid4().hex[:6]}@example.com",
        "password": "a-good-password", "lat": 10.0, "lon": 10.0})
    assert r.status_code == 422
    assert "not inside" in r.json()["detail"]


@pytest.mark.asyncio
async def test_an_existing_account_can_set_its_home_later(client, db_session, a_block):
    uid, tok = await _user(db_session, f"late{uuid.uuid4().hex[:5]}", UserRole.citizen)
    h = {"Authorization": f"Bearer {tok}"}
    r = await client.put("/api/v1/citizen/me/home", json={"block_id": a_block["id"]},
                         headers=h)
    assert r.status_code == 200, r.text
    subs = await client.get("/api/v1/citizen/subscriptions", headers=h)
    assert [s["id"] for s in subs.json()] == [a_block["id"]]

    off = await client.put("/api/v1/citizen/me/preferences",
                           json={"alert_email_opt_in": False}, headers=h)
    assert off.json() == {"alert_email_opt_in": False}


# ── delivery ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_sends_once_records_it_and_never_repeats(db_session, a_block):
    uid, _ = await _user(db_session, f"d{uuid.uuid4().hex[:5]}", UserRole.citizen)
    await AlertService(db_session).subscribe(uid, uuid.UUID(a_block["id"]))
    alert_id = await _measured_alert(db_session, a_block["id"])

    m = FakeMailer()
    first = await notify.deliver_pending(mailer=m)
    assert first["sent"] == 1 and first["failed"] == 0, first
    to, subject, body = m.sent[0]
    assert to.endswith("@example.com")
    assert "Nitrate above the safe limit" in subject
    assert "Test Block" in subject
    assert "laboratory measurement, not a prediction" in body
    assert "/alerts" in body

    again = await notify.deliver_pending(mailer=m)
    assert again["sent"] == 0 and again["pending"] == 0
    assert len(m.sent) == 1

    rows = (await db_session.execute(text(
        "SELECT status, address FROM alert_deliveries WHERE alert_id = :a"),
        {"a": alert_id})).all()
    assert [r[0] for r in rows] == ["sent"]


@pytest.mark.asyncio
async def test_an_unconfigured_relay_is_a_visible_backlog(db_session, a_block):
    uid, _ = await _user(db_session, f"u{uuid.uuid4().hex[:5]}", UserRole.citizen)
    await AlertService(db_session).subscribe(uid, uuid.UUID(a_block["id"]))
    await _measured_alert(db_session, a_block["id"])

    out = await notify.deliver_pending(mailer=UnconfiguredMailer())
    assert out["configured"] is False
    assert out["pending"] == 1 and out["sent"] == 0
    n = (await db_session.execute(text("SELECT count(*) FROM alert_deliveries"))).scalar()
    assert n == 0, "nothing must be recorded as delivered when nothing was sent"


@pytest.mark.asyncio
async def test_a_failed_send_is_recorded_not_lost(db_session, a_block):
    uid, _ = await _user(db_session, f"f{uuid.uuid4().hex[:5]}", UserRole.citizen)
    email = (await db_session.execute(text("SELECT email FROM users WHERE id = :u"),
                                      {"u": str(uid)})).scalar()
    await AlertService(db_session).subscribe(uid, uuid.UUID(a_block["id"]))
    await _measured_alert(db_session, a_block["id"])

    out = await notify.deliver_pending(mailer=FakeMailer(fail_for=email))
    assert out["failed"] == 1 and out["sent"] == 0
    row = (await db_session.execute(text(
        "SELECT status, detail FROM alert_deliveries"))).first()
    assert row[0] == "failed" and "relay refused" in row[1]


@pytest.mark.asyncio
async def test_demo_addresses_never_reach_a_relay(db_session, a_block):
    """`citizen@jaldrishti.local` is published in the README on purpose. A
    reserved-domain address is skipped and recorded as such, so a fresh
    provider's first impression is not a bounce."""
    from app.models.user import User
    from app.services.auth import hash_password
    u = User(username="demo-cit", email="citizen@jaldrishti.local",
             hashed_password=hash_password("citizen123"), role=UserRole.citizen)
    db_session.add(u)
    await db_session.commit()
    await AlertService(db_session).subscribe(u.id, uuid.UUID(a_block["id"]))
    await _measured_alert(db_session, a_block["id"])

    m = FakeMailer()
    out = await notify.deliver_pending(mailer=m)
    assert out["skipped"] == 1 and m.sent == []


@pytest.mark.asyncio
async def test_opting_out_stops_email_but_not_the_inbox(db_session, a_block):
    uid, _ = await _user(db_session, f"o{uuid.uuid4().hex[:5]}", UserRole.citizen)
    await db_session.execute(text(
        "UPDATE users SET alert_email_opt_in = false WHERE id = :u"), {"u": str(uid)})
    await db_session.commit()
    await AlertService(db_session).subscribe(uid, uuid.UUID(a_block["id"]))
    await _measured_alert(db_session, a_block["id"])

    out = await notify.deliver_pending(mailer=FakeMailer())
    assert out["pending"] == 0 and out["sent"] == 0
    inbox = await AlertService(db_session).inbox(uid)
    assert len(inbox) == 1, "the portal inbox is unaffected by the email preference"


def test_modelled_kinds_open_with_the_premise_and_the_measured_kind_does_not():
    base = {"headline": "H", "body": "B", "block_name": "Blk", "district_name": "D",
            "username": "x", "sampled_at": None}
    _, measured = notify.render_alert_email({**base, "kind": "measured_exceedance"})
    assert "not a prediction" in measured
    for kind in ("published_screening", "aquifer_pathway", "aquifer_breach_due"):
        _, body = notify.render_alert_email({**base, "kind": kind})
        lead = body.split("\n")[2]
        assert "hypothetical" in lead or "No " in lead, (kind, lead)
        assert "not a prediction" not in lead, kind


# ── the anonymous endpoints registration depends on ──────────────────

@pytest.mark.asyncio
async def test_block_search_needs_no_account_and_exposes_names_only(client, a_block):
    r = await client.get("/api/v1/public/risk/blocks/search", params={"q": "test"})
    assert r.status_code == 200, r.text
    hit = next(b for b in r.json() if b["id"] == a_block["id"])
    assert set(hit) == {"id", "name", "district"}

    at = await client.get("/api/v1/public/risk/blocks/at",
                          params={"lat": 22.65, "lon": 86.36})
    assert at.json()["id"] == a_block["id"]
    miss = await client.get("/api/v1/public/risk/blocks/at",
                            params={"lat": 10, "lon": 10})
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_public_advisories_lists_published_only_and_no_coordinates(client, db_session, a_block):
    from tests.test_p5_citizen import _user as mk
    aid, _ = await mk(db_session, f"an{uuid.uuid4().hex[:5]}", UserRole.analyst)
    # A site, a run and two advisories: one published, one merely proposed.
    ids = (await db_session.execute(text("""
        WITH p AS (
            INSERT INTO isr_points (id, name, location, injection_rate_m3_day,
                                    bleed_percent, operation_years, restoration_years,
                                    wellfield_width_m, monitor_ring_m, ore_depth_m,
                                    ore_thickness_m)
            VALUES (gen_random_uuid(), 'Secret Site',
                    ST_SetSRID(ST_MakePoint(86.36, 22.65), 4326),
                    1000, 2, 8, 0, 300, 100, 150, 20)
            RETURNING id
        ), r AS (
            INSERT INTO simulation_runs (id, isr_point_id, species, status, request,
                                         created_by)
            SELECT gen_random_uuid(), p.id, 'uranium', 'queued', '{}'::jsonb,
                   CAST(:actor AS uuid)
            FROM p RETURNING id, isr_point_id
        )
        INSERT INTO advisories (id, isr_point_id, run_id, status, headline,
                                what_it_means, species, affected_blocks,
                                decided_by, published_at, proposed_by)
        SELECT gen_random_uuid(), r.isr_point_id, r.id, s.status, s.headline,
               'means', 'uranium',
               jsonb_build_array(jsonb_build_object('id', CAST(:bid AS text), 'name', 'Test Block',
                                                    'district', 'Test District',
                                                    'overlap_ha', 3.2)),
               CASE WHEN s.status = 'published' THEN CAST(:actor AS uuid) END,
               CASE WHEN s.status = 'published' THEN now() END,
               CAST(:actor AS uuid)
        FROM r, (VALUES ('published', 'PUBLIC ONE'), ('proposed', 'DRAFT ONE')) AS s(status, headline)
        RETURNING id::text
    """), {"bid": a_block["id"], "actor": str(aid)})).all()
    await db_session.commit()
    assert len(ids) == 2

    r = await client.get("/api/v1/public/risk/advisories")
    assert r.status_code == 200, r.text
    body = r.json()
    heads = [a["headline"] for a in body["advisories"]]
    assert "PUBLIC ONE" in heads and "DRAFT ONE" not in heads
    pub = next(a for a in body["advisories"] if a["headline"] == "PUBLIC ONE")
    assert pub["blocks"][0]["name"] == "Test Block"
    text_blob = r.text.lower()
    for forbidden in ("86.36", "22.65", "isr_point", "run_id", "secret site"):
        assert forbidden not in text_blob, forbidden


# ── the source-level guard ───────────────────────────────────────────

def test_delivery_resets_rls_context_after_every_commit():
    """The test database has no RLS policies, so a delivery job that went
    anonymous after its first commit would still pass every runtime test here
    and silently write nothing in production. Guard the pattern instead."""
    src = inspect.getsource(notify.deliver_pending)
    loop = src[src.index("for row in pending"):]
    assert loop.count("await db.commit()") == 1
    assert loop.index("await db.commit()") < loop.index("await set_rls_context(db, bypass=True)")


def test_the_scheduler_is_wired_and_does_not_automate_the_breach_due_scan():
    """Two things about `_alert_scheduler`: it exists in the lifespan, and it
    does NOT call `scan_breach_due`, because that scan is dry-run by default
    for a stated reason (the only alert that fires without anybody acting)."""
    from app import main
    src = inspect.getsource(main.lifespan)
    assert "_alert_scheduler" in src
    cycle = inspect.getsource(main._alert_cycle)
    assert "scan_measured_exceedances" in cycle
    assert "scan_breach_due" not in cycle


# ── found on the deployed portal after R16 shipped ───────────────────

@pytest.mark.asyncio
async def test_every_alert_kind_is_filterable(client, db_session, a_block):
    """The inbox's `kind` filter admitted two of the four kinds, so the Alerts
    screen's "Shared aquifer" tab returned a 422 to every resident."""
    _, tok = await _user(db_session, f"k{uuid.uuid4().hex[:5]}", UserRole.citizen)
    h = {"Authorization": f"Bearer {tok}"}
    for kind in ("measured_exceedance", "published_screening",
                 "aquifer_pathway", "aquifer_breach_due"):
        r = await client.get(f"/api/v1/citizen/alerts?kind={kind}", headers=h)
        assert r.status_code == 200, (kind, r.text)


@pytest.mark.asyncio
async def test_data_quality_report_needs_no_file(client, db_session, a_block):
    """The report is computed from the database, not read from a JSON the seed
    wrote on some other machine -- the deployed host had no such file and told
    the administrator to run the seed there."""
    _, tok = await _user(db_session, f"q{uuid.uuid4().hex[:5]}", UserRole.analyst)
    r = await client.get("/api/v1/ingest/data-quality-report",
                         headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"].startswith("computed live")
    assert body["row_counts"]["blocks"] >= 1
    assert "uranium_ppb" in body["water_sample_null_rates"] or body["row_counts"]["water_samples"] == 0
