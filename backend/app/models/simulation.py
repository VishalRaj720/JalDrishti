"""The `simulations` table.

`SimulationAquifer` and `PlumeParameter` used to live here. Migration
`0024_drop_vestigial_sim` dropped both: created by `0001_initial`, never read
and never written by any route, service or query in the repository. See that
migration for why an empty `plume_parameters` was worse than no table at all.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Simulation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "simulations"

    isr_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isr_points.id", ondelete="CASCADE"), nullable=False, index=True
    )
    simulation_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Results
    affected_area: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="km2")
    estimated_concentration_spread: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    vulnerability_assessment: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    uncertainty_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    suggested_recovery: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    isr_point: Mapped[object] = relationship("IsrPoint", back_populates="simulations")
