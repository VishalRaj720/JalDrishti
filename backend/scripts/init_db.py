"""Create all database tables for JalDrishti.

Idempotent: safe to run repeatedly. Creates the PostGIS extension and the
PostgreSQL ENUM types the models rely on, then runs SQLAlchemy `create_all`
(which only creates tables that don't already exist).

This is the simple "fewer moving parts" alternative to Alembic for a prototype.
Run after creating the database itself:

    createdb groundwater_db                 # or: CREATE DATABASE groundwater_db;
    python -m scripts.init_db
    python -m scripts.seed
"""
import asyncio

from loguru import logger
from sqlalchemy import text

from app.database import Base, engine
import app.models  # noqa: F401 — registers every table on Base.metadata
from app.models.user import UserRole
from app.models.aquifer import AquiferType


# PGEnum(..., create_type=False) means we own the CREATE TYPE here.
_ENUMS = {
    "userrole": [r.value for r in UserRole],
    "aquifertype": [t.value for t in AquiferType],
}


def _create_enum_statements(name: str, values: list[str]) -> list[str]:
    """Create the enum, or reconcile it if it already exists.

    ONE STATEMENT PER LIST ENTRY, deliberately. The first version of this
    returned a single multi-statement string, which works under psycopg2
    (autocommit, no prepare) but asyncpg REFUSES with "cannot insert multiple
    commands into a prepared statement". `tests/conftest.py` uses psycopg2 and
    `scripts.init_db` uses asyncpg, so the seed broke while the tests stayed
    green.

    Why reconcile at all: the create-only version silently skipped databases
    that already had the type, so when the role model grew from three values to
    five, every pre-existing database kept the old enum and failed at INSERT
    with "invalid input value for enum userrole".

    `ADD VALUE IF NOT EXISTS` is append-only, which matches Postgres: a value
    cannot be removed from an enum. Removing one needs a deliberate type swap in
    a migration.
    """
    labels = ", ".join(f"'{v}'" for v in values)
    # CREATE TYPE has no IF NOT EXISTS; guard with a catalog check.
    stmts = [
        f"DO $$ BEGIN "
        f"IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN "
        f"CREATE TYPE {name} AS ENUM ({labels}); "
        f"END IF; END $$;"
    ]
    stmts += [f"ALTER TYPE {name} ADD VALUE IF NOT EXISTS '{v}';" for v in values]
    return stmts


def _privileged_engine():
    """DDL needs the owner role, not the API's restricted one.

    Since the P2 cutover `DATABASE_URL` points at `jaldrishti_app`, which has no
    CREATE privilege by design. CREATE EXTENSION postgis and CREATE TYPE would
    both fail under it, so this schema work uses MIGRATION_DATABASE_URL when one
    is configured and falls back to the app engine otherwise (a fresh clone that
    has not split the roles yet).
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from app.config import settings
    if settings.MIGRATION_DATABASE_URL:
        return create_async_engine(settings.MIGRATION_DATABASE_URL), True
    return engine, False


async def init_db() -> None:
    ddl_engine, owned = _privileged_engine()
    try:
        await _init_db_with(ddl_engine)
    finally:
        if owned:
            await ddl_engine.dispose()


async def _init_db_with(engine) -> None:
    async with engine.begin() as conn:
        logger.info("Ensuring PostGIS extension ...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        for name, values in _ENUMS.items():
            logger.info(f"Ensuring ENUM type '{name}' ...")
            for stmt in _create_enum_statements(name, values):
                await conn.execute(text(stmt))

        logger.info("Creating tables (create_all) ...")
        await conn.run_sync(Base.metadata.create_all)

    tables = ", ".join(sorted(Base.metadata.tables))
    logger.info(f"Done. Tables present: {tables}")
    # Disposal is the caller's job (init_db): this may be the shared app engine.


if __name__ == "__main__":
    asyncio.run(init_db())
