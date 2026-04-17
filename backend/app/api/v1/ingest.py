"""Data Ingestion router."""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.ingestion import IngestionService
from app.dependencies import require_analyst_or_admin, require_any_role
from app.exceptions import AppException

router = APIRouter(prefix="/ingest", tags=["Data Ingestion"])


# ── GeoJSON upserts ───────────────────────────────────────────────────────────

@router.post("/districts/geojson")
async def ingest_districts_geojson(
    file: UploadFile = File(..., description="GeoJSON FeatureCollection of districts"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload a GeoJSON file to upsert district boundaries."""
    try:
        contents = await file.read()
        return await IngestionService(db).ingest_geojson_districts(contents, file_name=file.filename)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/subdistricts/geojson")
async def ingest_subdistricts_geojson(
    file: UploadFile = File(..., description="GeoJSON FeatureCollection of sub-districts/blocks"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload a GeoJSON file to upsert sub-district (block) boundaries."""
    try:
        contents = await file.read()
        return await IngestionService(db).ingest_geojson_subdistricts(contents, file_name=file.filename)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/aquifers/geojson")
async def ingest_aquifers_geojson(
    file: UploadFile = File(..., description="GeoJSON FeatureCollection of aquifers"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload GeoJSON aquifers. Parses range strings → midpoint; fills missing
    porosity / hydraulic_conductivity from literature with `*_source` provenance tags."""
    try:
        contents = await file.read()
        return await IngestionService(db).ingest_geojson_aquifers(contents, file_name=file.filename)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Groundwater levels (JSON time-series) ─────────────────────────────────────

@router.post("/groundwater-levels/json")
async def ingest_groundwater_levels_json(
    file: UploadFile = File(..., description="CGWB station JSON with readings"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload a single CGWB groundwater-level station JSON."""
    try:
        contents = await file.read()
        data = json.loads(contents)
        return await IngestionService(db).ingest_json_groundwater_levels(data, file_name=file.filename)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Water quality (CSV) ───────────────────────────────────────────────────────

@router.post("/water-quality/csv")
async def ingest_water_quality_csv(
    file: UploadFile = File(..., description="Water-quality sample CSV"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload a water-quality CSV. Creates monitoring_wells deduped by (lat,lon);
    derives TDS = 0.65 × EC with `tds_derived=true` when EC present and TDS absent."""
    try:
        contents = await file.read()
        return await IngestionService(db).ingest_csv_water_quality(contents, file_name=file.filename)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Data-quality report ───────────────────────────────────────────────────────

_REPORT_PATH = Path(__file__).resolve().parents[3] / "reports" / "data_quality_report.json"


@router.get("/data-quality-report")
async def get_data_quality_report(_=Depends(require_any_role)):
    """Return the most recent seed-script data-quality report (if present)."""
    if not _REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No data_quality_report.json yet. Run `python -m scripts.seed_month3_data`.",
        )
    try:
        return json.loads(_REPORT_PATH.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Corrupt report file: {e}")
