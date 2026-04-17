"""Month 3 schema: data_sources, monitoring_wells, water_samples,
contamination_events, spatial_analysis_results, piezometric_heads.
Adds *_source columns to aquifers.
"""
from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

revision = '0004_month3_schema'
down_revision = '0003_drop_monitoring_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- aquifers: provenance columns ----------
    op.add_column('aquifers', sa.Column('porosity_source', sa.String(20), nullable=True))
    op.add_column('aquifers', sa.Column('hydraulic_conductivity_source', sa.String(20), nullable=True))
    op.add_column('aquifers', sa.Column('transmissivity_source', sa.String(20), nullable=True))

    # ---------- data_sources ----------
    op.create_table(
        'data_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False,
                  comment='geojson_district | geojson_subdistrict | geojson_aquifer | json_gw_level | csv_water_quality'),
        sa.Column('file_name', sa.String(512), nullable=True),
        sa.Column('checksum', sa.String(64), nullable=True, comment='sha256 of source bytes'),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('loaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'checksum', name='uq_data_sources_name_checksum'),
    )
    op.create_index('ix_data_sources_source_type', 'data_sources', ['source_type'])

    # ---------- monitoring_wells ----------
    op.create_table(
        'monitoring_wells',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('block_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('depth', sa.Float(), nullable=True, comment='Well depth in metres'),
        sa.Column('well_type', sa.String(50), nullable=True, comment='e.g. dug, bore, tube'),
        sa.Column('paired_station_id', postgresql.UUID(as_uuid=True), nullable=True,
                  comment='Optional link to a monitoring_stations record if this well co-locates with a GW-level station'),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['blocks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['paired_station_id'], ['monitoring_stations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('latitude', 'longitude', name='uq_monitoring_wells_lat_lon'),
    )
    op.create_index('ix_monitoring_wells_name', 'monitoring_wells', ['name'])
    op.create_index('ix_monitoring_wells_block_id', 'monitoring_wells', ['block_id'])
    op.create_index('ix_monitoring_wells_location', 'monitoring_wells', ['location'], postgresql_using='gist')

    # ---------- water_samples ----------
    op.create_table(
        'water_samples',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('well_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sampled_at', sa.DateTime(timezone=True), nullable=False),

        # Physical
        sa.Column('ph', sa.Float(), nullable=True),
        sa.Column('ec_us_cm', sa.Float(), nullable=True, comment='Electrical conductivity, µS/cm'),
        sa.Column('tds_mg_l', sa.Float(), nullable=True),
        sa.Column('tds_derived', sa.Boolean(), nullable=False, server_default=sa.text('false'),
                  comment='True when tds_mg_l was computed from EC (0.65 * EC)'),
        sa.Column('turbidity_ntu', sa.Float(), nullable=True),
        sa.Column('do_mg_l', sa.Float(), nullable=True, comment='Dissolved oxygen'),
        sa.Column('total_hardness', sa.Float(), nullable=True),

        # Chemistry
        sa.Column('uranium_ppb', sa.Float(), nullable=True),
        sa.Column('nitrate_mg_l', sa.Float(), nullable=True),
        sa.Column('fluoride_mg_l', sa.Float(), nullable=True),
        sa.Column('arsenic_ppb', sa.Float(), nullable=True),
        sa.Column('iron_ppm', sa.Float(), nullable=True),
        sa.Column('chloride_mg_l', sa.Float(), nullable=True),
        sa.Column('sulphate_mg_l', sa.Float(), nullable=True),
        sa.Column('bicarbonate_mg_l', sa.Float(), nullable=True),
        sa.Column('carbonate_mg_l', sa.Float(), nullable=True),
        sa.Column('phosphate_mg_l', sa.Float(), nullable=True),
        sa.Column('calcium_mg_l', sa.Float(), nullable=True),
        sa.Column('magnesium_mg_l', sa.Float(), nullable=True),
        sa.Column('sodium_mg_l', sa.Float(), nullable=True),
        sa.Column('potassium_mg_l', sa.Float(), nullable=True),

        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['well_id'], ['monitoring_wells.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_water_samples_well_id', 'water_samples', ['well_id'])
    op.create_index('ix_water_samples_sampled_at', 'water_samples', ['sampled_at'])
    op.create_index('ix_water_samples_well_sampled', 'water_samples', ['well_id', 'sampled_at'])

    # ---------- contamination_events ----------
    op.create_table(
        'contamination_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('isr_point_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('contaminant', sa.String(50), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('threshold', sa.Float(), nullable=False),
        sa.Column('exceeded', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['isr_point_id'], ['isr_points.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contamination_events_isr_point_id', 'contamination_events', ['isr_point_id'])
    op.create_index('ix_contamination_events_detected_at', 'contamination_events', ['detected_at'])

    # ---------- spatial_analysis_results ----------
    op.create_table(
        'spatial_analysis_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('simulation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aquifer_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=True),
        sa.Column('vulnerability_level', sa.String(20), nullable=True),
        sa.Column('affected_area_km2', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['simulation_id'], ['simulations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['aquifer_id'], ['aquifers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('simulation_id', 'aquifer_id', name='uq_spatial_result_sim_aquifer'),
    )
    op.create_index('ix_spatial_results_simulation_id', 'spatial_analysis_results', ['simulation_id'])

    # ---------- piezometric_heads ----------
    op.create_table(
        'piezometric_heads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('station_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('measured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('head_value_m', sa.Float(), nullable=False, comment='Piezometric head in metres (elevation datum)'),
        sa.Column('data_source', sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(['station_id'], ['monitoring_stations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_piezometric_heads_station_id', 'piezometric_heads', ['station_id'])
    op.create_index('ix_piezometric_heads_station_measured', 'piezometric_heads', ['station_id', 'measured_at'])


def downgrade() -> None:
    op.drop_index('ix_piezometric_heads_station_measured', table_name='piezometric_heads')
    op.drop_index('ix_piezometric_heads_station_id', table_name='piezometric_heads')
    op.drop_table('piezometric_heads')

    op.drop_index('ix_spatial_results_simulation_id', table_name='spatial_analysis_results')
    op.drop_table('spatial_analysis_results')

    op.drop_index('ix_contamination_events_detected_at', table_name='contamination_events')
    op.drop_index('ix_contamination_events_isr_point_id', table_name='contamination_events')
    op.drop_table('contamination_events')

    op.drop_index('ix_water_samples_well_sampled', table_name='water_samples')
    op.drop_index('ix_water_samples_sampled_at', table_name='water_samples')
    op.drop_index('ix_water_samples_well_id', table_name='water_samples')
    op.drop_table('water_samples')

    op.drop_index('ix_monitoring_wells_location', table_name='monitoring_wells')
    op.drop_index('ix_monitoring_wells_block_id', table_name='monitoring_wells')
    op.drop_index('ix_monitoring_wells_name', table_name='monitoring_wells')
    op.drop_table('monitoring_wells')

    op.drop_index('ix_data_sources_source_type', table_name='data_sources')
    op.drop_table('data_sources')

    op.drop_column('aquifers', 'transmissivity_source')
    op.drop_column('aquifers', 'hydraulic_conductivity_source')
    op.drop_column('aquifers', 'porosity_source')
