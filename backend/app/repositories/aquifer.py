"""Aquifer repository with spatial queries."""
import uuid
from typing import List, Optional
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.aquifer import Aquifer
from app.repositories.base import BaseRepository


class AquiferRepository(BaseRepository[Aquifer]):
    def __init__(self, db: AsyncSession):
        super().__init__(Aquifer, db)

    async def get_by_block(self, block_id: uuid.UUID) -> List[Aquifer]:
        result = await self.db.execute(
            select(Aquifer).where(Aquifer.block_id == block_id)
        )
        return list(result.scalars().all())

    async def get_within_radius(self, lat: float, lon: float, radius_km: float) -> List[Aquifer]:
        """Return aquifers whose geometry intersects a circle around the given point."""
        radius_m = radius_km * 1000
        stmt = text(
            """
            SELECT a.*
            FROM aquifers a
            WHERE ST_DWithin(
                a.geometry::geography,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius_m
            )
            """
        )
        result = await self.db.execute(stmt, {"lat": lat, "lon": lon, "radius_m": radius_m})
        return list(result.mappings().all())

    async def get_intersecting_plume(self, plume_wkt: str) -> List[Aquifer]:
        """Return aquifers intersecting a given plume geometry (WKT, SRID 4326)."""
        stmt = text(
            """
            SELECT *
            FROM aquifers
            WHERE ST_Intersects(
                geometry,
                ST_GeomFromText(:plume_wkt, 4326)
            )
            """
        )
        result = await self.db.execute(stmt, {"plume_wkt": plume_wkt})
        rows = result.mappings().all()
        # Convert raw rows to Aquifer objects via ORM re-query
        ids = [r["id"] for r in rows]
        if not ids:
            return []
        result2 = await self.db.execute(select(Aquifer).where(Aquifer.id.in_(ids)))
        return list(result2.scalars().all())
