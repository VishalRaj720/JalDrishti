"""User model with RBAC roles."""
import uuid
from datetime import datetime
import enum
from typing import Optional
from sqlalchemy import String, ForeignKey, func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"
    # Added by migration 0007 (PRODUCT_DESIGN.md section 2). The vocabulary
    # exists so the schema can express the five designed roles; the gateway that
    # actually distinguishes them is P2, which is also where `viewer` migrates to
    # `citizen`. Until then `viewer` remains the default and stays valid --
    # Postgres cannot drop an enum value, and retiring it here without the code
    # that depends on it would strand the running app.
    regulator = "regulator"
    field_officer = "field_officer"
    citizen = "citizen"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        PGEnum(UserRole, name="userrole", create_type=False),
        nullable=False,
        default=UserRole.viewer,
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
