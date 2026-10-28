"""Constants for the inexogy integration."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .parser import RecentData

DOMAIN = "inexogy"

API_BASE_URL = "https://api.inexogy.com/portal"

CONF_SERIES_ID = "series_id"
CONF_METER_SERIAL = "meter_serial"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# How far back the "recent" endpoint is queried. The portal delivers
# 15-minute power intervals, so a few hours are plenty.
RECENT_LOOKBACK = timedelta(hours=3)

# Used when the response does not reveal the raster (fewer than two intervals).
DEFAULT_MEASUREMENT_INTERVAL = timedelta(minutes=15)

# Polls are scheduled with some jitter; a poll this much early still counts as on time.
POLL_TOLERANCE = timedelta(minutes=1)


def meter_id(series_id: str, serial: str) -> str:
    """Return the ID used for a meter's device and entity unique IDs."""
    return f"{series_id}_{serial}"


def primary_meter(data: RecentData) -> str | None:
    """Return the meter that carries container-wide entities (the first one)."""
    return next(iter(data.meters), None)
