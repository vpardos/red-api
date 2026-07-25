from __future__ import annotations

import re
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from .models import (
    Connections,
    LineStatus,
    MetroLineConnection,
    MetrotrenLine,
    MetrotrenStation,
    StationStatus,
)


_HTML_PARSER = "html.parser"

_STATUS_CLASS_MAP: dict[str, StationStatus] = {
    "operativa": StationStatus.OPERATIVA,
    "cerrada-temporalmente": StationStatus.CERRADA_TEMPORALMENTE,
    "no-habilitada": StationStatus.NO_HABILITADA,
}

# A Metro line id parsed from a connection block.
_METRO_LINE_ID_REGEX = re.compile(r"^l[1-6]a?$")

# Pulls a color hex out of a CSS style attribute value.
_COLOR_REGEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

# Validates the path segment we extract from station hrefs.
_STATION_SLUG_REGEX = re.compile(r"^[a-z0-9-]{1,80}$")

# Metrotren has exactly one line.
_LINE_ID = "metrotren-nos"

# Official Metrotren Nos color (hardcoded).
_LINE_COLOR = "#a9218e"


def _parse_color_from_style(style_attr: Optional[str]) -> Optional[str]:
    if not style_attr:
        return None
    match = _COLOR_REGEX.search(style_attr)
    return match.group(0).lower() if match else None


def _line_status_from_stations(stations: List[MetrotrenStation]) -> LineStatus:
    if any(s.status != StationStatus.OPERATIVA for s in stations):
        return LineStatus.CON_PROBLEMAS
    return LineStatus.OPERATIVA


def _parse_connections(li: Tag) -> Connections:
    metro_lines: List[MetroLineConnection] = []
    other_services: List[str] = []

    for div in li.find_all("div", class_="recorrido"):
        label = div.find("strong")
        if not label:
            continue
        line_label = label.get_text(strip=True)
        line_id = line_label.strip().lower()
        if not _METRO_LINE_ID_REGEX.match(line_id):
            continue
        line_name = f"Línea {line_id[1:].upper()}"
        color = _parse_color_from_style(div.get("style"))
        metro_lines.append(
            MetroLineConnection(id=line_id, name=line_name, color=color)
        )

    for p in li.find_all("p"):
        if p.find("div", class_="recorrido"):
            continue
        text = p.get_text(strip=True)
        if text:
            other_services.append(text)

    return Connections(metro_lines=metro_lines, other_services=other_services)


def _parse_station(li: Tag) -> Optional[MetrotrenStation]:
    classes = li.get("class") or []
    # Filter helper classes to find the status marker.
    raw_class = next((c for c in classes if c in _STATUS_CLASS_MAP), None)
    if raw_class is None:
        # Preserve unknown status classes for forward-compat.
        raw_class = next((c for c in classes if c and c not in {"col", "sg-li"}), None)
        if raw_class is None:
            return None
        status = StationStatus.DESCONOCIDO
    else:
        status = _STATUS_CLASS_MAP[raw_class]

    has_connections = "con-conexiones" in classes

    anchor = li.find("a")
    if not anchor:
        return None
    href = (anchor.get("href") or "").strip()
    name = anchor.get_text(strip=True)
    if not href or not name:
        return None

    station_id = href.rstrip("/").split("/")[-1].lower()
    if not _STATION_SLUG_REGEX.match(station_id):
        return None

    connections = _parse_connections(li) if has_connections else None

    return MetrotrenStation(
        id=station_id,
        name=name,
        status=status,
        raw_status_class=raw_class if status == StationStatus.DESCONOCIDO else None,
        detail_url=href,
        has_connections=has_connections,
        connections=connections,
    )


def _find_line_ul(soup: BeautifulSoup) -> Optional[Tag]:
    ul = soup.find("ul", class_="linea-metrotren")
    return ul if isinstance(ul, Tag) else None


def _find_line_name(soup: BeautifulSoup) -> str:
    h2 = soup.find("h2")
    if isinstance(h2, Tag):
        name = h2.get_text(strip=True)
        if name:
            return name
    return "Metrotren Nos"


def parse_metrotren_html(html: str) -> MetrotrenLine:
    soup = BeautifulSoup(html, _HTML_PARSER)
    line_name = _find_line_name(soup)

    ul = _find_line_ul(soup)
    stations: List[MetrotrenStation] = []
    if isinstance(ul, Tag):
        for li in ul.find_all("li", recursive=False):
            station = _parse_station(li)
            if station is not None:
                stations.append(station)

    return MetrotrenLine(
        id=_LINE_ID,
        name=line_name,
        color=_LINE_COLOR,
        stations=stations,
        status=_line_status_from_stations(stations),
    )
