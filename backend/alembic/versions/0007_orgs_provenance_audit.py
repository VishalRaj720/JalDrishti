"""P1: organisations, the dataset provenance spine, and the audit log.

PRODUCT_DESIGN.md section 5 / delivery plan P1.

TWO DEVIATIONS FROM THE DESIGN DOCUMENT, both deliberate:

1. `dataset_versions` does NOT absorb what `data_sources` already does.
   The design sketched `dataset_versions` with `sha256` and `row_count`, but
   `data_sources` already carries both, for 419 rows of real load history. Two
   tables owning checksum semantics is the same "two code paths for one entity"
   failure the design rejects in section 3.1, and provenance is the last place
   to accept it.

   The two are kept at the granularities they actually operate on:
     * `data_sources`  -- the LOAD LEDGER. One row per ingested batch, with the
       file checksum. 415 of its current rows are per-station groundwater
       batches (`gw_level:<station>`) that all came from one CSV.
     * `dataset_versions` -- the CITABLE DATASET. One row per logical dataset,
       carrying the things a regulator needs and a checksum cannot express:
       source organisation, citation, supporting sample size, caveat.
   `data_sources.dataset_version_id` links ledger to spine, so a simulation run
   can pin the dataset it used and still reach the individual file loads.

2. The `roles` / `user_roles` / `permissions` tables in the design's schema map
   are NOT created here. `users.role` (the `userrole` enum) is still the only
   thing the auth layer reads, and standing up a parallel, unread role store
   would recreate the exact duplication described above. This migration instead
   EXTENDS the enum with the three new roles so the vocabulary exists; P2 builds
   the gateway that reads them and can migrate `viewer` -> `citizen` together
   with the code that depends on it.

   The enum change is purely additive. `viewer` remains valid and every existing
   user keeps working -- Postgres cannot remove an enum value anyway, so
   pretending otherwise here would strand the running app.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007_orgs_provenance_audit'
down_revision = '0006_drop_orphan_tables'
branch_labels = None
depends_on = None

_NEW_ROLES = ('regulator', 'field_officer', 'citizen')


def upgrade() -> None:
    # ── organisations ────────────────────────────────────────────────
    op.create_table(
        'orgs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.CheckConstraint(
            "kind IN ('regulator','academic','utility','other')",
            name='ck_orgs_kind'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_orgs_code'),
    )

    # ── the citable-dataset provenance spine ─────────────────────────
    op.create_table(
        'dataset_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('label', sa.String(length=128), nullable=False),
        sa.Column('source_org', sa.String(length=64), nullable=False),
        sa.Column('citation', sa.Text(), nullable=False),
        # Sample size behind the dataset, where it is small enough to change how
        # a number should be read. The uranium source term rests on 9
        # measurements from 7 mines; a portal rendering "15,180 ppb" to five
        # significant figures without saying so is misleading by omission.
        sa.Column('n_supporting', sa.Integer(), nullable=True),
        sa.Column('caveat', sa.Text(), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('label', name='uq_dataset_versions_label'),
    )

    # Ledger -> spine. Nullable: a file load without a registered dataset is a
    # gap to report in the data-quality report, not a reason to reject the load.
    op.add_column('data_sources', sa.Column(
        'dataset_version_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_data_sources_dataset_version', 'data_sources',
                          'dataset_versions', ['dataset_version_id'], ['id'],
                          ondelete='SET NULL')
    op.create_index('ix_data_sources_dataset_version', 'data_sources',
                    ['dataset_version_id'])

    # ── users belong to an organisation ──────────────────────────────
    op.add_column('users', sa.Column(
        'org_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_users_org', 'users', 'orgs',
                          ['org_id'], ['id'], ondelete='RESTRICT')
    op.create_index('ix_users_org_id', 'users', ['org_id'])

    # ── audit log ────────────────────────────────────────────────────
    # Append-only by convention here; P2 adds the RLS policy that enforces it.
    # actor_id is nullable and ON DELETE SET NULL: deleting a user must never
    # delete the record of what they did.
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor_label', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.String(length=64), nullable=True),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_occurred_at', 'audit_log', ['occurred_at'])
    op.create_index('ix_audit_log_actor', 'audit_log', ['actor_id'])
    op.create_index('ix_audit_log_entity', 'audit_log',
                    ['entity_type', 'entity_id'])

    # ── role vocabulary (additive only; see module docstring) ────────
    for role in _NEW_ROLES:
        op.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{role}'")


def downgrade() -> None:
    # Postgres cannot remove a value from an enum, so the three added roles are
    # one-way. Any user holding one must be reassigned before downgrading, or
    # the column will reference a label this migration cannot take back.
    op.drop_index('ix_audit_log_entity', table_name='audit_log')
    op.drop_index('ix_audit_log_actor', table_name='audit_log')
    op.drop_index('ix_audit_log_occurred_at', table_name='audit_log')
    op.drop_table('audit_log')

    op.drop_index('ix_users_org_id', table_name='users')
    op.drop_constraint('fk_users_org', 'users', type_='foreignkey')
    op.drop_column('users', 'org_id')

    op.drop_index('ix_data_sources_dataset_version', table_name='data_sources')
    op.drop_constraint('fk_data_sources_dataset_version', 'data_sources',
                       type_='foreignkey')
    op.drop_column('data_sources', 'dataset_version_id')

    op.drop_table('dataset_versions')
    op.drop_table('orgs')
