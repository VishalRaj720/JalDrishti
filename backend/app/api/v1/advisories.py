"""Advisories — proposing a screening, and the decision on it.

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
from app.dependencies import (require_analyst_or_admin, require_reviewer,
                              require_staff)
from app.exceptions import AppException
from app.models.user import User, UserRole
from app.services.advisory import AdvisoryService

router = APIRouter(prefix="/advisories", tags=["Advisories"])

# Publishing is the act that reaches the public, so it sits with the role
# accountable for what the institution says — not with the analyst who ran the
# model. Proposing is open to whoever may run it.
#
# R7 retired `regulator`, so `require_reviewer` now resolves to admin alone. The
# separation that mattered is unchanged: the proposer and the decider are still
# different people, enforced by `ck_advisory_published_has_a_decider`.


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
    drafts, which are internal until a reviewer decides otherwise."""
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

    Proposing publishes nothing. It puts the screening into a reviewer's queue
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
    """Publish, reject or withdraw. Admin only.

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


# ── one-step publication: run, save, propose, decide ─────────────────


class PublishRunRequest(BaseModel):
    """Publish a screening in one action, saving the run that backs it.

    THE WORKFLOW THIS REPLACES. Publishing used to take four deliberate steps:
    run a preview, press *Save this run*, press *Propose*, then find the
    proposal and press *Publish*. Every step was defensible on its own and the
    sequence was not: the analyst had already decided at step one, and the three
    that followed were bookkeeping the product made them perform by hand.

    WHAT IS NOT BEING RELAXED. The run is still **saved before** the advisory
    exists, because an advisory cites a run and a citation must point at
    something durable — a published statement backed by a preview nobody kept is
    unfalsifiable. Saving is now a consequence of publishing rather than a
    prerequisite the user has to remember, which is the same guarantee reached
    by a shorter road.

    WHAT IS STILL SEPARATE. Proposing and deciding remain two records with two
    actors. An analyst calling this gets a *proposal*; only an admin's call
    carries through to published, and `ck_advisory_published_has_a_decider`
    still holds. The four-step route also still works — this is an additional
    door, not a replacement, so nothing that already links to it breaks.
    """
    isr_point_id: uuid.UUID
    #: Omit to publish a run that is already stored; supply to run a fresh one.
    run_id: Optional[uuid.UUID] = None
    species: Optional[str] = None
    time_years: Optional[float] = None
    restoration_years: Optional[float] = None

    headline: str = Field(..., min_length=8, max_length=200)
    what_it_means: str = Field(..., min_length=20)
    what_to_do: Optional[str] = None


class PublishRunResponse(BaseModel):
    advisory: AdvisoryResponse
    run_id: uuid.UUID
    #: True when this call created and stored the run, rather than reusing one.
    run_was_saved: bool
    #: False for an analyst — the advisory is queued, not public.
    published: bool
    note: str


@router.post("/publish-run", response_model=PublishRunResponse, status_code=201)
async def publish_run(
    payload: PublishRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_analyst_or_admin),
):
    """Run the engine, store the run, and publish it — one call.

    The engine runs **inline** rather than as a background task. `POST
    /simulations/{isr_id}` returns 202 and expects the client to poll, which is
    right when the client wants a run; it is wrong here, because the caller has
    asked for a *publication* and cannot be told "queued" about something that
    either reaches residents or does not. A screening run is seconds of
    analytical work, and the caller waits for it.

    A run that fails leaves its failed row behind and publishes nothing. That is
    deliberate: the attempt is part of the record, and an advisory whose run
    errored is exactly the thing this must never create.
    """
    from app.database import set_rls_context
    from app.services.simulation_run import SimulationRunService

    async def _reidentify() -> None:
        """Put the caller's identity back after a commit dropped it.

        `set_rls_context` uses `SET LOCAL`, which Postgres discards at COMMIT.
        That is the correct choice — a plain SET would leak one request's
        identity into the next through the connection pool — but it means any
        route that commits and then keeps querying is anonymous from that point
        on, and every RLS-protected table simply returns nothing.

        No other route noticed: they all commit as their last act. This one
        creates a run, executes it, proposes and decides, so it crosses the
        boundary four times. Found by the run vanishing between `create` and
        `execute` with a 404 naming an id that had just been inserted.
        """
        await set_rls_context(
            db, role=actor.role.value,
            org_id=(str(actor.org_id) if actor.org_id else None),
            user_id=str(actor.id))

    svc = SimulationRunService(db)
    ip = request.client.host if request.client else None
    run_was_saved = False

    if payload.run_id is not None:
        try:
            run = await svc.get(payload.run_id)
        except AppException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if run.isr_point_id != payload.isr_point_id:
            raise HTTPException(
                status_code=400,
                detail="That run belongs to a different site. An advisory names "
                       "one location and must cite a run from it.")
    else:
        params = {k: v for k, v in {
            "species": payload.species,
            "time_years": payload.time_years,
            "restoration_years": payload.restoration_years,
        }.items() if v is not None}
        try:
            run = await svc.create(actor=actor, isr_id=payload.isr_point_id,
                                   params=params, ip=ip)
        except AppException as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        run_was_saved = True
        await _reidentify()

        # Executed in ITS OWN session with the system context, which is exactly
        # what `POST /simulations/{isr_id}` queues as a background task. Running
        # it on the request session instead would need RLS bypass for the engine
        # writes and would leave the rest of this request — the propose and the
        # decide — running with elevated privileges it must not have.
        from app.api.v1.simulations import _run_in_background
        await _run_in_background(run.id)   # never raises; records failure on the run

        # The other session committed; this one must be told to look again
        # rather than trust the copy in its identity map. `refresh` re-SELECTs
        # this one object — `expire_all()` would also expire `actor`, whose next
        # attribute access then triggers a lazy reload outside the async
        # greenlet and raises MissingGreenlet instead of doing anything useful.
        await _reidentify()
        await db.refresh(run)

    if run.status != "completed":
        raise HTTPException(
            status_code=422,
            detail=(f"The run did not complete ({run.status}), so there is "
                    f"nothing to publish. "
                    f"{run.error_message or 'The engine reported no result.'} "
                    f"The failed run has been kept as run {run.id}."))

    try:
        adv = await AdvisoryService(db).propose(
            actor=actor, run_id=run.id, headline=payload.headline,
            what_it_means=payload.what_it_means,
            what_to_do=payload.what_to_do, ip=ip)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    published = False
    if actor.role == UserRole.admin:
        await _reidentify()          # `propose` committed; see _reidentify
        try:
            adv = await AdvisoryService(db).decide(
                actor=actor, advisory_id=adv.id, decision="publish",
                note="Published in one step from the Console.", ip=ip)
            published = True
        except AppException as e:
            # The proposal survives a failed decision — it is a real record and
            # can be decided from the review queue. Losing it would be worse.
            raise HTTPException(
                status_code=e.status_code,
                detail=(f"{e.message} The advisory was saved as a proposal "
                        f"({adv.id}) and can be published from the review queue."))

    return PublishRunResponse(
        advisory=AdvisoryResponse.model_validate(adv),
        run_id=run.id,
        run_was_saved=run_was_saved,
        published=published,
        note=("Published. The run behind it was saved automatically, so the "
              "statement cites a stored result."
              if published else
              "Saved and sent for review. It is not public until an "
              "administrator publishes it."),
    )
