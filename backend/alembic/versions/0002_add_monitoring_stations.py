"""Add monitoring_stations and groundwater_level_readings tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_add_monitoring_stations'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # monitoring_stations
    op.create_table(
        'monitoring_stations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('block_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('village', sa.String(255), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('well_depth', sa.Float(), nullable=True, comment='Depth of the well in metres'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_monitoring_stations_name', 'monitoring_stations', ['name'])
    op.create_index('ix_monitoring_stations_block_id', 'monitoring_stations', ['block_id'])

    # groundwater_level_readings
    op.create_table(
        'groundwater_level_readings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'recorded_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Timestamp of the observation',
        ),
        sa.Column(
            'groundwater_level',
            sa.Float(),
            nullable=False,
            comment='Groundwater level in metres below ground level (mbgl)',
        ),
        sa.ForeignKeyConstraint(['station_id'], ['monitoring_stations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gwl_readings_recorded_at', 'groundwater_level_readings', ['recorded_at'])
    op.create_index('ix_gwl_readings_station_id', 'groundwater_level_readings', ['station_id'])
    op.create_index(
        'ix_gwl_readings_station_recorded',
        'groundwater_level_readings',
        ['station_id', 'recorded_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_gwl_readings_station_recorded', table_name='groundwater_level_readings')
    op.drop_index('ix_gwl_readings_station_id', table_name='groundwater_level_readings')
    op.drop_index('ix_gwl_readings_recorded_at', table_name='groundwater_level_readings')
    op.drop_table('groundwater_level_readings')

    op.drop_index('ix_monitoring_stations_block_id', table_name='monitoring_stations')
    op.drop_index('ix_monitoring_stations_name', table_name='monitoring_stations')
    op.drop_table('monitoring_stations')
