"""Dataset version — the citable provenance spine.

PRODUCT_DESIGN.md section 5.3. Deliberately NOT a second copy of
`data_sources`: that table is the load ledger (one row per ingested batch, with
the file checksum), and duplicating checksum semantics across two tables is the
failure mode section 3.1 rejects. This table answers a different question —
*which citable dataset is this, who published it, how much evidence is behind
it, and what should a reader be warned about* — and `data_sources` points at it
through `dataset_version_id`.

`n_supporting` is the reason the table exists. The uranium source term rests on
9 measurements from 7 mines; a portal rendering "15,180 ppb" to five significant
figures without saying so is misleading by omission.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Text, Boolean, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class DatasetVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "dataset_versions"

    label: Mapped[str] = mapped_column(String(128), nullable=False)
    source_org: Mapped[str] = mapped_column(String(64), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    n_supporting: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    caveat: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true")
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("label", name="uq_dataset_versions_label"),
    )
