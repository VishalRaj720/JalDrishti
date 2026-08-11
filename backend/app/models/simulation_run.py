"""A single execution of the real ml_pipeline engine, pinned for reproducibility.

See `alembic/versions/0012_simulation_runs.py` for why the provenance columns
are required on a completed run.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (String, Text, Integer, DateTime, ForeignKey, Index,
                        CheckConstraint, func)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    isr_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isr_points.id", ondelete="CASCADE"),
        nullable=False)
    scenario_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        server_default="queued")
    engine: Mapped[str] = mapped_column(String(16), nullable=False,
                                        server_default="both")
    species: Mapped[str] = mapped_column(String(32), nullable=False)

    model_card_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    artifacts_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    code_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True)

    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    inputs: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    excursion: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    extrapolation: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True)
    hydro: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    runtime_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')",
                        name="ck_sim_runs_status"),
        CheckConstraint("engine IN ('analytical','ml','both')",
                        name="ck_sim_runs_engine"),
        CheckConstraint(
            "status <> 'completed' OR (model_card_sha IS NOT NULL "
            "AND artifacts_sha IS NOT NULL AND code_version IS NOT NULL)",
            name="ck_sim_runs_completed_is_pinned"),
        Index("ix_sim_runs_isr_point", "isr_point_id"),
        Index("ix_sim_runs_created_at", "created_at"),
    )
