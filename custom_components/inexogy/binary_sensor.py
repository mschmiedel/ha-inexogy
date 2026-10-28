"""Binary sensors for inexogy."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import primary_meter
from .coordinator import InexogyConfigEntry, InexogyCoordinator
from .sensor import meter_device_info

PARALLEL_UPDATES = 0

CONNECTION = BinarySensorEntityDescription(
    key="connection",
    translation_key="connection",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: InexogyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the connection sensor on the container's first meter (REQ-25)."""
    coordinator = entry.runtime_data
    if (serial := primary_meter(coordinator.data)) is not None:
        async_add_entities([InexogyConnectionSensor(coordinator, serial)])


class InexogyConnectionSensor(CoordinatorEntity[InexogyCoordinator], BinarySensorEntity):
    """Whether the portal receives data from the meter (container not offline).

    The container list is only fetched while this entity is enabled.
    """

    _attr_has_entity_name = True
    entity_description = CONNECTION

    def __init__(self, coordinator: InexogyCoordinator, serial: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.series_id}_{CONNECTION.key}"
        self._attr_device_info = meter_device_info(coordinator.series_id, serial)

    async def async_added_to_hass(self) -> None:
        """Start fetching container data while the entity exists."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.track_containers())
        self.coordinator.config_entry.async_create_background_task(
            self.hass,
            self.coordinator.async_refresh_containers(),
            "inexogy containers",
        )

    @property
    def available(self) -> bool:
        """Return whether the offline flag is known."""
        return self.coordinator.offline is not None

    @property
    def is_on(self) -> bool | None:
        """Return True while the container is online."""
        offline = self.coordinator.offline
        return None if offline is None else not offline
