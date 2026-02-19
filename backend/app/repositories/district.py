"""District and Block repositories."""
from typing import List, Optional
import uuid
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.district import District
from app.models.block import Block
from app.repositories.base import BaseRepository


class DistrictRepository(BaseRepository[District]):
    def __init__(self, db: AsyncSession):
        super().__init__(District, db)

    async def get_by_name(self, name: str) -> Optional[District]:
        result = await self.db.execute(select(District).where(District.name == name))
        return result.scalar_one_or_none()


class BlockRepository(BaseRepository[Block]):
    def __init__(self, db: AsyncSession):
        super().__init__(Block, db)

    async def get_by_district(self, district_id: uuid.UUID) -> List[Block]:
        result = await self.db.execute(
            select(Block).where(Block.district_id == district_id)
        )
        return list(result.scalars().all())

    async def get_by_name_in_district(self, name: str, district_id: uuid.UUID) -> Optional[Block]:
        result = await self.db.execute(
            select(Block).where(Block.name == name, Block.district_id == district_id)
        )
        return result.scalar_one_or_none()
