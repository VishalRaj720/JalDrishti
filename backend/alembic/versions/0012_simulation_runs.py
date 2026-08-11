"""P3: reproducible simulation runs backed by the real ml_pipeline engine.

PRODUCT_DESIGN.md §5.3. Replaces nothing — the legacy `simulations` table stays
untouched for the rows it already holds — and gives the real engine somewhere to
write that can be defended a year later.

WHY THE REPRODUCIBILITY COLUMNS ARE NOT NULLABLE. A screening number a regulator
acted on has to be re-derivable. `model_card_sha`, `artifacts_sha` and
`code_version` pin the three things that can change underneath a result: the
deployed model, the artifact bundle it loaded, and the code that drove it. If a
run cannot record them it should fail, not be written unpinned.

`inputs` stores the RESOLVED inputs the engine actually used, not the raw
request. The pin resolves aquifer properties, flow azimuth, gradient and
baselines from `ml_pipeline`'s own datasets, and those resolved values are what
reproduce the run — the slider payload alone does not.

`dataset_version_id` is nullable on purpose. The surrogate reads
`Datasets/` and its own artifacts, NOT the database, so a run is not pinned to a
`dataset_versions` row today. The column exists for when a run does depend on
database-held data; leaving it nullable is honest, inventing a link would not be.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012_simulation_runs'
down_revision = '0011_fix_swapped_district_axes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'simulation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('isr_point_id', postgresql.UUID(as_uuid=True), nullable=False),
        # Reserved for named/saved scenarios, the remaining slice of P3.
        sa.Column('scenario_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False,
                  server_default='queued'),
        sa.Column('engine', sa.String(length=16), nullable=False,
                  server_default='both'),
        sa.Column('species', sa.String(length=32), nullable=False),

        # ── reproducibility ──
        sa.Column('model_card_sha', sa.String(length=64), nullable=True),
        sa.Column('artifacts_sha', sa.String(length=64), nullable=True),
        sa.Column('code_version', sa.String(length=64), nullable=True),
        sa.Column('dataset_version_id', postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column('request', postgresql.JSONB(), nullable=False),
        sa.Column('inputs', postgresql.JSONB(), nullable=True),
        sa.Column('metrics', postgresql.JSONB(), nullable=True),
        sa.Column('excursion', postgresql.JSONB(), nullable=True),
        sa.Column('extrapolation', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('hydro', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('runtime_ms', sa.Integer(), nullable=True),

        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),

        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name='ck_sim_runs_status'),
        sa.CheckConstraint("engine IN ('analytical','ml','both')",
                           name='ck_sim_runs_engine'),
        # A completed run must carry its provenance, or it cannot be defended.
        sa.CheckConstraint(
            "status <> 'completed' OR (model_card_sha IS NOT NULL "
            "AND artifacts_sha IS NOT NULL AND code_version IS NOT NULL)",
            name='ck_sim_runs_completed_is_pinned'),
        sa.ForeignKeyConstraint(['isr_point_id'], ['isr_points.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dataset_version_id'], ['dataset_versions.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sim_runs_isr_point', 'simulation_runs', ['isr_point_id'])
    op.create_index('ix_sim_runs_created_at', 'simulation_runs', ['created_at'])

    op.execute('ALTER TABLE simulation_runs ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE simulation_runs FORCE ROW LEVEL SECURITY')
    # Runs describe hypothetical ISR sites, so they carry the same coordinate
    # sensitivity as `isr_points`: staff only, citizens never.
    op.execute("""
        CREATE POLICY sim_runs_read ON simulation_runs FOR SELECT
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
                 IN ('admin','regulator','analyst','field_officer')
        );
    """)
    op.execute("""
        CREATE POLICY sim_runs_write ON simulation_runs FOR ALL
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
    op.execute('DROP POLICY IF EXISTS sim_runs_read ON simulation_runs')
    op.execute('DROP POLICY IF EXISTS sim_runs_write ON simulation_runs')
    op.drop_table('simulation_runs')
