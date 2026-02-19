"""ISR Point repository."""
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.isr_point import IsrPoint
from app.repositories.base import BaseRepository


class IsrPointRepository(BaseRepository[IsrPoint]):
    def __init__(self, db: AsyncSession):
        super().__init__(IsrPoint, db)
