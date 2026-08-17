"""Universal, idempotent database seed for JalDrishti.

ONE command takes an empty database all the way to a fully populated one:

    createdb groundwater_db            # or: CREATE DATABASE groundwater_db;
    python -m scripts.seed             # schema + every table filled

What it does, in order:
  0. Schema      : PostGIS extension + ENUM types + all tables (via scripts.init_db)
  1. Users       : one account per role (admin / regulator / analyst /
                   field_officer / citizen)
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

from app.database import AsyncSessionLocal as _AppSessionLocal


def _session_factory():
    """Seed as the OWNER role, not the restricted application role.

    `DATABASE_URL` points at `jaldrishti_app`, which is NOSUPERUSER/NOBYPASSRLS
    by design — so writing `isr_points` through it fails the `isr_points_write`
    policy with "new row violates row-level security policy". Seeding is
    owner-level work, exactly like migrations, so it uses the same privileged
    connection they do. Falls back to the app session when the two roles have
    not been split (a fresh clone).
    """
    from app.config import settings
    if settings.MIGRATION_DATABASE_URL:
        from sqlalchemy.ext.asyncio import (create_async_engine,
                                            async_sessionmaker, AsyncSession)
        engine = create_async_engine(settings.MIGRATION_DATABASE_URL)
        return async_sessionmaker(engine, class_=AsyncSession,
                                  expire_on_commit=False), engine
    return _AppSessionLocal, None


AsyncSessionLocal, _seed_engine = _session_factory()
from app.services.auth import hash_password
from app.services.ingestion import IngestionService
from app.models.user import User, UserRole
from app.models.org import Org
from app.models.dataset_version import DatasetVersion
from app.models.data_source import DataSource
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


# ONE ACCOUNT PER DESIGNED ROLE. The seed previously created three
# (admin / analyst / viewer) while the system had five, so `regulator` and
# `field_officer` -- the two roles that carry the review workflow -- could not be
# exercised at all without hand-crafting a user.
#
# These are DEMONSTRATION credentials for a prototype. They are weak and public,
# which is fine for a fellowship demo and is not fine anywhere else; the README
# says so beside the table.
SEED_USERS = [
    {"username": "admin",     "email": "admin@jaldrishti.local",     "password": "admin123",     "role": UserRole.admin},
    {"username": "regulator", "email": "regulator@jaldrishti.local", "password": "regulator123", "role": UserRole.regulator},
    {"username": "analyst",   "email": "analyst@jaldrishti.local",   "password": "analyst123",   "role": UserRole.analyst},
    {"username": "fieldofficer", "email": "field@jaldrishti.local",  "password": "field123",     "role": UserRole.field_officer},
    {"username": "citizen",   "email": "citizen@jaldrishti.local",   "password": "citizen123",   "role": UserRole.citizen},
]

#: Accounts from before the five-role model that should not survive a reseed.
#: `viewer` was migrated to the `citizen` ROLE by 0008, but the account itself
#: lingered with its old identity; leaving it would mean two citizen logins and
#: a stale name in the audit trail.
RETIRED_USER_EMAILS = ["viewer@jaldrishti.local"]

# A hypothetical ISR field near Jaduguda — the East Singhbhum uranium belt is the
# only place in Jharkhand where uranium ISR would plausibly be sited. This gives
# the simulation/spread feature a realistic default scenario to run against.
SEED_ISR_POINTS = [
    {"name": "Jaduguda (hypothetical ISR)", "lon": 86.36, "lat": 22.65, "injection_rate_m3_day": 1000.0},
]


def _default_datasets_dir() -> Path:
    # this file lives at backend/scripts/seed.py; datasets live at repo_root/Datasets
    return Path(__file__).resolve().parents[2] / "Datasets"


def _default_report_path() -> Path:
    return Path(__file__).resolve().parents[1] / "reports" / "data_quality_report.json"


# ----------------- 0b. organisations + provenance spine (P1) -----------------

SEED_ORGS = [
    {"code": "BITS", "name": "BIT Sindri — TEXMiN Mining CPS CoE", "kind": "academic"},
    {"code": "CGWB", "name": "Central Ground Water Board", "kind": "regulator"},
    {"code": "SPCB", "name": "Jharkhand State Pollution Control Board", "kind": "regulator"},
]

# The org that owns seeded accounts and hypothetical sites. BIT Sindri runs the
# platform; CGWB and SPCB exist so P2's row-level security has real tenants to
# separate, not so seed users are filed under a regulator they do not work for.
HOST_ORG_CODE = "BITS"

# One entry per CITABLE dataset, keyed by the `source_type` its loads carry in
# `data_sources`. `n_supporting` and `caveat` are the reason this table exists:
# they carry what a checksum cannot, and the portal must surface them wherever
# the derived number is shown.
SEED_DATASET_VERSIONS = {
    "geojson_district": dict(
        label="JH-ADMIN-DISTRICT-v1", source_org="GSI / Survey of India",
        citation="Jharkhand district administrative boundaries, District_Boundary_JH.geojson.",
        n_supporting=24, caveat=None),
    "geojson_subdistrict": dict(
        label="JH-ADMIN-BLOCK-v1", source_org="GSI / Survey of India",
        citation="Jharkhand sub-district (block) boundaries, Sub_District_Boundary_JH.geojson.",
        n_supporting=264, caveat=None),
    "geojson_aquifer": dict(
        label="JH-AQUIFER-v1", source_org="CGWB",
        citation="CGWB principal aquifer systems of Jharkhand, Aquifers_Jharkhand.geojson.",
        n_supporting=23,
        caveat="23 polygons for the whole state: aquifer properties are regional "
               "averages and must not be read as site-specific values."),
    "json_gw_level": dict(
        label="CGWB-WATERLEVEL-JH-v1", source_org="CGWB",
        citation="CGWB Jharkhand groundwater level monitoring campaigns, "
                 "cgwb_waterlevel_jharkhand.csv.",
        n_supporting=8345,
        caveat="9,583 source rows contain 1,238 duplicate (station, date) pairs, "
               "collapsed to 8,345 by the composite primary key. Station names are "
               "NOT unique: 398 distinct names span 415 distinct "
               "(name, latitude, longitude) triples, so any aggregation grouping "
               "by name alone over-merges 17 stations."),
    "csv_water_quality": dict(
        label="CGWB-WATERQUALITY-JH-v1", source_org="CGWB",
        citation="CGWB Jharkhand groundwater quality survey, waterQuality_jharkhand.csv.",
        n_supporting=397,
        caveat="One sample per well; no temporal series, so seasonal variation "
               "cannot be separated from spatial variation."),
}


async def seed_orgs(db) -> None:
    logger.info("Seeding organisations ...")
    for o in SEED_ORGS:
        existing = await db.execute(select(Org).where(Org.code == o["code"]))
        if existing.scalar_one_or_none():
            logger.info(f"  [skip] org {o['code']} already exists")
            continue
        db.add(Org(**o))
        logger.info(f"  [ok]   created org {o['code']}")
    await db.commit()


async def seed_dataset_versions(db) -> None:
    """Register the citable datasets and link the load ledger to them.

    Idempotent on `label`, and the linking step only ever fills a NULL, so
    re-running never re-points a load that was deliberately reassigned.
    """
    logger.info("Seeding dataset versions (provenance spine) ...")
    for source_type, spec in SEED_DATASET_VERSIONS.items():
        row = (await db.execute(
            select(DatasetVersion).where(DatasetVersion.label == spec["label"])
        )).scalar_one_or_none()
        if row is None:
            row = DatasetVersion(**spec)
            db.add(row)
            await db.flush()
            logger.info(f"  [ok]   registered {spec['label']}")
        else:
            logger.info(f"  [skip] {spec['label']} already registered")

        linked = await db.execute(
            text("UPDATE data_sources SET dataset_version_id = :dv "
                 "WHERE source_type = :st AND dataset_version_id IS NULL"),
            {"dv": row.id, "st": source_type},
        )
        if linked.rowcount:
            logger.info(f"         linked {linked.rowcount} load(s) of "
                        f"source_type={source_type}")
    await db.commit()

    orphaned = (await db.execute(text(
        "SELECT count(*) FROM data_sources WHERE dataset_version_id IS NULL"
    ))).scalar()
    if orphaned:
        # Not fatal: an unregistered load is a data-quality finding, not a
        # broken seed. It is reported so it cannot pass unnoticed.
        logger.warning(f"  {orphaned} data_sources row(s) have no dataset_version; "
                       f"add a SEED_DATASET_VERSIONS entry for their source_type.")


async def assign_users_to_host_org(db) -> None:
    """Give every account without an org the host org. Never reassigns."""
    org_id = (await db.execute(
        select(Org.id).where(Org.code == HOST_ORG_CODE))).scalar_one()
    res = await db.execute(
        text("UPDATE users SET org_id = :o WHERE org_id IS NULL"), {"o": org_id})
    await db.commit()
    if res.rowcount:
        logger.info(f"  [ok]   assigned {res.rowcount} user(s) to {HOST_ORG_CODE}")


# ----------------- 1. users -----------------

async def retire_legacy_users(db) -> None:
    """Remove pre-five-role demo accounts. Safe: FKs from audit_log and
    field_observations are ON DELETE SET NULL / RESTRICT, so this refuses rather
    than cascades if the account actually did something worth keeping."""
    for email in RETIRED_USER_EMAILS:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is None:
            continue
        try:
            await db.delete(existing)
            await db.commit()
            logger.info(f"  [ok]   retired legacy account {email}")
        except Exception as exc:
            await db.rollback()
            logger.warning(f"  [skip] {email} has dependent records, left in place: "
                           f"{type(exc).__name__}")


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
            injection_rate_m3_day=p["injection_rate_m3_day"],
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


async def _stage_groundwater_levels(svc: IngestionService, csv_path: Path) -> Dict[str, Any]:
    """Ingest the CGWB statewide water-level series.

    SOURCE CHANGED 2026-08-11. This stage used to walk `Datasets/waterLevelJson/`,
    a folder of 28 India-WRIS JSON files covering Dhanbad only. That folder was
    deleted in the July dataset consolidation when it was superseded by
    `cgwb_waterlevel_jharkhand.csv` -- 398 stations across all 24 districts,
    9,583 readings, 2013-2021, four CGWB campaigns a year. The seed still pointed
    at the deleted folder and aborted with "Required dataset missing".

    The CSV is grouped per station and handed to the SAME
    `ingest_json_groundwater_levels()` the JSON files used, so the ingestion
    service, its dedupe and its provenance registration are untouched -- only
    the reader in front of it changed.
    """
    import csv as _csv
    from collections import defaultdict

    logger.info(f"[4/5] Ingesting groundwater levels from {csv_path.name} ...")
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(_csv.DictReader(fh))

    # group by the physical station: name + coordinates
    grouped: Dict[tuple, list] = defaultdict(list)
    for r in rows:
        key = (r.get("station_name"), r.get("latitude"), r.get("longitude"))
        if not all(key):
            continue
        grouped[key].append(r)

    total_stations, total_readings, skipped = 0, 0, 0
    for (name, lat, lon), recs in grouped.items():
        station_json = {
            "station": {"Station Name": name, "Latitude": lat, "Longitude": lon,
                        "Village": recs[0].get("district_name")},
            "readings": [{"timestamp": r.get("date"),
                          "water_level_m": r.get("currentlevel")} for r in recs],
        }
        result = await svc.ingest_json_groundwater_levels(
            station_json, file_name=csv_path.name)
        if result.get("skipped"):
            skipped += 1
            logger.debug(f"  {name}: skipped ({result.get('reason')})")
            continue
        total_stations += 1
        total_readings += result.get("readings_inserted", 0)
    return {"rows_read": len(rows), "stations_in_file": len(grouped),
            "stations": total_stations, "readings_inserted": total_readings,
            "skipped": skipped}


async def _stage_water_quality(svc: IngestionService, path: Path) -> Dict[str, Any]:
    logger.info(f"[5/5] Ingesting water-quality CSV from {path.name} ...")
    return await svc.ingest_csv_water_quality(path.read_bytes(), file_name=path.name)


async def seed_geodata(db, datasets_dir: Path) -> Dict[str, Any]:
    """Run all five ingestion stages in one transaction. Returns stage results."""
    district_file = datasets_dir / "District_Boundary_JH.geojson"
    subdistrict_file = datasets_dir / "Sub_District_Boundary_JH.geojson"
    aquifer_file = datasets_dir / "Aquifers_Jharkhand.geojson"
    # statewide CGWB series; replaced the deleted Dhanbad-only waterLevelJson/
    gwl_file = datasets_dir / "cgwb_waterlevel_jharkhand.csv"
    wq_file = datasets_dir / "waterQuality_jharkhand.csv"

    for p in (district_file, subdistrict_file, aquifer_file, gwl_file, wq_file):
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
    stage_results["groundwater_levels"] = await _stage_groundwater_levels(svc, gwl_file)
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

    # 0b + 1 + 2. Orgs, users and ISR points. Orgs come first: users reference them.
    async with AsyncSessionLocal() as db:
        await seed_orgs(db)
        await retire_legacy_users(db)
        await seed_users(db)
        await assign_users_to_host_org(db)
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

    # 3b. Provenance spine — after ingestion, because it links the loads that
    # ingestion just wrote into `data_sources`.
    async with AsyncSessionLocal() as db:
        await seed_dataset_versions(db)

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
