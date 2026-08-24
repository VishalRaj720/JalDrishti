"""Concentration and extent through the operation's whole life.

R4. The sweep endpoint answers "how does the ANSWER change as I change an
input". This answers a different question the product could not answer at all:
**what happens over time at one fixed set of inputs** — during injection, during
the remediation sweep, and for the decades afterwards.

WHAT THE MODEL ACTUALLY DOES. Measured against the engine before this was
designed, because the intuitive shape and the modelled shape differ in two ways
that matter, and plotting the intuitive one would have been wrong:

  * **Source concentration does NOT climb during operation — it is flat.** That
    is what injection is: the leach solution is held at strength. A verified
    Singhbhum run holds 14,294 ppb for the full ten years. What grows during
    operation is the affected AREA (0 → 9.8 ha).
  * **After restoration it does not decay away either.** It is HELD at the
    engine's rebound floor (14,294 → 4,639 under a 2-year sweep, then flat for
    the next 38 years), because residual uranium can re-oxidise rather than
    continue cleaning up. Meanwhile MIGRATION keeps growing — 0.2 m at closure
    to 12.7 m at 50 years — because hydraulic containment stops when the
    operation does.

So a single "concentration" line would be flat for a decade and read as a broken
chart. Three series are returned per species and the caller plots them together.

Phase boundaries come from the same numbers `front_position` uses, so a label
can never disagree with the physics it is describing.
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_simulation_roles
from app.engine_bounds import BOUNDS as B
from app.exceptions import AppException
from app.models.user import User
from app.services import audit

router = APIRouter(prefix="/simulations", tags=["Simulations"])

#: Units, so each series can label its own axis. A concentration without its
#: unit is not a number anyone can act on, and the unit changes with species.
SPECIES_UNIT = {
    "uranium_ppb": "ppb", "sulfate_mg_l": "mg/L",
    "tds_mg_l": "mg/L", "radium_226_mbq_l": "mBq/L",
}


class LifecycleRequest(BaseModel):
    species: list[str] = Field(
        default_factory=lambda: list(SPECIES_UNIT),
        description="Contaminants to trace. Defaults to all four.")
    time_years: float = Field(50.0, ge=B.horizon_min, le=B.horizon_ui_max,
                              description="Total evaluation horizon.")
    restoration_years: float = Field(0.0, ge=B.restoration_min,
                                     le=B.restoration_ui_max)
    points: int = Field(12, ge=4, le=24,
                        description="Samples across the horizon, per species.")


class LifecyclePoint(BaseModel):
    year: float
    phase: str
    source_conc: Optional[float] = None
    area_ha: Optional[float] = None
    migration_m: Optional[float] = None
    compliance_conc: Optional[float] = None
    excursion_declared: Optional[bool] = None
    shallow_impact_probability: Optional[float] = None
    extrapolating: bool = False
    error: Optional[str] = None


class LifecycleSeries(BaseModel):
    species: str
    unit: str
    threshold: Optional[float] = None
    #: The engine's own words when it refuses a source term (a non-ore zone for
    #: uranium). Carried per species so the chart can say why one line is flat
    #: at zero while the others are not.
    suppressed: Optional[str] = None
    points: list[LifecyclePoint]


class LifecycleResponse(BaseModel):
    persisted: bool = False
    persistence_note: str
    operation_years: float
    restoration_years: float
    time_years: float
    phases: list[dict[str, Any]]
    series: list[LifecycleSeries]
    reading_note: str


def _phase_of(year: float, op: float, rest: float) -> str:
    if year <= op:
        return "operation"
    if year <= op + rest:
        return "restoration"
    return "post_closure"


@router.post("/{isr_id}/lifecycle", response_model=LifecycleResponse)
async def lifecycle(
    isr_id: uuid.UUID,
    payload: LifecycleRequest,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_simulation_roles),
):
    """Trace every contaminant across operation → restoration → post-closure."""
    from app.services import ml_pipeline_adapter as mlp
    from app.services.simulation_run import SimulationRunService as _S

    try:
        site = await _S(db)._site(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    op = float(site.operation_years or 0.0)
    rest = float(payload.restoration_years)
    horizon = float(payload.time_years)

    # Sample the horizon, but FORCE a sample at each phase boundary and just
    # after it. Without that the chart can step straight over the restoration
    # drop — the single most informative feature on it — and appear to show
    # nothing happening at all.
    n = payload.points
    step = horizon / (n - 1) if n > 1 else 0.0
    years: set[float] = {round(i * step, 3) for i in range(n)}
    for edge in (op, op + rest):
        if 0 <= edge <= horizon:
            years.add(round(edge, 3))
            years.add(round(min(edge + max(step * 0.02, 0.05), horizon), 3))
    ordered = sorted(years)

    series: list[LifecycleSeries] = []
    for sp in payload.species:
        if sp not in SPECIES_UNIT:
            continue
        pts: list[LifecyclePoint] = []
        suppressed: Optional[str] = None
        threshold: Optional[float] = None

        for y in ordered:
            overrides = {"species": sp, "time_years": y, "restoration_years": rest}
            try:
                r = await mlp.predict(mlp.payload_from_site(site, overrides=overrides))
            except Exception as exc:  # noqa: BLE001
                # One bad point must not lose the rest of the trace. The chart
                # renders a gap and says why, rather than failing the question.
                pts.append(LifecyclePoint(year=y, phase=_phase_of(y, op, rest),
                                          error=f"{type(exc).__name__}: {exc}"))
                continue

            an = (r.get("metrics") or {}).get("analytical") or {}
            sz = (r.get("plume") or {}).get("source_zone") or {}
            vert = r.get("vertical") or {}
            if threshold is None:
                threshold = r.get("threshold")
            if r.get("notice") and suppressed is None:
                suppressed = r["notice"]

            pts.append(LifecyclePoint(
                year=y,
                # The engine's own phase label where it gave one; otherwise the
                # same boundaries it uses internally.
                phase=((r.get("timeline") or {}).get("phase")
                       or _phase_of(y, op, rest)),
                source_conc=sz.get("conc"),
                area_ha=an.get("area_ha"),
                migration_m=an.get("migration_m"),
                compliance_conc=an.get("compliance_conc"),
                excursion_declared=bool(
                    (r.get("isr_excursion") or {}).get("excursion_declared")),
                shallow_impact_probability=vert.get("shallow_impact_probability"),
                extrapolating=bool(r.get("extrapolation")),
            ))

        series.append(LifecycleSeries(
            species=sp, unit=SPECIES_UNIT[sp], threshold=threshold,
            suppressed=suppressed, points=pts))

    await audit.record(
        action="simulation.lifecycle", entity_type="isr-points",
        entity_id=str(isr_id), actor_id=actor.id, actor_label=actor.email,
        detail={"species": payload.species, "time_years": horizon,
                "restoration_years": rest, "points": len(ordered)},
    )

    return LifecycleResponse(
        persistence_note=(
            "A lifecycle trace is a diagnostic over this site, not a result "
            "about it, and is not stored. Save the run you want to keep."),
        operation_years=op, restoration_years=rest, time_years=horizon,
        phases=[
            {"phase": "operation", "from": 0.0, "to": min(op, horizon),
             "label": "Injection and capture",
             "note": "Source strength is held constant — that is what injection "
                     "does. What grows is the affected area."},
            {"phase": "restoration", "from": min(op, horizon),
             "to": min(op + rest, horizon),
             "label": "Restoration sweep",
             "note": ("Source strength falls as the sweep flushes the leach zone."
                      if rest > 0 else
                      "No remediation sweep is planned for this run, so there is "
                      "no restoration phase.")},
            {"phase": "post_closure", "from": min(op + rest, horizon), "to": horizon,
             "label": "Post-closure drift",
             "note": "Source strength is HELD at the demonstrated stable endpoint "
                     "rather than decaying further — residual uranium can "
                     "re-oxidise. Migration keeps growing because hydraulic "
                     "containment stops when the operation does."},
        ],
        series=series,
        reading_note=(
            "Read the three series together. Source strength is flat during "
            "injection and falls only under a restoration sweep; the affected "
            "area grows during injection; migration distance grows after "
            "closure, once containment stops holding the front."),
    )
