"""SQLAlchemy async engine and session factory."""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def set_rls_context(
    session: AsyncSession,
    *,
    role: str = "",
    org_id: Optional[str] = None,
    bypass: bool = False,
) -> None:
    """Tell the RLS policies who is asking, for this transaction only.

    `SET LOCAL` is scoped to the transaction, so a pooled connection cannot leak
    one request's identity into the next — the setting is discarded at COMMIT or
    ROLLBACK. A plain `SET` here would be a cross-request authorisation bug.

    Values are bound as parameters rather than interpolated: `set_config` takes
    them as data, so a role or org id can never be read as SQL.
    """
    await session.execute(
        text("SELECT set_config('app.current_role', :role, true), "
             "       set_config('app.current_org_id', :org, true), "
             "       set_config('app.bypass_rls', :bypass, true)"),
        {"role": role or "", "org": org_id or "", "bypass": "on" if bypass else "off"},
    )


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async DB session.

    Opens as UNAUTHENTICATED. `app.dependencies.get_current_user` raises the
    context once it has verified who the caller is, so a route that forgets its
    auth dependency gets a session the RLS policies treat as anonymous — the
    failure mode is a denied read, not a leak.
    """
    async with AsyncSessionLocal() as session:
        try:
            await set_rls_context(session)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables (use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
