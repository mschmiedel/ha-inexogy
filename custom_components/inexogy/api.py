"""Minimal client for the inexogy portal API.

The portal hands out JWTs on login, but this is not a real OAuth2 setup:
there is no issuer metadata and the signature cannot be verified. The token
is therefore treated as an opaque bearer string. Its ``exp`` claim is read
(unverified) only to renew it shortly before it expires.

Renewal uses the refresh token (``POST /auth/refresh``); if that is expired
or rejected, the client logs in again with email and password. The refresh
token can be persisted by the caller (see ``on_refresh_token_changed``) so a
restart does not need a full login. A 401
response on a data request discards the access token and renews it once.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from datetime import UTC, datetime
import json
import logging
import time
from typing import Any

import aiohttp

from .const import API_BASE_URL
from .parser import RecentData, parse_recent
from .stats import ApiStats

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)
# Renew tokens this many seconds before they expire.
_EXPIRY_MARGIN = 60
_CONTAINER_PAGE_SIZE = 30
_MAX_CONTAINER_PAGES = 10


class InexogyError(Exception):
    """Base error for the inexogy client."""


class InexogyAuthError(InexogyError):
    """Credentials were rejected."""


class InexogyConnectionError(InexogyError):
    """The portal could not be reached or answered unexpectedly."""


def _token_expiry(token: str) -> float | None:
    """Return the unverified ``exp`` claim of a JWT, if present."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except (IndexError, ValueError, TypeError, AttributeError):
        return None


class InexogyClient:
    """Talk to the inexogy portal."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        stats: ApiStats | None = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self.stats = stats or ApiStats()
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._expires_at: float | None = None
        self._refresh_token: str | None = None
        self._refresh_expires_at: float | None = None
        self._lock = asyncio.Lock()
        # Called whenever the refresh token changes, so it can be persisted.
        self.on_refresh_token_changed: Callable[[], None] | None = None

    @property
    def refresh_token(self) -> str | None:
        """Return the current refresh token, if any."""
        return self._refresh_token

    def restore_refresh_token(self, token: str | None) -> None:
        """Use a refresh token from a previous run; ignored if already expired."""
        if not token:
            return
        expires_at = _token_expiry(token)
        if not self._usable(token, expires_at):
            return
        self._refresh_token = token
        self._refresh_expires_at = expires_at

    def _set_refresh_token(self, token: str | None) -> None:
        if token == self._refresh_token:
            return
        self._refresh_token = token
        self._refresh_expires_at = _token_expiry(token) if token else None
        if self.on_refresh_token_changed is not None:
            self.on_refresh_token_changed()

    def _count_call(self) -> None:
        self.stats.api_calls += 1
        self.stats.last_api_call = datetime.now(UTC)

    @staticmethod
    def _usable(token: str | None, expires_at: float | None) -> bool:
        if token is None:
            return False
        if expires_at is None:
            return True
        return time.time() < expires_at - _EXPIRY_MARGIN

    def _store_tokens(self, data: Any) -> None:
        token = data.get("accessToken") or data.get("token") if isinstance(data, dict) else None
        if not token:
            raise InexogyConnectionError("Auth response contained no access token")
        self._access_token = token
        self._expires_at = _token_expiry(token)
        refresh = data.get("refreshToken")
        if refresh:
            self._set_refresh_token(refresh)

    async def _async_refresh(self) -> bool:
        """Renew the access token with the refresh token; False on failure."""
        self._count_call()
        try:
            async with self._session.post(
                f"{API_BASE_URL}/auth/refresh",
                json={"token": self._refresh_token},
                timeout=_TIMEOUT,
            ) as resp:
                resp.raise_for_status()
                self._store_tokens(await resp.json(content_type=None))
        except (InexogyError, aiohttp.ClientError, TimeoutError, ValueError) as err:
            _LOGGER.debug("Token refresh failed, logging in again: %s", err)
            self._set_refresh_token(None)
            return False
        self.stats.token_refreshes += 1
        return True

    async def async_login(self) -> None:
        """Log in and store fresh tokens."""
        self._count_call()
        try:
            async with self._session.post(
                f"{API_BASE_URL}/auth",
                json={"email": self._email, "password": self._password},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (400, 401, 403):
                    raise InexogyAuthError("Login rejected")
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except InexogyAuthError:
            raise
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise InexogyConnectionError(f"Login failed: {err}") from err

        self._store_tokens(data)
        self.stats.logins += 1

    async def _ensure_token(self) -> str:
        async with self._lock:
            if not self._usable(self._access_token, self._expires_at):
                refreshed = (
                    self._usable(self._refresh_token, self._refresh_expires_at)
                    and await self._async_refresh()
                )
                if not refreshed:
                    await self.async_login()
            assert self._access_token is not None
            return self._access_token

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        for attempt in range(2):
            token = await self._ensure_token()
            self._count_call()
            try:
                async with self._session.get(
                    f"{API_BASE_URL}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status in (401, 403):
                        _LOGGER.debug("Access token rejected, logging in again")
                        self._access_token = None
                        if attempt == 0:
                            continue
                        raise InexogyAuthError("Access token rejected after fresh login")
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise InexogyConnectionError(f"Request to {path} failed: {err}") from err
        raise InexogyConnectionError("Unreachable")

    async def async_get_default_series_id(self) -> str | None:
        """Return the account's default measurement series ID."""
        payload = await self._get("/user/settings", {})
        if not isinstance(payload, dict):
            raise InexogyConnectionError("Unexpected response format")
        series_id = payload.get("defaultContainerId")
        return str(series_id) if series_id else None

    async def async_get_containers(self) -> list[dict[str, Any]]:
        """Return all containers (measurement series) of the account."""
        containers: list[dict[str, Any]] = []
        page = 0
        while page < _MAX_CONTAINER_PAGES:
            payload = await self._get(
                "/containers", {"pageNo": str(page), "pageSize": str(_CONTAINER_PAGE_SIZE)}
            )
            if not isinstance(payload, dict):
                raise InexogyConnectionError("Unexpected response format")
            batch = payload.get("containers") or []
            containers.extend(c for c in batch if isinstance(c, dict))
            if not batch or len(containers) >= int(payload.get("totalCount") or 0):
                break
            page += 1
        return containers

    async def async_get_recent(self, series_id: str, from_ms: int) -> RecentData:
        """Fetch current meter readings and the latest power intervals."""
        payload = await self._get(
            f"/measurement-series/{series_id}/recent",
            {"from": str(from_ms), "dimension": "standard"},
        )
        if not isinstance(payload, list):
            raise InexogyConnectionError("Unexpected response format")
        return parse_recent(payload)
