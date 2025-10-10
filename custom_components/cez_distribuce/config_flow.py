"""Config Flow for ČEZ Distribuce integration.

This module implements the Home Assistant UI (Config Entries) flow allowing
users to add the integration by providing their ČEZ Distribuce credentials.
Credentials are validated by performing a lightweight login via the REST client
in a background executor thread. Common error codes are returned for HA to
render localized error messages.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_USERNAME, CONF_PASSWORD
from .rest_client.rest_client import CezDistribuceRestClient

_LOGGER = logging.getLogger(__name__)


DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
})


async def _validate_credentials(hass: HomeAssistant, username: str, password: str) -> Optional[str]:
    """Try to login using the REST client. Return None if OK, otherwise error code string."""
    def _blocking_test_login() -> Optional[str]:
        try:
            client = CezDistribuceRestClient()
            client.login(username, password)
            # fetch something lightweight to confirm
            client.common_header()
            return None
        except Exception as e:  # broad: external service may change
            msg = str(e).lower()
            _LOGGER.warning("Login validation failed: %s", e)
            # Heuristic: bad credentials vs connectivity
            if "401" in msg or "invalid" in msg or "unauthor" in msg:
                return "invalid_auth"
            return "cannot_connect"
    return await hass.async_add_executor_job(_blocking_test_login)


class CezDistribuceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        errors: Dict[str, str] = {}

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, "").strip()
            password = user_input.get(CONF_PASSWORD, "")

            error = await _validate_credentials(self.hass, username, password)
            if error is None:
                await self.async_set_unique_id(username)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"ČEZ Distribuce ({username})", data={
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                })
            errors["base"] = error

        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
