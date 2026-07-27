from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from bs4 import BeautifulSoup, Tag

from .models import LineStatus, StationStatus

_HTML_PARSER = "html.parser"

_LINE_ICON_RE = re.compile(r"ico-l([\d]+a?)\.svg$")

_STATUS_OK = "ico-estado-ok.svg"
_STATUS_CERRADO = "ico-estado-cerrado.svg"

_CONTINGENCY_STATUS_MAP: dict[str, StationStatus] = {
    "cierre temporal": StationStatus.CERRADA_TEMPORALMENTE,
    "cierre parcial": StationStatus.CERRADA_TEMPORALMENTE,
    "estación cerrada": StationStatus.CERRADA_TEMPORALMENTE,
}


@dataclass
class MetroClStation:
    name: str
    status: StationStatus
    status_detail: str


@dataclass
class MetroClLineStatus:
    """Line-level status overlay from metro.cl."""

    line_id: str
    status: LineStatus
    description: str
    contingency_message: str = ""
    affected_stations: List[MetroClStation] = field(default_factory=list)


def _extract_line_id(img_src: str) -> Optional[str]:
    """Extract line id from icon src like '/images/ico-l1.svg'."""
    m = _LINE_ICON_RE.search(img_src)
    if m:
        return f"l{m.group(1)}"
    return None


def _parse_status_icon(img_src: str) -> LineStatus:
    """Determine line status from the status icon filename."""
    if _STATUS_CERRADO in img_src:
        return LineStatus.CON_PROBLEMAS
    return LineStatus.OPERATIVA


def _parse_contingency_stations(ul: Tag) -> List[MetroClStation]:
    """Parse affected stations from a contingency <ul>."""
    stations: List[MetroClStation] = []
    for li in ul.find_all("li", recursive=False):
        if not isinstance(li, Tag):
            continue
        strong = li.find("strong")
        if not strong:
            continue
        name = strong.get_text(strip=True)
        full_text = li.get_text(strip=True)
        detail = full_text.split(":", 1)[-1].strip() if ":" in full_text else full_text
        detail_lower = detail.lower()
        status = _CONTINGENCY_STATUS_MAP.get(detail_lower, StationStatus.CERRADA_TEMPORALMENTE)
        stations.append(MetroClStation(name=name, status=status, status_detail=detail))
    return stations


def parse_metro_cl_html(html: str) -> List[MetroClLineStatus]:
    """Parse metro.cl estado-red page and return line status overlays."""
    soup = BeautifulSoup(html, _HTML_PARSER)
    results: List[MetroClLineStatus] = []
    seen_ids: set[str] = set()

    for row in soup.find_all("div", class_="padding-bottom-30"):
        if not isinstance(row, Tag):
            continue

        line_icon = row.find("img", src=re.compile(r"ico-l\d"))
        if not line_icon or not isinstance(line_icon, Tag):
            continue

        src = (line_icon.get("src") or "").strip()
        line_id = _extract_line_id(src)
        if not line_id or line_id in seen_ids:
            continue

        status_icon = row.find("img", src=re.compile(r"ico-estado"))
        if not status_icon or not isinstance(status_icon, Tag):
            continue

        status_src = (status_icon.get("src") or "").strip()
        line_status = _parse_status_icon(status_src)

        desc_p = row.find("p", class_="h4")
        description = desc_p.get_text(strip=True) if desc_p else ""

        contingency_msg = ""
        affected_stations: List[MetroClStation] = []

        if line_status == LineStatus.CON_PROBLEMAS:
            detail_col = row.find("div", class_=re.compile(r"col-md-8"))
            if detail_col and isinstance(detail_col, Tag):
                first_p = detail_col.find("p")
                if first_p and first_p.get_text(strip=True):
                    contingency_msg = first_p.get_text(strip=True)

                ul = detail_col.find("ul")
                if ul and isinstance(ul, Tag):
                    affected_stations = _parse_contingency_stations(ul)

        results.append(MetroClLineStatus(
            line_id=line_id,
            status=line_status,
            description=description,
            contingency_message=contingency_msg,
            affected_stations=affected_stations,
        ))
        seen_ids.add(line_id)

    return results
