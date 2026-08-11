"""P1: drop five orphan tables left behind when their ORM models were deleted.

PRODUCT_DESIGN.md section 1.4b / 5.2.

`contamination_events`, `hydraulic_heads`, `ml_models`, `piezometric_heads` and
`spatial_analysis_results` exist in `groundwater_db` but have no ORM model. They
are unreachable from the application, invisible to SQLAlchemy, and make the
schema a reviewer connects to disagree with the ERD. All five were verified
empty (0 rows) before this migration was written.

WHERE THEY CAME FROM. All five were created by migrations -- `hydraulic_heads`
and `ml_models` by 0001_initial, and `contamination_events`,
`spatial_analysis_results` and `piezometric_heads` by 0004_month3_schema. The
migration chain is healthy and `alembic upgrade head` on an empty database
reproduces exactly this schema. What broke was the other direction: the ORM
models were deleted without a matching down-migration, so the chain kept
creating tables the application no longer knew about.

The DDL in `downgrade()` was reconstructed from the LIVE database
(information_schema + pg_indexes) and cross-checked against 0001/0004, so the
down path restores the columns, indexes and constraints that actually existed.

`tests/test_schema_integrity.py` now pins migrations and ORM metadata together
so this cannot silently recur.

`mlmodeltype` is dropped with `ml_models`, the only table that used it.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_drop_orphan_tables'
down_revision = '0005_water_samples_synth'
branch_labels = None
depends_on = None

_ORPHANS = (
    'spatial_analysis_results',   # FKs into simulations + aquifers
    'piezometric_heads',          # FK into monitoring_stations
    'contamination_events',       # FK into isr_points
    'hydraulic_heads',            # FK into aquifers
    'ml_models',
)


def upgrade() -> None:
    # Refuse to run if anyone has written to these since the audit. Dropping an
    # empty orphan is housekeeping; dropping a populated one is data loss, and
    # this migration is not authorised to make that call silently.
    conn = op.get_bind()
    for table in _ORPHANS:
        n = conn.execute(sa.text(f'SELECT count(*) FROM {table}')).scalar()
        if n:
            raise RuntimeError(
                f'{table} holds {n} row(s); it was empty when this migration '
                f'was written. Refusing to drop it. Inspect the data and '
                f'decide deliberately.'
            )

    for table in _ORPHANS:
        op.drop_table(table)

    # Only ml_models referenced it.
    op.execute('DROP TYPE IF EXISTS mlmodeltype')


def downgrade() -> None:
    # create_type=False is load-bearing. SQLAlchemy emits CREATE TYPE
    # automatically for an enum column when it builds the table, which collides
    # with the explicit create below ("type mlmodeltype already exists") and
    # aborts the downgrade. Create it once, here, and tell the table DDL not to.
    mlmodeltype = postgresql.ENUM(
        'regression', 'classification', 'plume_estimation',
        name='mlmodeltype', create_type=False,
    )
    mlmodeltype.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'ml_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('type', mlmodeltype, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('feature_schema', postgresql.JSONB(), nullable=True),
        sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metrics', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'hydraulic_heads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('head_value', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'contamination_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('isr_point_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('contaminant', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('exceeded', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['isr_point_id'], ['isr_points.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contamination_events_detected_at',
                    'contamination_events', ['detected_at'])
    op.create_index('ix_contamination_events_isr_point_id',
                    'contamination_events', ['isr_point_id'])

    op.create_table(
        'piezometric_heads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('measured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('head_value_m', sa.Float(), nullable=False),
        sa.Column('data_source', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['station_id'], ['monitoring_stations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_piezometric_heads_station_id',
                    'piezometric_heads', ['station_id'])
    op.create_index('ix_piezometric_heads_station_measured',
                    'piezometric_heads', ['station_id', 'measured_at'])

    op.create_table(
        'spatial_analysis_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('simulation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=True),
        sa.Column('vulnerability_level', sa.String(length=20), nullable=True),
        sa.Column('affected_area_km2', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id']),
        sa.ForeignKeyConstraint(['simulation_id'], ['simulations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('simulation_id', 'aquifer_id',
                            name='uq_spatial_result_sim_aquifer'),
    )
    op.create_index('ix_spatial_results_simulation_id',
                    'spatial_analysis_results', ['simulation_id'])
