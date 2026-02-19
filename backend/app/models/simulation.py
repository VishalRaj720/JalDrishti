"""Simulation, SimulationAquifer, PlumeParameter models."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class SimulationAquifer(Base):
    """Junction table linking simulations to impacted aquifers."""
    __tablename__ = "simulation_aquifers"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id", ondelete="CASCADE"), primary_key=True
    )
    aquifer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aquifers.id", ondelete="CASCADE"), primary_key=True
    )


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
    impacted_aquifers: Mapped[list] = relationship(
        "Aquifer",
        secondary="simulation_aquifers",
        lazy="select",
    )
    plume_parameters: Mapped[Optional[object]] = relationship(
        "PlumeParameter", back_populates="simulation", uselist=False
    )


class PlumeParameter(UUIDPrimaryKeyMixin, Base):
    """Optional physics parameters for the plume transport model."""
    __tablename__ = "plume_parameters"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    dispersivity_longitudinal: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dispersivity_transverse: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    retardation_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    decay_constant: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    simulation: Mapped[object] = relationship("Simulation", back_populates="plume_parameters")
