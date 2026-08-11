"""Row-level security: proven by enforcement, not by the policies existing.

WHY THIS FILE IS SHAPED LIKE THIS. It would be easy — and worthless — to assert
that rows exist in `pg_policies`. The application currently connects as
`postgres`, which has `rolbypassrls = true`, and RLS does not apply to such a
role at all. That was verified before the policies were written: a table with
FORCE ROW LEVEL SECURITY and a `USING (false)` deny-all policy still returned
every row to that connection.

So every test here connects as a purpose-made NOSUPERUSER NOBYPASSRLS role and
checks what that connection can actually see. If the policies are dropped, or
the app role is granted BYPASSRLS, or `SET LOCAL` is changed to `SET`, these
fail.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import pytest

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
RLS_DB = os.getenv("RLS_PROBE_DB", "jd_rls_probe_test")
RLS_ROLE = "jd_rls_probe_role"
RLS_PASSWORD = "probe-only-not-a-secret"


def _connect(dbname, user=None, password=None):
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=user or settings.DB_USER,
        password=password if user else settings.DB_PASSWORD,
        dbname=dbname,
    )
    conn.autocommit = True
    return conn


@pytest.fixture(scope="module")
def rls_db():
    """A migrated database plus a restricted role that cannot bypass RLS."""
    admin = _connect("postgres")
    with admin.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()", (RLS_DB,))
        cur.execute(f'DROP DATABASE IF EXISTS "{RLS_DB}"')
        cur.execute(f'CREATE DATABASE "{RLS_DB}"')
    admin.close()

    try:
        probe = _connect(RLS_DB)
        with probe.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        probe.close()

        env = dict(os.environ)
        env["DATABASE_URL"] = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{RLS_DB}"
        )
        proc = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                              cwd=BACKEND_DIR, env=env, capture_output=True,
                              text=True, timeout=300)
        assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

        owner = _connect(RLS_DB)
        with owner.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (RLS_ROLE,))
            if cur.fetchone():
                cur.execute(f"ALTER ROLE {RLS_ROLE} WITH LOGIN NOSUPERUSER "
                            f"NOBYPASSRLS PASSWORD %s", (RLS_PASSWORD,))
            else:
                cur.execute(f"CREATE ROLE {RLS_ROLE} WITH LOGIN NOSUPERUSER "
                            f"NOBYPASSRLS PASSWORD %s", (RLS_PASSWORD,))
            cur.execute(f'GRANT CONNECT ON DATABASE "{RLS_DB}" TO {RLS_ROLE}')
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_ROLE}")
            cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                        f"IN SCHEMA public TO {RLS_ROLE}")
            cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public "
                        f"TO {RLS_ROLE}")

            # Two orgs and one site owned by the first.
            cur.execute("INSERT INTO orgs (code, name, kind) VALUES "
                        "('ORGA','Org A','regulator'),('ORGB','Org B','regulator') "
                        "RETURNING id, code")
            orgs = {code: oid for oid, code in cur.fetchall()}
            cur.execute(
                "INSERT INTO isr_points (id, name, location, owner_org_id) "
                "VALUES (%s, 'Secret Site', "
                "ST_SetSRID(ST_MakePoint(86.36, 22.65), 4326), %s)",
                (str(uuid.uuid4()), orgs["ORGA"]),
            )
            cur.execute("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname=%s",
                        (RLS_ROLE,))
            bypass, sup = cur.fetchone()
            assert not bypass and not sup, "probe role could bypass RLS"
        owner.close()

        yield {"orgs": orgs}
    finally:
        admin = _connect("postgres")
        with admin.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (RLS_DB,))
            cur.execute(f'DROP DATABASE IF EXISTS "{RLS_DB}"')
            cur.execute(f"DROP ROLE IF EXISTS {RLS_ROLE}")
        admin.close()


def _as_role(role_name: str, org_id=None, sql="SELECT count(*) FROM isr_points"):
    """Run `sql` on the restricted connection with an RLS context applied."""
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=RLS_ROLE, password=RLS_PASSWORD, dbname=RLS_DB,
    )
    try:
        with conn:                      # one transaction, so SET LOCAL applies
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_role', %s, true), "
                    "       set_config('app.current_org_id', %s, true), "
                    "       set_config('app.bypass_rls', 'off', true)",
                    (role_name, str(org_id) if org_id else ""),
                )
                cur.execute(sql)
                return cur.fetchone()
    finally:
        conn.close()


# ── the control: the app's real connection does NOT enforce ──────────

def test_postgres_superuser_bypasses_rls(rls_db):
    """Documents the blocker. If this ever fails, `postgres` stopped being a
    superuser and the deployment note in scripts/create_app_role.py is stale."""
    conn = _connect(RLS_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.current_role', 'citizen', false)")
        cur.execute("SELECT count(*) FROM isr_points")
        visible = cur.fetchone()[0]
    conn.close()
    assert visible == 1, (
        "a citizen context on the superuser connection saw "
        f"{visible} site(s) — RLS is inert here, which is exactly why the API "
        "must connect as jaldrishti_app."
    )


# ── enforcement, under a role that cannot bypass ─────────────────────

@pytest.mark.parametrize("role", ["citizen", "viewer"])
def test_public_roles_cannot_see_isr_sites(rls_db, role):
    assert _as_role(role)[0] == 0, (
        f"{role} could read isr_points. Design section 2 forbids precise "
        f"coordinates for a hypothetical site to non-staff."
    )


@pytest.mark.parametrize("role", ["admin", "regulator", "analyst", "field_officer"])
def test_staff_roles_can_see_isr_sites(rls_db, role):
    assert _as_role(role)[0] == 1


def test_unauthenticated_context_sees_nothing(rls_db):
    """A route that forgets its auth dependency must fail closed."""
    assert _as_role("")[0] == 0


def _rowcount_as_role(role_name, sql, org_id=None):
    """Run a write on the restricted connection; return rows actually affected.

    NOTE ON RLS SEMANTICS, which the first version of these tests got wrong: a
    write whose USING clause does not match affects ZERO ROWS — it does not
    raise. Postgres only errors on a WITH CHECK violation (an attempt to write a
    row you could not then see). So "denied" here means rowcount 0, and the
    denial is SILENT. Anything relying on an exception to detect tampering would
    never fire.
    """
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=RLS_ROLE, password=RLS_PASSWORD, dbname=RLS_DB,
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.current_role', %s, true), "
                    "       set_config('app.current_org_id', %s, true), "
                    "       set_config('app.bypass_rls', 'off', true)",
                    (role_name, str(org_id) if org_id else ""),
                )
                cur.execute(sql)
                return cur.rowcount
    finally:
        conn.close()


def test_analyst_cannot_write_another_orgs_site(rls_db):
    affected = _rowcount_as_role(
        "analyst", "UPDATE isr_points SET name = 'hijacked'",
        org_id=rls_db["orgs"]["ORGB"])
    assert affected == 0, "an analyst modified a site belonging to another org"
    # and the row is genuinely untouched
    conn = _connect(RLS_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM isr_points WHERE name = 'hijacked'")
        assert cur.fetchone()[0] == 0
    conn.close()


def test_analyst_can_write_its_own_orgs_site(rls_db):
    affected = _rowcount_as_role(
        "analyst", "UPDATE isr_points SET name = 'renamed'",
        org_id=rls_db["orgs"]["ORGA"])
    assert affected == 1


def test_citizen_cannot_write_any_site(rls_db):
    assert _rowcount_as_role("citizen", "UPDATE isr_points SET name = 'x'") == 0
    assert _rowcount_as_role("citizen", "DELETE FROM isr_points") == 0


def test_audit_log_is_append_only_at_the_database(rls_db):
    """No UPDATE or DELETE policy exists, so neither can affect a row — even for
    admin, and even if an endpoint is added by mistake.

    The denial is silent (rowcount 0), not an error; see `_rowcount_as_role`.
    """
    conn = psycopg2.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=RLS_ROLE, password=RLS_PASSWORD, dbname=RLS_DB,
    )
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.current_role','admin',true)")
                cur.execute("INSERT INTO audit_log (action, entity_type) "
                            "VALUES ('probe','test')")
    finally:
        conn.close()

    assert _rowcount_as_role("admin", "UPDATE audit_log SET action='tampered'") == 0
    assert _rowcount_as_role("admin", "DELETE FROM audit_log") == 0

    owner = _connect(RLS_DB)
    with owner.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action = 'probe'")
        assert cur.fetchone()[0] == 1, "the audit entry was destroyed"
        cur.execute("SELECT count(*) FROM audit_log WHERE action = 'tampered'")
        assert cur.fetchone()[0] == 0
    owner.close()


def test_policy_staff_list_matches_the_application(rls_db):
    """The SQL policy and app.dependencies.STAFF_ROLES must not drift apart."""
    from app.dependencies import STAFF_ROLES
    conn = _connect(RLS_DB)
    with conn.cursor() as cur:
        cur.execute("SELECT qual FROM pg_policies WHERE policyname='isr_points_read'")
        qual = cur.fetchone()[0]
    conn.close()
    for role in STAFF_ROLES:
        assert f"'{role.value}'" in qual, (
            f"{role.value} is in STAFF_ROLES but not in the isr_points_read policy"
        )
