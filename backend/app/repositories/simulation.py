"""Simulation repository."""
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.simulation import Simulation
from app.repositories.base import BaseRepository


class SimulationRepository(BaseRepository[Simulation]):
    def __init__(self, db: AsyncSession):
        super().__init__(Simulation, db)

    async def get_by_isr_point(self, isr_point_id: uuid.UUID) -> List[Simulation]:
        result = await self.db.execute(
            select(Simulation)
            .where(Simulation.isr_point_id == isr_point_id)
            .order_by(Simulation.simulation_date.desc())
        )
        return list(result.scalars().all())

    async def get_by_task_id(self, task_id: str) -> Optional[Simulation]:
        result = await self.db.execute(
            select(Simulation).where(Simulation.task_id == task_id)
        )
        return result.scalar_one_or_none()
