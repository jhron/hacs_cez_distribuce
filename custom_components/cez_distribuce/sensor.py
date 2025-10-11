from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CezHub
from .const import DOMAIN


def _extract_readings_list(data: Any, uid: Optional[str]) -> List[Dict[str, Any]]:
    """Return a flat list of reading dicts for given UID from coordinator data.

    Expects coordinator.data to be a dict keyed by UID -> list of readings.
    """
    if not isinstance(data, dict) or not uid:
        return []
    val = data.get(uid)
    return val if isinstance(val, list) else []


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[
        DOMAIN] else hass.data[DOMAIN]
    entities = []
    for p in getattr(hub, "points", []) or []:
        ean = (p.supply_point_detail or {}).get("ean")
        uid = (p.supply_point or {}).get("uid")
        if not uid:
            continue
        name_suffix = f" – EAN {ean}" if ean else ""
        entities.append(CezReadingSensor(hub, uid, ean, "VT", f"Poslední stav VT{name_suffix}", "last_reading_vt"))
        entities.append(CezReadingSensor(hub, uid, ean, "NT", f"Poslední stav NT{name_suffix}", "last_reading_nt"))
        entities.append(CezTotalSensor(hub, uid, ean))
    async_add_entities(entities)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for p in getattr(hub, "points", []) or []:
        ean = (p.supply_point_detail or {}).get("ean")
        uid = (p.supply_point or {}).get("uid")
        if not uid:
            continue
        # Enhance names with EAN for clarity
        name_suffix = f" – EAN {ean}" if ean else ""
        entities.append(CezReadingSensor(hub, uid, ean, "VT", f"Poslední stav VT{name_suffix}", "last_reading_vt"))
        entities.append(CezReadingSensor(hub, uid, ean, "NT", f"Poslední stav NT{name_suffix}", "last_reading_nt"))
        entities.append(CezTotalSensor(hub, uid, ean))
    async_add_entities(entities)


def _latest_reading(readings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not readings:
        return None
    # readings already appear sorted newest first; ensure by max on date
    try:
        return sorted(readings, key=lambda r: r.get("datumOdectu", ""), reverse=True)[0]
    except Exception:
        return readings[0]


class CezReadingSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, hub: CezHub, uid: str, ean: Optional[str], kind: str, name: str, unique_suffix: str) -> None:
        super().__init__(hub.readings_coordinator)
        self._hub = hub
        self._uid = uid
        self._ean = ean
        self._kind = kind  # "VT" or "NT"
        self._attr_name = name
        base = ean or uid
        self._attr_unique_id = f"{base}_{unique_suffix}"

    @property
    def native_value(self) -> Optional[float]:
        readings = _extract_readings_list(self.coordinator.data, self._uid)
        latest = _latest_reading(readings)
        if not latest:
            return None
        key = "stavVt" if self._kind == "VT" else "stavNt"
        try:
            val = float(str(latest.get(key, "0")).strip())
            return round(val, 3)
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        latest = _latest_reading(_extract_readings_list(self.coordinator.data, self._uid)) or {}
        return {
            "ean": self._ean,
            "uid": self._uid,
            "serial": latest.get("sernr"),
            "date": latest.get("datumOdectu"),
            "reason": latest.get("duvodOdectuText"),
        }


class CezTotalSensor(CezReadingSensor):
    def __init__(self, hub: CezHub, uid: str, ean: Optional[str]) -> None:
        name = f"Poslední stav celkem{' – EAN ' + ean if ean else ''}"
        super().__init__(hub, uid, ean, "TOTAL", name, "last_reading_total")

    @property
    def native_value(self) -> Optional[float]:
        readings = _extract_readings_list(self.coordinator.data, self._uid)
        latest = _latest_reading(readings)
        if not latest:
            return None
        try:
            vt = float(str(latest.get("stavVt", "0")).strip())
        except Exception:
            vt = 0.0
        try:
            nt = float(str(latest.get("stavNt", "0")).strip())
        except Exception:
            nt = 0.0
        return round(vt + nt, 3)
