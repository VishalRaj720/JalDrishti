"""MLModel versioning model."""
import enum
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, ENUM as PGEnum
from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class MLModelType(str, enum.Enum):
    regression = "regression"
    classification = "classification"
    plume_estimation = "plume_estimation"


class MLModel(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ml_models"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[MLModelType] = mapped_column(
        PGEnum(MLModelType, name="mlmodeltype", create_type=False), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="S3 or local path to artifact")
    feature_schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    trained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
