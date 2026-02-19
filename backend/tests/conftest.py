"""Pytest configuration and fixtures."""
import asyncio
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.database import Base, get_db
from app.models.user import User, UserRole
from app.services.auth import hash_password, create_access_token

# Use an in-memory SQLite for tests (no PostGIS; patch spatial queries)
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def setup_db():
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
