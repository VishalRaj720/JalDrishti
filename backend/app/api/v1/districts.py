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


@router.post("", response_model=DistrictResponse, status_code=201)
async def create_district(
    payload: DistrictCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await DistrictService(db).create(payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"DEBUG ERROR: {str(e)}")


@router.put("/{district_id}", response_model=DistrictResponse)
async def update_district(
    district_id: uuid.UUID, payload: DistrictUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_analyst_or_admin),
):
    try:
        return await DistrictService(db).update(district_id, payload)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/{district_id}", status_code=204)
async def delete_district(
    district_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    try:
        await DistrictService(db).delete(district_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
