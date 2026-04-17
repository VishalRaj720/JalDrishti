"""MonitoringWell service."""
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.monitoring_well import MonitoringWell
from app.repositories.monitoring_well import MonitoringWellRepository
from app.schemas.monitoring_well import MonitoringWellCreate
from app.exceptions import ResourceNotFoundError, DuplicateResourceError


class MonitoringWellService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MonitoringWellRepository(db)

    async def get(self, well_id: uuid.UUID) -> MonitoringWell:
        obj = await self.repo.get(well_id)
        if not obj:
            raise ResourceNotFoundError("MonitoringWell", str(well_id))
        return obj

    async def list_in_bbox(
        self, min_lon: float, min_lat: float, max_lon: float, max_lat: float, limit: int = 1000
    ) -> List[MonitoringWell]:
        return await self.repo.list_in_bbox(min_lon, min_lat, max_lon, max_lat, limit=limit)

    async def create(self, data: MonitoringWellCreate) -> MonitoringWell:
        existing = await self.repo.get_by_lat_lon(data.latitude, data.longitude)
        if existing:
            raise DuplicateResourceError(
                "MonitoringWell", "latitude,longitude", f"{data.latitude},{data.longitude}"
            )
        obj = MonitoringWell(
            name=data.name,
            latitude=data.latitude,
            longitude=data.longitude,
            depth=data.depth,
            well_type=data.well_type,
            block_id=data.block_id,
            paired_station_id=data.paired_station_id,
            # EWKT — geoalchemy2 parses this directly
            location=f"SRID=4326;POINT({data.longitude} {data.latitude})",
        )
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj
