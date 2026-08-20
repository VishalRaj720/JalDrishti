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
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ResourceNotFoundError
from app.models.isr_point import IsrPoint
from app.models.simulation_run import SimulationRun
from app.models.user import User
from app.services import audit, ml_pipeline_adapter as mlp


def _plume_geometry(result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Extract the drawable geometry from an engine response (migration 0016).

    Copied out rather than storing the whole response for two reasons. The
    response carries the metrics and excursion state that already have their own
    columns, and duplicating them invites two answers to one question when a
    later migration reshapes either. And it carries `hydro`, which is large and
    already stored.

    Returns None when the engine produced no drawable extent — a legitimate
    outcome, not a failure: outside an ore zone the uranium source term is
    refused entirely, and the honest render for that is the engine's own notice,
    never an empty polygon presented as a measurement of safety (§4.6 rule 3).
    """
    plume = result.get("plume") or {}
    contours = plume.get("contours") or []
    source = plume.get("source_zone") or {}
    ring = plume.get("compliance_ring") or {}
    envelope = result.get("ml_envelope")

    if not contours and not source.get("polygon") and not ring.get("polygon"):
        return None

    return {
        "contours": contours,
        "compliance_ring": ring,
        "source_zone": source,
        "ml_envelope": envelope,
        "ml_envelope_skipped": result.get("ml_envelope_skipped") or {},
        "azimuth_deg": result.get("azimuth_deg"),
        "azimuth_source": result.get("azimuth_source"),
        "peak_conc": plume.get("peak_conc"),
        "Xc_m": plume.get("Xc_m"),
        "aspect_ratio": plume.get("aspect_ratio"),
        "lambda_radial": plume.get("lambda_radial"),
        "radial_dominated": plume.get("radial_dominated"),
        "off_scale": plume.get("off_scale"),
        # Carried so a redraw can reproduce the caveats that were on screen when
        # the run was read, not just its shape.
        "notice": result.get("notice"),
        "far_field_note": result.get("far_field_note"),
        "ore_zone": result.get("ore_zone"),
        "timeline": result.get("timeline"),
        "restoration": result.get("restoration"),
        "containment": result.get("containment"),
        "species": result.get("species"),
        "threshold": result.get("threshold"),
        "ml_status": result.get("ml_status"),
    }


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

    async def _site(self, isr_id: uuid.UUID) -> IsrPoint:
        """The whole site, not just its coordinate.

        Since migration 0015 a site carries the operation it represents —
        injection rate, bleed, footprint, monitor ring, ore depth — so the run
        needs the row, not two floats. A site with no location cannot be run at
        all; that is the same error it always was, raised earlier.
        """
        site = (await self.db.execute(
            select(IsrPoint).where(IsrPoint.id == isr_id))).scalar_one_or_none()
        if site is None or site.location is None:
            raise ResourceNotFoundError("ISR Point location", str(isr_id))
        return site

    async def create(self, *, actor: User, isr_id: uuid.UUID,
                     params: dict[str, Any], ip: Optional[str] = None
                     ) -> SimulationRun:
        await self._isr(isr_id)
        # P2, second enforcement point. `RunRequest` already refuses anything
        # outside RUN_VARIABLE, and the scenario validator refuses it at save
        # time — but this service is also called by the scenario RUN path with a
        # dict that was validated under an older, wider rule. Rows saved before
        # that narrowing still exist, so filtering here is what stops a stored
        # scenario from overriding its site's operation on its next run.
        #
        # Silently dropping rather than raising: the caller is replaying a
        # scenario they saved legitimately under the old rule, and failing their
        # run helps nobody. What they get is the site's own operation, which is
        # the correct answer to "run this site".
        from app.services.ml_pipeline_adapter import RUN_VARIABLE
        params = {k: v for k, v in (params or {}).items() if k in RUN_VARIABLE}
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

        site = await self._site(run.isr_point_id)
        run.status = "running"
        await self._commit()

        started = time.perf_counter()
        try:
            # Only the pin, the site's own operating parameters and the two
            # Studio variables cross the boundary. No database chemistry, no
            # approved field observation — see the adapter's docstring for why
            # that is a hard rule and not a preference.
            #
            # The site supplies the operation; `run.request` carries what the
            # Studio varied (evaluation year, restoration years) and wins where
            # the two overlap, which is what makes "test a 5-year sweep against
            # this site" possible without editing the site.
            payload = mlp.payload_from_site(site, overrides=run.request or {})
            result = await mlp.predict(payload)
            prov = mlp.provenance()

            run.inputs = result.get("hydro", {}).get("inputs") or payload
            run.metrics = result.get("metrics")
            run.excursion = result.get("isr_excursion")
            run.extrapolation = list(result.get("extrapolation") or [])
            run.hydro = result.get("hydro")

            # R11: the shallow-aquifer screening was computed on every run and
            # then thrown away. It is returned at the top level of the engine
            # payload, not inside `hydro`, so assigning `hydro` alone dropped it
            # — and the breakthrough time a user reads on screen came from the
            # live preview and existed nowhere afterwards. A published advisory
            # that says a pathway to the drinking-water aquifer exists has to be
            # able to point at the run that said so.
            #
            # `hydro` is a JSON column, so this needs no migration. Runs stored
            # before this carry no `vertical` key, and readers must treat its
            # absence as "not recorded" rather than "no pathway".
            vertical = result.get("vertical")
            if vertical and isinstance(run.hydro, dict):
                run.hydro = {**run.hydro, "vertical": vertical}
            run.plume = _plume_geometry(result)
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


#: A run that has been `queued` or `running` for longer than this cannot still
#: be executing. Generous on purpose: the longest real run is seconds, and the
#: cost of being wrong in this direction is failing a live run, which is worse
#: than leaving a corpse for another half hour.
ORPHAN_AFTER_MINUTES = 30


async def reap_orphaned_runs(db: AsyncSession, *,
                             older_than_minutes: int = ORPHAN_AFTER_MINUTES
                             ) -> dict[str, Any]:
    """Fail runs left mid-flight by a restart.

    DEPLOYMENT AUDIT. Simulations execute as in-process FastAPI background
    tasks — there is no queue and no broker, which is the right size for this
    product but means a restart silently abandons whatever was in flight. The
    row stays `queued` for ever, the UI shows a spinner nobody can clear, and
    the audit found three real ones sitting from the previous day.

    WHY A TIME THRESHOLD RATHER THAN "everything at startup". Under
    `--workers N` each worker runs the startup hook, so a blanket sweep would
    have worker 2 failing the run worker 1 is executing right now. Thirty
    minutes is far longer than any real run and far shorter than a shift.

    Marking them `failed` rather than deleting them: somebody asked for that
    run and is entitled to see what became of it. The message says restart
    rather than leaving a bare "failed" to be read as an engine problem.
    """
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    res = await db.execute(
        sa_update(SimulationRun)
        .where(SimulationRun.status.in_(("queued", "running")),
               SimulationRun.created_at < cutoff)
        .values(status="failed",
                error_message=(
                    "Abandoned when the server restarted. Simulations run "
                    "in-process, so a restart ends anything in flight. Nothing "
                    "was written from this run — start it again."),
                completed_at=datetime.now(timezone.utc))
        .returning(SimulationRun.id))
    ids = [str(r[0]) for r in res.fetchall()]
    await db.commit()
    if ids:
        logger.warning(f"reaped {len(ids)} orphaned simulation run(s) older "
                       f"than {older_than_minutes}m: {ids[:5]}")
    return {"reaped": len(ids), "run_ids": ids,
            "older_than_minutes": older_than_minutes}
