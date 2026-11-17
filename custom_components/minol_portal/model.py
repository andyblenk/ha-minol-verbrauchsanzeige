"""Pure discovery logic, independent of Home Assistant."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json

from .const import HISTORY_MONTHS
from .portal.models import DeviceReading, METER_VIEW_FAMILIES, MonthRange, PortalSnapshot


@dataclass(frozen=True)
class Meter:
    identifier: str
    service: str
    reading: DeviceReading
    result_unit: str | None
    source_view: str
    retrieved_at: str | None = None


def query_period(today: date | None = None) -> MonthRange:
    """Request the current calendar month and the preceding eleven months."""
    today = today or date.today()
    first_index = today.year * 12 + today.month - HISTORY_MONTHS
    year, month = divmod(first_index, 12)
    return MonthRange(f"{year:04d}{month + 1:02d}", today.strftime("%Y%m"))


def discover_meters(snapshot: PortalSnapshot) -> dict[str, Meter]:
    results = {result.view_key: result for result in snapshot.results}
    meters = {}
    for service, candidates in METER_VIEW_FAMILIES.items():
        result = next((results[key] for key in candidates if key in results), None)
        if result is None:
            continue
        for reading in result.devices:
            if not reading.device_number:
                continue
            parts = (snapshot.selected_tenant["userNumber"], service, reading.device_number)
            identifier = hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:32]
            # Ambiguous duplicate rows must not silently overwrite a device reading.
            if identifier in meters:
                raise ValueError("Das Portal liefert mehrdeutige Zeilen für dasselbe Gerät.")
            meters[identifier] = Meter(identifier, service, reading,
                                       {"KWH": "kWh", "M3": "m³"}.get((reading.unit or "").upper()), result.view_key)
    return meters


def latest_reporting_month(snapshot: PortalSnapshot) -> str | None:
    """Return the latest valid month advertised for the selected tenant."""
    months = []
    periods = snapshot.layer_info.get("periods", [])
    if not isinstance(periods, list):
        return None
    for period in periods:
        if not isinstance(period, dict) or period.get("type") != "CALMONTH":
            continue
        key = period.get("key")
        if not isinstance(key, str) or len(key) != 6 or not key.isdecimal():
            continue
        try:
            date(int(key[:4]), int(key[4:]), 1)
        except ValueError:
            continue
        months.append(key)
    if not months:
        return None
    latest = max(months)
    return f"{latest[:4]}-{latest[4:]}"


def master_data(snapshot: PortalSnapshot) -> dict:
    """Use the selected tenant's fields, as displayed in the portal user panel."""
    tenant = snapshot.selected_tenant
    account = snapshot.account
    street = " ".join(str(tenant[key]) for key in ("addrStreet", "addrHouseNum") if tenant.get(key))
    city = " ".join(str(tenant[key]) for key in ("addrPostalCode", "addrCity") if tenant.get(key))
    floor = " ".join(str(tenant[key]) for key in ("geschossText", "lageText") if tenant.get(key))
    return {
        **account,
        "displayName": tenant.get("name") or account.get("displayName"),
        "email": tenant.get("email") or account.get("email"),
        "property_number": tenant.get("lgnr"),
        "unit_number": tenant.get("nenrMinol"),
        "tenant_number": tenant.get("userNumber"),
        "floor_position": floor or None,
        "street": street or None,
        "city": city or None,
        "country": tenant.get("addrCountry"),
        "move_in": tenant.get("einzugMieter") or None,
        "move_out": tenant.get("auszugMieter") or None,
    }


def entry_title(tenant: dict) -> str:
    """Suggest an editable entry name identifying the selected dwelling."""
    unit = str(tenant.get("nenrMinol") or "").strip()
    street = " ".join(str(tenant[key]).strip() for key in ("addrStreet", "addrHouseNum") if tenant.get(key))
    city = str(tenant.get("addrCity") or "").strip()
    address = ", ".join(part for part in (street, city) if part)
    if unit and address:
        return f"Einheit {unit} - {address}"
    return f"Einheit {unit}" if unit else address or "Minol Verbrauchsanzeige"
