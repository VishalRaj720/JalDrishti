"""Drop monitoring_data table (replaced by groundwater_level_readings on monitoring_stations)."""
from alembic import op

revision = '0003_drop_monitoring_data'
down_revision = '0002_add_monitoring_stations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index('ix_monitoring_data_aquifer_id', table_name='monitoring_data', if_exists=True)
    op.drop_index('ix_monitoring_data_timestamp', table_name='monitoring_data', if_exists=True)
    op.drop_table('monitoring_data')


def downgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql
    op.create_table(
        'monitoring_data',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('uranium_conc', sa.Float(), nullable=True),
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('ec', sa.Float(), nullable=True),
        sa.Column('eh', sa.Float(), nullable=True),
        sa.Column('major_ions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('hydraulic_head', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
