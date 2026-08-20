"""Simulations, backed by the real ml_pipeline engine.

P0 deleted the stub that fabricated results (a `random.uniform(30, 90)` flow
direction and a constant 0.5733 km² affected area) and left this endpoint
returning 501. P3 wires it to `ml_pipeline` — the engine with 307 tests, an
exact-solution-benchmarked transport kernel and conformally calibrated bands.

A run is queued, executed in the background (~6 s), and polled. Every completed
run records the model card, artifact bundle and git SHA that produced it, so the
number can be re-derived later; `ck_sim_runs_completed_is_pinned` refuses a
completed run that cannot name them.

**What does NOT cross into the engine:** anything from the database. Only the
pin coordinates and the operational sliders. See
`app/services/ml_pipeline_adapter.py` — approved field observations must never
move a contamination model without a deliberate retrain.
"""
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                     Request, status)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (require_admin, require_analyst_or_admin,
                              require_staff)
from app.engine_bounds import BOUNDS as B
from app.exceptions import AppException
from app.models.user import User
from app.schemas.simulation import SimulationResponse
from app.services import audit, run_compare as rc
from app.services.simulation import SimulationService
from app.services.simulation_run import SimulationRunService

router = APIRouter(prefix="/simulations", tags=["Simulations"])

#: Units, so a sweep's y-axis can be labelled. A concentration without its unit
#: is not a number a regulator can act on, and the unit changes with species.
_SPECIES_UNIT = {
    "uranium_ppb": "ppb", "sulfate_mg_l": "mg/L",
    "tds_mg_l": "mg/L", "radium_226_mbq_l": "mBq/L",
}


class RunRequest(BaseModel):
    """What a run may vary. Three fields, and that is the whole surface.

    P2 CUT THIS DOWN FROM TEN. The site location has never come from the body —
    a caller must not run a scenario at a pin the registry does not hold — but
    until now the *operation* did: `injection_rate_m3_day`, `bleed_percent`,
    `operation_years`, `wellfield_width_m`, `monitor_ring_m`, `gradient` and
    `azimuth_deg` were all accepted per run and silently overrode whatever the
    registered site held.

    That defeated migration `0015`, whose entire purpose was that a site IS the
    operation, so that two people running "Jaduguda" run the same thing. With
    the overrides in place they did not: the Studio sent its own hard-coded
    defaults on every run, so the stored site parameters were never used by the
    one screen built to use them.

    What legitimately varies per run is the question being asked of a fixed
    site: **how far out do we look**, and **how long do we sweep afterwards**.
    Everything else is a property of the operation and is changed by editing
    the site — an audited write — not by passing a different number.

    `species` stays because it selects which contaminant to solve for, not how
    the operation is configured.

    Bounds are read from the engine, never retyped (see `app/engine_bounds.py`).
    Both ranges deliberately extend past the trained envelope: the analytical
    engine serves out there correctly and the ML band is FLAGGED as
    extrapolating rather than refused, which is a limitation to report, not to
    clamp away.
    """
    species: str = Field("uranium_ppb")
    time_years: Optional[float] = Field(
        None, ge=B.horizon_min, le=B.horizon_ui_max,
        description="Evaluation horizon — how far past the start to look.")
    restoration_years: Optional[float] = Field(
        None, ge=B.restoration_min, le=B.restoration_ui_max,
        description="Remediation sweep length to test against this site. "
                    "Does not modify the site's own stored value.")


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    isr_point_id: uuid.UUID
    status: str
    engine: str
    species: str
    model_card_sha: Optional[str]
    artifacts_sha: Optional[str]
    code_version: Optional[str]
    request: dict[str, Any]
    metrics: Optional[dict[str, Any]]
    excursion: Optional[dict[str, Any]]
    extrapolation: Optional[list[str]]
    hydro: Optional[dict[str, Any]]
    #: Drawable plume geometry (migration 0016). NULL on runs completed before
    #: P2 and on runs where the engine legitimately produced no extent — the
    #: client distinguishes the two rather than drawing an empty map for both.
    plume: Optional[dict[str, Any]]
    error_message: Optional[str]
    runtime_ms: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]


class RunWithSyncState(RunResponse):
    """A run plus how far the datasets it read lag the approved record.

    Surfaced on the run itself because that is where it matters: a user reading
    a plume needs to know that N approved observations were not part of the
    inputs that produced it."""
    approved_pending_sync: int = 0
    sync_note: Optional[str] = None


async def _run_in_background(run_id: uuid.UUID) -> None:
    from app.database import AsyncSessionLocal, set_rls_context
    async with AsyncSessionLocal() as db:
        # The background task has no request identity, so it runs as the system.
        # It is executing work a permitted caller already authorised at queue
        # time; the audit row records that caller as the actor.
        await set_rls_context(db, bypass=True)
        await SimulationRunService(db, system=True).execute(run_id)


class CompareRunsRequest(BaseModel):
    run_a: uuid.UUID
    run_b: uuid.UUID


# Declared BEFORE `POST /{isr_id}` for the same reason as `/compare`.
@router.post("/reap")
async def reap_runs(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    """Fail simulations abandoned by a restart. Admin only.

    Also runs automatically at startup. Exposed as well because a restart is not
    the only way to strand one, and because a stuck spinner is the kind of thing
    somebody wants to clear without waiting for a deploy.
    """
    from app.services.simulation_run import reap_orphaned_runs
    return await reap_orphaned_runs(db)


# Declared BEFORE `POST /{isr_id}`: FastAPI matches in declaration order,
# so a later registration would have "compare" parsed as an isr_id UUID.
@router.post("/compare")
async def compare_runs(
    payload: CompareRunsRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_staff),
):
    """Diff two stored runs and attribute the difference.

    Works across ISR sites, which `POST /scenarios/{id}/compare` could not:
    runs saved from the Console carry `scenario_id = NULL`, so the scenario route
    needed a scenario id that does not exist for exactly the comparison an
    analyst wants — this site versus that one.

    Both runs must be `completed`. An incomplete run has no metrics, and saying
    so beats returning a diff full of nulls.
    """
    svc = SimulationRunService(db)
    try:
        a = await svc.get(payload.run_a)
        b = await svc.get(payload.run_b)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    for r in (a, b):
        if r.status != "completed":
            raise HTTPException(
                status_code=409,
                detail=(f"Run {r.id} is '{r.status}'; only completed runs can be "
                        f"compared."))
    if a.id == b.id:
        raise HTTPException(status_code=400,
                            detail="Pick two different runs to compare.")
    return rc.diff(a, b)


@router.post("/{isr_id}", response_model=RunResponse,
             status_code=status.HTTP_202_ACCEPTED)
async def trigger_simulation(
    isr_id: uuid.UUID,
    payload: RunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_analyst_or_admin),
):
    """Queue a run against a registered ISR point. Poll `GET /simulations/runs/{id}`."""
    try:
        run = await SimulationRunService(db).create(
            actor=actor, isr_id=isr_id,
            params=payload.model_dump(exclude_none=True),
            ip=(request.client.host if request.client else None))
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    background_tasks.add_task(_run_in_background, run.id)
    return run


class SweepRequest(BaseModel):
    """Sweep one axis against a fixed site, to answer a shape question.

    P3. Two questions this product exists to answer are not answerable one run
    at a time:

      * *"How many years of restoration is enough?"* — a single sweep length
        gives one number with nothing to compare it against. The answer is the
        SHAPE of residual contamination against sweep length, and the year the
        curve crosses the screening limit.
      * *"How does contamination change over the evaluation period?"* — likewise
        a curve, not a point.

    Making a user re-run six times and remember six numbers is how you get a
    conclusion drawn from whichever run they happened to look at last.

    NOT PERSISTED, and deliberately so. A sweep is a diagnostic over a site, not
    a result about it: writing 12 rows into `simulation_runs` for every question
    would bury the runs a regulator is meant to read. The point a user decides
    to keep is stored the normal way, with its provenance.

    The cost was measured before this was designed rather than assumed: a warm
    engine call is ~0.26 s, so a 6-point sweep is ~1.6 s and the cap of 12 is
    ~3 s — inside a request. The often-quoted "5–15 s per run" is the queue,
    background-task and provenance overhead of a *stored* run, not the physics.
    """
    axis: Literal["restoration", "evaluation"]
    species: str = Field("uranium_ppb")
    points: int = Field(6, ge=2, le=12,
                        description="Samples along the axis, endpoints included.")
    #: The value held FIXED on the other axis. Restoration adequacy is
    #: conditional on when you look, and vice versa — so the held value is an
    #: input, never an implicit default the reader cannot see.
    time_years: Optional[float] = Field(
        None, ge=B.horizon_min, le=B.horizon_ui_max)
    restoration_years: Optional[float] = Field(
        None, ge=B.restoration_min, le=B.restoration_ui_max)
    #: Upper end of the swept axis. Defaults to the engine's UI exploration max.
    max_value: Optional[float] = Field(None, ge=0)


class SweepPoint(BaseModel):
    value: float
    area_ha: Optional[float] = None
    migration_m: Optional[float] = None
    compliance_conc: Optional[float] = None
    excursion_declared: Optional[bool] = None
    source_zone_above_threshold: Optional[bool] = None
    residual_fraction: Optional[float] = None
    extrapolating: bool = False
    error: Optional[str] = None


class SweepResponse(BaseModel):
    persisted: bool = False
    persistence_note: str
    axis: str
    species: str
    unit: str
    held: dict[str, Any]
    points: list[SweepPoint]
    #: The smallest swept value at which nothing remains above the screening
    #: limit, or None if the curve never gets there within the swept range.
    crossing_value: Optional[float] = None
    crossing_note: str


@router.post("/{isr_id}/sweep", response_model=SweepResponse)
async def sweep_simulation(
    isr_id: uuid.UUID,
    payload: SweepRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_analyst_or_admin),
):
    """Run the engine across one axis against a registered site."""
    from app.services import ml_pipeline_adapter as mlp
    from app.services.simulation_run import SimulationRunService as _S

    try:
        site = await _S(db)._site(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    if payload.axis == "restoration":
        top = payload.max_value if payload.max_value is not None else B.restoration_ui_max
        # No `horizon_default` exists in the engine bounds, and inventing one
        # here would be a fabricated modelling choice. The trained maximum is
        # the defensible fallback: it is the furthest the ML band is guaranteed
        # at, so a restoration curve read there is the one with the strongest
        # claim behind it.
        held = {"time_years": payload.time_years
                if payload.time_years is not None else B.horizon_trained_max}
        varied = "restoration_years"
    else:
        top = payload.max_value if payload.max_value is not None else B.horizon_ui_max
        held = {"restoration_years": payload.restoration_years
                if payload.restoration_years is not None else (site.restoration_years or 0.0)}
        varied = "time_years"

    n = payload.points
    step = top / (n - 1) if n > 1 else 0.0
    values = [round(i * step, 3) for i in range(n)]

    results: list[SweepPoint] = []
    for v in values:
        overrides = {"species": payload.species, varied: v, **held}
        try:
            r = await mlp.predict(mlp.payload_from_site(site, overrides=overrides))
        except Exception as exc:  # noqa: BLE001
            # One bad point must not lose the other eleven. The curve renders
            # with a gap and says why, rather than failing the whole question.
            results.append(SweepPoint(value=v, error=f"{type(exc).__name__}: {exc}"))
            continue
        an = (r.get("metrics") or {}).get("analytical") or {}
        sz = (r.get("plume") or {}).get("source_zone") or {}
        results.append(SweepPoint(
            value=v,
            area_ha=an.get("area_ha"),
            migration_m=an.get("migration_m"),
            compliance_conc=an.get("compliance_conc"),
            excursion_declared=bool((r.get("isr_excursion") or {}).get("excursion_declared")),
            source_zone_above_threshold=sz.get("above_threshold"),
            residual_fraction=(r.get("restoration") or {}).get("residual_endpoint_fraction"),
            extrapolating=bool(r.get("extrapolation")),
        ))

    crossing = next((p.value for p in results
                     if p.error is None and (p.area_ha or 0) <= 0), None)

    if payload.axis == "restoration":
        note = (
            f"The shortest swept restoration length at which the model shows no "
            f"area above the screening limit, evaluated at "
            f"{held['time_years']} yr. This is conditional on that horizon — "
            f"a sweep that looks sufficient at one evaluation year need not be "
            f"at another, so the horizon is stated rather than assumed."
            if crossing is not None else
            f"Within 0–{top:g} yr of sweeping, the model never shows the footprint "
            f"falling below the screening limit at a {held['time_years']} yr "
            f"horizon. That is a result, not a missing answer.")
    else:
        note = (
            f"The evaluation year by which the model shows no area above the "
            f"screening limit, with a {held['restoration_years']} yr sweep."
            if crossing is not None else
            f"Across 0–{top:g} yr of evaluation the footprint does not fall below "
            f"the screening limit with a {held['restoration_years']} yr sweep.")

    await audit.record(
        action="simulation.sweep", entity_type="isr-points", entity_id=str(isr_id),
        actor_id=actor.id, actor_label=actor.email,
        detail={"axis": payload.axis, "species": payload.species,
                "points": n, "max_value": top, "held": held},
    )

    return SweepResponse(
        persistence_note=(
            "A sweep is a diagnostic over this site, not a result about it, and "
            "is not stored. Run and store the point you want to keep — that run "
            "carries the model card, artifact bundle and code version."),
        axis=payload.axis, species=payload.species,
        unit=_SPECIES_UNIT.get(payload.species, ""),
        held=held, points=results,
        crossing_value=crossing, crossing_note=note,
    )


@router.get("/runs/{run_id}", response_model=RunWithSyncState)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    try:
        run = await SimulationRunService(db).get(run_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # The split-brain, made visible at the point it matters. A plume is read as
    # "what we know"; if approved observations were not in the inputs that
    # produced it, the reader has to be told here, not in a settings screen.
    from app.services.dataset_sync import pending_summary
    summary = await pending_summary(db)
    n = summary["approved_pending_sync"]
    out = RunWithSyncState.model_validate(run, from_attributes=True)
    out.approved_pending_sync = n
    out.sync_note = (
        f"{n} approved field observation(s) are not yet in Datasets/, so they "
        f"were not part of the inputs to this run." if n else None)
    return out


@router.get("/runs", response_model=list[RunResponse])
async def list_runs(
    isr_id: uuid.UUID = Query(...),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    return await SimulationRunService(db).list_for_isr(isr_id, limit=limit)


@router.get("/{sim_id}", response_model=SimulationResponse)
async def get_legacy_simulation(
    sim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_staff),
):
    """Rows written by the pre-P0 engine. Retained so historical ids still
    resolve; nothing writes here any more."""
    try:
        return await SimulationService(db).get(sim_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
