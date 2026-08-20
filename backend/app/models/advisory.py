"""A screening published to the public, and the regulator decision behind it.

See `alembic/versions/0017_advisories.py` for why publication is a regulator
act, why the plain-language text is stored rather than templated at read time,
and why `footprint` is real PostGIS geometry when `simulation_runs.plume` is
not.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (CheckConstraint, DateTime, Float, ForeignKey, Index,
                        String, Text, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geometry

from app.database import Base


class Advisory(Base):
    __tablename__ = "advisories"

    #: `server_default` MATCHES THE MIGRATION. `default=uuid.uuid4` alone is a
    #: Python-side default that applies only to ORM inserts, and the test
    #: database is built from this metadata rather than from the migrations — so
    #: any raw-SQL insert would work in development (where the migration set the
    #: default) and fail in tests. Keeping both means the two paths agree.
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    isr_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("isr_points.id", ondelete="CASCADE"),
        nullable=False)
    #: RESTRICT, not CASCADE: an advisory that cannot name the run behind it is
    #: an opinion. Deleting a published run must fail loudly.
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("simulation_runs.id", ondelete="RESTRICT"),
        nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        server_default="proposed")

    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    what_it_means: Mapped[str] = mapped_column(Text, nullable=False)
    what_to_do: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    species: Mapped[str] = mapped_column(String(32), nullable=False)
    time_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    restoration_years: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    footprint: Mapped[Optional[object]] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True)
    footprint_ha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    affected_blocks: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True)

    proposed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    proposed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
        onupdate=func.now())

    __table_args__ = (
        CheckConstraint("status IN ('proposed','published','withdrawn','rejected')",
                        name="ck_advisory_status"),
        CheckConstraint(
            "status <> 'published' OR (decided_by IS NOT NULL "
            "AND published_at IS NOT NULL)",
            name="ck_advisory_published_has_a_decider"),
        CheckConstraint(
            "status <> 'withdrawn' OR withdrawn_at IS NOT NULL",
            name="ck_advisory_withdrawn_has_a_time"),
        Index("ix_advisories_status", "status"),
        Index("ix_advisories_isr_point", "isr_point_id"),
    )
