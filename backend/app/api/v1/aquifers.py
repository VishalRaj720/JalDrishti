"""Aquifers router with spatial query support."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.aquifer import AquiferCreate, AquiferUpdate, AquiferResponse
from app.services.aquifer import AquiferService
from app.dependencies import require_analyst_or_admin, require_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/aquifers", tags=["Aquifers"])


@router.get("", response_model=List[AquiferResponse])
async def list_aquifers(
    skip: int = 0,
    limit: int = 100,
    block_id: Optional[uuid.UUID] = Query(None),
    lat: Optional[float] = Query(None, description="Latitude for spatial filter"),
    lon: Optional[float] = Query(None, description="Longitude for spatial filter"),
    radius_km: float = Query(10.0, description="Radius in km for spatial filter"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    svc = AquiferService(db)
    if lat is not None and lon is not None:
        return await svc.list_within_radius(lat, lon, radius_km)
    if block_id:
        return await svc.list_by_block(block_id)
    return await svc.list(skip=skip, limit=limit)


@router.get("/{aquifer_id}", response_model=AquiferResponse)
async def get_aquifer(
    aquifer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await AquiferService(db).get(aquifer_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=AquiferResponse, status_code=201)
async def create_aquifer(
    payload: AquiferCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await AquiferService(db).create(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DEBUG ERROR: {str(e)}")


@router.put("/{aquifer_id}", response_model=AquiferResponse)
async def update_aquifer(
    aquifer_id: uuid.UUID,
    payload: AquiferUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await AquiferService(db).update(aquifer_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{aquifer_id}", status_code=204)
async def delete_aquifer(
    aquifer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        await AquiferService(db).delete(aquifer_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
