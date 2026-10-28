"""Config flow for inexogy."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import InexogyAuthError, InexogyClient, InexogyError
from .const import CONF_METER_SERIAL, CONF_SERIES_ID, DOMAIN, RECENT_LOOKBACK
from .parser import find_container_for_meter

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
        vol.Optional(CONF_METER_SERIAL): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)

STEP_RECONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
        ),
        vol.Optional(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
        ),
    }
)


class InexogyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for inexogy."""

    VERSION = 1

    async def _validate(
        self,
        email: str,
        password: str,
        series_id: str | None = None,
        meter_serial: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Return ``(series_id, error_key)``.

        New entries pass a meter serial (container looked up via /containers)
        or nothing (the account's default container is used). Re-authentication
        passes the series ID stored in the entry.
        """
        client = InexogyClient(async_get_clientsession(self.hass), email, password)
        from_ms = int((dt_util.utcnow() - RECENT_LOOKBACK).timestamp() * 1000)
        try:
            await client.async_login()
            if not series_id and meter_serial:
                series_id = find_container_for_meter(
                    await client.async_get_containers(), meter_serial
                )
                if not series_id:
                    return None, "meter_not_found"
            if not series_id:
                series_id = await client.async_get_default_series_id()
                if not series_id:
                    return None, "no_series_id"
            data = await client.async_get_recent(series_id, from_ms)
        except InexogyAuthError:
            return series_id, "invalid_auth"
        except InexogyError:
            _LOGGER.debug("Validation failed", exc_info=True)
            return series_id, "cannot_connect"
        if not data.meters:
            return series_id, "no_data"
        return series_id, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            series_id, error = await self._validate(
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                meter_serial=(user_input.get(CONF_METER_SERIAL) or "").strip() or None,
            )
            if error is None:
                await self.async_set_unique_id(series_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SERIES_ID: series_id,
                    },
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication after the password was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            _, error = await self._validate(
                entry.data[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                entry.data[CONF_SERIES_ID],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change email and/or password; the measurement series stays (REQ-06)."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            password = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
            _, error = await self._validate(email, password, entry.data[CONF_SERIES_ID])
            if error is None:
                # Keep a user-defined title; follow the email otherwise (REQ-02).
                title = email if entry.title == entry.data[CONF_EMAIL] else entry.title
                return self.async_update_reload_and_abort(
                    entry,
                    title=title,
                    data_updates={CONF_EMAIL: email, CONF_PASSWORD: password},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_SCHEMA,
                {CONF_EMAIL: (user_input or entry.data)[CONF_EMAIL]},
            ),
            errors=errors,
        )
