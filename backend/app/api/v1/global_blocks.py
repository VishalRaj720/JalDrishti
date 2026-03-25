"""Global Blocks router."""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.district import BlockResponse
from app.services.district import BlockService
from app.dependencies import require_any_role

router = APIRouter(prefix="/blocks", tags=["Blocks (Global)"])

@router.get("", response_model=List[BlockResponse])
async def list_global_blocks(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    """Retrieve blocks across all districts."""
    return await BlockService(db).list_all(skip=skip, limit=limit)
