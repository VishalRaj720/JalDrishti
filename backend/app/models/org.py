"""Organisation — the tenant a user and a hypothetical site belong to.

PRODUCT_DESIGN.md section 2: CGWB, SPCB and BIT Sindri are separate bodies with
different mandates, and P2's row-level security keys on `owner_org_id`. Modelling
them now means the RLS policy has something to attach to when it lands.
"""
from datetime import datetime
from sqlalchemy import String, CheckConstraint, UniqueConstraint, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class Org(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "orgs"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # regulator = CGWB/SPCB, academic = BIT Sindri/TEXMiN, utility = water boards
    kind: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_orgs_code"),
        CheckConstraint("kind IN ('regulator','academic','utility','other')",
                        name="ck_orgs_kind"),
    )
