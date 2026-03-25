"""Global Monitoring Stations router."""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.monitoring_station import MonitoringStationResponse
from app.services.monitoring_station import MonitoringStationService
from app.dependencies import require_any_role

router = APIRouter(prefix="/monitoring-stations", tags=["Monitoring (Global)"])

@router.get("", response_model=List[MonitoringStationResponse])
async def list_global_stations(
    skip: int = 0,
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """Retrieve all monitoring stations across all blocks."""
    return await MonitoringStationService(db).repo.get_all(skip=skip, limit=limit)

@router.get("/count", response_model=int)
async def count_global_stations(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """Retrieve total count of all monitoring stations."""
    from sqlalchemy import select, func
    from app.models.monitoring_station import MonitoringStation
    result = await db.execute(select(func.count()).select_from(MonitoringStation))
    return result.scalar_one()
