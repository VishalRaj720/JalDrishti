"""One-step publication, and the alerts that publication is supposed to raise.

The headline finding pinned here: **eight advisories had been published and the
`alerts` table was empty.** Not sparse — empty. Every insert was refused by the
`alerts_write` row-level-security policy, and the caller wrapped the whole thing
in `except Exception` and logged it. The product said "published", showed the
advisory to citizens, and notified nobody, once per publication, for the life of
the feature.

Nothing in the suite would have caught it, because nothing asserted that
publishing *produces* an alert. That is what the first test here does.
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.user import User, UserRole
from app.services.auth import create_access_token, hash_password


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


async def _user(db_session, role: UserRole) -> User:
    u = User(id=uuid.uuid4(), username=f"pub{role.value}{uuid.uuid4().hex[:4]}",
             email=f"pub{role.value}{uuid.uuid4().hex[:4]}@test.com",
             hashed_password=hash_password("pw123456"), role=role)
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture()
async def tokens(db_session):
    out = {}
    for role in (UserRole.admin, UserRole.analyst, UserRole.field_officer,
                 UserRole.citizen):
        u = await _user(db_session, role)
        out[role.value] = create_access_token(str(u.id), u.role)
    return out


@pytest_asyncio.fixture()
async def analyst_token(tokens):
    return tokens["analyst"]


@pytest_asyncio.fixture()
async def db(db_session):
    return db_session


@pytest_asyncio.fixture()
async def site(db_session, seeded_block):
    """A registered hypothetical site inside the ore belt.

    Created here rather than skipping on an empty database. These tests used to
    skip when no ISR point existed, which is the worst of both worlds: a green
    suite that asserted nothing about the flow it exists to protect.
    """
    from app.models.isr_point import IsrPoint

    await db_session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    p = IsrPoint(name=f"PublishTest {uuid.uuid4().hex[:6]}",
                 location="SRID=4326;POINT(86.3564 22.6547)",   # Jaduguda
                 injection_rate_m3_day=2500.0, bleed_percent=3.0,
                 operation_years=10.0, restoration_years=0.0,
                 wellfield_width_m=300.0, monitor_ring_m=150.0)
    db_session.add(p)
    await db_session.commit()
    await db_session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    return {"id": str(p.id), "name": p.name}


@pytest_asyncio.fixture()
async def second_site(db_session, seeded_block):
    from app.models.isr_point import IsrPoint

    await db_session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    p = IsrPoint(name=f"PublishTest2 {uuid.uuid4().hex[:6]}",
                 location="SRID=4326;POINT(86.40 22.70)",
                 injection_rate_m3_day=2500.0, operation_years=10.0,
                 restoration_years=0.0)
    db_session.add(p)
    await db_session.commit()
    await db_session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    return {"id": str(p.id), "name": p.name}


BODY = {
    "headline": "Groundwater screening published for the test area",
    "what_it_means": ("A model of what would happen to groundwater if a uranium "
                      "in-situ recovery operation ran at this location."),
}


# ── the regression that motivated all of this ────────────────────────


@pytest.mark.asyncio
async def test_publishing_actually_writes_the_alert_rows(client, admin_token, db, site):
    """Publication must leave alerts behind, not just a log line.

    `set_rls_context` uses SET LOCAL, which Postgres discards at COMMIT. The
    decision commits and *then* raised alerts, so the session had no context and
    `alerts_write` — which requires `app.bypass_rls = 'on'` — refused every
    insert. Alerting now runs in its own session with the system context, the
    way `audit.record` always has.

    Asserted on the DATABASE, not on the response: the response said "published"
    the whole time it was broken.
    """
    r = await client.post("/api/v1/advisories/publish-run",
                          headers=_h(admin_token),
                          json={"isr_point_id": site["id"], "time_years": 20,
                                **BODY})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["published"] is True
    adv = out["advisory"]

    n = (await db.execute(text(
        "SELECT count(*) FROM alerts WHERE advisory_id = :a"),
        {"a": adv["id"]})).scalar()

    assert adv["affected_blocks"], (
        "fixture assumption: the test block must contain the footprint, or this "
        "test passes without ever exercising the insert that was broken")
    assert n > 0, (
        f"advisory {adv['id']} reaches {len(adv['affected_blocks'])} block(s) "
        f"and raised NO alerts — the exact failure this test exists for")

    kinds = dict((await db.execute(text(
        "SELECT kind, count(*) FROM alerts WHERE advisory_id = :a GROUP BY kind"),
        {"a": adv["id"]})).all())
    assert kinds.get("published_screening", 0) > 0


def test_alert_writes_go_through_a_system_session():
    """A static guard, because the runtime one is impossible here.

    THE TEST DATABASE HAS NO ROW-LEVEL SECURITY. It is built from ORM metadata
    via `create_all`, and the policies live in migrations — so `alerts_write` does
    not exist in it, and an insert that production refuses succeeds here without
    complaint. That is not a gap worth papering over with a runtime assertion
    that cannot fail: it is the direct reason this bug reached eight published
    advisories without a single test going red.

    So the invariant is asserted on the SOURCE instead, the same way the sync
    tests pin their JOIN column. `raise_for_advisory` must open its own session
    and set the system context, and must re-set it after the first commit —
    COMMIT discards `SET LOCAL`, so a single call at the top is not enough.
    """
    import inspect

    from app.services import alerts

    src = inspect.getsource(alerts.raise_for_advisory)
    assert "AsyncSessionLocal()" in src, (
        "alerts must be raised in their own session — the caller's session has "
        "already committed and lost its RLS context by the time this runs")
    assert src.count("set_rls_context(db, bypass=True)") >= 2, (
        "the context must be set again after `announce_advisory` commits; a "
        "single call at the top is discarded by that COMMIT and every "
        "subsequent query silently returns nothing")

    decide = inspect.getsource(
        __import__("app.services.advisory", fromlist=["x"]).AdvisoryService.decide)
    assert "raise_for_advisory" in decide, (
        "publication must go through the system-session entry point, not call "
        "AlertService on the request session")


# ── the one-step flow itself ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_saves_the_run_it_publishes(client, admin_token, site):
    """The guarantee that made a separate save a precondition, kept.

    An advisory cites a run. If publishing could cite a preview nobody stored,
    the citation would point at nothing and the statement would be
    unfalsifiable. Saving is now a consequence of publishing rather than a step
    the user has to remember — the run must still exist afterwards.
    """
    r = await client.post("/api/v1/advisories/publish-run",
                          headers=_h(admin_token),
                          json={"isr_point_id": site["id"], "time_years": 10,
                                **BODY})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["run_was_saved"] is True

    got = await client.get(f"/api/v1/simulations/runs/{out['run_id']}",
                           headers=_h(admin_token))
    assert got.status_code == 200, got.text
    run = got.json()
    assert run["status"] == "completed"
    # Provenance is pinned on a stored run; that is why storing it matters.
    assert run["code_version"]
    assert out["advisory"]["run_id"] == out["run_id"]


@pytest.mark.asyncio
async def test_an_analyst_proposes_and_does_not_publish(client, analyst_token, site):
    """The review step is not what was removed.

    Collapsing run/save/propose/decide into one action must not collapse the two
    PEOPLE. An analyst pressing the same button gets a queue entry.
    """
    r = await client.post("/api/v1/advisories/publish-run",
                          headers=_h(analyst_token),
                          json={"isr_point_id": site["id"], "time_years": 10,
                                **BODY})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["published"] is False
    assert out["advisory"]["status"] == "proposed"
    assert out["advisory"]["published_at"] is None
    assert "not public" in out["note"].lower()


@pytest.mark.asyncio
async def test_reusing_a_stored_run_does_not_store_a_second_one(
        client, admin_token, site):
    first = (await client.post("/api/v1/advisories/publish-run",
                               headers=_h(admin_token),
                               json={"isr_point_id": site["id"],
                                     "time_years": 10, **BODY})).json()

    again = await client.post("/api/v1/advisories/publish-run",
                              headers=_h(admin_token),
                              json={"isr_point_id": site["id"],
                                    "run_id": first["run_id"],
                                    "headline": "A second statement, same run",
                                    "what_it_means": BODY["what_it_means"]})
    assert again.status_code == 201, again.text
    out = again.json()
    assert out["run_was_saved"] is False
    assert out["run_id"] == first["run_id"]


@pytest.mark.asyncio
async def test_a_run_from_another_site_is_refused(client, admin_token, site, second_site):
    """An advisory names one location. Citing a run from somewhere else would
    publish a number about a place it was never computed for."""
    first = (await client.post("/api/v1/advisories/publish-run",
                               headers=_h(admin_token),
                               json={"isr_point_id": site["id"],
                                     "time_years": 10, **BODY})).json()

    bad = await client.post("/api/v1/advisories/publish-run",
                            headers=_h(admin_token),
                            json={"isr_point_id": second_site["id"],
                                  "run_id": first["run_id"], **BODY})
    assert bad.status_code == 400, bad.text
    assert "different site" in bad.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["field_officer", "citizen"])
async def test_publish_run_is_closed_to_non_analysts(client, tokens, role):
    r = await client.post("/api/v1/advisories/publish-run",
                          headers=_h(tokens[role]),
                          json={"isr_point_id": str(uuid.uuid4()), **BODY})
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_a_one_word_advisory_is_refused(client, admin_token, site):
    """Unchanged from the four-step route: a resident cannot act on 'uranium'."""
    r = await client.post("/api/v1/advisories/publish-run",
                          headers=_h(admin_token),
                          json={"isr_point_id": site["id"],
                                "headline": "short", "what_it_means": "brief"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_the_premise_survives_the_shorter_route(client, admin_token, site):
    """The hypothetical premise is appended server-side and cannot be edited
    away. A faster path to publication must not be a path around that."""
    out = (await client.post("/api/v1/advisories/publish-run",
                             headers=_h(admin_token),
                             json={"isr_point_id": site["id"], **BODY})).json()
    assert "No uranium in-situ recovery mine operates in Jharkhand" in \
        out["advisory"]["what_it_means"]


# ── the vertical screening the alert depends on ──────────────────────


@pytest.mark.asyncio
async def test_a_saved_run_keeps_its_shallow_aquifer_screening(
        client, admin_token, site):
    """It was computed on every run and thrown away.

    The engine returns it at the top level of the payload, not inside `hydro`,
    so assigning `hydro` alone dropped it — the breakthrough time a user reads
    on screen came from the live preview and existed nowhere afterwards. An
    advisory that says a pathway to the drinking-water aquifer exists has to be
    able to point at the run that said so.
    """
    out = (await client.post("/api/v1/advisories/publish-run",
                             headers=_h(admin_token),
                             json={"isr_point_id": site["id"],
                                   "time_years": 20, **BODY})).json()

    run = (await client.get(f"/api/v1/simulations/runs/{out['run_id']}",
                            headers=_h(admin_token))).json()
    vertical = (run.get("hydro") or {}).get("vertical")
    assert vertical, "the shallow-aquifer screening was dropped again"
    assert "years_to_vertical_breakthrough" in vertical
    assert vertical.get("breakthrough_basis") in ("duty_cycle", "mean_gradient")

    seasonal = vertical.get("seasonal") or {}
    if seasonal.get("breakthrough_years_range"):
        lo, hi = seasonal["breakthrough_years_range"]
        head = vertical["years_to_vertical_breakthrough"]
        if head is not None:
            assert lo <= head <= hi, (
                f"stored headline {head} yr sits outside its own seasonal band "
                f"[{lo}, {hi}] — LIMITATIONS.md finding 1b")


# ── withdrawal has to reach the people the alert reached ─────────────


@pytest.mark.asyncio
async def test_withdrawing_an_advisory_retracts_its_alert(
        client, admin_token, tokens, db, site, seeded_block):
    """Withdrawal was cosmetic: the notification stayed in the inbox.

    Withdrawing is the act of taking a public statement back, and the alert is
    the most public part of it — it went to people's devices. The inbox query
    joined nothing to `advisories`, so a retracted screening kept notifying
    residents indefinitely, and the unread badge kept counting it.

    Measured exceedances are deliberately unaffected: a laboratory result is not
    withdrawn by anybody's decision.
    """
    from app.services.alerts import AlertService

    out = (await client.post("/api/v1/advisories/publish-run",
                             headers=_h(admin_token),
                             json={"isr_point_id": site["id"], **BODY})).json()
    adv_id = out["advisory"]["id"]

    citizen = (await db.execute(text(
        "SELECT id FROM users WHERE role = 'citizen' LIMIT 1"))).scalar()
    await db.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    await db.execute(text("""
        INSERT INTO block_subscriptions (user_id, block_id) VALUES (:u, :b)
        ON CONFLICT DO NOTHING
    """), {"u": str(citizen), "b": seeded_block["block_id"]})
    await db.commit()
    await db.execute(text("SELECT set_config('app.bypass_rls','on',true)"))

    svc = AlertService(db)
    before = await svc.inbox(citizen)
    assert any(a["advisory_id"] == adv_id for a in before), (
        "the published advisory did not reach the subscribed citizen at all")

    r = await client.post(f"/api/v1/advisories/{adv_id}/decision",
                          headers=_h(admin_token),
                          json={"decision": "withdraw", "note": "retracted"})
    assert r.status_code == 200, r.text

    await db.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
    after = await svc.inbox(citizen)
    assert not any(a["advisory_id"] == adv_id for a in after), (
        "a withdrawn advisory is still notifying residents — withdrawal has to "
        "retract the alert, not just change a status nobody sees")
    assert await svc.unread_count(citizen) <= len(after)
