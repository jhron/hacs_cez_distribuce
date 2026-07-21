"""HA-style tests for setup / unload of the ČEZ Distribuce integration.

Drives the real ``async_setup_entry`` / ``async_unload_entry`` machinery with
the REST client monkeypatched, so the calendar and sensor platforms actually
get wired up and entities are created.

Entries are added directly to ``hass.config_entries`` (bypassing the user flow)
so the test does not depend on flow-level credential validation, which itself
needs a separate client mock.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from custom_components.cez_distribuce import DOMAIN, CezHub

# Sample portal data used to populate the hub without any network access.
SUPPLY_POINTS_PAYLOAD = {
    "vstelleBlocks": {
        "blocks": [
            {"vstelles": [{"uid": "U1", "ean": "8591824000000011"}]}
        ]
    }
}
DETAIL_PAYLOAD = {"ean": "8591824000000011", "hdo": True}
READINGS_PAYLOAD = [{"datumOdectu": "2025-01-01", "stavVt": 100.0, "stavNt": 50.0, "sernr": "S1"}]
SIGNALS_PAYLOAD = {"signals": [{"datum": "01.01.2025", "casy": "00:00 - 08:00", "nazevSignalu": "NT"}]}
OUTAGES_PAYLOAD = []


@pytest.fixture()
def mock_client():
    """A MagicMock REST client whose data methods return canned payloads.

    Patches ``CezDistribuceRestClient`` in the integration package so both
    CezHub (used during setup) and config_flow (used during validation) get
    the same fake instance.
    """
    client = MagicMock()
    client.login.return_value = None
    client.common_header.return_value = {"user": "test"}
    client.get_supply_points.return_value = SUPPLY_POINTS_PAYLOAD
    client.get_supply_point_detail.return_value = DETAIL_PAYLOAD
    client.get_readings.return_value = READINGS_PAYLOAD
    client.get_signals.return_value = SIGNALS_PAYLOAD
    client.get_outages.return_value = OUTAGES_PAYLOAD
    with patch(
        "custom_components.cez_distribuce.CezDistribuceRestClient",
        return_value=client,
    ), patch(
        "custom_components.cez_distribuce.config_flow.CezDistribuceRestClient",
        return_value=client,
    ):
        yield client


async def _add_loaded_entry(hass: HomeAssistant) -> ConfigEntry:
    """Add a config entry directly and run its setup. Returns the entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="ČEZ Distribuce (test-user)",
        data={CONF_USERNAME: "test-user", CONF_PASSWORD: "test-pass"},
        source="user",
        options={},
        unique_id="test-user",
        subentries_data=(),
        discovery_keys={},
    )
    hass.config_entries._entries[entry.entry_id] = entry
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_entry_loads_and_sets_up_platforms(
    hass: HomeAssistant, enable_custom_integrations, mock_client
):
    """async_setup_entry should load data and create calendar + sensor entities."""
    entry = await _add_loaded_entry(hass)

    assert entry.state is ConfigEntryState.LOADED

    # The hub is stored in hass.data under the entry id
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(hub, CezHub)
    assert hub.points, "static data should have populated hub.points"
    assert hub.ean == "8591824000000011"

    # The client should have been called for login + each data method
    mock_client.login.assert_called_once_with("test-user", "test-pass")
    mock_client.get_supply_points.assert_called_once()
    mock_client.get_supply_point_detail.assert_called_with("U1")
    mock_client.get_readings.assert_called_with("U1")
    mock_client.get_signals.assert_called_with("8591824000000011")
    mock_client.get_outages.assert_called_with(ean="8591824000000011")


async def test_setup_entry_creates_expected_entities(
    hass: HomeAssistant, enable_custom_integrations, mock_client
):
    """The calendar and sensor platforms should expose the right entities.

    Entity IDs derive from the Czech display names, so we assert on substrings
    rather than exact ids to stay robust to HA's slug normalization.
    """
    await _add_loaded_entry(hass)

    entity_ids = list(hass.states.async_entity_ids())
    # 2 calendars (outage + current signal)
    calendar_ids = [eid for eid in entity_ids if eid.startswith("calendar.")]
    sensor_ids = [eid for eid in entity_ids if eid.startswith("sensor.")]
    assert any("odstavky" in eid for eid in calendar_ids), calendar_ids
    assert any("hdo" in eid and "signal" in eid for eid in calendar_ids), calendar_ids
    # 3 sensors (VT, NT, total) for the one supply point
    vt_ids = [eid for eid in sensor_ids if "vt" in eid]
    nt_ids = [eid for eid in sensor_ids if "nt" in eid and "celkem" not in eid]
    total_ids = [eid for eid in sensor_ids if "celkem" in eid]
    assert vt_ids and nt_ids and total_ids, sensor_ids

    # Sensors should also carry the right numeric values from READINGS_PAYLOAD
    # (stavVt=100, stavNt=50 -> total=150).
    vt_state = hass.states.get(vt_ids[0])
    nt_state = hass.states.get(nt_ids[0])
    total_state = hass.states.get(total_ids[0])
    assert vt_state is not None and float(vt_state.state) == 100.0
    assert nt_state is not None and float(nt_state.state) == 50.0
    assert total_state is not None and float(total_state.state) == 150.0


async def test_unload_entry_removes_hub_data(
    hass: HomeAssistant, enable_custom_integrations, mock_client
):
    """async_unload_entry should clean up the hub from hass.data."""
    entry = await _add_loaded_entry(hass)
    entry_id = entry.entry_id

    ok = await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert ok is True
    assert entry.state is ConfigEntryState.NOT_LOADED
    # The per-entry hub is gone; the domain key may remain (empty) or be removed
    if DOMAIN in hass.data:
        assert entry_id not in hass.data[DOMAIN]


async def test_setup_entry_failure_surfaces_as_setup_error(
    hass: HomeAssistant, enable_custom_integrations, mock_client
):
    """If login fails during setup, the entry ends up in SETUP_RETRY/ERROR."""
    mock_client.login.side_effect = Exception("portal down")

    entry = await _add_loaded_entry(hass)

    # Login blew up inside _login_and_load_static -> async_setup raised
    assert entry.state in (ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_ERROR)
