"""Monitoring Station and Groundwater Level Reading Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# ── Groundwater Level Readings ────────────────────────────────────────────────

class GroundwaterReadingBase(BaseModel):
    recorded_at: datetime
    groundwater_level: float = Field(..., description="Groundwater level in metres below ground level (mbgl)")


class GroundwaterReadingCreate(GroundwaterReadingBase):
    pass


class GroundwaterReadingResponse(GroundwaterReadingBase):
    id: uuid.UUID
    station_id: uuid.UUID

    model_config = {"from_attributes": True}


# ── Monitoring Stations ───────────────────────────────────────────────────────

class MonitoringStationBase(BaseModel):
    name: str
    village: Optional[str] = None
    latitude: float
    longitude: float
    well_depth: Optional[float] = Field(None, description="Well depth in metres")


class MonitoringStationCreate(MonitoringStationBase):
    pass


class MonitoringStationUpdate(BaseModel):
    name: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    well_depth: Optional[float] = None


class MonitoringStationResponse(MonitoringStationBase):
    id: uuid.UUID
    block_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    groundwater_readings: List[GroundwaterReadingResponse] = []

    @field_validator("groundwater_readings", mode="before")
    @classmethod
    def coerce_to_list(cls, v):
        """Coerce None or a bare ORM object into a list — SQLAlchemy can return either
        when a relationship collection has never been fully loaded."""
        if v is None:
            return []
        if not isinstance(v, list):
            return [v]
        return v

    model_config = {"from_attributes": True}


# ── Overview (embedded in BlockDetailResponse) ────────────────────────────────

class MonitoringStationOverview(BaseModel):
    """Slim summary embedded in block detail responses."""
    id: uuid.UUID
    name: str
    village: Optional[str] = None
    latitude: float
    longitude: float
    well_depth: Optional[float] = None
    reading_count: int = 0
    latest_groundwater_level: Optional[float] = None
    latest_recorded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
