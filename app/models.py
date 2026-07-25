from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class BusArrival(BaseModel):
    id: str
    meters_distance: int
    min_arrival_time: int
    max_arrival_time: int


class Service(BaseModel):
    id: str
    valid: bool
    status_description: str
    buses: List[BusArrival] = Field(default_factory=list)


class StopArrivalResponse(BaseModel):
    id: str
    name: str
    status_code: int
    status_description: str
    services: List[Service] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    id: str
    name: Optional[str] = None
    status_code: int
    status_description: str
    services: List[Service] = Field(default_factory=list)


class StationStatus(str, Enum):
    OPERATIVA = "operativa"
    CERRADA_TEMPORALMENTE = "cerrada_temporalmente"
    NO_HABILITADA = "no_habilitada"
    DESCONOCIDO = "desconocido"


class LineStatus(str, Enum):
    OPERATIVA = "operativa"
    CON_PROBLEMAS = "con_problemas"


class MetroStation(BaseModel):
    id: str
    name: str
    status: StationStatus
    raw_status_class: Optional[str] = None
    detail_url: str


class MetroLine(BaseModel):
    id: str
    name: str
    line_number: str
    color: Optional[str] = None
    status: LineStatus
    stations: List[MetroStation] = Field(default_factory=list)


class MetroSnapshot(BaseModel):
    source: str
    fetched_at: datetime
    lines: List[MetroLine] = Field(default_factory=list)


class MetroLineConnection(BaseModel):
    """A Metro line that a Metrotren station connects to (e.g. L1 from Alameda)."""

    id: str  # e.g. "l1", "l4a"
    name: str  # e.g. "Línea 1"
    color: Optional[str] = None  # e.g. "#ec1d25"


class Connections(BaseModel):
    """Intermodal connection info for a Metrotren station."""

    metro_lines: List[MetroLineConnection] = Field(default_factory=list)
    other_services: List[str] = Field(default_factory=list)


class MetrotrenStation(BaseModel):
    id: str
    name: str
    status: StationStatus
    raw_status_class: Optional[str] = None
    detail_url: str
    has_connections: bool = False
    connections: Optional[Connections] = None


class MetrotrenLine(BaseModel):
    id: str
    name: str
    color: Optional[str] = None
    status: LineStatus
    stations: List[MetrotrenStation] = Field(default_factory=list)


class MetrotrenSnapshot(BaseModel):
    source: str
    fetched_at: datetime
    line: MetrotrenLine
