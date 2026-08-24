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

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from loguru import logger

# Shared with the citizen band so the two surfaces phrase a list the same way.
from app.api.v1.public_risk import _join_and
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
        """Raise an alert for every well whose latest sample breaches a health limit.

        THE REAL CHANNEL. These are not model output — they are laboratory
        results already in the database, and for most citizens they are the only
        thing on this platform about water they actually drink today.

        AND IT HAD NEVER SENT AN ALERT. Until 2026-08-25 this scanned
        `WHERE uranium_ppb > 30` and nothing else. Statewide maximum uranium is
        28.5 ppb, so the query matched **zero rows, every time it ran** — while
        22 wells exceeded the nitrate limit (one at 121 mg/L, 2.7x) and 11
        exceeded the fluoride permissible limit. The `alerts` table held eight
        rows, all of them `published_screening`: this platform had warned people
        eight times about a mine that does not exist and not once about the
        contamination measured in their own wells.

        That is the same defect as the uranium-only citizen band (section 4e),
        in the one place where it mattered most, and it was invisible for the
        same reason — a scan that finds nothing looks exactly like a scan that
        found nothing wrong.

        ONE ALERT PER WELL, not one per determinand. A well over both nitrate
        and fluoride is one problem with that well, and two notifications about
        it would read as two problems. It also keeps the existing
        `(block_id, well_name, sampled_at)` unique index correct — with an alert
        per determinand the second insert would hit `ON CONFLICT DO NOTHING` and
        vanish silently.

        Only the LATEST sample per well is considered. A well that exceeded in
        2019 and has been clean since should not generate an alert that reads as
        current; the honest statement is about its most recent result.
        """
        from app.api.v1.public_risk import (FLUORIDE_ACCEPTABLE_MG_L,
                                            FLUORIDE_PERMISSIBLE_MG_L,
                                            NITRATE_LIMIT_MG_L,
                                            URANIUM_LIMIT_PPB)

        rows = (await self.db.execute(text("""
            WITH latest AS (
                SELECT DISTINCT ON (ws.well_id)
                       ws.well_id, ws.sampled_at,
                       ws.uranium_ppb, ws.nitrate_mg_l, ws.fluoride_mg_l,
                       ws.arsenic_ppb, ws.iron_ppm,
                       mw.name AS well_name, mw.block_id
                FROM water_samples ws
                JOIN monitoring_wells mw ON mw.block_id IS NOT NULL
                                        AND mw.id = ws.well_id
                ORDER BY ws.well_id, ws.sampled_at DESC
            )
            SELECT * FROM latest
            WHERE uranium_ppb  >  :u
               OR nitrate_mg_l >  :no3
               OR fluoride_mg_l > :f_perm
               OR arsenic_ppb  >  :as_perm
               OR iron_ppm     >  :fe
            ORDER BY sampled_at DESC
            LIMIT :cap
        """), {"u": URANIUM_LIMIT_PPB, "no3": NITRATE_LIMIT_MG_L,
               "f_perm": FLUORIDE_PERMISSIBLE_MG_L, "as_perm": 50.0,
               "fe": 0.3, "cap": limit})).mappings().all()

        made = 0
        for r in rows:
            breaches = self._breaches(r)
            if not breaches:
                continue

            # Severity from how far over, not from a general sense of concern:
            # 3x the limit is a different message from 1.1x.
            worst = max(b["times_limit"] for b in breaches)
            severity = "high" if worst >= 2.0 else "warning"

            names = _join_and([b["label"] for b in breaches])
            headline = (f"{names.capitalize()} above the safe limit in a well "
                        f"near you")

            lines = [
                f"A government monitoring well"
                f"{f' ({r['well_name']})' if r['well_name'] else ''} in your "
                f"block was tested and found:",
                "",
            ]
            for b in breaches:
                lines.append(
                    f"  - {b['label']}: {b['value']:g} {b['unit']} "
                    f"(safe limit {b['limit']:g} {b['unit']})")
            lines += [
                "",
                "These are real laboratory results from government groundwater "
                "sampling. This is a measurement, not a prediction, and it was "
                "the most recent test at this well.",
                "",
            ]
            advice = [b["advice"] for b in breaches if b["advice"]]
            if advice:
                lines += advice + [""]
            lines.append(
                "If you drink from a borewell or handpump near this location, "
                "consider having it tested. Your district groundwater office "
                "and the State Pollution Control Board can advise on testing "
                "and on alternative supply.")

            res = await self.db.execute(text("""
                INSERT INTO alerts (kind, block_id, headline, body, severity,
                                    well_name, measured_value, measured_unit,
                                    sampled_at)
                VALUES ('measured_exceedance', :block_id, :headline, :body,
                        :severity, :well_name, :value, :unit, :sampled_at)
                ON CONFLICT (block_id, well_name, sampled_at)
                WHERE kind = 'measured_exceedance'
                DO NOTHING
                RETURNING id
            """), {"block_id": str(r["block_id"]), "headline": headline,
                   "body": "\n".join(lines), "severity": severity,
                   "well_name": r["well_name"],
                   # The driving determinand's reading, for the compact card.
                   "value": breaches[0]["value"], "unit": breaches[0]["unit"],
                   "sampled_at": r["sampled_at"]})
            if res.first():
                made += 1

        await self.db.commit()
        return {
            "wells_over_limit": len(rows),
            "alerts_created": made,
            "judged_on": {
                "uranium_ppb": URANIUM_LIMIT_PPB,
                "nitrate_mg_l": NITRATE_LIMIT_MG_L,
                "fluoride_mg_l": FLUORIDE_PERMISSIBLE_MG_L,
                "arsenic_ppb": 50.0, "iron_mg_l": 0.3,
            },
            "note": ("Health-significant determinands only, and only the most "
                     "recent sample per well — a well that exceeded years ago "
                     "and has been clean since must not raise an alert that "
                     "reads as current. Hardness, alkalinity and TDS are not "
                     "alerted on: they exceed at most Jharkhand wells and are "
                     "aquifer chemistry rather than contamination."),
        }

    @staticmethod
    def _breaches(r: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every health limit this sample is over, worst first.

        Arsenic and iron are included even though the CGWB file carries no
        values for either — the day a lab result arrives, the alert should fire
        without anybody remembering to come back and add it here.
        """
        from app.api.v1.public_risk import (FLUORIDE_PERMISSIBLE_MG_L,
                                            NITRATE_LIMIT_MG_L,
                                            URANIUM_LIMIT_PPB)
        spec = [
            ("uranium_ppb", "uranium", "ppb", URANIUM_LIMIT_PPB,
             "Boiling does not remove uranium."),
            ("nitrate_mg_l", "nitrate", "mg/L", NITRATE_LIMIT_MG_L,
             "Nitrate is mainly a risk to infants under six months. Do not use "
             "this water to make formula feed. Boiling concentrates it rather "
             "than removing it."),
            ("fluoride_mg_l", "fluoride", "mg/L", FLUORIDE_PERMISSIBLE_MG_L,
             "Long-term fluoride exposure causes dental and skeletal fluorosis. "
             "Boiling does not remove it."),
            ("arsenic_ppb", "arsenic", "ppb", 50.0,
             "Arsenic is a long-term poison and boiling does not remove it."),
            ("iron_ppm", "iron", "mg/L", 0.3, ""),
        ]
        out = []
        for col, label, unit, limit, advice in spec:
            v = r.get(col)
            if v is None or float(v) <= limit:
                continue
            out.append({"key": col, "label": label, "unit": unit,
                        "value": float(v), "limit": limit,
                        "times_limit": float(v) / limit, "advice": advice})
        out.sort(key=lambda b: -b["times_limit"])
        return out

    # ── the time-triggered alert ─────────────────────────────────────

    #: A modelled breakthrough probability at or above this raises the alert.
    #: Below it the milestone is reported in the scan result but nobody is told:
    #: a coin-flip dressed as a warning spends the credibility the measured
    #: alerts depend on.
    BREACH_PROBABILITY_THRESHOLD = 0.5

    async def scan_breach_due(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Alert where a published screening's shallow-breakthrough date has passed.

        WHAT THIS IS. Every other alert in this system fires on an event: a
        sample was analysed, an advisory was published, a formation was found to
        be shared. This one fires because a clock ran out. A published screening
        modelled that contamination would rise from the ore zone into the
        shallow aquifer after N years; the hypothetical operation's injection
        start date is now more than N years ago; so on the model's own terms
        that milestone has been passed and the people over that aquifer have not
        been told anything since the day it was published.

        WHAT IT IS NOT, and this is the sentence that governs the copy. **No ISR
        mine operates in Jharkhand.** Nothing is injecting, nothing is
        breaching, and no water has been contaminated by anything this platform
        models. The alert says what the published screening WOULD have implied by
        now, and it names the hypothetical start date it counted from so a reader
        can see the assumption rather than infer an event.

        THE GATES, each of which alone would over-claim:

        1. **Published.** A draft screening is internal; only the deliberate act
           of publication puts a screening in front of residents at all.
        2. **The run must actually carry a vertical screening.** Runs stored
           before 2026-08-20 have no `vertical` block, and its absence means
           "not assessed", NEVER "no pathway" (LIMITATIONS.md 4b). Those are
           skipped and counted, not cleared.
        3. **A real injection start date.** The clock is anchored to when the
           hypothetical operation would have begun injecting, not to when the
           advisory was published — those are different dates and only the first
           one means anything to the transport model. A site without one is
           skipped rather than assumed.
        4. **Elapsed time must have passed the modelled breakthrough.**
        5. **Probability at or above `BREACH_PROBABILITY_THRESHOLD`.**

        Reach is bounded exactly as `announce_aquifer_reach` bounds it, and for
        the same reason: alerting everyone on the formation would turn one
        hypothetical 13-hectare plume into a statewide warning, because the
        Basement Gneissic Complex alone covers over half of Jharkhand.

        Returns the reasons for raising nothing, because on the current data
        that is the entire result and a bare 0 would hide why.
        """
        now = datetime.now(timezone.utc)
        rows = (await self.db.execute(text("""
            SELECT a.id::text AS advisory_id, a.headline, a.species,
                   a.isr_point_id::text AS isr_point_id,
                   a.affected_blocks, a.published_at,
                   ip.name AS site_name, ip.injection_start_date,
                   sr.hydro, sr.request
            FROM advisories a
            JOIN isr_points ip      ON ip.id = a.isr_point_id
            JOIN simulation_runs sr ON sr.id = a.run_id
            WHERE a.status = 'published'
            ORDER BY a.published_at DESC
        """))).mappings().all()

        considered, skipped, raised = [], [], 0
        for r in rows:
            hydro = r["hydro"] or {}
            if isinstance(hydro, str):
                hydro = json.loads(hydro)
            v = (hydro or {}).get("vertical") or {}

            if not v:
                skipped.append({"advisory_id": r["advisory_id"],
                                "site": r["site_name"],
                                "reason": "no_vertical_screening",
                                "note": ("Run stored before shallow-aquifer "
                                         "screening was persisted. Not assessed "
                                         "— not a finding of no pathway.")})
                continue

            start = r["injection_start_date"]
            if start is None:
                skipped.append({"advisory_id": r["advisory_id"],
                                "site": r["site_name"],
                                "reason": "no_injection_start_date",
                                "note": ("The hypothetical operation has no start "
                                         "date, so there is no clock to run. "
                                         "Publication date is not a substitute — "
                                         "it is when people were told, not when "
                                         "injection would have begun.")})
                continue

            yrs = v.get("years_to_vertical_breakthrough")
            prob = v.get("shallow_impact_probability")
            elapsed = (now - start).days / 365.2425

            state = {
                "advisory_id": r["advisory_id"], "site": r["site_name"],
                "injection_start": start.date().isoformat(),
                "elapsed_years": round(elapsed, 1),
                "years_to_breakthrough": yrs,
                "probability": prob,
            }

            if yrs is None:
                state["reason"] = "no_breakthrough_modelled"
                skipped.append(state)
                continue
            if elapsed < float(yrs):
                state["reason"] = "not_yet_due"
                state["due_in_years"] = round(float(yrs) - elapsed, 1)
                considered.append(state)
                continue
            if prob is None or float(prob) < self.BREACH_PROBABILITY_THRESHOLD:
                state["reason"] = "below_probability_threshold"
                state["threshold"] = self.BREACH_PROBABILITY_THRESHOLD
                considered.append(state)
                continue

            state["reason"] = "due"
            considered.append(state)
            if not dry_run:
                raised += await self._raise_breach_alerts(r, v, elapsed)

        if not dry_run:
            await self.db.commit()

        due = [c for c in considered if c.get("reason") == "due"]
        return {
            "published_screenings": len(rows),
            "assessable": len(considered),
            "skipped": skipped,
            "considered": considered,
            "due_now": len(due),
            "alerts_created": raised,
            "dry_run": dry_run,
            "threshold": self.BREACH_PROBABILITY_THRESHOLD,
            "what_this_is": (
                "No ISR mine operates in Jharkhand. This reports where a "
                "PUBLISHED screening's own modelled timetable would, by now, "
                "have passed the point at which contamination reached shallow "
                "drinking water — had such an operation existed and begun "
                "injecting on the date recorded for it."),
        }

    async def _raise_breach_alerts(self, r: Mapping[str, Any],
                                   v: dict, elapsed: float) -> int:
        """Insert the alert for every block within the bounded shallow reach."""
        flow = None
        hydro = r["hydro"] or {}
        if isinstance(hydro, str):
            hydro = json.loads(hydro)
        flow = (hydro or {}).get("flow") or {}
        i = float(flow.get("gradient_i") or 0.0)

        aq = (await self.db.execute(text("""
            SELECT a.id, a.name, a.hydraulic_conductivity, a.porosity
            FROM aquifers a
            JOIN isr_points p ON ST_Contains(a.geometry, p.location)
            WHERE p.id = :pid AND a.geometry IS NOT NULL
            ORDER BY a.min_depth NULLS LAST
            LIMIT 1
        """), {"pid": r["isr_point_id"]})).mappings().first()
        if aq is None:
            return 0

        K = float(aq["hydraulic_conductivity"] or 0.0)
        phi = float(aq["porosity"] or 0.0)
        if K <= 0 or phi <= 0 or i <= 0:
            return 0

        # Reach over the ELAPSED period, not the run's evaluation horizon: the
        # question this alert answers is how far the model implies it could have
        # travelled by today.
        reach_m = min(K * i / phi * elapsed * 365.0,
                      self.AQUIFER_REACH_CAP_KM * 1000.0)

        blocks = (await self.db.execute(text("""
            SELECT b.id::text AS id, b.name, d.name AS district
            FROM blocks b
            JOIN isr_points p ON p.id = :pid
            JOIN aquifers a ON a.id = :aid
            LEFT JOIN districts d ON d.id = b.district_id
            WHERE b.geometry IS NOT NULL
              AND ST_Intersects(b.geometry, a.geometry)
              AND ST_DWithin(p.location::geography, b.geometry::geography, :reach)
        """), {"pid": r["isr_point_id"], "aid": str(aq["id"]),
               "reach": reach_m})).mappings().all()

        yrs = v.get("years_to_vertical_breakthrough")
        prob = float(v.get("shallow_impact_probability") or 0.0)
        made = 0
        for b in blocks:
            headline = ("A published groundwater screening for your area has "
                        "passed its modelled timetable")
            body = (
                f"In {r['published_at'].year if r['published_at'] else 'a previous year'}, "
                f"a screening was published for a HYPOTHETICAL uranium in-situ "
                f"recovery operation near {b['name']}.\n\n"
                f"NO SUCH MINE EXISTS. None is planned. The screening asked what "
                f"would happen if one operated, and it modelled that "
                f"contamination would take about {float(yrs):.0f} years to rise "
                f"from the ore zone into the shallow aquifer that supplies "
                f"wells and handpumps.\n\n"
                f"Counting from {r['injection_start_date'].date().isoformat()}, "
                f"the date recorded for when such an operation would have begun, "
                f"{elapsed:.0f} years have now passed — more than the "
                f"{float(yrs):.0f} the model gave. The screening put the "
                f"likelihood of that pathway opening at "
                f"{prob * 100:.0f}%.\n\n"
                f"WHAT THIS DOES AND DOES NOT MEAN. It does not mean your water "
                f"is contaminated, and it is not a measurement of anything. It "
                f"means a published assessment's own timetable has been passed, "
                f"and that the {aq['name']} aquifer beneath your block is the "
                f"one it described. If you drink from a borewell or handpump, "
                f"this is a good reason to ask your block water office to test "
                f"it — real testing is the only thing that can answer the "
                f"question this model raises."
            )
            res = await self.db.execute(text("""
                INSERT INTO alerts (kind, block_id, advisory_id, headline, body,
                                    severity)
                VALUES ('aquifer_breach_due', :block_id, :advisory_id,
                        :headline, :body, 'warning')
                ON CONFLICT (advisory_id, block_id, kind)
                WHERE advisory_id IS NOT NULL
                DO NOTHING
                RETURNING id
            """), {"block_id": b["id"], "advisory_id": r["advisory_id"],
                   "headline": headline, "body": body})
            if res.first():
                made += 1
        return made

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
