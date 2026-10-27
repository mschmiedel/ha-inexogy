"""Tests for the API statistics."""

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import sys

# Load stats.py directly so the tests do not need Home Assistant installed.
_PATH = Path(__file__).parents[1] / "custom_components" / "inexogy" / "stats.py"
_SPEC = importlib.util.spec_from_file_location("inexogy_stats", _PATH)
stats_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = stats_module
_SPEC.loader.exec_module(stats_module)
ApiStats = stats_module.ApiStats


def test_ratios_without_polls():
    stats = ApiStats()
    assert stats.polls_per_new_value is None
    assert stats.new_data_ratio is None


def test_ratios():
    stats = ApiStats(polls_new_data=4, polls_no_new_data=8, polls_failed=3)
    assert stats.polls_successful == 12
    assert stats.polls_per_new_value == 3.0
    assert stats.new_data_ratio == 33.3


def test_roundtrip():
    stats = ApiStats(api_calls=7, logins=1, last_api_call=datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    assert ApiStats.from_dict(stats.as_dict()) == stats


def test_from_dict_tolerates_garbage():
    restored = ApiStats.from_dict(
        {"api_calls": "x", "logins": 2, "unknown": 1, "last_api_call": "?"}
    )
    assert restored == ApiStats(logins=2)
    assert ApiStats.from_dict(None) == ApiStats()
