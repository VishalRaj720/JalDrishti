"""Universal, idempotent database seed for JalDrishti.

ONE command takes an empty database all the way to a fully populated one:

    createdb groundwater_db            # or: CREATE DATABASE groundwater_db;
    python -m scripts.seed             # schema + every table filled

What it does, in order:
  0. Schema      : PostGIS extension + ENUM types + all tables (via scripts.init_db)
  1. Users       : default RBAC users (admin / analyst / viewer)
  2. ISR points  : a hypothetical uranium ISR injection point near Jaduguda
  3. Geodata     : Jharkhand districts, sub-districts (blocks), aquifers,
                   groundwater-level time series, and CGWB water-quality samples
                   (incl. real uranium), ingested from repo_root/Datasets
  4. Report      : a data-quality report at backend/reports/data_quality_report.json

Idempotent by design — re-running does NOT duplicate rows:
  * schema     : init_db uses CREATE ... IF NOT EXISTS / create_all (no-op if present)
  * users      : skipped if the email already exists
  * ISR points : skipped if the name already exists
  * geodata    : IngestionService dedupes by data_sources.checksum (same file
                 content -> skipped)

Flags:
    python -m scripts.seed --skip-schema      # assume tables already exist (e.g. Alembic)
    python -m scripts.seed --datasets-dir ../Datasets
    python -m scripts.seed --report-path reports/data_quality_report.json
"""
import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from geoalchemy2.elements import WKTElement
from loguru import logger
from sqlalchemy import func, select, text

from app.database import AsyncSessionLocal
from app.services.auth import hash_password
from app.services.ingestion import IngestionService
from app.models.user import User, UserRole
from app.models.isr_point import IsrPoint
from app.models.district import District
from app.models.block import Block
from app.models.aquifer import Aquifer
from app.models.monitoring_station import MonitoringStation, GroundwaterLevelReading
from app.models.monitoring_well import MonitoringWell
from app.models.water_sample import WaterSample
from scripts.init_db import init_db


WHO_URANIUM_PPB = 30.0  # WHO limit 0.03 mg/L = 30 ppb
TDS_DERIVATION_FACTOR = 0.65

# Quantitative targets from the roadmap
TARGET_MIN_WELLS = 50
TARGET_MIN_SAMPLES = 200


SEED_USERS = [
    {"username": "admin",   "email": "admin@jaldrishti.local",   "password": "admin123",   "role": UserRole.admin},
    {"username": "analyst", "email": "analyst@jaldrishti.local", "password": "analyst123", "role": UserRole.analyst},
    {"username": "viewer",  "email": "viewer@jaldrishti.local",  "password": "viewer123",  "role": UserRole.viewer},
]

# A hypothetical ISR field near Jaduguda — the East Singhbhum uranium belt is the
# only place in Jharkhand where uranium ISR would plausibly be sited. This gives
# the simulation/spread feature a realistic default scenario to run against.
SEED_ISR_POINTS = [
    {"name": "Jaduguda (hypothetical ISR)", "lon": 86.36, "lat": 22.65, "injection_rate": 1000.0},
]


def _default_datasets_dir() -> Path:
    # this file lives at backend/scripts/seed.py; datasets live at repo_root/Datasets
    return Path(__file__).resolve().parents[2] / "Datasets"


def _default_report_path() -> Path:
    return Path(__file__).resolve().parents[1] / "reports" / "data_quality_report.json"


# ----------------- 1. users -----------------

async def seed_users(db) -> None:
    logger.info("Seeding users ...")
    for u in SEED_USERS:
        existing = await db.execute(select(User).where(User.email == u["email"]))
        if existing.scalar_one_or_none():
            logger.info(f"  [skip] {u['email']} already exists")
            continue
        db.add(User(
            id=uuid.uuid4(),
            username=u["username"],
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            role=u["role"],
        ))
        logger.info(f"  [ok]   created {u['role'].value}: {u['email']}")
    await db.commit()


# ----------------- 2. ISR points -----------------

async def seed_isr_points(db) -> None:
    logger.info("Seeding ISR points ...")
    for p in SEED_ISR_POINTS:
        existing = await db.execute(select(IsrPoint).where(IsrPoint.name == p["name"]))
        if existing.scalar_one_or_none():
            logger.info(f"  [skip] ISR point '{p['name']}' already exists")
            continue
        db.add(IsrPoint(
            name=p["name"],
            location=WKTElement(f"POINT({p['lon']} {p['lat']})", srid=4326),
            injection_rate=p["injection_rate"],
        ))
        logger.info(f"  [ok]   created ISR point '{p['name']}'")
    await db.commit()


# ----------------- 3. geodata ingestion stages -----------------

async def _stage_districts(svc: IngestionService, path: Path) -> Dict[str, Any]:
    logger.info(f"[1/5] Ingesting districts from {path.name} ...")
    return await svc.ingest_geojson_districts(path.read_bytes(), file_name=path.name)


async def _stage_subdistricts(svc: IngestionService, path: Path) -> Dict[str, Any]:
    logger.info(f"[2/5] Ingesting sub-districts (blocks) from {path.name} ...")
    return await svc.ingest_geojson_subdistricts(path.read_bytes(), file_name=path.name)


async def _stage_aquifers(svc: IngestionService, path: Path) -> Dict[str, Any]:
    logger.info(f"[3/5] Ingesting aquifers from {path.name} ...")
    return await svc.ingest_geojson_aquifers(path.read_bytes(), file_name=path.name)


async def _stage_groundwater_levels(svc: IngestionService, folder: Path) -> Dict[str, Any]:
    logger.info(f"[4/5] Ingesting groundwater-level JSONs from {folder} ...")
    files = sorted(folder.glob("*.json"))
    total_stations, total_readings, skipped = 0, 0, 0
    for f in files:
        try:
            station_json = json.loads(f.read_bytes())
        except json.JSONDecodeError as e:
            logger.warning(f"  {f.name}: JSON parse error ({e}); skipping")
            skipped += 1
            continue
        result = await svc.ingest_json_groundwater_levels(station_json, file_name=f.name)
        if result.get("skipped"):
            skipped += 1
            logger.debug(f"  {f.name}: skipped ({result.get('reason')})")
            continue
        total_stations += 1
        total_readings += result.get("readings_inserted", 0)
    return {"files_processed": len(files), "stations": total_stations,
            "readings_inserted": total_readings, "skipped": skipped}


async def _stage_water_quality(svc: IngestionService, path: Path) -> Dict[str, Any]:
    logger.info(f"[5/5] Ingesting water-quality CSV from {path.name} ...")
    return await svc.ingest_csv_water_quality(path.read_bytes(), file_name=path.name)


async def seed_geodata(db, datasets_dir: Path) -> Dict[str, Any]:
    """Run all five ingestion stages in one transaction. Returns stage results."""
    district_file = datasets_dir / "District_Boundary_JH.geojson"
    subdistrict_file = datasets_dir / "Sub_District_Boundary_JH.geojson"
    aquifer_file = datasets_dir / "Aquifers_Jharkhand.geojson"
    gwl_folder = datasets_dir / "waterLevelJson"
    wq_file = datasets_dir / "waterQuality_jharkhand.csv"

    for p in (district_file, subdistrict_file, aquifer_file, gwl_folder, wq_file):
        if not p.exists():
            raise FileNotFoundError(f"Required dataset missing: {p}")

    svc = IngestionService(db)
    stage_results: Dict[str, Any] = {}
    stage_results["districts"] = await _stage_districts(svc, district_file)
    logger.info(f"  -> {stage_results['districts']}")
    stage_results["subdistricts"] = await _stage_subdistricts(svc, subdistrict_file)
    logger.info(f"  -> {stage_results['subdistricts']}")
    stage_results["aquifers"] = await _stage_aquifers(svc, aquifer_file)
    logger.info(f"  -> {stage_results['aquifers']}")
    stage_results["groundwater_levels"] = await _stage_groundwater_levels(svc, gwl_folder)
    logger.info(f"  -> {stage_results['groundwater_levels']}")
    stage_results["water_quality"] = await _stage_water_quality(svc, wq_file)
    logger.info(f"  -> {stage_results['water_quality']}")
    await db.commit()
    return stage_results


# ----------------- 4. data-quality report -----------------

async def _sample_null_rates(db, total: int) -> Dict[str, float]:
    cols = [
        "ph", "ec_us_cm", "tds_mg_l", "uranium_ppb", "nitrate_mg_l", "fluoride_mg_l",
        "arsenic_ppb", "iron_ppm", "chloride_mg_l", "sulphate_mg_l", "bicarbonate_mg_l",
        "total_hardness", "calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "potassium_mg_l",
    ]
    null_rates: Dict[str, float] = {}
    for c in cols:
        nulls = (await db.execute(
            text(f"SELECT COUNT(*) FROM water_samples WHERE {c} IS NULL")
        )).scalar_one()
        null_rates[c] = round(nulls / total, 4)
    return null_rates


async def _build_quality_report(db) -> Dict[str, Any]:
    districts = (await db.execute(select(func.count()).select_from(District))).scalar_one()
    blocks = (await db.execute(select(func.count()).select_from(Block))).scalar_one()
    aquifers = (await db.execute(select(func.count()).select_from(Aquifer))).scalar_one()
    stations = (await db.execute(select(func.count()).select_from(MonitoringStation))).scalar_one()
    readings = (await db.execute(select(func.count()).select_from(GroundwaterLevelReading))).scalar_one()
    wells = (await db.execute(select(func.count()).select_from(MonitoringWell))).scalar_one()
    samples = (await db.execute(select(func.count()).select_from(WaterSample))).scalar_one()

    sample_null_rates: Dict[str, float] = {}
    if samples > 0:
        sample_null_rates = await _sample_null_rates(db, samples)

    uranium_exceeded = (await db.execute(
        select(func.count()).select_from(WaterSample).where(
            WaterSample.uranium_ppb.is_not(None),
            WaterSample.uranium_ppb > WHO_URANIUM_PPB,
        )
    )).scalar_one()
    uranium_present = (await db.execute(
        select(func.count()).select_from(WaterSample).where(
            WaterSample.uranium_ppb.is_not(None)
        )
    )).scalar_one()

    tds_derived_count = (await db.execute(
        select(func.count()).select_from(WaterSample).where(WaterSample.tds_derived.is_(True))
    )).scalar_one()

    bbox_outliers = (await db.execute(text("""
        SELECT COUNT(*) FROM monitoring_wells
        WHERE latitude < 21.9 OR latitude > 25.6
           OR longitude < 83.3 OR longitude > 87.9
    """))).scalar_one()

    literature_filled = {}
    for col in ("porosity_source", "hydraulic_conductivity_source", "transmissivity_source"):
        row = (await db.execute(text(f"""
            SELECT {col} AS src, COUNT(*) AS n FROM aquifers GROUP BY {col}
        """))).all()
        literature_filled[col] = {str(src or "null"): int(n) for src, n in row}

    wells_without_block = (await db.execute(
        select(func.count()).select_from(MonitoringWell).where(MonitoringWell.block_id.is_(None))
    )).scalar_one()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_counts": {
            "districts": districts,
            "blocks": blocks,
            "aquifers": aquifers,
            "monitoring_stations": stations,
            "groundwater_level_readings": readings,
            "monitoring_wells": wells,
            "water_samples": samples,
        },
        "targets": {
            "min_wells": TARGET_MIN_WELLS,
            "min_samples": TARGET_MIN_SAMPLES,
            "wells_met": wells >= TARGET_MIN_WELLS,
            "samples_met": samples >= TARGET_MIN_SAMPLES,
        },
        "water_sample_null_rates": sample_null_rates,
        "uranium": {
            "records_with_value": uranium_present,
            "who_exceedance_count": uranium_exceeded,
            "who_threshold_ppb": WHO_URANIUM_PPB,
        },
        "tds": {
            "derived_count": tds_derived_count,
            "factor_used": TDS_DERIVATION_FACTOR,
        },
        "spatial_checks": {
            "wells_outside_jharkhand_bbox": bbox_outliers,
            "wells_without_block": wells_without_block,
        },
        "aquifer_provenance": literature_filled,
    }


# ----------------- runner -----------------

async def run(datasets_dir: Path, report_path: Path, skip_schema: bool) -> int:
    logger.info("=" * 60)
    logger.info("JalDrishti universal seed starting")
    logger.info(f"Datasets dir : {datasets_dir}")
    logger.info(f"Report path  : {report_path}")
    logger.info("=" * 60)

    # 0. Schema
    if skip_schema:
        logger.info("Skipping schema creation (--skip-schema).")
    else:
        logger.info("Ensuring schema (PostGIS + ENUMs + tables) ...")
        await init_db()

    # 1 + 2. Users and ISR points
    async with AsyncSessionLocal() as db:
        await seed_users(db)
        await seed_isr_points(db)

    # 3. Geodata
    async with AsyncSessionLocal() as db:
        try:
            stage_results = await seed_geodata(db, datasets_dir)
        except FileNotFoundError as e:
            logger.error(str(e))
            return 2
        except Exception:
            await db.rollback()
            logger.exception("Ingestion failed; rolled back.")
            return 1

    # 4. Quality report
    async with AsyncSessionLocal() as db:
        report = await _build_quality_report(db)
    report["ingestion_stage_results"] = stage_results

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str))
    logger.info(f"Data-quality report written: {report_path}")

    wells = report["row_counts"]["monitoring_wells"]
    samples = report["row_counts"]["water_samples"]
    logger.info("-" * 60)
    logger.info(f"Wells:   {wells}  (target >= {TARGET_MIN_WELLS})   "
                f"{'OK' if wells >= TARGET_MIN_WELLS else 'FAIL'}")
    logger.info(f"Samples: {samples} (target >= {TARGET_MIN_SAMPLES})  "
                f"{'OK' if samples >= TARGET_MIN_SAMPLES else 'FAIL'}")
    logger.info("-" * 60)
    if wells < TARGET_MIN_WELLS or samples < TARGET_MIN_SAMPLES:
        logger.warning("One or more deliverable targets were not met.")
        return 3
    logger.info("Universal seed completed successfully.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Universal JalDrishti DB seed.")
    parser.add_argument("--datasets-dir", type=Path, default=_default_datasets_dir())
    parser.add_argument("--report-path", type=Path, default=_default_report_path())
    parser.add_argument("--skip-schema", action="store_true",
                        help="Assume tables already exist (e.g. created via Alembic).")
    args = parser.parse_args()
    return asyncio.run(run(args.datasets_dir, args.report_path, args.skip_schema))


if __name__ == "__main__":
    sys.exit(main())
