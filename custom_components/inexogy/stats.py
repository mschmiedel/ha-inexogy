"""API usage statistics.

Kept free of Home Assistant imports so it can be unit tested on its own.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any


@dataclass
class ApiStats:
    """Counters about the communication with the inexogy portal."""

    api_calls: int = 0
    logins: int = 0
    token_refreshes: int = 0
    polls_new_data: int = 0
    polls_no_new_data: int = 0
    polls_failed: int = 0
    last_api_call: datetime | None = None

    @property
    def polls_successful(self) -> int:
        """Polls that returned a valid response."""
        return self.polls_new_data + self.polls_no_new_data

    @property
    def polls_per_new_value(self) -> float | None:
        """Successful polls needed per new measurement (ideal: 1.0)."""
        if not self.polls_new_data:
            return None
        return round(self.polls_successful / self.polls_new_data, 2)

    @property
    def new_data_ratio(self) -> float | None:
        """Share of successful polls that brought new data, in percent."""
        if not self.polls_successful:
            return None
        return round(self.polls_new_data / self.polls_successful * 100, 1)

    def as_dict(self) -> dict[str, Any]:
        """Serialize for Home Assistant storage."""
        data = asdict(self)
        data["last_api_call"] = self.last_api_call.isoformat() if self.last_api_call else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ApiStats:
        """Restore from storage, ignoring unknown or broken fields."""
        stats = cls()
        if not data:
            return stats
        for f in fields(cls):
            value = data.get(f.name)
            if value is None:
                continue
            try:
                if f.name == "last_api_call":
                    stats.last_api_call = datetime.fromisoformat(value)
                else:
                    setattr(stats, f.name, int(value))
            except (TypeError, ValueError):
                continue
        return stats
