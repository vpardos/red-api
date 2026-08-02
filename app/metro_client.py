from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .cache import metro_cache
from .config import settings
from .metro_cl_parser import MetroClLineStatus, MetroClStation, parse_metro_cl_html
from .metro_parser import parse_metro_html
from .models import (
    LineStatus,
    MetroLine,
    MetroSnapshot,
    MetroStation,
    StationStatus,
)


class MetroError(Exception):
    pass


async def _fetch_html(url: str) -> str:
    """Fetch a URL and return the response HTML."""
    headers = {"User-Agent": settings.user_agent}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


async def _try_red_cl() -> Optional[List[MetroLine]]:
    """Fetch and parse red.cl metro page. Returns None on failure."""
    try:
        html = await _fetch_html(settings.metro_status_url)
        return parse_metro_html(html)
    except Exception:
        return None


async def _try_metro_cl() -> Optional[List[MetroClLineStatus]]:
    """Fetch and parse metro.cl status page. Returns None on failure."""
    try:
        html = await _fetch_html(settings.metro_cl_status_url)
        return parse_metro_cl_html(html)
    except Exception:
        return None


def _merge(
    red_cl_lines: Optional[List[MetroLine]],
    metro_cl_data: Optional[List[MetroClLineStatus]],
) -> tuple[str, List[MetroLine]]:
    """Merge data from both sources.

    metro.cl is the authoritative source. Whenever metro.cl has data for a
    line, its view wins on every discrepancy:

    - Line status: metro.cl overrides red.cl.
    - Per-station status: if metro.cl reports the line as operativa, every
      station on that line is operativa in the merged output (any red.cl
      per-station non-operativa status is overridden). If metro.cl reports
      the line as con_problemas, only the stations metro.cl lists in
      `affected_stations` are non-operativa, and the rest of the line is
      operativa.

    red.cl contributes the full station roster (slug, name, href, color)
    and is the only source of station enumeration; metro.cl is only used to
    declare which of those stations are affected.

    If metro.cl is unavailable, we fall back to red.cl as-is.

    Returns (source_label, merged_lines).
    """
    cl_map: dict[str, MetroClLineStatus] = {}
    if metro_cl_data:
        for item in metro_cl_data:
            cl_map[item.line_id] = item

    if red_cl_lines and not cl_map:
        return "red.cl", red_cl_lines

    if cl_map and not red_cl_lines:
        lines: List[MetroLine] = []
        for item in cl_map.values():
            stations: List[MetroStation] = []
            for s in item.affected_stations:
                stations.append(MetroStation(
                    id=_slugify(s.name),
                    name=s.name,
                    status=s.status,
                    detail_url="",
                ))
            lines.append(MetroLine(
                id=item.line_id,
                name=item.description or f"Línea {item.line_id[1:]}",
                line_number=item.line_id[1:],
                status=item.status,
                stations=stations,
            ))
        return "metro.cl", lines

    assert red_cl_lines is not None
    merged: List[MetroLine] = []
    for line in red_cl_lines:
        cl_line = cl_map.get(line.id)
        if cl_line is None:
            # metro.cl has no opinion on this line - trust red.cl.
            merged.append(line)
            continue

        new_line_status = cl_line.status

        affected_names = {s.name.lower() for s in cl_line.affected_stations}
        new_stations: List[MetroStation] = []
        for station in line.stations:
            cl_station = _find_cl_station(station, cl_line.affected_stations)
            if cl_station is not None:
                new_status = cl_station.status
            elif new_line_status == LineStatus.OPERATIVA:
                new_status = StationStatus.OPERATIVA
            else:
                # metro.cl says the line has problems but didn't list this
                # station among the affected ones
                new_status = StationStatus.OPERATIVA
            new_stations.append(MetroStation(
                id=station.id,
                name=station.name,
                status=new_status,
                raw_status_class=station.raw_status_class if new_status == StationStatus.DESCONOCIDO else None,
                detail_url=station.detail_url,
            ))

        merged.append(MetroLine(
            id=line.id,
            name=line.name,
            line_number=line.line_number,
            color=line.color,
            status=new_line_status,
            stations=new_stations,
        ))

    return "metro.cl + red.cl", merged


def _slugify(name: str) -> str:
    """Turn a station name into a rough slug for the id field."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    slug = ascii_name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    return slug[:80]


def _station_matches_affected(station: MetroStation, affected_names: set[str]) -> bool:
    """Check if a red.cl station matches any metro.cl affected station name."""
    station_lower = station.name.lower().strip()
    for name in affected_names:
        if station_lower == name:
            return True
        if name.startswith(station_lower):
            return True
        if station_lower.startswith(name):
            return True
    return False


def _find_cl_station(
    station: MetroStation, affected: list
) -> Optional[MetroClStation]:
    """Find the metro.cl station entry that matches a red.cl station."""
    station_lower = station.name.lower().strip()
    for cl_s in affected:
        cl_lower = cl_s.name.lower().strip()
        if station_lower == cl_lower or cl_lower.startswith(station_lower):
            return cl_s
    return None


async def get_metro_snapshot() -> MetroSnapshot:

    async def factory() -> MetroSnapshot:
        # Fetch both sources in parallel
        red_cl_task = asyncio.create_task(_try_red_cl())
        metro_cl_task = asyncio.create_task(_try_metro_cl())

        red_cl_lines, metro_cl_data = await asyncio.gather(
            red_cl_task, metro_cl_task
        )

        if red_cl_lines is None and metro_cl_data is None:
            raise MetroError(
                "Failed to fetch metro status from both red.cl and metro.cl"
            )

        source, lines = _merge(red_cl_lines, metro_cl_data)

        return MetroSnapshot(
            source=source,
            fetched_at=datetime.now(timezone.utc),
            lines=lines,
        )

    return await metro_cache.get_or_set("metro_snapshot", factory)


def invalidate_metro_cache() -> None:
    """Clear the metro cache (mainly useful for tests / manual refresh)."""
    metro_cache.invalidate()
