"""P2: site ownership + row-level security policies.

PRODUCT_DESIGN.md section 2: "Enforced with row-level security in Postgres keyed
on `owner_org_id` and role, not only in application code — so a service bug
cannot leak site detail to a citizen session."

THE POLICIES ONLY BITE IF THE API CONNECTS AS A NON-BYPASSRLS ROLE. This was
verified the hard way before the policies were written: with the app's current
`postgres` connection, a table carrying FORCE ROW LEVEL SECURITY and a
`USING (false)` deny-all policy still returned every row, because `postgres` has
`rolbypassrls = true`. Run `python -m scripts.create_app_role` and point the API
at `jaldrishti_app`. `app/main.py` warns loudly at startup while that is
outstanding, and `tests/test_rls.py` proves enforcement by connecting as the
restricted role rather than asserting the policies merely exist.

The policies read three per-transaction settings, set by `get_db`:

    app.current_role      the caller's role name, '' when unauthenticated
    app.current_org_id    the caller's organisation, '' when none
    app.bypass_rls        'on' for trusted internal work (seed, ingest jobs)

`current_setting(..., true)` returns NULL rather than erroring when a setting is
absent, so a connection that never sets them (a migration, a psql session) is
treated as unauthenticated rather than crashing.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_isr_owner_org_and_rls'
down_revision = '0008_viewer_to_citizen'
branch_labels = None
depends_on = None

# Staff roles may see every site. `citizen` (and legacy `viewer`) may not: design
# section 2 forbids them precise coordinates for a hypothetical site next to a
# named village. This mirrors `app.dependencies.STAFF_ROLES`; the two are pinned
# together by tests/test_rls.py.
_STAFF = "('admin','regulator','analyst','field_officer')"

_ISR_READ = f"""
CREATE POLICY isr_points_read ON isr_points FOR SELECT
USING (
    coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
    OR coalesce(current_setting('app.current_role', true), '') IN {_STAFF}
);
"""

_ISR_WRITE = f"""
CREATE POLICY isr_points_write ON isr_points FOR ALL
USING (
    coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
    OR coalesce(current_setting('app.current_role', true), '') IN ('admin','regulator')
    OR (
        coalesce(current_setting('app.current_role', true), '') = 'analyst'
        AND owner_org_id::text = coalesce(current_setting('app.current_org_id', true), '')
    )
)
WITH CHECK (
    coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
    OR coalesce(current_setting('app.current_role', true), '') IN ('admin','regulator')
    OR (
        coalesce(current_setting('app.current_role', true), '') = 'analyst'
        AND owner_org_id::text = coalesce(current_setting('app.current_org_id', true), '')
    )
);
"""

# The audit log is append-only at the database, not merely by convention: there
# is no UPDATE or DELETE policy, so those are denied for any non-bypassing role
# even if an endpoint is added by mistake.
_AUDIT_INSERT = """
CREATE POLICY audit_log_insert ON audit_log FOR INSERT
WITH CHECK (true);
"""

_AUDIT_READ = """
CREATE POLICY audit_log_read ON audit_log FOR SELECT
USING (
    coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
    OR coalesce(current_setting('app.current_role', true), '') IN ('admin','regulator')
);
"""


def upgrade() -> None:
    op.add_column('isr_points', sa.Column(
        'owner_org_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_isr_points_org', 'isr_points', 'orgs',
                          ['owner_org_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_isr_points_owner_org', 'isr_points', ['owner_org_id'])

    # Existing sites belong to the host organisation. Nullable so a site can be
    # created before its org is decided; the write policy treats NULL as
    # not-mine for an analyst, which fails closed.
    op.execute("""
        UPDATE isr_points SET owner_org_id = (SELECT id FROM orgs WHERE code = 'BITS')
        WHERE owner_org_id IS NULL AND EXISTS (SELECT 1 FROM orgs WHERE code = 'BITS')
    """)

    for table in ('isr_points', 'audit_log'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        # FORCE so the policies apply to the table OWNER too, not just to other
        # roles. Without it, running the app as the owner silently bypasses them.
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

    op.execute(_ISR_READ)
    op.execute(_ISR_WRITE)
    op.execute(_AUDIT_INSERT)
    op.execute(_AUDIT_READ)


def downgrade() -> None:
    for policy, table in (('isr_points_read', 'isr_points'),
                          ('isr_points_write', 'isr_points'),
                          ('audit_log_insert', 'audit_log'),
                          ('audit_log_read', 'audit_log')):
        op.execute(f'DROP POLICY IF EXISTS {policy} ON {table}')
    for table in ('isr_points', 'audit_log'):
        op.execute(f'ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')

    op.drop_index('ix_isr_points_owner_org', table_name='isr_points')
    op.drop_constraint('fk_isr_points_org', 'isr_points', type_='foreignkey')
    op.drop_column('isr_points', 'owner_org_id')
