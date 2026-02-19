"""Celery aggregation task."""
import asyncio
from loguru import logger
from app.celery_app import celery_app


@celery_app.task(name="tasks.refresh_aggregates")
def refresh_aggregates_task() -> dict:
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.aggregation import AggregationService
        async with AsyncSessionLocal() as db:
            svc = AggregationService(db)
            await svc.refresh_district_aggregates()
            await svc.refresh_block_aggregates()
    asyncio.run(_run())
    logger.info("Aggregates refreshed via Celery task.")
    return {"status": "ok"}
