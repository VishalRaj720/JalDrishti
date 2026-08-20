"""ISR (In-Situ Recovery) point model."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class IsrPoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "isr_points"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[Optional[object]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    # ── the operating parameters (migration 0015) ────────────────────
    # A site is a fully specified hypothetical operation, not a bare
    # coordinate: the Studio varies only evaluation year and restoration
    # years, so everything else has to be pinned here or two people running
    # the same site would not be running the same thing.
    injection_rate_m3_day: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="2500", comment="m3/day")
    bleed_percent: Mapped[float] = mapped_column(Float, nullable=False, server_default="2.0")
    operation_years: Mapped[float] = mapped_column(Float, nullable=False, server_default="8.0")
    #: Defaults to 0 — an operation with no remediation sweep — whenever
    #: registration leaves it unset. Editable per-run in the Studio regardless,
    #: because "what if we swept for five years" is a decision to test, not a
    #: property of the site.
    restoration_years: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    wellfield_width_m: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="300.0",
        comment="DIAMETER of the circular well-pattern footprint, not a borehole width")
    monitor_ring_m: Mapped[float] = mapped_column(Float, nullable=False, server_default="100.0")
    ore_depth_m: Mapped[float] = mapped_column(Float, nullable=False, server_default="150.0")
    ore_thickness_m: Mapped[float] = mapped_column(Float, nullable=False, server_default="20.0")

    #: Null means "resolve from the pin" — a different statement from any value
    #: we could store, so these stay nullable rather than taking a default.
    regime_override: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    gradient_i: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    azimuth_deg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    #: The engine's `start_date`: a presentation anchor that turns an evaluation
    #: year into a calendar date and selects the seasonal water-table month. It
    #: does NOT make a run historical — no ISR has operated in Jharkhand.
    injection_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Owning organisation. Migration 0009 added the column and the
    #: `isr_points_write` RLS policy that reads it — an analyst may only write
    #: rows matching their own org — but the mapping was never added here, so
    #: the ORM could not set it and every analyst insert failed the policy.
    owner_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id"), nullable=True, index=True
    )

    # Relationships
    simulations: Mapped[list] = relationship("Simulation", back_populates="isr_point")
