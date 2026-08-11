"""Audit router — read the trail.

PRODUCT_DESIGN.md section 3.3: "who ran what, when — non-negotiable for a
government portal."

Read-only by design. There is no POST: entries are written by the audit
middleware and by explicit `audit.record()` calls, never by a client. There is
no DELETE either — an audit log a user can edit is not an audit log. P2 leaves
append-only as a convention enforced by the absence of endpoints; the Postgres
policy that enforces it at the database is tracked with the rest of RLS.

Restricted to `admin` and `regulator`. Analysts and field officers appear IN the
log and cannot read it, which is the point.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, IPvAnyAddress
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_regulator_or_admin
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_id: Optional[uuid.UUID]
    actor_label: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    detail: Optional[dict[str, Any]]
    # asyncpg maps Postgres INET to an ipaddress object, not a str. Declaring
    # this `str` made the endpoint 500 on its own data.
    ip_address: Optional[IPvAnyAddress]


@router.get("", response_model=list[AuditEntry])
async def list_audit(
    action: Optional[str] = Query(None, description="Exact action, e.g. 'login_failed'"),
    entity_type: Optional[str] = Query(None),
    actor_id: Optional[uuid.UUID] = Query(None),
    since: Optional[datetime] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_regulator_or_admin),
):
    """Most recent first."""
    stmt = select(AuditLog).order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if since:
        stmt = stmt.where(AuditLog.occurred_at >= since)
    result = await db.execute(stmt.offset(offset).limit(limit))
    return list(result.scalars().all())
