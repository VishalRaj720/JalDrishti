"""Lightweight in-process cache.

Redis was removed in the Month-1 slim-down (fewer moving parts). This keeps the
same async interface the API already uses, backed by a simple in-memory dict
with TTL. Good enough for a single-process prototype; swap for Redis later if
horizontal scaling is ever needed.
"""
import fnmatch
import time
from typing import Any, Dict, Optional, Tuple

# key -> (expires_at_epoch, value)
_store: Dict[str, Tuple[float, Any]] = {}


async def cache_get(key: str) -> Optional[Any]:
    item = _store.get(key)
    if item is None:
        return None
    expires_at, value = item
    if expires_at and expires_at < time.time():
        _store.pop(key, None)
        return None
    return value


async def cache_set(key: str, value: Any, ttl: int = 3600) -> None:
    _store[key] = (time.time() + ttl if ttl else 0, value)


async def cache_delete(key: str) -> None:
    _store.pop(key, None)


async def cache_invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern (e.g., 'district:*')."""
    for key in [k for k in _store if fnmatch.fnmatch(k, pattern)]:
        _store.pop(key, None)
