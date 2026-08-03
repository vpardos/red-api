import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import FrozenSet, Optional
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from .config import settings

logger = logging.getLogger(__name__)

_SANTIAGO_TZ = ZoneInfo("America/Santiago")


@dataclass(frozen=True)
class MallaNocturnaData:

    services_24_7: FrozenSet[str]
    services_night_only: FrozenSet[str]
    services_extended: FrozenSet[str]
    fetched_at: datetime
    source: str  # "live" or "fallback"

    def is_24_7(self, service_id: str) -> bool:
        return service_id in self.services_24_7

    def is_night_only(self, service_id: str) -> bool:
        return service_id in self.services_night_only

    def is_extended(self, service_id: str) -> bool:
        return service_id in self.services_extended


class MallaNocturnaParseError(Exception):



def _parse_time(s: str) -> time:

    cleaned = s.strip().replace(".", ":")
    parts = cleaned.split(":")
    return time(int(parts[0]), int(parts[1]))


_TIME_00_00 = _parse_time("0:00")
_TIME_05_30 = _parse_time("5:30")
_TIME_01_30 = _parse_time("1:30")
_TIME_23_59 = _parse_time("23:59")


# --- HTML parser (pure) ---------------------------------------------------

def parse_malla_nocturna_html(html: str) -> MallaNocturnaData:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="table")
    if table is None:
        raise MallaNocturnaParseError("Table with class 'table' not found")

    tbody = table.find("tbody")
    if tbody is None:
        raise MallaNocturnaParseError("Table has no tbody")

    services_24_7: set[str] = set()
    services_night_only: set[str] = set()
    services_extended: set[str] = set()

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        service_id = cells[0].get_text(strip=True)
        if not service_id:
            continue

        try:
            start = _parse_time(cells[3].get_text(strip=True))
            end = _parse_time(cells[4].get_text(strip=True))
        except (ValueError, IndexError):
            continue

        if start == _TIME_00_00 and end == _TIME_23_59:
            services_24_7.add(service_id)
        elif service_id.endswith("N"):
            services_night_only.add(service_id)
        elif start == _TIME_05_30 and end == _TIME_01_30:
            services_extended.add(service_id)

    return MallaNocturnaData(
        services_24_7=frozenset(services_24_7),
        services_night_only=frozenset(services_night_only),
        services_extended=frozenset(services_extended),
        fetched_at=datetime.now(_SANTIAGO_TZ),
        source="live",
    )



class MallaNocturnaStore:

    def __init__(self) -> None:
        self._data: Optional[MallaNocturnaData] = None

    def get(self) -> MallaNocturnaData:
        if self._data is None:
            raise RuntimeError("Malla nocturna data not initialized")
        return self._data

    def set(self, data: MallaNocturnaData) -> None:
        self._data = data

    def is_initialized(self) -> bool:
        return self._data is not None


malla_store = MallaNocturnaStore()


_FALLBACK_24_7: FrozenSet[str] = frozenset(
    {
        "104", "107", "119",
        "201", "207", "210", "210v", "230",
        "301", "303",
        "401", "403", "405", "407", "418", "426",
        "506", "508", "513", "516", "518",
        "C02", "F20", "G08", "J08",
    }
)

_FALLBACK_NIGHT_ONLY: FrozenSet[str] = frozenset(
    {
        "109N", "203N", "204N", "262N", "264N", "302N", "346N",
        "432N", "541N", "712N",
        "B02N", "B30N", "B31N",
        "F30N",
        "I08N", "I10N", "I11N", "I14N",
    }
)

_FALLBACK_EXTENDED: FrozenSet[str] = frozenset({"103", "D09"})


def _get_fallback_data() -> MallaNocturnaData:
    return MallaNocturnaData(
        services_24_7=_FALLBACK_24_7,
        services_night_only=_FALLBACK_NIGHT_ONLY,
        services_extended=_FALLBACK_EXTENDED,
        fetched_at=datetime.now(_SANTIAGO_TZ),
        source="fallback",
    )



class MallaNocturnaFetcher:

    def __init__(self) -> None:
        self._etag: Optional[str] = None
        self._last_modified: Optional[str] = None

    async def fetch(self) -> Optional[str]:
        headers = {"User-Agent": settings.user_agent}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified

        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(
                settings.malla_nocturna_url,
                headers=headers,
            )

            if response.status_code == 304:
                return None

            response.raise_for_status()

            self._etag = response.headers.get("ETag")
            self._last_modified = response.headers.get("Last-Modified")

            return response.text


_fetcher = MallaNocturnaFetcher()



async def refresh_malla_nocturna() -> MallaNocturnaData:
    try:
        html = await _fetcher.fetch()

        if html is None:
            # 304 Not Modified
            if malla_store.is_initialized():
                return malla_store.get()
            # Store empty + 304 shouldn't happen, but be defensive.
            data = _get_fallback_data()
            malla_store.set(data)
            return data

        data = parse_malla_nocturna_html(html)
        malla_store.set(data)
        logger.info(
            "Refreshed malla nocturna: %d 24/7, %d night-only, %d extended",
            len(data.services_24_7),
            len(data.services_night_only),
            len(data.services_extended),
        )
        return data

    except Exception as exc:
        logger.warning("Failed to refresh malla nocturna: %s", exc)
        if not malla_store.is_initialized():
            data = _get_fallback_data()
            malla_store.set(data)
            logger.warning("Using hardcoded fallback for malla nocturna")
        return malla_store.get()


async def periodic_refresh_loop() -> None:
    while True:
        try:
            await asyncio.sleep(settings.malla_nocturna_refresh_interval_seconds)
        except asyncio.CancelledError:
            raise
        try:
            await refresh_malla_nocturna()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Periodic malla nocturna refresh failed: %s", exc)
