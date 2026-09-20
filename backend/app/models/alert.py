"""Block subscriptions and the in-portal alert inbox.

See `alembic/versions/0018_citizen_alerts.py` for why the two alert channels are
kept structurally separate, why delivery is in-portal only, and why a
subscription is the most privacy-sensitive row in this system.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (CheckConstraint, DateTime, Float, ForeignKey, Index,
                        String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BlockSubscription(Base):
    __tablename__ = "block_subscriptions"

    #: `server_default` MATCHES THE MIGRATION, deliberately. The ORM's
    #: `default=uuid.uuid4` is a Python-side default and applies only to inserts
    #: made through the ORM; this service inserts via raw SQL (for
    #: `ON CONFLICT DO NOTHING`, which is what makes alerts idempotent). The
    #: development database got its default from the migration and worked; the
    #: test database is built from this metadata and did not, so the drift
    #: surfaced as a NOT NULL violation in one environment only.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "block_id", name="uq_subscription_user_block"),
        Index("ix_block_subs_user", "user_id"),
        Index("ix_block_subs_block", "block_id"),
    )


class Alert(Base):
    """One alert, about one block.

    Not per-person: an alert is a fact about an area, and every subscriber to
    that area sees the same one. Read state is separate (`AlertRead`) for
    exactly that reason.
    """
    __tablename__ = "alerts"

    #: `server_default` MATCHES THE MIGRATION, deliberately. The ORM's
    #: `default=uuid.uuid4` is a Python-side default and applies only to inserts
    #: made through the ORM; this service inserts via raw SQL (for
    #: `ON CONFLICT DO NOTHING`, which is what makes alerts idempotent). The
    #: development database got its default from the migration and worked; the
    #: test database is built from this metadata and did not, so the drift
    #: surfaced as a NOT NULL violation in one environment only.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    #: 'measured_exceedance' — a real CGWB lab result over the BIS limit.
    #: 'published_screening' — a regulator published a modelled assessment.
    #: These must never be merged into one feed; see the migration docstring.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False)
    advisory_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advisories.id", ondelete="CASCADE"),
        nullable=True)

    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Legacy three-valued severity, derived from `tier` since R17 so older
    #: readers keep working. `tier` is the authoritative field.
    severity: Mapped[str] = mapped_column(String(16), nullable=False,
                                          server_default="info")
    #: R17 (migration 0026). `notice | warning | alert | critical` on the
    #: IS 10500 acceptable/permissible ladder with one project-defined rung
    #: (see `services/alert_tiers.py`). A modelled alert is never `critical`;
    #: the CHECK below refuses the row if code ever tries.
    tier: Mapped[str] = mapped_column(String(16), nullable=False,
                                      server_default="notice")
    #: `observed` (a laboratory result) or `modelled` (a screening). Explicit
    #: rather than inferred from `kind`, and cross-checked against it.
    basis: Mapped[str] = mapped_column(String(16), nullable=False,
                                       server_default="modelled")
    #: The seven fields: what_happened, driver, where, tier, basis,
    #: confidence, next_action. NULL only on rows written before R17 and not
    #: yet rebuilt; readers must treat that as "not recorded".
    explanation: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    well_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    measured_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measured_unit: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    sampled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('measured_exceedance','published_screening',"
            "'aquifer_pathway','aquifer_breach_due','possible_reach')",
            name="ck_alert_kind"),
        CheckConstraint("severity IN ('info','warning','high')",
                        name="ck_alert_severity"),
        CheckConstraint("tier IN ('notice','warning','alert','critical')",
                        name="ck_alert_tier"),
        CheckConstraint("basis IN ('observed','modelled')",
                        name="ck_alert_basis"),
        # a modelled result is never critical: no mine exists, nothing measured
        CheckConstraint("NOT (basis = 'modelled' AND tier = 'critical')",
                        name="ck_modelled_never_critical"),
        CheckConstraint("(kind = 'measured_exceedance') = (basis = 'observed')",
                        name="ck_basis_matches_kind"),
        CheckConstraint("kind <> 'published_screening' OR advisory_id IS NOT NULL",
                        name="ck_screening_alert_names_its_advisory"),
        CheckConstraint(
            "kind <> 'measured_exceedance' OR "
            "(measured_value IS NOT NULL AND sampled_at IS NOT NULL)",
            name="ck_measured_alert_carries_its_reading"),
        Index("ix_alerts_block", "block_id"),
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_tier", "tier"),
        # THE PARTIAL UNIQUE INDEXES ARE LOAD-BEARING, not an optimisation.
        # `AlertService` inserts with `ON CONFLICT (...) DO NOTHING`, and that
        # clause needs a matching unique index to arbitrate against — without
        # them the insert raises instead of skipping, and re-running a scan
        # would either error or put the same warning in front of a citizen
        # twice. They must therefore live here as well as in migration 0018,
        # because the test database is built from this metadata.
        # `kind` is part of the key (migration 0021). A block can legitimately
        # receive both the footprint alert and the aquifer-pathway alert from
        # one advisory — they are different claims about different areas. Keyed
        # on (advisory, block) alone, the second insert would have hit
        # ON CONFLICT DO NOTHING and vanished with no error to notice.
        Index("uq_alert_screening", "advisory_id", "block_id", "kind",
              unique=True,
              postgresql_where=text("advisory_id IS NOT NULL")),
        Index("uq_alert_measured", "block_id", "well_name", "sampled_at",
              unique=True,
              postgresql_where=text("kind = 'measured_exceedance'")),
    )


class AlertDelivery(Base):
    """One attempt to put one alert in front of one person, off-portal.

    The inbox is per-block; this is per-person, because delivery is. The
    unique index on (alert, user, channel) is what makes `notify.deliver_pending`
    idempotent: re-running it after a crash sends nothing twice. `status` is
    what makes a failed SMTP attempt visible instead of silently dropped —
    the operator's delivery panel counts them.

    RLS-scoped to the row's own user (migration 0025), because an address and
    a block together say where a named person lives.
    """
    __tablename__ = "alert_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("channel IN ('email')", name="ck_delivery_channel"),
        CheckConstraint("status IN ('sent','failed','skipped')",
                        name="ck_delivery_status"),
        # Load-bearing for ON CONFLICT DO NOTHING; see `Alert.__table_args__`.
        Index("uq_alert_delivery", "alert_id", "user_id", "channel", unique=True),
        Index("ix_alert_deliveries_user", "user_id"),
        Index("ix_alert_deliveries_created", "created_at"),
    )


class AlertRead(Base):
    __tablename__ = "alert_reads"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="CASCADE"),
        primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True)
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
