"""Monitoring station and groundwater level reading repositories."""
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.monitoring_station import MonitoringStation, GroundwaterLevelReading
from app.repositories.base import BaseRepository


class MonitoringStationRepository(BaseRepository[MonitoringStation]):
    def __init__(self, db: AsyncSession):
        super().__init__(MonitoringStation, db)

    # Override get() to always eagerly load groundwater_readings
    async def get(self, id: uuid.UUID) -> Optional[MonitoringStation]:
        result = await self.db.execute(
            select(MonitoringStation)
            .where(MonitoringStation.id == id)
            .options(selectinload(MonitoringStation.groundwater_readings))
        )
        return result.scalar_one_or_none()

    # Override create() — flush+refresh writes the row, then re-SELECT with
    # selectinload to populate groundwater_readings without any lazy IO
    async def create(self, obj_in: Dict[str, Any]) -> MonitoringStation:
        obj = MonitoringStation(**obj_in)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        station_id = obj.id
        # Expunge so the identity map doesn't return this stale instance on re-SELECT
        self.db.expunge(obj)
        # Fresh SELECT with explicit eager load — always safe in async context
        result = await self.db.execute(
            select(MonitoringStation)
            .where(MonitoringStation.id == station_id)
            .options(selectinload(MonitoringStation.groundwater_readings))
        )
        return result.scalar_one()

    # Override update() to reload with readings after update
    async def update(self, obj: MonitoringStation, updates: Dict[str, Any]) -> MonitoringStation:
        for key, value in updates.items():
            setattr(obj, key, value)
        await self.db.flush()
        # Re-fetch with selectinload so readings are available
        return await self.get(obj.id)

    async def get_by_block(self, block_id: uuid.UUID) -> List[MonitoringStation]:
        result = await self.db.execute(
            select(MonitoringStation)
            .where(MonitoringStation.block_id == block_id)
            .options(selectinload(MonitoringStation.groundwater_readings))
        )
        return list(result.scalars().all())



class GroundwaterReadingRepository(BaseRepository[GroundwaterLevelReading]):
    def __init__(self, db: AsyncSession):
        super().__init__(GroundwaterLevelReading, db)

    async def get_by_station(
        self, station_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[GroundwaterLevelReading]:
        result = await self.db.execute(
            select(GroundwaterLevelReading)
            .where(GroundwaterLevelReading.station_id == station_id)
            .order_by(GroundwaterLevelReading.recorded_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest(self, station_id: uuid.UUID) -> Optional[GroundwaterLevelReading]:
        result = await self.db.execute(
            select(GroundwaterLevelReading)
            .where(GroundwaterLevelReading.station_id == station_id)
            .order_by(desc(GroundwaterLevelReading.recorded_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def count_by_station(self, station_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(GroundwaterLevelReading).where(
                GroundwaterLevelReading.station_id == station_id
            )
        )
        return result.scalar_one()

