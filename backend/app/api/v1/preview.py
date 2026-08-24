"""Running a registered site without storing the result.

R5. Until now `POST /simulations/{id}` was the only way to run a registered
site, and it always persisted — queued a row, executed in a background task,
polled, and wrote a provenance-pinned record. So exploring "what does 12 years
look like? what about 18?" left a trail of runs nobody meant to keep, and the
run history stopped being a record of decisions and became a log of curiosity.

The fix is to separate the two things that were conflated:

  **Preview** (here)  — run it, look at it, throw it away. Synchronous, because
  the physics is fast: a warm engine call is ~0.26 s, so there is nothing to
  queue and nothing to poll. Returns the full engine response including plume
  geometry, so a preview draws exactly what a stored run draws.

  **Save** (`POST /simulations/{id}`) — the deliberate act of keeping one. That
  is where the model card, artifact bundle and git SHA get pinned, because those
  only mean something for a result somebody chose to stand behind.

WHY THE STORED PATH KEEPS ITS QUEUE. It could now be synchronous too. It is not,
because the queue is what gives a stored run its own row and status *before* the
engine runs — which is what makes a crashed or hung run visible rather than
silently absent. A preview that fails just fails; a saved run that fails must
leave evidence.

The same rule as everywhere else applies: only species, evaluation horizon and
restoration sweep may vary. The operation belongs to the site.
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

router = APIRouter(prefix="/simulations", tags=["Simulations"])


class PreviewRequest(BaseModel):
    """The three things a run may vary — identical to `RunRequest`.

    Deliberately a separate class rather than a shared import: these two
    endpoints are allowed to diverge (a preview could gain a debug flag a stored
    run must never have), and a shared model would make that divergence look
    like a mistake rather than a decision.
    """
    species: str = Field("uranium_ppb")
    time_years: Optional[float] = Field(None, ge=B.horizon_min, le=B.horizon_ui_max)
    restoration_years: Optional[float] = Field(
        None, ge=B.restoration_min, le=B.restoration_ui_max)


@router.post("/{isr_id}/preview")
async def preview_run(
    isr_id: uuid.UUID,
    payload: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_simulation_roles),
) -> dict[str, Any]:
    """Run a registered site and return the result WITHOUT storing it."""
    from app.services import ml_pipeline_adapter as mlp
    from app.services.simulation_run import SimulationRunService as _S, _plume_geometry

    try:
        site = await _S(db)._site(isr_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    overrides = {k: v for k, v in payload.model_dump().items() if v is not None}
    try:
        result = await mlp.predict(mlp.payload_from_site(site, overrides=overrides))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"Engine call failed: {type(exc).__name__}: {exc}")

    # Shaped like a stored run so the client renders both through one path. A
    # preview that had to be displayed by different code would eventually look
    # different from the thing it is previewing, which defeats the point.
    return {
        "persisted": False,
        "persistence_note": (
            "This run was not stored. Save it to pin the model card, artifact "
            "bundle and code version that produced it — that is what makes a "
            "number re-derivable later."),
        "isr_point_id": str(isr_id),
        "status": "completed",
        "species": result.get("species") or payload.species,
        "request": overrides,
        "metrics": result.get("metrics"),
        "excursion": result.get("isr_excursion"),
        "extrapolation": list(result.get("extrapolation") or []),
        "hydro": result.get("hydro"),
        "plume": _plume_geometry(result),
        # Everything the Console renders beyond the plume itself. Returned whole
        # rather than cherry-picked: the engine owns which caveats apply, and a
        # client-side subset is how a caveat silently stops being shown.
        "vertical": result.get("vertical"),
        "timeline": result.get("timeline"),
        "restoration": result.get("restoration"),
        "containment": result.get("containment"),
        "notice": result.get("notice"),
        "far_field_note": result.get("far_field_note"),
        "ore_zone": result.get("ore_zone"),
        "nearest_river_km": result.get("nearest_river_km"),
        "river_crossing": result.get("river_crossing"),
        "azimuth_deg": result.get("azimuth_deg"),
        "azimuth_source": result.get("azimuth_source"),
        "wellfield_geometry": result.get("wellfield_geometry"),
        "threshold": result.get("threshold"),
        "ml_status": result.get("ml_status"),
        "ml_envelope": result.get("ml_envelope"),
        "ml_envelope_skipped": result.get("ml_envelope_skipped"),
        "disagreement": result.get("disagreement"),
        "beta_override": result.get("beta_override"),
    }
