"""DataSource repository."""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.data_source import DataSource
from app.repositories.base import BaseRepository


class DataSourceRepository(BaseRepository[DataSource]):
    def __init__(self, db: AsyncSession):
        super().__init__(DataSource, db)

    async def get_by_name_checksum(self, name: str, checksum: Optional[str]) -> Optional[DataSource]:
        q = select(DataSource).where(DataSource.name == name)
        if checksum is not None:
            q = q.where(DataSource.checksum == checksum)
        result = await self.db.execute(q)
        return result.scalar_one_or_none()
