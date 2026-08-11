"""Simulation service — registry and retrieval of simulation runs.

P0 (2026-08-11): THE FABRICATED PHYSICS PATH WAS DELETED FROM THIS MODULE.

What used to be here was a 9-step `run()` that produced numbers no one should
have trusted, and that contradicted `ml_pipeline/` — the engine this project
actually validated. Specifically:

  * the groundwater flow direction was `random.uniform(30, 90)`, so two runs of
    the same site returned different plumes;
  * `affected_area` was `pi * (50*sqrt(365)/1000) * (10*sqrt(365)/1000)`, which
    is the constant **0.5733 km2** for every site, every injection rate, every
    aquifer — it did not even read the plume geometry computed two steps above;
  * the concentration time series was the peak scaled by the literal sequence
    [1.0, 0.8, 0.6, 0.4, 0.2];
  * "uncertainty" was the standard deviation of Gaussian noise applied to that
    peak, which measures the noise generator, not the model;
  * remediation advice ("enhanced bioremediation with electron donor
    injection") was emitted from three uncited porosity thresholds;
  * the whole thing called `ml_prediction.predict_for_simulation`, which
    labelled its own output `month1_placeholder`.

`ml_pipeline/` derives the gradient from a plane fit over real CGWB stations
and solves Domenico transport with conformal bands, and it is covered by 307
tests. Two endpoints in one product returning different answers for the same
site is a correctness bug, not a migration detail, so the weaker path is gone
rather than deprecated. See PRODUCT_DESIGN.md section 1.3.

`POST /simulations/{isr_id}` therefore returns 501 until P3 wires this service
to `ml_pipeline`. The read paths below are real and stay: they serve rows that
a future, honest engine will write.
"""
import uuid
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.simulation import SimulationRepository
from app.repositories.isr_point import IsrPointRepository
from app.models.simulation import Simulation
from app.exceptions import ResourceNotFoundError


class SimulationService:
    def __init__(self, db: AsyncSession):
        self.sim_repo = SimulationRepository(db)
        self.isr_repo = IsrPointRepository(db)
        self.db = db

    async def assert_isr_exists(self, isr_point_id: uuid.UUID) -> None:
        """Validate the ISR point before the router reports 501.

        Kept separate from `create_pending` so the API can still answer 404 for
        an unknown site without first writing a row it can never complete.
        """
        if not await self.isr_repo.get(isr_point_id):
            raise ResourceNotFoundError("ISR Point", str(isr_point_id))

    async def create_pending(self, isr_point_id: uuid.UUID) -> Simulation:
        await self.assert_isr_exists(isr_point_id)
        return await self.sim_repo.create({
            "isr_point_id": isr_point_id,
            "status": "pending",
        })

    async def get(self, sim_id: uuid.UUID) -> Simulation:
        obj = await self.sim_repo.get(sim_id)
        if not obj:
            raise ResourceNotFoundError("Simulation", str(sim_id))
        return obj

    async def list_by_isr(self, isr_point_id: uuid.UUID) -> List[Simulation]:
        return await self.sim_repo.get_by_isr_point(isr_point_id)
