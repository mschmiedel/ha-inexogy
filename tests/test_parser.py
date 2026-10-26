"""Tests for the response parser (synthetic data only)."""

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys

# Load parser.py directly so the tests do not need Home Assistant installed.
_PATH = Path(__file__).parents[1] / "custom_components" / "inexogy" / "parser.py"
_SPEC = importlib.util.spec_from_file_location("inexogy_parser", _PATH)
parser = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = parser
_SPEC.loader.exec_module(parser)

T0 = 1_700_000_000_000  # arbitrary epoch ms
QUARTER = 900_000


def _entry(time: int, value: int, reading: int = 0) -> dict:
    return {
        "cost": 0.0,
        "isComputedValue": False,
        "marketPriceInCents": None,
        "reactiveReading": 0,
        "reading": reading,
        "selfConsumptionReward": 0.0,
        "time": time,
        "value": value,
    }


def _series(type_: str, series_type: str, values: list[dict]) -> dict:
    return {
        "meterSerialNumber": "00000000",
        "type": type_,
        "values": values,
        "seriesType": series_type,
    }


RECENT = [
    # 1234.5 kWh drawn, 56.789 kWh fed in
    _series("ENERGY", "CONSUMPTION", [_entry(T0 + 2 * QUARTER, 12_345_000_000_000)]),
    _series("ENERGY", "FEED", [_entry(T0 + 2 * QUARTER, 567_890_000_000)]),
    # power 500 W -> 800 W -> 300 W, reading grows with it
    _series(
        "POWER",
        "CONSUMPTION",
        [
            _entry(T0, 500_000, 12_340_000_000_000),
            _entry(QUARTER, 300_000, 2_000_000_000),
            _entry(QUARTER, -500_000, 750_000_000),
        ],
    ),
    # feed-in is reported negative: -100 W -> -50 W -> -2000 W
    _series(
        "POWER",
        "FEED",
        [
            _entry(T0, -100_000, 567_000_000_000),
            _entry(QUARTER, 50_000, 25_000_000),
            _entry(QUARTER, -1_950_000, 12_500_000),
        ],
    ),
]


def test_decode_values_is_cumulative():
    points = parser.decode_values(RECENT[2]["values"])
    assert [p.value for p in points] == [500_000, 800_000, 300_000]
    assert [p.reading for p in points] == [
        12_340_000_000_000,
        12_342_000_000_000,
        12_342_750_000_000,
    ]
    assert points[-1].time == datetime.fromtimestamp((T0 + 2 * QUARTER) / 1000, tz=UTC)


def test_recent_values():
    data = parser.parse_recent(RECENT)
    assert data.consumption_energy_kwh == 1234.5
    assert data.feed_in_energy_kwh == 56.789
    assert data.consumption_power_w == 300.0
    assert data.feed_in_power_w == 2000.0
    assert data.net_power_w == -1700.0
    assert data.last_measurement == datetime.fromtimestamp((T0 + 2 * QUARTER) / 1000, tz=UTC)
    assert data.meter_serial_number == "00000000"


def test_missing_series():
    data = parser.parse_recent([RECENT[0]])
    assert data.consumption_energy_kwh == 1234.5
    assert data.feed_in_energy_kwh is None
    assert data.consumption_power_w is None
    assert data.net_power_w is None
    assert data.last_measurement is None


def test_empty_response():
    data = parser.parse_recent([])
    assert data.series == {}
    assert data.meter_serial_number is None
