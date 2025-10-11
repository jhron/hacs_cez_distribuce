from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CezHub
from .const import DOMAIN


def _extract_readings_list(data: Any) -> List[Dict[str, Any]]:
    """Return a flat list of reading dicts from coordinator data.

    Supports both legacy list form and the new dict form with a legacy
    compatibility key 'readings' populated by the hub.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        val = data.get("readings")
        if isinstance(val, list):
            return val
    return []


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[DOMAIN] else hass.data[DOMAIN]
    async_add_entities([
        CezReadingSensor(hub, "VT", "Poslední stav VT", "last_reading_vt"),
        CezReadingSensor(hub, "NT", "Poslední stav NT", "last_reading_nt"),
        CezTotalSensor(hub),
    ])


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        CezReadingSensor(hub, "VT", "Poslední stav VT", "last_reading_vt"),
        CezReadingSensor(hub, "NT", "Poslední stav NT", "last_reading_nt"),
        CezTotalSensor(hub),
    ])


def _latest_reading(readings: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not readings:
        return None
    # readings already appear sorted newest first; ensure by max on date
    try:
        return sorted(readings, key=lambda r: r.get("datumOdectu", ""), reverse=True)[0]
    except Exception:
        return readings[0]


class CezReadingSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, hub: CezHub, kind: str, name: str, unique_suffix: str) -> None:
        super().__init__(hub.readings_coordinator)
        self._hub = hub
        self._kind = kind  # "VT" or "NT"
        self._attr_name = name
        self._attr_unique_id = f"{hub.ean}_{unique_suffix}"
        self._attr_native_unit_of_measurement = "kWh"
        self._attr_device_class = "energy"
        self._attr_state_class = "total_increasing"

    @property
    def native_value(self) -> Optional[float]:
        readings = _extract_readings_list(self.coordinator.data)
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
        latest = _latest_reading(_extract_readings_list(self.coordinator.data)) or {}
        return {
            "ean": self._hub.ean,
            "serial": latest.get("sernr"),
            "date": latest.get("datumOdectu"),
            "reason": latest.get("duvodOdectuText"),
        }


class CezTotalSensor(CezReadingSensor):
    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub, "TOTAL", "Poslední stav celkem", "last_reading_total")

    @property
    def native_value(self) -> Optional[float]:
        readings = _extract_readings_list(self.coordinator.data)
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
