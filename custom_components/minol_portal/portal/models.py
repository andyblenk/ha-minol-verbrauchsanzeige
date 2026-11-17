"""Portal contracts. Device tables and room-level series remain separate."""

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from .errors import ProtocolError


METER_VIEW_FAMILIES = {
    "Heizung": ("100EHRAUM", "100KWHRAUM", "100EH", "100KWH"),
    "Warmwasser": ("200RAUM", "200"),
    "Kaltwasser": ("300RAUM", "300"),
}


@dataclass(frozen=True)
class Credentials:
    email: str = field(repr=False)
    password: str = field(repr=False)
    user_num: str = field(default="", repr=False)

    def __post_init__(self):
        if not isinstance(self.email, str) or not self.email.strip():
            raise ValueError("Für die Anmeldung ist eine E-Mail-Adresse oder Anmeldekennung erforderlich.")
        if not isinstance(self.password, str) or not self.password:
            raise ValueError("Für die Anmeldung ist ein Passwort erforderlich.")
        if not isinstance(self.user_num, str):
            raise ValueError("Die Nutzereinheiten-ID muss eine Zeichenfolge sein.")


def _month(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-?\d{2}", value):
        raise ValueError("Monate müssen YYYY-MM oder YYYYMM entsprechen.")
    value = value.replace("-", "")
    date(int(value[:4]), int(value[4:]), 1)
    return value


@dataclass(frozen=True)
class MonthRange:
    start: str
    end: str

    def __post_init__(self):
        object.__setattr__(self, "start", _month(self.start))
        object.__setattr__(self, "end", _month(self.end))
        if self.start > self.end:
            raise ValueError("Der Beginn darf nicht nach dem Ende liegen.")

    @classmethod
    def default(cls):
        today = date.today()
        month_index = today.year * 12 + today.month - 1 - 13
        year, month = divmod(month_index, 12)
        return cls(f"{year:04d}{month + 1:02d}", today.strftime("%Y%m"))

    def months(self) -> list[str]:
        first = int(self.start[:4]) * 12 + int(self.start[4:]) - 1
        last = int(self.end[:4]) * 12 + int(self.end[4:]) - 1
        return [f"{index // 12:04d}{index % 12 + 1:02d}" for index in range(first, last + 1)]

    def selection(self, user_number: str) -> dict[str, Any]:
        return {
            "userNum": user_number,
            "layer": "NE",
            "scale": "CALMONTH",
            "chartRefUnit": "ABS",
            "refObject": "NOREF",
            "consType": "HEIZUNG",
            "dashBoardKey": "PE",
            "timelineStart": self.start,
            "timelineEnd": self.end,
            "timelineStartTxt": f"{self.start[4:]}.{self.start[:4]}",
            "timelineEndTxt": f"{self.end[4:]}.{self.end[:4]}",
            "valuesInKWH": True,
        }


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ProtocolError("Ein numerisches Verbrauchsfeld hat ein unerwartetes Format.")
    try:
        result = float(value)
    except ValueError:
        raise ProtocolError("Ein numerisches Verbrauchsfeld hat ein unerwartetes Format.") from None
    if not math.isfinite(result):
        raise ProtocolError("Ein Verbrauchsfeld enthält keinen endlichen Wert.")
    return result


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _rows(data: dict, key: str) -> list[dict]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ProtocolError("Die Portalantwort enthält eine unerwartete Tabellenstruktur.")
    return value


@dataclass(frozen=True)
class DeviceReading:
    room: str | None
    room_key: str | None
    device_number: str | None
    reading: float | None
    initial_reading: float | None
    consumption: float | None
    rating: float | None
    location_factor: float | None
    conversion_factor: float | None
    evaluated_consumption: float | None
    unit: str | None
    quality: str | None

    @classmethod
    def parse(cls, row: dict):
        return cls(
            room=_text(row.get("raum")), room_key=_text(row.get("raumKey")),
            device_number=_text(row.get("gerNr")), reading=_number(row.get("ablesung")),
            initial_reading=_number(row.get("anfangsstand")), consumption=_number(row.get("consumption")),
            rating=_number(row.get("bewertung")), location_factor=_number(row.get("laFaktor")),
            conversion_factor=_number(row.get("reFaktor")), evaluated_consumption=_number(row.get("consumptionBew")),
            unit=_text(row.get("unit")), quality=_text(row.get("valueStatus")),
        )


@dataclass(frozen=True)
class SeriesPoint:
    period: str | None
    series: str | None
    value: float | None
    quality: str | None

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ConsumptionData:
    view_key: str
    devices: list[DeviceReading] = field(repr=False)
    series: list[SeriesPoint] = field(repr=False)
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def parse(cls, view_key: str, raw: dict):
        if not isinstance(raw, dict) or not any(key in raw for key in ("table", "chart", "dashboard")):
            raise ProtocolError("Die Verbrauchsantwort entspricht nicht dem bekannten Portalvertrag.")
        devices = [DeviceReading.parse(row) for row in _rows(raw, "table")]
        series = [SeriesPoint(_text(row.get("categoryInt")), _text(row.get("keyFigure")),
                              _number(row.get("value")), _text(row.get("valueStatus")))
                  for row in _rows(raw, "chart")]
        _rows(raw, "dashboard")
        return cls(view_key, devices, series, raw)


@dataclass(frozen=True)
class PortalSnapshot:
    account: dict = field(repr=False)
    tenants: list[dict] = field(repr=False)
    selected_tenant: dict = field(repr=False)
    layer_info: dict = field(repr=False)
    period: MonthRange
    results: list[ConsumptionData] = field(repr=False)
    warnings: list[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    monthly_results: dict[str, list[ConsumptionData]] = field(default_factory=dict, repr=False)

    def to_dict(self):
        return asdict(self)
