"""HA-style config-flow tests for the ČEZ Distribuce integration.

These use the standard ``pytest-homeassistant-custom-component`` fixtures
(``hass``, ``enable_custom_integrations``) and drive the real
``config_entries.flow`` machinery. The network layer (``CezDistribuceRestClient``)
is monkeypatched so no real portal contact happens.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.cez_distribuce import DOMAIN
from custom_components.cez_distribuce.const import CONF_PASSWORD, CONF_USERNAME


@pytest.fixture(autouse=True)
def _mock_validate_credentials():
    """Patch the REST client used by config_flow so tests stay offline.

    Individual tests override ``side_effect`` on the returned mock to model
    success / invalid_auth / cannot_connect.
    """
    fake_client = MagicMock()
    fake_client.login.return_value = None
    fake_client.common_header.return_value = {"ok": True}

    # Patch the symbol as imported inside config_flow.py
    with patch(
        "custom_components.cez_distribuce.config_flow.CezDistribuceRestClient",
        return_value=fake_client,
    ) as patched:
        yield patched, fake_client


async def test_form_success_creates_entry(
    hass: HomeAssistant, enable_custom_integrations
):
    """A successful login creates a config entry with the right data."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"},
    )
    await hass.async_block_till_done()

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "ČEZ Distribuce (test-user)"
    assert result["data"] == {CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"}


async def test_form_invalid_auth_shows_error(
    hass: HomeAssistant, enable_custom_integrations, _mock_validate_credentials
):
    """Bad credentials surface as the localized 'invalid_auth' error."""
    _, fake_client = _mock_validate_credentials
    fake_client.login.side_effect = Exception("HTTP 401 unauthorized")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "bad-user", CONF_PASSWORD: "bad-pass"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_cannot_connect_shows_error(
    hass: HomeAssistant, enable_custom_integrations, _mock_validate_credentials
):
    """Connectivity / unknown failures surface as 'cannot_connect'."""
    _, fake_client = _mock_validate_credentials
    fake_client.login.side_effect = Exception("connection reset by peer")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "any-user", CONF_PASSWORD: "any-pass"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_form_strips_username_whitespace(
    hass: HomeAssistant, enable_custom_integrations, _mock_validate_credentials
):
    """Username is stripped before being stored (config_flow strips it)."""
    _, fake_client = _mock_validate_credentials

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "  spaced-user  ", CONF_PASSWORD: "pass"},
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USERNAME] == "spaced-user"
    # And the client was called with the stripped username
    fake_client.login.assert_called_once_with("spaced-user", "pass")


async def test_unique_id_aborts_on_reconfigure(
    hass: HomeAssistant, enable_custom_integrations
):
    """Adding the same username twice aborts the second flow."""
    # First entry succeeds
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_USERNAME: "dup-user", CONF_PASSWORD: "pass"},
    )
    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY

    # Second flow with the same username aborts
    result2 = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_USERNAME: "dup-user", CONF_PASSWORD: "pass"},
    )
    assert result2["type"] is data_entry_flow.FlowResultType.ABORT
    assert result2["reason"] == "already_configured"
