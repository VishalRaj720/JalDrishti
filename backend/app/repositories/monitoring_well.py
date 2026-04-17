"""MonitoringWell repository."""
from typing import List, Optional
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.monitoring_well import MonitoringWell
from app.repositories.base import BaseRepository


class MonitoringWellRepository(BaseRepository[MonitoringWell]):
    def __init__(self, db: AsyncSession):
        super().__init__(MonitoringWell, db)

    async def get_by_lat_lon(self, latitude: float, longitude: float) -> Optional[MonitoringWell]:
        result = await self.db.execute(
            select(MonitoringWell).where(
                MonitoringWell.latitude == latitude,
                MonitoringWell.longitude == longitude,
            )
        )
        return result.scalar_one_or_none()

    async def list_in_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
        limit: int = 1000,
    ) -> List[MonitoringWell]:
        """Return wells whose point falls within the bbox (EPSG:4326).
        Uses the GIST index on `location` via ST_MakeEnvelope intersection."""
        q = (
            select(MonitoringWell)
            .where(
                text(
                    "ST_Intersects(location, ST_MakeEnvelope(:min_lon, :min_lat, :max_lon, :max_lat, 4326))"
                )
            )
            .limit(limit)
        )
        result = await self.db.execute(
            q,
            {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat},
        )
        return list(result.scalars().all())
