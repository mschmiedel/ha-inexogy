"""Data update coordinator for inexogy."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import InexogyAuthError, InexogyClient, InexogyError
from .const import (
    CONF_SERIES_ID,
    DEFAULT_MEASUREMENT_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    RECENT_LOOKBACK,
)
from .parser import RecentData

_LOGGER = logging.getLogger(__name__)

AUTH_STORAGE_VERSION = 1
STATS_STORAGE_VERSION = 1
# Write statistics to disk at most this often (seconds); HA flushes on shutdown.
STATS_SAVE_DELAY = 60

type InexogyConfigEntry = ConfigEntry[InexogyCoordinator]


def stats_store(hass: HomeAssistant, entry_id: str) -> Store[dict]:
    """Return the storage holding an entry's API statistics."""
    return Store(hass, STATS_STORAGE_VERSION, f"{DOMAIN}.{entry_id}.stats")


def auth_store(hass: HomeAssistant, entry_id: str) -> Store[dict]:
    """Return the storage holding an entry's refresh token (file mode 0600)."""
    return Store(hass, AUTH_STORAGE_VERSION, f"{DOMAIN}.{entry_id}.auth", private=True)


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
        self.stats = client.stats
        self.series_id: str = entry.data[CONF_SERIES_ID]
        self._store = stats_store(hass, entry.entry_id)
        self._auth_store = auth_store(hass, entry.entry_id)
        self._last_measurements: dict[str, datetime] = {}
        client.on_refresh_token_changed = self._schedule_auth_save

    async def async_load_auth(self) -> None:
        """Restore the refresh token of a previous run, if still valid."""
        stored = await self._auth_store.async_load()
        if stored:
            self.client.restore_refresh_token(stored.get("refresh_token"))

    def _auth_data(self) -> dict:
        return {"refresh_token": self.client.refresh_token}

    def _schedule_auth_save(self) -> None:
        self._auth_store.async_delay_save(self._auth_data, 1)

    async def async_save_auth(self) -> None:
        """Write the refresh token now, e.g. before the entry is unloaded."""
        await self._auth_store.async_save(self._auth_data())

    async def async_load_stats(self) -> None:
        """Restore counters from a previous run."""
        stored = await self._store.async_load()
        if not stored:
            return
        restored = type(self.stats).from_dict(stored)
        for name, value in vars(restored).items():
            setattr(self.stats, name, value)
        # Remember what was already seen, so the first poll after a restart
        # does not count as new data.
        for serial, value in (stored.get("last_measurements") or {}).items():
            try:
                self._last_measurements[serial] = datetime.fromisoformat(value)
            except (TypeError, ValueError):
                continue

    def _stats_data(self) -> dict:
        return {
            **self.stats.as_dict(),
            "last_measurements": {
                serial: value.isoformat() for serial, value in self._last_measurements.items()
            },
        }

    async def async_save_stats(self) -> None:
        """Write counters now, e.g. before the entry is unloaded."""
        await self._store.async_save(self._stats_data())

    async def _async_update_data(self) -> RecentData:
        # Skip polls that cannot return anything new: after the latest value T
        # the next one cannot exist before T + interval. The faster inexogy
        # delivers, the more polls are skipped.
        if self.data is not None:
            due = self.data.next_measurement_due(DEFAULT_MEASUREMENT_INTERVAL)
            if due is not None and dt_util.utcnow() < due:
                self.stats.polls_skipped += 1
                self._store.async_delay_save(self._stats_data, STATS_SAVE_DELAY)
                return self.data
        from_ms = int((dt_util.utcnow() - RECENT_LOOKBACK).timestamp() * 1000)
        try:
            data = await self.client.async_get_recent(self.series_id, from_ms)
        except InexogyAuthError as err:
            self._count_poll(failed=True)
            raise ConfigEntryAuthFailed(str(err)) from err
        except InexogyError as err:
            self._count_poll(failed=True)
            raise UpdateFailed(str(err)) from err
        self._count_poll(new_data=self._has_new_data(data))
        return data

    def _has_new_data(self, data: RecentData) -> bool:
        """Return whether the latest measurement of any meter advanced."""
        new_data = False
        for serial, meter in data.meters.items():
            latest = meter.last_measurement
            if latest is None:
                continue
            previous = self._last_measurements.get(serial)
            if previous is None or latest > previous:
                new_data = True
                self._last_measurements[serial] = latest
        return new_data

    def _count_poll(self, *, new_data: bool = False, failed: bool = False) -> None:
        if failed:
            self.stats.polls_failed += 1
        elif new_data:
            self.stats.polls_new_data += 1
        else:
            self.stats.polls_no_new_data += 1
        self._store.async_delay_save(self._stats_data, STATS_SAVE_DELAY)
