
import asyncio
import httpx
import sys

BASE_URL = "http://127.0.0.1:8000/api/v1"

async def test_users_api():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Login as admin
        print("Logging in...", flush=True)
        login_resp = await client.post(
            f"{BASE_URL}/auth/token",
            data={"username": "admin@jaldrishti.local", "password": "admin123"}, # Checks seed user
        )
        if login_resp.status_code != 200:
             # Try other creds if seed logic different
             login_resp = await client.post(
                f"{BASE_URL}/auth/token",
                data={"username": "admin@example.com", "password": "admin123"},
            )
        
        if login_resp.status_code != 200:
            print(f"[ERROR] Login failed: {login_resp.status_code} {login_resp.text}", flush=True)
            return

        token = login_resp.json()["access_token"]
        print(f"Logged in. Token: {token[:10]}...", flush=True)

        # 2. Get Users
        print("Getting users...", flush=True)
        resp = await client.get(
            f"{BASE_URL}/users",
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"Response Status: {resp.status_code}", flush=True)
        print(f"Response Body: {resp.text}", flush=True)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_users_api())
