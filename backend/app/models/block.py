"""Block model (subdivision of districts)."""
import uuid
from typing import Optional
from sqlalchemy import String, Float, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class Block(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "blocks"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    district_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("districts.id", ondelete="CASCADE"), nullable=False
    )
    geometry: Mapped[Optional[object]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    aquifer_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    avg_porosity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_permeability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    district: Mapped[object] = relationship("District", back_populates="blocks")
    aquifers: Mapped[list] = relationship("Aquifer", back_populates="block", lazy="select")

    __table_args__ = (
        UniqueConstraint("name", "district_id", name="uq_block_name_district"),
        Index("ix_blocks_geometry", "geometry", postgresql_using="gist"),
    )
