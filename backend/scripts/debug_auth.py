
import asyncio
import sys
import uuid
import traceback
from app.database import AsyncSessionLocal
from app.repositories.user import UserRepository
from app.services.auth import create_access_token, decode_access_token
from app.models.user import UserRole, User

async def debug_auth():
    print("Starting debug_auth...", flush=True)
    async with AsyncSessionLocal() as db:
        repo = UserRepository(db)
        # 1. Fetch admin user to test with
        admin_user = await repo.get_by_email("admin@jaldrishti.local") # From seed
        if not admin_user:
            # Fallback to older seed email if different?
            admin_user = await repo.get_by_email("admin@example.com")
        
        if not admin_user:
            print("[ERROR] No admin user found.", flush=True)
            return

        print(f"Found admin user: {admin_user.id} ({admin_user.role})", flush=True)

        # 2. Simulate Token Creation
        print("Creating token...", flush=True)
        token = create_access_token(str(admin_user.id), admin_user.role)
        print(f"Token created: {token[:20]}...", flush=True)

        # 3. Simulate get_current_user logic
        print("Simulating get_current_user...", flush=True)
        try:
            payload = decode_access_token(token)
            print(f"Token payload: {payload}", flush=True)
            user_id_str = payload.get("sub")
            print(f"User ID from payload: {user_id_str} (type: {type(user_id_str)})", flush=True)

            user_id = uuid.UUID(user_id_str)
            print(f"UUID obj: {user_id}", flush=True)

            user = await repo.get(user_id)
            if not user:
                 print("[ERROR] User not found by ID from token.", flush=True)
            else:
                 print(f"User fetched: {user.email}", flush=True)
                 print(f"User Role: {user.role} (type: {type(user.role)})", flush=True)

        except Exception as e:
            print(f"[CRITICAL] get_current_user logic failed: {e}", flush=True)
            traceback.print_exc()

        # 4. Simulate require_admin logic
        try:
            print("Simulating require_admin...", flush=True)
            # require_roles(UserRole.admin)
            required_roles = (UserRole.admin,)
            if user.role not in required_roles:
                print(f"[ERROR] Role mismatch! {user.role} not in {required_roles}", flush=True)
            else:
                print("[OK] Role check passed.", flush=True)
        except Exception as e:
            print(f"[CRITICAL] require_admin logic failed: {e}", flush=True)
            traceback.print_exc()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(debug_auth())
