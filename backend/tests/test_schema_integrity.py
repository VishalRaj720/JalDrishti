"""Guard: the migration chain and the ORM metadata must describe one schema.

WHY THIS EXISTS. Five tables (`contamination_events`, `hydraulic_heads`,
`ml_models`, `piezometric_heads`, `spatial_analysis_results`) sat in
`groundwater_db` with no ORM model until migration 0006 removed them. They were
created legitimately by migrations 0001 and 0004; what went wrong is that the
models were later deleted without a matching down-migration, so the chain kept
building tables the application could not see. Nothing failed, which is why it
survived several releases.

`conftest.py` builds its database with `Base.metadata.create_all()`, so the
normal test suite compares the ORM against itself and can never catch this. This
module therefore stands up a scratch database, runs `alembic upgrade head`
against it, and diffs the result. It catches divergence in both directions:

  * a table migrations create but no model declares  -> the orphan bug;
  * a table a model declares but no migration creates -> a table that exists in
    dev (via create_all) and is missing in any migrated environment.
"""
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

from app.config import settings
from app.database import Base
import app.models  # noqa: F401 — registers every table on Base.metadata

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROBE_DB = os.getenv("SCHEMA_PROBE_DB", "jd_schema_probe_test")

# Alembic bookkeeping and a PostGIS-owned table; neither is ours to model.
_NOT_OURS = {"alembic_version", "spatial_ref_sys"}


def _admin_conn(dbname="postgres"):
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD, dbname=dbname,
    )
    conn.autocommit = True
    return conn


@pytest.fixture(scope="module")
def migrated_tables():
    """Build a scratch DB from the migration chain; yield its table names."""
    admin = _admin_conn()
    with admin.cursor() as cur:
        # Terminate stragglers so DROP cannot block on a leaked connection.
        cur.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()", (PROBE_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')
        cur.execute(f'CREATE DATABASE "{PROBE_DB}"')
    admin.close()

    try:
        probe = _admin_conn(PROBE_DB)
        with probe.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        probe.close()

        env = dict(os.environ)
        env["DATABASE_URL"] = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{PROBE_DB}"
        )
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300,
        )
        assert proc.returncode == 0, (
            "`alembic upgrade head` failed on an empty database — the chain "
            f"cannot rebuild the schema from scratch:\n{proc.stdout}\n{proc.stderr}"
        )

        probe = _admin_conn(PROBE_DB)
        with probe.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'")
            tables = {r[0] for r in cur.fetchall()} - _NOT_OURS
        probe.close()
        yield tables
    finally:
        admin = _admin_conn()
        with admin.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()", (PROBE_DB,))
            cur.execute(f'DROP DATABASE IF EXISTS "{PROBE_DB}"')
        admin.close()


def test_no_migrated_table_lacks_an_orm_model(migrated_tables):
    """The orphan-table bug, caught at its own shape."""
    orphans = migrated_tables - set(Base.metadata.tables)
    assert not orphans, (
        f"tables created by migrations with no ORM model: {sorted(orphans)}. "
        "They are unreachable from the application and invisible to SQLAlchemy. "
        "Either add the model or drop them in a new migration."
    )


def test_no_orm_model_lacks_a_migration(migrated_tables):
    """The reverse: a model that only ever appears via create_all()."""
    unmigrated = set(Base.metadata.tables) - migrated_tables
    assert not unmigrated, (
        f"models with no table in the migration chain: {sorted(unmigrated)}. "
        "These exist in any create_all() database and are missing everywhere "
        "the schema is built by `alembic upgrade head`."
    )


def test_dropped_orphans_stay_dropped(migrated_tables):
    """Migration 0006's five tables must not come back."""
    revived = migrated_tables & {
        "contamination_events", "hydraulic_heads", "ml_models",
        "piezometric_heads", "spatial_analysis_results",
    }
    assert not revived, f"orphan tables reintroduced: {sorted(revived)}"
