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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import InexogyConfigEntry, InexogyCoordinator
from .parser import RecentData

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class InexogySensorEntityDescription(SensorEntityDescription):
    """Describes an inexogy sensor."""

    value_fn: Callable[[RecentData], float | datetime | None]


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
    """Set up inexogy sensors."""
    coordinator = entry.runtime_data
    async_add_entities(InexogySensor(coordinator, description) for description in SENSORS)


class InexogySensor(CoordinatorEntity[InexogyCoordinator], SensorEntity):
    """A sensor fed by the inexogy coordinator."""

    _attr_has_entity_name = True
    entity_description: InexogySensorEntityDescription

    def __init__(
        self,
        coordinator: InexogyCoordinator,
        description: InexogySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.series_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.series_id)},
            name=f"inexogy {coordinator.data.meter_serial_number or coordinator.series_id[:8]}",
            manufacturer="inexogy",
            model="Smart meter",
            serial_number=coordinator.data.meter_serial_number,
        )

    @property
    def native_value(self) -> float | datetime | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
