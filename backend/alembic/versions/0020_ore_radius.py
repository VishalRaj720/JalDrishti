"""Record the observed extent of an ore sighting.

The sync drew a fixed 400 m circle around every approved ore observation. That
number was the system's invention, applied identically to a roadside outcrop and
to a mapped lens, and it decides real behaviour: the circle becomes the deposit
polygon, and `ore_zone_at()` uses it to decide whether a uranium plume is
possible at a pin.

Whoever stood at the outcrop knows roughly how far the ore they saw extends.
Asking them is better than assuming, and a stated radius is a claim someone can
be held to — an invented one is not.

Nullable, with the previous 400 m as the documented fallback, so every existing
row keeps exactly the geometry it already had.

Revision ID: 0020_ore_radius
Revises: 0019_retire_regulator
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_ore_radius"
down_revision = "0019_retire_regulator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ore_observations",
        sa.Column("radius_m", sa.Float(), nullable=True,
                  comment="Observed extent in metres, as reported. NULL means "
                          "the submitter did not state one and the sync falls "
                          "back to 400 m."),
    )
    # A sighting with a 50 km radius is a data-entry slip, not an observation.
    # The upper bound is generous — the largest deposit outline in the shipped
    # file is well under 5 km across — but it stops a stray keystroke redrawing
    # the ore map.
    op.create_check_constraint(
        "ck_ore_obs_radius_sane",
        "ore_observations",
        "radius_m IS NULL OR (radius_m > 0 AND radius_m <= 20000)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ore_obs_radius_sane", "ore_observations",
                       type_="check")
    op.drop_column("ore_observations", "radius_m")
