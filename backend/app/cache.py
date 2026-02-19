"""Redis cache client wrapper."""
import json
from typing import Any, Optional
import redis.asyncio as aioredis
from loguru import logger
from app.config import settings

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def cache_get(key: str) -> Optional[Any]:
    try:
        r = await get_redis()
        data = await r.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"Cache GET error for key '{key}': {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.warning(f"Cache SET error for key '{key}': {e}")


async def cache_delete(key: str) -> None:
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception as e:
        logger.warning(f"Cache DELETE error for key '{key}': {e}")


async def cache_invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern (e.g., 'district:*')."""
    try:
        r = await get_redis()
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
    except Exception as e:
        logger.warning(f"Cache invalidate pattern error '{pattern}': {e}")
