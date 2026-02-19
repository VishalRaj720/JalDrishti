"""District and Block Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class DistrictBase(BaseModel):
    name: str
    avg_porosity: Optional[float] = None
    avg_hydraulic_conductivity: Optional[float] = None
    vulnerability_index: Optional[float] = None


class DistrictCreate(DistrictBase):
    geometry: Optional[Any] = None  # GeoJSON FeatureCollection or dict


class DistrictUpdate(BaseModel):
    name: Optional[str] = None
    geometry: Optional[Any] = None
    avg_porosity: Optional[float] = None
    avg_hydraulic_conductivity: Optional[float] = None
    vulnerability_index: Optional[float] = None


class DistrictResponse(DistrictBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Blocks ────────────────────────────────────────────────────────

class BlockBase(BaseModel):
    name: str
    district_id: uuid.UUID
    aquifer_distribution: Optional[dict] = None
    avg_porosity: Optional[float] = None
    avg_permeability: Optional[float] = None


class BlockCreate(BlockBase):
    geometry: Optional[Any] = None


class BlockUpdate(BaseModel):
    name: Optional[str] = None
    geometry: Optional[Any] = None
    aquifer_distribution: Optional[dict] = None
    avg_porosity: Optional[float] = None
    avg_permeability: Optional[float] = None


class BlockResponse(BlockBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
