"""Parsing of inexogy portal responses.

Kept free of Home Assistant imports so it can be unit tested on its own.

The portal delta-encodes its value lists: the first entry carries absolute
numbers for ``time``, ``value`` and ``reading``, every following entry only
the difference to its predecessor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Energy readings are delivered in 10^-10 kWh, power values in mW.
ENERGY_DIVISOR_KWH = 10_000_000_000
POWER_DIVISOR_W = 1_000

SERIES_CONSUMPTION = "CONSUMPTION"
SERIES_FEED = "FEED"
TYPE_ENERGY = "ENERGY"
TYPE_POWER = "POWER"

_DELTA_FIELDS = ("time", "value", "reading")


@dataclass(frozen=True)
class Point:
    """One decoded data point."""

    time: datetime
    value: int
    reading: int


@dataclass
class Series:
    """One decoded measurement series."""

    type: str
    series_type: str
    meter_serial_number: str | None
    points: list[Point] = field(default_factory=list)

    @property
    def latest(self) -> Point | None:
        """Return the most recent data point."""
        return self.points[-1] if self.points else None


@dataclass
class RecentData:
    """Current values derived from the ``recent`` endpoint."""

    series: dict[tuple[str, str], Series]

    def _latest(self, type_: str, series_type: str) -> Point | None:
        series = self.series.get((type_, series_type))
        return series.latest if series else None

    @property
    def meter_serial_number(self) -> str | None:
        """Return the serial number reported for the meter."""
        for series in self.series.values():
            if series.meter_serial_number:
                return series.meter_serial_number
        return None

    @property
    def consumption_energy_kwh(self) -> float | None:
        """Meter reading for energy drawn from the grid."""
        point = self._latest(TYPE_ENERGY, SERIES_CONSUMPTION)
        return point.value / ENERGY_DIVISOR_KWH if point else None

    @property
    def feed_in_energy_kwh(self) -> float | None:
        """Meter reading for energy fed into the grid."""
        point = self._latest(TYPE_ENERGY, SERIES_FEED)
        return point.value / ENERGY_DIVISOR_KWH if point else None

    @property
    def consumption_power_w(self) -> float | None:
        """Average grid import power of the latest interval."""
        point = self._latest(TYPE_POWER, SERIES_CONSUMPTION)
        return abs(point.value) / POWER_DIVISOR_W if point else None

    @property
    def feed_in_power_w(self) -> float | None:
        """Average grid export power of the latest interval.

        The portal reports feed-in power with a negative sign.
        """
        point = self._latest(TYPE_POWER, SERIES_FEED)
        return abs(point.value) / POWER_DIVISOR_W if point else None

    @property
    def net_power_w(self) -> float | None:
        """Grid import minus grid export (negative while exporting)."""
        consumption = self.consumption_power_w
        feed_in = self.feed_in_power_w
        if consumption is None and feed_in is None:
            return None
        return (consumption or 0.0) - (feed_in or 0.0)

    @property
    def last_measurement(self) -> datetime | None:
        """Timestamp of the latest power interval."""
        times = [
            point.time
            for key in ((TYPE_POWER, SERIES_CONSUMPTION), (TYPE_POWER, SERIES_FEED))
            if (point := self._latest(*key)) is not None
        ]
        return max(times) if times else None


def decode_values(values: list[dict[str, Any]]) -> list[Point]:
    """Undo the delta encoding of a value list."""
    points: list[Point] = []
    running = dict.fromkeys(_DELTA_FIELDS, 0)
    for entry in values:
        for key in _DELTA_FIELDS:
            running[key] += int(entry.get(key) or 0)
        points.append(
            Point(
                time=datetime.fromtimestamp(running["time"] / 1000, tz=UTC),
                value=running["value"],
                reading=running["reading"],
            )
        )
    return points


def parse_series(payload: list[dict[str, Any]]) -> dict[tuple[str, str], Series]:
    """Parse a list of series as returned by the portal."""
    result: dict[tuple[str, str], Series] = {}
    for raw in payload:
        series = Series(
            type=str(raw.get("type")),
            series_type=str(raw.get("seriesType")),
            meter_serial_number=raw.get("meterSerialNumber"),
            points=decode_values(raw.get("values") or []),
        )
        result[(series.type, series.series_type)] = series
    return result


def parse_recent(payload: list[dict[str, Any]]) -> RecentData:
    """Parse the response of the ``recent`` endpoint."""
    return RecentData(series=parse_series(payload))
