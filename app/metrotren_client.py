from __future__ import annotations

from datetime import datetime, timezone

import httpx

from .cache import metrotren_cache
from .config import settings
from .metrotren_parser import parse_metrotren_html
from .models import MetrotrenSnapshot


class MetrotrenError(Exception):
    pass


async def get_metrotren_snapshot() -> MetrotrenSnapshot:

    async def factory() -> MetrotrenSnapshot:
        try:
            headers = {"User-Agent": settings.user_agent}
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds
            ) as client:
                response = await client.get(
                    settings.metrotren_status_url, headers=headers
                )
                response.raise_for_status()
                html = response.text
        except httpx.HTTPError as exc:
            raise MetrotrenError(f"Failed to fetch metrotren page: {exc}") from exc
        except Exception as exc:
            raise MetrotrenError(
                f"Unexpected error fetching metrotren page: {exc}"
            ) from exc

        try:
            line = parse_metrotren_html(html)
        except Exception as exc:
            raise MetrotrenError(f"Failed to parse metrotren page: {exc}") from exc

        return MetrotrenSnapshot(
            source=settings.metrotren_status_url,
            fetched_at=datetime.now(timezone.utc),
            line=line,
        )

    return await metrotren_cache.get_or_set("metrotren_snapshot", factory)


def invalidate_metrotren_cache() -> None:
    metrotren_cache.invalidate()
