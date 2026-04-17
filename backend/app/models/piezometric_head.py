"""Piezometric head observations (FK to monitoring_stations)."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class PiezometricHead(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "piezometric_heads"

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_stations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    head_value_m: Mapped[float] = mapped_column(Float, nullable=False)
    data_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("ix_piezometric_heads_station_measured", "station_id", "measured_at"),
    )
