"""
ml_pipeline.dashboard.server  (PHASE 4 -- FastAPI backend)
========================================================
Decoupled API that wraps the Phase-3 unified predictor and serves the vanilla-JS
frontend. The analytical engine always runs (it provides the plume geometry);
the ML surrogate runs alongside it (P10/P50/P90 bands) so the UI's
"Analytical vs ML" toggle is instant client-side.

Guardrails (2026-07 review, Phase 0/1 + Phase 4):
  * request bounds match the training envelope (config.OPERATIONAL_RANGES);
  * every response carries `extrapolation`: input names outside the envelope
    the DEPLOYED model was trained on (ML bands are unvalidated there);
  * latitude AND longitude of the pin are validated;
  * `off_scale` is surfaced for the ML path too (area/migration heads were
    trained with off-scale rows censored);
  * DRIFT MONITOR: every request records analytical-vs-ML disagreement; the
    rolling summary is at GET /api/drift (`drifting` flag when the median gap
    exceeds threshold) -- the surrogate's health signal for free;
  * CORS is NOT wide-open by default -- localhost only unless ML_PIPELINE_DEV=1
    or an explicit ML_PIPELINE_CORS_ORIGINS allow-list is set.

Run:
    uvicorn ml_pipeline.dashboard.server:app --reload --port 8077
    # then open http://localhost:8077
Env:
    ML_PIPELINE_DEV=1                      # allow CORS '*' (dev only)
    ML_PIPELINE_CORS_ORIGINS=https://...   # explicit prod allow-list
    ML_PIPELINE_DRIFT_THRESHOLD=0.25       # median rel-gap drift trigger
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ml_pipeline.config import parameters as P
from ml_pipeline.ml.predict import predict, predict_analytical
from ml_pipeline.dashboard.resolve import (
    resolve_inputs, pin_info, _assets, envelope_violations,
)
from ml_pipeline.dashboard.plume_geometry import (
    field_to_contours, compliance_ring, ml_envelope_ellipses,
    source_zone_polygon,
)


def _replace_field(field, C_new):
    """A PlumeResult view carrying a different concentration grid.

    Used to contour the plume-only field while leaving `field.metrics` — the
    numbers actually reported — completely untouched (bug A).
    """
    import copy
    view = copy.copy(field)
    view.C = C_new
    return view
from ml_pipeline.dashboard.drift import MONITOR
from ml_pipeline.data_prep.boundary import in_jharkhand, boundary_geojson

# Frontend was relocated out of the dashboard package to the repo-level
# `frontend/` directory (frontend/ml_pipeline/). server.py lives at
# ml_pipeline/dashboard/server.py, so the repo root is three levels up.
_REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = _REPO_ROOT / "frontend" / "ml_pipeline"


def _cors_origins() -> list[str]:
    """Allowed CORS origins. Default: the local dashboard only. `*` requires an
    explicit opt-in (ML_PIPELINE_DEV=1) so a deployed instance is not wide open;
    ML_PIPELINE_CORS_ORIGINS (comma-separated) sets an explicit allow-list."""
    explicit = os.environ.get("ML_PIPELINE_CORS_ORIGINS")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    if os.environ.get("ML_PIPELINE_DEV", "").lower() in {"1", "true", "yes"}:
        return ["*"]
    return ["http://localhost:8077", "http://127.0.0.1:8077"]


app = FastAPI(title="JalDrishti ml_pipeline — ISR plume surrogate", version="1.2")
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(),
                   allow_methods=["GET", "POST"], allow_headers=["*"])


# --------------------------------------------------------------------------- #
# V-6: availability controls. Twelve endpoints previously had NO rate limiting
# and NO caching. `POST /api/predict` runs a 200^2 grid solve plus a 48-draw
# Monte Carlo per call, and the timeline animation issues one request per
# simulated month BY DESIGN -- so sustained request rates are a normal traffic
# pattern here, not an attack signature, and the limit must sit well above it.
# Integrity was already sound (Pydantic bounds validate every numeric input, and
# the previous audit could not construct a crashing payload); this closes the
# availability gap.
#
# Deliberately dependency-free and in-process: a token bucket keyed on client
# host. That is the right scope for a single-process screening dashboard. A
# multi-worker or public deployment needs a shared store (Redis) or a reverse
# proxy -- stated in the health endpoint rather than implied to be solved.
# --------------------------------------------------------------------------- #
RATE_LIMIT_PER_MIN = int(os.environ.get("ML_PIPELINE_RATE_LIMIT_PER_MIN", "240"))
RATE_LIMIT_BURST = int(os.environ.get("ML_PIPELINE_RATE_LIMIT_BURST", "60"))
_BUCKETS: dict[str, tuple[float, float]] = {}     # host -> (tokens, last_seen)


@app.middleware("http")
async def _rate_limit(request, call_next):
    import time
    if RATE_LIMIT_PER_MIN <= 0 or not request.url.path.startswith("/api/"):
        return await call_next(request)
    host = (request.client.host if request.client else "unknown")
    now = time.monotonic()
    tokens, last = _BUCKETS.get(host, (float(RATE_LIMIT_BURST), now))
    tokens = min(float(RATE_LIMIT_BURST),
                 tokens + (now - last) * RATE_LIMIT_PER_MIN / 60.0)
    if tokens < 1.0:
        _BUCKETS[host] = (tokens, now)
        return JSONResponse(
            status_code=429,
            content={"code": "RATE_LIMITED",
                     "message": (f"More than {RATE_LIMIT_PER_MIN} requests/min "
                                 f"from this client. Set "
                                 f"ML_PIPELINE_RATE_LIMIT_PER_MIN to change.")},
            headers={"Retry-After": "1"})
    _BUCKETS[host] = (tokens - 1.0, now)
    return await call_next(request)


# The static overlay endpoints are deterministic functions of committed data
# files, and /api/aquifers alone returns ~0.48 MB uncached on every call.
_STATIC_CACHE_CONTROL = "public, max-age=86400"


def _cached_geojson(payload: dict) -> JSONResponse:
    """Deterministic overlay response with validators, so a browser (or proxy)
    stops re-downloading unchanged geometry on every pin move."""
    import hashlib
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    etag = '"' + hashlib.sha256(body.encode("utf-8")).hexdigest()[:32] + '"'
    return JSONResponse(content=payload,
                        headers={"Cache-Control": _STATIC_CACHE_CONTROL,
                                 "ETag": etag})


_OR = P.OPERATIONAL_RANGES


class PredictRequest(BaseModel):
    lon: float
    lat: float
    species: str = "uranium_ppb"
    regime: str | None = None                      # None -> use pin's lithology
    injection_rate_m3_day: float = Field(2500, ge=_OR["injection_rate_m3_day"][0],
                                         le=_OR["injection_rate_m3_day"][1])
    bleed_percent: float = Field(2.0, ge=_OR["bleed_fraction"][0] * 100,
                                 le=_OR["bleed_fraction"][1] * 100)
    operation_years: float = Field(8, ge=_OR["operation_years"][0],
                                   le=_OR["operation_years"][1])
    # None -> data-derived default from the D1 flow field at the pin (Stage B).
    gradient_i: float | None = Field(None, ge=_OR["hydraulic_gradient"][0],
                                     le=_OR["hydraulic_gradient"][1])
    # UI EXPLORATION bound (0-50 yr), DECOUPLED from the trained horizon like
    # restoration_years: the 30 yr disc-flush half-life decays over evaluation time
    # (t - operation_years), so the horizon must reach past ~op+30 to show it. The
    # analytical engine serves any horizon; ML bands beyond the deployed model's
    # trained max (model card, 20 yr) are flagged via `extrapolation`, not rejected.
    time_years: float = Field(10, ge=_OR["horizon_years"][0],
                              le=P.HORIZON_SLIDER_MAX_YEARS)
    # NAME KEPT, MEANING CLARIFIED (2026-08-10). This is the DIAMETER of the
    # circular well-pattern footprint -- the full transverse extent of the
    # wellfield, not a borehole width and not a spacing. The field name is a
    # trained model feature so it cannot be renamed without a retrain; the
    # response carries a `wellfield_geometry` block and the UI label says
    # "well-pattern footprint diameter" instead.
    wellfield_width_m: float = Field(
        300, ge=_OR["wellfield_width_m"][0], le=_OR["wellfield_width_m"][1],
        description=("Diameter of the circular well-pattern footprint (full "
                     "transverse extent of the wellfield), in metres."))
    # R-2: perimeter monitor-well ring distance from the wellfield EDGE.
    # NUREG-1569 Sec. 5.7.8.3 p.139 records licensed rings at 75-180 m, with
    # justification required beyond ~150 m. The trained surrogate's
    # compliance_conc target was baked at P.COMPLIANCE_BUFFER_M, so moving the
    # ring makes that ML head extrapolate -- reported, not silently served.
    monitor_ring_m: float = Field(P.COMPLIANCE_BUFFER_M,
                                  ge=P.MONITOR_RING_RANGE_M[0],
                                  le=P.MONITOR_RING_RANGE_M[1])
    # UI EXPLORATION bound (0-50 yr), deliberately DECOUPLED from the training
    # envelope: the analytical engine serves any sweep length correctly, and the
    # ML bands beyond the deployed model's trained max (model card, currently 10 yr)
    # are flagged via `extrapolation`/the drift monitor rather than rejected. Lets a
    # user view how a sweep plays out past the 30 yr disc-flush half-life.
    restoration_years: float = Field(0, ge=0, le=P.RESTORATION_SLIDER_MAX_YEARS)
    # None -> down-gradient bearing from the D1 flow field (radial near a divide).
    azimuth_deg: float | None = Field(None, ge=0, le=360)
    # Module 5A (2.5D): depth of the ore/ISR target zone + its vertical extent
    ore_depth_m: float = Field(P.VERTICAL["ore_depth_default_m"],
                               ge=P.VERTICAL["ore_depth_range_m"][0],
                               le=P.VERTICAL["ore_depth_range_m"][1])
    ore_thickness_m: float = Field(P.VERTICAL["ore_thickness_default_m"],
                                   ge=P.VERTICAL["ore_thickness_range_m"][0],
                                   le=P.VERTICAL["ore_thickness_range_m"][1])
    mode: str = "both"                             # analytical | ml | both
    # TIMELINE (3.7b): ISR start date, ISO "YYYY-MM-DD". Purely a presentation
    # anchor -- it converts `time_years` into a calendar date and selects the
    # month whose water table drives the seasonal vertical state. It does NOT
    # make the run historical: no ISR has ever operated in Jharkhand, so the
    # date is a user-chosen hypothesis and is labelled as such in the response.
    start_date: str | None = None
    # expert overrides (None -> resolved from the pin / literature)
    kd_L_kg: float | None = Field(None, ge=0, le=50)
    beta: float | None = Field(None, ge=0, le=50)
    K_m_day: float | None = Field(None, gt=0, le=500)
    phi_mobile: float | None = Field(None, gt=0, le=0.45)
    downtime_fraction: float | None = Field(None, ge=0, le=0.30)
    gradient_seasonal_amp: float | None = Field(None, ge=0, le=0.40)
    # real-ISR upgrade: expert override for the U redox-trapping rate [1/yr].
    # None -> literature mode (0.20) for uranium, 0 for sulfate/TDS. Values
    # above the trained max (0.70) are served analytically + flagged.
    u_attenuation_k_per_yr: float | None = Field(None, ge=0, le=2.0)


def _bands(d: dict) -> dict:
    return {"p10": round(d["p10"], 3), "p50": round(d["p50"], 3), "p90": round(d["p90"], 3)}


def _timeline(start_date: str | None, t_years: float, op_years: float,
              rest_years: float) -> dict | None:
    """Map elapsed model time onto a calendar, for the timeline animation.

    Returns the current date, its month/season (which selects the water table),
    and which LIFECYCLE PHASE the run is in. The phase boundaries are exactly the
    ones `front_position` already uses -- operation, restoration sweep, then
    post-closure drift -- so the label can never disagree with the physics.
    """
    if not start_date:
        return None
    try:
        t0 = _dt.date.fromisoformat(start_date.strip())
    except (ValueError, AttributeError):
        return None
    # ROUND, don't truncate: date + timedelta drops the sub-day remainder, and at
    # a monthly animation step that repeatedly lands one day short of the 1st --
    # which made the animation repeat some months and skip others entirely
    # (Jan/Aug/Oct twice, Feb/Sep/Nov never shown).
    now = t0 + _dt.timedelta(days=round(float(t_years) * 365.25))
    if t_years <= op_years:
        phase, phase_label = "operation", "Operation (injection + capture)"
    elif t_years <= op_years + rest_years:
        phase, phase_label = "restoration", "Restoration sweep (front held)"
    else:
        phase, phase_label = "drift", "Post-closure drift"
    return {
        "start_date": t0.isoformat(),
        "current_date": now.isoformat(),
        "elapsed_years": round(float(t_years), 2),
        "month": now.month,
        "season": P.SEASON_LABELS[now.month],
        # HONESTY: CGWB samples FOUR campaigns a year (Jan/May/Aug/Nov). Those
        # months are MEASURED; the other eight are interpolated between them.
        # The animation must say which it is showing rather than presenting all
        # twelve as if they were equally evidenced.
        "water_table_measured": now.month in P.WATER_TABLE_CAMPAIGNS_M,
        "water_table_basis": ("CGWB campaign (measured)"
                              if now.month in P.WATER_TABLE_CAMPAIGNS_M
                              else "interpolated between CGWB campaigns"),
        "phase": phase,
        "phase_label": phase_label,
        "operation_ends": (t0 + _dt.timedelta(days=op_years * 365.25)).isoformat(),
        "restoration_ends": (t0 + _dt.timedelta(
            days=(op_years + rest_years) * 365.25)).isoformat(),
        # Non-negotiable label: this is a scenario clock, not a record of events.
        "hypothetical": True,
        "disclaimer": ("Hypothetical lifecycle. No ISR operation has ever existed "
                       "in Jharkhand; the start date is a user-chosen scenario "
                       "anchor, not a historical record. Seasonal state is a "
                       "repeating CGWB climatology (2013-2021), not live data."),
    }


def _source_zone_crossing(*, C0: float, thr_inc: float, op_years: float,
                          rest_years: float, residual_ref: float,
                          start_date: str | None) -> dict:
    """When does the uniform leach disc drop below the screening threshold?

    THE PROBLEM THIS ANSWERS (bug C, 2026-08-11). The E1 leach disc carries a
    SINGLE uniform concentration, so the moment that one value crosses the
    incremental threshold the ENTIRE footprint leaves the exceedance area at
    once. Measured at a deposit pin with radium: 13.78 ha at t = 44 y 1 mo,
    0.00 ha at 44 y 2 mo. That is arithmetically correct for a uniform disc and
    physically an artefact -- a real source zone has a concentration gradient,
    so its above-threshold area would shrink continuously.

    Radium shows it most starkly because its migration is 0 m at every time
    (Rd ~ 1.2e4), so the disc IS the whole area; for U/SO4/TDS a travelling
    plume survives the disc dropping out.

    Fixing the disc itself means giving it a radial taper, which changes the
    training labels and needs a re-bake -- forbidden under the current freeze
    (ML_PIPELINE_READINESS.md section 7). So the step stays and is REPORTED:
    the UI states the crossing time instead of showing a bare 0.00 ha.

    Solved by bisection on `source_strength_fraction`, which is monotone
    non-increasing in t across every branch (elapsed-sweep credit, post-closure
    flush, rebound floor). Using the real function rather than re-deriving a
    closed form per branch is what keeps this diagnostic honest: it cannot
    disagree with the served field.
    """
    from ml_pipeline.physics.transport import source_strength_fraction

    def disc_at(t_years: float) -> float:
        return C0 * source_strength_fraction(residual_ref, t_years * 365.0,
                                             op_years * 365.0, rest_years * 365.0)

    # the ratio itself lives on the parent `source_zone` block as
    # `conc_over_threshold`; this block answers only "when does it cross".
    out = {"crosses": False, "crossing_years": None,
           "crossing_date": None, "reason": None}
    if thr_inc <= 0 or C0 <= 0:
        out["reason"] = "no screening threshold for this species"
        return out
    if disc_at(op_years) < thr_inc:
        out["reason"] = ("the source zone is below the screening threshold "
                         "already at end-of-operations")
        return out

    # search out to a long horizon; the disc is monotone so a sign change is
    # necessary and sufficient
    T_MAX = 500.0
    if disc_at(T_MAX) >= thr_inc:
        out["reason"] = (
            "the source zone never falls below the threshold on this model's "
            "horizon" + (" — after a restoration sweep it is held at the "
                         "measured stable endpoint and stops decaying"
                         if rest_years > 0 and P.RESTORATION_REBOUND_FLOOR else ""))
        return out

    lo, hi = op_years, T_MAX
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if disc_at(mid) >= thr_inc:
            lo = mid
        else:
            hi = mid
    t_cross = 0.5 * (lo + hi)
    out.update(crosses=True, crossing_years=round(t_cross, 3), reason=None)
    if start_date:
        try:
            t0 = _dt.date.fromisoformat(start_date.strip())
            out["crossing_date"] = (
                t0 + _dt.timedelta(days=round(t_cross * 365.25))).isoformat()
        except (ValueError, AttributeError):
            pass
    return out


# Module 1: strict boundary. The state bbox is a cheap pre-filter; the dissolved
# district polygon (data_prep.boundary) is authoritative.
_OUTSIDE_JH = {
    "code": "OUTSIDE_JHARKHAND",
    "message": ("Coordinate is outside Jharkhand. This tool has aquifer and "
                "water-quality data only for Jharkhand; predictions elsewhere "
                "would be fabricated."),
}


def _in_jharkhand(lon: float, lat: float) -> bool:
    B = P.JHARKHAND_BOUNDS
    if not (B["lon_min"] <= lon <= B["lon_max"]
            and B["lat_min"] <= lat <= B["lat_max"]):
        return False                                   # far outside -> skip PIP
    return in_jharkhand(lon, lat)                       # authoritative polygon test


@app.get("/api/health")
def health():
    try:
        from ml_pipeline.ml.predict import _surrogate
        _surrogate()
        ml_ok = True
    except Exception as e:
        ml_ok = f"unavailable: {type(e).__name__}"
    return {"status": "ok", "ml_surrogate": ml_ok,
            "bis_thresholds": P.EXCURSION_THRESHOLDS,
            "compliance_buffer_m": P.COMPLIANCE_BUFFER_M,
            "monitor_ring_range_m": list(P.MONITOR_RING_RANGE_M),
            "cors_origins": _cors_origins(),
            # V-6: state the availability posture explicitly, including its limit
            "rate_limit_per_min": RATE_LIMIT_PER_MIN,
            "rate_limit_burst": RATE_LIMIT_BURST,
            "rate_limit_scope": ("in-process, per client host. A multi-worker or "
                                 "public deployment needs a shared store or a "
                                 "reverse proxy; this is not that."),
            "auth": ("none — this API is unauthenticated by design for local "
                     "screening use. Do not expose it publicly without an "
                     "auth layer in front."),
            "static_cache_control": _STATIC_CACHE_CONTROL}


@app.get("/api/assumptions")
def api_assumptions():
    """Every constant this model rests on that is NOT measured or cited.

    Exposed so a reader can see what the answer depends on without reading the
    config. Backed by `P.UNGROUNDED_PARAMETERS` and pinned by
    tests/test_assumptions_register.py, so an ungrounded value cannot be added
    or silently changed without this list moving too."""
    return _cached_geojson({
        "scenario_assumptions": P.UNGROUNDED_PARAMETERS,
        "note": ("Everything not listed here is either derived from a dataset "
                 "in Datasets/ or carries an inline citation in "
                 "ml_pipeline/config/parameters.py."),
        "permanent_limitations": {
            "no_field_validation": ("No ISR operation has ever existed in "
                                    "Jharkhand, so the bands quantify PARAMETER "
                                    "uncertainty, not structural model error."),
            "premise": ("Commercial ISR is not physically plausible in "
                        "schist-hosted ore. Read every output as 'IF ISR-strength "
                        "lixiviant entered this aquifer', never as feasibility."),
        },
    })


@app.get("/api/pin")
def api_pin(lon: float = Query(...), lat: float = Query(...)):
    if not _in_jharkhand(lon, lat):
        raise HTTPException(422, _OUTSIDE_JH)
    return pin_info(lon, lat)


@app.get("/api/boundary")
def api_boundary():
    """Dissolved Jharkhand state boundary (lon/lat GeoJSON geometry) for the map
    outline + client-side inverse mask. Simplified to keep the payload light."""
    return _cached_geojson(boundary_geojson())


@app.get("/api/ore")
def api_ore():
    """Uranium deposit polygons + Singhbhum belt envelope (Module 2 overlay), so
    users can see which zones carry a real / hypothetical / no uranium source."""
    from ml_pipeline.data_prep.ore_loader import ore_geojson
    return _cached_geojson(ore_geojson())


@app.get("/api/rivers")
def api_rivers():
    """Perennial river polylines (HydroRIVERS, DIS>=1 m3/s) for the map overlay,
    so users see where a plume would discharge to surface water (Stage B2)."""
    from ml_pipeline.data_prep.rivers import rivers_geojson, RIVER_NPZ
    if not RIVER_NPZ.exists():
        return _cached_geojson({"type": "FeatureCollection", "features": []})
    return _cached_geojson(rivers_geojson())


@app.get("/api/flow_field")
def api_flow_field(step: int = 2):
    """D1 groundwater-flow vectors (down-gradient azimuth per cell) for the map
    overlay -- the plume's TRAVEL direction. Decimated to keep the payload light."""
    import numpy as np
    from ml_pipeline.data_prep.flow_field import load_flow_field
    ff = load_flow_field()
    lon_c, lat_c, fe, fn = ff["lon_c"], ff["lat_c"], ff["flow_e"], ff["flow_n"]
    grad, src, injh = ff["gradient_i"], ff["source"], ff["in_jh"]
    st = max(1, int(step))
    feats = []
    for j in range(0, injh.shape[0], st):
        for i in range(0, injh.shape[1], st):
            if not injh[j, i]:
                continue
            e, n = float(fe[j, i]), float(fn[j, i])
            if e * e + n * n < 1e-9:
                continue
            az = float(np.degrees(np.arctan2(e, n)) % 360.0)
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point",
                                       "coordinates": [float(lon_c[i]), float(lat_c[j])]},
                          "properties": {"azimuth_deg": round(az, 1),
                                         "gradient_i": round(float(grad[j, i]), 5),
                                         "source": "stations" if src[j, i] == 1 else "dem"}})
    return _cached_geojson({"type": "FeatureCollection", "features": feats})


@app.get("/api/strike_field")
def api_strike_field(step: int = 2):
    """D2 fracture-strike orientation (axial, undirected) per cell for the map
    overlay. This is the fabric that ELONGATES the plume (E1), NOT its travel
    direction -- rendered as a double-headed tick, coloured by dispersion V."""
    import numpy as np
    from ml_pipeline.data_prep.strike_field import load_strike_field
    sf = load_strike_field()
    lon_c, lat_c, rx, ry, injh = (sf["lon_c"], sf["lat_c"], sf["res_x"],
                                  sf["res_y"], sf["in_jh"])
    st = max(1, int(step))
    feats = []
    for j in range(0, injh.shape[0], st):
        for i in range(0, injh.shape[1], st):
            if not injh[j, i]:
                continue
            x, y = float(rx[j, i]), float(ry[j, i])
            strike = float((np.degrees(np.arctan2(y, x)) / 2.0) % 180.0)
            V = float(max(0.0, min(1.0, 1.0 - np.hypot(x, y))))
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point",
                                       "coordinates": [float(lon_c[i]), float(lat_c[j])]},
                          "properties": {"strike_deg": round(strike, 1),
                                         "circular_variance": round(V, 3)}})
    return _cached_geojson({"type": "FeatureCollection", "features": feats})


@app.get("/api/aquifers")
def api_aquifers():
    """Regime-coloured aquifer polygons (simplified) for the map overlay."""
    aq, _, _ = _assets()
    g = aq[["lithology", "regime", "K_m_day", "eff_porosity", "thickness_m", "geometry"]].copy()
    g["geometry"] = g["geometry"].simplify(0.004)        # lighten payload
    return _cached_geojson(json.loads(g.to_json()))


@app.post("/api/predict")
def api_predict(req: PredictRequest):
    if not _in_jharkhand(req.lon, req.lat):
        raise HTTPException(422, _OUTSIDE_JH)
    payload = req.model_dump()
    try:
        inputs, hydro = resolve_inputs(payload)
    except Exception as e:
        raise HTTPException(400, f"could not resolve pin hydrogeology: {e}")

    species = inputs["species"]
    threshold = P.EXCURSION_THRESHOLDS[species]
    extrapolation = envelope_violations(inputs)
    half_w = inputs["wellfield_width_m"] / 2.0        # source plane offset from pin

    # Effective display azimuth (Stage B/E2): explicit user override wins; else the
    # D1 down-gradient bearing; else (near a water divide, no preferred direction)
    # fall back to North -- E1 will render this radial. Flags the provenance.
    flow = hydro.get("flow", {})
    strike = hydro.get("strike", {})
    if req.azimuth_deg is not None:
        azimuth, azimuth_source = float(req.azimuth_deg), "user"
    elif flow.get("azimuth_deg") is not None:
        azimuth, azimuth_source = float(flow["azimuth_deg"]), "flow_field"
        # E1 (Stage H): in fractured rock the Darcy flux rotates toward the high-K
        # fracture strike -- rotate the DISPLAY azimuth (labels stay flow-aligned).
        if inputs["regime"] == "fractured" and strike.get("mean_strike_deg") is not None:
            from ml_pipeline.data_prep.strike_field import flux_azimuth
            azimuth = round(flux_azimuth(azimuth, strike["mean_strike_deg"],
                                         strike["circular_variance"]), 1)
            azimuth_source = "flow_field+strike"
    else:
        azimuth, azimuth_source = 0.0, "indeterminate_divide"

    # effective containment (after pump-downtime degradation) for the diagnostic
    from ml_pipeline.ml.predict import features_from_inputs as _ffi
    _feat_eta = _ffi(**inputs)[1]["_eta_eff"]

    # --- analytical (always: provides the plume geometry) ---
    # R-2: evaluate the compliance point at the ring the user actually asked for
    # (and that the map draws), not at a hard-coded 100 m.
    a = predict_analytical(compliance_x=float(req.monitor_ring_m), **inputs)
    field = a.pop("_field")
    restoration = a.get("restoration")     # realized-residual diagnostic (or None)
    fm = field.metrics
    # BUG A (2026-08-11): contour the PLUME-ONLY field, not the display field
    # with the source disc unioned into it. Contouring the union welded a circle
    # to the plume lobe and produced re-entrant notches that read as a rendering
    # fault. The disc is returned separately (plume.source_zone.polygon) and drawn
    # as its own layer. Read-only reuse of frozen functions -- no physics changes,
    # and the METRICS still come from `field.metrics`, untouched.
    try:
        from ml_pipeline.ml.predict import features_from_inputs as _ffi2
        from ml_pipeline.physics.transport import (params_from_features,
                                                   concentration_field)
        import numpy as _np
        _feat = _ffi2(**inputs)[1]
        _prm = params_from_features(
            _feat, species_C0=inputs["source_conc_C0"],
            t_days=inputs["time_years"] * 365.0,
            operation_days=inputs["operation_years"] * 365.0,
            restoration_days=float(inputs.get("restoration_years", 0.0) or 0.0) * 365.0,
            residual_fraction=_feat.get("_residual_endpoint", 1.0))
        _cp = concentration_field(field.X, field.Y, _prm, include_disc=False)
        # same up-gradient display mask solve_plume applies (the Domenico
        # upstream half-plane is a solution artifact, not a plume)
        field_for_contours = _replace_field(field, _np.where(field.X > 0.0, _cp, 0.0))
        source_zone_poly = source_zone_polygon(
            req.lon, req.lat, azimuth, _prm.disc_radius_m, _prm.disc_center_x_m,
            x_offset_m=half_w) if _prm.disc_radius_m > 0 else None
    except Exception:
        field_for_contours, source_zone_poly = field, None
    contours = field_to_contours(field_for_contours, lon0=req.lon, lat0=req.lat,
                                 azimuth_deg=azimuth, threshold=threshold,
                                 background=inputs["background_conc_Cb"],
                                 x_offset_m=half_w)
    # R-2: the ring is now an input. The ML `compliance_conc` head was trained at
    # P.COMPLIANCE_BUFFER_M, so a moved ring puts that head out of support --
    # flagged like any other envelope violation rather than served silently.
    ring_offset = float(req.monitor_ring_m)
    if abs(ring_offset - P.COMPLIANCE_BUFFER_M) > 1e-6:
        extrapolation = list(extrapolation) + ["monitor_ring_m"]
    ring_radius = half_w + ring_offset                # from the centre pin
    ring = compliance_ring(req.lon, req.lat, azimuth, ring_radius)
    aspect = fm["max_downgradient_m"] / max(fm["plume_halfwidth_m"], 1.0)

    # --- ML surrogate (bands), if artifacts present ---
    # Module 2: in a non-ore zone the uranium source term is clamped to a trace
    # level (far outside the surrogate's training envelope), so bypass the ML
    # call entirely and let the analytical engine report the ~zero U plume.
    ml_metrics, envelope, ml_status, m = None, None, "ok", None
    envelope_skipped = {}
    from ml_pipeline.ml.predict import ML_SPECIES
    if species not in ML_SPECIES:
        # fix 3.9: Ra-226 is served by the physics engine only. The deployed
        # surrogate was trained on a 3-species one-hot, so it has no radium
        # encoding; feeding it an all-zero species flag would silently return a
        # uranium-ish answer. Extending the surrogate is a deliberate retrain.
        ml_status = (f"analytical only for {species} — the ML surrogate is "
                     f"trained on {', '.join(ML_SPECIES)} and would be "
                     f"extrapolating on this species")
    elif hydro.get("u_suppressed"):
        ml_status = "suppressed: non-ore zone (no radiological source term)"
    else:
        try:
            m = predict("ml", **inputs)
            ml_metrics = {
                "area_ha": _bands(m["area_ha"]),
                "migration_m": _bands(m["migration_m"]),
                "compliance_conc": _bands(m["compliance_conc"]),
                "excursion_probability": round(m["excursion_probability"], 3),
                "breach_probability": round(m["breach_probability"], 3),
                "off_scale": bool(m.get("off_scale", False)),
            }
            # BUG B: down-gradient lobes anchored at the source plane, sized by
            # the plume's measured half-width; bands too small to draw are
            # reported as skipped rather than rendered as an invisible dot.
            _env = ml_envelope_ellipses(
                req.lon, req.lat, azimuth,
                {k: m["migration_m"][k] for k in ("p10", "p50", "p90")}, aspect,
                x_offset_m=half_w, halfwidth_m=fm.get("plume_halfwidth_m"))
            envelope = _env["rings"]
            envelope_skipped = _env["skipped"]
        except Exception as e:
            m = None
            ml_status = f"unavailable: {type(e).__name__} ({e})"

    # drift monitor: record analytical-vs-ML disagreement for this request
    disagreement = MONITOR.record(
        a, m, extrapolation=extrapolation,
        off_scale=bool(fm.get("off_scale", False)))

    # TIMELINE (3.7b): calendar anchor for the animation. None unless the caller
    # supplied a start date; everything downstream degrades to the un-dated
    # behaviour in that case.
    timeline = _timeline(req.start_date, req.time_years,
                         req.operation_years, req.restoration_years)

    # Module 5A (2.5D): screening estimate of shallow (Layer-1) aquifer impact.
    # Uses the deep plume's front reach + source term; the horizontal metrics are
    # untouched. alpha_L is recomputed from the same scale-dependent law the
    # transport engine uses (L = max(front reach, wellfield width)).
    L_disp = max(fm["Xc_m"], inputs["wellfield_width_m"], 1.0)
    alpha_L = P.longitudinal_dispersivity(L_disp)
    from ml_pipeline.physics.transport import shallow_impact_screening
    # D3: per-district shallow-aquifer base from the NAQUIM reports (falls back to
    # the state-wide VERTICAL default for districts without a report).
    from ml_pipeline.data_prep.naquim_vertical import vertical_params_at
    vparams = vertical_params_at(req.lon, req.lat)
    vertical = shallow_impact_screening(
        C0=inputs["source_conc_C0"], background=inputs["background_conc_Cb"],
        threshold=threshold, Xc_m=fm["Xc_m"],
        source_width_m=inputs["wellfield_width_m"], alpha_L=alpha_L,
        alpha_V=alpha_L * P.VERTICAL["alpha_V_ratio"],
        ore_depth_m=req.ore_depth_m, ore_thickness_m=req.ore_thickness_m,
        layer1_base_m=vparams["layer1_base_m"], K_m_day=inputs["K_m_day"],
        # confining Layer-2 porosity is FIXED (fractured bedrock, not the ore
        # regime); the regime enters through vertical anisotropy Kv/Kh instead.
        phi_confining=P.VERTICAL["phi_confining"],
        Kv_Kh_ratio=P.VERTICAL["Kv_Kh_by_regime"].get(inputs["regime"], 0.01),
        upward_gradient=P.VERTICAL["upward_gradient"],
        t_days=req.time_years * 365.0,
        wellbore_failure_prob=P.VERTICAL["wellbore_failure_prob"],
        # D1: real post-monsoon (shallowest) water table as receptor context
        water_table_m=flow.get("depth_to_water_shallow_m"),
        # 3.7: the wet/dry pair drives the seasonal vertical band. Both must be
        # present for a per-pin band; otherwise the screening falls back to the
        # state-wide CGWB campaign medians (flagged in `seasonal.water_table_source`).
        water_table_wet_m=flow.get("depth_to_water_shallow_m"),
        water_table_dry_m=flow.get("depth_to_water_deep_m"),
        # TIMELINE: this month's interpolated table (None unless a start date was
        # given). Amplitude is the pin's own wet/dry pair; only the monsoon
        # TIMING is state-wide -- see P.water_table_shape for why.
        water_table_now_m=(
            P.water_table_at_month(
                timeline["month"],
                flow.get("depth_to_water_shallow_m", P.VERTICAL_SEASONAL["water_table_wet_m"])
                or P.VERTICAL_SEASONAL["water_table_wet_m"],
                flow.get("depth_to_water_deep_m", P.VERTICAL_SEASONAL["water_table_dry_m"])
                or P.VERTICAL_SEASONAL["water_table_dry_m"])
            if timeline else None))
    # R-4: what a licensed programme would deploy to DETECT a vertical excursion,
    # so the screening index sits next to the monitoring that would find it.
    # NUREG/CR-6733 Sec. 4.3.3 (via NUREG-1569 p.139) also records that
    # "significant risks for vertical excursions may exist if monitor wells are
    # randomly located" at those densities -- which is the regulator's own basis
    # for treating the vertical pathway as non-trivial.
    _pattern_ha = (3.14159265 * (inputs["wellfield_width_m"] / 2.0) ** 2) / 1e4
    vertical["monitoring"] = {
        "pattern_area_ha": round(_pattern_ha, 2),
        "overlying_wells_required": max(1, round(
            _pattern_ha / P.VERTICAL["vertical_monitor_ha_per_well_overlying"])),
        "underlying_wells_required": max(1, round(
            _pattern_ha / P.VERTICAL["vertical_monitor_ha_per_well_underlying"])),
        "ha_per_well_overlying": P.VERTICAL["vertical_monitor_ha_per_well_overlying"],
        "ha_per_well_underlying": P.VERTICAL["vertical_monitor_ha_per_well_underlying"],
        "citation": P.VERTICAL["vertical_monitor_citation"],
        "note": ("Licensed vertical-excursion monitor-well density for a "
                 "wellfield of this footprint. The shallow-impact index above is "
                 "a screening estimate of the PATHWAY; this is the monitoring "
                 "that would be required to detect it."),
    }
    # D3: attach per-district provenance for the shallow-aquifer base
    vertical["district"] = vparams["district"]
    vertical["layer1_base_source"] = vparams["source"]
    vertical["layer1_base_confidence"] = vparams["confidence"]
    if vparams["fracture_min_m"] is not None:
        vertical["fractured_aquifer_range_m"] = [vparams["fracture_min_m"],
                                                 vparams["fracture_max_m"]]

    # Far-field reach note (Stage B2): the analytical plume advects down-gradient
    # UNBOUNDED, but a real plume discharges once it meets a perennial (gaining)
    # stream. B2 uses the HydroRIVERS-derived per-pin distance to the nearest
    # perennial river (data_prep.rivers); falls back to the statewide drainage-
    # density statistic if that artifact is absent. QUALITATIVE context only --
    # never caps a metric.
    from ml_pipeline.data_prep.rivers import river_distance_at, plume_river_discharge
    reach_km = a["migration_m"]["p50"] / 1000.0
    nearest_river_km = river_distance_at(req.lon, req.lat)
    # Polish #1: PRECISE test -- does the BIS-breach plume polygon actually cross a
    # perennial river? (Stronger than reach>distance: works even when pinned on a
    # river, and confirms a specific crossing.) The reach>distance heuristic is the
    # fallback when the plume clears its threshold nowhere / crosses nothing.
    bis_rings = [ring for cspec in contours if cspec.get("is_bis")
                 for ring in cspec["polygons"]]
    river_crossing = plume_river_discharge(bis_rings)
    far_field_note = None
    if river_crossing is not None:
        far_field_note = (
            f"Plume reaches a perennial river (~{river_crossing['max_discharge_cms']} "
            f"m³/s) — contamination discharges to surface water, so down-gradient "
            f"migration terminates there rather than continuing as modelled.")
    elif nearest_river_km is not None:
        if reach_km > nearest_river_km:
            far_field_note = (
                f"Far-field limit: predicted reach ~{reach_km:.1f} km exceeds the "
                f"~{nearest_river_km:.1f} km to the nearest perennial river, so the "
                f"plume would likely intercept perennial drainage and discharge to "
                f"surface water — real down-gradient migration is shorter than the "
                f"unbounded model shows.")
    elif reach_km > P.FARFIELD_DRAINAGE_P90_KM:          # no river artifact -> fallback
        far_field_note = (
            f"Far-field limit: predicted reach ~{reach_km:.0f} km assumes unbounded "
            f"down-gradient flow. Jharkhand's terrain is dissected by perennial "
            f"drainage (typically within ~{P.FARFIELD_DRAINAGE_MEDIAN_KM:.0f} km), so "
            f"at this scale the plume would intersect and discharge to surface water "
            f"— actual down-gradient migration is shorter than modelled.")

    # Module 2: user-facing ore-zone notice (uranium only)
    ore = hydro.get("ore_zone", {})
    notice = None
    if species == "uranium_ppb":
        if ore.get("zone") == "none":
            notice = ("Non-Ore Zone: restricting simulation to non-radiological "
                      "chemistry (sulfate / TDS). No uranium source term at this "
                      "location — ISR here would not leach uranium.")
        elif ore.get("zone") == "belt":
            notice = ("Prospective Belt (Singhbhum envelope): hypothetical "
                      "low-confidence ore assumed — uranium source term reduced.")

    # R-1: the REGULATORY excursion test (NUREG-1569 2-of-N conservative
    # indicators at the perimeter ring), reported ALONGSIDE the health-limit
    # breach above rather than replacing it. They answer different questions and
    # a real operation is judged on this one.
    from ml_pipeline.dashboard.isr_excursion import isr_indicator_excursion
    try:
        isr_excursion = isr_indicator_excursion(payload, ring_m=ring_offset)
    except Exception as e:                       # never break the main answer
        isr_excursion = {"status": f"unavailable: {type(e).__name__} ({e})"}

    # V-7: beta is the single most leveraged user-settable parameter (measured:
    # migration 7.1 m -> 232.4 m and excursion probability 0.00 -> 0.98 between
    # beta = 10 and beta = 0), and it is one of the values fidelity row 3.4 flags
    # as having ZERO Singhbhum measurements behind it. Keeping the override is
    # right -- expert use is legitimate -- but the user must be able to see what
    # it cost. When beta is supplied, the default-beta answer is returned next to
    # it. Deterministic only (no Monte-Carlo): this is a sensitivity readout.
    beta_override = None
    if payload.get("beta") is not None:
        try:
            default_payload = dict(payload)
            default_payload["beta"] = None
            d_inputs, d_hydro = resolve_inputs(default_payload)
            d = predict_analytical(**d_inputs)
            d.pop("_field", None)
            beta_override = {
                "user_beta": round(float(inputs["beta"]), 3),
                "default_beta": round(float(d_inputs["beta"]), 3),
                "with_user_beta": {
                    "area_ha": round(a["area_ha"]["p50"], 3),
                    "migration_m": round(a["migration_m"]["p50"], 1),
                    "excursion_probability": round(a["excursion_probability"], 3)},
                "with_default_beta": {
                    "area_ha": round(d["area_ha"]["p50"], 3),
                    "migration_m": round(d["migration_m"]["p50"], 1),
                    "excursion_probability": round(d["excursion_probability"], 3)},
                "note": ("beta (dual-porosity capacity ratio) has no Singhbhum "
                         "measurement behind it — see fidelity row 3.4. Both "
                         "answers are shown so the sensitivity of your override "
                         "is visible rather than implicit."),
            }
        except Exception as e:
            beta_override = {"status": f"unavailable: {type(e).__name__} ({e})"}

    return {
        "pin": {"lon": req.lon, "lat": req.lat},
        "hydro": hydro,
        "species": species,
        "threshold": threshold,
        "azimuth_deg": round(azimuth, 1),
        "azimuth_source": azimuth_source,
        # Containment diagnostic. eta = min(1, Q_net/(q*b*W)) SATURATES at 1, so
        # past the bleed that first achieves full capture the slider does nothing
        # -- measured at Jaduguda: migration flat from ~2.1% bleed upward. And
        # eta only holds the front WHILE OPERATING, so at long evaluation times
        # most travel happened after containment stopped mattering. Surfaced so
        # the UI can say this instead of looking unresponsive.
        "containment": {
            "eta": round(float(_feat_eta), 4),
            "saturated": bool(_feat_eta >= 0.999),
            "operating_years": round(float(req.operation_years), 2),
            "post_closure_years": round(max(req.time_years - req.operation_years, 0.0), 2),
        },
        "mode": req.mode,
        "notice": notice,
        "far_field_note": far_field_note,
        "nearest_river_km": nearest_river_km,
        "river_crossing": river_crossing,
        "ore_zone": ore,
        "restoration": restoration,
        "vertical": vertical,
        "timeline": timeline,
        # R-1: NUREG-1569 regulatory excursion test (conservative indicators)
        "isr_excursion": isr_excursion,
        # V-7: default-beta comparison when the user overrode beta
        "beta_override": beta_override,
        # wellfield_width_m is a well-PATTERN FOOTPRINT DIAMETER; the old label
        # invited reading it as a borehole width or a well spacing.
        "wellfield_geometry": {
            "pattern_footprint_diameter_m": round(inputs["wellfield_width_m"], 1),
            "pattern_footprint_radius_m": round(half_w, 1),
            "monitor_ring_m": round(ring_offset, 1),
            "monitor_ring_from_pin_m": round(ring_radius, 1),
            "monitor_ring_licensed_range_m": list(P.MONITOR_RING_RANGE_M),
            "monitor_ring_needs_justification": bool(
                ring_offset > P.MONITOR_RING_JUSTIFY_BEYOND_M),
            "monitor_ring_citation": P.MONITOR_RING_CITATION,
            "note": ("`wellfield_width_m` is the DIAMETER of the circular "
                     "well-pattern footprint (the full transverse extent of the "
                     "wellfield) — not a borehole width and not a well spacing."),
        },
        # inputs outside the deployed model's training envelope (ML bands
        # are extrapolating there; the conformal 80% guarantee is void)
        "extrapolation": extrapolation,
        "plume": {
            "contours": contours,
            "compliance_ring": {"radius_m": round(ring_radius, 1), "polygon": ring},
            "peak_conc": round(fm["peak_conc"], 2),
            "off_scale": fm.get("off_scale", False),
            "Xc_m": round(fm["Xc_m"], 1),
            "aspect_ratio": round(aspect, 2),
            # E1: radial vs drift diagnostic. Lambda<1 = the source-zone disc
            # dominates -> "migration" reads as contaminated EXTENT, not travel.
            "lambda_radial": round(fm["Xc_m"] / max(half_w, 1.0), 2),
            "radial_dominated": bool(fm["Xc_m"] / max(half_w, 1.0) < 1.0),
            # Source-zone state, so the UI can EXPLAIN a footprint that drops to
            # zero rather than leaving the user to read it as a fault. The leach
            # disc is uniform-concentration, so it leaves the exceedance area in
            # one step when the post-closure flush takes it under the threshold.
            "source_zone": {
                "conc": round(float(fm.get("source_zone_conc", 0.0)), 2),
                "threshold": round(float(fm["incremental_threshold"]), 2),
                "above_threshold": bool(fm.get("source_zone_above_threshold", False)),
                "radius_m": round(float(fm.get("source_zone_radius_m", 0.0)), 1),
                # drawn as its OWN layer so the plume contour is not welded to it
                "polygon": source_zone_poly,
                # bug C: the disc is uniform, so its footprint leaves the
                # exceedance area in ONE step. Report the step instead of
                # letting the user meet a bare 0.00 ha.
                "area_ha": round(math.pi
                                 * float(fm.get("source_zone_radius_m", 0.0)) ** 2 / 1e4, 3),
                "conc_over_threshold": (
                    round(float(fm.get("source_zone_conc", 0.0))
                          / float(fm["incremental_threshold"]), 4)
                    if fm.get("incremental_threshold") else None),
                "crossing": _source_zone_crossing(
                    C0=float(inputs["source_conc_C0"]),
                    thr_inc=float(fm["incremental_threshold"]),
                    op_years=float(req.operation_years),
                    rest_years=float(req.restoration_years or 0.0),
                    residual_ref=float((restoration or {}).get(
                        "residual_endpoint_fraction", 1.0)),
                    start_date=req.start_date),
            },
        },
        "metrics": {
            "analytical": {
                "area_ha": round(a["area_ha"]["p50"], 3),
                "migration_m": round(a["migration_m"]["p50"], 1),
                "compliance_conc": round(a["compliance_conc"]["p50"], 3),
                "excursion_probability": round(a["excursion_probability"], 3),
                "breach": int(a["breach_probability"]),
            },
            "ml": ml_metrics,
        },
        "ml_envelope": envelope,
        # bands whose extent is below the minimum drawable size, with the reason
        "ml_envelope_skipped": envelope_skipped,
        "ml_status": ml_status,
        # per-request analytical-vs-ML relative disagreement (surrogate health)
        "disagreement": disagreement,
    }


@app.get("/api/drift")
def api_drift():
    """Rolling analytical-vs-ML disagreement summary (surrogate drift monitor).
    `drifting: true` when the median relative gap on any metric exceeds the
    threshold over a sufficient window -> the surrogate is being queried where
    it no longer tracks the physics; retrain or restrict inputs."""
    return MONITOR.status()


@app.post("/api/drift/reset")
def api_drift_reset():
    MONITOR.reset()
    return {"status": "reset"}


# ----- static frontend -----
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/")
def index():
    idx = FRONTEND / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"detail": "frontend not built"}, status_code=404)


if __name__ == "__main__":
    import os
    import uvicorn
    # honour the PORT env var (preview autoPort / container platforms); default 8077
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8077")), reload=False)
