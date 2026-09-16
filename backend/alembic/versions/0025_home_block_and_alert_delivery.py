"""home block on the account, and a record of every alert delivery

Revision ID: 0025_home_block_alert_delivery
Revises: 0024_drop_vestigial_sim

R16 (2026-09-16). The alert system had every gate and no exit.

Publication raised the right alerts for the right blocks (migrations 0018,
0021, 0023) and then wrote them to a table that a resident could only read by
signing in, opening the bell, and — before any of that — having manually
searched for and "followed" the block that later turned out to be affected.
The Alerts screen said so in its own subtitle: *"this portal does not send SMS
or email."* The proposal this project answers promises stakeholders will
"receive vulnerability assessments and alerts", and PRODUCT_DESIGN.md §4.4 C3
specified email delivery on threshold crossing. Neither had been built.

Two things close that, and both need schema:

1. **`users.home_block_id`.** A citizen account now carries where the person
   lives. Registration asks for it, resolves it from a map point if offered,
   and subscribes the account to that block on the spot — so the first alert
   about a resident's own water does not depend on their having predicted it.
   Nullable: staff accounts have no home block, and an existing citizen may
   set one later. `ON DELETE SET NULL` because a block re-import must not
   delete accounts.

   `alert_email_opt_in` sits beside it. Delivery defaults ON — an alert about
   drinking water that is opt-in reaches nobody, which is the state this
   migration exists to leave — and the account screen lets a person turn it
   off.

2. **`alert_deliveries`.** One row per (alert, user, channel) attempt, with the
   address it went to and whether it succeeded. Without this the system cannot
   answer "who was told, and when" — which for a public-warning channel is the
   audit question that matters most — and cannot avoid emailing the same
   person twice. The unique index is what makes delivery idempotent; the
   status column is what makes a failed SMTP attempt visible to the operator
   instead of silently retried forever or silently dropped.

   Row-level security: a delivery row carries an email address and a block,
   which together say where a named person lives. Scoped to the row's own
   user exactly as `block_subscriptions` is (migration 0018), with the system
   bypass for the delivery job itself.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_home_block_alert_delivery"
down_revision = "0024_drop_vestigial_sim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── where the account holder lives ───────────────────────────────
    op.add_column("users", sa.Column(
        "home_block_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True))
    op.add_column("users", sa.Column(
        "alert_email_opt_in", sa.Boolean(), nullable=False,
        server_default=sa.text("true")))
    op.create_index("ix_users_home_block", "users", ["home_block_id"])

    # ── the delivery log ─────────────────────────────────────────────
    op.create_table(
        "alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("channel IN ('email')", name="ck_delivery_channel"),
        sa.CheckConstraint("status IN ('sent','failed','skipped')",
                           name="ck_delivery_status"),
    )
    op.create_index("uq_alert_delivery", "alert_deliveries",
                    ["alert_id", "user_id", "channel"], unique=True)
    op.create_index("ix_alert_deliveries_user", "alert_deliveries", ["user_id"])
    op.create_index("ix_alert_deliveries_created", "alert_deliveries", ["created_at"])

    op.execute("ALTER TABLE alert_deliveries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE alert_deliveries FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY alert_deliveries_own ON alert_deliveries FOR ALL
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


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS alert_deliveries_own ON alert_deliveries")
    op.drop_index("ix_alert_deliveries_created", table_name="alert_deliveries")
    op.drop_index("ix_alert_deliveries_user", table_name="alert_deliveries")
    op.drop_index("uq_alert_delivery", table_name="alert_deliveries")
    op.drop_table("alert_deliveries")
    op.drop_index("ix_users_home_block", table_name="users")
    op.drop_column("users", "alert_email_opt_in")
    op.drop_column("users", "home_block_id")
