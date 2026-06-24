"""Consolidated, idempotent database seed for JalDrishti.

One command seeds everything:
  1. Default RBAC users (admin / analyst / viewer)
  2. A hypothetical uranium ISR injection point near Jaduguda (East Singhbhum)
  3. Jharkhand geodata: districts, blocks, aquifers, groundwater-level time series,
     and CGWB water-quality samples (incl. real uranium)

Idempotent by design — re-running does NOT duplicate rows:
  * users      : skipped if the email already exists
  * ISR points : skipped if the name already exists
  * geodata    : IngestionService dedupes by data_sources.checksum (same file
                 content -> skipped)

Usage (from backend/, after `python -m scripts.init_db`):
    python -m scripts.seed
"""
import asyncio
import sys
import uuid
from pathlib import Path

from geoalchemy2.elements import WKTElement
from loguru import logger
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.isr_point import IsrPoint
from app.models.user import User, UserRole
from app.services.auth import hash_password
from scripts.seed_month3_data import _default_datasets_dir, run as seed_geodata


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


async def main() -> int:
    async with AsyncSessionLocal() as db:
        await seed_users(db)
        await seed_isr_points(db)

    report_path = Path(__file__).resolve().parents[1] / "reports" / "data_quality_report.json"
    rc = await seed_geodata(_default_datasets_dir(), report_path)
    logger.info("Seed finished.")
    return rc or 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
