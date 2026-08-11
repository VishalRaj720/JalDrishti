"""Districts router."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.district import DistrictCreate, DistrictUpdate, DistrictResponse
from app.services.district import DistrictService
from app.dependencies import require_analyst_or_admin, require_admin, require_any_role
from app.exceptions import AppException

from fastapi.responses import JSONResponse

router = APIRouter(prefix="/districts", tags=["Districts"])


@router.get("", response_model=List[DistrictResponse])
async def list_districts(
    skip: int = 0, limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    return await DistrictService(db).list(skip=skip, limit=limit)


@router.get("/geojson", response_class=JSONResponse)
async def districts_geojson(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role)
):
    """Return all districts as a single GeoJSON FeatureCollection."""
    from shapely.geometry import mapping
    from geoalchemy2.shape import to_shape
    districts = await DistrictService(db).list(limit=500)
    features = []
    for d in districts:
        if d.geometry:
            features.append({
                "type": "Feature",
                "geometry": mapping(to_shape(d.geometry)),
                "properties": {
                    "id": str(d.id),
                    "name": d.name,
                    "vulnerability_index": float(d.vulnerability_index) if d.vulnerability_index else None,
                    "avg_porosity": float(d.avg_porosity) if d.avg_porosity else None,
                }
            })
    return {"type": "FeatureCollection", "features": features}


@router.get("/{district_id}", response_model=DistrictResponse)
async def get_district(
    district_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_any_role),
):
    try:
        return await DistrictService(db).get(district_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

# ── Reference geography is READ-ONLY ────────────────────────────────
# P2 (PRODUCT_DESIGN.md section 3.1) deleted POST / PUT / DELETE here.
# Districts come from CGWB/GSI and are not user-editable content: editing them
# through an ad-hoc CRUD endpoint silently forks the scientific basis of every
# simulation that has already run against them, with no version record.
# The supported path is versioned bulk ingest -- POST /api/v1/ingest/* --
# which checksums the source file and writes a `data_sources` row linked to a
# `dataset_versions` entry.
