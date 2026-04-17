"""Monitoring Wells router (water-quality sampling points)."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.monitoring_well import MonitoringWellCreate, MonitoringWellResponse
from app.services.monitoring_well import MonitoringWellService
from app.dependencies import require_analyst_or_admin, require_any_role
from app.exceptions import AppException
from app.cache import cache_get, cache_set, cache_invalidate_pattern

router = APIRouter(prefix="/monitoring-wells", tags=["Monitoring Wells"])

# Cache config — ONLY used by the bbox list endpoint
_BBOX_CACHE_TTL = 1800  # 30 minutes
_BBOX_CACHE_PREFIX = "wells:bbox:"


def _parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'min_lon,min_lat,max_lon,max_lat' → tuple of floats."""
    try:
        parts = [float(x) for x in bbox.split(",")]
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox must be 4 comma-separated floats")
    if len(parts) != 4:
        raise HTTPException(status_code=422, detail="bbox must have exactly 4 values")
    min_lon, min_lat, max_lon, max_lat = parts
    if min_lon > max_lon or min_lat > max_lat:
        raise HTTPException(status_code=422, detail="bbox min must be <= max")
    return min_lon, min_lat, max_lon, max_lat


def _bbox_cache_key(min_lon: float, min_lat: float, max_lon: float, max_lat: float, limit: int) -> str:
    # Round to 4 dp (~11m) to prevent key explosion from tiny float differences.
    return (
        f"{_BBOX_CACHE_PREFIX}"
        f"{round(min_lon,4)},{round(min_lat,4)},{round(max_lon,4)},{round(max_lat,4)}:{limit}"
    )


@router.get("", response_model=List[MonitoringWellResponse])
async def list_monitoring_wells(
    bbox: str = Query(..., description="min_lon,min_lat,max_lon,max_lat (EPSG:4326)"),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """List wells inside a bounding box. Cached in Redis for 30 min."""
    min_lon, min_lat, max_lon, max_lat = _parse_bbox(bbox)
    key = _bbox_cache_key(min_lon, min_lat, max_lon, max_lat, limit)

    cached = await cache_get(key)
    if cached is not None:
        return cached

    wells = await MonitoringWellService(db).list_in_bbox(
        min_lon, min_lat, max_lon, max_lat, limit=limit
    )
    payload = [MonitoringWellResponse.model_validate(w).model_dump(mode="json") for w in wells]
    await cache_set(key, payload, ttl=_BBOX_CACHE_TTL)
    return payload


@router.get("/{well_id}", response_model=MonitoringWellResponse)
async def get_monitoring_well(
    well_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await MonitoringWellService(db).get(well_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=MonitoringWellResponse, status_code=201)
async def create_monitoring_well(
    payload: MonitoringWellCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        well = await MonitoringWellService(db).create(payload)
        # Invalidate bbox cache — any cached bbox may now be stale
        await cache_invalidate_pattern(f"{_BBOX_CACHE_PREFIX}*")
        return well
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
