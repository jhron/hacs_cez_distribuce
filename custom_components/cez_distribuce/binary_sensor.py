from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from . import CezHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[DOMAIN] else hass.data[DOMAIN]
    entities: List[BinarySensorEntity] = [
        CezLowTariffBinarySensor(hub)
    ]
    async_add_entities(entities)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    entities: List[BinarySensorEntity] = [
        CezLowTariffBinarySensor(hub)
    ]
    async_add_entities(entities)


def _parse_time_ranges(casy: str) -> List[tuple]:
    res = []
    for part in casy.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            start_s, end_s = part.split("-")
            res.append((start_s.strip(), end_s.strip()))
        except Exception:
            continue
    return res


def _is_now_in_ranges(now: dt.datetime, ranges: List[tuple]) -> bool:
    for start_s, end_s in ranges:
        try:
            start = dt.time.fromisoformat(start_s)
            end = dt.time.fromisoformat(end_s)
            if start <= now.time() <= end:
                return True
        except Exception:
            continue
    return False


class CezLowTariffBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_name = "Nízký tarif"
    _attr_icon = "mdi:timer-outline"
    _attr_unique_id = "cez_distribuce_low_tariff"

    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.signals_coordinator)
        self._hub = hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.ean or "")},
            name="ČEZ Distribuce",
            manufacturer="ČEZ Distribuce",
            model=(hub.data.supply_point_detail.get("sazba") if hub.data else None) or "",
        )

    @property
    def is_on(self) -> bool:
        data: Dict[str, Any] = self.coordinator.data or {}
        signals: List[Dict[str, Any]] = data.get("signals", [])
        if not signals:
            return False
        today_str = dt.datetime.now().strftime("%d.%m.%Y")
        todays = [s for s in signals if s.get("datum") == today_str]
        if not todays:
            # fallback: take first
            todays = signals[:1]
        ranges: List[tuple] = []
        for s in todays:
            casy = s.get("casy", "")
            ranges.extend(_parse_time_ranges(casy))
        return _is_now_in_ranges(dt.datetime.now(), ranges)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        data: Dict[str, Any] = self.coordinator.data or {}
        return {
            "ean": self._hub.ean,
            "supply_point": (self._hub.data.supply_point if self._hub.data else {}),
            "signals_count": len(data.get("signals", [])),
        }
