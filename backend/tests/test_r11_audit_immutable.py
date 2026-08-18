"""The audit log must stay append-only.

It already is, at two independent layers: `api/v1/audit.py` exposes only a GET,
and migration `0009` grants `audit_log` an INSERT policy and a SELECT policy and
nothing else — so as `jaldrishti_app` (NOSUPERUSER, NOBYPASSRLS) an UPDATE or
DELETE is refused by Postgres, not merely absent from the API.

What was missing is a guard. Both properties are the kind a later change removes
by accident — a convenience "clean up test rows" endpoint, or a migration that
adds `FOR ALL` where it meant `FOR SELECT` — and nothing would have failed. These
tests are cheap and pin both.

R11 considered making audit entries admin-deletable and did not: an audit log the
audited party can quietly remove rows from is not evidence, and `/audit` exists
precisely to answer "who changed the model's inputs, and when".
"""
import pytest
from sqlalchemy import text

from app.main import app


def test_audit_router_exposes_no_mutating_route():
    """No POST/PUT/PATCH/DELETE anywhere under /audit."""
    offenders = [
        (m, r.path)
        for r in app.routes if hasattr(r, "methods") and "/audit" in r.path
        for m in r.methods
        if m in {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert offenders == [], (
        f"the audit log gained a mutating route: {offenders}. An audit log a user "
        f"can edit is not an audit log.")


def test_no_migration_grants_audit_log_an_update_or_delete_policy():
    """Postgres itself must refuse to change or remove an entry.

    Asserted against the **migration source**, not a live catalog. The test
    database is built from ORM metadata rather than by running alembic, so it
    carries no RLS policies at all — a `pg_policies` query here returns an empty
    set and every such assertion passes vacuously, proving nothing. (The same
    blind spot makes `test_p6_roles.py`'s regulator-policy check weaker than it
    looks.) Reading the DDL that production actually applies is the only version
    of this check that can fail when it should.
    """
    import re
    from pathlib import Path

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    pattern = re.compile(
        r"CREATE\s+POLICY\s+(\w+)\s+ON\s+audit_log\s+FOR\s+(\w+)", re.I)

    found: list[tuple[str, str, str]] = []
    for mig in sorted(versions.glob("*.py")):
        for name, cmd in pattern.findall(mig.read_text(encoding="utf-8")):
            found.append((mig.name, name, cmd.upper()))

    assert found, "no CREATE POLICY on audit_log found in any migration"
    offenders = [f for f in found if f[2] in {"UPDATE", "DELETE", "ALL"}]
    assert not offenders, (
        f"a migration grants audit_log a mutating policy: {offenders}. Only "
        f"INSERT and SELECT may exist — 'FOR ALL' silently grants UPDATE and "
        f"DELETE too, which would make the audit log editable by the app role.")

    # And nothing may drop the protection by disabling RLS on the table.
    for mig in sorted(versions.glob("*.py")):
        body = mig.read_text(encoding="utf-8")
        assert not re.search(r"audit_log\s+DISABLE\s+ROW\s+LEVEL\s+SECURITY", body, re.I), (
            f"{mig.name} disables RLS on audit_log")


@pytest.mark.asyncio
async def test_factory_reset_is_audited_and_refuses_without_confirmation(
        client, admin_token):
    """The destructive path must be awkward, and must leave a permanent record."""
    r = await client.post(
        "/api/v1/model-ops/factory-reset?dry_run=false",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 400, r.text
    assert "confirm=RESET" in r.json()["detail"]

    # A dry run reports without writing, and needs no confirmation.
    r = await client.post(
        "/api/v1/model-ops/factory-reset?dry_run=true",
        headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert "by_file" in body
    assert "NOT deleted" in body["note"]
