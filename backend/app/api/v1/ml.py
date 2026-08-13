"""The ML engine, served under the portal's own origin and auth.

`ml_pipeline` ships its own FastAPI dashboard on :8077. That server is
unauthenticated by design (its `/api/health` says so in as many words), which is
fine for a researcher running it locally and wrong for a government portal: the
browser would be talking to a second origin with no session, no role check and
no audit trail, and the ore-deposit and pin endpoints would be readable by
anyone who could reach the port.

This router puts the same capabilities behind the backend's JWT, its role
guards, its rate limiter and its audit middleware. Nothing here re-implements
the engine — every handler forwards to the pipeline app in-process through
`ml_pipeline_adapter`, so there is still exactly one implementation of the
physics and one place the model artifacts are read.

Two access tiers:

* **Reference geography** (boundary, ore, rivers, aquifers, flow, strike) is
  staff-readable. It is the map's context layer and carries no prediction.
* **`/pin` and `/predict`** are restricted to the roles that may run the model
  at all — admin, regulator, analyst. A field officer collects evidence and a
  citizen reads measurements; neither runs a contaminant simulation.

**`/predict` here is interactive, not the auditable record.** It returns plume
geometry for live exploration on the map and persists nothing.
`POST /simulations/{isr_id}` remains the path that writes a run with its
provenance triple. The response says so, so a screenshot of this cannot be
mistaken for a filed result.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.dependencies import require_simulation_roles, require_staff
from app.services import ml_pipeline_adapter as mlp

router = APIRouter(prefix="/ml", tags=["ML Engine"])

#: **`no-store`, deliberately.** These payloads are role-restricted — `/ml/ore`
#: is the map of where a hypothetical uranium site could be placed, and design
#: §2 keeps that away from citizens. `private, max-age=...` does NOT mean
#: "per-user": it only excludes shared proxy caches. The browser's own cache is
#: keyed on the URL, not the Authorization header, so on a shared machine a
#: citizen signing in after an analyst was served the analyst's cached ore
#: polygons and saw a 200 for an endpoint the server refuses them. Caught in
#: verification, when a citizen's role sweep returned 200 while curl returned
#: 403 for the same token.
#:
#: The responsiveness this gives up is recovered client-side: the portal holds
#: these layers in TanStack Query with a one-hour `staleTime`, which is
#: in-memory, per-page-load, and therefore cannot outlive a sign-out.
_GEO_CACHE = "no-store"


async def _forward(path: str, response: Response,
                   params: dict[str, Any] | None = None,
                   cache: str | None = _GEO_CACHE) -> Any:
    """Forward to the pipeline, turning engine failure into a 503.

    503 rather than 500: the engine being unavailable is a dependency problem
    the caller can retry, not a bug in the request they sent.
    """
    try:
        payload = await mlp.get_json(path, params)
    except mlp.MLPipelineError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if cache:
        response.headers["Cache-Control"] = cache
    return payload


# ── engine state ─────────────────────────────────────────────────────

@router.get("/health")
async def ml_health(_=Depends(require_staff)):
    """Engine reachability plus the provenance triple identifying the artifacts."""
    return await mlp.health()


@router.get("/assumptions")
async def ml_assumptions(response: Response, _=Depends(require_staff)):
    """Every constant the model rests on that is not measured or cited.

    Surfaced in the portal because a screening number is only as good as the
    register of what it assumed.
    """
    return await _forward("/api/assumptions", response)


@router.get("/drift")
async def ml_drift(response: Response, _=Depends(require_staff)):
    """Rolling analytical-vs-ML disagreement — the surrogate's own health check."""
    return await _forward("/api/drift", response, cache=None)


# ── reference geography for the map ──────────────────────────────────

@router.get("/boundary")
async def ml_boundary(response: Response, _=Depends(require_staff)):
    """Dissolved Jharkhand outline, for the map border and the inverse mask."""
    return await _forward("/api/boundary", response)


@router.get("/ore")
async def ml_ore(response: Response, _=Depends(require_staff)):
    """Uranium deposit polygons and the Singhbhum belt envelope.

    Staff only. These are the zones where the engine will produce a uranium
    plume at all, so they double as a map of where a hypothetical site could
    even be placed.
    """
    return await _forward("/api/ore", response)


@router.get("/rivers")
async def ml_rivers(response: Response, _=Depends(require_staff)):
    """Perennial rivers — where a plume would discharge to surface water."""
    return await _forward("/api/rivers", response)


@router.get("/aquifers")
async def ml_aquifers(response: Response, _=Depends(require_staff)):
    """Regime-coloured aquifer polygons (fractured vs weathered/porous)."""
    return await _forward("/api/aquifers", response)


@router.get("/flow-field")
async def ml_flow_field(response: Response, step: int = Query(2, ge=1, le=10),
                        _=Depends(require_staff)):
    """Down-gradient flow azimuth per cell — the direction a plume travels."""
    return await _forward("/api/flow_field", response, {"step": step})


@router.get("/strike-field")
async def ml_strike_field(response: Response, step: int = Query(2, ge=1, le=10),
                          _=Depends(require_staff)):
    """Fracture-strike fabric per cell — what ELONGATES a plume, not where it goes."""
    return await _forward("/api/strike_field", response, {"step": step})


# ── the engine itself ────────────────────────────────────────────────

@router.get("/pin")
async def ml_pin(response: Response,
                 lon: float = Query(..., ge=-180, le=180),
                 lat: float = Query(..., ge=-90, le=90),
                 _=Depends(require_simulation_roles)):
    """Resolve what the engine knows at a coordinate before anyone runs it.

    Lithology, regime, hydraulic conductivity, flow azimuth, gradient, ore
    proximity. This is what makes clicking the map an informed act rather than
    a guess: the user sees the inputs the run would resolve, and whether the
    point sits in an ore zone at all.
    """
    try:
        return await mlp.get_json("/api/pin", {"lon": lon, "lat": lat})
    except mlp.MLPipelineError as exc:
        # The pipeline answers 422 outside Jharkhand; that is a user-correctable
        # condition, not an outage, so it must not surface as a 503.
        text = str(exc)
        if "422" in text:
            raise HTTPException(
                status_code=422,
                detail="That point is outside Jharkhand. The engine resolves "
                       "hydrogeology only inside the state boundary.") from exc
        raise HTTPException(status_code=503, detail=text) from exc


@router.post("/predict")
async def ml_predict(payload: dict[str, Any],
                     _=Depends(require_simulation_roles)):
    """Run the engine interactively and return plume geometry.

    **Not persisted.** Use `POST /simulations/{isr_id}` for a run that is stored
    with its model card, artifact bundle and code version. The `persisted: false`
    flag in the response is there so a client cannot present this as a filed
    result by accident.

    The payload is filtered by the adapter's allowlist, so only the pin and the
    operational sliders reach the engine. Expert chemistry overrides that the
    pipeline's own local dashboard exposes are withheld here — those values are
    the engine's to resolve from `Datasets/`, and letting a portal user hand-tune
    them would produce an authoritative-looking number with no provenance.
    """
    lon, lat = payload.get("lon"), payload.get("lat")
    if lon is None or lat is None:
        raise HTTPException(status_code=422, detail="lon and lat are required.")

    withheld = sorted(set(payload) & mlp.EXPERT_OVERRIDES_WITHHELD)
    if withheld:
        raise HTTPException(
            status_code=422,
            detail=f"These engine inputs cannot be set through the portal: "
                   f"{withheld}. They are resolved from the pipeline's own "
                   f"datasets at the pin.")

    body = mlp.build_payload(lon=float(lon), lat=float(lat), params=payload)
    try:
        result = await mlp.predict(body)
    except mlp.MLPipelineError as exc:
        text = str(exc)
        if "422" in text:
            raise HTTPException(
                status_code=422,
                detail="That point is outside Jharkhand, or a slider is out of "
                       "range for the engine.") from exc
        raise HTTPException(status_code=503, detail=text) from exc

    result["persisted"] = False
    result["persistence_note"] = (
        "Interactive run — not stored. Register the location as an ISR point "
        "and run it from the Simulation Studio to produce an auditable record.")
    return result
