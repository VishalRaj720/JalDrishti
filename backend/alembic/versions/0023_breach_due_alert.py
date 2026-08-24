"""aquifer_breach_due alert kind

Revision ID: 0023_breach_due_alert
Revises: 0022_regulator_single_admin

R14 (2026-08-25). A fourth kind of alert, and the first one that is about
ELAPSED TIME rather than about a decision somebody just made.

The other three fire on an event: a sample was analysed, an advisory was
published, a formation was found to be shared. This one fires because a clock
ran out — a published screening said the modelled plume would reach the shallow
aquifer in N years, the hypothetical operation's injection start date is now
more than N years ago, and so the milestone the screening described has, on the
model's own terms, been passed.

WHY THIS IS THE MOST DANGEROUS ALERT IN THE SYSTEM, and what bounds it.
No ISR mine operates in Jharkhand. There is no injection, no plume, and nothing
is breaching anything. An alert that says "the aquifer is now at risk" would be
read as a report of a present-day event, which is exactly wrong. So the copy
this kind carries is written in the conditional throughout, it names the
hypothetical start date it counted from, and `alerts.py` refuses to raise it at
all unless the run actually recorded a vertical screening — absence of that
record means "not assessed", never "no pathway" (LIMITATIONS.md 4b).
"""
from alembic import op

revision = "0023_breach_due_alert"
down_revision = "0022_regulator_single_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance','published_screening',
                        'aquifer_pathway','aquifer_breach_due'))
    """)
    # `uq_alert_screening` is keyed on (advisory_id, block_id, kind) and already
    # covers this kind, so re-running the scan cannot double-alert a block.
    # No new index is needed — which is the point of having put `kind` in that
    # key in migration 0021.


def downgrade() -> None:
    op.execute("DELETE FROM alerts WHERE kind = 'aquifer_breach_due'")
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alert_kind")
    op.execute("""
        ALTER TABLE alerts ADD CONSTRAINT ck_alert_kind
        CHECK (kind IN ('measured_exceedance','published_screening',
                        'aquifer_pathway'))
    """)
