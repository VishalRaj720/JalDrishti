"""
Celery simulation task.
Runs inside the Celery worker process (sync wrapper around async code).
"""
import uuid
import asyncio
from loguru import logger
from app.celery_app import celery_app


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="tasks.run_simulation",
)
def run_simulation_task(self, simulation_id: str) -> dict:
    """Celery task: execute simulation workflow asynchronously."""
    logger.info(f"Celery task started for simulation {simulation_id}")

    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.simulation import SimulationService
        from app.services.aggregation import AggregationService

        async with AsyncSessionLocal() as db:
            sim_service = SimulationService(db)
            sim = await sim_service.run(uuid.UUID(simulation_id))

            # Refresh aggregates after simulation
            agg_service = AggregationService(db)
            await agg_service.refresh_district_aggregates()
            await agg_service.refresh_block_aggregates()

            return {
                "simulation_id": str(sim.id),
                "status": sim.status,
                "affected_area": sim.affected_area,
            }

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Simulation task failed: {exc}")
        raise self.retry(exc=exc)
