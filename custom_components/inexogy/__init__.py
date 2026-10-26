"""The inexogy integration."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InexogyClient
from .const import DOMAIN, meter_id
from .coordinator import InexogyConfigEntry, InexogyCoordinator
from .sensor import SENSORS

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Set up inexogy from a config entry."""
    client = InexogyClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = InexogyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    meters = list(coordinator.data.meters)
    if meters:
        _migrate_single_device(hass, entry, coordinator.series_id, meters[0])

    # Entries created before 0.3.0 were titled after the series ID; switch
    # them to the meter serial unless the user renamed the entry.
    if len(meters) == 1 and entry.title == f"inexogy {coordinator.series_id[:8]}":
        hass.config_entries.async_update_entry(entry, title=f"inexogy {meters[0]}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


@callback
def _migrate_single_device(
    hass: HomeAssistant, entry: InexogyConfigEntry, series_id: str, serial: str
) -> None:
    """Move the pre-0.4.0 device and entities (one per series) to the first meter.

    Keeps entity IDs and history when the device ID gains the meter serial.
    """
    new_id = meter_id(series_id, serial)

    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device(identifiers={(DOMAIN, series_id)}):
        device_registry.async_update_device(device.id, new_identifiers={(DOMAIN, new_id)})

    # Old unique IDs are "<series>_<key>", new ones "<series>_<serial>_<key>".
    old_unique_ids = {f"{series_id}_{d.key}": d.key for d in SENSORS}
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if key := old_unique_ids.get(entity.unique_id):
            entity_registry.async_update_entity(entity.entity_id, new_unique_id=f"{new_id}_{key}")


async def async_unload_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
