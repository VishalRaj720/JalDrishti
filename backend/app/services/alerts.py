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
                ON CONFLICT (advisory_id, block_id) WHERE advisory_id IS NOT NULL
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
            ON CONFLICT (alert_id, user_id) DO NOTHING
        """), {"uid": str(user_id)})
        await self.db.commit()
        return res.rowcount or 0


# Re-exported so importers do not need the model module for a type check.
__all__ = ["AlertService", "Alert", "AlertRead", "BlockSubscription",
           "URANIUM_LIMIT_PPB"]
