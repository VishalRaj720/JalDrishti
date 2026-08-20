"""Stored runs carry their plume geometry.

P2. A completed run recorded metrics, excursion state and hydrogeology — but
not one coordinate of the plume itself. The consequence was structural rather
than cosmetic: the Simulation Studio, the AUDITABLE path, could only render
three numbers and a table, while the Map Console's explicitly *unpersisted*
live run drew contours, the leach zone, the compliance ring and the ML
envelope. The product's best evidence lived on its throwaway route.

Rendering it required inventing geometry client-side or re-running the engine,
and re-running is not the same thing: the artifacts, the code version or the
`Datasets/` sync state may all have moved since. A run that cannot be redrawn
exactly as it was is not reproducible in the sense the provenance columns
promise.

So the geometry is stored with the run, as JSONB:

    plume = {
      "contours":        [{level, polygon:[[lat,lon],…], label}],
      "compliance_ring": {radius_m, polygon},
      "source_zone":     {polygon, radius_m, area_ha, conc, threshold, …},
      "ml_envelope":     {p10|p50|p90: polygon} | null,
      "azimuth_deg":     float,
      "azimuth_source":  str,
      "peak_conc": float, "Xc_m": float, "aspect_ratio": float,
      "radial_dominated": bool
    }

JSONB and not PostGIS geometry, deliberately. These are *model output* in a
local down-gradient frame projected to lat/lon for display — not surveyed
features. Storing them as `geometry` would invite spatial joins against
districts and wells as though they were measured extents, which is exactly the
over-claiming §4.5 forbids. The one place a real spatial question is asked of a
plume — which blocks a published advisory covers — builds its geometry
explicitly at publication time (migration 0017).

NULL is meaningful and permitted: runs completed before this migration have no
geometry and never will. The API reports `plume: null` and the client says the
run predates geometry capture rather than drawing an empty map.

Revision ID: 0016_sim_run_plume
Revises: 0015_isr_operating_parameters
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0016_sim_run_plume'
down_revision = '0015_isr_operating_parameters'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "simulation_runs",
        sa.Column("plume", postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  comment="Model-output plume geometry for redraw; NULL for runs "
                          "completed before P2. Not PostGIS: this is model output "
                          "in a display projection, not a surveyed feature."),
    )


def downgrade() -> None:
    op.drop_column("simulation_runs", "plume")
