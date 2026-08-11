"""Execute and persist ml_pipeline runs.

P3. The run is created `queued`, executed in a background task (a prediction
takes ~6 s, too long to hold a request open), and lands `completed` or `failed`
— never partially written and never with a fabricated number, which is what P0
removed.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ResourceNotFoundError
from app.models.isr_point import IsrPoint
from app.models.simulation_run import SimulationRun
from app.models.user import User
from app.services import audit, ml_pipeline_adapter as mlp


class SimulationRunService:
    """
    A NOTE ON `SET LOCAL` AND COMMITS, because it bit this service hard.

    `set_rls_context` uses `SET LOCAL` so a pooled connection cannot leak one
    request's identity into the next. The cost is that **COMMIT discards it**.
    `execute()` commits mid-operation (to publish `running` before a ~6 s
    prediction), so every statement after that first commit ran with no role and
    no bypass — the `sim_runs_write` policy then matched zero rows and
    SQLAlchemy raised `StaleDataError: expected to update 1 row(s); 0 were
    matched`. The run sat at `running` forever.

    Every commit here is therefore followed by re-establishing the context.
    The test suite cannot catch this: it connects as `postgres`, which bypasses
    RLS, so the missing context is invisible there.
    """

    def __init__(self, db: AsyncSession, *, system: bool = False):
        self.db = db
        self._system = system

    async def _commit(self) -> None:
        """Commit, then restore the RLS context the commit just dropped."""
        await self.db.commit()
        if self._system:
            from app.database import set_rls_context
            await set_rls_context(self.db, bypass=True)

    async def _isr(self, isr_id: uuid.UUID) -> IsrPoint:
        obj = (await self.db.execute(
            select(IsrPoint).where(IsrPoint.id == isr_id))).scalar_one_or_none()
        if obj is None:
            raise ResourceNotFoundError("ISR Point", str(isr_id))
        return obj

    async def _lonlat(self, isr_id: uuid.UUID) -> tuple[float, float]:
        row = (await self.db.execute(text(
            "SELECT ST_X(location::geometry) AS lon, "
            "       ST_Y(location::geometry) AS lat "
            "FROM isr_points WHERE id = :i"), {"i": str(isr_id)})).first()
        if row is None or row.lon is None:
            raise ResourceNotFoundError("ISR Point location", str(isr_id))
        return float(row.lon), float(row.lat)

    async def create(self, *, actor: User, isr_id: uuid.UUID,
                     params: dict[str, Any], ip: Optional[str] = None
                     ) -> SimulationRun:
        await self._isr(isr_id)
        run = SimulationRun(
            isr_point_id=isr_id,
            status="queued",
            engine="both",
            species=params.get("species") or "uranium_ppb",
            request=dict(params),
            created_by=actor.id,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.commit()
        await audit.record(
            action="simulation.queue", entity_type="simulation_runs",
            entity_id=str(run.id), actor_id=actor.id, actor_label=actor.email,
            ip_address=ip, detail={"isr_point_id": str(isr_id), "params": params},
        )
        return run

    async def get(self, run_id: uuid.UUID) -> SimulationRun:
        obj = (await self.db.execute(
            select(SimulationRun).where(SimulationRun.id == run_id)
        )).scalar_one_or_none()
        if obj is None:
            raise ResourceNotFoundError("SimulationRun", str(run_id))
        return obj

    async def list_for_isr(self, isr_id: uuid.UUID, limit: int = 50
                           ) -> list[SimulationRun]:
        res = await self.db.execute(
            select(SimulationRun).where(SimulationRun.isr_point_id == isr_id)
            .order_by(SimulationRun.created_at.desc()).limit(limit))
        return list(res.scalars().all())

    async def execute(self, run_id: uuid.UUID) -> None:
        """Run the engine and record the outcome. Never raises to the caller."""
        run = await self.get(run_id)
        if run.status != "queued":
            logger.info(f"run {run_id} is '{run.status}', not executing again")
            return

        lon, lat = await self._lonlat(run.isr_point_id)
        run.status = "running"
        await self._commit()

        started = time.perf_counter()
        try:
            # Only the pin and the sliders cross the boundary. No database
            # chemistry, no approved field observation — see the adapter's
            # docstring for why that is a hard rule and not a preference.
            payload = mlp.build_payload(lon=lon, lat=lat, params=run.request)
            result = await mlp.predict(payload)
            prov = mlp.provenance()

            run.inputs = result.get("hydro", {}).get("inputs") or payload
            run.metrics = result.get("metrics")
            run.excursion = result.get("isr_excursion")
            run.extrapolation = list(result.get("extrapolation") or [])
            run.hydro = result.get("hydro")
            run.model_card_sha = prov["model_card_sha"]
            run.artifacts_sha = prov["artifacts_sha"]
            run.code_version = prov["code_version"]
            run.status = "completed"
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {exc}"
            logger.exception(f"simulation run {run_id} failed")
        finally:
            run.runtime_ms = int((time.perf_counter() - started) * 1000)
            run.completed_at = datetime.now(timezone.utc)
            await self._commit()

        await audit.record(
            action=f"simulation.{run.status}", entity_type="simulation_runs",
            entity_id=str(run.id), actor_id=run.created_by,
            detail={"status": run.status, "runtime_ms": run.runtime_ms,
                    "model_card_sha": run.model_card_sha,
                    "code_version": run.code_version,
                    "extrapolation": run.extrapolation,
                    "error": run.error_message},
        )
