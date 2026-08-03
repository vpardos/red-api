import re
from datetime import datetime, time, timedelta
from typing import Any, Dict, FrozenSet, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .cache import out_of_hours_cache
from .malla_nocturna import malla_store
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

    schedule = malla_store.get()

    return Service(
        id=service_id,
        valid=code in VALID_SERVICE_CODES,
        status_description=description,
        buses=_build_buses_for_service(service_item),
        is_24_7=schedule.is_24_7(service_id),
        is_night_only=schedule.is_night_only(service_id),
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
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def _get_operating_window(service_id: str) -> Tuple[bool, time, time]:
    schedule = malla_store.get()
    if schedule.is_24_7(service_id):
        return True, time(0, 0), time(23, 59)
    if schedule.is_night_only(service_id):
        return False, _NIGHT_START, _NIGHT_END
    if schedule.is_extended(service_id):
        return False, _EXTENDED_START, _EXTENDED_END
    return False, _DAY_START, _DAY_END


def _seconds_until_next_window_start(service_id: str, now: datetime) -> int:
    is_24_7, start, _ = _get_operating_window(service_id)
    if is_24_7:
        return 0
    current_time = now.time()
    today = now.date()
    tz = now.tzinfo

    if start <= current_time:
        next_start = datetime.combine(today + timedelta(days=1), start, tzinfo=tz)
    elif start <= time(23, 59):
        next_start = datetime.combine(today, start, tzinfo=tz)
    else:
        next_start = datetime.combine(today + timedelta(days=1), start, tzinfo=tz)

    delta = (next_start - now).total_seconds()
    return max(int(delta), 1)


def _out_of_hours_override(service: Service) -> Service:
    return service.model_copy(
        update={
            "valid": False,
            "status_description": _OUT_OF_HOURS,
            "buses": [],
        }
    )


async def _apply_operating_window(service: Service, now: datetime) -> Service:
    is_24_7, start, end = _get_operating_window(service.id)
    if is_24_7:
        return service
    if service.buses:
        return service
    if _is_in_window(now.time(), start, end):
        return service

    cached = await out_of_hours_cache.get(service.id)
    if cached:
        return _out_of_hours_override(service)

    ttl = _seconds_until_next_window_start(service.id, now)
    await out_of_hours_cache.set(service.id, True, ttl_seconds=ttl)
    return _out_of_hours_override(service)


async def transform(raw: Dict[str, Any]) -> StopArrivalResponse:
    servicios = raw.get("servicios") or {}
    items: List[Dict[str, Any]] = servicios.get("item") or []

    services = [_build_service(item) for item in items]
    now = datetime.now(_SANTIAGO_TZ)
    services = [await _apply_operating_window(s, now) for s in services]

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
