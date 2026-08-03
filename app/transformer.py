import re
from datetime import datetime, time
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .models import BusArrival, Service, StopArrivalResponse


CODE_MULTIPLE_BUSES = "00"
CODE_SINGLE_BUS = "01"
CODE_FREQUENCY = "9"
CODE_NO_BUSES = "10"
CODE_CLOSED_STOP = "11"
CODE_UNAVAILABLE = "12"
CODE_OFFLINE = "20"

VALID_SERVICE_CODES = {CODE_MULTIPLE_BUSES, CODE_SINGLE_BUS, CODE_FREQUENCY}

_PARADERO_OFFLINE = "Sistema fuera de linea temporalmente"
_PARADERO_OK = "Itinerario obtenido satisfactoriamente"
_PARADERO_NOT_FOUND = "Paradero no encontrado"
_OUT_OF_HOURS = "Fuera de horario de operación"

_24_7_SERVICES: FrozenSet[str] = frozenset(
    {
        "104", "107", "119",
        "201", "207", "210", "210v", "230",
        "301", "303",
        "401", "403", "405", "407", "418", "426",
        "506", "508", "513", "516", "518",
        "C02", "F20", "G08", "J08",
    }
)

_NIGHT_ONLY_SERVICES: FrozenSet[str] = frozenset(
    {
        "109N", "203N", "204N", "262N", "264N", "302N", "346N",
        "432N", "541N", "712N",
        "B02N", "B30N", "B31N",
        "F30N",
        "I08N", "I10N", "I11N", "I14N",
    }
)

_EXTENDED_DAY_SERVICES: FrozenSet[str] = frozenset({"103", "D09"})

_DAY_START = time(5, 30)
_DAY_END = time(23, 59)

_NIGHT_START = time(0, 0)
_NIGHT_END = time(5, 0)

_EXTENDED_START = time(5, 30)
_EXTENDED_END = time(1, 30)

_SANTIAGO_TZ = ZoneInfo("America/Santiago")

_TIME_RANGE_REGEX = re.compile(
    r"(\d+)\s*[Yy]\s*(\d+)\s*min", re.IGNORECASE
)
_LESS_THAN_REGEX = re.compile(
    r"(?:en\s*)?menos\s*de\s*(\d+)\s*min", re.IGNORECASE
)
_MORE_THAN_REGEX = re.compile(
    r"m[áa]s\s*de\s*(\d+)\s*min", re.IGNORECASE
)
_SINGLE_TIME_REGEX = re.compile(r"(\d+)\s*min", re.IGNORECASE)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _parse_arrival_window(
    text: Optional[str],
) -> Tuple[int, int]:
    if _is_blank(text):
        return 0, 0

    cleaned = text.strip()
    lowered = cleaned.lower()

    if "llegando" in lowered:
        return 0, 0

    less_than_match = _LESS_THAN_REGEX.search(cleaned)
    if less_than_match:
        return 0, int(less_than_match.group(1))

    more_than_match = _MORE_THAN_REGEX.search(cleaned)
    if more_than_match:
        return int(more_than_match.group(1)), -1

    range_match = _TIME_RANGE_REGEX.search(cleaned)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    single_match = _SINGLE_TIME_REGEX.search(cleaned)
    if single_match:
        minutes = int(single_match.group(1))
        return minutes, minutes

    return 0, 0


def _to_int(value: Any) -> int:
    if _is_blank(value):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        return int(digits) if digits else 0
    return 0


def _build_bus(
    *,
    bus_id: Any,
    distance: Any,
    prediction: Any,
) -> Optional[BusArrival]:
    if _is_blank(bus_id):
        return None
    min_time, max_time = _parse_arrival_window(prediction)
    return BusArrival(
        id=str(bus_id).strip(),
        meters_distance=_to_int(distance),
        min_arrival_time=min_time,
        max_arrival_time=max_time,
    )


def _build_buses_for_service(service_item: Dict[str, Any]) -> List[BusArrival]:
    code = service_item.get("codigorespuesta")
    buses: List[BusArrival] = []

    if code == CODE_MULTIPLE_BUSES:
        slots = ("1", "2")
    elif code == CODE_SINGLE_BUS:
        slots = ("1",)
    else:
        return buses

    for slot in slots:
        bus = _build_bus(
            bus_id=service_item.get(f"ppubus{slot}"),
            distance=service_item.get(f"distanciabus{slot}"),
            prediction=service_item.get(f"horaprediccionbus{slot}"),
        )
        if bus:
            buses.append(bus)

    return buses


def _build_service(service_item: Dict[str, Any]) -> Service:
    code = service_item.get("codigorespuesta") or CODE_UNAVAILABLE
    raw_description = service_item.get("respuestaServicio")
    if _is_blank(raw_description):
        description = "Servicio no disponible"
    else:
        description = str(raw_description).strip()

    service_id = (service_item.get("servicio") or "").strip()

    return Service(
        id=service_id,
        valid=code in VALID_SERVICE_CODES,
        status_description=description,
        buses=_build_buses_for_service(service_item),
        is_24_7=service_id in _24_7_SERVICES,
        is_night_only=service_id in _NIGHT_ONLY_SERVICES,
    )


def _paradero_status_code(paradero_response: Optional[str]) -> int:
    if _is_blank(paradero_response):
        return 0
    lowered = paradero_response.lower()
    if "fuera de linea" in lowered or "fuera de línea" in lowered:
        return 20
    if "no encontrad" in lowered or "no existe" in lowered:
        return 1
    return 0


def _paradero_status_description(
    paradero_response: Optional[str],
    status_code: int,
) -> str:
    if status_code == 20:
        return _PARADERO_OFFLINE
    if status_code == 1:
        return _PARADERO_NOT_FOUND
    return _PARADERO_OK


def _is_in_window(now: time, start: time, end: time) -> bool:
    """Return True if `now` is in the half-open interval [start, end].

    Handles windows that cross midnight (end < start), e.g. 05:30–01:30.
    """
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _get_operating_window(service_id: str) -> Tuple[bool, time, time]:
    """Return (is_24_7, start, end) for a service based on the malla nocturna table.

    24/7 services are flagged but the window is unused (never overridden).
    """
    if service_id in _24_7_SERVICES:
        return True, time(0, 0), time(23, 59)
    if service_id in _NIGHT_ONLY_SERVICES:
        return False, _NIGHT_START, _NIGHT_END
    if service_id in _EXTENDED_DAY_SERVICES:
        return False, _EXTENDED_START, _EXTENDED_END
    return False, _DAY_START, _DAY_END


def _apply_operating_window(service: Service, now: datetime) -> Service:
    """Override a service to out-of-hours state when appropriate.

    A service is only marked "Fuera de horario de operación" when BOTH:
      - the current time is outside its operating window, AND
      - the upstream red.cl response reported no buses for this service.

    This avoids a false positive when a service is technically inside its
    window but red.cl temporarily reports no buses (e.g. a deviation,
    detour, or upstream outage): in that case we keep the upstream's
    description so users can still see the reason.
    """
    is_24_7, start, end = _get_operating_window(service.id)
    if is_24_7:
        return service
    if service.buses:
        return service
    if _is_in_window(now.time(), start, end):
        return service
    return service.model_copy(
        update={
            "valid": False,
            "status_description": _OUT_OF_HOURS,
            "buses": [],
        }
    )


def transform(raw: Dict[str, Any]) -> StopArrivalResponse:
    servicios = raw.get("servicios") or {}
    items: List[Dict[str, Any]] = servicios.get("item") or []

    services = [_build_service(item) for item in items]
    now = datetime.now(_SANTIAGO_TZ)
    services = [_apply_operating_window(s, now) for s in services]

    status_code = _paradero_status_code(raw.get("respuestaParadero"))
    status_description = _paradero_status_description(
        raw.get("respuestaParadero"),
        status_code,
    )

    return StopArrivalResponse(
        id=raw.get("paradero") or "",
        name=raw.get("nomett") or "",
        status_code=status_code,
        status_description=status_description,
        services=services,
    )
