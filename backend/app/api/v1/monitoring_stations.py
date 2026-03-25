"""Monitoring stations router (nested under blocks)."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.monitoring_station import (
    MonitoringStationCreate,
    MonitoringStationUpdate,
    MonitoringStationResponse,
    GroundwaterReadingCreate,
    GroundwaterReadingResponse,
)
from app.services.monitoring_station import MonitoringStationService
from app.dependencies import require_analyst_or_admin, require_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/blocks/{block_id}/monitoring-stations", tags=["Monitoring Stations"])


@router.get("", response_model=List[MonitoringStationResponse])
async def list_monitoring_stations(
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """List all monitoring stations for a given block (each includes its groundwater readings)."""
    return await MonitoringStationService(db).list_by_block(block_id)


@router.post("", response_model=MonitoringStationResponse, status_code=201)
async def create_monitoring_station(
    block_id: uuid.UUID,
    payload: MonitoringStationCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Create a new monitoring station linked to a block."""
    try:
        return await MonitoringStationService(db).create(block_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/{station_id}", response_model=MonitoringStationResponse)
async def get_monitoring_station(
    block_id: uuid.UUID,
    station_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """Get a single monitoring station with all groundwater level readings."""
    try:
        return await MonitoringStationService(db).get(station_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{station_id}", response_model=MonitoringStationResponse)
async def update_monitoring_station(
    block_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: MonitoringStationUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Update a monitoring station's metadata."""
    try:
        return await MonitoringStationService(db).update(station_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{station_id}", status_code=204)
async def delete_monitoring_station(
    block_id: uuid.UUID,
    station_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Delete a monitoring station and all its readings."""
    try:
        await MonitoringStationService(db).delete(station_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ── Groundwater Level Readings ────────────────────────────────────────────────

@router.post("/{station_id}/readings", response_model=GroundwaterReadingResponse, status_code=201)
async def add_groundwater_reading(
    block_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: GroundwaterReadingCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Add a new groundwater level reading (time series data point) to a station."""
    try:
        return await MonitoringStationService(db).add_reading(station_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/{station_id}/readings", response_model=List[GroundwaterReadingResponse])
async def list_groundwater_readings(
    block_id: uuid.UUID,
    station_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """List groundwater level readings for a station (newest first, paginated)."""
    try:
        return await MonitoringStationService(db).list_readings(station_id, skip=skip, limit=limit)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
