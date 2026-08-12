"""Track whether an approved observation has reached `Datasets/` yet.

THE PROBLEM THIS MAKES VISIBLE. An approved field observation becomes
authoritative in the database immediately, but `ml_pipeline` reads only
`Datasets/` — so between approval and a dataset sync the portal and the engine
disagree, and until now they disagreed *silently*. A map could show an approved
uranium ore sighting while a simulation at that exact point still reported
"non-ore zone, no plume".

That gap is deliberate: the engine's artifacts are frozen and its conformal
coverage was calibrated against a fixed input distribution, so approved data must
not slide into the model on its own (PRODUCT_DESIGN.md §3.4). The fix is not to
close the gap automatically but to **show it**, which needs these two columns:

    synced_to_dataset_at   when the approved change reached Datasets/
    dataset_sync_ref       which sync batch carried it

Together with `status` they give the three states the UI renders:

    pending                          -> red    : awaiting review
    approved, synced_to_dataset_at IS NULL -> amber : approved, not in the model
    approved, synced_to_dataset_at IS NOT NULL -> green : approved and in the model

`ck_field_obs_synced_only_when_approved` keeps the amber/green distinction
meaningful: an unapproved row can never claim to be in a dataset.
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_dataset_sync_state'
down_revision = '0012_simulation_runs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('field_observations',
                  sa.Column('synced_to_dataset_at', sa.DateTime(timezone=True),
                            nullable=True))
    op.add_column('field_observations',
                  sa.Column('dataset_sync_ref', sa.String(length=64), nullable=True))
    op.create_check_constraint(
        'ck_field_obs_synced_only_when_approved', 'field_observations',
        "synced_to_dataset_at IS NULL OR status = 'approved'")
    # The amber query — approved and unsynced — is what the UI polls.
    op.create_index('ix_field_obs_pending_sync', 'field_observations',
                    ['observation_type'],
                    postgresql_where=sa.text(
                        "status = 'approved' AND synced_to_dataset_at IS NULL"))


def downgrade() -> None:
    op.drop_index('ix_field_obs_pending_sync', table_name='field_observations')
    op.drop_constraint('ck_field_obs_synced_only_when_approved',
                       'field_observations', type_='check')
    op.drop_column('field_observations', 'dataset_sync_ref')
    op.drop_column('field_observations', 'synced_to_dataset_at')
