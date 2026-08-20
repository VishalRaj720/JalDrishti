"""A second kind of alert: the pathway into the shallow aquifer.

A published screening currently alerts the blocks the plume's HORIZONTAL
footprint intersects — typically a few hectares inside one block. That is the
right claim about the plume, and it is not the only thing a resident needs to
hear. Where the vertical screening says lixiviant could reach the shallow
drinking-water aquifer, the water that carries it moves on, and the people who
draw from that aquifer down-gradient are not inside the footprint.

Two things this must NOT become:

  * A second alert saying the same thing to the same people. The unique index
    now keys on `kind` as well, so a block can hold at most one of each rather
    than two copies of one.
  * A licence to alert an entire aquifer formation. The Basement Gneissic
    Complex alone covers 48,047 km² — over half of Jharkhand — so "every block
    touching the aquifer" would turn one hypothetical 13-hectare plume into a
    statewide warning. The reach is bounded in the service by advective travel
    distance over the run's own horizon; see `AlertService.announce_aquifer_reach`.

Revision ID: 0021_aquifer_pathway
Revises: 0020_ore_radius
"""
from alembic import op

revision = "0021_aquifer_pathway"
down_revision = "0020_ore_radius"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance', 'published_screening',
                        'aquifer_pathway'))
    """)
    # Was UNIQUE (advisory_id, block_id) WHERE advisory_id IS NOT NULL, which
    # would have let the footprint alert silently swallow the aquifer one via
    # the existing ON CONFLICT DO NOTHING — no error, no alert, no way to tell.
    op.execute("DROP INDEX IF EXISTS uq_alert_screening")
    op.execute("""
        CREATE UNIQUE INDEX uq_alert_screening
        ON alerts (advisory_id, block_id, kind)
        WHERE advisory_id IS NOT NULL
    """)


def downgrade() -> None:
    # Rows of the new kind must go before the old constraint can hold again.
    op.execute("DELETE FROM alerts WHERE kind = 'aquifer_pathway'")
    op.execute("DROP INDEX IF EXISTS uq_alert_screening")
    op.execute("""
        CREATE UNIQUE INDEX uq_alert_screening
        ON alerts (advisory_id, block_id)
        WHERE advisory_id IS NOT NULL
    """)
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance', 'published_screening'))
    """)
