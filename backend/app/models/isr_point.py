"""ISR (In-Situ Recovery) point model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Float, DateTime
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
    injection_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="m3/day")
    injection_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    injection_end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    simulations: Mapped[list] = relationship("Simulation", back_populates="isr_point")
