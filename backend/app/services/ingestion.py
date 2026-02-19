"""
Ingestion service: parse CSV, GeoJSON, and shapefiles.
Uses pandas, geopandas, and openpyxl for batch data loading.
"""
import io
import json
import uuid
from typing import Dict, Any, List
from loguru import logger

try:
    import pandas as pd
    import geopandas as gpd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.aquifer import AquiferRepository
from app.repositories.district import DistrictRepository, BlockRepository


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.aquifer_repo = AquiferRepository(db)
        self.district_repo = DistrictRepository(db)
        self.block_repo = BlockRepository(db)

    async def ingest_geojson_districts(self, geojson_bytes: bytes) -> Dict[str, int]:
        """Parse a GeoJSON FeatureCollection and upsert districts."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("geopandas not installed.")
        gdf = gpd.read_file(io.BytesIO(geojson_bytes))
        inserted, updated = 0, 0
        for _, row in gdf.iterrows():
            name = row.get("name") or row.get("NAME") or row.get("district")
            if not name:
                continue
            geom_wkt = row.geometry.wkt if row.geometry else None
            existing = await self.district_repo.get_by_name(str(name))
            if existing:
                await self.district_repo.update(existing, {
                    "geometry": f"SRID=4326;{geom_wkt}" if geom_wkt else None
                })
                updated += 1
            else:
                await self.district_repo.create({
                    "name": str(name),
                    "geometry": f"SRID=4326;{geom_wkt}" if geom_wkt else None,
                })
                inserted += 1
        logger.info(f"District ingestion: {inserted} inserted, {updated} updated.")
        return {"inserted": inserted, "updated": updated}

    async def ingest_xlsx_aquifers(self, xlsx_bytes: bytes, block_id: uuid.UUID) -> Dict[str, int]:
        """Parse the Principle Aquifer of Jharkhand xlsx format."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("pandas not installed.")
        df = pd.read_excel(io.BytesIO(xlsx_bytes))
        df.columns = [str(c).strip().lower() for c in df.columns]
        inserted = 0
        for _, row in df.iterrows():
            name = str(row.get("aquifer name", row.get("name", f"aquifer-{inserted}")))
            aq_type_raw = str(row.get("type", row.get("aquifer type", "gneiss"))).lower().strip()
            # Sanitise type
            valid_types = ["basalt","charnockite","gneiss","limestone","sandstone","alluvium",
                          "basement_gneissic_complex","granite","intrusive","laterite","quartzite","schist"]
            aq_type = aq_type_raw if aq_type_raw in valid_types else "gneiss"
            obj = {
                "block_id": block_id,
                "name": name,
                "type": aq_type,
                "min_depth": _safe_float(row.get("min depth")),
                "max_depth": _safe_float(row.get("max depth")),
                "porosity": _safe_float(row.get("porosity")),
                "hydraulic_conductivity": _safe_float(row.get("hydraulic conductivity")),
                "transmissivity": _safe_float(row.get("transmissivity")),
                "storage_coefficient": _safe_float(row.get("storage coefficient")),
                "specific_yield": _safe_float(row.get("specific yield")),
                "quality_ec": _safe_float(row.get("ec")),
                "dtw_decadal_avg": _safe_float(row.get("dtw")),
                "fractures_encountered": str(row.get("fractures encountered", "")),
                "yield_range": str(row.get("yield", "")),
            }
            min_d, max_d = obj.get("min_depth"), obj.get("max_depth")
            if min_d and max_d:
                obj["thickness"] = max_d - min_d
            obj_clean = {k: v for k, v in obj.items() if v is not None and v != "nan"}
            await self.aquifer_repo.create(obj_clean)
            inserted += 1
        logger.info(f"Aquifer XLSX ingestion: {inserted} records inserted.")
        return {"inserted": inserted}


def _safe_float(val) -> float | None:
    try:
        v = float(val)
        return v if not (v != v) else None  # NaN check
    except (TypeError, ValueError):
        return None
