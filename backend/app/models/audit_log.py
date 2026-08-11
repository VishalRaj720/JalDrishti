"""Audit log — who ran what, when.

PRODUCT_DESIGN.md section 3.3 lists `GET /audit` as non-negotiable for a
government portal. Two deliberate choices:

* `actor_id` is `ON DELETE SET NULL`, and `actor_label` keeps a denormalised
  copy of the identity. Deleting a user must never delete the record of what
  they did, and the log must stay readable after the account is gone.
* Append-only is convention here, not yet enforcement; P2 adds the RLS policy
  that forbids UPDATE and DELETE.
"""
import uuid
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any, Optional, Union
from sqlalchemy import (String, Text, BigInteger, DateTime, ForeignKey, Index,
                        func)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # BigInteger identity rather than UUID: this table is append-only and read
    # in time order, so a monotonic key indexes and pages better than a random one.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True,
                                    autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
    actor_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # Accepts a str on write; asyncpg reads it back as an ipaddress object.
    ip_address: Mapped[Optional[Union[str, IPv4Address, IPv6Address]]] = \
        mapped_column(INET, nullable=True)

    __table_args__ = (
        Index("ix_audit_log_occurred_at", "occurred_at"),
        Index("ix_audit_log_actor", "actor_id"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )
