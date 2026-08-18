"""Proposing, publishing and withdrawing public screening advisories.

THE HONEST-AREA PROBLEM, which is the whole reason this service exists rather
than a three-line CRUD router.

A verified run in the Singhbhum belt produces a footprint of about **12.9 ha**.
A Jharkhand administrative block is on the order of **30,000 ha**. If publishing
an advisory alerted "the block", the portal would be telling tens of thousands
of people that a 0.04 % sliver of their block had been screened — and every one
of them would reasonably read it as being about their own water.

So the affected area is computed by real spatial intersection against the
`blocks` table, and the result is reported exactly as it comes out. In practice
that is usually **the host block alone, and frequently nothing beyond it**. That
is a finding worth stating plainly, not a number to round up to something that
feels more significant.

`Datasets/` carries no village, settlement or population layer, so block is the
finest resolution available and the advisory says so rather than implying a
precision it does not have.

WHAT IS DELIBERATELY NOT DONE HERE: no advisory says an operation occurred. No
ISR uranium mine operates in Jharkhand. Every public string this module writes
describes an *assessment that has been published*, and `_PREMISE` is appended to
each one so the qualification cannot be lost by a caller who forgets it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppValidationError, ResourceNotFoundError
from app.models.advisory import Advisory
from app.models.simulation_run import SimulationRun
from app.models.user import User
from app.services import audit

#: Appended to every citizen-facing advisory body, at write time, so that a
#: caller cannot produce one without it and a later template change cannot
#: silently remove it from advisories a regulator already approved.
_PREMISE = (
    "This is a modelled assessment, not a report of something that has "
    "happened. No uranium in-situ recovery mine operates in Jharkhand. It "
    "shows what the model expects if an operation of this kind were run at "
    "this location."
)


class AdvisoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── reads ────────────────────────────────────────────────────────

    async def get(self, advisory_id: uuid.UUID) -> Advisory:
        obj = (await self.db.execute(
            select(Advisory).where(Advisory.id == advisory_id))).scalar_one_or_none()
        if obj is None:
            raise ResourceNotFoundError("Advisory", str(advisory_id))
        return obj

    async def list(self, *, status: Optional[str] = None,
                   isr_point_id: Optional[uuid.UUID] = None,
                   limit: int = 100) -> list[Advisory]:
        stmt = select(Advisory).order_by(Advisory.proposed_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Advisory.status == status)
        if isr_point_id:
            stmt = stmt.where(Advisory.isr_point_id == isr_point_id)
        return list((await self.db.execute(stmt)).scalars().all())

    # ── the footprint, and who it actually reaches ───────────────────

    @staticmethod
    def _footprint_wkt(run: SimulationRun) -> Optional[str]:
        """Build the affected extent from the run's stored plume geometry.

        WHICH RINGS COUNT. Only the contour at the **screening limit** (`is_bis`)
        and the leach zone. The lower contours are real model output but they lie
        *below* the limit — including them would publish an "affected area" that
        is largely ground the model says is within the safe threshold, which
        inflates the number in exactly the direction that causes alarm.

        Returns None when there is no extent. That is a legitimate outcome
        (outside an ore zone the engine refuses a uranium source term) and the
        advisory records it as such rather than as a missing value.
        """
        plume = run.plume or {}
        rings: list[str] = []

        def ring_to_wkt(poly: list[list[float]]) -> Optional[str]:
            if not poly or len(poly) < 3:
                return None
            pts = [(float(p[0]), float(p[1])) for p in poly]
            if pts[0] != pts[-1]:            # a polygon ring must close
                pts.append(pts[0])
            if len(pts) < 4:
                return None
            return "((" + ", ".join(f"{x} {y}" for x, y in pts) + "))"

        for contour in plume.get("contours") or []:
            if not contour.get("is_bis"):
                continue
            for poly in contour.get("polygons") or []:
                w = ring_to_wkt(poly)
                if w:
                    rings.append(w)

        source = (plume.get("source_zone") or {}).get("polygon")
        if source:
            w = ring_to_wkt(source)
            if w:
                rings.append(w)

        if not rings:
            return None
        return f"MULTIPOLYGON({', '.join(rings)})"

    async def _resolve_extent(self, wkt: Optional[str]) -> tuple[Any, Optional[float],
                                                                list[dict[str, Any]]]:
        """Validated geometry, its area in hectares, and the blocks it reaches.

        `ST_MakeValid` is not optional. Contour rings come from a marching-
        squares extraction on a 200² grid and can self-intersect where two lobes
        nearly touch; an invalid geometry makes `ST_Intersects` raise, and the
        failure would land at publication time — the worst possible moment.

        Area is measured in a metric projection (EPSG:32645, UTM 45N, which
        covers Jharkhand) rather than in degrees. Square degrees are not an area
        and the number they produce is meaningless at this latitude.
        """
        if not wkt:
            return None, None, []

        row = (await self.db.execute(text("""
            SELECT ST_AsEWKT(g) AS geom,
                   ST_Area(ST_Transform(g, 32645)) / 10000.0 AS ha
            FROM (SELECT ST_MakeValid(
                      ST_Multi(ST_SetSRID(ST_GeomFromText(:wkt), 4326))) AS g) s
        """), {"wkt": wkt})).mappings().one()

        blocks = (await self.db.execute(text("""
            SELECT b.id::text AS id, b.name AS name, d.name AS district,
                   ST_Area(ST_Transform(ST_Intersection(
                       b.geometry, ST_MakeValid(ST_SetSRID(ST_GeomFromText(:wkt), 4326))
                   ), 32645)) / 10000.0 AS overlap_ha
            FROM blocks b
            LEFT JOIN districts d ON d.id = b.district_id
            WHERE ST_Intersects(
                b.geometry,
                ST_MakeValid(ST_SetSRID(ST_GeomFromText(:wkt), 4326)))
            ORDER BY overlap_ha DESC
        """), {"wkt": wkt})).mappings().all()

        return row["geom"], round(float(row["ha"]), 4), [
            {"id": b["id"], "name": b["name"], "district": b["district"],
             "overlap_ha": round(float(b["overlap_ha"] or 0), 4)}
            for b in blocks
        ]

    # ── writes ───────────────────────────────────────────────────────

    async def propose(self, *, actor: User, run_id: uuid.UUID, headline: str,
                      what_it_means: str, what_to_do: Optional[str] = None,
                      ip: Optional[str] = None) -> Advisory:
        run = (await self.db.execute(
            select(SimulationRun).where(SimulationRun.id == run_id))).scalar_one_or_none()
        if run is None:
            raise ResourceNotFoundError("SimulationRun", str(run_id))
        if run.status != "completed":
            raise AppValidationError(
                f"Run is '{run.status}'. Only a completed run can be proposed for "
                f"publication — publishing an incomplete one would put a number "
                f"in front of residents that the engine never finished producing.")

        wkt = self._footprint_wkt(run)
        geom, ha, blocks = await self._resolve_extent(wkt)

        body = what_it_means.strip()
        if _PREMISE not in body:
            body = f"{body}\n\n{_PREMISE}"

        adv = Advisory(
            isr_point_id=run.isr_point_id,
            run_id=run.id,
            status="proposed",
            headline=headline.strip(),
            what_it_means=body,
            what_to_do=(what_to_do or "").strip() or None,
            species=run.species,
            time_years=(run.request or {}).get("time_years"),
            restoration_years=(run.request or {}).get("restoration_years"),
            footprint=geom,
            footprint_ha=ha,
            affected_blocks=blocks,
            proposed_by=actor.id,
        )
        self.db.add(adv)
        await self.db.flush()
        await self.db.commit()

        await audit.record(
            action="advisory.propose", entity_type="advisories",
            entity_id=str(adv.id), actor_id=actor.id, actor_label=actor.email,
            ip_address=ip,
            detail={"run_id": str(run.id), "footprint_ha": ha,
                    "affected_blocks": len(blocks)},
        )
        return adv

    async def decide(self, *, actor: User, advisory_id: uuid.UUID,
                     decision: str, note: Optional[str] = None,
                     ip: Optional[str] = None) -> Advisory:
        """Publish, reject or withdraw. Admin only.

        The role check is in the router (`require_reviewer`); what is enforced
        HERE is the state machine, because an advisory that can be published
        twice, or withdrawn before it was ever public, produces a citizen-facing
        history that does not describe what happened.
        """
        adv = await self.get(advisory_id)
        now = datetime.now(timezone.utc)

        if decision == "publish":
            if adv.status == "published":
                raise AppValidationError("This advisory is already published.")
            if adv.status == "withdrawn":
                raise AppValidationError(
                    "A withdrawn advisory cannot be re-published. Propose a new "
                    "one from a current run, so the public record shows what "
                    "actually changed rather than a statement that reappeared.")
            adv.status = "published"
            adv.published_at = now
        elif decision == "reject":
            if adv.status != "proposed":
                raise AppValidationError(
                    f"Only a proposed advisory can be rejected; this one is "
                    f"'{adv.status}'.")
            adv.status = "rejected"
        elif decision == "withdraw":
            if adv.status != "published":
                raise AppValidationError(
                    "Only a published advisory can be withdrawn — there is "
                    "nothing public to take back otherwise.")
            adv.status = "withdrawn"
            adv.withdrawn_at = now
        else:
            raise AppValidationError(f"Unknown decision '{decision}'.")

        adv.decided_by = actor.id
        adv.decided_at = now
        adv.decision_note = (note or "").strip() or None
        await self.db.commit()

        # Publishing is what reaches people, so the alerts are raised HERE
        # rather than by a separate job somebody has to remember to run. One
        # alert per block the footprint actually intersects — usually one, and
        # only the part of it the model covers.
        #
        # Failure to raise alerts must not undo a publication a regulator has
        # already committed to: the advisory is public either way, and a lost
        # notification is recoverable (the block list is stored) while a
        # rolled-back decision is confusing. So it is logged, not raised.
        if decision == "publish":
            try:
                from app.services.alerts import AlertService
                await AlertService(self.db).announce_advisory(adv)
            except Exception as exc:  # noqa: BLE001
                from loguru import logger
                logger.exception(
                    f"advisory {adv.id} published but alerts failed: {exc}")

        await audit.record(
            action=f"advisory.{decision}", entity_type="advisories",
            entity_id=str(adv.id), actor_id=actor.id, actor_label=actor.email,
            ip_address=ip, detail={"status": adv.status, "note": adv.decision_note},
        )
        return adv
