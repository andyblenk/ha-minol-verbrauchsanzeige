"""Persistent monthly consumption, independent of recorder retention."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .model import Meter, discover_meters
from .portal.models import MonthRange


STORAGE_VERSION = 1
CONSUMPTION_FIELDS = ("consumption", "evaluated_consumption")


class MinolHistory:
    def __init__(self, hass, entry_id):
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self.data = None

    async def async_update(self, snapshot) -> dict[str, Meter]:
        if self.data is None:
            self.data = await self.store.async_load() or {"meters": {}}
        updated = deepcopy(self.data)
        current_meters = {}
        available_readings = {}
        for month in sorted(snapshot.monthly_results):
            month_snapshot = replace(
                snapshot, period=MonthRange(month, month), results=snapshot.monthly_results[month])
            fetched = discover_meters(month_snapshot)
            month_key = f"{month[:4]}-{month[4:]}"
            for identifier, record in updated["meters"].items():
                if identifier not in fetched and month_key in record["months"]:
                    record["months"][month_key] = dict.fromkeys(CONSUMPTION_FIELDS, 0)
            for identifier, meter in fetched.items():
                record = updated["meters"].setdefault(identifier, {"months": {}})
                record["months"][month_key] = {
                    field: getattr(meter.reading, field) for field in CONSUMPTION_FIELDS
                }
                # Prefer the latest available reading over a missing-month placeholder.
                has_reading = meter.reading.reading is not None and (
                    meter.reading.quality != "F" or meter.reading.reading != 0)
                current_meters[identifier] = meter
                if has_reading:
                    available_readings[identifier] = meter
        current_meters.update(available_readings)
        meters = {}
        for identifier, meter in current_meters.items():
            months = updated["meters"][identifier]["months"]
            totals = {field: float(sum(
                (Decimal(str(values.get(field) or 0)) for values in months.values()),
                Decimal(0),
            )) for field in CONSUMPTION_FIELDS}
            meters[identifier] = replace(
                meter, reading=replace(meter.reading, **totals), retrieved_at=snapshot.retrieved_at)
        if updated != self.data:
            # Publish new totals only after their complete monthly basis is saved.
            await self.store.async_save(updated)
            self.data = updated
        return meters
