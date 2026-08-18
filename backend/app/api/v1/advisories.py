"""Advisories — proposing a screening, and the regulator decision on it.

The staff side. The citizen-facing read is in `public_risk.py`, deliberately
separate: this router serves drafts and decisions, that one serves only what has
been published, and keeping them in one module is how a filter gets forgotten
and a draft reaches the public.
"""
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_analyst_or_admin, require_roles, require_staff
from app.exceptions import AppException
from app.models.user import User, UserRole
from app.services.advisory import AdvisoryService

router = APIRouter(prefix="/advisories", tags=["Advisories"])

#: Publishing is the act that reaches the public, so it sits with the roles
#: accountable for what the institution says — not with the analyst who ran the
#: model. Proposing is open to whoever may run it.
require_reviewer = require_roles(UserRole.admin, UserRole.regulator)


class AdvisoryPropose(BaseModel):
    run_id: uuid.UUID
    headline: str = Field(..., min_length=8, max_length=200)
    what_it_means: str = Field(
        ..., min_length=20,
        description="Plain language, for someone who has never heard the word "
                    "'conformal'. The hypothetical premise is appended "
                    "automatically and cannot be omitted.")
    what_to_do: Optional[str] = Field(
        None, description="Who to contact, and what a household water test costs.")


class AdvisoryDecision(BaseModel):
    decision: Literal["publish", "reject", "withdraw"]
    note: Optional[str] = None


class AdvisoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    isr_point_id: uuid.UUID
    run_id: uuid.UUID
    status: str
    headline: str
    what_it_means: str
    what_to_do: Optional[str]
    species: str
    time_years: Optional[float]
    restoration_years: Optional[float]
    footprint_ha: Optional[float]
    affected_blocks: Optional[list[dict[str, Any]]]
    proposed_by: Optional[uuid.UUID]
    proposed_at: datetime
    decided_by: Optional[uuid.UUID]
    decided_at: Optional[datetime]
    decision_note: Optional[str]
    published_at: Optional[datetime]
    withdrawn_at: Optional[datetime]


@router.get("", response_model=list[AdvisoryResponse])
async def list_advisories(
    response: Response,
    status: Optional[str] = Query(None),
    isr_point_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Every advisory, in any state. Staff only — this includes unpublished
    drafts, which are internal until a regulator decides otherwise."""
    response.headers["Cache-Control"] = "no-store"
    return await AdvisoryService(db).list(
        status=status, isr_point_id=isr_point_id, limit=limit)


@router.get("/{advisory_id}", response_model=AdvisoryResponse)
async def get_advisory(
    advisory_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        return await AdvisoryService(db).get(advisory_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("", response_model=AdvisoryResponse, status_code=201)
async def propose_advisory(
    payload: AdvisoryPropose,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_analyst_or_admin),
):
    """Propose a completed run for publication.

    Proposing publishes nothing. It puts the screening into a regulator's queue
    with its footprint and the blocks that footprint actually intersects already
    resolved, so the decision is made against real numbers rather than an
    impression of how far the plume went.
    """
    try:
        return await AdvisoryService(db).propose(
            actor=actor, run_id=payload.run_id, headline=payload.headline,
            what_it_means=payload.what_it_means, what_to_do=payload.what_to_do,
            ip=(request.client.host if request.client else None))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{advisory_id}/decision", response_model=AdvisoryResponse)
async def decide_advisory(
    advisory_id: uuid.UUID,
    payload: AdvisoryDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_reviewer),
):
    """Publish, reject or withdraw. Regulator and admin only.

    This is the single point at which anything in this system becomes visible to
    a member of the public, which is why it is one endpoint with one guard
    rather than three convenience routes.
    """
    try:
        return await AdvisoryService(db).decide(
            actor=actor, advisory_id=advisory_id, decision=payload.decision,
            note=payload.note,
            ip=(request.client.host if request.client else None))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
