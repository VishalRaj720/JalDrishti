"""ISR Point and Simulation Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, field_validator


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
    # P4: the registry accepted `location` on create/update but never returned
    # it, so the site registry could not say where a site was and the Map
    # Console had nothing to plot. Design §3.2 calls this registry "the heart of
    # the product"; a site without coordinates is not one.
    location: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("location", mode="before")
    @classmethod
    def _geometry_to_geojson(cls, v: Any) -> Optional[Dict[str, Any]]:
        """PostGIS hands back a WKB element; the API speaks GeoJSON."""
        if v is None or isinstance(v, dict):
            return v
        from geoalchemy2.shape import to_shape
        from shapely.geometry import mapping
        return mapping(to_shape(v))


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
