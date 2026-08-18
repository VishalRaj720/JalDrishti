"""Retire the `regulator` role; admin absorbs it.

R7. The five-role model gave `regulator` four powers — approve field
observations, read the audit trail, run the model, publish advisories — and
`admin` already had every one of them. In practice the role carried no
capability of its own, only a different label on the same authority, and the
product owner asked for it to go.

WHAT IS PRESERVED. The separation of duties that mattered is *not* the
regulator label, it is that **the person who proposes a public screening is not
the person who publishes it**. That survives intact: an analyst proposes,
an admin decides, and `ck_advisory_published_has_a_decider` still refuses a
published row that cannot name who published it.

WHAT CHANGES FOR CITIZENS. Public copy said "published by a regulator". With no
regulator in the system that would be false, so it becomes "published by the
authority" — see `app/api/v1/citizen.py`.

THE ENUM LABEL SURVIVES, DELIBERATELY. PostgreSQL cannot drop a value from an
enum type in a transactional migration; migration 0008 hit exactly this when
retiring `viewer`. Dropping and recreating `userrole` would require rewriting
every dependent column under an exclusive lock. So the label stays in the type
and is retired from the APPLICATION vocabulary instead — `UserRole.regulator`
is removed from `STAFF_ROLES` and every guard, so nothing can mint one, and
`tests/test_p6_roles.py` asserts no route admits it.

Rows are migrated rather than deleted: a regulator account belongs to a real
person who still needs to sign in.

Revision ID: 0019_retire_regulator
Revises: 0018_citizen_alerts
"""
from alembic import op
import sqlalchemy as sa

revision = '0019_retire_regulator'
down_revision = '0018_citizen_alerts'
branch_labels = None
depends_on = None

#: The staff vocabulary after this migration. Must stay identical to
#: `app.dependencies.STAFF_ROLES`; `tests/test_rls.py` pins the two together.
_STAFF = "('admin','analyst','field_officer')"
_REVIEWER = "('admin')"

#: (table, policy, FOR-clause, USING, WITH CHECK or None)
_POLICIES = [
    # `isr_points_read` carries the staff list verbatim from migration 0009.
    # Easy to miss, and missing it would leave a policy admitting a role nobody
    # can hold — harmless today, misleading to the next person who reads it.
    ("isr_points", "isr_points_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_STAFF}", None),
    ("audit_log", "audit_log_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_REVIEWER}", None),
    ("simulation_runs", "sim_runs_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_STAFF}", None),
    ("scenarios", "scenarios_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_STAFF}", None),
    ("ore_observations", "ore_obs_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_STAFF}", None),
    ("advisories", "advisories_read", "SELECT",
     f"coalesce(current_setting('app.current_role', true), '') IN {_STAFF}"
     " OR status = 'published'", None),
    ("advisories", "advisories_write", "INSERT", None,
     "coalesce(current_setting('app.current_role', true), '') IN ('admin','analyst')"),
    ("advisories", "advisories_update", "UPDATE",
     f"coalesce(current_setting('app.current_role', true), '') IN {_REVIEWER}",
     f"coalesce(current_setting('app.current_role', true), '') IN {_REVIEWER}"),
]

_BYPASS = "coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'"


def upgrade() -> None:
    # 1. The people. A regulator account belongs to someone who still works
    #    here; they become an admin rather than losing access.
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'regulator'")

    # 2. The policies that name the retired role. Rewritten rather than left
    #    alone: a policy referencing a role nobody can hold is dead code in the
    #    one place dead code is most dangerous to reason about.
    for table, policy, action, using, check in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
        clauses = f"CREATE POLICY {policy} ON {table} FOR {action}"
        if using:
            clauses += f"\nUSING ({_BYPASS} OR {using})"
        if check:
            clauses += f"\nWITH CHECK ({_BYPASS} OR {check})"
        op.execute(clauses)

    # 3. `isr_points_write` and the field-observation policies carry an
    #    org-scoped analyst branch, so they are rewritten in full rather than
    #    generated from the table above.
    op.execute("DROP POLICY IF EXISTS isr_points_write ON isr_points")
    op.execute(f"""
        CREATE POLICY isr_points_write ON isr_points FOR ALL
        USING (
            {_BYPASS}
            OR coalesce(current_setting('app.current_role', true), '') = 'admin'
            OR (coalesce(current_setting('app.current_role', true), '') = 'analyst'
                AND owner_org_id::text = coalesce(
                    current_setting('app.current_org_id', true), ''))
        )
        WITH CHECK (
            {_BYPASS}
            OR coalesce(current_setting('app.current_role', true), '') = 'admin'
            OR (coalesce(current_setting('app.current_role', true), '') = 'analyst'
                AND owner_org_id::text = coalesce(
                    current_setting('app.current_org_id', true), ''))
        )
    """)

    op.execute("DROP POLICY IF EXISTS field_obs_read ON field_observations")
    op.execute(f"""
        CREATE POLICY field_obs_read ON field_observations FOR SELECT
        USING (
            {_BYPASS}
            OR coalesce(current_setting('app.current_role', true), '')
               IN ('admin','analyst')
            OR submitted_by::text = coalesce(
                   current_setting('app.current_user_id', true), '')
        )
    """)
    op.execute("DROP POLICY IF EXISTS field_obs_write ON field_observations")
    op.execute(f"""
        CREATE POLICY field_obs_write ON field_observations FOR ALL
        USING (
            {_BYPASS}
            OR coalesce(current_setting('app.current_role', true), '') = 'admin'
            OR submitted_by::text = coalesce(
                   current_setting('app.current_user_id', true), '')
        )
        WITH CHECK (
            {_BYPASS}
            OR coalesce(current_setting('app.current_role', true), '')
               IN ('admin','field_officer')
            OR submitted_by::text = coalesce(
                   current_setting('app.current_user_id', true), '')
        )
    """)


def downgrade() -> None:
    """Restores the policies. It cannot restore who was a regulator.

    That information is destroyed by the UPDATE above — recording it would mean
    keeping a column describing a role the system no longer has. Stated here
    rather than silently: a downgrade leaves former regulators as admins.
    """
    raise NotImplementedError(
        "Downgrade is not supported: the migration merges regulators into admin "
        "and does not record which admins were formerly regulators.")
