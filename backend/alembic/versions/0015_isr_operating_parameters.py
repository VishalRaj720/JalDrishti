"""ISR points carry the full operating parameter set.

P5. An ISR point was a name and a coordinate: the only engine input it held was
`injection_rate`, and every other parameter was chosen fresh in the Simulation
Studio for each run. That made two things impossible. A site could not be
*specified* — two people running "Jaduguda" were not necessarily running the
same operation — and the Studio could not become a timelapse, because a
timelapse needs everything except time to be fixed.

After this migration a site is a fully described hypothetical operation, and the
Studio varies only evaluation year and restoration years (the one remediation
decision a reviewer needs to test against an otherwise fixed site).

RANGES AND DEFAULTS come from `ml_pipeline.config.parameters` and are enforced
in the Pydantic schema, not here. A CHECK constraint would freeze a bound that
belongs to the engine: `restoration_years` alone has a trained max of 10 and a
deliberately decoupled UI exploration bound of 30, and the engine is entitled to
move either without a database migration.

`injection_rate` is RENAMED rather than replaced, so existing rows keep their
value. `injection_end_date` is DROPPED: with `start_date` and `operation_years`
both present it was a third source of truth for the same fact, and the one most
likely to drift.

Revision ID: 0015_isr_operating_parameters
Revises: 0014_scenarios
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_isr_operating_parameters'
down_revision = '0014_scenarios'
branch_labels = None
depends_on = None


#: (column, type, default) — defaults match the engine's own, so a site
#: registered before this migration behaves exactly as the Studio's old
#: defaults did rather than silently changing what a re-run produces.
_COLUMNS = [
    ("bleed_percent",       sa.Float(), "2.0"),
    ("operation_years",     sa.Float(), "8.0"),
    ("restoration_years",   sa.Float(), "0.0"),
    ("wellfield_width_m",   sa.Float(), "300.0"),
    ("monitor_ring_m",      sa.Float(), "100.0"),
    ("ore_depth_m",         sa.Float(), "150.0"),
    ("ore_thickness_m",     sa.Float(), "20.0"),
]

#: Nullable on purpose — null means "resolve it from the pin", which is a
#: different statement from any number we could store.
_NULLABLE = [
    ("regime_override", sa.String(length=16)),
    ("gradient_i",      sa.Float()),
    ("azimuth_deg",     sa.Float()),
]


def upgrade() -> None:
    # The engine's field is `injection_rate_m3_day`; the column was named for
    # neither the unit nor the engine, so the mapping had to be remembered.
    op.alter_column("isr_points", "injection_rate",
                    new_column_name="injection_rate_m3_day")
    op.execute("UPDATE isr_points SET injection_rate_m3_day = 2500 "
               "WHERE injection_rate_m3_day IS NULL")
    op.alter_column("isr_points", "injection_rate_m3_day",
                    existing_type=sa.Float(), nullable=False,
                    server_default="2500")

    for name, type_, default in _COLUMNS:
        op.add_column("isr_points", sa.Column(
            name, type_, nullable=False, server_default=default))

    for name, type_ in _NULLABLE:
        op.add_column("isr_points", sa.Column(name, type_, nullable=True))

    # `injection_start_date` stays and becomes the engine's `start_date` — the
    # lifecycle anchor that turns an evaluation year into a calendar date. The
    # end date is now derived from it plus `operation_years`.
    op.drop_column("isr_points", "injection_end_date")


def downgrade() -> None:
    op.add_column("isr_points", sa.Column(
        "injection_end_date", sa.DateTime(timezone=True), nullable=True))
    for name, _ in _NULLABLE:
        op.drop_column("isr_points", name)
    for name, _, _d in _COLUMNS:
        op.drop_column("isr_points", name)
    op.alter_column("isr_points", "injection_rate_m3_day",
                    existing_type=sa.Float(), nullable=True, server_default=None)
    op.alter_column("isr_points", "injection_rate_m3_day",
                    new_column_name="injection_rate")
