import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

async def check():
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        r1 = await conn.execute(text("SELECT count(*) FROM monitoring_stations"))
        r2 = await conn.execute(text("SELECT count(*) FROM districts"))
        r3 = await conn.execute(text("SELECT count(*) FROM blocks"))
        r4 = await conn.execute(text("SELECT count(*) FROM aquifers"))
        print(f"Stations: {r1.scalar()}, Districts: {r2.scalar()}, Blocks: {r3.scalar()}, Aquifers: {r4.scalar()}")

asyncio.run(check())
