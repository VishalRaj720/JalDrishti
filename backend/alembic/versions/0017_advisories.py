"""Public screening advisories, and the regulator gate in front of them.

P4. Until now nothing an analyst produced could reach a resident. A screening
was run, read by whoever ran it, and stopped there — which is the gap the
proposal's "decision-support tool for mine operators, regulators and local
communities" names and the portal did not fill.

THE THREE DESIGN DECISIONS THIS TABLE ENCODES.

**1. Publication is a regulator act, not an analyst act.** An analyst registers
sites and runs screenings; that is investigation. Turning one into something
residents of a named block are told about is a decision with consequences an
analyst is not positioned to own — land value, alarm, and the standing of the
institution publishing it. So an advisory is *proposed* by whoever ran the
screening and *published* by a regulator or admin, and the two actors are
recorded separately. `ck_advisory_published_has_a_decider` refuses a published
row that cannot name who published it.

**2. An advisory is a SCREENING, never a report of an operation.** No ISR
uranium mine operates in Jharkhand. The public-facing wording therefore says
that an assessment has been published for an area — not that contamination has
occurred. `headline` and `what_it_means` are stored rather than generated at
read time so that what a regulator approved is exactly what a citizen sees; a
template changed later must not silently rewrite an advisory somebody signed.

**3. The affected area is REAL geometry, and it is usually small.** This is the
one place a genuine spatial question is asked of model output — *which blocks
does this footprint actually reach* — so unlike `simulation_runs.plume` (JSONB,
because it is display output) `footprint` is PostGIS and gets a GiST index.

That distinction matters more than it looks. A verified run in the Singhbhum
belt produces ~12.9 ha. An administrative block is four orders of magnitude
larger. Alerting a whole block for a 12.9 ha footprint would be exactly the
over-claiming §4.5 forbids, so `affected_blocks` is computed by real
intersection at publication time and is frequently **just the host block, or
empty beyond it**. That is a finding to report, not a number to inflate — there
is no village or settlement layer in `Datasets/`, so block is the finest
honest resolution available.

`footprint` is nullable: a run outside an ore zone correctly produces no extent,
and an advisory may still be worth publishing to say so.

Revision ID: 0017_advisories
Revises: 0016_sim_run_plume
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision = '0017_advisories'
down_revision = '0016_sim_run_plume'
branch_labels = None
depends_on = None

#: Kept identical to migration 0009's `_STAFF`. `tests/test_rls.py` pins the
#: list against `app.dependencies.STAFF_ROLES` so schema and code cannot drift.
_STAFF = "('admin','regulator','analyst','field_officer')"


def upgrade() -> None:
    op.create_table(
        "advisories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("isr_point_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("isr_points.id", ondelete="CASCADE"), nullable=False),
        # The exact run being published. An advisory that cannot name the run
        # behind it is an opinion; this one can be re-derived from the run's
        # model card, artifact bundle and code version.
        sa.Column("run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("simulation_runs.id", ondelete="RESTRICT"),
                  nullable=False),

        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),

        # Plain-language content, stored as approved rather than templated at
        # read time — see the module docstring.
        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("what_it_means", sa.Text(), nullable=False),
        sa.Column("what_to_do", sa.Text(), nullable=True),

        sa.Column("species", sa.String(32), nullable=False),
        sa.Column("time_years", sa.Float(), nullable=True),
        sa.Column("restoration_years", sa.Float(), nullable=True),

        # Real geometry, for a real spatial question (decision 3 above).
        sa.Column("footprint",
                  Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True),
        sa.Column("footprint_ha", sa.Float(), nullable=True),
        sa.Column("affected_blocks", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True,
                  comment="Blocks the footprint actually intersects, resolved at "
                          "publication. Often only the host block — reported, "
                          "never inflated to the surrounding area."),

        sa.Column("proposed_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("proposed_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint("status IN ('proposed','published','withdrawn','rejected')",
                           name="ck_advisory_status"),
        # A published advisory must be able to name who published it and when.
        # Publication is the act this table exists to make accountable, so an
        # unattributable one is refused by the database, not just by the service.
        sa.CheckConstraint(
            "status <> 'published' OR (decided_by IS NOT NULL "
            "AND published_at IS NOT NULL)",
            name="ck_advisory_published_has_a_decider"),
        sa.CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_advisory_withdrawn_has_a_time"),
    )

    op.create_index("ix_advisories_status", "advisories", ["status"])
    op.create_index("ix_advisories_isr_point", "advisories", ["isr_point_id"])
    op.create_index("ix_advisories_footprint", "advisories", ["footprint"],
                    postgresql_using="gist")

    # ── row-level security ───────────────────────────────────────────
    # The reason RLS is here and not only in the service: this is the first
    # table whose rows are readable by CITIZENS, and the difference between a
    # proposed and a published advisory is the difference between an internal
    # draft and a public statement about someone's drinking water. A service
    # bug that leaked a draft would publish an unapproved claim, so the
    # constraint belongs where a service bug cannot reach it.
    op.execute("ALTER TABLE advisories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE advisories FORCE ROW LEVEL SECURITY")

    # Setting names and the coalesce form match migration 0009 exactly. They are
    # `app.current_role` / `app.bypass_rls`, and the coalesce matters: an unset
    # GUC makes the whole predicate NULL rather than false, which is not the
    # same thing and does not fail closed the way it looks like it does.
    op.execute(f"""
        CREATE POLICY advisories_read ON advisories FOR SELECT
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '') IN {_STAFF}
            OR status = 'published'
        )
    """)
    # Proposing is for the roles that may run the model at all. The service
    # narrows publish and withdraw further to regulator and admin — the database
    # enforces the floor, the service enforces the ceiling.
    op.execute("""
        CREATE POLICY advisories_write ON advisories FOR INSERT
        WITH CHECK (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
               IN ('admin','regulator','analyst')
        )
    """)
    op.execute("""
        CREATE POLICY advisories_update ON advisories FOR UPDATE
        USING (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
               IN ('admin','regulator')
        )
        WITH CHECK (
            coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
            OR coalesce(current_setting('app.current_role', true), '')
               IN ('admin','regulator')
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS advisories_update ON advisories")
    op.execute("DROP POLICY IF EXISTS advisories_write ON advisories")
    op.execute("DROP POLICY IF EXISTS advisories_read ON advisories")
    op.drop_index("ix_advisories_footprint", table_name="advisories")
    op.drop_index("ix_advisories_isr_point", table_name="advisories")
    op.drop_index("ix_advisories_status", table_name="advisories")
    op.drop_table("advisories")
