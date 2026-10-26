"""Data update coordinator for inexogy."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import InexogyAuthError, InexogyClient, InexogyError
from .const import CONF_SERIES_ID, DEFAULT_SCAN_INTERVAL, DOMAIN, RECENT_LOOKBACK
from .parser import RecentData

_LOGGER = logging.getLogger(__name__)

type InexogyConfigEntry = ConfigEntry[InexogyCoordinator]


class InexogyCoordinator(DataUpdateCoordinator[RecentData]):
    """Poll the inexogy portal for recent values."""

    config_entry: InexogyConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: InexogyConfigEntry, client: InexogyClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.series_id: str = entry.data[CONF_SERIES_ID]

    async def _async_update_data(self) -> RecentData:
        from_ms = int((dt_util.utcnow() - RECENT_LOOKBACK).timestamp() * 1000)
        try:
            return await self.client.async_get_recent(self.series_id, from_ms)
        except InexogyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except InexogyError as err:
            raise UpdateFailed(str(err)) from err
