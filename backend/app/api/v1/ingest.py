"""Data Ingestion router."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.services.ingestion import IngestionService
from app.dependencies import require_analyst_or_admin
from app.exceptions import AppException

router = APIRouter(prefix="/ingest", tags=["Data Ingestion"])


@router.post("/districts/geojson")
async def ingest_districts_geojson(
    file: UploadFile = File(..., description="GeoJSON FeatureCollection of districts"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload a GeoJSON file to upsert district boundaries."""
    try:
        contents = await file.read()
        result = await IngestionService(db).ingest_geojson_districts(contents)
        return result
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/aquifers/xlsx")
async def ingest_aquifers_xlsx(
    block_id: uuid.UUID,
    file: UploadFile = File(..., description="Principle Aquifer xlsx file"),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    """Upload the Jharkhand aquifer xlsx to bulk-insert aquifer records for a block."""
    try:
        contents = await file.read()
        result = await IngestionService(db).ingest_xlsx_aquifers(contents, block_id)
        return result
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
