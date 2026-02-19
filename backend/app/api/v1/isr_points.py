"""ISR Points router."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.simulation import IsrPointCreate, IsrPointUpdate, IsrPointResponse, SimulationResponse
from app.services.isr_point import IsrPointService
from app.services.simulation import SimulationService
from app.dependencies import require_analyst_or_admin, require_admin, require_any_role
from app.exceptions import AppException
from app.schemas.common import JobResponse

router = APIRouter(prefix="/isr-points", tags=["ISR Points"])


@router.get("", response_model=List[IsrPointResponse])
async def list_isr_points(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await IsrPointService(db).list(skip=skip, limit=limit)


@router.get("/{isr_id}", response_model=IsrPointResponse)
async def get_isr_point(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await IsrPointService(db).get(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=IsrPointResponse, status_code=201)
async def create_isr_point(
    payload: IsrPointCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await IsrPointService(db).create(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{isr_id}", response_model=IsrPointResponse)
async def update_isr_point(
    isr_id: uuid.UUID,
    payload: IsrPointUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await IsrPointService(db).update(isr_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{isr_id}", status_code=204)
async def delete_isr_point(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        await IsrPointService(db).delete(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/{isr_id}/simulations", response_model=List[SimulationResponse])
async def list_simulations_for_isr(
    isr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await SimulationService(db).list_by_isr(isr_id)
