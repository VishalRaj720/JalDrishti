"""Putting an alert in front of the person it is about, off-portal.

WHAT WAS MISSING. Every alert kind in `alerts.py` writes a row to a table.
Until R16 that row was the whole channel: a resident saw it only by signing
in, opening the bell, and having earlier followed the block it was about. The
Alerts screen said so in its subtitle -- "this portal does not send SMS or
email" -- and the proposal's promise that stakeholders "receive ... alerts"
was, in practice, a promise that a row existed.

WHAT THIS DOES. `deliver_pending` finds every (alert, subscriber) pair that has
not yet been delivered by email, sends one message per pair, and records the
attempt in `alert_deliveries`. It is safe to call as often as you like:

  * the unique index on (alert_id, user_id, channel) makes a re-run send
    nothing twice ONCE SENT, even after a crash between send and record;
  * a failed send is recorded as `failed` with the SMTP error, so it is
    visible on the operator's panel and retried on the next run rather than
    forgotten -- literally: `pending_deliveries` treats a `failed` row the
    same as no row, and the insert is an UPSERT that overwrites it, so a
    transient relay outage or a credentials fix does not orphan every alert
    that happened to be raised during the bad window (2026-09-21: found live,
    a wrong SMTP credential left three deliveries permanently `failed` with
    zero retries because the insert used to be `ON CONFLICT ... DO NOTHING`
    against a row that already existed);
  * with no SMTP host configured it sends nothing, records nothing, and
    returns the size of the backlog -- a number the Administration screen
    shows, so "delivery is not set up" is a visible state and not a silent one.

WHO IS TOLD. The join is to `block_subscriptions`, which since R16 is
populated automatically from the home block a citizen gives at registration.
Withdrawn advisories are excluded exactly as the inbox excludes them: an alert
that was taken back must not go out by a slower channel after the fact.

WHY SMTP AND NOT A PROVIDER SDK. Five settings cover Brevo, Mailjet, SES and a
Gmail app password alike, and the standard library does it in a thread. A
provider client would be a dependency, an API key format and a rate-limit
scheme for a message volume of tens per month.

RLS. This runs under the system context in its own session, like
`audit.record` and `alerts.raise_for_advisory`, because delivery is system
work authorised by a decision already made. And the same hazard as everywhere
else applies: `SET LOCAL` dies at COMMIT, so the context is re-established
after every per-message commit. The per-message commit is deliberate -- a
record that a person was emailed must survive the process dying on the next
one.
"""
from __future__ import annotations

import asyncio
import json
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Optional

from loguru import logger
from sqlalchemy import text

from app.config import settings

#: One alert kind, one opening sentence. The measured channel needs no
#: hedging; the modelled channels must not be mistaken for a report of an event.
_KIND_LEAD = {
    "measured_exceedance": (
        "A government groundwater test near you came back above a drinking-water "
        "limit. This is a laboratory measurement, not a prediction."),
    "published_screening": (
        "An authority has published a modelled screening for your area. No "
        "uranium mine of this kind operates in Jharkhand; this shows what the "
        "model expects WOULD happen if one did."),
    "aquifer_pathway": (
        "A published screening for a hypothetical operation nearby found a "
        "pathway into the shallow aquifer your block shares. Nothing has been "
        "measured in your block as part of this."),
    "aquifer_breach_due": (
        "A published screening's own modelled timetable has now been passed. No "
        "such mine exists; this is the model's clock running out, not a "
        "detection."),
    "possible_reach": (
        "Your block lies inside the UPPER estimate of a published screening's "
        "uncertainty band, and outside its central estimate. No such mine "
        "exists; this is the width of the model's uncertainty, not a finding."),
}

_KIND_LABEL = {
    "measured_exceedance": "Measured result",
    "published_screening": "Published screening",
    "aquifer_pathway": "Shared shallow aquifer",
    "aquifer_breach_due": "Screening timetable passed",
    "possible_reach": "Within a screening's uncertainty band",
}

_TIER_LABEL = {"notice": "NOTICE", "warning": "WARNING", "alert": "ALERT",
               "critical": "CRITICAL"}


def _explanation_lines(x: dict[str, Any]) -> list[str]:
    """The seven fields, in plain text, in the order a reader asks them.
    Tolerates a partial or missing explanation (rows written before R17)."""
    if not x:
        return []
    out = ["", "AT A GLANCE"]
    if x.get("what_happened"):
        out.append(f"  What happened:   {x['what_happened']}")
    d = x.get("driver") or {}
    if d.get("determinand"):
        out.append(f"  Driven by:       {d['determinand']} {d.get('value')} "
                   f"{d.get('unit')} against a limit of {d.get('limit')} "
                   f"{d.get('unit')} ({d.get('limit_kind')}; "
                   f"{d.get('times_limit')}x)")
        extra = [b for b in (d.get("all_breaches") or [])[1:]]
        for b in extra:
            out.append(f"                   also {b['determinand']} {b['value']} "
                       f"{b['unit']} (limit {b['limit']} {b['unit']})")
    elif d.get("quantity"):
        out.append(f"  Driven by:       {d['quantity']}"
                   + (f" ({d['species']})" if d.get("species") else ""))
    w = x.get("where") or {}
    if w:
        out.append(f"  Where:           {w.get('block')}"
                   + (f", {w['district']}" if w.get("district") else "")
                   + (f" -- {w['well_name']}" if w.get("well_name") else "")
                   + (f" ({w['scope']})" if w.get("scope") else ""))
    t = x.get("tier") or {}
    if t:
        out.append(f"  Level:           {_TIER_LABEL.get(t.get('level'), t.get('level'))}"
                   f" -- {t.get('rule')}")
    out.append(f"  Basis:           "
               + ("OBSERVED -- a laboratory measurement"
                  if x.get("basis") == "observed"
                  else "MODELLED -- a screening of a hypothetical scenario, "
                       "not a report of an event"))
    c = x.get("confidence") or {}
    if c.get("kind") == "measurement":
        out.append(f"  Confidence:      {c.get('source')}"
                   + (f", sampled {str(c['sampled_at'])[:10]}" if c.get("sampled_at") else "")
                   + ("; a single sample, so a reading rather than a trend"
                      if c.get("single_sample") else ""))
    elif c:
        mig = c.get("migration_m") or {}
        band = (f"migration P10/P50/P90 = {mig.get('p10')}/{mig.get('p50')}/"
                f"{mig.get('p90')} m" if mig else "band not recorded")
        flags = c.get("extrapolation") or []
        out.append(f"  Confidence:      {band}"
                   + (f"; outside trained support on {', '.join(flags)}" if flags
                      else "; inside the model's trained support")
                   + (f"; excursion probability {c['excursion_probability']}"
                      if c.get("excursion_probability") is not None else ""))
    na = x.get("next_action") or []
    if na:
        out.append("  What next:")
        for line in na:
            out.append(f"    - {line}")
    return out


@dataclass(frozen=True)
class Mailer:
    host: str
    port: int
    user: str
    password: str
    starttls: bool
    from_email: str
    from_name: str

    @classmethod
    def from_settings(cls) -> "Mailer":
        return cls(
            host=settings.SMTP_HOST.strip(), port=int(settings.SMTP_PORT),
            user=settings.SMTP_USER, password=settings.SMTP_PASSWORD,
            starttls=bool(settings.SMTP_STARTTLS),
            from_email=settings.ALERT_FROM_EMAIL.strip(),
            from_name=settings.ALERT_FROM_NAME,
        )

    @property
    def configured(self) -> bool:
        return bool(self.host and self.from_email)

    def _send_blocking(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.from_email))
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=20,
                                  context=ssl.create_default_context()) as s:
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)
            return
        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            s.ehlo()
            if self.starttls:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> None:
        """Send in a worker thread; smtplib is blocking and the API is not."""
        await asyncio.to_thread(self._send_blocking, to, subject, body)


def render_alert_email(row: dict[str, Any]) -> tuple[str, str]:
    """Subject and plain-text body for one alert, to one person.

    Plain text, deliberately. The audience includes phones on weak connections
    and mail clients that strip HTML; the copy has been written to read in
    order without formatting, and the body already carries the premise.
    """
    kind = row["kind"]
    where = row["block_name"] + (f", {row['district_name']}" if row.get("district_name") else "")
    subject = f"[JalDrishti] {row['headline']} — {row['block_name']}"
    lines = [
        f"Hello {row.get('username') or ''}".rstrip() + ",",
        "",
        _KIND_LEAD.get(kind, ""),
        "",
        f"Area: {where}",
        f"Type: {_KIND_LABEL.get(kind, kind)}",
    ]
    if row.get("tier"):
        lines.append(f"Level: {_TIER_LABEL.get(row['tier'], row['tier'])}"
                     f" ({'measured' if row.get('basis') == 'observed' else 'modelled'})")
    if row.get("sampled_at"):
        lines.append(f"Sample date: {row['sampled_at']:%d %B %Y}")
    lines += ["", row["headline"].upper(), "", row["body"].strip(), ""]
    x = row.get("explanation")
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError:
            x = None
    lines += _explanation_lines(x or {})
    lines.append("")
    lines += [
        "Open the portal for the full record and what to do next:",
        f"  {settings.PORTAL_URL.rstrip('/')}/alerts",
        "",
        "You are receiving this because your JalDrishti account follows "
        f"{row['block_name']} block. You can change the areas you follow, or "
        "turn off email, from My Area in the portal.",
        "",
        "JalDrishti is a screening and monitoring platform for Jharkhand "
        "groundwater. No ISR uranium mine operates in Jharkhand; any modelled "
        "result is preparedness screening, never a report of an event.",
    ]
    return subject, "\n".join(lines)


async def pending_deliveries(db, *, limit: int = 500) -> list[dict[str, Any]]:
    """Every (alert, subscriber) pair not yet SUCCESSFULLY delivered by email.

    "Not yet delivered" includes a pair that was already tried and failed --
    the unique row on (alert_id, user_id, channel) means there is at most one
    delivery record per pair, and a `failed` one must be as eligible for
    another attempt as no row at all, or a `failed` is a dead end forever
    (found live, 2026-09-21: a bad SMTP credential window permanently
    orphaned three deliveries this way -- see deliver_pending's UPSERT)."""
    rows = (await db.execute(text("""
        SELECT a.id::text        AS alert_id,
               a.kind, a.headline, a.body, a.severity, a.sampled_at,
               a.tier, a.basis, a.explanation,
               a.created_at,
               u.id::text        AS user_id,
               u.username, u.email,
               b.name            AS block_name,
               d.name            AS district_name
        FROM alerts a
        JOIN block_subscriptions bs ON bs.block_id = a.block_id
        JOIN users u ON u.id = bs.user_id
        JOIN blocks b ON b.id = a.block_id
        LEFT JOIN districts d ON d.id = b.district_id
        LEFT JOIN alert_deliveries ad
               ON ad.alert_id = a.id AND ad.user_id = u.id AND ad.channel = 'email'
        WHERE (ad.id IS NULL OR ad.status = 'failed')
          AND u.alert_email_opt_in
          AND u.email IS NOT NULL AND u.email <> ''
          -- Withdrawn advisories are taken back everywhere, the slow channel
          -- included. Same rule as the inbox.
          AND (a.advisory_id IS NULL
               OR EXISTS (SELECT 1 FROM advisories ad2
                          WHERE ad2.id = a.advisory_id
                            AND ad2.status = 'published'))
        ORDER BY a.created_at ASC
        LIMIT :cap
    """), {"cap": limit})).mappings().all()
    return [dict(r) for r in rows]


async def deliver_pending(*, limit: int = 200, mailer: Optional[Mailer] = None) -> dict[str, Any]:
    """Send every undelivered alert email. Own session, system context.

    Returns counts rather than raising: this is called from request handlers
    after a publication and from the scheduler, and neither should fail because
    a mail relay is down. The failures are in the table.
    """
    from app.database import AsyncSessionLocal, set_rls_context

    m = mailer or Mailer.from_settings()
    out: dict[str, Any] = {"configured": m.configured, "sent": 0, "failed": 0,
                           "pending": 0, "skipped": 0}

    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        pending = await pending_deliveries(db, limit=limit)
        out["pending"] = len(pending)
        if not pending:
            return out
        if not m.configured:
            logger.warning(f"alert delivery: {len(pending)} alert email(s) waiting "
                           f"and SMTP_HOST is not configured -- nothing sent")
            return out

        for row in pending:
            # Demo accounts on a reserved domain must never be handed to a
            # relay: `.local` is not routable, and a bounce storm from the demo
            # citizen would be the first thing a new provider sees.
            addr = (row["email"] or "").strip()
            if addr.lower().endswith((".local", ".invalid", ".test", ".example")):
                status, detail = "skipped", "non-routable demo address"
            else:
                subject, body = render_alert_email(row)
                try:
                    await m.send(addr, subject, body)
                    status, detail = "sent", None
                except Exception as exc:  # noqa: BLE001 -- recorded, not raised
                    status, detail = "failed", f"{type(exc).__name__}: {exc}"[:2000]
                    logger.error(f"alert delivery to {addr} failed: {detail}")

            # UPSERT, not INSERT ... DO NOTHING: the only row `pending_deliveries`
            # can have handed us is either absent or `failed` (see its docstring),
            # so a conflict here is always a RETRY and must overwrite the old
            # failed attempt, not silently discard this one's outcome. The extra
            # `WHERE` is a belt-and-suspenders repeat of that same invariant --
            # it must never overwrite an already-`sent` row, even if some future
            # caller feeds this function a pair pending_deliveries would not have.
            await db.execute(text("""
                INSERT INTO alert_deliveries (alert_id, user_id, channel, address,
                                              status, detail)
                VALUES (:aid, :uid, 'email', :addr, :status, :detail)
                ON CONFLICT (alert_id, user_id, channel) DO UPDATE
                SET address = EXCLUDED.address, status = EXCLUDED.status,
                    detail = EXCLUDED.detail
                WHERE alert_deliveries.status = 'failed'
            """), {"aid": row["alert_id"], "uid": row["user_id"], "addr": addr,
                   "status": status, "detail": detail})
            # Commit per message so a record of a sent email survives the
            # process dying on the next one -- and then re-establish the
            # context COMMIT just discarded. See the module docstring.
            await db.commit()
            await set_rls_context(db, bypass=True)
            out[status] += 1

        out["pending"] = max(0, out["pending"] - out["sent"] - out["skipped"])
    logger.info(f"alert delivery: sent={out['sent']} failed={out['failed']} "
                f"skipped={out['skipped']} still_pending={out['pending']}")
    return out


async def delivery_status() -> dict[str, Any]:
    """What the operator's panel shows: is delivery set up, and is it keeping up."""
    from app.database import AsyncSessionLocal, set_rls_context

    m = Mailer.from_settings()
    async with AsyncSessionLocal() as db:
        await set_rls_context(db, bypass=True)
        pending = len(await pending_deliveries(db, limit=10_000))
        counts = (await db.execute(text("""
            SELECT status, count(*) AS n, max(created_at) AS last_at
            FROM alert_deliveries WHERE channel = 'email'
            GROUP BY status
        """))).mappings().all()
        subs = (await db.execute(text("""
            SELECT count(DISTINCT user_id) AS people,
                   count(DISTINCT block_id) AS blocks
            FROM block_subscriptions
        """))).mappings().first() or {"people": 0, "blocks": 0}
        alerts_total = (await db.execute(text("SELECT count(*) FROM alerts"))).scalar() or 0

    by = {r["status"]: {"count": int(r["n"]), "last_at": r["last_at"]} for r in counts}
    return {
        "configured": m.configured,
        "provider_host": m.host or None,
        "from_email": m.from_email or None,
        "pending": pending,
        "sent": by.get("sent", {}).get("count", 0),
        "failed": by.get("failed", {}).get("count", 0),
        "skipped": by.get("skipped", {}).get("count", 0),
        "last_sent_at": by.get("sent", {}).get("last_at"),
        "last_failed_at": by.get("failed", {}).get("last_at"),
        "subscribers": int(subs["people"]), "blocks_followed": int(subs["blocks"]),
        "alerts_total": int(alerts_total),
        "scheduler_interval_hours": settings.ALERT_SCAN_INTERVAL_HOURS,
        "checked_at": datetime.now(timezone.utc),
        "note": ("Alerts always appear in the portal inbox. Email is the "
                 "off-portal channel; with no SMTP host configured they wait "
                 "here rather than being dropped."),
    }


__all__ = ["Mailer", "deliver_pending", "delivery_status", "pending_deliveries",
           "render_alert_email"]
