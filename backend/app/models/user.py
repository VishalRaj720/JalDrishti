"""User model with RBAC roles."""
import uuid
from datetime import datetime
import enum
from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, TimestampMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


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
