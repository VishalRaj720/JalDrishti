"""MonitoringStation and GroundwaterLevelReading models."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class MonitoringStation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical groundwater monitoring well linked to a block."""
    __tablename__ = "monitoring_stations"

    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    village: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    well_depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Depth of the well in metres")

    # Relationships
    block: Mapped[object] = relationship("Block", back_populates="monitoring_stations")
    groundwater_readings: Mapped[list] = relationship(
        "GroundwaterLevelReading",
        back_populates="station",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_monitoring_stations_block_id", "block_id"),
    )


class GroundwaterLevelReading(UUIDPrimaryKeyMixin, Base):
    """A single time-stamped groundwater level reading for a monitoring station."""
    __tablename__ = "groundwater_level_readings"

    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    groundwater_level: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Groundwater level in metres below ground level (mbgl)"
    )

    # Relationship
    station: Mapped[object] = relationship("MonitoringStation", back_populates="groundwater_readings")

    __table_args__ = (
        Index("ix_gwl_readings_station_recorded", "station_id", "recorded_at"),
    )
