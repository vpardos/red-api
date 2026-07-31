import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .cache import NegativeStopResult, negative_stops_cache
from .client import RedClError, get_prediction
from .config import settings
from .metro_client import MetroError, get_metro_snapshot
from .metrotren_client import MetrotrenError, get_metrotren_snapshot
from .models import (
    ErrorResponse,
    MetroLine,
    MetroSnapshot,
    MetroStation,
    MetrotrenSnapshot,
    MetrotrenStation,
    StopArrivalResponse,
)
from .transformer import transform

_docs_enabled = settings.docs_enabled
app = FastAPI(
    title="red-api",
    description="API HTTP no oficial y de código abierto para el sistema de transporte público Red Movilidad de Santiago. Extrae información de red.cl de los paraderos de RED, el Metro de Santiago y el servicio Tren Nos - Estación Central en un formato JSON limpio.",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

STOP_ID_REGEX = re.compile(r"^[A-Z0-9]{1,10}$")
LINE_ID_REGEX = re.compile(r"^l[1-6]a?$")
STATION_SLUG_REGEX = re.compile(r"^[a-z0-9-]{1,80}$")


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok"}


_FAVICON_ICO = (
    b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x20\x00\x68\x04"
    b"\x00\x00\x16\x00\x00\x00\x28\x00\x00\x00\x10\x00\x00\x00\x20\x00"
    b"\x00\x00\x01\x00\x20\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
)


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon() -> Response:
    return Response(content=_FAVICON_ICO, media_type="image/x-icon")


@app.get(
    "/stops/{stop_id}",
    response_model=StopArrivalResponse,
    tags=["stops"],
    summary="Obtener tiempos de llegada para un paradero",
)
async def get_stop_arrivals(stop_id: str) -> StopArrivalResponse:
    stop_id = stop_id.strip().upper()
    if not STOP_ID_REGEX.match(stop_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid stop id. Must be 1-10 alphanumeric characters.",
        )

    # Negative cache: short-circuit repeat probes to invalid or unknown
    # stop IDs so we don't keep hitting red.cl with the same bad request.
    cached_negative = await negative_stops_cache.get(stop_id)
    if cached_negative is not None:
        if cached_negative.kind == "http_error":
            raise HTTPException(
                status_code=cached_negative.http_status,
                detail=cached_negative.http_detail,
            )
        if cached_negative.kind == "not_found" and cached_negative.body is not None:
            return ErrorResponse(**cached_negative.body)

    try:
        raw = await get_prediction(stop_id)
    except RedClError as exc:
        detail = f"Upstream error: {exc}"
        await negative_stops_cache.set(
            stop_id,
            NegativeStopResult(
                kind="http_error", http_status=502, http_detail=detail
            ),
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        await negative_stops_cache.set(
            stop_id,
            NegativeStopResult(
                kind="http_error",
                http_status=502,
                http_detail="Upstream service unavailable",
            ),
        )
        raise HTTPException(
            status_code=502, detail="Upstream service unavailable"
        ) from exc

    response = transform(raw)
    if not response.services and not response.name:
        error_body = ErrorResponse(
            id=stop_id,
            name=None,
            status_code=1,
            status_description="Paradero no encontrado",
            services=[],
        )
        await negative_stops_cache.set(
            stop_id,
            NegativeStopResult(kind="not_found", body=error_body.model_dump()),
        )
        return error_body

    return response


async def _get_snapshot_or_502() -> MetroSnapshot:
    try:
        return await get_metro_snapshot()
    except MetroError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=502, detail="Upstream service unavailable"
        ) from exc


@app.get(
    "/metro/status",
    response_model=MetroSnapshot,
    tags=["metro"],
    summary="Estado de todas las líneas y estaciones de Metro",
)
async def get_metro_status() -> MetroSnapshot:
    return await _get_snapshot_or_502()


@app.get(
    "/metro/lines/{line_id}",
    response_model=MetroLine,
    tags=["metro"],
    summary="Estado de una línea de Metro",
)
async def get_metro_line(line_id: str) -> MetroLine:
    line_id = line_id.strip().lower()
    if not LINE_ID_REGEX.match(line_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid line id. Expected one of: l1, l2, l3, l4, l4a, l5, l6.",
        )

    snapshot = await _get_snapshot_or_502()
    for line in snapshot.lines:
        if line.id == line_id:
            return line
    raise HTTPException(status_code=404, detail=f"Line '{line_id}' not found")


@app.get(
    "/metro/stations/{station_slug:path}",
    response_model=MetroStation,
    tags=["metro"],
    summary="Estado de una estación de Metro",
)
async def get_metro_station(station_slug: str) -> MetroStation:
    slug = station_slug.strip().lower().rstrip("/")
    if not STATION_SLUG_REGEX.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Invalid station slug. Must be 1-80 chars of [a-z0-9-].",
        )

    snapshot = await _get_snapshot_or_502()
    for line in snapshot.lines:
        for station in line.stations:
            if station.id == slug:
                return station
    raise HTTPException(status_code=404, detail=f"Station '{slug}' not found")


async def _get_metrotren_snapshot_or_502() -> MetrotrenSnapshot:
    try:
        return await get_metrotren_snapshot()
    except MetrotrenError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=502, detail="Upstream service unavailable"
        ) from exc


@app.get(
    "/metrotren/status",
    response_model=MetrotrenSnapshot,
    tags=["metrotren"],
    summary="Estado de la línea Metrotren Nos y sus estaciones",
)
async def get_metrotren_status() -> MetrotrenSnapshot:
    return await _get_metrotren_snapshot_or_502()


@app.get(
    "/metrotren/stations/{station_slug:path}",
    response_model=MetrotrenStation,
    tags=["metrotren"],
    summary="Estado de una estación del Metrotren Nos",
)
async def get_metrotren_station(station_slug: str) -> MetrotrenStation:
    slug = station_slug.strip().lower().rstrip("/")
    if not STATION_SLUG_REGEX.match(slug):
        raise HTTPException(
            status_code=400,
            detail="Invalid station slug.",
        )

    snapshot = await _get_metrotren_snapshot_or_502()
    for station in snapshot.line.stations:
        if station.id == slug:
            return station
    raise HTTPException(status_code=404, detail=f"Station '{slug}' not found")
