"""District model with PostGIS geometry."""
from typing import Optional
from sqlalchemy import String, Float, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class District(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "districts"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    geometry: Mapped[Optional[object]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    avg_porosity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_hydraulic_conductivity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vulnerability_index: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    blocks: Mapped[list] = relationship("Block", back_populates="district", lazy="select")

    __table_args__ = (
        Index("ix_districts_geometry", "geometry", postgresql_using="gist"),
    )
