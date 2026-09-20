"""alert tiers, basis and the structured explanation

Revision ID: 0026_alert_tiers_explanation
Revises: 0025_home_block_alert_delivery

R17 (2026-09-20). An alert becomes an auditable decision record.

Until now an alert carried a headline, a body of prose and a three-valued
`severity`. The prose answered a reader's questions -- what happened, which
substance, where, how bad, measured or modelled, how sure, what next -- only in
sentences, and only where the author had remembered to. Three things change:

1. **`tier`** -- `notice | warning | alert | critical`, the ladder built on
   IS 10500:2012's own two limits (acceptable / permissible, "no relaxation")
   with one project-defined rung: `critical` at >= 2x the alert limit or two
   or more health determinands over their limit at one well. The rule text is
   stored with every row (`explanation.tier.rule`), so a reader can disagree
   with a number they can see. `severity` is kept and derived from the tier
   so nothing that reads it breaks.

2. **`basis`** -- `observed | modelled`. This was implicit in `kind`; it is now
   a column with a CHECK that a modelled alert can never be `critical`. No ISR
   mine exists and nothing has been measured, so the database refuses the row
   if code ever tries.

3. **`explanation`** -- JSONB with the seven fields (`what_happened`, `driver`,
   `where`, `tier`, `basis`, `confidence`, `next_action`). For modelled alerts
   `confidence` carries the run's P10/P50/P90 band, its extrapolation flags and
   its data-confidence reasons; for observed ones the sample date and the fact
   that it is a single sample.

A fifth kind, **`possible_reach`**, tells a block that lies inside the model's
upper (P90) migration envelope but outside its central footprint. It is
tiered `warning` and worded as the width of the band, never as a finding.

BACKFILL. Existing rows get `basis` from `kind` and `tier` from `severity`
(`info -> notice`, `warning -> warning`, `high -> alert`); `explanation` stays
NULL until the scan or `POST /citizen/alerts/rebuild` regenerates it -- the
measured scan upserts the structured fields onto rows that lack them without
creating duplicates. A backfilled measured `high` is tiered `alert`, not
`critical`, because the row does not record whether it was one determinand at
2x or two determinands; the rebuild recomputes it from the sample.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026_alert_tiers_explanation"
down_revision = "0025_home_block_alert_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("tier", sa.String(16), nullable=False,
                                      server_default="notice"))
    op.add_column("alerts", sa.Column("basis", sa.String(16), nullable=False,
                                      server_default="modelled"))
    op.add_column("alerts", sa.Column("explanation", postgresql.JSONB(),
                                      nullable=True))

    # backfill from what the rows already say
    op.execute("""
        UPDATE alerts SET
            basis = CASE WHEN kind = 'measured_exceedance' THEN 'observed'
                         ELSE 'modelled' END,
            tier  = CASE severity WHEN 'info' THEN 'notice'
                                  WHEN 'warning' THEN 'warning'
                                  WHEN 'high' THEN 'alert'
                                  ELSE 'notice' END
    """)

    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance','published_screening',
                        'aquifer_pathway','aquifer_breach_due','possible_reach'))
    """)
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_tier
        CHECK (tier IN ('notice','warning','alert','critical'))
    """)
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_basis
        CHECK (basis IN ('observed','modelled'))
    """)
    # a modelled result is never critical: no mine exists, nothing was measured
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_modelled_never_critical
        CHECK (NOT (basis = 'modelled' AND tier = 'critical'))
    """)
    # an observed alert is a measurement; a modelled one names its advisory
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_basis_matches_kind
        CHECK ((kind = 'measured_exceedance') = (basis = 'observed'))
    """)
    op.create_index("ix_alerts_tier", "alerts", ["tier"])


def downgrade() -> None:
    op.drop_index("ix_alerts_tier", table_name="alerts")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_basis_matches_kind")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_modelled_never_critical")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_basis")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_tier")
    op.execute("DELETE FROM alerts WHERE kind = 'possible_reach'")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance','published_screening',
                        'aquifer_pathway','aquifer_breach_due'))
    """)
    op.drop_column("alerts", "explanation")
    op.drop_column("alerts", "basis")
    op.drop_column("alerts", "tier")
