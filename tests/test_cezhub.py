from types import SimpleNamespace

from custom_components.cez_distribuce.__init__ import CezHub, CezData


def test_cezhub_ean_property_returns_from_data():
    # Minimal dummy hass object
    hass = SimpleNamespace()

    hub = CezHub(
        hass=hass,
        username="u",
        password="p",
        scan_signals_min=360,
        scan_outages_min=360,
        scan_readings_min=1440,
    )

    # Without data, ean is None
    assert hub.ean is None

    # Populate minimal CezData
    hub.data = CezData(
        header={},
        supply_point={},
        supply_point_detail={"ean": "123456789012345678"},
        readings=[],
        signals={"signals": []},
        outages_for_ean=[],
    )

    assert hub.ean == "123456789012345678"


def test_cezhub_ean_property_handles_missing():
    hass = SimpleNamespace()
    hub = CezHub(hass, "u", "p", 1, 1, 1)

    # Data present but key missing -> property should catch and return None
    hub.data = CezData(
        header={},
        supply_point={},
        supply_point_detail={},
        readings=[],
        signals={"signals": []},
        outages_for_ean=[],
    )

    assert hub.ean is None
