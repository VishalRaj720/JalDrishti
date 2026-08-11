"""Field observations: the proposal queue, and field-discovered ore presence.

See `alembic/versions/0010_field_observations.py` for why proposals live in a
separate table instead of a `status` column on the authoritative ones.
"""
import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from geoalchemy2 import Geography
from sqlalchemy import (String, Text, Float, DateTime, ForeignKey, Index,
                        CheckConstraint, func)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ObservationType(str, enum.Enum):
    water_sample = "water_sample"
    groundwater_level = "groundwater_level"
    ore_presence = "ore_presence"


class ObservationOperation(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"


class ObservationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


#: Which authoritative table each observation type resolves to. Nothing outside
#: this mapping can be targeted — a submission naming an arbitrary table would
#: otherwise turn the approval path into a generic write primitive.
TARGET_TABLES: dict[str, str] = {
    ObservationType.water_sample.value: "water_samples",
    ObservationType.groundwater_level.value: "groundwater_level_readings",
    ObservationType.ore_presence.value: "ore_observations",
}

#: Columns a field officer may set, per type. Anything else in a payload is
#: rejected at submit time rather than silently dropped: an allowlist keeps the
#: approval path from writing to columns nobody reviewed, such as `synthetic`
#: (which marks ML-augmented rows) or a primary key.
ALLOWED_FIELDS: dict[str, frozenset[str]] = {
    ObservationType.water_sample.value: frozenset({
        "well_id", "sampled_at", "ph", "ec_us_cm", "tds_mg_l", "turbidity_ntu",
        "do_mg_l", "total_hardness", "uranium_ppb", "nitrate_mg_l",
        "fluoride_mg_l", "arsenic_ppb", "iron_ppm", "chloride_mg_l",
        "sulphate_mg_l", "bicarbonate_mg_l", "carbonate_mg_l", "phosphate_mg_l",
        "calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "potassium_mg_l",
    }),
    ObservationType.groundwater_level.value: frozenset({
        "station_id", "recorded_at", "groundwater_level",
    }),
    ObservationType.ore_presence.value: frozenset({
        "name", "longitude", "latitude", "ore_zone", "uranium_grade_pct",
        "depth_m", "observed_at", "notes",
    }),
}

#: Fields that are timestamps. JSON carries them as ISO strings, but asyncpg
#: binds parameters by Python type and rejects a str for a timestamptz column
#: ("expected a datetime.date or datetime.datetime instance"). They are parsed
#: at submit time so a bad value is refused by the submitter rather than
#: surfacing as an error for the reviewer, and re-parsed at apply time because
#: JSONB stores them back as strings.
DATETIME_FIELDS: dict[str, frozenset[str]] = {
    ObservationType.water_sample.value: frozenset({"sampled_at"}),
    ObservationType.groundwater_level.value: frozenset({"recorded_at"}),
    ObservationType.ore_presence.value: frozenset({"observed_at"}),
}

#: Fields that must be a UUID for the same reason.
UUID_FIELDS: dict[str, frozenset[str]] = {
    ObservationType.water_sample.value: frozenset({"well_id"}),
    ObservationType.groundwater_level.value: frozenset({"station_id"}),
    ObservationType.ore_presence.value: frozenset(),
}

#: Required on a `create`, per type.
REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    ObservationType.water_sample.value: frozenset({"well_id", "sampled_at"}),
    ObservationType.groundwater_level.value: frozenset(
        {"station_id", "recorded_at", "groundwater_level"}),
    ObservationType.ore_presence.value: frozenset(
        {"name", "longitude", "latitude", "ore_zone", "observed_at"}),
}


class FieldObservation(Base):
    __tablename__ = "field_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    observation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(8), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True)

    proposed: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    previous: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    target_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    location = mapped_column(Geography(geometry_type="POINT", srid=4326),
                             nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        server_default="pending")
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True)

    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applied_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "observation_type IN ('water_sample','groundwater_level','ore_presence')",
            name="ck_field_obs_type"),
        CheckConstraint("operation IN ('create','update','delete')",
                        name="ck_field_obs_operation"),
        CheckConstraint("status IN ('pending','approved','rejected','withdrawn')",
                        name="ck_field_obs_status"),
        CheckConstraint("reviewed_by IS NULL OR reviewed_by <> submitted_by",
                        name="ck_field_obs_no_self_review"),
        CheckConstraint(
            "(status IN ('pending','withdrawn')) "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_field_obs_decided_has_reviewer"),
        CheckConstraint(
            "(operation = 'create' AND target_id IS NULL) "
            "OR (operation IN ('update','delete') AND target_id IS NOT NULL)",
            name="ck_field_obs_target_matches_operation"),
        CheckConstraint("applied_id IS NULL OR status = 'approved'",
                        name="ck_field_obs_applied_only_when_approved"),
        Index("ix_field_obs_status", "status"),
        Index("ix_field_obs_submitter", "submitted_by"),
        Index("ix_field_obs_target", "target_table", "target_id"),
    )


class OreObservation(Base):
    """Field-discovered uranium ore presence.

    Deliberately separate from the reference ore dataset under `Datasets/`,
    which carries GSI and mine-record provenance. A field sighting approved by a
    regulator is a different kind of evidence and must stay distinguishable.
    """
    __tablename__ = "ore_observations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location = mapped_column(Geography(geometry_type="POINT", srid=4326),
                             nullable=False)
    ore_zone: Mapped[str] = mapped_column(String(16), nullable=False)
    uranium_grade_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    origin_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("ore_zone IN ('deposit','belt','none')",
                        name="ck_ore_observations_zone"),
        CheckConstraint(
            "uranium_grade_pct IS NULL OR "
            "(uranium_grade_pct >= 0 AND uranium_grade_pct <= 100)",
            name="ck_ore_observations_grade"),
    )
