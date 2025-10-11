from types import SimpleNamespace

from custom_components.cez_distribuce.__init__ import CezHub


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



