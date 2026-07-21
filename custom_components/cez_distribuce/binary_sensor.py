"""Binary sensor platform for the ČEZ Distribuce integration.

Exposes simple on/off states derived from the (already-fetched) supply-point
detail, so no additional HTTP request is needed:

* ``binary_sensor.cez_odstavka_prubezi`` – whether an outage is currently in
  progress for the OM (``probihajiciOdstavka``). Complements the planned
  outages calendar, which shows future windows.
* ``binary_sensor.cez_smlouva_aktivni`` – whether the distribution contract is
  active (``stavSmlouvyDistribuce == "AKTIV"``). Useful as a health signal.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity

from . import CezHub
from .const import DOMAIN


def _detail_for_uid(hub: CezHub, uid: Optional[str]) -> Dict[str, Any]:
    """Return the supply_point_detail dict for the given UID, or {}."""
    if not uid:
        return {}
    for p in getattr(hub, "points", []) or []:
        if (p.supply_point or {}).get("uid") == uid:
            return p.supply_point_detail or {}
    return {}


def _detail_for_ean(hub: CezHub, ean: Optional[str]) -> Dict[str, Any]:
    """Return the supply_point_detail dict for the given EAN, or {}."""
    if not ean:
        return {}
    for p in getattr(hub, "points", []) or []:
        if (p.supply_point_detail or {}).get("ean") == ean:
            return p.supply_point_detail or {}
    return {}


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[
        DOMAIN] else hass.data[DOMAIN]
    entities: list[Entity] = []
    for p in getattr(hub, "points", []) or []:
        ean = (p.supply_point_detail or {}).get("ean")
        uid = (p.supply_point or {}).get("uid")
        if not uid:
            continue
        entities.append(CezOutageActiveBinarySensor(hub, uid, ean))
        entities.append(CezContractActiveBinarySensor(hub, uid, ean))
    async_add_entities(entities)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    entities: list[Entity] = []
    for p in getattr(hub, "points", []) or []:
        ean = (p.supply_point_detail or {}).get("ean")
        uid = (p.supply_point or {}).get("uid")
        if not uid:
            continue
        entities.append(CezOutageActiveBinarySensor(hub, uid, ean))
        entities.append(CezContractActiveBinarySensor(hub, uid, ean))
    async_add_entities(entities)


class CezDetailBinarySensor(BinarySensorEntity):
    """Base binary sensor reading a static flag from the supply-point detail.

    The detail is loaded once during hub setup; these entities therefore expose
    ``should_poll = False`` and reflect whatever was fetched at startup. Restart
    Home Assistant (or reload the integration) to pick up changes.
    """

    _attr_should_poll = False

    def __init__(self, hub: CezHub, uid: str, ean: Optional[str], name: str, unique_suffix: str) -> None:
        self._hub = hub
        self._uid = uid
        self._ean = ean
        self._attr_name = name
        base = ean or uid
        self._attr_unique_id = f"{base}_{unique_suffix}"

    @property
    def detail(self) -> Dict[str, Any]:
        return _detail_for_uid(self._hub, self._uid)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"ean": self._ean, "uid": self._uid}


class CezOutageActiveBinarySensor(CezDetailBinarySensor):
    """``on`` while a distribution outage is currently in progress."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hub: CezHub, uid: str, ean: Optional[str]) -> None:
        super().__init__(hub, uid, ean, "ČEZ Odstávka právě probíhá", "outage_active")

    @property
    def is_on(self) -> bool:
        return bool(self.detail.get("probihajiciOdstavka"))


class CezContractActiveBinarySensor(CezDetailBinarySensor):
    """``on`` when the distribution contract is in the AKTIV state."""

    # No device_class: default plain "on/off" reads better than "Running/Not
    # running" for a contract status.

    def __init__(self, hub: CezHub, uid: str, ean: Optional[str]) -> None:
        super().__init__(hub, uid, ean, "ČEZ Smlouva aktivní", "contract_active")

    @property
    def is_on(self) -> bool:
        return self.detail.get("stavSmlouvyDistribuce") == "AKTIV"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        attrs = super().extra_state_attributes
        attrs["stav_text"] = self.detail.get("stavSmlouvyDistribuceTxt")
        return attrs
