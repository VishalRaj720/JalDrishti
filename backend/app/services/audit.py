"""Audit trail writer.

PRODUCT_DESIGN.md section 3.3 lists `GET /audit` as non-negotiable for a
government portal. This is the write half.

THREE RULES THIS MODULE ENFORCES:

1. **An audit failure must never fail the request.** A portal that 500s because
   its logging table is unreachable is worse than one that serves the request.
   Every write is wrapped, and a failure is logged loudly rather than raised.

2. **An audit write must never ride the request's transaction.** If it did, a
   rolled-back request would erase its own audit record — and the requests most
   worth auditing are exactly the ones that fail. Each write opens its own
   session and commits independently.

3. **Denials are audited, not just successes.** A 403 is the single most
   interesting line in an access log; recording only what succeeded would hide
   every attempt to reach something.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal, set_rls_context
from app.models.audit_log import AuditLog

# Mutating verbs are audited wholesale. Reads are not: at 415 stations and 8,345
# readings the read traffic would bury the entries that matter. Sensitive reads
# get an explicit `record()` call instead.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def record(
    *,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    actor_id: Optional[uuid.UUID] = None,
    actor_label: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Append one audit row. Never raises."""
    try:
        async with AsyncSessionLocal() as db:
            # The audit writer acts as the SYSTEM, not as the caller, so it runs
            # with the bypass flag rather than the caller's role.
            #
            # This is not a convenience. `audit_log` has RLS enabled, and
            # SQLAlchemy emits `INSERT ... RETURNING id, occurred_at` — RETURNING
            # requires the new row to be visible under the SELECT policy, which
            # only admits admin and regulator. Without the bypass, every audit
            # write by an analyst, field officer or citizen failed with "new row
            # violates row-level security policy", and because `record()`
            # swallows its own errors (rule 1), the trail died SILENTLY while
            # the API kept answering 200. The test suite could not see it either:
            # tests connect as `postgres`, which bypasses RLS anyway.
            await set_rls_context(db, bypass=True)
            db.add(AuditLog(
                actor_id=actor_id,
                actor_label=actor_label,
                action=action,
                entity_type=entity_type,
                entity_id=(str(entity_id) if entity_id is not None else None),
                detail=detail,
                ip_address=ip_address,
            ))
            try:
                await db.commit()
            except IntegrityError:
                # The only realistic cause is actor_id referencing a user that
                # no longer exists (deleted mid-request). The action still
                # happened, so keep the record and drop the broken link rather
                # than losing the line entirely.
                await db.rollback()
                # ROLLBACK discards SET LOCAL, so the bypass has to be re-applied
                # or this retry hits the same RLS wall the first insert cleared.
                await set_rls_context(db, bypass=True)
                db.add(AuditLog(
                    actor_id=None,
                    actor_label=actor_label or (str(actor_id) if actor_id else None),
                    action=action,
                    entity_type=entity_type,
                    entity_id=(str(entity_id) if entity_id is not None else None),
                    detail={**(detail or {}), "actor_fk_unresolved": True},
                    ip_address=ip_address,
                ))
                await db.commit()
    except Exception as exc:  # noqa: BLE001 — rule 1
        logger.error(f"AUDIT WRITE FAILED ({action} {entity_type} "
                     f"{entity_id}): {type(exc).__name__}: {exc}")


def entity_from_path(path: str) -> tuple[str, Optional[str]]:
    """Best-effort (entity_type, entity_id) from a REST path.

    `/api/v1/isr-points/2b8f.../simulations` -> ("isr-points", "2b8f...").
    Deliberately dumb: the audit row records what was addressed, and the route
    can always call `record()` directly when it knows better.
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api":
        parts = parts[2:]           # drop 'api', 'v1'
    if not parts:
        return ("root", None)
    entity_type = parts[0]
    entity_id = None
    for p in parts[1:]:
        # a UUID-ish or numeric segment is the addressed record
        if "-" in p and len(p) >= 32:
            entity_id = p
        elif p.isdigit():
            entity_id = p
    return (entity_type, entity_id)
