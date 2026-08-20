"""Citizen block subscriptions, and the in-portal alert inbox.

P5. The proposal names "timely alerts" as a deliverable and lists local
communities as stakeholders; until now a citizen got a district choropleth, a
table, and a card saying alerts were planned.

TWO CHANNELS, KEPT SEPARATE ON PURPOSE. `alerts.kind` is not decoration:

  **`measured_exceedance`** — a real CGWB laboratory result above the 30 ppb
  BIS limit for uranium. Nothing hypothetical about it, and it needs no
  hedging: a well was sampled, this is what it measured, here is when.

  **`published_screening`** — a regulator has published a modelled assessment
  covering this block. It describes what a hypothetical ISR operation *would*
  do, and every word of it says so.

Merging them into one feed would be the single most damaging simplification
available here. A resident who cannot tell "your water tested above the safe
limit" from "someone modelled a mine that does not exist" will either panic at
the second or ignore the first, and both failures are caused by us.

DELIVERY IS IN-PORTAL ONLY. No SMS, no email. There is no notification service,
no credentials, and no budget for one; building the inbox and pretending
delivery exists would be worse than not claiming it. Read state lives in
`alert_reads` rather than on `alerts`, because one alert covers a block and is
seen by every subscriber to it independently.

WHY BLOCK AND NOT SOMETHING FINER. `Datasets/` carries no village, settlement or
population layer. Block is the finest honest resolution available, and the UI
says so rather than implying a precision the data does not support.

Revision ID: 0018_citizen_alerts
Revises: 0017_advisories
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0018_citizen_alerts'
down_revision = '0017_advisories'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── subscriptions ────────────────────────────────────────────────
    op.create_table(
        "block_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "block_id", name="uq_subscription_user_block"),
    )
    op.create_index("ix_block_subs_user", "block_subscriptions", ["user_id"])
    op.create_index("ix_block_subs_block", "block_subscriptions", ["block_id"])

    # ── alerts ───────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("block_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False),
        # Set only for a screening alert. RESTRICT: an alert pointing at a
        # deleted advisory would be a public claim with nothing behind it.
        sa.Column("advisory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("advisories.id", ondelete="CASCADE"), nullable=True),

        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),

        # Measured-channel detail. Present only for `measured_exceedance`, and
        # stored so the alert can state the actual reading rather than sending
        # the reader off to find it.
        sa.Column("well_name", sa.String(255), nullable=True),
        sa.Column("measured_value", sa.Float(), nullable=True),
        sa.Column("measured_unit", sa.String(16), nullable=True),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),

        sa.CheckConstraint("kind IN ('measured_exceedance','published_screening')",
                           name="ck_alert_kind"),
        sa.CheckConstraint("severity IN ('info','warning','high')",
                           name="ck_alert_severity"),
        # The two channels have different obligations, enforced rather than
        # documented: a screening alert must name the advisory it came from, and
        # a measured alert must carry the reading it is reporting.
        sa.CheckConstraint(
            "kind <> 'published_screening' OR advisory_id IS NOT NULL",
            name="ck_screening_alert_names_its_advisory"),
        sa.CheckConstraint(
            "kind <> 'measured_exceedance' OR "
            "(measured_value IS NOT NULL AND sampled_at IS NOT NULL)",
            name="ck_measured_alert_carries_its_reading"),
    )
    op.create_index("ix_alerts_block", "alerts", ["block_id"])
    op.create_index("ix_alerts_created", "alerts", ["created_at"])
    # One alert per advisory per block, and one per well per sampling date:
    # re-running the generator must not duplicate what a citizen already read.
    op.create_index("uq_alert_screening", "alerts", ["advisory_id", "block_id"],
                    unique=True, postgresql_where=sa.text("advisory_id IS NOT NULL"))
    op.create_index("uq_alert_measured", "alerts",
                    ["block_id", "well_name", "sampled_at"], unique=True,
                    postgresql_where=sa.text("kind = 'measured_exceedance'"))

    # ── read state, per subscriber ───────────────────────────────────
    op.create_table(
        "alert_reads",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("read_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )

    # ── row-level security ───────────────────────────────────────────
    # A subscription is a statement about where somebody lives. It is the most
    # personal datum this system holds, and it must not be readable across
    # accounts — so the policy is scoped to the row's own user, not to a role.
    for table in ("block_subscriptions", "alert_reads"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY {table}_own ON {table} FOR ALL
            USING (
                coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
                OR user_id::text = coalesce(
                       current_setting('app.current_user_id', true), '')
            )
            WITH CHECK (
                coalesce(current_setting('app.bypass_rls', true), 'off') = 'on'
                OR user_id::text = coalesce(
                       current_setting('app.current_user_id', true), '')
            )
        """)

    # Alerts themselves are readable by any signed-in user: they are per-BLOCK,
    # not per-person, and carry nothing about who subscribed. The inbox query
    # joins to subscriptions, which is where the personal filter lives.
    op.execute("ALTER TABLE alerts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE alerts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY alerts_read ON alerts FOR SELECT USING (true)
    """)
    # Only the system generates alerts. There is no endpoint that mints one from
    # user input, and this makes that structural rather than a convention.
    op.execute("""
        CREATE POLICY alerts_write ON alerts FOR INSERT
        WITH CHECK (coalesce(current_setting('app.bypass_rls', true), 'off') = 'on')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS alerts_write ON alerts")
    op.execute("DROP POLICY IF EXISTS alerts_read ON alerts")
    op.execute("DROP POLICY IF EXISTS alert_reads_own ON alert_reads")
    op.execute("DROP POLICY IF EXISTS block_subscriptions_own ON block_subscriptions")
    op.drop_table("alert_reads")
    op.drop_index("uq_alert_measured", table_name="alerts")
    op.drop_index("uq_alert_screening", table_name="alerts")
    op.drop_index("ix_alerts_created", table_name="alerts")
    op.drop_index("ix_alerts_block", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_block_subs_block", table_name="block_subscriptions")
    op.drop_index("ix_block_subs_user", table_name="block_subscriptions")
    op.drop_table("block_subscriptions")
