"""Load ledger — one row per ingested batch, with the file checksum.

This is the LEDGER half of provenance. The citable-dataset half lives in
`dataset_versions` (added by migration 0007) and this table points at it, so
checksum semantics stay owned in exactly one place. See that model's docstring
for why the two are not merged.

Note the granularity is per-batch, not per-file: the groundwater load writes one
row per station (`gw_level:<station>`), so 415 of the current rows all reference
the same CSV.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (String, Integer, Text, DateTime, ForeignKey,
                        UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import UUID
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
    # Nullable on purpose: a load with no registered dataset is a gap for the
    # data-quality report to flag, not a reason to reject the load.
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # NOTE: source_type already gets an index via `index=True` above; a second
    # explicit Index with the same name made create_all fail ("already exists").
    __table_args__ = (
        UniqueConstraint("name", "checksum", name="uq_data_sources_name_checksum"),
    )
