"""drop the two simulation tables nothing ever read or wrote

Revision ID: 0024_drop_vestigial_sim
Revises: 0023_breach_due_alert

Deployment audit, 2026-08-25. `simulation_aquifers` and `plume_parameters` were
created by `0001_initial` and never touched again. A repo-wide search for either
name -- Python, TypeScript, SQL, raw `text()` queries, the portal -- returns only
their own definition in `app/models/simulation.py`, their CREATE in `0001`, and
their DROP in `0001.downgrade`. No route reads them, no service writes them, no
RLS policy constrains them, and the two ORM relationships that named them
(`Simulation.impacted_aquifers`, `Simulation.plume_parameters`) were themselves
never referenced.

They are not the same thing as `simulations`, which IS live -- `/api/v1/ml/*` and
`/api/v1/simulations/*` both use it. Only the junction table and the optional
physics side-table go.

WHY THIS MATTERS BEYOND TIDINESS. `plume_parameters` holds four columns --
dispersivity_longitudinal, dispersivity_transverse, retardation_factor,
decay_constant -- with the same names as real parameters the engine solves with.
The engine gets those from `ml_pipeline/parameters.py`, which carries provenance
for each. An empty table with authoritative-looking column names is an invitation
to write a query against it later and get NULLs that read as zeros. Better gone.

Reversible: downgrade recreates both exactly as `0001` had them.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0024_drop_vestigial_sim"
down_revision = "0023_breach_due_alert"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # plume_parameters first: it has an FK to simulations, and dropping the
    # junction table first would leave the order dependent on nothing.
    op.drop_table("plume_parameters")
    op.drop_table("simulation_aquifers")


def downgrade() -> None:
    op.create_table(
        "simulation_aquifers",
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("aquifer_id", UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_id"], ["simulations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["aquifer_id"], ["aquifers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("simulation_id", "aquifer_id"),
    )
    op.create_table(
        "plume_parameters",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dispersivity_longitudinal", sa.Float(), nullable=True),
        sa.Column("dispersivity_transverse", sa.Float(), nullable=True),
        sa.Column("retardation_factor", sa.Float(), nullable=True),
        sa.Column("decay_constant", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["simulation_id"], ["simulations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("simulation_id"),
    )
