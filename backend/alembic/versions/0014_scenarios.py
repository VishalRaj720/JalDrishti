"""P3 (final slice): named, saveable scenarios.

PRODUCT_DESIGN.md §3.3 — "saved, named, shareable scenarios: what makes this a
product rather than a calculator". `simulation_runs.scenario_id` was reserved by
0012; this is the table it points at, and the FK that makes the link real.

A scenario is a NAMED SET OF INPUTS, not a result. Runs stay immutable and
pinned to the model that produced them (0012), so re-running a scenario after a
retrain yields a second run with a different `artifacts_sha` — and the
difference is visible rather than silently overwriting the first. That is the
whole point of separating the two.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0014_scenarios'
down_revision = '0013_dataset_sync_state'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'scenarios',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('isr_point_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('params', postgresql.JSONB(), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['isr_point_id'], ['isr_points.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        # Unique per site, not globally: two districts may both want "baseline".
        sa.UniqueConstraint('isr_point_id', 'name', name='uq_scenario_site_name'),
    )
    op.create_index('ix_scenarios_isr_point', 'scenarios', ['isr_point_id'])

    op.create_foreign_key('fk_sim_runs_scenario', 'simulation_runs', 'scenarios',
                          ['scenario_id'], ['id'], ondelete='SET NULL')

    op.execute('ALTER TABLE scenarios ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE scenarios FORCE ROW LEVEL SECURITY')
    # Scenarios name a hypothetical ISR site, so they inherit the coordinate
    # sensitivity of `isr_points`: staff read, citizens never.
    op.execute("""
        CREATE POLICY scenarios_read ON scenarios FOR SELECT
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
                 IN ('admin','regulator','analyst','field_officer')
        );
    """)
    op.execute("""
        CREATE POLICY scenarios_write ON scenarios FOR ALL
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
                 IN ('admin','analyst')
        )
        WITH CHECK (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
                 IN ('admin','analyst')
        );
    """)


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS scenarios_read ON scenarios')
    op.execute('DROP POLICY IF EXISTS scenarios_write ON scenarios')
    op.drop_constraint('fk_sim_runs_scenario', 'simulation_runs',
                       type_='foreignkey')
    op.drop_table('scenarios')
