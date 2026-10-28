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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, meter_id, primary_meter
from .coordinator import InexogyConfigEntry, InexogyCoordinator
from .parser import MeterData
from .stats import ApiStats

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


@dataclass(frozen=True, kw_only=True)
class InexogyStatsSensorEntityDescription(SensorEntityDescription):
    """Describes a diagnostic sensor about the API usage."""

    value_fn: Callable[[ApiStats], float | int | datetime | None]
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    entity_registry_enabled_default: bool = False


def _counter(key: str, attr: str) -> InexogyStatsSensorEntityDescription:
    return InexogyStatsSensorEntityDescription(
        key=key,
        translation_key=key,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda stats: getattr(stats, attr),
    )


STATS_SENSORS: tuple[InexogyStatsSensorEntityDescription, ...] = (
    _counter("api_calls", "api_calls"),
    _counter("logins", "logins"),
    _counter("token_refreshes", "token_refreshes"),
    _counter("polls_new_data", "polls_new_data"),
    _counter("polls_no_new_data", "polls_no_new_data"),
    _counter("polls_failed", "polls_failed"),
    _counter("polls_skipped", "polls_skipped"),
    _counter("missing_values", "missing_values"),
    InexogyStatsSensorEntityDescription(
        key="polls_per_new_value",
        translation_key="polls_per_new_value",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda stats: stats.polls_per_new_value,
    ),
    InexogyStatsSensorEntityDescription(
        key="new_data_ratio",
        translation_key="new_data_ratio",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        value_fn=lambda stats: stats.new_data_ratio,
    ),
    InexogyStatsSensorEntityDescription(
        key="last_api_call",
        translation_key="last_api_call",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda stats: stats.last_api_call,
    ),
)


def meter_device_info(series_id: str, serial: str) -> DeviceInfo:
    """Return the device of one meter (REQ-12, REQ-14)."""
    return DeviceInfo(
        identifiers={(DOMAIN, meter_id(series_id, serial))},
        name=f"inexogy {serial}",
        manufacturer="inexogy",
        model="Smart meter",
        serial_number=serial,
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
    # API statistics belong to the container; they live on its (first) meter.
    if (serial := primary_meter(coordinator.data)) is not None:
        async_add_entities(
            InexogyStatsSensor(coordinator, serial, description) for description in STATS_SENSORS
        )


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
        self._attr_device_info = meter_device_info(coordinator.series_id, serial)

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


class InexogyStatsSensor(CoordinatorEntity[InexogyCoordinator], SensorEntity):
    """Diagnostic sensor about the communication with the portal."""

    _attr_has_entity_name = True
    entity_description: InexogyStatsSensorEntityDescription

    def __init__(
        self,
        coordinator: InexogyCoordinator,
        serial: str,
        description: InexogyStatsSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.series_id}_api_{description.key}"
        self._attr_device_info = meter_device_info(coordinator.series_id, serial)

    @property
    def available(self) -> bool:
        """Statistics stay available while the portal fails; they count the failures."""
        return True

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the statistic."""
        return self.entity_description.value_fn(self.coordinator.stats)
