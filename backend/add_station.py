import asyncio
import uuid
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

async def add():
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT id FROM blocks LIMIT 1"))
        block_id = r.scalar()
        if block_id:
            station_id = str(uuid.uuid4())
            await conn.execute(text(f"""
                INSERT INTO monitoring_stations (id, block_id, name, latitude, longitude, created_at, updated_at) 
                VALUES ('{station_id}', '{block_id}', 'Diagnostic Station', 23.5, 86.5, NOW(), NOW())
            """))
            r1 = await conn.execute(text("SELECT count(*) FROM monitoring_stations"))
            print(f"Inserted station. New count: {r1.scalar()}")

asyncio.run(add())
