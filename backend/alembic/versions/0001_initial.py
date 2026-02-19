"""Initial migration: create all tables with PostGIS extension."""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable PostGIS
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis_topology")

    # Enums — drop first (safe: no tables exist yet at this point), then recreate cleanly.
    # DO $$ EXCEPTION approach doesn't work under Alembic's transactional DDL mode.
    op.execute("DROP TYPE IF EXISTS userrole CASCADE")
    op.execute("DROP TYPE IF EXISTS aquifertype CASCADE")
    op.execute("DROP TYPE IF EXISTS mlmodeltype CASCADE")

    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'analyst', 'viewer')")
    op.execute("""
        CREATE TYPE aquifertype AS ENUM (
            'basalt','charnockite','gneiss','limestone','sandstone','alluvium',
            'basement_gneissic_complex','granite','intrusive','laterite','quartzite','schist'
        )
    """)
    op.execute("CREATE TYPE mlmodeltype AS ENUM ('regression','classification','plume_estimation')")

    # users
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', postgresql.ENUM('admin', 'analyst', 'viewer', name='userrole', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('username'),
    )


    op.create_table('districts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('geometry', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326), nullable=True),
        sa.Column('avg_porosity', sa.Float(), nullable=True),
        sa.Column('avg_hydraulic_conductivity', sa.Float(), nullable=True),
        sa.Column('vulnerability_index', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_districts_geometry', 'districts', ['geometry'], postgresql_using='gist')

    # blocks
    op.create_table('blocks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('district_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('geometry', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326), nullable=True),
        sa.Column('aquifer_distribution', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('avg_porosity', sa.Float(), nullable=True),
        sa.Column('avg_permeability', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'district_id', name='uq_block_name_district'),
    )
    op.create_index('ix_blocks_geometry', 'blocks', ['geometry'], postgresql_using='gist')

    # aquifers
    op.create_table('aquifers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('block_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', postgresql.ENUM('basalt', 'charnockite', 'gneiss', 'limestone', 'sandstone', 'alluvium', 'basement_gneissic_complex', 'granite', 'intrusive', 'laterite', 'quartzite', 'schist', name='aquifertype', create_type=False), nullable=False),
        sa.Column('min_depth', sa.Float(), nullable=True),
        sa.Column('max_depth', sa.Float(), nullable=True),
        sa.Column('thickness', sa.Float(), nullable=True),
        sa.Column('geometry', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326), nullable=True),
        sa.Column('porosity', sa.Float(), nullable=True),
        sa.Column('hydraulic_conductivity', sa.Float(), nullable=True),
        sa.Column('transmissivity', sa.Float(), nullable=True),
        sa.Column('storage_coefficient', sa.Float(), nullable=True),
        sa.Column('specific_yield', sa.Float(), nullable=True),
        sa.Column('quality_ec', sa.Float(), nullable=True),
        sa.Column('dtw_decadal_avg', sa.Float(), nullable=True),
        sa.Column('fractures_encountered', sa.String(50), nullable=True),
        sa.Column('yield', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_aquifers_geometry', 'aquifers', ['geometry'], postgresql_using='gist')
    op.create_index('ix_aquifers_block_id', 'aquifers', ['block_id'])


    op.create_table('isr_points',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('injection_rate', sa.Float(), nullable=True),
        sa.Column('injection_start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('injection_end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # simulations
    op.create_table('simulations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('isr_point_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('simulation_date', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('affected_area', sa.Float(), nullable=True),
        sa.Column('estimated_concentration_spread', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('vulnerability_assessment', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('uncertainty_estimate', sa.Float(), nullable=True),
        sa.Column('suggested_recovery', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['isr_point_id'], ['isr_points.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # simulation_aquifers
    op.create_table('simulation_aquifers',
        sa.Column('simulation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['simulation_id'], ['simulations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('simulation_id', 'aquifer_id'),
    )

    # plume_parameters
    op.create_table('plume_parameters',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('simulation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dispersivity_longitudinal', sa.Float(), nullable=True),
        sa.Column('dispersivity_transverse', sa.Float(), nullable=True),
        sa.Column('retardation_factor', sa.Float(), nullable=True),
        sa.Column('decay_constant', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['simulation_id'], ['simulations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('simulation_id'),
    )

    # monitoring_data
    op.create_table('monitoring_data',
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

    # hydraulic_heads
    op.create_table('hydraulic_heads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('head_value', sa.Float(), nullable=False),
        sa.Column('source', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ml_models
    op.create_table('ml_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('type', postgresql.ENUM('regression', 'classification', 'plume_estimation', name='mlmodeltype', create_type=False), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(255), nullable=True),
        sa.Column('feature_schema', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


    # Materialized views for district/block aggregates
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS district_aggregates AS
        SELECT
            d.id AS district_id,
            d.name,
            AVG(a.porosity) AS avg_porosity,
            AVG(a.hydraulic_conductivity) AS avg_hydraulic_conductivity,
            COUNT(DISTINCT a.id) AS aquifer_count
        FROM districts d
        LEFT JOIN blocks b ON b.district_id = d.id
        LEFT JOIN aquifers a ON a.block_id = b.id
        GROUP BY d.id, d.name
        WITH DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX ON district_aggregates (district_id)
    """)

    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS block_aggregates AS
        SELECT
            b.id AS block_id,
            b.name,
            b.district_id,
            AVG(a.porosity) AS avg_porosity,
            AVG(a.hydraulic_conductivity) AS avg_hydraulic_conductivity,
            COUNT(DISTINCT a.id) AS aquifer_count
        FROM blocks b
        LEFT JOIN aquifers a ON a.block_id = b.id
        GROUP BY b.id, b.name, b.district_id
        WITH DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX ON block_aggregates (block_id)
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS block_aggregates")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS district_aggregates")
    op.drop_table('ml_models')
    op.drop_table('hydraulic_heads')
    op.drop_table('monitoring_data')
    op.drop_table('plume_parameters')
    op.drop_table('simulation_aquifers')
    op.drop_table('simulations')
    op.drop_table('isr_points')
    op.drop_table('aquifers')
    op.drop_table('blocks')
    op.drop_table('districts')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS mlmodeltype")
    op.execute("DROP TYPE IF EXISTS aquifertype")
    op.execute("DROP TYPE IF EXISTS userrole")
