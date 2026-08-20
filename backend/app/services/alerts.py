"""Generating and reading citizen alerts.

THE TWO CHANNELS, AND WHY THE WORDING DIFFERS SO MUCH BETWEEN THEM.

`measured_exceedance` reports a laboratory result. A well was sampled, the
uranium concentration came back above the 30 ppb BIS drinking-water limit, and
that is simply true. It needs no hedging and gets none — hedging a real
exceedance is how a warning stops being read.

`published_screening` reports that a regulator has published a *model* of what a
hypothetical ISR operation would do. No such operation exists in Jharkhand. Every
sentence is written so that it cannot be mistaken for a report of an event, and
the advisory's own approved text (which already carries the premise, appended by
`AdvisoryService`) is what the citizen reads in full.

Getting this distinction wrong in either direction is the failure mode that
matters most in this product: understate a real exceedance and someone drinks
contaminated water, overstate a screening and you have alarmed a village about a
mine that does not exist.

GENERATION IS ADMIN-TRIGGERED, not scheduled. There is no scheduler in this
deployment, and a cron job that silently stops is worse than a button somebody
presses — the button's absence is visible.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.advisory import Advisory
from app.models.alert import Alert, AlertRead, BlockSubscription

#: BIS / WHO drinking-water limit for uranium. Matches the public risk API's
#: banding rule and `ml_pipeline`'s own `EXCURSION_THRESHOLDS`.
URANIUM_LIMIT_PPB = 30.0


class AlertService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ── generation ───────────────────────────────────────────────────

    async def announce_advisory(self, advisory: Advisory) -> int:
        """One alert per block the published advisory's footprint actually reaches.

        Called when a regulator publishes. The block list was resolved by real
        spatial intersection at proposal time, so this alerts the blocks the
        footprint touches — usually one, and only the part of it the model
        actually covers. Alerting the surrounding area would be the
        over-claiming the whole workflow exists to prevent.
        """
        blocks = advisory.affected_blocks or []
        if not blocks:
            logger.info(f"advisory {advisory.id} reaches no block; no alerts raised")
            return 0

        made = 0
        for b in blocks:
            body = (
                f"{advisory.what_it_means}\n\n"
                f"The modelled area covers about {b.get('overlap_ha', 0):.1f} hectares "
                f"of {b.get('name')} block. A block covers many thousands of hectares, "
                f"so this is a small part of it — not the whole area."
            )
            if advisory.what_to_do:
                body += f"\n\nWhat to do: {advisory.what_to_do}"

            # ON CONFLICT DO NOTHING against the partial unique index:
            # re-publishing or re-running generation must not put the same alert
            # in front of a citizen twice.
            res = await self.db.execute(text("""
                INSERT INTO alerts (kind, block_id, advisory_id, headline, body, severity)
                VALUES ('published_screening', :block_id, :advisory_id,
                        :headline, :body, 'info')
                ON CONFLICT (advisory_id, block_id, kind)
                    WHERE advisory_id IS NOT NULL
                DO NOTHING
                RETURNING id
            """), {"block_id": b["id"], "advisory_id": str(advisory.id),
                   "headline": advisory.headline, "body": body})
            if res.first():
                made += 1

        await self.db.commit()
        logger.info(f"advisory {advisory.id}: {made} block alert(s) raised")
        return made

    async def scan_measured_exceedances(self, *, limit: int = 500) -> dict[str, Any]:
        """Raise an alert for every CGWB sample over the uranium limit.

        THE REAL CHANNEL. These are not model output — they are laboratory
        results already in the database, and for most citizens they are the only
        thing on this platform that is about water they actually drink today.

        Only the LATEST sample per well is considered. A well that exceeded in
        2019 and has been clean since should not generate an alert that reads as
        current; the honest statement is about its most recent result.

        Idempotent by the `(block_id, well_name, sampled_at)` unique index, so
        running it twice does not double-alert.
        """
        rows = (await self.db.execute(text("""
            WITH latest AS (
                SELECT DISTINCT ON (ws.well_id)
                       ws.well_id, ws.uranium_ppb, ws.sampled_at,
                       mw.name AS well_name, mw.block_id
                FROM water_samples ws
                JOIN monitoring_wells mw ON mw.id = ws.well_id
                WHERE ws.uranium_ppb IS NOT NULL
                  AND mw.block_id IS NOT NULL
                ORDER BY ws.well_id, ws.sampled_at DESC
            )
            SELECT * FROM latest
            WHERE uranium_ppb > :limit
            ORDER BY uranium_ppb DESC
            LIMIT :cap
        """), {"limit": URANIUM_LIMIT_PPB, "cap": limit})).mappings().all()

        made = 0
        for r in rows:
            value = float(r["uranium_ppb"])
            # Severity from how far over the limit, not from a general sense of
            # concern: 3x the limit is a different message from 1.1x.
            severity = "high" if value >= URANIUM_LIMIT_PPB * 2 else "warning"
            headline = (f"Uranium above the safe limit in a well near you "
                        f"({value:.0f} ppb)")
            body = (
                f"A government monitoring well{f' ({r['well_name']})' if r['well_name'] else ''} "
                f"in your block was tested and measured {value:.1f} ppb of uranium. "
                f"The safe limit for drinking water is {URANIUM_LIMIT_PPB:.0f} ppb.\n\n"
                f"This is a real laboratory result from groundwater sampling, not a "
                f"prediction. It was the most recent test at this well.\n\n"
                f"If you drink water from a borewell or handpump near this location, "
                f"consider having it tested. Your district groundwater office and the "
                f"State Pollution Control Board can advise on testing and on "
                f"alternative supply."
            )
            res = await self.db.execute(text("""
                INSERT INTO alerts (kind, block_id, headline, body, severity,
                                    well_name, measured_value, measured_unit, sampled_at)
                VALUES ('measured_exceedance', :block_id, :headline, :body, :severity,
                        :well_name, :value, 'ppb', :sampled_at)
                ON CONFLICT (block_id, well_name, sampled_at)
                WHERE kind = 'measured_exceedance'
                DO NOTHING
                RETURNING id
            """), {"block_id": str(r["block_id"]), "headline": headline, "body": body,
                   "severity": severity, "well_name": r["well_name"],
                   "value": value, "sampled_at": r["sampled_at"]})
            if res.first():
                made += 1

        await self.db.commit()
        return {
            "wells_over_limit": len(rows),
            "alerts_created": made,
            "limit_ppb": URANIUM_LIMIT_PPB,
            "note": ("Only the most recent sample per well is considered — a well "
                     "that exceeded years ago and has been clean since must not "
                     "raise an alert that reads as current."),
        }

    # ── subscriptions ────────────────────────────────────────────────

    async def subscriptions(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = (await self.db.execute(text("""
            SELECT bs.block_id::text AS id, b.name, d.name AS district,
                   bs.created_at
            FROM block_subscriptions bs
            JOIN blocks b ON b.id = bs.block_id
            LEFT JOIN districts d ON d.id = b.district_id
            WHERE bs.user_id = :uid
            ORDER BY b.name
        """), {"uid": str(user_id)})).mappings().all()
        return [dict(r) for r in rows]

    async def subscribe(self, user_id: uuid.UUID, block_id: uuid.UUID) -> None:
        await self.db.execute(text("""
            INSERT INTO block_subscriptions (user_id, block_id)
            VALUES (:uid, :bid)
            ON CONFLICT (user_id, block_id) DO NOTHING
        """), {"uid": str(user_id), "bid": str(block_id)})
        await self.db.commit()

    async def unsubscribe(self, user_id: uuid.UUID, block_id: uuid.UUID) -> None:
        await self.db.execute(
            select(BlockSubscription).where(
                BlockSubscription.user_id == user_id,
                BlockSubscription.block_id == block_id))
        await self.db.execute(text("""
            DELETE FROM block_subscriptions WHERE user_id = :uid AND block_id = :bid
        """), {"uid": str(user_id), "bid": str(block_id)})
        await self.db.commit()

    # ── inbox ────────────────────────────────────────────────────────

    async def inbox(self, user_id: uuid.UUID, *, kind: Optional[str] = None,
                    limit: int = 100) -> list[dict[str, Any]]:
        """Alerts for the blocks this user subscribes to, newest first."""
        rows = (await self.db.execute(text("""
            SELECT a.id::text AS id, a.kind, a.headline, a.body, a.severity,
                   a.well_name, a.measured_value, a.measured_unit, a.sampled_at,
                   a.created_at, a.advisory_id::text AS advisory_id,
                   b.id::text AS block_id, b.name AS block_name,
                   d.name AS district_name,
                   (ar.user_id IS NOT NULL) AS is_read
            FROM alerts a
            JOIN block_subscriptions bs
              ON bs.block_id = a.block_id AND bs.user_id = :uid
            JOIN blocks b ON b.id = a.block_id
            LEFT JOIN districts d ON d.id = b.district_id
            LEFT JOIN alert_reads ar ON ar.alert_id = a.id AND ar.user_id = :uid
            -- CAST(...) rather than `:kind::text`: SQLAlchemy's `text()` parser
            -- reads the `::` cast as the start of a second bind parameter and
            -- leaves the first one unsubstituted, producing a syntax error at
            -- the colon. The explicit CAST is unambiguous.
            WHERE (CAST(:kind AS text) IS NULL OR a.kind = :kind)
            -- R11: an alert outlives the advisory that raised it unless this
            -- filter exists. Withdrawal is the act of TAKING A PUBLIC STATEMENT
            -- BACK, and the notification that reached people is the most public
            -- part of it — leaving it in the inbox makes withdrawal cosmetic.
            -- Measured-exceedance alerts have no advisory and are unaffected:
            -- a laboratory result is not withdrawn by anybody's decision.
              AND (a.advisory_id IS NULL
                   OR EXISTS (SELECT 1 FROM advisories ad
                              WHERE ad.id = a.advisory_id
                                AND ad.status = 'published'))
            ORDER BY a.created_at DESC
            LIMIT :cap
        """), {"uid": str(user_id), "kind": kind, "cap": limit})).mappings().all()
        return [dict(r) for r in rows]

    async def unread_count(self, user_id: uuid.UUID) -> int:
        return int((await self.db.execute(text("""
            SELECT count(*)
            FROM alerts a
            JOIN block_subscriptions bs
              ON bs.block_id = a.block_id AND bs.user_id = :uid
            LEFT JOIN alert_reads ar ON ar.alert_id = a.id AND ar.user_id = :uid
            WHERE ar.user_id IS NULL
            -- R11: an alert outlives the advisory that raised it unless this
            -- filter exists. Withdrawal is the act of TAKING A PUBLIC STATEMENT
            -- BACK, and the notification that reached people is the most public
            -- part of it — leaving it in the inbox makes withdrawal cosmetic.
            -- Measured-exceedance alerts have no advisory and are unaffected:
            -- a laboratory result is not withdrawn by anybody's decision.
              AND (a.advisory_id IS NULL
                   OR EXISTS (SELECT 1 FROM advisories ad
                              WHERE ad.id = a.advisory_id
                                AND ad.status = 'published'))
        """), {"uid": str(user_id)})).scalar_one())

    async def mark_read(self, user_id: uuid.UUID, alert_id: uuid.UUID) -> None:
        await self.db.execute(text("""
            INSERT INTO alert_reads (alert_id, user_id) VALUES (:aid, :uid)
            ON CONFLICT (alert_id, user_id) DO NOTHING
        """), {"aid": str(alert_id), "uid": str(user_id)})
        await self.db.commit()

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        res = await self.db.execute(text("""
            INSERT INTO alert_reads (alert_id, user_id)
            SELECT a.id, :uid
            FROM alerts a
            JOIN block_subscriptions bs
              ON bs.block_id = a.block_id AND bs.user_id = :uid
            WHERE true
            -- R11: an alert outlives the advisory that raised it unless this
            -- filter exists. Withdrawal is the act of TAKING A PUBLIC STATEMENT
            -- BACK, and the notification that reached people is the most public
            -- part of it — leaving it in the inbox makes withdrawal cosmetic.
            -- Measured-exceedance alerts have no advisory and are unaffected:
            -- a laboratory result is not withdrawn by anybody's decision.
              AND (a.advisory_id IS NULL
                   OR EXISTS (SELECT 1 FROM advisories ad
                              WHERE ad.id = a.advisory_id
                                AND ad.status = 'published'))
            ON CONFLICT (alert_id, user_id) DO NOTHING
        """), {"uid": str(user_id)})
        await self.db.commit()
        return res.rowcount or 0


    # ── the vertical pathway: who else drinks from that aquifer ──────

    #: A hypothetical operation cannot warn the whole state. The Basement
    #: Gneissic Complex covers 48,047 km², over half of Jharkhand, so "every
    #: block touching the aquifer" is not a reach — it is an abdication. The
    #: bound below is advective travel in the SHALLOW aquifer over the run's own
    #: evaluation horizon, which is a distance the engine's own numbers imply
    #: rather than one chosen for comfort.
    AQUIFER_REACH_CAP_KM = 25.0

    async def announce_aquifer_reach(self, advisory: Advisory,
                                     run: Any) -> dict[str, Any]:
        """Alert the blocks the SHALLOW aquifer carries this to, if any.

        WHY THIS IS A SEPARATE CLAIM. The footprint alert says "the modelled
        plume covers N hectares of your block". This one says something else
        entirely: that a pathway exists from the deep ore zone up into the
        shallow aquifer people actually drink from, and that the same aquifer
        extends under blocks the footprint never touches. Conflating the two
        would either under-warn the second group or tell the first group their
        drinking water is contaminated, and neither is what the model says.

        THE THREE GATES, in order, because each one alone would over-claim:

        1. **Breakthrough must be credible within the horizon.** If the vertical
           screening reports no breakthrough, or one beyond the years the run
           was evaluated over, nothing is raised. A pathway that opens after the
           period modelled is not a finding about that period.
        2. **The aquifer must be the one under the site.** Resolved by
           point-in-polygon, not by name.
        3. **The reach is bounded by advective travel**, v = K*i/phi over the
           horizon, capped at `AQUIFER_REACH_CAP_KM`. Shallow transport after
           breakthrough is NOT modelled by this product — there is no shallow
           plume solution here — so this is a screening radius for *who should
           be told*, never a predicted extent. It is stated in those words in
           the alert body.

        Returns a dict rather than a count because the reasons for raising
        nothing are the interesting part, and a bare 0 hides them.
        """
        v = ((run.hydro or {}).get("vertical") or {}) if run is not None else {}
        if not v:
            return {"alerts": 0, "reason": "no_vertical_screening",
                    "note": ("This run stored no shallow-aquifer screening. Runs "
                             "saved before R11 did not keep one — that is a gap "
                             "in the record, not a finding of no pathway.")}

        yrs = v.get("years_to_vertical_breakthrough")
        horizon = float((run.request or {}).get("time_years") or 0) or None
        if yrs is None:
            return {"alerts": 0, "reason": "no_breakthrough",
                    "note": ("The screening found no upward pathway to the "
                             "shallow aquifer, so there is nobody beyond the "
                             "footprint to tell.")}
        if horizon is not None and float(yrs) > horizon:
            return {"alerts": 0, "reason": "breakthrough_beyond_horizon",
                    "years_to_breakthrough": yrs, "horizon_years": horizon,
                    "note": (f"Breakthrough is estimated at {yrs} yr, beyond the "
                             f"{horizon:g}-year period this run evaluated. "
                             f"Raising an alert would state as a finding of this "
                             f"run something it did not model.")}

        # Shallow advective reach. `gradient_i` and K come from the run's own
        # resolved hydrogeology, so the radius is derived, not decreed.
        flow = (run.hydro or {}).get("flow") or {}
        i = float(flow.get("gradient_i") or 0.0)
        row = (await self.db.execute(text("""
            SELECT a.id, a.name, a.hydraulic_conductivity, a.porosity
            FROM aquifers a
            JOIN isr_points p ON ST_Contains(a.geometry, p.location)
            WHERE p.id = :pid AND a.geometry IS NOT NULL
            ORDER BY a.min_depth NULLS LAST
            LIMIT 1
        """), {"pid": str(advisory.isr_point_id)})).mappings().first()
        if row is None:
            return {"alerts": 0, "reason": "no_aquifer_polygon",
                    "note": ("No mapped aquifer polygon contains this site, so "
                             "there is no defensible way to say who shares its "
                             "water. That is a data gap, not an all-clear.")}

        K = float(row["hydraulic_conductivity"] or 0.0)
        phi = float(row["porosity"] or 0.0)
        if K <= 0 or phi <= 0 or i <= 0:
            return {"alerts": 0, "reason": "no_flow_parameters",
                    "aquifer": row["name"],
                    "note": ("The shallow aquifer's conductivity, porosity or "
                             "gradient is unknown here, so travel distance "
                             "cannot be derived. Guessing one would invent the "
                             "reach this alert exists to bound.")}

        years = horizon or float(yrs)
        reach_m = min(K * i / phi * years * 365.0,
                      self.AQUIFER_REACH_CAP_KM * 1000.0)
        capped = reach_m >= self.AQUIFER_REACH_CAP_KM * 1000.0

        # Blocks inside BOTH the aquifer polygon and the travel radius, minus
        # the ones the footprint alert already covered — nobody is told twice.
        already = {str(b.get("id")) for b in (advisory.affected_blocks or [])}
        blocks = (await self.db.execute(text("""
            SELECT b.id::text AS id, b.name, d.name AS district,
                   ROUND(ST_Distance(p.location::geography,
                                     b.geometry::geography)::numeric / 1000.0, 1)
                       AS distance_km
            FROM blocks b
            JOIN isr_points p ON p.id = :pid
            JOIN aquifers a ON a.id = :aid
            LEFT JOIN districts d ON d.id = b.district_id
            WHERE b.geometry IS NOT NULL
              AND ST_Intersects(b.geometry, a.geometry)
              AND ST_DWithin(p.location::geography, b.geometry::geography, :reach)
            ORDER BY distance_km
        """), {"pid": str(advisory.isr_point_id), "aid": str(row["id"]),
               "reach": reach_m})).mappings().all()

        # Context, never a trigger. Shallow groundwater in Jharkhand's hard rock
        # moves on the order of 1.5 m/yr (Phyllite: K 0.08 m/day, phi 0.04,
        # i 0.0021), and even the state's fastest unit — Older Alluvium, K 5.0,
        # phi 0.3 — reaches only ~255 m in twenty years. So this alert will
        # usually add nobody, and that is the finding rather than a failure:
        # lateral shallow transport does not carry this to the next block within
        # any period the run modelled. The count of blocks sharing the FORMATION
        # is reported so the difference between "shares a rock unit" and "is
        # reached by anything" stays visible, and it is deliberately not a basis
        # for alerting: the Basement Gneissic Complex alone spans over half the
        # state.
        shared = (await self.db.execute(text("""
            SELECT count(*) FROM blocks b
            WHERE b.geometry IS NOT NULL
              AND ST_Intersects(b.geometry, (SELECT geometry FROM aquifers
                                             WHERE id = :aid))
        """), {"aid": str(row["id"])})).scalar()

        targets = [b for b in blocks if b["id"] not in already]
        if not targets:
            return {"alerts": 0, "reason": "no_additional_blocks",
                    "aquifer": row["name"], "reach_km": round(reach_m / 1000, 1),
                    "reach_m": round(reach_m, 1),
                    "blocks_sharing_formation": shared,
                    "note": (f"Shallow groundwater travels about "
                             f"{reach_m:.0f} m here in {years:g} years, so every "
                             f"block within that distance was already alerted by "
                             f"the footprint. {shared} blocks sit on the same "
                             f"{row['name']} formation, which is a shared rock "
                             f"unit and not a shared exposure — nothing the "
                             f"model produced reaches them.")}

        made = 0
        reach_km = round(reach_m / 1000.0, 1)
        for b in targets:
            dist = b["distance_km"]
            name = b["name"]
            body = (
                f"A groundwater screening for a hypothetical uranium in-situ "
                f"recovery operation about {dist} km away estimates that "
                f"lixiviant could reach the shallow aquifer within {yrs:g} "
                f"years. {name} block draws on the same shallow aquifer "
                f"({row['name']}).\n\n"
                f"This is not a finding that your water is affected, and "
                f"nothing has been measured in your block as part of this. It "
                f"is a statement that you share the water body a modelled "
                f"pathway would enter. The {reach_km} km distance is how far "
                f"shallow groundwater travels here in {years:g} years — it "
                f"marks who should be told, not how far anything has spread. "
                f"Movement within the shallow aquifer is not modelled by this "
                f"system.\n\n"
                f"{advisory.what_it_means}"
            )
            if advisory.what_to_do:
                body += f"\n\nWhat to do: {advisory.what_to_do}"

            res = await self.db.execute(text("""
                INSERT INTO alerts (kind, block_id, advisory_id, headline, body,
                                    severity)
                VALUES ('aquifer_pathway', :block_id, :advisory_id, :headline,
                        :body, 'warning')
                ON CONFLICT (advisory_id, block_id, kind)
                    WHERE advisory_id IS NOT NULL
                DO NOTHING
                RETURNING id
            """), {"block_id": b["id"], "advisory_id": str(advisory.id),
                   "headline": (f"Shallow aquifer shared with a screened area "
                                f"— {name}"),
                   "body": body})
            if res.first():
                made += 1

        await self.db.commit()
        logger.info(f"advisory {advisory.id}: {made} aquifer-pathway alert(s) "
                    f"across {row['name']} within {reach_km} km")
        return {"alerts": made, "reason": "raised", "aquifer": row["name"],
                "reach_km": reach_km, "reach_m": round(reach_m, 1),
                "blocks_sharing_formation": shared,
                "reach_was_capped": capped,
                "years_to_breakthrough": yrs,
                "blocks": [dict(b) for b in targets]}


# ── the entry point publication uses ─────────────────────────────────


async def raise_for_advisory(advisory_id: uuid.UUID) -> dict[str, Any]:
    """Raise every alert a newly-published advisory warrants. Own session.

    THE BUG THIS EXISTS TO FIX, found in R11: eight advisories had been
    published and the `alerts` table was EMPTY. Not under-populated — empty.
    Every insert had been rejected by the `alerts_write` RLS policy, which
    requires `app.bypass_rls = 'on'`, and `decide()` wrapped the call in a broad
    `except Exception` that logged the failure and let the publication stand. So
    the product reported a successful publication, showed the advisory to
    citizens, and notified nobody — and the log line that said so scrolled past
    once per publication.

    WHY THE POLICY WAS RIGHT AND THE CALL WAS WRONG. `set_rls_context` uses
    `SET LOCAL`, which Postgres discards at COMMIT — deliberately, so a pooled
    connection cannot leak one request's identity into the next. `decide()`
    commits the decision and *then* raises alerts, so by that point the session
    has no context at all and `bypass_rls` reads as 'off'. Alerting is system
    work authorised by a decision that has already been made and recorded; it
    is not the caller's privilege. So it gets its own session with the system
    context, which is exactly what `audit.record` already does and for the same
    reason.

    Nothing crosses a session boundary: the advisory and its run are re-loaded
    here rather than handed in, so there is no detached instance to lazy-load
    at the worst moment.
    """
    from app.database import AsyncSessionLocal, set_rls_context
    from app.models.simulation_run import SimulationRun

    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        adv = (await db.execute(
            select(Advisory).where(Advisory.id == advisory_id)
        )).scalar_one_or_none()
        if adv is None:
            return {"footprint_alerts": 0, "aquifer_reach": None,
                    "error": f"advisory {advisory_id} not found"}

        run = (await db.execute(
            select(SimulationRun).where(SimulationRun.id == adv.run_id)
        )).scalar_one_or_none()

        svc = AlertService(db)
        footprint = await svc.announce_advisory(adv)

        # `announce_advisory` commits, and COMMIT discards `SET LOCAL` — so the
        # system context set above is gone by now and every RLS-protected table
        # reads as empty. The first symptom was `announce_aquifer_reach`
        # reporting "no mapped aquifer polygon contains this site" for a site
        # that provably sits inside one: the JOIN to `isr_points` returned
        # nothing because the session had become anonymous mid-function.
        #
        # This is the same failure as the one in `decide()` one level up, and it
        # will recur anywhere a commit is followed by more queries. The rule:
        # after any commit, the context is gone until it is set again.
        await set_rls_context(db, bypass=True)
        aquifer = await svc.announce_aquifer_reach(adv, run)
        return {"footprint_alerts": footprint, "aquifer_reach": aquifer}

# Re-exported so importers do not need the model module for a type check.
__all__ = ["AlertService", "raise_for_advisory", "Alert", "AlertRead",
           "BlockSubscription", "URANIUM_LIMIT_PPB"]
