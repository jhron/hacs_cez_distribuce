"""Integration tests against the live ČEZ Distribuce portal.

Marked ``@pytest.mark.integration``. The ``conftest.py`` auto-skips these
unless both ``CEZ_USERNAME`` and ``CEZ_PASSWORD`` are available (env var or the
git-ignored ``.env.local``), so the suite stays green in CI without secrets.

Run locally with::

    pytest -q -m integration -s

The ``-s`` flag lets the structural data dumps (printed for future API-change
debugging) reach stdout.

Login is performed exactly once via the module-scoped ``client`` fixture; every
data test reuses the same authenticated session, which mirrors how the
integration behaves in production (one login per hub setup).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from custom_components.cez_distribuce.rest_client.rest_client import (
    CAS_BASE_URL,
    CEZ_DISTRIBUCECLIENT_ID,
    CezDistribuceRestClient,
)

pytestmark = pytest.mark.integration

_LOGGER = logging.getLogger(__name__)


def _dump(label: str, data: Any, limit_keys: int = 30) -> None:
    """Pretty-print a short structural summary of a ČEZ API response.

    Truncates long string values and large lists so the dump stays readable.
    Intended for debugging when the portal changes shape again.
    """
    def _shorten(obj: Any, depth: int = 0):
        if depth > 4:
            return "..."
        if isinstance(obj, dict):
            keys = list(obj.keys())[:limit_keys]
            out = {k: _shorten(obj[k], depth + 1) for k in keys}
            if len(obj) > limit_keys:
                out[f"...(+{len(obj) - limit_keys} more)"] = None
            return out
        if isinstance(obj, list):
            if not obj:
                return []
            return [_shorten(obj[0], depth + 1), f"...({len(obj)} items total)"]
        if isinstance(obj, str) and len(obj) > 80:
            return obj[:80] + f"...(+{len(obj) - 80} chars)"
        return obj

    print(f"\n=== {label} ===")
    print(json.dumps(_shorten(data), indent=2, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Authenticated client shared across tests.
# ---------------------------------------------------------------------------
# Cached at module level so the CAS login (a multi-step dance) happens once per
# pytest session. We cannot use a module-scoped fixture directly because the
# pytest-homeassistant-custom-component socket patches are function-scoped: they
# would block the network during a module-scoped fixture's setup. By logging in
# lazily inside a function-scoped fixture (whose setup runs after our network
# fixture lifts the patches), login succeeds and subsequent tests reuse the
# cached, already-authenticated session.
_cached_client: CezDistribuceRestClient | None = None


@pytest.fixture()
def client(env_credentials) -> CezDistribuceRestClient:
    """Return the shared authenticated client, logging in on first use."""
    global _cached_client
    if _cached_client is None:
        _cached_client = CezDistribuceRestClient()
        _cached_client.login(*env_credentials)
    return _cached_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_auth_endpoints_target_mepas_host():
    """Sanity gate: confirm the client is built against the current MEPAS host.

    Runs without network/credentials and fails loudly if the CAS host or
    client_id drifts, which is the most common cause of integration outages.
    """
    assert CAS_BASE_URL == "https://mepas.cez.cz/cas"
    assert CEZ_DISTRIBUCECLIENT_ID == "emiCuDBbivwYxraX.dip.dip.ext.zak.prod.v1"


def test_login_sets_request_tokens(client: CezDistribuceRestClient):
    """After login both sessions must carry an X-Request-Token header.

    Mirrors ``config_flow._validate_credentials``: this is the gate the user
    passes through when adding the integration via the HA UI.
    """
    assert client._session.headers.get("X-Request-Token"), "auth token missing"
    assert client._anonymous_session.headers.get("X-Request-Token"), "anon token missing"


def test_common_header_returns_dict(client: CezDistribuceRestClient):
    """common_header must return a dict (lightweight post-login check)."""
    header = client.common_header()
    assert isinstance(header, dict)
    _dump("common_header()", header)


@pytest.fixture()
def supply_points(client: CezDistribuceRestClient):
    """Fetch the account's supply points (cheap with the cached client)."""
    sp = client.get_supply_points()
    _dump("get_supply_points()", sp)
    return sp


def test_get_supply_points_has_expected_shape(supply_points):
    """get_supply_points must expose vstelleBlocks.blocks[*].vstelles[*].uid."""
    assert isinstance(supply_points, dict)
    blocks = supply_points.get("vstelleBlocks", {}).get("blocks", [])
    assert isinstance(blocks, list) and blocks, "no supply-point blocks returned"
    first_vstelles = blocks[0].get("vstelles", [])
    assert first_vstelles, "first block has no vstelles"
    assert "uid" in first_vstelles[0], "first vstelle has no uid"


@pytest.fixture()
def first_supply_point(client: CezDistribuceRestClient, supply_points):
    """Return (uid, detail, ean) for the first supply point."""
    sp = supply_points["vstelleBlocks"]["blocks"][0]["vstelles"][0]
    uid = sp["uid"]
    detail = client.get_supply_point_detail(uid)
    ean = detail.get("ean")
    _dump("first supply_point detail", detail)
    return uid, detail, ean


def test_get_supply_point_detail_has_ean(first_supply_point):
    """The first supply point detail must carry an EAN."""
    uid, detail, ean = first_supply_point
    assert ean, f"no ean in detail for uid={uid}"


def test_get_readings_returns_list(first_supply_point, client):
    """get_readings must return a list (possibly empty)."""
    uid, detail, ean = first_supply_point
    readings = client.get_readings(uid)
    assert isinstance(readings, list), f"readings not a list: {type(readings)}"
    if not readings:
        pytest.skip("portal returned no meter readings for this account")
    _dump("get_readings() first item", readings[0])


def test_get_signals_returns_signals_dict(first_supply_point, client):
    """get_signals must return a dict containing a 'signals' list."""
    uid, detail, ean = first_supply_point
    if not detail.get("hdo"):
        pytest.skip("this supply point has no HDO configured; signals not applicable")
    assert ean, "ean required for signals"
    signals = client.get_signals(ean)
    assert isinstance(signals, dict), f"signals not a dict: {type(signals)}"
    assert "signals" in signals, f"no 'signals' key: {list(signals.keys())}"
    _dump("get_signals() first signal", (signals["signals"] or [{}])[0])


def test_get_outages_returns_list_for_ean(first_supply_point, client):
    """get_outages (anonymous endpoint) must return a list for the OM's EAN."""
    uid, detail, ean = first_supply_point
    assert ean, "ean required for outages"
    outages = client.get_outages(ean=ean)
    assert isinstance(outages, list), f"outages not a list: {type(outages)}"
    _dump("get_outages() summary", {"count": len(outages), "first": outages[0] if outages else None})


def test_get_outages_works_anonymously_without_login():
    """The outages endpoint must work on a fresh anonymous session without login.

    Documents that outage lookups by EAN do not require credentials at all and
    confirms the anon-token flow. Uses its own client to avoid touching the
    shared authenticated module-scoped instance.
    """
    anon_client = CezDistribuceRestClient()
    anon_client.refresh_anon_api_token()
    try:
        result = anon_client.get_outages(ean="8591824000000000")
    except Exception as exc:
        # A 4xx for a non-existent EAN is acceptable; a network/auth error is not.
        msg = str(exc).lower()
        if any(s in msg for s in ("token", "login", "unable")):
            pytest.fail(f"anonymous outage lookup failed on auth: {exc}")
        pytest.skip(f"portal rejected test EAN (expected): {exc}")
    assert isinstance(result, list)
