"""Aquifer Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel
from app.models.aquifer import AquiferType


class AquiferBase(BaseModel):
    name: str
    type: AquiferType
    block_id: Optional[uuid.UUID] = None
    min_depth: Optional[float] = None
    max_depth: Optional[float] = None
    porosity: Optional[float] = None
    hydraulic_conductivity: Optional[float] = None
    transmissivity: Optional[float] = None
    storage_coefficient: Optional[float] = None
    specific_yield: Optional[float] = None
    quality_ec: Optional[float] = None
    dtw_decadal_avg: Optional[float] = None
    fractures_encountered: Optional[str] = None
    yield_range: Optional[str] = None


class AquiferCreate(AquiferBase):
    geometry: Optional[Any] = None


class AquiferUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[AquiferType] = None
    block_id: Optional[uuid.UUID] = None
    geometry: Optional[Any] = None
    min_depth: Optional[float] = None
    max_depth: Optional[float] = None
    porosity: Optional[float] = None
    hydraulic_conductivity: Optional[float] = None
    transmissivity: Optional[float] = None
    storage_coefficient: Optional[float] = None
    specific_yield: Optional[float] = None
    quality_ec: Optional[float] = None
    dtw_decadal_avg: Optional[float] = None
    fractures_encountered: Optional[str] = None
    yield_range: Optional[str] = None


class AquiferResponse(AquiferBase):
    id: uuid.UUID
    thickness: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
