"""ISR Point and Simulation Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel


# ── ISR Points ────────────────────────────────────────────────────

class IsrPointBase(BaseModel):
    name: str
    injection_rate: Optional[float] = None
    injection_start_date: Optional[datetime] = None
    injection_end_date: Optional[datetime] = None


class IsrPointCreate(IsrPointBase):
    location: Optional[Dict[str, Any]] = None  # GeoJSON Point


class IsrPointUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    injection_rate: Optional[float] = None
    injection_start_date: Optional[datetime] = None
    injection_end_date: Optional[datetime] = None


class IsrPointResponse(IsrPointBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Simulations ───────────────────────────────────────────────────

class SimulationResponse(BaseModel):
    id: uuid.UUID
    isr_point_id: uuid.UUID
    simulation_date: datetime
    status: str
    task_id: Optional[str] = None
    affected_area: Optional[float] = None
    estimated_concentration_spread: Optional[Dict] = None
    vulnerability_assessment: Optional[Dict] = None
    uncertainty_estimate: Optional[float] = None
    suggested_recovery: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlumeParameterCreate(BaseModel):
    dispersivity_longitudinal: Optional[float] = None
    dispersivity_transverse: Optional[float] = None
    retardation_factor: Optional[float] = None
    decay_constant: Optional[float] = None
