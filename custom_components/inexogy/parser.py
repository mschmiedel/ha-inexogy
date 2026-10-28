"""Parsing of inexogy portal responses.

Kept free of Home Assistant imports so it can be unit tested on its own.

The portal delta-encodes its value lists: the first entry carries absolute
numbers for ``time``, ``value`` and ``reading``, every following entry only
the difference to its predecessor.

One response can contain series of several meters. The same meter may show
up with different serial lengths (with and without manufacturer prefix,
e.g. ``1ABC0012345678`` and ``12345678``); those are merged into one meter
named after the longest variant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
class MeterData:
    """Current values of one meter."""

    serial_number: str
    series: dict[tuple[str, str], Series] = field(default_factory=dict)

    def _latest(self, type_: str, series_type: str) -> Point | None:
        series = self.series.get((type_, series_type))
        return series.latest if series else None

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

    @property
    def measurement_interval(self) -> timedelta | None:
        """Spacing of the latest power intervals (usually 15 minutes)."""
        for key in ((TYPE_POWER, SERIES_CONSUMPTION), (TYPE_POWER, SERIES_FEED)):
            series = self.series.get(key)
            if series and len(series.points) >= 2:
                interval = series.points[-1].time - series.points[-2].time
                if interval > timedelta(0):
                    return interval
        return None


@dataclass
class RecentData:
    """Current values derived from the ``recent`` endpoint, per meter."""

    meters: dict[str, MeterData]

    def measurement_interval(self, default_interval: timedelta) -> timedelta:
        """Shortest measurement interval of all meters (fallback: default)."""
        intervals = [
            interval
            for meter in self.meters.values()
            if (interval := meter.measurement_interval) is not None
        ]
        return min(intervals) if intervals else default_interval

    def next_measurement_due(self, default_interval: timedelta) -> datetime | None:
        """Earliest time a newer measurement can exist for any meter.

        A value for measurement time T is only available after T, so after the
        latest value T no newer one can appear before T + interval. With
        several meters the one that is due first counts.
        """
        due = [
            latest + (meter.measurement_interval or default_interval)
            for meter in self.meters.values()
            if (latest := meter.last_measurement) is not None
        ]
        return min(due) if due else None


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


def parse_series(payload: list[dict[str, Any]]) -> list[Series]:
    """Parse a list of series as returned by the portal."""
    return [
        Series(
            type=str(raw.get("type")),
            series_type=str(raw.get("seriesType")),
            meter_serial_number=raw.get("meterSerialNumber") or None,
            points=decode_values(raw.get("values") or []),
        )
        for raw in payload
    ]


def _canonical_serials(serials: set[str]) -> dict[str, str]:
    """Map every serial to the longest serial it is a suffix of."""
    canonical: dict[str, str] = {}
    for serial in sorted(serials, key=len, reverse=True):
        canonical[serial] = next((c for c in canonical.values() if c.endswith(serial)), serial)
    return canonical


def parse_recent(payload: list[dict[str, Any]]) -> RecentData:
    """Parse the response of the ``recent`` endpoint."""
    series_list = parse_series(payload)
    canonical = _canonical_serials(
        {s.meter_serial_number for s in series_list if s.meter_serial_number}
    )
    meters: dict[str, MeterData] = {}
    for series in series_list:
        if series.meter_serial_number:
            serial = canonical[series.meter_serial_number]
        elif len(set(canonical.values())) == 1:
            # Series without serial belong to the only meter there is.
            serial = next(iter(canonical.values()))
        else:
            serial = "unknown"
        meter = meters.setdefault(serial, MeterData(serial_number=serial))
        meter.series[(series.type, series.series_type)] = series
    return RecentData(meters=meters)


# A serial without manufacturer prefix has 8 digits; shorter input must not
# match via its ending only.
_MIN_PARTIAL_SERIAL = 8


def _normalize_serial(serial: str) -> str:
    return "".join(ch for ch in serial.upper() if ch.isalnum())


def find_container_for_meter(containers: list[dict[str, Any]], serial: str) -> str | None:
    """Return the ID of the container holding the meter with ``serial``.

    The serial may be given with or without manufacturer prefix
    (``1ABC0012345678`` or ``12345678``); a match on the ending needs at least
    8 characters. Returns None when no container or
    more than one container matches.
    """
    wanted = _normalize_serial(serial)
    if not wanted:
        return None
    exact: list[str] = []
    partial: list[str] = []
    for container in containers:
        container_id = container.get("id")
        if not container_id:
            continue
        for candidate in container.get("meterSerialNumbers") or []:
            have = _normalize_serial(str(candidate))
            if have == wanted:
                exact.append(str(container_id))
            elif min(len(have), len(wanted)) >= _MIN_PARTIAL_SERIAL and (
                have.endswith(wanted) or wanted.endswith(have)
            ):
                partial.append(str(container_id))
    matches = list(dict.fromkeys(exact or partial))
    return matches[0] if len(matches) == 1 else None
