"""Monitoring well: water-quality sampling point (separate from monitoring_stations)."""
import uuid
from typing import Optional
from sqlalchemy import String, Float, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class MonitoringWell(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "monitoring_wells"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    block_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Well depth in metres")
    well_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    paired_station_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_stations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )

    water_samples: Mapped[list] = relationship(
        "WaterSample", back_populates="well", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("latitude", "longitude", name="uq_monitoring_wells_lat_lon"),
        Index("ix_monitoring_wells_location", "location", postgresql_using="gist"),
    )
