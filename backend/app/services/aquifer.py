"""Aquifer service with spatial query support."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.aquifer import AquiferRepository
from app.models.aquifer import Aquifer
from app.models.block import Block
from app.schemas.aquifer import AquiferCreate, AquiferUpdate
from app.exceptions import ResourceNotFoundError, InsufficientDataError
from sqlalchemy import select


class AquiferService:
    def __init__(self, db: AsyncSession):
        self.repo = AquiferRepository(db)

    async def create(self, data: AquiferCreate) -> Aquifer:
        obj_in = data.model_dump(exclude_none=True)
        # Compute thickness if depth ranges are provided
        if obj_in.get("min_depth") is not None and obj_in.get("max_depth") is not None:
            obj_in["thickness"] = obj_in["max_depth"] - obj_in["min_depth"]
        # Fix for Swagger UI sending "string" as default value for geometry
        if obj_in.get("geometry") == "string":
            del obj_in["geometry"]
        
        # Check if block_id exists if provided
        if obj_in.get("block_id"):
             result = await self.repo.db.execute(select(Block.id).where(Block.id == obj_in["block_id"]))
             if not result.scalar_one_or_none():
                 raise ResourceNotFoundError("Block", str(obj_in["block_id"]))

        return await self.repo.create(obj_in)

    async def get(self, aquifer_id: uuid.UUID) -> Aquifer:
        obj = await self.repo.get(aquifer_id)
        if not obj:
            raise ResourceNotFoundError("Aquifer", str(aquifer_id))
        return obj

    async def list(self, skip: int = 0, limit: int = 100) -> List[Aquifer]:
        return await self.repo.get_all(skip=skip, limit=limit)

    async def list_by_block(self, block_id: uuid.UUID) -> List[Aquifer]:
        return await self.repo.get_by_block(block_id)

    async def list_within_radius(
        self, lat: float, lon: float, radius_km: float
    ) -> List[Aquifer]:
        return await self.repo.get_within_radius(lat, lon, radius_km)

    async def update(self, aquifer_id: uuid.UUID, data: AquiferUpdate) -> Aquifer:
        obj = await self.get(aquifer_id)
        updates = data.model_dump(exclude_none=True)
        min_d = updates.get("min_depth", obj.min_depth)
        max_d = updates.get("max_depth", obj.max_depth)
        if min_d is not None and max_d is not None:
            updates["thickness"] = max_d - min_d
        # Fix for Swagger UI sending "string" as default value for geometry
        if updates.get("geometry") == "string":
            del updates["geometry"]
        
        if updates.get("block_id"):
             result = await self.repo.db.execute(select(Block.id).where(Block.id == updates["block_id"]))
             if not result.scalar_one_or_none():
                 raise ResourceNotFoundError("Block", str(updates["block_id"]))

        return await self.repo.update(obj, updates)

    async def delete(self, aquifer_id: uuid.UUID) -> None:
        obj = await self.get(aquifer_id)
        await self.repo.delete(obj)

    async def validate_for_simulation(self, aquifer: Aquifer) -> None:
        """Raise InsufficientDataError if critical fields are missing."""
        if aquifer.porosity is None:
            raise InsufficientDataError("porosity", str(aquifer.id), ">20%")
        if aquifer.hydraulic_conductivity is None:
            raise InsufficientDataError("hydraulic_conductivity", str(aquifer.id), ">15%")
