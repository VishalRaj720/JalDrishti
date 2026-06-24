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


def _create_enum_sql(name: str, values: list[str]) -> str:
    labels = ", ".join(f"'{v}'" for v in values)
    # CREATE TYPE has no IF NOT EXISTS; guard with a catalog check.
    return f"""
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
            CREATE TYPE {name} AS ENUM ({labels});
        END IF;
    END $$;
    """


async def init_db() -> None:
    async with engine.begin() as conn:
        logger.info("Ensuring PostGIS extension ...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        for name, values in _ENUMS.items():
            logger.info(f"Ensuring ENUM type '{name}' ...")
            await conn.execute(text(_create_enum_sql(name, values)))

        logger.info("Creating tables (create_all) ...")
        await conn.run_sync(Base.metadata.create_all)

    tables = ", ".join(sorted(Base.metadata.tables))
    logger.info(f"Done. Tables present: {tables}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
