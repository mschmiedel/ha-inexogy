"""The inexogy integration."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InexogyClient
from .coordinator import InexogyConfigEntry, InexogyCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Set up inexogy from a config entry."""
    client = InexogyClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = InexogyCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Entries created before 0.3.0 were titled after the series ID; switch
    # them to the meter serial unless the user renamed the entry.
    serial = coordinator.data.meter_serial_number
    if serial and entry.title == f"inexogy {coordinator.series_id[:8]}":
        hass.config_entries.async_update_entry(entry, title=f"inexogy {serial}")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InexogyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
