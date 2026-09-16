"""The data-quality report, computed from the database it describes.

R16 (2026-09-16). `GET /ingest/data-quality-report` used to read a JSON file
that `scripts/seed` wrote next to the code on whichever machine ran the seed.
The deployed database was seeded from the owner's laptop, so the file existed
there and nowhere else, and the Administration screen on the deployed host
read *"No data_quality_report.json yet. Run `python -m scripts.seed`"* -- an
instruction that could not have helped, because running it there would have
written the file to a container filesystem that is discarded on the next
deploy.

The report is a set of counts and null-rates over tables that already exist.
It is cheaper to compute than to store, and computed it can never be stale or
describe a different database from the one serving it. `scripts/seed` still
writes the JSON as a record of what a particular seed run produced; the
endpoint no longer depends on that file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aquifer import Aquifer
from app.models.block import Block
from app.models.district import District
from app.models.monitoring_station import GroundwaterLevelReading, MonitoringStation
from app.models.monitoring_well import MonitoringWell
from app.models.water_sample import WaterSample

WHO_URANIUM_PPB = 30.0  # WHO limit 0.03 mg/L = 30 ppb
TDS_DERIVATION_FACTOR = 0.65
TARGET_MIN_WELLS = 50
TARGET_MIN_SAMPLES = 200

#: Every determinand column in `water_samples`, for the null-rate table. A
#: column at 100 % null is the data gap the proposal asks this project to name.
SAMPLE_COLUMNS = (
    "ph", "ec_us_cm", "tds_mg_l", "uranium_ppb", "nitrate_mg_l", "fluoride_mg_l",
    "arsenic_ppb", "iron_ppm", "chloride_mg_l", "sulphate_mg_l", "bicarbonate_mg_l",
    "total_hardness", "calcium_mg_l", "magnesium_mg_l", "sodium_mg_l", "potassium_mg_l",
)


async def sample_null_rates(db: AsyncSession, total: int) -> Dict[str, float]:
    null_rates: Dict[str, float] = {}
    for c in SAMPLE_COLUMNS:
        # Column names come from the tuple above, never from a caller.
        nulls = (await db.execute(
            text(f"SELECT COUNT(*) FROM water_samples WHERE {c} IS NULL")
        )).scalar_one()
        null_rates[c] = round(nulls / total, 4) if total else 1.0
    return null_rates


async def build_quality_report(db: AsyncSession) -> Dict[str, Any]:
    districts = (await db.execute(select(func.count()).select_from(District))).scalar_one()
    blocks = (await db.execute(select(func.count()).select_from(Block))).scalar_one()
    aquifers = (await db.execute(select(func.count()).select_from(Aquifer))).scalar_one()
    stations = (await db.execute(select(func.count()).select_from(MonitoringStation))).scalar_one()
    readings = (await db.execute(select(func.count()).select_from(GroundwaterLevelReading))).scalar_one()
    wells = (await db.execute(select(func.count()).select_from(MonitoringWell))).scalar_one()
    samples = (await db.execute(select(func.count()).select_from(WaterSample))).scalar_one()

    null_rates = await sample_null_rates(db, samples) if samples > 0 else {}

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

    literature_filled: Dict[str, Dict[str, int]] = {}
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
        "source": "computed live from the database",
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
        "water_sample_null_rates": null_rates,
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
