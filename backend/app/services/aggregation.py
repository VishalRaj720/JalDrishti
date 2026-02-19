"""Aggregation service: refreshes materialized views and updates district/block aggregates."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from loguru import logger


class AggregationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def refresh_district_aggregates(self) -> None:
        """Refresh district materialized view if present, else compute inline."""
        try:
            await self.db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY district_aggregates"))
            logger.info("Refreshed district_aggregates materialized view.")
        except Exception:
            # View may not exist yet; compute inline update
            await self.db.execute(text("""
                UPDATE districts d
                SET
                    avg_porosity = sub.avg_porosity,
                    avg_hydraulic_conductivity = sub.avg_hc
                FROM (
                    SELECT
                        b.district_id,
                        AVG(a.porosity) AS avg_porosity,
                        AVG(a.hydraulic_conductivity) AS avg_hc
                    FROM aquifers a
                    JOIN blocks b ON a.block_id = b.id
                    GROUP BY b.district_id
                ) sub
                WHERE d.id = sub.district_id
            """))
            logger.info("Updated district aggregates inline (no materialized view).")

    async def refresh_block_aggregates(self) -> None:
        try:
            await self.db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY block_aggregates"))
            logger.info("Refreshed block_aggregates materialized view.")
        except Exception:
            await self.db.execute(text("""
                UPDATE blocks b
                SET
                    avg_porosity = sub.avg_porosity,
                    avg_permeability = sub.avg_perm
                FROM (
                    SELECT
                        block_id,
                        AVG(porosity) AS avg_porosity,
                        AVG(hydraulic_conductivity) AS avg_perm
                    FROM aquifers
                    GROUP BY block_id
                ) sub
                WHERE b.id = sub.block_id
            """))
            logger.info("Updated block aggregates inline (no materialized view).")
