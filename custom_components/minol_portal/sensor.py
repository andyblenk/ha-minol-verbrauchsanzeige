"""Dynamic per-meter entities; no fabricated consumption statistics."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .model import latest_reporting_month, master_data


@dataclass(frozen=True, kw_only=True)
class MinolSensorDescription(SensorEntityDescription):
    field: str | None = None


DESCRIPTIONS = (
    MinolSensorDescription(key="reading", name="Letzte Ablesung", field="reading", icon="mdi:counter"),
    MinolSensorDescription(key="evaluated_consumption", name="Gesamtverbrauch", field="evaluated_consumption", icon="mdi:chart-bar"),
    MinolSensorDescription(key="rating", name="Bewertungsfaktor", field="rating", icon="mdi:multiplication"),
    MinolSensorDescription(key="consumption", name="Rohverbrauch gesamt", field="consumption"),
    MinolSensorDescription(key="device_number", name="Gerätenummer", field="device_number", entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:identifier"),
    MinolSensorDescription(key="service", name="Verbrauchsart", entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:format-list-bulleted"),
    MinolSensorDescription(key="last_reporting_month", name="Letzter Berichtsmonat", entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:calendar-month"),
    MinolSensorDescription(key="last_refresh", name="Letzter erfolgreicher Abruf", device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC),
    MinolSensorDescription(key="room", name="Raum", field="room", entity_category=EntityCategory.DIAGNOSTIC, icon="mdi:floor-plan"),
)


USER_DESCRIPTIONS = (
    SensorEntityDescription(key="email", name="E-Mail", icon="mdi:email-outline"),
    SensorEntityDescription(key="userId", name="Benutzerkennung", icon="mdi:account-key-outline"),
    SensorEntityDescription(key="displayName", name="Name", icon="mdi:account-outline"),
    SensorEntityDescription(key="customerName", name="Kundenname", icon="mdi:account-outline"),
    SensorEntityDescription(key="customer", name="Kundennummer", icon="mdi:identifier"),
    SensorEntityDescription(key="property_number", name="Liegenschaft", icon="mdi:office-building"),
    SensorEntityDescription(key="unit_number", name="Nutzeinheit", icon="mdi:home-outline"),
    SensorEntityDescription(key="tenant_number", name="Nutzereinheiten-ID", icon="mdi:identifier"),
    SensorEntityDescription(key="floor_position", name="Geschosslage", icon="mdi:stairs"),
    SensorEntityDescription(key="street", name="Straße", icon="mdi:road-variant"),
    SensorEntityDescription(key="city", name="Ort", icon="mdi:city"),
    SensorEntityDescription(key="country", name="Land", icon="mdi:earth"),
    SensorEntityDescription(key="move_in", name="Einzug", icon="mdi:calendar-arrow-right"),
    SensorEntityDescription(key="move_out", name="Auszug", icon="mdi:calendar-arrow-left"),
    SensorEntityDescription(key="locale", name="Sprache", icon="mdi:translate"),
    SensorEntityDescription(key="userType", name="Benutzertyp", icon="mdi:account-outline"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    known = set()
    known_user_fields = set()

    @callback
    def discover():
        additions = []
        for identifier, meter in coordinator.data.meters.items():
            if identifier in known:
                continue
            known.add(identifier)
            additions.extend(MinolMeterSensor(coordinator, meter, description) for description in DESCRIPTIONS)
        user_data = master_data(coordinator.data.snapshot)
        for description in USER_DESCRIPTIONS:
            if description.key in known_user_fields:
                continue
            if user_data.get(description.key) is not None:
                known_user_fields.add(description.key)
                additions.append(MinolUserSensor(coordinator, entry.unique_id, description))
        if additions:
            async_add_entities(additions)

    discover()
    entry.async_on_unload(coordinator.async_add_listener(discover))


class MinolMeterSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, meter, description):
        super().__init__(coordinator)
        self.entity_description = description
        self.identifier = meter.identifier
        self._attr_unique_id = f"{meter.identifier}_{description.key}"
        # Keep the room once in entity IDs, independently of HA's device prefix.
        object_id = slugify(
            f"{meter.reading.room or 'Raum unbekannt'} {meter.service} "
            f"{meter.reading.device_number} {description.name}"
        )
        self.entity_id = f"sensor.{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, meter.identifier)},
            name=f"{meter.service} {meter.reading.room or 'Raum unbekannt'} {meter.reading.device_number}",
            serial_number=meter.reading.device_number, suggested_area=meter.reading.room,
        )
        if description.key in {"consumption", "evaluated_consumption"}:
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_suggested_display_precision = 2
        if description.key == "evaluated_consumption":
            self._attr_native_unit_of_measurement = meter.result_unit
            self._attr_device_class = {"kWh": SensorDeviceClass.ENERGY, "m³": SensorDeviceClass.WATER}.get(meter.result_unit)

    @property
    def available(self):
        return super().available and self.identifier in self.coordinator.data.meters

    @property
    def native_value(self):
        meter = self.coordinator.data.meters.get(self.identifier)
        if meter is None:
            return None
        if self.entity_description.key == "last_refresh":
            return datetime.fromisoformat(meter.retrieved_at) if meter.retrieved_at else None
        if self.entity_description.key == "last_reporting_month":
            return latest_reporting_month(self.coordinator.data.snapshot)
        if self.entity_description.key == "service":
            return meter.service
        value = getattr(meter.reading, self.entity_description.field)
        if self.entity_description.key in {"consumption", "evaluated_consumption"} and value is not None:
            return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return value

    @property
    def extra_state_attributes(self):
        meter = self.coordinator.data.meters.get(self.identifier)
        if meter is None:
            return {}
        snapshot = self.coordinator.data.snapshot
        return {"period_start": snapshot.period.start, "period_end": snapshot.period.end,
                "rating": meter.reading.rating, "location_factor": meter.reading.location_factor,
                "conversion_factor": meter.reading.conversion_factor, "quality": meter.reading.quality,
                "source_view": meter.source_view, "retrieved_at": meter.retrieved_at}


class MinolUserSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, identifier, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{identifier}_user_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name="Stammdaten",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return master_data(self.coordinator.data.snapshot).get(self.entity_description.key)
