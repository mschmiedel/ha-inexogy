"""Constants for the inexogy integration."""

from datetime import timedelta

DOMAIN = "inexogy"

API_BASE_URL = "https://api.inexogy.com/portal"

CONF_SERIES_ID = "series_id"

DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)

# How far back the "recent" endpoint is queried. The portal delivers
# 15-minute power intervals, so a few hours are plenty.
RECENT_LOOKBACK = timedelta(hours=3)
