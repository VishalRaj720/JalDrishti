"""HydraulicHead model for piezometric measurements."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Float, ForeignKey, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class HydraulicHead(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "hydraulic_heads"

    aquifer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aquifers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    head_value: Mapped[float] = mapped_column(Float, nullable=False, comment="m")
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="e.g. well measurement")

    aquifer: Mapped[object] = relationship("Aquifer", back_populates="hydraulic_heads")
