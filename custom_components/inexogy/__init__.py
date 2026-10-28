"""The inexogy integration."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InexogyClient
from .const import DOMAIN, meter_id, primary_meter
from .coordinator import InexogyConfigEntry, InexogyCoordinator, auth_store, stats_store
from .sensor import SENSORS

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Set up inexogy from a config entry."""
    client = InexogyClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = InexogyCoordinator(hass, entry, client)
    await coordinator.async_load_stats()
    await coordinator.async_load_auth()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    meters = list(coordinator.data.meters)
    if (serial := primary_meter(coordinator.data)) is not None:
        _migrate_single_device(hass, entry, coordinator.series_id, serial)
        _migrate_api_device(hass, coordinator.series_id, serial)

    # Entries are titled after the account; older versions used the series ID
    # or the meter serials. Switch those unless the user renamed the entry.
    legacy_titles = {
        f"inexogy {coordinator.series_id[:8]}",
        f"inexogy {', '.join(meters)}",
        *(f"inexogy {serial}" for serial in meters),
    }
    if entry.title in legacy_titles:
        hass.config_entries.async_update_entry(entry, title=entry.data[CONF_EMAIL])

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


@callback
def _migrate_api_device(hass: HomeAssistant, series_id: str, serial: str) -> None:
    """Move diagnostics from the 1.1.0rc1 "inexogy API" device to the meter.

    Entities keep their entity IDs, enabled state and history.
    """
    device_registry = dr.async_get(hass)
    old = device_registry.async_get_device(identifiers={(DOMAIN, f"{series_id}_api")})
    if old is None:
        return
    new = device_registry.async_get_device(identifiers={(DOMAIN, meter_id(series_id, serial))})
    if new is None:
        return
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_device(
        entity_registry, old.id, include_disabled_entities=True
    ):
        entity_registry.async_update_entity(entity.entity_id, device_id=new.id)
    device_registry.async_remove_device(old.id)


async def async_unload_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_stats()
        await entry.runtime_data.async_save_auth()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> None:
    """Delete the stored API statistics and refresh token together with the entry."""
    await stats_store(hass, entry.entry_id).async_remove()
    await auth_store(hass, entry.entry_id).async_remove()
