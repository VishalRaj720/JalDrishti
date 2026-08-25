"""Pytest configuration and fixtures.

Tests run against a real PostgreSQL/PostGIS database (the project is Postgres-only;
there is no SQLite fallback). A dedicated `groundwater_test_db` is created
automatically and is kept separate from the development database, so tests never
touch real data. Each test gets a fresh schema (create_all / drop_all).

Override the test DB via env var TEST_DATABASE_URL if needed.
"""
import os
import uuid

import psycopg2
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.ratelimit import limiter
from app.models.user import User, UserRole
from app.services.auth import hash_password, create_access_token
from scripts.init_db import _ENUMS, _create_enum_statements

#: Hosts a test run is allowed to create databases on.
#:
#: Deployment audit 2026-08-25. `TEST_DB_URL` and `_bootstrap_test_db` below are
#: built from `settings.DB_HOST/DB_USER/DB_PASSWORD` -- the PRIVILEGED
#: credentials -- and `_bootstrap_test_db` issues `CREATE DATABASE`. That is
#: correct while those point at a local development cluster, and actively
#: dangerous the moment they point at a managed provider: aiming `.env` at a
#: Neon project (which is exactly what deploying this thing requires) turns a
#: plain `pytest` into "create a database inside the production project, then
#: run 402 tests against it over the internet".
#:
#: Nothing in the suite would have complained. It would simply have worked.
_LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "", "host.docker.internal"})


def _refuse_remote_test_database() -> None:
    """Fail the run rather than create a database on someone else's server.

    Raised at IMPORT time, not inside a fixture: by the time a fixture runs
    pytest has printed a header that makes the run look normal, and the point is
    to stop before anything touches the network.

    The escape hatch is `JALDRISHTI_ALLOW_REMOTE_TEST_DB=1`, for the case where
    somebody genuinely means it -- a disposable Neon branch, say. It is an
    explicit opt-in because the failure it guards against is silent and
    expensive, and `TEST_DATABASE_URL` alone would not save you: the bootstrap
    fixture still connects with `DB_HOST` to issue CREATE DATABASE.
    """
    if os.getenv("JALDRISHTI_ALLOW_REMOTE_TEST_DB") == "1":
        return
    host = (settings.DB_HOST or "").strip().lower()
    if host in _LOCAL_DB_HOSTS:
        return
    raise RuntimeError(
        f"""

Refusing to run the test suite against DB_HOST={settings.DB_HOST!r}.

The suite creates a database ({TEST_DB_NAME!r}) using DB_USER/DB_PASSWORD,
which are the privileged credentials. Against a managed provider that means
creating a database inside a real project -- most likely the one this
deployment runs on.

Point DB_HOST back at a local cluster to run the tests:
    DB_HOST=localhost

If you genuinely intend a remote test database (a disposable branch, for
instance), set JALDRISHTI_ALLOW_REMOTE_TEST_DB=1 and re-run.
"""
    )


def _refuse_inherited_migration_url() -> None:
    """Refuse a run that would migrate the wrong database.

    `tests/test_schema_integrity.py` and `tests/test_rls.py` each build a
    scratch database and populate it by shelling out to
    `alembic upgrade head` with `env = dict(os.environ)` plus an explicit
    `DATABASE_URL` naming that scratch database. But `alembic/env.py` resolves
    its target as:

        MIGRATION_DATABASE_URL  ->  DATABASE_URL  ->  .env  ->  alembic.ini

    so an INHERITED `MIGRATION_DATABASE_URL` outranks the `DATABASE_URL` those
    fixtures carefully set. Alembic then migrates whatever that variable names --
    in the incident that prompted this, the developer's real `groundwater_db` --
    and leaves the scratch database empty.

    The failure does not look like a misdirected migration. It looks like a
    broken schema: `migrated_tables` comes back empty, so every ORM model
    appears to have no migration, and the RLS fixtures raise `UndefinedTable`
    from a database with no tables in it. Twelve errors and two failures, none
    of them where the problem was.

    Only `os.environ` is consulted, never `settings`. pydantic-settings reads
    `.env` into the Settings object WITHOUT exporting to the process
    environment, so a `MIGRATION_DATABASE_URL` line in `.env` -- the normal case,
    and harmless, because subprocesses do not inherit it -- does not trip this.
    Reaching here means somebody exported it into the shell.
    """
    inherited = os.environ.get("MIGRATION_DATABASE_URL")
    if not inherited:
        return
    raise RuntimeError(
        f"""

Refusing to run the test suite with MIGRATION_DATABASE_URL exported.

    MIGRATION_DATABASE_URL={inherited}

test_schema_integrity.py and test_rls.py migrate a scratch database by running
`alembic upgrade head` in a subprocess that inherits this environment. In
alembic/env.py, MIGRATION_DATABASE_URL is resolved BEFORE the DATABASE_URL those
fixtures set, so alembic would migrate the database named above instead -- and
report the damage as a broken schema somewhere else entirely.

Unset it and let .env supply the value instead:

    PowerShell   $env:MIGRATION_DATABASE_URL = $null
    bash         unset MIGRATION_DATABASE_URL

A MIGRATION_DATABASE_URL line inside .env is fine and is the normal setup:
subprocesses do not inherit it.
"""
    )


TEST_DB_NAME = os.getenv("TEST_DB_NAME", "groundwater_test_db")
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{TEST_DB_NAME}",
)

_refuse_remote_test_database()
_refuse_inherited_migration_url()

# NullPool: don't reuse asyncpg connections across pytest-asyncio's per-function
# event loops (a pooled connection bound to a closed loop raises
# "another operation is in progress").
test_engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _disable_rate_limiting():
    """Turn the rate limiter off for the suite, and say why.

    Every request in these tests arrives from the same ASGI transport, so they
    all share one bucket. The suite makes far more than `RATE_LIMIT_PER_MINUTE`
    requests, and once the limiter became real (2026-08-24) that turned into
    spurious 429s in tests that are not about rate limiting at all.

    Switched off here rather than raised to a large number, because a limit high
    enough never to trip is a limit that is not being tested either way. The
    tests that DO exercise it re-enable it around themselves — see
    `test_rate_limiting.py`.
    """
    limiter.enabled = False
    yield
    limiter.enabled = True


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_test_db():
    """Create the test DB + PostGIS extension + enum types once per session.

    Done synchronously (psycopg2) so there is no session-scoped async fixture —
    that keeps every async fixture on pytest-asyncio's per-function loop and
    avoids cross-event-loop errors.
    """
    admin = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD, dbname="postgres",
    )
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    admin.close()

    db = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD, dbname=TEST_DB_NAME,
    )
    db.autocommit = True
    with db.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        for name, values in _ENUMS.items():
            for stmt in _create_enum_statements(name, values):
                cur.execute(stmt)
    db.close()
    yield


@pytest_asyncio.fixture()
async def setup_db(_bootstrap_test_db):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _own_session_writers_go_to_the_test_db(monkeypatch):
    """Point every component that opens its OWN session at the test database.

    Two places deliberately bypass the `get_db` override:

      * `app.services.audit.record` — so a rolled-back request cannot erase its
        own audit record;
      * the simulation background task — it outlives the request, so there is
        no request session to borrow.

    Both are correct designs and both write to the DEVELOPMENT database during
    tests unless redirected here. That is a false pass *and* real pollution of
    `groundwater_db`: the background task's run row landed in dev while the test
    read the test database and saw its run stuck at `queued`.
    """
    monkeypatch.setattr("app.services.audit.AsyncSessionLocal", TestSessionLocal)
    # Imported inside the function it is used in, so patch it at the source.
    monkeypatch.setattr("app.database.AsyncSessionLocal", TestSessionLocal)


@pytest_asyncio.fixture()
async def db_session(setup_db):
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def admin_user(db_session):
    user = User(
        id=uuid.uuid4(),
        username="testadmin",
        email="admin@test.com",
        hashed_password=hash_password("admin123"),
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture()
def admin_token(admin_user):
    return create_access_token(str(admin_user.id), admin_user.role)


@pytest_asyncio.fixture()
async def seeded_block(db_session):
    """A district and a block with real geometry, inside Jharkhand.

    WHY THIS EXISTS. The test database is built from ORM metadata, not from the
    seed script, so it has no geography at all. Several tests responded by
    calling `pytest.skip("no blocks in the test database")` — which turns a red
    test into a green one without changing anything it was written to check.
    Two of the project's own rules were being "verified" that way: that a
    sampled-but-untested well reads as a monitoring gap rather than a clean
    result, and that re-seeding water samples upserts instead of duplicating.

    That is not hypothetical. A test in `test_r11_publish_and_alerts.py` took
    exactly this shape — with no blocks, an advisory reached none, so the
    assertion took its "alerts nobody" branch and passed while the insert path
    that was broken in production never ran once.

    A ~0.25 deg box around Jaduguda: inside the ore belt, and big enough that a
    modelled footprint lands within it.

    Returns the ids plus the centroid, since point-in-polygon callers need a
    coordinate that is guaranteed to be inside.
    """
    from sqlalchemy import text as _text

    from app.models.block import Block
    from app.models.district import District

    await db_session.execute(
        _text("SELECT set_config('app.bypass_rls','on',true)"))
    d = District(name=f"TestDistrict {uuid.uuid4().hex[:6]}")
    db_session.add(d)
    await db_session.flush()
    b = Block(name=f"TestBlock {uuid.uuid4().hex[:6]}", district_id=d.id,
              geometry=("SRID=4326;MULTIPOLYGON(((86.25 22.55, 86.50 22.55, "
                        "86.50 22.80, 86.25 22.80, 86.25 22.55)))"))
    db_session.add(b)
    await db_session.commit()
    await db_session.execute(
        _text("SELECT set_config('app.bypass_rls','on',true)"))
    return {"district_id": str(d.id), "district_name": d.name,
            "block_id": str(b.id), "block_name": b.name,
            "lon": 86.375, "lat": 22.675}
