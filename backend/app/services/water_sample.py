"""WaterSample service."""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.water_sample import WaterSample
from app.repositories.water_sample import WaterSampleRepository
from app.repositories.monitoring_well import MonitoringWellRepository
from app.schemas.water_sample import WaterSampleBulkCreate
from app.exceptions import ResourceNotFoundError


class WaterSampleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WaterSampleRepository(db)
        self.well_repo = MonitoringWellRepository(db)

    async def list_by_well(
        self,
        well_id: uuid.UUID,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WaterSample]:
        well = await self.well_repo.get(well_id)
        if not well:
            raise ResourceNotFoundError("MonitoringWell", str(well_id))
        return await self.repo.list_by_well(
            well_id, from_dt=from_dt, to_dt=to_dt, skip=skip, limit=limit
        )

    async def bulk_create(self, payload: WaterSampleBulkCreate) -> List[WaterSample]:
        well = await self.well_repo.get(payload.well_id)
        if not well:
            raise ResourceNotFoundError("MonitoringWell", str(payload.well_id))
        created: List[WaterSample] = []
        for s in payload.samples:
            obj = WaterSample(well_id=payload.well_id, **s.model_dump())
            self.db.add(obj)
            created.append(obj)
        await self.db.flush()
        for obj in created:
            await self.db.refresh(obj)
        return created
