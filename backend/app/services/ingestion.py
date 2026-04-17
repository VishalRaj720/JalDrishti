"""
Ingestion service: parse CSV, GeoJSON, and shapefiles.
Month 3 scope: infrastructure + ingestion only (no imputation, no caching).
"""
import io
import re
import json
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from loguru import logger

try:
    import pandas as pd
    import geopandas as gpd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.aquifer import AquiferRepository
from app.repositories.district import DistrictRepository, BlockRepository
from app.repositories.monitoring_station import MonitoringStationRepository
from app.repositories.monitoring_well import MonitoringWellRepository
from app.repositories.water_sample import WaterSampleRepository
from app.repositories.data_source import DataSourceRepository
from app.services.hydro_literature import get_literature_defaults


# -------------------- constants --------------------

TDS_FROM_EC_FACTOR = 0.65  # TDS (mg/L) ≈ 0.65 × EC (µS/cm)

_VALID_AQUIFER_TYPES = {
    "basalt", "charnockite", "gneiss", "limestone", "sandstone", "alluvium",
    "basement_gneissic_complex", "granite", "intrusive", "laterite",
    "quartzite", "schist",
}


# -------------------- parsing helpers --------------------

def _safe_float(val: Any) -> Optional[float]:
    """Parse a scalar into float; return None for nan, empty, '-', or non-numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        try:
            f = float(val)
            return f if f == f else None  # NaN check
        except (TypeError, ValueError):
            return None
    s = str(val).strip()
    if s == "" or s == "-" or s.lower() in ("nan", "none", "null", "na"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_range_midpoint(val: Any) -> Optional[float]:
    """Parse strings like '26 - 176', '100 - 130', '2-3%', '10-35' → midpoint float.
    Returns None for unparseable input. Strips %, spaces, and non-numeric suffixes."""
    if val is None:
        return None
    s = str(val).strip()
    if s == "" or s == "-":
        return None
    # Direct numeric?
    direct = _safe_float(s)
    if direct is not None:
        return direct
    # Extract numbers — robust to '%', units, arbitrary separators
    nums = re.findall(r"-?\d+(?:\.\d+)?", s)
    if not nums:
        return None
    floats = [float(n) for n in nums]
    if len(floats) == 1:
        return floats[0]
    return (floats[0] + floats[-1]) / 2.0


def _normalise_aquifer_type(raw: Any) -> str:
    """Map free-text aquifer label to one of the enum values. Falls back to 'gneiss'."""
    s = (str(raw or "")).lower().strip().replace(" ", "_").replace("-", "_")
    if s in _VALID_AQUIFER_TYPES:
        return s
    # Fuzzy substring match
    for t in _VALID_AQUIFER_TYPES:
        if t in s:
            return t
    return "gneiss"


def _jharkhand_bbox_ok(lon: float, lat: float) -> bool:
    """Approximate Jharkhand bounding box: lon 83.3-87.9, lat 21.9-25.6."""
    return 83.3 <= lon <= 87.9 and 21.9 <= lat <= 25.6


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -------------------- spatial mapping helpers --------------------

async def _find_block_for_point(
    db: AsyncSession, longitude: float, latitude: float
) -> Optional[uuid.UUID]:
    """Find block containing point; fall back to nearest block centroid."""
    q = text("""
        SELECT id FROM blocks
        WHERE geometry IS NOT NULL
          AND ST_Within(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), geometry)
        LIMIT 1
    """)
    row = (await db.execute(q, {"lon": longitude, "lat": latitude})).first()
    if row is not None:
        return row[0]
    # Fallback: nearest
    q2 = text("""
        SELECT id FROM blocks
        WHERE geometry IS NOT NULL
        ORDER BY ST_Distance(
            geometry::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
        ) ASC
        LIMIT 1
    """)
    row = (await db.execute(q2, {"lon": longitude, "lat": latitude})).first()
    return row[0] if row is not None else None


async def _find_block_for_polygon_wkt(db: AsyncSession, wkt: str) -> Optional[uuid.UUID]:
    """Find block with largest intersection with given polygon WKT; fall back to nearest."""
    q = text("""
        SELECT id
        FROM blocks
        WHERE geometry IS NOT NULL
          AND ST_Intersects(geometry, ST_GeomFromText(:wkt, 4326))
        ORDER BY ST_Area(ST_Intersection(geometry, ST_GeomFromText(:wkt, 4326))) DESC
        LIMIT 1
    """)
    row = (await db.execute(q, {"wkt": wkt})).first()
    if row is not None:
        return row[0]
    q2 = text("""
        SELECT id FROM blocks
        WHERE geometry IS NOT NULL
        ORDER BY ST_Distance(geometry::geography, ST_GeomFromText(:wkt, 4326)::geography) ASC
        LIMIT 1
    """)
    row = (await db.execute(q2, {"wkt": wkt})).first()
    return row[0] if row is not None else None


# -------------------- IngestionService --------------------

class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.aquifer_repo = AquiferRepository(db)
        self.district_repo = DistrictRepository(db)
        self.block_repo = BlockRepository(db)
        self.station_repo = MonitoringStationRepository(db)
        self.well_repo = MonitoringWellRepository(db)
        self.sample_repo = WaterSampleRepository(db)
        self.source_repo = DataSourceRepository(db)

    # ----------------- data source provenance -----------------

    async def _register_source(
        self, name: str, source_type: str, file_name: Optional[str],
        content: bytes, row_count: Optional[int] = None, notes: Optional[str] = None,
    ) -> Tuple[uuid.UUID, bool]:
        """Return (source_id, is_new). is_new=False means same checksum was ingested before."""
        checksum = _checksum(content)
        existing = await self.source_repo.get_by_name_checksum(name, checksum)
        if existing:
            return existing.id, False
        created = await self.source_repo.create({
            "name": name,
            "source_type": source_type,
            "file_name": file_name,
            "checksum": checksum,
            "row_count": row_count,
            "notes": notes,
        })
        return created.id, True

    # ----------------- districts -----------------

    async def ingest_geojson_districts(self, geojson_bytes: bytes, file_name: Optional[str] = None) -> Dict[str, int]:
        """Upsert districts from a GeoJSON FeatureCollection.
        Matches names against 'District' | 'name' | 'NAME' | 'district' in properties."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("geopandas not installed.")
        gdf = gpd.read_file(io.BytesIO(geojson_bytes))
        inserted, updated, skipped = 0, 0, 0
        source_id, _ = await self._register_source(
            name="districts_geojson", source_type="geojson_district",
            file_name=file_name, content=geojson_bytes, row_count=len(gdf),
        )
        for _, row in gdf.iterrows():
            name = (
                row.get("District") or row.get("name") or row.get("NAME")
                or row.get("district")
            )
            if not name or row.geometry is None:
                skipped += 1
                continue
            geom_wkt = row.geometry.wkt
            existing = await self.district_repo.get_by_name(str(name))
            if existing:
                await self.district_repo.update(existing, {
                    "geometry": f"SRID=4326;{geom_wkt}",
                })
                updated += 1
            else:
                await self.district_repo.create({
                    "name": str(name),
                    "geometry": f"SRID=4326;{geom_wkt}",
                })
                inserted += 1
        logger.info(f"Districts: {inserted} inserted, {updated} updated, {skipped} skipped.")
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "source_id": str(source_id)}

    # ----------------- sub-districts (blocks) -----------------

    async def ingest_geojson_subdistricts(self, geojson_bytes: bytes, file_name: Optional[str] = None) -> Dict[str, int]:
        """Upsert blocks (sub-districts) from a GeoJSON FeatureCollection.
        Each feature must carry 'Sub_District' (name) and 'District' (parent)."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("geopandas not installed.")
        gdf = gpd.read_file(io.BytesIO(geojson_bytes))
        inserted, updated, skipped = 0, 0, 0
        source_id, _ = await self._register_source(
            name="subdistricts_geojson", source_type="geojson_subdistrict",
            file_name=file_name, content=geojson_bytes, row_count=len(gdf),
        )
        for _, row in gdf.iterrows():
            name = row.get("Sub_District") or row.get("subdistrict") or row.get("name")
            parent = row.get("District") or row.get("district")
            if not name or not parent or row.geometry is None:
                skipped += 1
                continue
            district = await self.district_repo.get_by_name(str(parent))
            if district is None:
                skipped += 1
                logger.warning(f"Sub_District '{name}' skipped: parent district '{parent}' not found.")
                continue
            geom_wkt = row.geometry.wkt
            existing = await self.block_repo.get_by_name_in_district(str(name), district.id)
            if existing:
                await self.block_repo.update(existing, {"geometry": f"SRID=4326;{geom_wkt}"})
                updated += 1
            else:
                await self.block_repo.create({
                    "name": str(name),
                    "district_id": district.id,
                    "geometry": f"SRID=4326;{geom_wkt}",
                })
                inserted += 1
        logger.info(f"Sub-districts: {inserted} inserted, {updated} updated, {skipped} skipped.")
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "source_id": str(source_id)}

    # ----------------- aquifers (geojson) -----------------

    async def ingest_geojson_aquifers(self, geojson_bytes: bytes, file_name: Optional[str] = None) -> Dict[str, int]:
        """Upsert aquifers from Aquifers_Jharkhand.geojson. Parses range strings to midpoints;
        fills missing porosity / hydraulic_conductivity from literature table."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("geopandas not installed.")
        gdf = gpd.read_file(io.BytesIO(geojson_bytes))
        source_id, is_new = await self._register_source(
            name="aquifers_geojson", source_type="geojson_aquifer",
            file_name=file_name, content=geojson_bytes, row_count=len(gdf),
        )
        if not is_new:
            logger.info("Aquifers geojson already ingested (checksum match); skipping.")
            return {"inserted": 0, "skipped": len(gdf), "source_id": str(source_id), "reason": "already_ingested"}
        inserted, skipped = 0, 0
        for idx, row in gdf.iterrows():
            if row.geometry is None:
                skipped += 1
                continue

            aq_type = _normalise_aquifer_type(row.get("aquifer"))
            lit = get_literature_defaults(aq_type)

            # Range-string fields in the source geojson:
            #   m2_perday  → transmissivity (m²/day)
            #   avg_mbgl   → depth to water (m bgl)
            #   yeild__    → specific yield (%)
            #   mbgl       → max depth (m bgl)
            transmissivity = _parse_range_midpoint(row.get("m2_perday"))
            dtw_avg = _parse_range_midpoint(row.get("avg_mbgl"))
            specific_yield = _parse_range_midpoint(row.get("yeild__"))
            max_depth = _parse_range_midpoint(row.get("mbgl"))
            min_depth = _parse_range_midpoint(row.get("zone_m"))

            # Provenance tags
            porosity = lit["porosity"]
            porosity_source = "literature"
            hydraulic_conductivity = lit["hydraulic_conductivity"]
            hydraulic_conductivity_source = "literature"
            transmissivity_source = "derived" if transmissivity is not None else None

            geom_wkt = row.geometry.wkt
            block_id = await _find_block_for_polygon_wkt(self.db, geom_wkt)

            name = str(row.get("aquifer0") or row.get("aquifer") or f"aquifer-{idx}")

            thickness = None
            if min_depth is not None and max_depth is not None and max_depth >= min_depth:
                thickness = max_depth - min_depth

            obj = {
                "block_id": block_id,
                "name": name,
                "type": aq_type,
                "min_depth": min_depth,
                "max_depth": max_depth,
                "thickness": thickness,
                "porosity": porosity,
                "porosity_source": porosity_source,
                "hydraulic_conductivity": hydraulic_conductivity,
                "hydraulic_conductivity_source": hydraulic_conductivity_source,
                "transmissivity": transmissivity,
                "transmissivity_source": transmissivity_source,
                "specific_yield": specific_yield,
                "dtw_decadal_avg": dtw_avg,
                "yield_range": str(row.get("m3_per_day") or "")[:50] or None,
                "geometry": f"SRID=4326;{geom_wkt}",
            }
            obj = {k: v for k, v in obj.items() if v is not None}
            await self.aquifer_repo.create(obj)
            inserted += 1

        logger.info(f"Aquifers (geojson): {inserted} inserted, {skipped} skipped.")
        return {"inserted": inserted, "skipped": skipped, "source_id": str(source_id)}

    # ----------------- groundwater level timeseries (JSON) -----------------

    async def ingest_json_groundwater_levels(
        self, station_json: Dict[str, Any], file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upsert one CGWB station + its readings.
        Expected shape: {'station': {...}, 'readings': [{'timestamp', 'water_level_m'}, ...]}"""
        st = station_json.get("station") or {}
        readings = station_json.get("readings") or []
        lat = _safe_float(st.get("Latitude"))
        lon = _safe_float(st.get("Longitude"))
        name = st.get("Station Name") or st.get("Station Code")
        if lat is None or lon is None or not name:
            return {"skipped": True, "reason": "missing lat/lon/name"}
        if not _jharkhand_bbox_ok(lon, lat):
            return {"skipped": True, "reason": "outside_jharkhand_bbox"}

        content_bytes = json.dumps(station_json, sort_keys=True, default=str).encode("utf-8")
        source_id, _ = await self._register_source(
            name=f"gw_level:{name}", source_type="json_gw_level",
            file_name=file_name, content=content_bytes, row_count=len(readings),
        )

        block_id = await _find_block_for_point(self.db, lon, lat)
        if block_id is None:
            return {"skipped": True, "reason": "no_block_match"}

        # Dedupe by (name, lat, lon)
        station = await self._find_station(name=str(name), lat=lat, lon=lon, block_id=block_id)
        if station is None:
            station = await self.station_repo.create({
                "block_id": block_id,
                "name": str(name),
                "village": st.get("Village"),
                "latitude": lat,
                "longitude": lon,
                "well_depth": _safe_float(st.get("Well Depth")),
            })

        # Insert readings (skip existing timestamps via (station_id, recorded_at) dedupe)
        existing_ts = await self._existing_reading_ts(station.id)
        inserted_readings = 0
        from app.models.monitoring_station import GroundwaterLevelReading
        for r in readings:
            ts_raw = r.get("timestamp")
            lvl = _safe_float(r.get("water_level_m"))
            if ts_raw is None or lvl is None:
                continue
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if ts in existing_ts:
                continue
            self.db.add(GroundwaterLevelReading(
                station_id=station.id, recorded_at=ts, groundwater_level=lvl,
            ))
            existing_ts.add(ts)
            inserted_readings += 1
        await self.db.flush()

        return {
            "station_id": str(station.id),
            "station_name": str(name),
            "readings_inserted": inserted_readings,
            "source_id": str(source_id),
        }

    async def _find_station(self, name: str, lat: float, lon: float, block_id: uuid.UUID):
        from app.models.monitoring_station import MonitoringStation
        from sqlalchemy import select
        result = await self.db.execute(
            select(MonitoringStation).where(
                MonitoringStation.name == name,
                MonitoringStation.latitude == lat,
                MonitoringStation.longitude == lon,
            )
        )
        return result.scalar_one_or_none()

    async def _existing_reading_ts(self, station_id: uuid.UUID) -> set:
        from app.models.monitoring_station import GroundwaterLevelReading
        from sqlalchemy import select
        result = await self.db.execute(
            select(GroundwaterLevelReading.recorded_at).where(
                GroundwaterLevelReading.station_id == station_id
            )
        )
        return set(result.scalars().all())

    # ----------------- water-quality CSV -----------------

    async def ingest_csv_water_quality(
        self, csv_bytes: bytes, file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parse India-WRIS / CGWB water-quality CSV → monitoring_wells + water_samples.
        TDS is always derived as 0.65 × EC and flagged with tds_derived=True."""
        if not PANDAS_AVAILABLE:
            raise RuntimeError("pandas not installed.")
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="utf-8-sig")
        df.columns = [str(c).strip() for c in df.columns]

        col = _build_column_resolver(df.columns)
        source_id, is_new = await self._register_source(
            name="water_quality_csv", source_type="csv_water_quality",
            file_name=file_name, content=csv_bytes, row_count=len(df),
        )
        if not is_new:
            logger.info("Water-quality CSV already ingested (checksum match); skipping.")
            return {
                "wells_created": 0, "wells_reused": 0, "samples_inserted": 0,
                "skipped": len(df), "source_id": str(source_id), "reason": "already_ingested",
            }

        wells_created, wells_reused, samples_inserted, skipped = 0, 0, 0, 0
        for _, row in df.iterrows():
            lat = _safe_float(row.get(col("Latitude")))
            lon = _safe_float(row.get(col("Longitude")))
            if lat is None or lon is None or not _jharkhand_bbox_ok(lon, lat):
                skipped += 1
                continue

            well = await self.well_repo.get_by_lat_lon(lat, lon)
            if well is None:
                block_id = await _find_block_for_point(self.db, lon, lat)
                well_name = str(row.get(col("Location")) or f"well-{lat:.4f}-{lon:.4f}")
                well = await self.well_repo.create({
                    "name": well_name,
                    "block_id": block_id,
                    "location": f"SRID=4326;POINT({lon} {lat})",
                    "latitude": lat,
                    "longitude": lon,
                    "source_id": source_id,
                })
                wells_created += 1
            else:
                wells_reused += 1

            # Sample timestamp: use Year if present, else skip (sampled_at is NOT NULL)
            year = _safe_float(row.get(col("Year")))
            if year is None:
                skipped += 1
                continue
            sampled_at = datetime(int(year), 1, 1, tzinfo=timezone.utc)

            ec = _safe_float(row.get(col("EC")))
            tds = (ec * TDS_FROM_EC_FACTOR) if ec is not None else None

            sample = {
                "well_id": well.id,
                "source_id": source_id,
                "sampled_at": sampled_at,
                "ph": _safe_float(row.get(col("pH"))),
                "ec_us_cm": ec,
                "tds_mg_l": tds,
                "tds_derived": tds is not None,
                "total_hardness": _safe_float(row.get(col("Total Hardness"))),
                "uranium_ppb": _safe_float(row.get(col("U"))),
                "nitrate_mg_l": _safe_float(row.get(col("NO3"))),
                "fluoride_mg_l": _safe_float(row.get(col("F"))),
                "arsenic_ppb": _safe_float(row.get(col("As"))),
                "iron_ppm": _safe_float(row.get(col("Fe"))),
                "chloride_mg_l": _safe_float(row.get(col("Cl"))),
                "sulphate_mg_l": _safe_float(row.get(col("SO4"))),
                "bicarbonate_mg_l": _safe_float(row.get(col("HCO3"))),
                "carbonate_mg_l": _safe_float(row.get(col("CO3"))),
                "phosphate_mg_l": _safe_float(row.get(col("PO4"))),
                "calcium_mg_l": _safe_float(row.get(col("Ca"))),
                "magnesium_mg_l": _safe_float(row.get(col("Mg"))),
                "sodium_mg_l": _safe_float(row.get(col("Na"))),
                "potassium_mg_l": _safe_float(row.get(col("K"))),
            }
            await self.sample_repo.create(sample)
            samples_inserted += 1

        logger.info(
            f"Water quality CSV: wells created={wells_created} reused={wells_reused} "
            f"samples_inserted={samples_inserted} skipped={skipped}"
        )
        return {
            "wells_created": wells_created,
            "wells_reused": wells_reused,
            "samples_inserted": samples_inserted,
            "skipped": skipped,
            "source_id": str(source_id),
        }


# -------------------- CSV column resolver --------------------

def _build_column_resolver(columns: Iterable[str]):
    """Return a function col(key) -> actual DataFrame column name or None.
    Key matches case-insensitive as substring on DF headers."""
    cols = list(columns)
    lc = {c.lower(): c for c in cols}

    # Explicit aliases — first match wins
    aliases = {
        "Latitude": ["latitude", "lat"],
        "Longitude": ["longitude", "lon", "long"],
        "Location": ["location", "site", "village"],
        "Year": ["year"],
        "pH": ["ph"],
        "EC": ["ec ", "ec(", "ec/"],   # 'EC (µS/cm at' -> substring 'ec ('
        "Total Hardness": ["hardness"],
        "U": ["u (", "uranium"],
        "NO3": ["no3", "nitrate"],
        "F": ["f (", "fluoride"],
        "As": ["as ", "as(", "arsenic"],
        "Fe": ["fe ", "fe(", "iron"],
        "Cl": ["cl ", "cl("],
        "SO4": ["so4", "sulphate", "sulfate"],
        "HCO3": ["hco3", "bicarb"],
        "CO3": ["co3", "carbon"],
        "PO4": ["po4", "phosph"],
        "Ca": ["ca ", "ca("],
        "Mg": ["mg ", "mg("],
        "Na": ["na ", "na("],
        "K": ["k ", "k("],
    }

    def resolve(key: str) -> Optional[str]:
        # Direct case-insensitive match
        if key.lower() in lc:
            return lc[key.lower()]
        for alias in aliases.get(key, []):
            for c_low, c_orig in lc.items():
                if alias in c_low:
                    return c_orig
        return None

    return resolve
