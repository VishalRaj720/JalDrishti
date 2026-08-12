"""A named, saveable set of simulation inputs.

A scenario is inputs, never results. Runs (`simulation_run.py`) stay immutable
and pinned to the artifacts that produced them, so re-running a scenario after a
retrain adds a second run with a different `artifacts_sha` rather than
overwriting the first — which is what makes a before/after comparison possible
at all.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    isr_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isr_points.id", ondelete="CASCADE"),
        nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("isr_point_id", "name", name="uq_scenario_site_name"),
        Index("ix_scenarios_isr_point", "isr_point_id"),
    )
