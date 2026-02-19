"""MonitoringData model for temporal groundwater quality measurements."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class MonitoringData(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "monitoring_data"

    aquifer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aquifers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    uranium_conc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ec: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Electrical Conductivity")
    eh: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="Redox potential")
    major_ions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    hydraulic_head: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    aquifer: Mapped[object] = relationship("Aquifer", back_populates="monitoring_data")
