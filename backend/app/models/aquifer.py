"""Aquifer model with PostGIS geometry and comprehensive geological fields."""
import uuid
import enum
from typing import Optional
from sqlalchemy import String, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class AquiferType(str, enum.Enum):
    basalt = "basalt"
    charnockite = "charnockite"
    gneiss = "gneiss"
    limestone = "limestone"
    sandstone = "sandstone"
    alluvium = "alluvium"
    basement_gneissic_complex = "basement_gneissic_complex"
    granite = "granite"
    intrusive = "intrusive"
    laterite = "laterite"
    quartzite = "quartzite"
    schist = "schist"


class Aquifer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "aquifers"

    block_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("blocks.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[AquiferType] = mapped_column(
        PGEnum(AquiferType, name="aquifertype", create_type=False), nullable=False
    )

    # Depth
    min_depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="m")
    max_depth: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="m")
    thickness: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Computed as max - min, m")

    # Spatial
    geometry: Mapped[Optional[object]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )

    # Hydraulic properties
    porosity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hydraulic_conductivity: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="m/day")
    transmissivity: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="m2/day")
    storage_coefficient: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    specific_yield: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="%")

    # Water quality
    quality_ec: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="micromhos/cm")
    dtw_decadal_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Depth to water, m bgl")

    # Well statistics
    fractures_encountered: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    yield_range: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, name="yield", comment="e.g. 26-176 m3/day"
    )

    # Relationships
    block: Mapped[Optional[object]] = relationship("Block", back_populates="aquifers")
    hydraulic_heads: Mapped[list] = relationship("HydraulicHead", back_populates="aquifer")
    monitoring_data: Mapped[list] = relationship("MonitoringData", back_populates="aquifer")

    __table_args__ = (
        Index("ix_aquifers_geometry", "geometry", postgresql_using="gist"),
        Index("ix_aquifers_block_id", "block_id"),
    )
