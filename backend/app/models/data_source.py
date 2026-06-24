"""Data provenance record for every ingested file."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class DataSource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # NOTE: source_type already gets an index via `index=True` above; a second
    # explicit Index with the same name made create_all fail ("already exists").
    __table_args__ = (
        UniqueConstraint("name", "checksum", name="uq_data_sources_name_checksum"),
    )
