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
from app.models.user import User, UserRole
from app.services.auth import hash_password, create_access_token
from scripts.init_db import _ENUMS, _create_enum_sql

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
            cur.execute(_create_enum_sql(name, values))
    db.close()
    yield


@pytest_asyncio.fixture()
async def setup_db(_bootstrap_test_db):
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
