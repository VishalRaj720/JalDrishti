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

import json
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
)
from ml_pipeline.dashboard.drift import MONITOR
from ml_pipeline.data_prep.boundary import in_jharkhand, boundary_geojson

FRONTEND = Path(__file__).resolve().parent / "frontend"


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
    time_years: float = Field(10, ge=_OR["horizon_years"][0],
                              le=_OR["horizon_years"][1])
    wellfield_width_m: float = Field(300, ge=_OR["wellfield_width_m"][0],
                                     le=_OR["wellfield_width_m"][1])
    restoration_years: float = Field(0, ge=0, le=_OR["restoration_years"][1])
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
    # expert overrides (None -> resolved from the pin / literature)
    kd_L_kg: float | None = Field(None, ge=0, le=50)
    beta: float | None = Field(None, ge=0, le=50)
    K_m_day: float | None = Field(None, gt=0, le=500)
    phi_mobile: float | None = Field(None, gt=0, le=0.45)
    downtime_fraction: float | None = Field(None, ge=0, le=0.30)
    gradient_seasonal_amp: float | None = Field(None, ge=0, le=0.40)


def _bands(d: dict) -> dict:
    return {"p10": round(d["p10"], 3), "p50": round(d["p50"], 3), "p90": round(d["p90"], 3)}


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
            "cors_origins": _cors_origins()}


@app.get("/api/pin")
def api_pin(lon: float = Query(...), lat: float = Query(...)):
    if not _in_jharkhand(lon, lat):
        raise HTTPException(422, _OUTSIDE_JH)
    return pin_info(lon, lat)


@app.get("/api/boundary")
def api_boundary():
    """Dissolved Jharkhand state boundary (lon/lat GeoJSON geometry) for the map
    outline + client-side inverse mask. Simplified to keep the payload light."""
    return JSONResponse(boundary_geojson())


@app.get("/api/ore")
def api_ore():
    """Uranium deposit polygons + Singhbhum belt envelope (Module 2 overlay), so
    users can see which zones carry a real / hypothetical / no uranium source."""
    from ml_pipeline.data_prep.ore_loader import ore_geojson
    return JSONResponse(ore_geojson())


@app.get("/api/rivers")
def api_rivers():
    """Perennial river polylines (HydroRIVERS, DIS>=1 m3/s) for the map overlay,
    so users see where a plume would discharge to surface water (Stage B2)."""
    from ml_pipeline.data_prep.rivers import rivers_geojson, RIVER_NPZ
    if not RIVER_NPZ.exists():
        return JSONResponse({"type": "FeatureCollection", "features": []})
    return JSONResponse(rivers_geojson())


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
    return JSONResponse({"type": "FeatureCollection", "features": feats})


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
    return JSONResponse({"type": "FeatureCollection", "features": feats})


@app.get("/api/aquifers")
def api_aquifers():
    """Regime-coloured aquifer polygons (simplified) for the map overlay."""
    aq, _, _ = _assets()
    g = aq[["lithology", "regime", "K_m_day", "eff_porosity", "thickness_m", "geometry"]].copy()
    g["geometry"] = g["geometry"].simplify(0.004)        # lighten payload
    return JSONResponse(json.loads(g.to_json()))


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

    # --- analytical (always: provides the plume geometry) ---
    a = predict_analytical(**inputs)
    field = a.pop("_field")
    fm = field.metrics
    contours = field_to_contours(field, lon0=req.lon, lat0=req.lat,
                                 azimuth_deg=azimuth, threshold=threshold,
                                 background=inputs["background_conc_Cb"],
                                 x_offset_m=half_w)
    ring_radius = half_w + P.COMPLIANCE_BUFFER_M      # from the centre pin
    ring = compliance_ring(req.lon, req.lat, azimuth, ring_radius)
    aspect = fm["max_downgradient_m"] / max(fm["plume_halfwidth_m"], 1.0)

    # --- ML surrogate (bands), if artifacts present ---
    # Module 2: in a non-ore zone the uranium source term is clamped to a trace
    # level (far outside the surrogate's training envelope), so bypass the ML
    # call entirely and let the analytical engine report the ~zero U plume.
    ml_metrics, envelope, ml_status, m = None, None, "ok", None
    if hydro.get("u_suppressed"):
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
            envelope = ml_envelope_ellipses(
                req.lon, req.lat, azimuth,
                {k: m["migration_m"][k] for k in ("p10", "p50", "p90")}, aspect,
                x_offset_m=half_w)
        except Exception as e:
            m = None
            ml_status = f"unavailable: {type(e).__name__} ({e})"

    # drift monitor: record analytical-vs-ML disagreement for this request
    disagreement = MONITOR.record(
        a, m, extrapolation=extrapolation,
        off_scale=bool(fm.get("off_scale", False)))

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
        water_table_m=flow.get("depth_to_water_shallow_m"))
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

    return {
        "pin": {"lon": req.lon, "lat": req.lat},
        "hydro": hydro,
        "species": species,
        "threshold": threshold,
        "azimuth_deg": round(azimuth, 1),
        "azimuth_source": azimuth_source,
        "mode": req.mode,
        "notice": notice,
        "far_field_note": far_field_note,
        "nearest_river_km": nearest_river_km,
        "river_crossing": river_crossing,
        "ore_zone": ore,
        "vertical": vertical,
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
