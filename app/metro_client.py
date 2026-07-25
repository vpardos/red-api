from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .cache import metro_cache
from .config import settings
from .metro_parser import parse_metro_html
from .models import MetroSnapshot


class MetroError(Exception):

async def get_metro_snapshot() -> MetroSnapshot:

    async def factory() -> MetroSnapshot:
        try:
            headers = {"User-Agent": settings.user_agent}
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds
            ) as client:
                response = await client.get(
                    settings.metro_status_url, headers=headers
                )
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError as exc:
            raise MetroError(f"Failed to fetch metro page: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise MetroError(f"Unexpected error fetching metro page: {exc}") from exc

        try:
            lines = parse_metro_html(html)
        except Exception as exc:
            raise MetroError(f"Failed to parse metro page: {exc}") from exc

        return MetroSnapshot(
            source=settings.metro_status_url,
            fetched_at=datetime.now(timezone.utc),
            lines=lines,
        )

    return await metro_cache.get_or_set("metro_snapshot", factory)


def invalidate_metro_cache() -> None:
    """Clear the metro cache (mainly useful for tests / manual refresh)."""
    metro_cache.invalidate()
