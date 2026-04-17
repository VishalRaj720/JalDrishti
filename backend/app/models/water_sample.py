"""WaterSample: one water-quality measurement taken at a monitoring well."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Float, Boolean, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class WaterSample(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "water_samples"

    well_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("monitoring_wells.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Physical
    ph: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ec_us_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tds_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tds_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    turbidity_ntu: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    do_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_hardness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Chemistry
    uranium_ppb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    nitrate_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fluoride_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    arsenic_ppb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iron_ppm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chloride_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sulphate_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bicarbonate_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbonate_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    phosphate_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calcium_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    magnesium_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sodium_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    potassium_mg_l: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    well: Mapped[object] = relationship("MonitoringWell", back_populates="water_samples")

    __table_args__ = (
        Index("ix_water_samples_well_sampled", "well_id", "sampled_at"),
    )
