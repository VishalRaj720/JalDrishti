"""
ml_pipeline.dashboard.server  (PHASE 4 -- FastAPI backend)
========================================================
Decoupled API that wraps the Phase-3 unified predictor and serves the vanilla-JS
frontend. The analytical engine always runs (it provides the plume geometry);
the ML surrogate runs alongside it (P10/P50/P90 bands) so the UI's
"Analytical vs ML" toggle is instant client-side.

Run:
    uvicorn ml_pipeline.dashboard.server:app --reload --port 8077
    # then open http://localhost:8077
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ml_pipeline.config import parameters as P
from ml_pipeline.ml.predict import predict, predict_analytical
from ml_pipeline.dashboard.resolve import resolve_inputs, pin_info, _assets
from ml_pipeline.dashboard.plume_geometry import (
    field_to_contours, compliance_ring, ml_envelope_ellipses,
)

FRONTEND = Path(__file__).resolve().parent / "frontend"
COMPLIANCE_BUFFER_M = 100.0

app = FastAPI(title="JalDrishti ml_pipeline — ISR plume surrogate", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


class PredictRequest(BaseModel):
    lon: float
    lat: float
    species: str = "uranium_ppb"
    regime: str | None = None                      # None -> use pin's lithology
    injection_rate_m3_day: float = Field(2500, ge=50, le=20000)
    bleed_percent: float = Field(2.0, ge=0, le=20)
    operation_years: float = Field(8, ge=0.5, le=20)
    gradient_i: float = Field(0.005, ge=0.0001, le=0.05)
    time_years: float = Field(10, ge=0, le=20)
    wellfield_width_m: float = Field(300, ge=50, le=1500)
    azimuth_deg: float = Field(45, ge=0, le=360)
    mode: str = "both"                             # analytical | ml | both


def _bands(d: dict) -> dict:
    return {"p10": round(d["p10"], 3), "p50": round(d["p50"], 3), "p90": round(d["p90"], 3)}


@app.get("/api/health")
def health():
    try:
        from ml_pipeline.ml.predict import _surrogate
        _surrogate()
        ml_ok = True
    except Exception as e:
        ml_ok = f"unavailable: {type(e).__name__}"
    return {"status": "ok", "ml_surrogate": ml_ok,
            "bis_thresholds": P.EXCURSION_THRESHOLDS}


@app.get("/api/pin")
def api_pin(lon: float = Query(...), lat: float = Query(...)):
    if not (P.JHARKHAND_BOUNDS["lon_min"] - 1 <= lon <= P.JHARKHAND_BOUNDS["lon_max"] + 1):
        raise HTTPException(400, "longitude outside Jharkhand region")
    return pin_info(lon, lat)


@app.get("/api/aquifers")
def api_aquifers():
    """Regime-coloured aquifer polygons (simplified) for the map overlay."""
    aq, _, _ = _assets()
    g = aq[["lithology", "regime", "K_m_day", "eff_porosity", "thickness_m", "geometry"]].copy()
    g["geometry"] = g["geometry"].simplify(0.004)        # lighten payload
    return JSONResponse(json.loads(g.to_json()))


@app.post("/api/predict")
def api_predict(req: PredictRequest):
    payload = req.model_dump()
    try:
        inputs, hydro = resolve_inputs(payload)
    except Exception as e:
        raise HTTPException(400, f"could not resolve pin hydrogeology: {e}")

    species = inputs["species"]
    threshold = P.EXCURSION_THRESHOLDS[species]

    # --- analytical (always: provides the plume geometry) ---
    a = predict_analytical(**inputs)
    field = a.pop("_field")
    fm = field.metrics
    contours = field_to_contours(field, lon0=req.lon, lat0=req.lat,
                                 azimuth_deg=req.azimuth_deg, threshold=threshold,
                                 background=inputs["background_conc_Cb"])
    ring_radius = inputs["wellfield_width_m"] / 2.0 + COMPLIANCE_BUFFER_M
    ring = compliance_ring(req.lon, req.lat, req.azimuth_deg, ring_radius)
    aspect = fm["max_downgradient_m"] / max(fm["plume_halfwidth_m"], 1.0)

    # --- ML surrogate (bands), if artifacts present ---
    ml_metrics, envelope, ml_status = None, None, "ok"
    try:
        m = predict("ml", **inputs)
        ml_metrics = {
            "area_ha": _bands(m["area_ha"]),
            "migration_m": _bands(m["migration_m"]),
            "compliance_conc": _bands(m["compliance_conc"]),
            "excursion_probability": round(m["excursion_probability"], 3),
            "breach_probability": round(m["breach_probability"], 3),
        }
        envelope = ml_envelope_ellipses(
            req.lon, req.lat, req.azimuth_deg,
            {k: m["migration_m"][k] for k in ("p10", "p50", "p90")}, aspect)
    except Exception as e:
        ml_status = f"unavailable: {type(e).__name__} ({e})"

    return {
        "pin": {"lon": req.lon, "lat": req.lat},
        "hydro": hydro,
        "species": species,
        "threshold": threshold,
        "azimuth_deg": req.azimuth_deg,
        "mode": req.mode,
        "plume": {
            "contours": contours,
            "compliance_ring": {"radius_m": round(ring_radius, 1), "polygon": ring},
            "peak_conc": round(fm["peak_conc"], 2),
            "off_scale": fm.get("off_scale", False),
            "Xc_m": round(fm["Xc_m"], 1),
            "aspect_ratio": round(aspect, 2),
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
    }


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
