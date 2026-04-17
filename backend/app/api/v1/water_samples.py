"""Water Samples router."""
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.water_sample import WaterSampleBulkCreate, WaterSampleResponse
from app.services.water_sample import WaterSampleService
from app.dependencies import require_analyst_or_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/water-samples", tags=["Water Samples"])


@router.get("", response_model=List[WaterSampleResponse])
async def list_water_samples(
    well_id: uuid.UUID = Query(..., description="Filter samples for this monitoring well"),
    from_dt: Optional[datetime] = Query(None, alias="from", description="sampled_at >= this ISO datetime"),
    to_dt: Optional[datetime] = Query(None, alias="to", description="sampled_at <= this ISO datetime"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """List water-quality samples for a well, newest first, optional date window."""
    try:
        return await WaterSampleService(db).list_by_well(
            well_id, from_dt=from_dt, to_dt=to_dt, skip=skip, limit=limit
        )
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/bulk", response_model=List[WaterSampleResponse], status_code=201)
async def bulk_create_water_samples(
    payload: WaterSampleBulkCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Insert multiple water-quality samples for a single well in one call."""
    try:
        return await WaterSampleService(db).bulk_create(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
