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

TEST_DB_NAME = os.getenv("TEST_DB_NAME", "groundwater_test_db")
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{TEST_DB_NAME}",
)

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
