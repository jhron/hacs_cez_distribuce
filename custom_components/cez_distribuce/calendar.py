from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CezHub
from .const import DOMAIN


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[DOMAIN] else hass.data[DOMAIN]
    async_add_entities([
        CezTariffCalendar(hub),
        CezOutageCalendar(hub),
    ])


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        CezTariffCalendar(hub),
        CezOutageCalendar(hub),
    ])


class CezTariffCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.signals_coordinator)
        self._hub = hub
        self._attr_name = "HDO – nízký tarif"
        self._attr_unique_id = f"{hub.ean}_hdo_calendar"

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        signals: List[Dict[str, Any]] = data.get("signals", [])
        events: List[CalendarEvent] = []
        for s in signals:
            date_str = s.get("datum")  # e.g., '10.10.2025'
            if not date_str:
                continue
            # parse date
            try:
                day = dt.datetime.strptime(date_str, "%d.%m.%Y")
            except Exception:
                continue
            casy = s.get("casy", "")
            for part in [p.strip() for p in casy.split(";") if p.strip()]:
                try:
                    start_s, end_s = [x.strip() for x in part.split("-")]
                    start_dt = dt.datetime.combine(day.date(), dt.time.fromisoformat(start_s))
                    end_dt = dt.datetime.combine(day.date(), dt.time.fromisoformat(end_s))
                except Exception:
                    continue
                if end_dt < start_date or start_dt > end_date:
                    continue
                ev = CalendarEvent(
                    summary="Nízký tarif",
                    start=start_dt,
                    end=end_dt,
                    description=f"Signal {s.get('signal','')} – {s.get('den','')}",
                )
                events.append(ev)
        return events


class CezOutageCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.outages_coordinator)
        self._hub = hub
        self._attr_name = "ČEZ Odstávky"
        self._attr_unique_id = f"{hub.ean}_outages_calendar"

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[CalendarEvent]:
        outages: List[Dict[str, Any]] = self.coordinator.data or []
        events: List[CalendarEvent] = []
        for o in outages:
            try:
                date_val = o.get("dateFormatted") or o.get("date")
                if not date_val:
                    continue
                if "." in date_val:
                    # dateFormatted like '29.10.2025'
                    day = dt.datetime.strptime(date_val, "%d.%m.%Y")
                else:
                    # ISO date '2025-10-29T00:00:00'
                    day = dt.datetime.fromisoformat(date_val)
                time_fmt = o.get("timeFormatted") or "00:00 - 23:59"
                start_s, end_s = [x.strip() for x in time_fmt.replace("–", "-").split("-")]
                start_dt = dt.datetime.combine(day.date(), dt.time.fromisoformat(start_s))
                end_dt = dt.datetime.combine(day.date(), dt.time.fromisoformat(end_s))
            except Exception:
                continue
            if end_dt < start_date or start_dt > end_date:
                continue
            number = o.get("number", "")
            summary = f"Odstávka {number}" if number else "Odstávka"
            desc = []
            for p in (o.get("sortedParts") or o.get("parts") or []):
                desc.append(p.get("description", ""))
            events.append(CalendarEvent(summary=summary, start=start_dt, end=end_dt, description="; ".join(desc)))
        return events
