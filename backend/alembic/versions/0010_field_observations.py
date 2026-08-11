"""Field-observation submissions with an approve/reject workflow.

WHY A STAGING TABLE AND NOT A STATUS COLUMN. The requirement is that a field
officer's change must not touch the authoritative dataset or reach the
excursion/ML calculations until it is approved. Two designs were possible:

  (a) add `status` to `water_samples` etc. and filter it out everywhere;
  (b) hold proposals in a SEPARATE table and write to the authoritative one only
      on approval.

(a) fails open: the guarantee then depends on every present and future query
remembering `WHERE status = 'approved'`, and the first one that forgets silently
feeds unreviewed field data into a contamination calculation. (b) fails closed —
a pending proposal is not in `water_samples` at all, so no query can see it by
accident, including queries nobody has written yet.

This migration therefore adds:

  field_observations   the proposal queue. Carries the FULL previous and
                       proposed payloads, so the audit trail can show old vs new
                       without reconstructing anything.
  ore_observations     an authoritative home for field-discovered uranium ore
                       presence. Deliberately NOT the reference ore dataset in
                       `Datasets/` — that is GSI/mine-record provenance, and
                       field sightings must not be mixed into it.

SEPARATION OF DUTIES IS ENFORCED IN THE SCHEMA, not only in the service:
`ck_field_obs_no_self_review` makes a row where `reviewed_by = submitted_by`
unrepresentable. A service bug, a bad migration, or someone with psql cannot
approve their own submission.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision = '0010_field_observations'
down_revision = '0009_isr_owner_org_and_rls'
branch_labels = None
depends_on = None

_STAFF = "('admin','regulator','analyst','field_officer')"
_REVIEWERS = "('admin','regulator')"


def upgrade() -> None:
    # ── authoritative: field-discovered ore presence ─────────────────
    op.create_table(
        'ore_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('location', geoalchemy2.Geography(
            geometry_type='POINT', srid=4326), nullable=False),
        sa.Column('ore_zone', sa.String(length=16), nullable=False),
        sa.Column('uranium_grade_pct', sa.Float(), nullable=True),
        sa.Column('depth_m', sa.Float(), nullable=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        # Every authoritative row records the submission that produced it, so a
        # value on the map can always be traced to who saw it and who approved it.
        sa.Column('origin_observation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.CheckConstraint("ore_zone IN ('deposit','belt','none')",
                           name='ck_ore_observations_zone'),
        sa.CheckConstraint(
            "uranium_grade_pct IS NULL OR "
            "(uranium_grade_pct >= 0 AND uranium_grade_pct <= 100)",
            name='ck_ore_observations_grade'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ore_observations_location', 'ore_observations',
                    ['location'], postgresql_using='gist')

    # ── the proposal queue ───────────────────────────────────────────
    op.create_table(
        'field_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('observation_type', sa.String(length=32), nullable=False),
        sa.Column('operation', sa.String(length=8), nullable=False),
        sa.Column('target_table', sa.String(length=64), nullable=False),
        # NULL for a create; set for update/delete.
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),
        # NULL for a delete; the values to write otherwise.
        sa.Column('proposed', postgresql.JSONB(), nullable=True),
        # Snapshot of the target row AS IT WAS when the proposal was made. This
        # is the "old" half of the old/new record, and the basis of the staleness
        # check at approval time.
        sa.Column('previous', postgresql.JSONB(), nullable=True),
        # Digest of `previous`. If the authoritative row has moved on since the
        # proposal was written, approving would silently clobber someone else's
        # edit, so approval refuses instead.
        sa.Column('target_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('location', geoalchemy2.Geography(
            geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False,
                  server_default='pending'),
        sa.Column('submitted_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        # The authoritative row this became. NULL until approved.
        sa.Column('applied_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('now()')),

        sa.CheckConstraint(
            "observation_type IN ('water_sample','groundwater_level','ore_presence')",
            name='ck_field_obs_type'),
        sa.CheckConstraint("operation IN ('create','update','delete')",
                           name='ck_field_obs_operation'),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','withdrawn')",
            name='ck_field_obs_status'),
        # SEPARATION OF DUTIES, at the database. A reviewer may not be the
        # submitter -- unrepresentable, not merely rejected by the service.
        sa.CheckConstraint("reviewed_by IS NULL OR reviewed_by <> submitted_by",
                           name='ck_field_obs_no_self_review'),
        # A decided proposal must record who decided it and when.
        sa.CheckConstraint(
            "(status IN ('pending','withdrawn')) "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name='ck_field_obs_decided_has_reviewer'),
        # An update or delete must name its target; a create must not.
        sa.CheckConstraint(
            "(operation = 'create' AND target_id IS NULL) "
            "OR (operation IN ('update','delete') AND target_id IS NOT NULL)",
            name='ck_field_obs_target_matches_operation'),
        # Only an approved proposal may point at an applied row.
        sa.CheckConstraint("applied_id IS NULL OR status = 'approved'",
                           name='ck_field_obs_applied_only_when_approved'),

        sa.ForeignKeyConstraint(['submitted_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_field_obs_status', 'field_observations', ['status'])
    op.create_index('ix_field_obs_submitter', 'field_observations', ['submitted_by'])
    op.create_index('ix_field_obs_target', 'field_observations',
                    ['target_table', 'target_id'])
    op.create_index('ix_field_obs_location', 'field_observations',
                    ['location'], postgresql_using='gist')

    # ── RLS ──────────────────────────────────────────────────────────
    for table in ('field_observations', 'ore_observations'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

    # Staff read the queue; a field officer sees only what they submitted, so one
    # officer cannot browse another's unreviewed observations.
    op.execute(f"""
        CREATE POLICY field_obs_read ON field_observations FOR SELECT
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
                 IN ('admin','regulator','analyst')
            OR (
                coalesce(current_setting('app.current_role', true), '') = 'field_officer'
                AND submitted_by::text = coalesce(current_setting('app.current_user_id', true), '')
            )
        );
    """)
    # Writes go through the service, which runs with the caller's context.
    op.execute(f"""
        CREATE POLICY field_obs_write ON field_observations FOR ALL
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '') IN {_REVIEWERS}
            OR (
                coalesce(current_setting('app.current_role', true), '') = 'field_officer'
                AND submitted_by::text = coalesce(current_setting('app.current_user_id', true), '')
            )
        )
        WITH CHECK (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '') IN {_REVIEWERS}
            OR (
                coalesce(current_setting('app.current_role', true), '') = 'field_officer'
                AND submitted_by::text = coalesce(current_setting('app.current_user_id', true), '')
            )
        );
    """)

    op.execute(f"""
        CREATE POLICY ore_obs_read ON ore_observations FOR SELECT
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '') IN {_STAFF}
        );
    """)
    # Only the approval path writes here, and it runs with the system bypass.
    # No role writes this table directly -- not even admin, through the API.
    op.execute("""
        CREATE POLICY ore_obs_write ON ore_observations FOR ALL
        USING (coalesce(current_setting('app.bypass_rls', true), 'off') = 'on')
        WITH CHECK (coalesce(current_setting('app.bypass_rls', true), 'off') = 'on');
    """)


def downgrade() -> None:
    for policy, table in (('field_obs_read', 'field_observations'),
                          ('field_obs_write', 'field_observations'),
                          ('ore_obs_read', 'ore_observations'),
                          ('ore_obs_write', 'ore_observations')):
        op.execute(f'DROP POLICY IF EXISTS {policy} ON {table}')
    op.drop_table('field_observations')
    op.drop_index('ix_ore_observations_location', table_name='ore_observations')
    op.drop_table('ore_observations')
