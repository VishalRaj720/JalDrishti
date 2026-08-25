"""ISR Point and Simulation Pydantic schemas."""
import uuid
from datetime import datetime
from typing import Optional, Any, Dict, List, Literal
from pydantic import BaseModel, Field, field_validator

from app.engine_bounds import BOUNDS as B


# ── ISR Points ────────────────────────────────────────────────────
#
# Every bound below is READ FROM `ml_pipeline` at import (see
# `app/engine_bounds.py`), never retyped. A range copied by hand is a range
# that drifts: the engine is entitled to widen `restoration_years` or move the
# monitor-ring window, and when it does, a hand-typed `le=` here would start
# rejecting values the engine happily serves — or, worse, accepting ones it
# does not.

class IsrPointBase(BaseModel):
    name: str

    #: The operating parameters. A site is a fully specified hypothetical
    #: operation (migration 0015) so that the Studio can vary time alone.
    injection_rate_m3_day: float = Field(
        B.injection_rate_default, ge=B.injection_rate_min, le=B.injection_rate_max)
    bleed_percent: float = Field(B.bleed_default, ge=B.bleed_min, le=B.bleed_max)
    operation_years: float = Field(
        B.operation_years_default, ge=B.operation_years_min, le=B.operation_years_max)
    #: 0 = no remediation sweep. Deliberately the default rather than a required
    #: field: an unanswered question should read as "none planned", and the
    #: Studio can test a sweep against the site without editing it.
    restoration_years: float = Field(
        0.0, ge=B.restoration_min, le=B.restoration_ui_max)
    wellfield_width_m: float = Field(
        B.wellfield_width_default, ge=B.wellfield_width_min, le=B.wellfield_width_max,
        description="DIAMETER of the circular well-pattern footprint — "
                    "not a borehole width and not a well spacing.")
    monitor_ring_m: float = Field(
        B.monitor_ring_default, ge=B.monitor_ring_min, le=B.monitor_ring_max)
    ore_depth_m: float = Field(
        B.ore_depth_default, ge=B.ore_depth_min, le=B.ore_depth_max)
    ore_thickness_m: float = Field(
        B.ore_thickness_default, ge=B.ore_thickness_min, le=B.ore_thickness_max)

    #: None = resolve from the pin. Not the same as any value we could pick.
    regime_override: Optional[Literal["fractured", "porous"]] = None
    gradient_i: Optional[float] = Field(None, ge=B.gradient_min, le=B.gradient_max)
    azimuth_deg: Optional[float] = Field(None, ge=0, le=360)

    #: The engine's `start_date` — a scenario anchor, not a record. No ISR
    #: operation has ever existed in Jharkhand.
    injection_start_date: Optional[datetime] = None


class IsrPointCreate(IsrPointBase):
    """Registration demands a fully specified operation.

    P2. Every operating parameter previously carried a default, so a client
    could register a site by posting a name alone — and the portal's own map did
    exactly that, sending a misspelled `injection_rate` that Pydantic silently
    dropped. The result was a registry of sites that all claimed 2500 m³/day
    because nobody had ever chosen a value.

    A site is the operation (migration 0015). If it can be created without
    stating what the operation IS, then the operation is whatever the schema
    happened to default to, and "run the registered site" means nothing.

    THE SPLIT between required and optional is deliberate and is not about
    importance:

    * **Required** — the operator's choices. There is no defensible default for
      how much lixiviant you inject or how wide the wellfield is; a default here
      is a fabricated decision attributed to a user.
    * **Optional** — the three fields where `None` is a *different statement*
      from any number: `regime_override`, `gradient_i` and `azimuth_deg` mean
      "resolve this from the pin's own hydrogeology", which is the more honest
      answer and usually the right one. `injection_start_date` is a presentation
      anchor. `restoration_years` defaults to 0 because "no remediation sweep
      planned" is a real, common answer — and the sweep is the one thing a run
      may vary against a fixed site anyway.

    `location` becomes required for the same reason: design §3.2 calls the
    registry the heart of the product, and a site without a coordinate cannot be
    drawn, cannot be run, and cannot be published.
    """
    location: Dict[str, Any] = Field(
        ..., description="GeoJSON Point — required. A site without a coordinate "
                         "cannot be run or drawn.")

    injection_rate_m3_day: float = Field(
        ..., ge=B.injection_rate_min, le=B.injection_rate_max)
    bleed_percent: float = Field(..., ge=B.bleed_min, le=B.bleed_max)
    operation_years: float = Field(
        ..., ge=B.operation_years_min, le=B.operation_years_max)
    wellfield_width_m: float = Field(
        ..., ge=B.wellfield_width_min, le=B.wellfield_width_max,
        description="DIAMETER of the circular well-pattern footprint.")
    monitor_ring_m: float = Field(
        ..., ge=B.monitor_ring_min, le=B.monitor_ring_max)
    ore_depth_m: float = Field(..., ge=B.ore_depth_min, le=B.ore_depth_max)
    ore_thickness_m: float = Field(
        ..., ge=B.ore_thickness_min, le=B.ore_thickness_max)

    @field_validator("location")
    @classmethod
    def _is_a_point(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Reject anything that is not a GeoJSON Point with two finite numbers.

        Caught here rather than at the PostGIS layer because the database error
        for a malformed geometry names a WKB parse failure, which tells the
        analyst nothing they can act on.
        """
        if not isinstance(v, dict) or v.get("type") != "Point":
            raise ValueError("location must be a GeoJSON Point")
        coords = v.get("coordinates")
        if (not isinstance(coords, (list, tuple)) or len(coords) != 2
                or not all(isinstance(c, (int, float)) for c in coords)):
            raise ValueError("location.coordinates must be [longitude, latitude]")
        lon, lat = float(coords[0]), float(coords[1])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("location.coordinates out of range; expected "
                             "[longitude, latitude] in that order")
        return v


class IsrPointUpdate(BaseModel):
    """Every field optional: a partial edit must not reset the rest to defaults."""
    name: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    injection_rate_m3_day: Optional[float] = Field(
        None, ge=B.injection_rate_min, le=B.injection_rate_max)
    bleed_percent: Optional[float] = Field(None, ge=B.bleed_min, le=B.bleed_max)
    operation_years: Optional[float] = Field(
        None, ge=B.operation_years_min, le=B.operation_years_max)
    restoration_years: Optional[float] = Field(
        None, ge=B.restoration_min, le=B.restoration_ui_max)
    wellfield_width_m: Optional[float] = Field(
        None, ge=B.wellfield_width_min, le=B.wellfield_width_max)
    monitor_ring_m: Optional[float] = Field(
        None, ge=B.monitor_ring_min, le=B.monitor_ring_max)
    ore_depth_m: Optional[float] = Field(None, ge=B.ore_depth_min, le=B.ore_depth_max)
    ore_thickness_m: Optional[float] = Field(
        None, ge=B.ore_thickness_min, le=B.ore_thickness_max)
    regime_override: Optional[Literal["fractured", "porous"]] = None
    gradient_i: Optional[float] = Field(None, ge=B.gradient_min, le=B.gradient_max)
    azimuth_deg: Optional[float] = Field(None, ge=0, le=360)
    injection_start_date: Optional[datetime] = None


class IsrPointResponse(BaseModel):
    """What a site looks like on the way OUT.

    Deliberately NOT inheriting `IsrPointBase`. The bounds there are input
    validation — "the engine will not accept this" — and applying them to a
    response makes the API unable to report what the database actually holds.
    A row written before a bound narrowed, or by a migration default, would
    fail serialisation and 500 on read: the endpoint would refuse to tell you
    about the very row you need to fix. Reading is not the place to relitigate
    whether a value should have been allowed in.
    """
    id: uuid.UUID
    name: str

    injection_rate_m3_day: Optional[float] = None
    bleed_percent: Optional[float] = None
    operation_years: Optional[float] = None
    restoration_years: Optional[float] = None
    wellfield_width_m: Optional[float] = None
    monitor_ring_m: Optional[float] = None
    ore_depth_m: Optional[float] = None
    ore_thickness_m: Optional[float] = None
    regime_override: Optional[str] = None
    gradient_i: Optional[float] = None
    azimuth_deg: Optional[float] = None
    injection_start_date: Optional[datetime] = None
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

