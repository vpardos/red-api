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

    async def get(self, key: str) -> Optional[T]:
        entry = self._store.get(key)
        if entry and entry.expires_at > time.monotonic():
            return entry.value
        return None

    async def set(self, key: str, value: T) -> None:
        async with self._lock:
            self._store[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + self._ttl,
            )

    def invalidate(self, key: Optional[str] = None) -> None:
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


@dataclass
class NegativeStopResult:
    """Cached outcome of a failed /stops/{stop_id} lookup.

    Used to short-circuit repeated probes (bad or unknown stop IDs) to the
    upstream red.cl service, mitigating abuse without breaking the response
    contract.
    """

    kind: str  # "http_error" or "not_found"
    http_status: int = 502
    http_detail: str = "Upstream service unavailable"
    # Serialized ErrorResponse payload for the "not_found" case.
    body: Optional[Dict[str, Any]] = None


token_cache: TTLCache[str] = TTLCache(ttl_seconds=55 * 60)
prediction_cache: TTLCache[Dict[str, Any]] = TTLCache(ttl_seconds=30)
metro_cache: TTLCache[Any] = TTLCache(ttl_seconds=60)
metrotren_cache: TTLCache[Any] = TTLCache(ttl_seconds=60)
negative_stops_cache: TTLCache[NegativeStopResult] = TTLCache(ttl_seconds=60)
