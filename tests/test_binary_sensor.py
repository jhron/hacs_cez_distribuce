"""Unit tests for the ČEZ Distribuce binary_sensor entities.

Both entities derive their state from the (static) supply-point detail, so the
tests use lightweight dummy hubs without a coordinator or HA runtime.
"""
from __future__ import annotations

from types import SimpleNamespace

from custom_components.cez_distribuce import CezData
from custom_components.cez_distribuce.binary_sensor import (
    CezContractActiveBinarySensor,
    CezOutageActiveBinarySensor,
)

UID = "U1"
EAN = "859182400607292391"


class DummyHub(SimpleNamespace):
    pass


def _hub(detail: dict) -> DummyHub:
    return DummyHub(points=[CezData(
        header={},
        supply_point={"uid": UID},
        supply_point_detail=detail,
        readings=[],
        signals={"signals": []},
        outages_for_ean=[],
    )])


# ---------------------------------------------------------------------------
# CezOutageActiveBinarySensor
# ---------------------------------------------------------------------------

def test_outage_active_sensor_off_when_no_outage():
    sensor = CezOutageActiveBinarySensor(_hub({"probihajiciOdstavka": False}), UID, EAN)
    assert sensor.is_on is False


def test_outage_active_sensor_on_when_outage_in_progress():
    sensor = CezOutageActiveBinarySensor(_hub({"probihajiciOdstavka": True}), UID, EAN)
    assert sensor.is_on is True


def test_outage_active_sensor_off_when_field_missing():
    sensor = CezOutageActiveBinarySensor(_hub({}), UID, EAN)
    assert sensor.is_on is False


def test_outage_active_sensor_exposes_ean_and_uid():
    sensor = CezOutageActiveBinarySensor(_hub({"probihajiciOdstavka": False}), UID, EAN)
    attrs = sensor.extra_state_attributes
    assert attrs["ean"] == EAN
    assert attrs["uid"] == UID


def test_outage_active_sensor_has_problem_device_class():
    from homeassistant.components.binary_sensor import BinarySensorDeviceClass
    sensor = CezOutageActiveBinarySensor(_hub({}), UID, EAN)
    assert sensor.device_class is BinarySensorDeviceClass.PROBLEM


# ---------------------------------------------------------------------------
# CezContractActiveBinarySensor
# ---------------------------------------------------------------------------

def test_contract_active_sensor_on_when_aktiv():
    sensor = CezContractActiveBinarySensor(
        _hub({"stavSmlouvyDistribuce": "AKTIV", "stavSmlouvyDistribuceTxt": "Aktivní"}),
        UID, EAN,
    )
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["stav_text"] == "Aktivní"


def test_contract_active_sensor_off_when_not_aktiv():
    sensor = CezContractActiveBinarySensor(
        _hub({"stavSmlouvyDistribuce": "UKONCENO", "stavSmlouvyDistribuceTxt": "Ukončené"}),
        UID, EAN,
    )
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["stav_text"] == "Ukončené"


def test_contract_active_sensor_off_when_field_missing():
    sensor = CezContractActiveBinarySensor(_hub({}), UID, EAN)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["stav_text"] is None


def test_contract_active_sensor_no_device_class():
    """No device_class: 'running' reads poorly for a contract status."""
    sensor = CezContractActiveBinarySensor(_hub({}), UID, EAN)
    assert sensor.device_class is None
