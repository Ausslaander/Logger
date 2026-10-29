from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MeasurementStatus(Enum):
    OK = "ok"
    ERROR = "error"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class MeasurementDefinition:
    """Описание измеряемой величины."""

    key: str
    name: str
    unit: str
    precision: int = 3


@dataclass
class MeasurementValue:
    """Значение величины с временной меткой."""

    value: float | int | str | None
    timestamp: datetime
    status: MeasurementStatus = MeasurementStatus.OK


@dataclass
class MeasurementSnapshot:
    """Набор показаний, полученных за один цикл опроса."""

    values: dict[str, MeasurementValue] = field(default_factory=dict)


@dataclass
class DeviceInfo:
    """Информация о подключённом приборе."""

    name: str
    model: str
    port: str
    serial_number: str | None = None
    firmware_version: str | None = None
    extra: dict = field(default_factory=dict)
