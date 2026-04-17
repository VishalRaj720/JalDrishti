"""WaterSample repository."""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.water_sample import WaterSample
from app.repositories.base import BaseRepository


class WaterSampleRepository(BaseRepository[WaterSample]):
    def __init__(self, db: AsyncSession):
        super().__init__(WaterSample, db)

    async def list_by_well(
        self,
        well_id: uuid.UUID,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WaterSample]:
        """Return samples for a well, newest first, optionally bounded by sampled_at."""
        q = select(WaterSample).where(WaterSample.well_id == well_id)
        if from_dt is not None:
            q = q.where(WaterSample.sampled_at >= from_dt)
        if to_dt is not None:
            q = q.where(WaterSample.sampled_at <= to_dt)
        q = q.order_by(WaterSample.sampled_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())
