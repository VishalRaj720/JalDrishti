"""ISR Point service."""
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.isr_point import IsrPointRepository
from app.models.isr_point import IsrPoint
from app.schemas.simulation import IsrPointCreate, IsrPointUpdate
from app.exceptions import ResourceNotFoundError


class IsrPointService:
    def __init__(self, db: AsyncSession):
        self.repo = IsrPointRepository(db)

    async def create(self, data: IsrPointCreate) -> IsrPoint:
        obj_in = data.model_dump(exclude_none=True)
        # GeoJSON location → WKT for PostGIS
        if "location" in obj_in:
            loc = obj_in["location"]
            # Handle empty dict or incorrect structure
            if loc and isinstance(loc, dict) and loc.get("type") == "Point" and "coordinates" in loc:
                lon, lat = loc["coordinates"]
                obj_in["location"] = f"SRID=4326;POINT({lon} {lat})"
            else:
                # If invalid/empty location provided, remove it to avoid DB error or save as None if allowed
                del obj_in["location"]
        return await self.repo.create(obj_in)

    async def get(self, isr_id: uuid.UUID) -> IsrPoint:
        obj = await self.repo.get(isr_id)
        if not obj:
            raise ResourceNotFoundError("ISR Point", str(isr_id))
        return obj

    async def list(self, skip: int = 0, limit: int = 100) -> List[IsrPoint]:
        return await self.repo.get_all(skip=skip, limit=limit)

    async def update(self, isr_id: uuid.UUID, data: IsrPointUpdate) -> IsrPoint:
        obj = await self.get(isr_id)
        updates = data.model_dump(exclude_none=True)
        if "location" in updates:
            loc = updates["location"]
            if loc and isinstance(loc, dict) and loc.get("type") == "Point" and "coordinates" in loc:
                lon, lat = loc["coordinates"]
                updates["location"] = f"SRID=4326;POINT({lon} {lat})"
            else:
                 del updates["location"]
        return await self.repo.update(obj, updates)

    async def delete(self, isr_id: uuid.UUID) -> None:
        obj = await self.get(isr_id)
        await self.repo.delete(obj)
