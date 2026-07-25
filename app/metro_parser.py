from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from .models import LineStatus, MetroLine, MetroStation, StationStatus


_HTML_PARSER = "html.parser"

_STATUS_CLASS_MAP: dict[str, StationStatus] = {
    "operativa": StationStatus.OPERATIVA,
    "cerrada-temporalmente": StationStatus.CERRADA_TEMPORALMENTE,
    "no-habilitada": StationStatus.NO_HABILITADA,
}
#regex
# Matches the line id used as CSS class on the h2.
_LINE_ID_REGEX = re.compile(r"^l([1-6]a?)$")

# Pulls a color hex out of a CSS style attribute value.
_COLOR_REGEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# Validates the path segment we extract from station hrefs.
_STATION_SLUG_REGEX = re.compile(r"^[a-z0-9-]{1,80}$")


def _parse_color(style_attr: Optional[str], *, prop: str) -> Optional[str]:
    if not style_attr:
        return None
    if prop:
        match = re.search(rf"{re.escape(prop)}\s*:\s*(#[0-9a-fA-F]{{3,8}})", style_attr)
        if match:
            return match.group(1).lower()
        return None
    match = _COLOR_REGEX.search(style_attr)
    return match.group(0).lower() if match else None


def _line_status_from_stations(stations: List[MetroStation]) -> LineStatus:
    if any(s.status != StationStatus.OPERATIVA for s in stations):
        return LineStatus.CON_PROBLEMAS
    return LineStatus.OPERATIVA


def _parse_station(li: Tag) -> Optional[MetroStation]:
    classes = li.get("class") or []
    # Filter out any helper classes that aren't status markers.
    raw_class = next((c for c in classes if c in _STATUS_CLASS_MAP), None)
    if raw_class is None:
        # Unknown status class, preserve it so the API can surface a degradation
        # instead of silently dropping the station.
        raw_class = next((c for c in classes if c and c != "sg-li"), None)
        if raw_class is None:
            return None
        status = StationStatus.DESCONOCIDO
    else:
        status = _STATUS_CLASS_MAP[raw_class]

    anchor = li.find("a")
    if not anchor:
        return None

    href = (anchor.get("href") or "").strip()
    name = anchor.get_text(strip=True)
    if not href or not name:
        return None

    # Station id is the last non-empty path segment of the href.
    station_id = href.rstrip("/").split("/")[-1].lower()
    if not _STATION_SLUG_REGEX.match(station_id):
        return None

    return MetroStation(
        id=station_id,
        name=name,
        status=status,
        raw_status_class=raw_class if status == StationStatus.DESCONOCIDO else None,
        detail_url=href,
    )


def _parse_line(h2: Tag, ul: Tag) -> Optional[MetroLine]:
    classes = h2.get("class") or []
    line_id = next((c for c in classes if _LINE_ID_REGEX.match(c)), None)
    if not line_id:
        return None

    line_number = _LINE_ID_REGEX.match(line_id).group(1)  # type: ignore[union-attr]
    name = h2.get_text(strip=True) or f"Línea {line_number}"
    color = _parse_color(h2.get("style"), prop="background-color")
    if not color:
        color = _parse_color(ul.get("style"), prop="border-left-color")

    stations: List[MetroStation] = []
    for li in ul.find_all("li", recursive=False):
        station = _parse_station(li)
        if station is not None:
            stations.append(station)

    return MetroLine(
        id=line_id,
        name=name,
        line_number=line_number,
        color=color,
        stations=stations,
        status=_line_status_from_stations(stations),
    )


def _find_line_ul(h2: Tag) -> Optional[Tag]:
    container = h2.find_next_sibling("div")
    if not isinstance(container, Tag):
        return None
    ul = container.find("ul", class_="linea-metro", recursive=False)
    return ul if isinstance(ul, Tag) else None


def parse_metro_html(html: str) -> List[MetroLine]:
    soup = BeautifulSoup(html, _HTML_PARSER)
    lines: List[MetroLine] = []
    seen_ids: set[str] = set()

    for h2 in soup.find_all("h2"):
        if not isinstance(h2, Tag):
            continue
        classes = h2.get("class") or []
        if not any(_LINE_ID_REGEX.match(c) for c in classes):
            continue
        ul = _find_line_ul(h2)
        if not isinstance(ul, Tag):
            continue
        line = _parse_line(h2, ul)
        if line is None or line.id in seen_ids:
            continue
        seen_ids.add(line.id)
        lines.append(line)

    return lines
