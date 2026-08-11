"""Blocks router (nested under districts)."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.district import BlockCreate, BlockUpdate, BlockResponse, BlockDetailResponse
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


@router.get("/{block_id}", response_model=BlockDetailResponse)
async def get_block(
    district_id: uuid.UUID,
    block_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """Get a single block with an overview of all linked monitoring stations."""
    try:
        return await BlockService(db).get_detail(block_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# ── Reference geography is READ-ONLY ────────────────────────────────
# P2 (PRODUCT_DESIGN.md section 3.1) deleted POST / PUT / DELETE here.
# Blocks come from CGWB/GSI and are not user-editable content: editing them
# through an ad-hoc CRUD endpoint silently forks the scientific basis of every
# simulation that has already run against them, with no version record.
# The supported path is versioned bulk ingest -- POST /api/v1/ingest/* --
# which checksums the source file and writes a `data_sources` row linked to a
# `dataset_versions` entry.
