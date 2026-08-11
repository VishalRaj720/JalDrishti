"""The two guarantees that make the review workflow worth having.

1. Pending field data cannot reach any calculation.
2. RLS still binds after the new tables were added, under a role that cannot
   bypass it — asserted by connecting as such a role, not by reading pg_policies.

`test_field_observations.py` covers the workflow itself; this file covers the
boundary around it.
"""
import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import pytest

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
RLS_DB = os.getenv("FIELDOBS_PROBE_DB", "jd_fieldobs_probe_test")
RLS_ROLE = "jd_fieldobs_probe_role"
RLS_PW = "probe-only-not-a-secret"


# ── pending data cannot reach the ML / excursion path ────────────────

def test_ml_pipeline_does_not_read_the_database():
    """The strongest form of 'pending data cannot affect calculations'.

    `ml_pipeline/` loads its inputs from `Datasets/` and its own artifacts. It
    holds no database driver, no session, no connection string — so no row in
    Postgres, approved or pending, can reach the physics engine, the surrogate
    or the excursion indicators. If this ever fails, the isolation argument in
    PRODUCT_DESIGN.md needs rewriting, not patching.
    """
    offenders = []
    for path in (REPO_ROOT / "ml_pipeline").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        for needle in ("import psycopg", "import asyncpg", "from sqlalchemy",
                       "import sqlalchemy", "DATABASE_URL", "groundwater_db"):
            if needle in src:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {needle}")
    assert not offenders, (
        "ml_pipeline gained a database dependency:\n  " + "\n  ".join(offenders))


def test_ml_artifacts_are_unchanged():
    """No part of this feature retrains or rewrites a model artifact."""
    baseline_path = BACKEND_DIR / "tests" / "ml_artifact_hashes.json"
    artifacts = REPO_ROOT / "ml_pipeline" / "ml" / "artifacts"
    current = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(artifacts.iterdir()) if p.is_file()
    }
    if not baseline_path.exists():
        baseline_path.write_text(json.dumps(current, indent=1))
        pytest.skip("baseline written")
    baseline = json.loads(baseline_path.read_text())
    changed = {k for k in baseline if baseline[k] != current.get(k)}
    missing = set(baseline) - set(current)
    assert not changed and not missing, (
        f"ML artifacts changed: {sorted(changed | missing)}. Backend work must "
        f"never touch them; if a retrain was intended, update the baseline "
        f"deliberately."
    )


# ── RLS, under a role that cannot bypass it ──────────────────────────

def _admin(dbname="postgres"):
    c = psycopg2.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                         user=settings.DB_USER, password=settings.DB_PASSWORD,
                         dbname=dbname)
    c.autocommit = True
    return c


@pytest.fixture(scope="module")
def probe():
    admin = _admin()
    with admin.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()", (RLS_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{RLS_DB}"')
        cur.execute(f'CREATE DATABASE "{RLS_DB}"')
    admin.close()
    try:
        c = _admin(RLS_DB)
        with c.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        c.close()

        env = dict(os.environ)
        env["DATABASE_URL"] = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{RLS_DB}")
        env.pop("MIGRATION_DATABASE_URL", None)
        p = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                           cwd=BACKEND_DIR, env=env, capture_output=True,
                           text=True, timeout=300)
        assert p.returncode == 0, f"{p.stdout}\n{p.stderr}"

        owner = _admin(RLS_DB)
        with owner.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RLS_ROLE,))
            verb = "ALTER" if cur.fetchone() else "CREATE"
            cur.execute(f"{verb} ROLE {RLS_ROLE} WITH LOGIN NOSUPERUSER "
                        f"NOBYPASSRLS PASSWORD %s", (RLS_PW,))
            cur.execute(f'GRANT CONNECT ON DATABASE "{RLS_DB}" TO {RLS_ROLE}')
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                        f"IN SCHEMA public TO {RLS_ROLE}")
            cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
                        f"TO {RLS_ROLE}")

            cur.execute("INSERT INTO users (id, username, email, "
                        "hashed_password, role) VALUES "
                        "(gen_random_uuid(),'o1','o1@x.com','x','field_officer'),"
                        "(gen_random_uuid(),'o2','o2@x.com','x','field_officer') "
                        "RETURNING id, username")
            users = {u: i for i, u in cur.fetchall()}
            cur.execute(
                "INSERT INTO field_observations "
                "(id, observation_type, operation, target_table, proposed, "
                " status, submitted_by) VALUES "
                "(gen_random_uuid(),'ore_presence','create','ore_observations',"
                " '{\"name\":\"secret\"}'::jsonb,'pending',%s)",
                (users["o1"],))
            cur.execute(
                "INSERT INTO ore_observations (name, location, ore_zone, "
                "observed_at) VALUES ('approved ore', "
                "ST_SetSRID(ST_MakePoint(86.3,22.6),4326)::geography, "
                "'deposit', now())")
        owner.close()
        yield users
    finally:
        admin = _admin()
        with admin.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (RLS_DB,))
            cur.execute(f'DROP DATABASE IF EXISTS "{RLS_DB}"')
            cur.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
        admin.close()


def _as(role, sql, user_id=None):
    conn = psycopg2.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                            user=RLS_ROLE, password=RLS_PW, dbname=RLS_DB)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_role',%s,true), "
                    "       set_config('app.current_user_id',%s,true), "
                    "       set_config('app.bypass_rls','off',true)",
                    (role, str(user_id) if user_id else ""))
                cur.execute(sql)
                return cur.fetchone()
    finally:
        conn.close()


def test_citizen_cannot_read_field_observations(probe):
    assert _as("citizen", "SELECT count(*) FROM field_observations")[0] == 0


def test_citizen_cannot_read_ore_observations(probe):
    assert _as("citizen", "SELECT count(*) FROM ore_observations")[0] == 0


def test_reviewers_see_the_whole_queue(probe):
    for role in ("admin", "regulator", "analyst"):
        assert _as(role, "SELECT count(*) FROM field_observations")[0] == 1, role


def test_field_officer_sees_only_their_own_submissions(probe):
    """One officer must not browse another's unreviewed observations."""
    mine = _as("field_officer", "SELECT count(*) FROM field_observations",
               user_id=probe["o1"])[0]
    theirs = _as("field_officer", "SELECT count(*) FROM field_observations",
                 user_id=probe["o2"])[0]
    assert mine == 1
    assert theirs == 0


def test_ore_observations_are_writable_only_under_the_system_bypass(probe):
    """The approval path holds the bypass; no ROLE may write here directly —
    so an authoritative ore record cannot appear without a review."""
    conn = psycopg2.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                            user=RLS_ROLE, password=RLS_PW, dbname=RLS_DB)
    try:
        for role in ("admin", "regulator", "field_officer"):
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.current_role',%s,true), "
                        "       set_config('app.bypass_rls','off',true)", (role,))
                    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                        cur.execute(
                            "INSERT INTO ore_observations (name, location, "
                            "ore_zone, observed_at) VALUES ('sneaky', "
                            "ST_SetSRID(ST_MakePoint(1,1),4326)::geography, "
                            "'deposit', now())")
    finally:
        conn.close()


def test_unauthenticated_context_sees_no_field_data(probe):
    assert _as("", "SELECT count(*) FROM field_observations")[0] == 0
    assert _as("", "SELECT count(*) FROM ore_observations")[0] == 0
