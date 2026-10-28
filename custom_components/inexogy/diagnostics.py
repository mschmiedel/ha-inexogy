"""Diagnostics download for inexogy (REQ-24)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import CONF_SERIES_ID, DEFAULT_MEASUREMENT_INTERVAL
from .coordinator import InexogyConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, CONF_SERIES_ID, "title", "unique_id"}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: InexogyConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Meters are listed by position, not by serial; tokens are not included.
    """
    coordinator = entry.runtime_data
    data = coordinator.data
    meters = []
    for meter in data.meters.values():
        interval = meter.measurement_interval
        meters.append(
            {
                "series": sorted(f"{type_}/{series_type}" for type_, series_type in meter.series),
                "consumption_energy_kwh": meter.consumption_energy_kwh,
                "feed_in_energy_kwh": meter.feed_in_energy_kwh,
                "consumption_power_w": meter.consumption_power_w,
                "feed_in_power_w": meter.feed_in_power_w,
                "net_power_w": meter.net_power_w,
                "last_measurement": _iso(meter.last_measurement),
                "measurement_interval_s": interval.total_seconds() if interval else None,
            }
        )
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
            "next_measurement_due": _iso(data.next_measurement_due(DEFAULT_MEASUREMENT_INTERVAL)),
            "last_new_data_at": _iso(coordinator.last_new_data_at),
            "skips_next_poll": coordinator.skips_next_poll,
            "offline": coordinator.offline,
        },
        "meters": meters,
        "api_stats": coordinator.stats.as_dict(),
    }
