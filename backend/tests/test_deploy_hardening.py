"""Deployment hardening — the audit findings, pinned.

These guard configuration, not product logic, which is exactly why nothing in
the suite caught them: `286 passed` said nothing about whether `/metrics` was
world-readable or whether row-level security was actually in force.

Each test here fails against the code as it stood on 2026-08-20 and passes after
the corresponding fix.
"""
import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings


def _build_app(monkeypatch, **overrides):
    """A fresh app with settings overridden, since the guards are wired at
    create_app() time rather than per-request."""
    for k, v in overrides.items():
        monkeypatch.setattr(settings, k, v, raising=False)
    import app.main as main
    importlib.reload(main)
    return main.create_app()


# ── F-2: /metrics must not be world-readable ─────────────────────────


@pytest.mark.asyncio
async def test_metrics_requires_a_token_when_one_is_configured(monkeypatch):
    """The production posture: a scrape must authenticate.

    Prometheus output leaks the route inventory, request volumes and latencies.
    It was served to anyone who asked.
    """
    app = _build_app(monkeypatch, METRICS_TOKEN="s3cret-scrape", APP_ENV="production")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as c:
        anon = await c.get("/metrics")
        assert anon.status_code == 401, (
            f"/metrics answered {anon.status_code} without a token — F-2")

        wrong = await c.get("/metrics",
                            headers={"Authorization": "Bearer wrong"})
        assert wrong.status_code == 401

        ok = await c.get("/metrics",
                         headers={"Authorization": "Bearer s3cret-scrape"})
        assert ok.status_code == 200
        assert "python_gc_objects" in ok.text


@pytest.mark.asyncio
async def test_metrics_is_not_mounted_in_production_without_a_token(monkeypatch):
    """Fail closed. An unset token in production must not mean 'wide open'."""
    app = _build_app(monkeypatch, METRICS_TOKEN="", APP_ENV="production")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as c:
        r = await c.get("/metrics")
        assert r.status_code == 404, (
            f"/metrics answered {r.status_code} in production with no token "
            f"configured; it must not be mounted at all — F-2")


@pytest.mark.asyncio
async def test_metrics_stays_open_in_development(monkeypatch):
    """A token on a laptop protects nothing and makes `curl /metrics` annoying.
    The fix must not make local work worse."""
    app = _build_app(monkeypatch, METRICS_TOKEN="", APP_ENV="development")
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://t") as c:
        assert (await c.get("/metrics")).status_code == 200


# ── F-3: dataset writes must be serialised ───────────────────────────


@pytest.mark.asyncio
async def test_a_second_dataset_writer_is_refused_not_interleaved(db_session):
    """The corruption path, closed.

    Every sync and the factory reset read a whole CSV or xlsx, mutate it in
    memory and rewrite it — inline in the request handler, with no queue. Two
    overlapping writers interleave at whole-file granularity, so one of them
    silently loses its rows, and BOTH return success. Two admins, or one admin
    with two browser tabs.

    A refusal is the correct answer rather than a queue: these take seconds, and
    a request that appears to hang is a request the user fires again.
    """
    from app.database import AsyncSessionLocal
    from app.services.dataset_lock import DatasetBusyError, dataset_write_lock

    async with AsyncSessionLocal() as first:
        async with dataset_write_lock(first, what="sync everything"):
            # A DIFFERENT session, as a second worker or a second request would
            # be. An in-process mutex would not catch this.
            async with AsyncSessionLocal() as second:
                with pytest.raises(DatasetBusyError) as exc:
                    async with dataset_write_lock(second, what="factory reset"):
                        pass
                assert exc.value.status_code == 409
                assert "already running" in exc.value.message

        # Released on exit: the same second session may now take it.
        async with AsyncSessionLocal() as third:
            async with dataset_write_lock(third, what="factory reset"):
                pass


@pytest.mark.asyncio
async def test_the_lock_is_reentrant_so_sync_all_can_call_the_others():
    """`sync_all` takes the lock and then calls three syncs that each take it.

    Postgres advisory locks are counted within a session, so nesting is safe —
    but only if every acquisition is matched by a release. If this ever
    deadlocks or leaks, `sync_all` is the caller that will expose it.
    """
    from app.database import AsyncSessionLocal
    from app.services.dataset_lock import dataset_write_lock

    async with AsyncSessionLocal() as db:
        async with dataset_write_lock(db, what="sync everything"):
            async with dataset_write_lock(db, what="sync ore deposits"):
                async with dataset_write_lock(db, what="sync water quality"):
                    pass

        # Fully released — a separate session can take it straight away.
        async with AsyncSessionLocal() as other:
            async with dataset_write_lock(other, what="factory reset"):
                pass


@pytest.mark.asyncio
async def test_a_dry_run_does_not_contend_for_the_write_lock():
    """A preview writes nothing, so refusing it while a sync runs would deny
    the user exactly the information they want at that moment."""
    from app.database import AsyncSessionLocal
    from app.services.dataset_lock import dataset_write_lock, with_dataset_lock

    calls = []

    @with_dataset_lock("probe")
    async def probe(db, *, dry_run=False):
        calls.append(dry_run)
        return "ran"

    async with AsyncSessionLocal() as holder:
        async with dataset_write_lock(holder, what="sync everything"):
            async with AsyncSessionLocal() as other:
                assert await probe(other, dry_run=True) == "ran"
                with pytest.raises(Exception):
                    await probe(other, dry_run=False)
    assert calls == [True]


def test_every_file_writing_entry_point_is_wrapped():
    """A new sync added without the decorator reopens the hole silently."""
    from app.services import dataset_sync, model_ops

    required = [
        (dataset_sync, "sync_ore"), (dataset_sync, "sync_water_quality"),
        (dataset_sync, "sync_groundwater_levels"), (dataset_sync, "sync_all"),
        (dataset_sync, "reconcile_orphans"), (model_ops, "factory_reset"),
    ]
    unwrapped = []
    for mod, name in required:
        fn = getattr(mod, name)
        # functools.wraps sets __wrapped__ only when the decorator was applied.
        if not hasattr(fn, "__wrapped__"):
            unwrapped.append(f"{mod.__name__}.{name}")
    assert unwrapped == [], (
        f"these rewrite dataset files without the write lock: {unwrapped}. "
        f"Add @with_dataset_lock — see deployment audit F-3.")


# ── F-4: inert row-level security must fail closed in production ─────


def _verdict(**kw):
    from app.main import _rls_verdict
    base = dict(user="postgres", is_super=True, bypasses=False, n_policies=19,
                app_env="production", allow_inert=False)
    base.update(kw)
    return _rls_verdict(**base)


def test_production_refuses_to_start_when_rls_is_inert():
    """A log line is not an enforcement mechanism.

    Postgres skips RLS entirely for a superuser or a BYPASSRLS role. If the API
    connects as one, every policy exists, reviews cleanly and enforces nothing —
    worse than having no policies, because the schema claims protection.

    This used to warn and serve. The deployment most likely to get the roles
    wrong is the first production one, and nobody reads startup logs on day two.
    """
    level, msg = _verdict()
    assert level == "fatal", f"expected a refusal, got {level}"
    assert "ROW-LEVEL SECURITY IS INERT" in msg
    assert "Refusing to start" in msg


def test_bypassrls_counts_as_inert_even_without_superuser():
    """BYPASSRLS is the subtler misconfiguration and skips policies just the
    same — a role granted it looks ordinary in a role listing."""
    assert _verdict(is_super=False, bypasses=True)[0] == "fatal"


def test_the_override_is_available_but_must_be_deliberate():
    """An escape hatch that has to be typed, and still logs at CRITICAL."""
    level, msg = _verdict(allow_inert=True)
    assert level == "critical"
    assert "Started anyway" in msg


def test_development_only_warns():
    """A laptop connecting as `postgres` is the normal case; blocking it would
    help nobody and would make the fix something people work around."""
    assert _verdict(app_env="development")[0] == "warn"


def test_a_correctly_configured_connection_is_simply_ok():
    """The real posture of this repo's dev database: `jaldrishti_app`, not a
    superuser, no bypass, 19 policies — RLS genuinely in force."""
    level, msg = _verdict(user="jaldrishti_app", is_super=False, bypasses=False)
    assert level == "ok"
    assert "active" in msg


def test_a_database_with_no_policies_at_all_is_not_reported_as_inert():
    """Nothing to enforce is a different condition from enforcement disabled,
    and conflating them would make the test database look compromised."""
    assert _verdict(n_policies=0)[0] == "ok"


# ── F-5: role-restricted responses must not be cacheable ─────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/audit?limit=5",
    "/api/v1/users",
    "/api/v1/isr-points",
    "/api/v1/field-observations?limit=5",
    "/api/v1/datasets",
    "/api/v1/advisories",
])
async def test_authenticated_routes_are_never_browser_cacheable(
        client, admin_token, path):
    """`no-store` was set in 4 of 21 routers; the rest sent nothing.

    An absent Cache-Control is weaker than an explicit `private`, but it is not
    a guarantee — on a shared machine, or behind any intermediary, a response is
    reusable. `/audit` and `/users` are the ones that matter: an admin's audit
    log sitting in a browser cache for the next person to sign in on that
    machine is exactly the leak `test_ml_router.py` already refuses to allow
    for map geography.
    """
    r = await client.get(path, headers={"Authorization": f"Bearer {admin_token}"})
    if r.status_code >= 400:
        pytest.skip(f"{path} -> {r.status_code}; not a cache question")
    cc = r.headers.get("cache-control", "")
    assert "no-store" in cc, (
        f"{path} sent Cache-Control: {cc!r}. A role-restricted response the "
        f"browser may reuse across sign-ins leaks it to the next user — F-5.")


@pytest.mark.asyncio
async def test_a_router_that_sets_its_own_cache_header_keeps_it(client):
    """Default-deny must not trample the deliberately public layers.

    `public_risk` serves citizen-facing geography with `public, max-age=3600`
    on purpose — it is the same for everyone and expensive to rebuild. The
    middleware only fills in a header that is absent.
    """
    r = await client.get("/api/v1/public/risk/districts")
    if r.status_code >= 400:
        pytest.skip(f"-> {r.status_code}")
    cc = r.headers.get("cache-control", "")
    assert "no-store" not in cc, (
        "the default overwrote a router's deliberate public cache policy")


# ── orphaned simulation runs after a restart ─────────────────────────


@pytest.mark.asyncio
async def test_a_restart_does_not_strand_a_run_for_ever(db_session):
    """Simulations execute in-process, so a restart abandons whatever is running.

    The audit found three real rows sitting at `queued` from the previous day —
    a spinner nobody could clear, and no code path that would ever finish them.
    """
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text as _text

    from app.models.isr_point import IsrPoint
    from app.models.simulation_run import SimulationRun
    from app.services.simulation_run import ORPHAN_AFTER_MINUTES, reap_orphaned_runs

    await db_session.execute(_text("SELECT set_config('app.bypass_rls','on',true)"))
    site = IsrPoint(name=f"Reap {_uuid.uuid4().hex[:6]}",
                    location="SRID=4326;POINT(86.3564 22.6547)")
    db_session.add(site)
    await db_session.flush()

    stale = SimulationRun(
        isr_point_id=site.id, status="queued", engine="both",
        species="uranium_ppb", request={},
        created_at=datetime.now(timezone.utc)
        - timedelta(minutes=ORPHAN_AFTER_MINUTES + 5))
    fresh = SimulationRun(
        isr_point_id=site.id, status="queued", engine="both",
        species="uranium_ppb", request={},
        created_at=datetime.now(timezone.utc))
    db_session.add_all([stale, fresh])
    await db_session.commit()
    await db_session.execute(_text("SELECT set_config('app.bypass_rls','on',true)"))

    out = await reap_orphaned_runs(db_session)
    assert str(stale.id) in out["run_ids"], "the abandoned run was not reaped"

    await db_session.execute(_text("SELECT set_config('app.bypass_rls','on',true)"))
    rows = dict((await db_session.execute(_text(
        "SELECT id::text, status FROM simulation_runs WHERE id = ANY(:ids)"),
        {"ids": [str(stale.id), str(fresh.id)]})).all())

    assert rows[str(stale.id)] == "failed"
    # THE PART THAT MATTERS UNDER `--workers N`. Every worker runs the startup
    # hook, so a blanket sweep would have worker 2 fail the run worker 1 is
    # executing right now. A recent run must survive.
    assert rows[str(fresh.id)] == "queued", (
        "a run that started moments ago was reaped; under multiple workers this "
        "would kill live simulations on every deploy")


@pytest.mark.asyncio
async def test_the_reaped_run_says_why(db_session):
    """"failed" with no message reads as an engine problem. It was a restart."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text as _text

    from app.models.isr_point import IsrPoint
    from app.models.simulation_run import SimulationRun
    from app.services.simulation_run import reap_orphaned_runs

    await db_session.execute(_text("SELECT set_config('app.bypass_rls','on',true)"))
    site = IsrPoint(name=f"Reap2 {_uuid.uuid4().hex[:6]}",
                    location="SRID=4326;POINT(86.3564 22.6547)")
    db_session.add(site)
    await db_session.flush()
    run = SimulationRun(isr_point_id=site.id, status="running", engine="both",
                        species="uranium_ppb", request={},
                        created_at=datetime.now(timezone.utc) - timedelta(hours=3))
    db_session.add(run)
    await db_session.commit()
    await db_session.execute(_text("SELECT set_config('app.bypass_rls','on',true)"))

    await reap_orphaned_runs(db_session)
    await db_session.refresh(run)
    assert run.status == "failed"
    assert "restart" in (run.error_message or "").lower()


# ── rate limiting behind a reverse proxy ─────────────────────────────


def test_the_rate_limiter_keys_on_the_user_not_the_proxy():
    """Behind a gateway, `request.client.host` is the GATEWAY.

    Keying on it gave every authenticated user one shared bucket, so the first
    busy user rate-limited everybody. The limiter was measuring the wrong thing,
    which no amount of raising the limit fixes.
    """
    import types

    # Moved to `app.ratelimit` on 2026-08-24: the routers decorate individual
    # endpoints with the limiter, and `main` imports the routers, so keeping
    # it in `main` would have been an import cycle.
    from app.ratelimit import rate_limit_key as _rate_limit_key
    from app.models.user import UserRole
    from app.services.auth import create_access_token

    proxy = types.SimpleNamespace(host="10.0.0.5")

    def req(headers):
        return types.SimpleNamespace(headers=headers, client=proxy)

    a = create_access_token("user-a", UserRole.analyst)
    b = create_access_token("user-b", UserRole.analyst)

    key_a = _rate_limit_key(req({"authorization": f"Bearer {a}"}))
    key_b = _rate_limit_key(req({"authorization": f"Bearer {b}"}))
    assert key_a != key_b, (
        "two users behind one proxy shared a rate-limit bucket")
    assert key_a.startswith("user:")

    # Anonymous still keys on the address — which is why the deployment still
    # needs `--proxy-headers`. Stated in DEPLOYMENT.md §6.
    assert _rate_limit_key(req({})).startswith("ip:")


def test_a_malformed_token_does_not_break_the_limiter():
    """The key is a bucket, not an authorisation decision. A garbage token must
    fall back to the address rather than raising inside middleware."""
    import types

    # Moved to `app.ratelimit` on 2026-08-24: the routers decorate individual
    # endpoints with the limiter, and `main` imports the routers, so keeping
    # it in `main` would have been an import cycle.
    from app.ratelimit import rate_limit_key as _rate_limit_key

    r = types.SimpleNamespace(headers={"authorization": "Bearer not.a.jwt"},
                              client=types.SimpleNamespace(host="10.0.0.5"))
    assert _rate_limit_key(r) == "ip:10.0.0.5"
