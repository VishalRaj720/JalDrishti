"""Per-aquifer spatial analysis result produced by a simulation."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class SpatialAnalysisResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "spatial_analysis_results"

    simulation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    aquifer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aquifers.id", ondelete="CASCADE"), nullable=False
    )
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vulnerability_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    affected_area_km2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("simulation_id", "aquifer_id", name="uq_spatial_result_sim_aquifer"),
    )
