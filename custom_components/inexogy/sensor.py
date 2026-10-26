"""Sensors for inexogy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, meter_id
from .coordinator import InexogyConfigEntry, InexogyCoordinator
from .parser import MeterData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class InexogySensorEntityDescription(SensorEntityDescription):
    """Describes an inexogy sensor."""

    value_fn: Callable[[MeterData], float | datetime | None]


SENSORS: tuple[InexogySensorEntityDescription, ...] = (
    InexogySensorEntityDescription(
        key="consumption_energy",
        translation_key="consumption_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda data: data.consumption_energy_kwh,
    ),
    InexogySensorEntityDescription(
        key="feed_in_energy",
        translation_key="feed_in_energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda data: data.feed_in_energy_kwh,
    ),
    InexogySensorEntityDescription(
        key="consumption_power",
        translation_key="consumption_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.consumption_power_w,
    ),
    InexogySensorEntityDescription(
        key="feed_in_power",
        translation_key="feed_in_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.feed_in_power_w,
    ),
    InexogySensorEntityDescription(
        key="net_power",
        translation_key="net_power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=lambda data: data.net_power_w,
    ),
    InexogySensorEntityDescription(
        key="last_measurement",
        translation_key="last_measurement",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: data.last_measurement,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InexogyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up inexogy sensors, one device per meter.

    Meters that show up in later updates get their entities added then.
    """
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_meters() -> None:
        new = [serial for serial in coordinator.data.meters if serial not in known]
        known.update(new)
        async_add_entities(
            InexogySensor(coordinator, serial, description)
            for serial in new
            for description in SENSORS
        )

    _add_new_meters()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_meters))


class InexogySensor(CoordinatorEntity[InexogyCoordinator], SensorEntity):
    """A sensor for one value of one meter."""

    _attr_has_entity_name = True
    entity_description: InexogySensorEntityDescription

    def __init__(
        self,
        coordinator: InexogyCoordinator,
        serial: str,
        description: InexogySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._serial = serial
        self._attr_unique_id = f"{meter_id(coordinator.series_id, serial)}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, meter_id(coordinator.series_id, serial))},
            name=f"inexogy {serial}",
            manufacturer="inexogy",
            model="Smart meter",
            serial_number=serial,
        )

    @property
    def _meter(self) -> MeterData | None:
        return self.coordinator.data.meters.get(self._serial)

    @property
    def available(self) -> bool:
        """Return whether the meter is part of the latest update."""
        return super().available and self._meter is not None

    @property
    def native_value(self) -> float | datetime | None:
        """Return the sensor value."""
        meter = self._meter
        return self.entity_description.value_fn(meter) if meter else None
