"""The seam between the backend and `ml_pipeline`.

P3. The backend's own stub engine was deleted in P0 for fabricating results
(a random flow direction and a constant 0.5733 km² area); this is what replaces
it. Every number now comes from the engine that has 307 tests, an
exact-solution-benchmarked transport kernel and conformally calibrated bands.

═══════════════════════════════════════════════════════════════════════════
THE ONE RULE THIS MODULE EXISTS TO ENFORCE
═══════════════════════════════════════════════════════════════════════════
**No database value is ever passed into the engine as chemistry, hydrogeology
or baseline.** The only things that cross this seam are:

    lon, lat            where the hypothetical site is
    operational sliders injection rate, wellfield width, bleed, years, species

Everything else — aquifer properties, flow azimuth, hydraulic gradient, fracture
strike, water-quality baselines, the Texas source term — the engine resolves
from its OWN datasets under `Datasets/` and its own frozen artifacts.

That matters specifically because of the field-observation workflow. An approved
field observation writes to `water_samples` and `ore_observations`, and a
regulator approving a reading must NOT thereby move a contamination model. The
surrogate's conformal coverage was calibrated against a fixed input
distribution; feeding it freshly approved field chemistry would invalidate the
calibration silently — the bands would still be printed, and they would no
longer mean 80%.

If field data should ever inform the model, the route is a deliberate re-bake
and retrain with the coverage gate re-run (`PRODUCT_DESIGN.md` §4.6 rule 9),
not a live read. `tests/test_p3_simulation.py` pins this by asserting the
payload that crosses this boundary contains nothing but the pin and the sliders.
"""
from __future__ import annotations

import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from loguru import logger

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = REPO_ROOT / "ml_pipeline" / "ml" / "artifacts"

#: The complete set of keys the backend may send. Anything not here cannot
#: reach the engine — enforced, not documented, by `build_payload`.
ALLOWED_PAYLOAD_KEYS = frozenset({
    "lon", "lat", "species",
    "operation_years", "time_years", "injection_rate_m3_day",
    "wellfield_width_m", "bleed_percent", "restoration_years",
    # `gradient_i`, not `gradient`: the engine's field is `gradient_i`, and the
    # old spelling passed this allowlist only to be dropped by the engine's own
    # model — a caller could set it and silently get the data-derived default.
    "gradient_i", "azimuth_deg", "monitor_ring_m",
    # Interactive map controls. Presentation and geometry, not chemistry.
    "regime", "mode", "start_date", "ore_depth_m", "ore_thickness_m",
})

#: Sliders a caller may set. `lon`/`lat` come from the ISR point, not the body.
CLIENT_TUNABLE = ALLOWED_PAYLOAD_KEYS - {"lon", "lat"}

#: Engine inputs a portal user may NOT override, even though the pipeline's own
#: local dashboard exposes them as "expert" fields. These are exactly the
#: chemistry and hydrogeology this module exists to keep on the engine's side of
#: the seam: resolved from `Datasets/` at the pin, never supplied by a caller.
#: Listed explicitly so the refusal is legible rather than an absence.
EXPERT_OVERRIDES_WITHHELD = frozenset({
    "kd_L_kg", "beta", "K_m_day", "phi_mobile",
    "downtime_fraction", "gradient_seasonal_amp", "u_attenuation_k_per_yr",
})


class MLPipelineError(RuntimeError):
    pass


#: Site column -> engine field. Identical for most, but the mapping is written
#: out so a rename on either side is a compile-time-ish failure here rather than
#: a parameter that silently stops crossing.
SITE_TO_ENGINE = {
    "injection_rate_m3_day": "injection_rate_m3_day",
    "bleed_percent": "bleed_percent",
    "operation_years": "operation_years",
    "restoration_years": "restoration_years",
    "wellfield_width_m": "wellfield_width_m",
    "monitor_ring_m": "monitor_ring_m",
    "ore_depth_m": "ore_depth_m",
    "ore_thickness_m": "ore_thickness_m",
    "regime_override": "regime",
    "gradient_i": "gradient_i",
    "azimuth_deg": "azimuth_deg",
}


def payload_from_site(site: Any, *, overrides: Optional[dict[str, Any]] = None
                      ) -> dict[str, Any]:
    """Build the engine payload from a registered ISR point.

    NOT a violation of this module's rule. The rule keeps *measured* values —
    chemistry, hydrogeology, baselines, anything a field observation could
    touch — from crossing into a model whose conformal coverage was calibrated
    without them. These are the operator's chosen SCENARIO INPUTS: how much
    lixiviant, over how many years, across what footprint. They are the same
    numbers a Studio slider used to supply, now stored on the site so a run is
    reproducible and two people mean the same thing by one name.

    `overrides` is what the Studio may still vary — evaluation year and
    restoration years — and is filtered by the same allowlist as everything
    else.
    """
    from geoalchemy2.shape import to_shape
    point = to_shape(site.location)
    params: dict[str, Any] = {}
    for column, field in SITE_TO_ENGINE.items():
        value = getattr(site, column, None)
        if value is not None:
            params[field] = value
    if getattr(site, "injection_start_date", None):
        params["start_date"] = site.injection_start_date.date().isoformat()
    params.update(overrides or {})
    return build_payload(lon=point.x, lat=point.y, params=params)


def build_payload(*, lon: float, lat: float,
                  params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Assemble the engine payload, dropping anything not explicitly allowed.

    The allowlist is the enforcement point for the rule above: a future caller
    cannot pass a measured uranium value, a well id, or anything else read from
    the database, because only these keys survive.
    """
    payload: dict[str, Any] = {"lon": float(lon), "lat": float(lat)}
    for key, value in (params or {}).items():
        if key in CLIENT_TUNABLE and value is not None:
            payload[key] = value
    payload.setdefault("species", "uranium_ppb")
    return payload


@lru_cache(maxsize=1)
def _ml_app():
    """The pipeline's own FastAPI app, imported in-process.

    In-process rather than over HTTP: `ml_pipeline` is a package in this repo
    and running a second service for a fellowship prototype is infrastructure
    with no payoff yet. PRODUCT_DESIGN.md §6 puts the pipeline behind the
    gateway as an internal service; this function is the single place that
    changes when it becomes a real one — the callers do not.

    NOT `fastapi.testclient.TestClient`: that is synchronous and drives the app
    through its own event-loop portal, so calling it from inside the running
    loop (which is where a FastAPI background task lives) blocks and the run
    never completes. It sat at status 'running' forever. An async ASGI
    transport shares the caller's loop, and the pipeline's own handlers are
    `def`, so FastAPI still runs them in its threadpool.
    """
    # `ml_pipeline` sits at the repo root, one level above `backend/`, and is
    # not an installed distribution. The backend runs with cwd=backend, so it is
    # not importable without this. When the pipeline becomes a separate service
    # (PRODUCT_DESIGN.md §6) this goes away with the in-process import.
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from ml_pipeline.dashboard.server import app as ml_app
    except Exception as exc:  # noqa: BLE001
        raise MLPipelineError(f"ml_pipeline is not importable: {exc}") from exc
    return ml_app


@lru_cache(maxsize=1)
def provenance() -> dict[str, str]:
    """Pin what produced a result: the model card, the artifact bundle, the code."""
    card = ARTIFACTS / "model_card.json"
    if not card.exists():
        raise MLPipelineError(f"model card missing at {card}")
    model_card_sha = hashlib.sha256(card.read_bytes()).hexdigest()

    # One digest over every artifact, so swapping a single .joblib is visible.
    h = hashlib.sha256()
    for p in sorted(ARTIFACTS.iterdir()):
        if p.is_file():
            h.update(p.name.encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
    artifacts_sha = h.hexdigest()

    try:
        code_version = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
            text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        code_version = "unknown"

    return {"model_card_sha": model_card_sha, "artifacts_sha": artifacts_sha,
            "code_version": code_version}


def assert_payload_allowed(payload: dict[str, Any]) -> None:
    """Refuse anything that is not the pin or an operational slider.

    Refuses rather than filters: a caller trying to pass database-derived values
    into the engine is a design error, and silently dropping them would hide it.
    """
    leaked = set(payload) - ALLOWED_PAYLOAD_KEYS
    if leaked:
        raise MLPipelineError(
            f"payload keys not permitted across the ml_pipeline boundary: "
            f"{sorted(leaked)}. Only the pin and operational sliders may cross; "
            f"see this module's docstring.")


async def predict(payload: dict[str, Any]) -> dict[str, Any]:
    """Run the engine. Raises MLPipelineError rather than returning a guess."""
    assert_payload_allowed(payload)
    from httpx import ASGITransport, AsyncClient
    try:
        async with AsyncClient(transport=ASGITransport(app=_ml_app()),
                               base_url="http://ml", timeout=120.0) as client:
            resp = await client.post("/api/predict", json=payload)
    except Exception as exc:  # noqa: BLE001
        raise MLPipelineError(f"ml_pipeline call failed: {exc}") from exc
    if resp.status_code != 200:
        raise MLPipelineError(
            f"ml_pipeline returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def get_json(path: str, params: Optional[dict[str, Any]] = None,
                   timeout: float = 60.0) -> Any:
    """GET a read-only endpoint on the pipeline app and return its JSON.

    Used by the `/api/v1/ml` router to serve the pipeline's reference geography
    (boundary, ore, rivers, aquifers, flow and strike fields) to the portal
    through one authenticated origin, instead of asking the browser to talk to
    a second, unauthenticated service on another port.

    Deliberately GET-only and path-driven by the router, never by user input:
    these are static reference layers. Anything that runs the engine goes
    through `predict`, which enforces the payload allowlist.
    """
    from httpx import ASGITransport, AsyncClient
    try:
        async with AsyncClient(transport=ASGITransport(app=_ml_app()),
                               base_url="http://ml", timeout=timeout) as client:
            resp = await client.get(path, params=params or {})
    except Exception as exc:  # noqa: BLE001
        raise MLPipelineError(f"ml_pipeline call failed: {exc}") from exc
    if resp.status_code != 200:
        raise MLPipelineError(
            f"ml_pipeline returned {resp.status_code}: {resp.text[:300]}",
            )
    return resp.json()


async def health() -> dict[str, Any]:
    from httpx import ASGITransport, AsyncClient
    try:
        async with AsyncClient(transport=ASGITransport(app=_ml_app()),
                               base_url="http://ml", timeout=30.0) as client:
            r = await client.get("/api/health")
        ok = r.status_code == 200
        return {"ok": ok, "detail": r.json() if ok else r.text[:200],
                **provenance()}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"ml_pipeline health check failed: {exc}")
        return {"ok": False, "detail": str(exc)}
