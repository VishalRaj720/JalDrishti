"""Monitoring station and groundwater level reading service."""
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.monitoring_station import MonitoringStationRepository, GroundwaterReadingRepository
from app.repositories.district import BlockRepository
from app.models.monitoring_station import MonitoringStation, GroundwaterLevelReading
from app.schemas.monitoring_station import (
    MonitoringStationCreate,
    MonitoringStationUpdate,
    GroundwaterReadingCreate,
    MonitoringStationOverview,
)
from app.exceptions import ResourceNotFoundError


class MonitoringStationService:
    def __init__(self, db: AsyncSession):
        self.repo = MonitoringStationRepository(db)
        self.reading_repo = GroundwaterReadingRepository(db)
        self.block_repo = BlockRepository(db)

    async def create(self, block_id: uuid.UUID, data: MonitoringStationCreate) -> MonitoringStation:
        block = await self.block_repo.get(block_id)
        if not block:
            raise ResourceNotFoundError("Block", str(block_id))
        obj_in = data.model_dump()
        obj_in["block_id"] = block_id
        return await self.repo.create(obj_in)

    async def get(self, station_id: uuid.UUID) -> MonitoringStation:
        obj = await self.repo.get(station_id)
        if not obj:
            raise ResourceNotFoundError("MonitoringStation", str(station_id))
        return obj

    async def list_by_block(self, block_id: uuid.UUID) -> List[MonitoringStation]:
        """Return all stations for a block (readings auto-loaded via lazy='selectin')."""
        return await self.repo.get_by_block(block_id)

    async def update(self, station_id: uuid.UUID, data: MonitoringStationUpdate) -> MonitoringStation:
        obj = await self.repo.get(station_id)
        if not obj:
            raise ResourceNotFoundError("MonitoringStation", str(station_id))
        updates = data.model_dump(exclude_none=True)
        return await self.repo.update(obj, updates)

    async def delete(self, station_id: uuid.UUID) -> None:
        obj = await self.repo.get(station_id)
        if not obj:
            raise ResourceNotFoundError("MonitoringStation", str(station_id))
        await self.repo.delete(obj)

    async def add_reading(
        self, station_id: uuid.UUID, data: GroundwaterReadingCreate
    ) -> GroundwaterLevelReading:
        # Ensure the station exists
        station = await self.repo.get(station_id)
        if not station:
            raise ResourceNotFoundError("MonitoringStation", str(station_id))
        obj_in = data.model_dump()
        obj_in["station_id"] = station_id
        return await self.reading_repo.create(obj_in)

    async def list_readings(
        self, station_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[GroundwaterLevelReading]:
        station = await self.repo.get(station_id)
        if not station:
            raise ResourceNotFoundError("MonitoringStation", str(station_id))
        return await self.reading_repo.get_by_station(station_id, skip=skip, limit=limit)

    async def get_station_overviews(self, block_id: uuid.UUID) -> List[MonitoringStationOverview]:
        """Return slim overview dicts for all stations in a block (used to embed in BlockDetailResponse)."""
        stations = await self.repo.get_by_block(block_id)
        overviews = []
        for station in stations:
            count = await self.reading_repo.count_by_station(station.id)
            latest = await self.reading_repo.get_latest(station.id)
            overviews.append(
                MonitoringStationOverview(
                    id=station.id,
                    name=station.name,
                    village=station.village,
                    latitude=station.latitude,
                    longitude=station.longitude,
                    well_depth=station.well_depth,
                    reading_count=count,
                    latest_groundwater_level=latest.groundwater_level if latest else None,
                    latest_recorded_at=latest.recorded_at if latest else None,
                )
            )
        return overviews
