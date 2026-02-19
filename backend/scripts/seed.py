"""
Seed script: Creates default users in the groundwater_db.
Run once after running Alembic migrations.

Usage (from backend/):
    python -m scripts.seed
"""
import asyncio
import uuid
from app.database import AsyncSessionLocal
from app.models.user import User, UserRole
from app.services.auth import hash_password


SEED_USERS = [
    {
        "username": "admin",
        "email": "admin@jaldrishti.local",
        "password": "admin123",
        "role": UserRole.admin,
    },
    {
        "username": "analyst",
        "email": "analyst@jaldrishti.local",
        "password": "analyst123",
        "role": UserRole.analyst,
    },
    {
        "username": "viewer",
        "email": "viewer@jaldrishti.local",
        "password": "viewer123",
        "role": UserRole.viewer,
    },
]


async def seed():
    async with AsyncSessionLocal() as db:
        for u in SEED_USERS:
            from sqlalchemy import select
            result = await db.execute(select(User).where(User.email == u["email"]))
            if result.scalar_one_or_none():
                print(f"  [SKIP] {u['email']} already exists.")
                continue
            user = User(
                id=uuid.uuid4(),
                username=u["username"],
                email=u["email"],
                hashed_password=hash_password(u["password"]),
                role=u["role"],
            )
            db.add(user)
            print(f"  [OK]   Created {u['role'].value}: {u['email']}")
        await db.commit()
    print("\nSeed completed.")


if __name__ == "__main__":
    asyncio.run(seed())
