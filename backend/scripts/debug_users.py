
import asyncio
import sys
import traceback
from app.database import AsyncSessionLocal
from app.services.user import UserService
from app.schemas.user import UserResponse
from sqlalchemy import select
from app.models.user import User

async def debug_users():
    print("Starting debug_users script...", flush=True)
    async with AsyncSessionLocal() as db:
        print("Database session created.", flush=True)
        try:
            # 1. Direct query test
            print("Executing direct SQL query...", flush=True)
            result = await db.execute(select(User).limit(5))
            users = result.scalars().all()
            print(f"Direct query found {len(users)} users.", flush=True)
            for u in users:
                print(f"  User ID: {u.id}, Role: {u.role} (type: {type(u.role)})", flush=True)
        except Exception:
            print("[ERROR] Direct query failed.", flush=True)
            traceback.print_exc()

        svc = UserService(db)
        try:
            # 2. Service test
            print("\nTesting UserService.list_users()...", flush=True)
            users = await svc.list_users()
            print(f"Service found {len(users)} users.", flush=True)
            
            # 3. Pydantic validation test
            for user in users:
                try:
                    print(f"Validating user {user.email}...", flush=True)
                    # Use model_validate instead of from_orm (v2)
                    pydantic_user = UserResponse.model_validate(user, from_attributes=True)
                    print(f"  [OK] Validated: {pydantic_user.email}", flush=True)
                except Exception as e:
                    print(f"  [ERROR] Pydantic validation failed for {user.email}:", flush=True)
                    traceback.print_exc()
        except Exception:
            print("[CRITICAL ERROR] Service test failed.", flush=True)
            traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(debug_users())
