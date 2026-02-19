
import asyncio
import sys
import traceback
from app.database import AsyncSessionLocal
from app.services.user import UserService
from app.schemas.user import UserResponse

async def debug_detached_serialization():
    print("Starting debug_detached_serialization...", flush=True)
    users = []
    
    # 1. Fetch users inside session
    try:
        async with AsyncSessionLocal() as db:
            print("Fetching users...", flush=True)
            svc = UserService(db)
            users = await svc.list_users()
            print(f"Fetched {len(users)} users inside session.", flush=True)
            # Session closes here
    except Exception as e:
        print(f"[CRITICAL] Database fetch failed: {e}", flush=True)
        traceback.print_exc()
        return

    # 2. Serialize users OUTSIDE session
    print("Session closed. Attempting serialization...", flush=True)
    try:
        for i, user in enumerate(users):
            print(f"Serializing user {i+1}...", flush=True)
            pydantic_user = UserResponse.model_validate(user, from_attributes=True)
            print(f"  [OK] Validated: {pydantic_user.email}", flush=True)
    except Exception as e:
        print(f"[ERROR] Serialization failed outside session: {e}", flush=True)
        traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(debug_detached_serialization())
