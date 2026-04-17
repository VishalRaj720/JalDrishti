"""MonitoringWell Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MonitoringWellBase(BaseModel):
    name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    depth: Optional[float] = Field(None, description="Well depth in metres")
    well_type: Optional[str] = None


class MonitoringWellCreate(MonitoringWellBase):
    block_id: Optional[uuid.UUID] = None
    paired_station_id: Optional[uuid.UUID] = None


class MonitoringWellResponse(MonitoringWellBase):
    id: uuid.UUID
    block_id: Optional[uuid.UUID] = None
    paired_station_id: Optional[uuid.UUID] = None
    source_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
