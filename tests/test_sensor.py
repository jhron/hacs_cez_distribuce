"""Unit tests for the ČEZ Distribuce sensor entities.

Covers the new detail-derived sensors (week-of-reading, tariff) and the
extended reading-sensor attributes, using lightweight dummy hubs so no HA
runtime is required.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.cez_distribuce import CezData
from custom_components.cez_distribuce.sensor import (
    CezReadingSensor,
    CezTariffSensor,
    CezTotalSensor,
    CezWeekReadingSensor,
    _as_int,
    _current_tariff_slice,
    _iso_date,
    _last_read_date,
)


class DummyReadingsCoordinator:
    """Minimal stand-in for the readings DataUpdateCoordinator."""

    def __init__(self, data):
        self.data = data

    def async_add_listener(self, update_callback, context=None):
        return lambda: None


class DummyHub(SimpleNamespace):
    pass


UID = "U1"
EAN = "859182400607292391"


def _make_point(detail: dict, readings=None) -> CezData:
    return CezData(
        header={},
        supply_point={"uid": UID},
        supply_point_detail=detail,
        readings=readings if readings is not None else [],
        signals={"signals": []},
        outages_for_ean=[],
    )


def _hub(detail: dict, readings=None) -> DummyHub:
    return DummyHub(points=[_make_point(detail, readings)])


# ---------------------------------------------------------------------------
# CezWeekReadingSensor
# ---------------------------------------------------------------------------

def test_week_reading_sensor_returns_week_number():
    detail = {"anlage_Dist": {"tydenOdectu": 23, "tydenOdectuFormatted": "23 (01.06.2026 - 07.06.2026)",
                              "cislo": "0004381597", "sazba": "D57D", "distributor": "CEZ-DI",
                              "distributorTxt": "ČEZ Distribuce", "mesicOdectu": 0}}
    sensor = CezWeekReadingSensor(_hub(detail), UID, EAN)
    assert sensor.native_value == 23
    attrs = sensor.extra_state_attributes
    assert attrs["interval"] == "23 (01.06.2026 - 07.06.2026)"
    assert attrs["mesic_odectu"] == 0
    assert attrs["cislo_smlouvy"] == "0004381597"
    assert attrs["sazba"] == "D57D"
    assert attrs["distributor"] == "ČEZ Distribuce"


def test_week_reading_sensor_returns_none_when_missing():
    sensor = CezWeekReadingSensor(_hub({}), UID, EAN)
    assert sensor.native_value is None


def test_week_reading_sensor_returns_none_when_anlage_missing():
    sensor = CezWeekReadingSensor(_hub({"anlage_Dist": None}), UID, EAN)
    assert sensor.native_value is None


def test_week_reading_sensor_handles_string_value():
    """Portal may return tydenOdectu as a numeric string."""
    sensor = CezWeekReadingSensor(_hub({"anlage_Dist": {"tydenOdectu": "42"}}), UID, EAN)
    assert sensor.native_value == 42


# ---------------------------------------------------------------------------
# CezTariffSensor
# ---------------------------------------------------------------------------

# The portal's casoveRezy list is NOT chronologically ordered. The current
# tariff is the slice with the newest sazbaDistribuceOd.
TARIFF_DETAIL = {
    "faktaOM": {
        "napetovaHladina": "NN",
        "typMereni": "C",
        "jisticCharakteristika": "B",
        "casoveRezy": [
            # Historically newer (D57D, 2019) — this is the CURRENT tariff.
            {"sazbaDistribuce": "D57D", "sazbaDistribuceOd": "2019-05-27T00:00:00",
             "hlavniJistic": 40.0, "pocetFazi": 3.0, "typMereni": "C", "typOdberu": "T"},
            # Older (D25D, 2008).
            {"sazbaDistribuce": "D25D", "sazbaDistribuceOd": "2008-09-26T00:00:00",
             "hlavniJistic": 25.0, "pocetFazi": 3.0, "typMereni": "C", "typOdberu": "T"},
        ],
    }
}


def test_tariff_sensor_picks_current_slice_despite_unsorted_list():
    sensor = CezTariffSensor(_hub(TARIFF_DETAIL), UID, EAN)
    # Current tariff is D57D (2019), NOT D25D (2008) even though D57D is first.
    assert sensor.native_value == "D57D"
    attrs = sensor.extra_state_attributes
    assert attrs["hlavni_jistic"] == 40  # int, not 40.0 float
    assert attrs["pocet_fazi"] == 3
    assert attrs["typ_mereni"] == "C"
    assert attrs["typ_odberu"] == "T"
    assert attrs["platnost_od"] == "2019-05-27"
    assert attrs["napetova_hladina"] == "NN"
    assert attrs["jistic_charakteristika"] == "B"


def test_tariff_sensor_returns_none_when_no_slices():
    sensor = CezTariffSensor(_hub({"faktaOM": {"casoveRezy": []}}), UID, EAN)
    assert sensor.native_value is None


def test_tariff_sensor_returns_none_when_fakta_missing():
    sensor = CezTariffSensor(_hub({}), UID, EAN)
    assert sensor.native_value is None


def test_tariff_sensor_picks_correct_slice_when_sorted_ascending():
    """Also works when the list happens to be oldest-first."""
    detail = {"faktaOM": {"casoveRezy": [
        {"sazbaDistribuce": "OLD", "sazbaDistribuceOd": "2008-01-01T00:00:00", "hlavniJistic": 16},
        {"sazbaDistribuce": "NEW", "sazbaDistribuceOd": "2020-01-01T00:00:00", "hlavniJistic": 40},
    ]}}
    sensor = CezTariffSensor(_hub(detail), UID, EAN)
    assert sensor.native_value == "NEW"
    assert sensor.extra_state_attributes["hlavni_jistic"] == 40


# ---------------------------------------------------------------------------
# _current_tariff_slice helper
# ---------------------------------------------------------------------------

def test_current_tariff_slice_returns_max_by_sazba_od():
    slices = [
        {"sazbaDistribuce": "A", "sazbaDistribuceOd": "2019-05-27T00:00:00"},
        {"sazbaDistribuce": "B", "sazbaDistribuceOd": "2008-09-26T00:00:00"},
    ]
    detail = {"faktaOM": {"casoveRezy": slices}}
    assert _current_tariff_slice(detail)["sazbaDistribuce"] == "A"


def test_current_tariff_slice_returns_none_for_empty():
    assert _current_tariff_slice({}) is None
    assert _current_tariff_slice({"faktaOM": {}}) is None
    assert _current_tariff_slice({"faktaOM": {"casoveRezy": []}}) is None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def test_as_int_handles_floats_strings_and_invalid():
    assert _as_int(40.0) == 40
    assert _as_int(3.0) == 3
    assert _as_int("25") == 25
    assert _as_int("25.9") == 25  # truncates, matching portal semantics for amps/phases
    assert _as_int(None) is None
    assert _as_int("abc") is None


def test_iso_date_strips_time_component():
    assert _iso_date("2026-06-30T00:00:00") == "2026-06-30"
    assert _iso_date("2026-06-30") == "2026-06-30"
    assert _iso_date(None) is None
    assert _iso_date("") is None
    assert _iso_date(123) is None  # non-string is ignored


def test_last_read_date_prefers_fakta():
    detail = {"faktaOM": {"datumPoslednihoOdectu": "2026-06-30T00:00:00"},
              "elektromery": [{"lastReadDate": "2026-05-31T00:00:00"}]}
    assert _last_read_date(detail) == "2026-06-30"


def test_last_read_date_falls_back_to_elektromery():
    detail = {"faktaOM": {}, "elektromery": [{"lastReadDate": "2026-05-31T00:00:00"}]}
    assert _last_read_date(detail) == "2026-05-31"


def test_last_read_date_returns_none_when_nothing_available():
    assert _last_read_date({}) is None


# ---------------------------------------------------------------------------
# CezReadingSensor extended attributes
# ---------------------------------------------------------------------------

READING_PAYLOAD = [
    {"datumOdectu": "2026-06-30", "stavVt": "100.0", "stavNt": "50.0", "sernr": "S1",
     "duvodOdectuText": "Kontrolní odečet"},
]
READINGS_COORD_DATA = {UID: READING_PAYLOAD}


def _readings_hub(detail: dict) -> DummyHub:
    hub = _hub(detail, readings=READING_PAYLOAD)
    hub.readings_coordinator = DummyReadingsCoordinator(READINGS_COORD_DATA)
    return hub


def test_reading_sensor_exposes_last_read_date_attribute():
    detail = {"faktaOM": {"datumPoslednihoOdectu": "2026-06-30T00:00:00"}}
    sensor = CezReadingSensor(_readings_hub(detail), UID, EAN, "VT", "VT", "vt")
    attrs = sensor.extra_state_attributes
    assert attrs["datum_posledniho_odectu"] == "2026-06-30"
    # Existing attributes still present
    assert attrs["serial"] == "S1"
    assert attrs["reason"] == "Kontrolní odečet"
    assert attrs["ean"] == EAN


def test_reading_sensor_last_read_date_none_when_detail_empty():
    sensor = CezReadingSensor(_readings_hub({}), UID, EAN, "VT", "VT", "vt")
    assert sensor.extra_state_attributes["datum_posledniho_odectu"] is None


def test_reading_sensor_parses_string_with_leading_spaces():
    """Portal returns stavVt/stavNt as strings with leading whitespace."""
    readings = {UID: [{"datumOdectu": "2026-06-30",
                       "stavVt": "            2865.00000000000000",
                       "stavNt": "           12388.00000000000000"}]}
    hub = _hub({})
    hub.readings_coordinator = DummyReadingsCoordinator(readings)
    vt = CezReadingSensor(hub, UID, EAN, "VT", "VT", "vt")
    nt = CezReadingSensor(hub, UID, EAN, "NT", "NT", "nt")
    total = CezTotalSensor(hub, UID, EAN)
    assert vt.native_value == 2865.0
    assert nt.native_value == 12388.0
    assert total.native_value == round(2865.0 + 12388.0, 3)
