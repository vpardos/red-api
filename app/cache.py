import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: Dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
    ) -> T:
        now = time.monotonic()
        entry = self._store.get(key)
        if entry and entry.expires_at > now:
            return entry.value

        async with self._lock:
            entry = self._store.get(key)
            if entry and entry.expires_at > now:
                return entry.value

            value = await factory()
            self._store[key] = CacheEntry(
                value=value,
                expires_at=now + self._ttl,
            )
            return value

    def invalidate(self, key: Optional[str] = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


token_cache: TTLCache[str] = TTLCache(ttl_seconds=55 * 60)
prediction_cache: TTLCache[Dict[str, Any]] = TTLCache(ttl_seconds=30)
metro_cache: TTLCache[Any] = TTLCache(ttl_seconds=60)
metrotren_cache: TTLCache[Any] = TTLCache(ttl_seconds=60)
