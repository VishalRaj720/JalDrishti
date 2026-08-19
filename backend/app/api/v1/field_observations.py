"""Field-observation submissions and their review.

Who can do what (see `docs/roles.md`):

    submit / withdraw own   field_officer, admin
    read the queue          admin, regulator, analyst; field_officer sees only
                            their own, enforced by RLS rather than by a filter
    approve / reject        admin, regulator -- and never one's own submission
    map overlay             staff; pending and authoritative are returned in
                            SEPARATE collections so a client cannot merge them
                            by accident

`POST /field-observations` is the ONLY way a field officer can change map data.
They hold no write access to `water_samples`, `groundwater_level_readings` or
`ore_observations`, at the API or in Postgres.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (require_regulator_or_admin, require_staff,
                              require_field_upload)
from app.exceptions import AppException
from app.models.field_observation import FieldObservation
from app.models.user import User
from app.services.field_observation import FieldObservationService

router = APIRouter(prefix="/field-observations", tags=["Field Observations"])


class ObservationSubmit(BaseModel):
    observation_type: str = Field(
        ..., description="water_sample | groundwater_level | ore_presence")
    operation: str = Field("create", description="create | update | delete")
    target_id: Optional[uuid.UUID] = Field(
        None, description="Required for update/delete; forbidden for create")
    payload: Optional[dict[str, Any]] = None
    note: Optional[str] = None


class ReviewDecision(BaseModel):
    review_note: Optional[str] = None


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    observation_type: str
    operation: str
    target_table: str
    target_id: Optional[uuid.UUID]
    proposed: Optional[dict[str, Any]]
    previous: Optional[dict[str, Any]]
    note: Optional[str]
    status: str
    submitted_by: uuid.UUID
    submitted_at: datetime
    reviewed_by: Optional[uuid.UUID]
    reviewed_at: Optional[datetime]
    review_note: Optional[str]
    applied_id: Optional[uuid.UUID]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("", response_model=ObservationResponse,
             status_code=status.HTTP_201_CREATED)
async def submit_observation(
    payload: ObservationSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_field_upload),
):
    """Submit a field observation. It enters `pending` and changes nothing yet."""
    try:
        return await FieldObservationService(db).submit(
            actor=actor, observation_type=payload.observation_type,
            operation=payload.operation, payload=payload.payload,
            target_id=payload.target_id, note=payload.note, ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("", response_model=list[ObservationResponse])
async def list_observations(
    status_filter: Optional[str] = Query(None, alias="status"),
    observation_type: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """List proposals. A field officer sees only their own — enforced by the
    `field_obs_read` RLS policy, not by a WHERE clause here."""
    return await FieldObservationService(db).list(
        status=status_filter, observation_type=observation_type,
        limit=limit, offset=offset)


@router.get("/map")
async def observations_map(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Map overlay, in the three states the UI must distinguish.

    Three collections rather than one list with a flag. A merged list invites a
    client to draw unreviewed field input, or approved-but-not-yet-modelled
    input, as though it were confirmed and in the model — the exact confusion
    this workflow exists to prevent.

        pending_review        red    — awaiting a reviewer. Changes nothing.
        approved_pending_sync amber  — authoritative in the portal, NOT yet in
                                       `Datasets/`, so a simulation at that point
                                       still ignores it.
        approved_in_model     green  — synced; the engine now sees it.
    """
    pending_review = (await db.execute(text("""
        SELECT id::text, observation_type, operation, submitted_at,
               ST_X(location::geometry) AS lon, ST_Y(location::geometry) AS lat
        FROM field_observations
        WHERE status = 'pending' AND location IS NOT NULL
    """))).mappings().all()

    # Ore rows carry their sync state through the observation that produced them.
    ore = (await db.execute(text("""
        SELECT o.id::text, o.name, o.ore_zone, o.uranium_grade_pct, o.observed_at,
               ST_X(o.location::geometry) AS lon,
               ST_Y(o.location::geometry) AS lat,
               f.synced_to_dataset_at, f.dataset_sync_ref
        FROM ore_observations o
        LEFT JOIN field_observations f ON f.id = o.origin_observation_id
    """))).mappings().all()

    amber = [dict(r) for r in ore if r["synced_to_dataset_at"] is None]
    green = [dict(r) for r in ore if r["synced_to_dataset_at"] is not None]

    return {
        "pending_review": [dict(r) for r in pending_review],
        "approved_pending_sync": amber,
        "approved_in_model": green,
        "legend": {
            "pending_review": "red — awaiting review; changes nothing",
            "approved_pending_sync": ("amber — approved and authoritative here, "
                                      "but not yet in Datasets/, so the physics "
                                      "engine and surrogate do not see it"),
            "approved_in_model": "green — approved and reflected in the model",
        },
        "counts": {"pending_review": len(pending_review),
                   "approved_pending_sync": len(amber),
                   "approved_in_model": len(green)},
    }


@router.get("/targets")
async def submission_targets(
    observation_type: str = Query(..., description="water_sample | groundwater_level"),
    q: Optional[str] = Query(None, description="filter by name or district"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """The wells / stations a submission can attach itself to.

    WHY THIS EXISTS. A chemistry sample belongs to a monitoring **well** and a
    level reading belongs to a monitoring **station**; neither can be submitted
    without naming one. The submission form said so and stopped there — "the
    picker is not implemented" — which is why two of the three observation types
    were unsubmittable.

    Deliberately narrow. R11 deleted the generic `/monitoring-stations` CRUD
    because nothing reached it and it was a second write path onto reference
    geography. This is not that returning: it is read-only, it returns only what
    a picker needs (id, name, where it is, and how recently it was sampled), and
    it has no create/update/delete beside it.

    `last_sampled` is included because it is the field officer's own signal about
    where a fresh sample is worth taking — the same "when did anyone last look
    here" question the monitoring recommendations answer at block scale.
    """
    if observation_type == "water_sample":
        sql = """
            SELECT w.id::text, w.name, w.latitude, w.longitude,
                   b.name AS block, d.name AS district,
                   count(s.id)                          AS samples,
                   max(s.sampled_at)                    AS last_sampled,
                   count(s.uranium_ppb)                 AS uranium_tests
            FROM monitoring_wells w
            LEFT JOIN blocks b        ON b.id = w.block_id
            LEFT JOIN districts d     ON d.id = b.district_id
            LEFT JOIN water_samples s ON s.well_id = w.id
            WHERE (CAST(:q AS text) IS NULL
                   OR w.name ILIKE '%' || CAST(:q AS text) || '%'
                   OR d.name ILIKE '%' || CAST(:q AS text) || '%')
            GROUP BY w.id, w.name, w.latitude, w.longitude, b.name, d.name
            ORDER BY d.name NULLS LAST, w.name
            LIMIT :lim
        """
    elif observation_type == "groundwater_level":
        sql = """
            SELECT st.id::text, st.name, st.latitude, st.longitude,
                   b.name AS block, d.name AS district,
                   count(r.id)              AS samples,
                   max(r.recorded_at)       AS last_sampled,
                   0                        AS uranium_tests
            FROM monitoring_stations st
            LEFT JOIN blocks b    ON b.id = st.block_id
            LEFT JOIN districts d ON d.id = b.district_id
            LEFT JOIN groundwater_level_readings r ON r.station_id = st.id
            WHERE (CAST(:q AS text) IS NULL
                   OR st.name ILIKE '%' || CAST(:q AS text) || '%'
                   OR d.name ILIKE '%' || CAST(:q AS text) || '%')
            GROUP BY st.id, st.name, st.latitude, st.longitude, b.name, d.name
            ORDER BY d.name NULLS LAST, st.name
            LIMIT :lim
        """
    else:
        raise HTTPException(
            status_code=400,
            detail=("targets exist only for water_sample (wells) and "
                    "groundwater_level (stations). An ore sighting is a point on "
                    "the map and attaches to nothing."))

    rows = (await db.execute(text(sql), {"q": q, "lim": limit})).mappings().all()
    return {
        "observation_type": observation_type,
        "target": "monitoring_well" if observation_type == "water_sample"
                  else "monitoring_station",
        "count": len(rows),
        "items": [dict(r) for r in rows],
    }


@router.get("/{obs_id}", response_model=ObservationResponse)
async def get_observation(
    obs_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    try:
        return await FieldObservationService(db).get(obs_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{obs_id}/withdraw", response_model=ObservationResponse)
async def withdraw_observation(
    obs_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_field_upload),
):
    try:
        return await FieldObservationService(db).withdraw(
            actor=actor, obs_id=obs_id, ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{obs_id}/approve", response_model=ObservationResponse)
async def approve_observation(
    obs_id: uuid.UUID,
    decision: ReviewDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_regulator_or_admin),
):
    """Approve and apply. The submitter cannot reach this even as a reviewer:
    the service refuses, and `ck_field_obs_no_self_review` makes the row
    unrepresentable regardless."""
    try:
        return await FieldObservationService(db).approve(
            actor=actor, obs_id=obs_id, review_note=decision.review_note,
            ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/{obs_id}/reject", response_model=ObservationResponse)
async def reject_observation(
    obs_id: uuid.UUID,
    decision: ReviewDecision,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_regulator_or_admin),
):
    try:
        return await FieldObservationService(db).reject(
            actor=actor, obs_id=obs_id, review_note=decision.review_note,
            ip=_ip(request))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
