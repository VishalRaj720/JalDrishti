"""District and Block services."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.district import DistrictRepository, BlockRepository
from app.models.district import District
from app.models.block import Block
from app.schemas.district import DistrictCreate, DistrictUpdate, BlockCreate, BlockUpdate
from app.exceptions import DuplicateResourceError, ResourceNotFoundError


class DistrictService:
    def __init__(self, db: AsyncSession):
        self.repo = DistrictRepository(db)

    async def create(self, data: DistrictCreate) -> District:
        if await self.repo.get_by_name(data.name):
            raise DuplicateResourceError("District", "name", data.name)
        obj_in = data.model_dump(exclude_none=True)
        # Fix for Swagger UI sending "string" as default value for geometry
        if obj_in.get("geometry") == "string":
            del obj_in["geometry"]
        return await self.repo.create(obj_in)

    async def get(self, district_id: uuid.UUID) -> District:
        obj = await self.repo.get(district_id)
        if not obj:
            raise ResourceNotFoundError("District", str(district_id))
        return obj

    async def list(self, skip: int = 0, limit: int = 100) -> List[District]:
        return await self.repo.get_all(skip=skip, limit=limit)

    async def update(self, district_id: uuid.UUID, data: DistrictUpdate) -> District:
        obj = await self.get(district_id)
        updates = data.model_dump(exclude_none=True)
        # Fix for Swagger UI sending "string" as default value for geometry
        if updates.get("geometry") == "string":
            del updates["geometry"]
        return await self.repo.update(obj, updates)

    async def delete(self, district_id: uuid.UUID) -> None:
        obj = await self.get(district_id)
        await self.repo.delete(obj)


class BlockService:
    def __init__(self, db: AsyncSession):
        self.repo = BlockRepository(db)

    async def create(self, data: BlockCreate) -> Block:
        existing = await self.repo.get_by_name_in_district(data.name, data.district_id)
        if existing:
            raise DuplicateResourceError("Block", "name in district", data.name)
        obj_in = data.model_dump(exclude_none=True)
        if obj_in.get("geometry") == "string":
            del obj_in["geometry"]
        return await self.repo.create(obj_in)

    async def get(self, block_id: uuid.UUID) -> Block:
        obj = await self.repo.get(block_id)
        if not obj:
            raise ResourceNotFoundError("Block", str(block_id))
        return obj

    async def list_by_district(self, district_id: uuid.UUID) -> List[Block]:
        return await self.repo.get_by_district(district_id)

    async def update(self, block_id: uuid.UUID, data: BlockUpdate) -> Block:
        obj = await self.get(block_id)
        updates = data.model_dump(exclude_none=True)
        if updates.get("geometry") == "string":
            del updates["geometry"]
        return await self.repo.update(obj, updates)

    async def delete(self, block_id: uuid.UUID) -> None:
        obj = await self.get(block_id)
        await self.repo.delete(obj)
