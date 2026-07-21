"""Unit tests for the CezHub helper (ean property, basic wiring).

These avoid any network access: the REST client is never called. We only test
the pure-Python properties of the hub that the sensor/calendar platforms read.
"""
from types import SimpleNamespace

from custom_components.cez_distribuce import CezData, CezHub


def _make_hub():
    """Build a CezHub without going through HA's async machinery."""
    hass = SimpleNamespace()
    return CezHub(
        hass=hass,
        username="u",
        password="p",
        scan_signals_min=360,
        scan_outages_min=360,
        scan_readings_min=1440,
    )


def test_cezhub_ean_property_returns_none_when_no_points():
    hub = _make_hub()
    # Without data, ean is None
    assert hub.ean is None


def test_cezhub_ean_property_returns_ean_from_first_point():
    hub = _make_hub()
    hub.points = [
        CezData(
            header={},
            supply_point={"uid": "U1"},
            supply_point_detail={"ean": "8591824001234567", "hdo": True},
            readings=[],
            signals={"signals": []},
            outages_for_ean=[],
        )
    ]
    assert hub.ean == "8591824001234567"


def test_cezhub_ean_property_returns_none_when_detail_has_no_ean():
    hub = _make_hub()
    hub.points = [
        CezData(
            header={},
            supply_point={"uid": "U1"},
            supply_point_detail={},
            readings=[],
            signals={"signals": []},
            outages_for_ean=[],
        )
    ]
    assert hub.ean is None


def test_cezhub_ean_property_returns_none_when_detail_is_none():
    """supply_point_detail may be None; the property guards with `or {}`."""
    hub = _make_hub()
    hub.points = [
        CezData(
            header={},
            supply_point={"uid": "U1"},
            supply_point_detail=None,
            readings=[],
            signals={"signals": []},
            outages_for_ean=[],
        )
    ]
    assert hub.ean is None


def test_cezhub_ean_property_swallows_exceptions_and_returns_none():
    """The try/except in the ean property must never raise to callers."""
    hub = _make_hub()

    # A points entry whose supply_point_detail raises on .get() (e.g. an int)
    class Boom:
        def __getattr__(self, item):
            raise RuntimeError("boom")

    hub.points = [Boom()]
    assert hub.ean is None


def test_cezhub_exposes_coordinator_attributes():
    """CezHub must expose the three coordinators the platforms bind to."""
    hub = _make_hub()
    # Before async_setup() they are None, but the attributes must exist.
    assert hasattr(hub, "signals_coordinator")
    assert hasattr(hub, "outages_coordinator")
    assert hasattr(hub, "readings_coordinator")
    assert hasattr(hub, "points")
    assert hasattr(hub, "hass")
