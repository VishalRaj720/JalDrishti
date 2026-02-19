"""Blocks router (nested under districts)."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.district import BlockCreate, BlockUpdate, BlockResponse
from app.services.district import BlockService
from app.dependencies import require_analyst_or_admin, require_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/districts/{district_id}/blocks", tags=["Blocks"])


@router.get("", response_model=List[BlockResponse])
async def list_blocks(
    district_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await BlockService(db).list_by_district(district_id)


@router.get("/{block_id}", response_model=BlockResponse)
async def get_block(
    district_id: uuid.UUID,
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await BlockService(db).get(block_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=BlockResponse, status_code=201)
async def create_block(
    district_id: uuid.UUID,
    payload: BlockCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        payload.district_id = district_id
        return await BlockService(db).create(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/{block_id}", response_model=BlockResponse)
async def update_block(
    district_id: uuid.UUID,
    block_id: uuid.UUID,
    payload: BlockUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await BlockService(db).update(block_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{block_id}", status_code=204)
async def delete_block(
    district_id: uuid.UUID,
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        await BlockService(db).delete(block_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
