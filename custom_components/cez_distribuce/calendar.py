from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CezHub
from .const import DOMAIN


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    # Legacy YAML path
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[DOMAIN] else hass.data[DOMAIN]
    async_add_entities([
        CezTariffCalendar(hub),
        CezOutageCalendar(hub),
        CezCurrentSignalCalendar(hub),
    ])


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        CezTariffCalendar(hub),
        CezOutageCalendar(hub),
        CezCurrentSignalCalendar(hub),
    ])


class CezTariffCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.signals_coordinator)
        self._hub = hub
        self._attr_name = "HDO – nízký tarif"
        self._attr_unique_id = f"{hub.ean}_hdo_calendar"

    @property
    def event(self) -> Optional[CalendarEvent]:
        # Minimal implementation to satisfy CalendarEntity API.
        # We return None so the entity reports state "off" by default.
        # The full list of events is provided via async_get_events.
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        signals: List[Dict[str, Any]] = data.get("signals", [])

        # 1) Parse and normalize all raw intervals into tz-aware datetimes
        intervals: List[Tuple[dt.datetime, dt.datetime]] = []
        for s in signals:
            date_str = s.get("datum")  # e.g., '10.10.2025'
            if not date_str:
                continue
            try:
                day = dt.datetime.strptime(date_str, "%d.%m.%Y")
            except Exception:
                continue
            casy = s.get("casy", "")
            for part in [p.strip() for p in casy.split(";") if p.strip()]:
                try:
                    start_s, end_s = [x.strip() for x in part.split("-")]
                    sdt = dt.datetime.combine(day.date(), dt.time.fromisoformat(start_s))
                    edt = dt.datetime.combine(day.date(), dt.time.fromisoformat(end_s))
                except Exception:
                    continue
                tz_ref = start_date.tzinfo or dt.timezone.utc
                ha_tz = dt_util.get_time_zone(getattr(hass.config, "time_zone", None)) or tz_ref
                if sdt.tzinfo is None:
                    sdt = sdt.replace(tzinfo=ha_tz)
                if edt.tzinfo is None:
                    edt = edt.replace(tzinfo=ha_tz)
                sdt = sdt.astimezone(tz_ref)
                edt = edt.astimezone(tz_ref)
                if edt <= sdt:
                    edt = edt + dt.timedelta(days=1)
                intervals.append((sdt, edt))

        if not intervals:
            return []

        # 2) Sort intervals by start and merge overlapping/contiguous ones
        intervals.sort(key=lambda x: x[0])
        merged: List[Tuple[dt.datetime, dt.datetime]] = []
        for sdt, edt in intervals:
            if not merged:
                merged.append((sdt, edt))
                continue
            last_s, last_e = merged[-1]
            # If overlaps or touches, extend the last interval
            if sdt <= last_e:
                if edt > last_e:
                    merged[-1] = (last_s, edt)
            else:
                merged.append((sdt, edt))

        # 3) Filter by requested window and create events (clip to window bounds to avoid visual spill)
        events: List[CalendarEvent] = []
        for sdt, edt in merged:
            if edt < start_date or sdt > end_date:
                continue
            ev_start = max(sdt, start_date)
            ev_end = min(edt, end_date)
            events.append(CalendarEvent(summary="Nízký tarif", start=ev_start, end=ev_end))

        return events


class CezOutageCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.outages_coordinator)
        self._hub = hub
        self._attr_name = "ČEZ Odstávky"
        self._attr_unique_id = f"{hub.ean}_outages_calendar"

    @property
    def event(self) -> Optional[CalendarEvent]:
        # Minimal implementation. We don't compute a current event here;
        # calendars will still expose events via async_get_events.
        return None

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
            # Normalize timezone similar to tariff calendar
            tz_ref = start_date.tzinfo or dt.timezone.utc
            ha_tz = dt_util.get_time_zone(getattr(hass.config, "time_zone", None)) or tz_ref
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=ha_tz)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=ha_tz)
            start_dt = start_dt.astimezone(tz_ref)
            end_dt = end_dt.astimezone(tz_ref)
            if end_dt <= start_dt:
                end_dt = end_dt + dt.timedelta(days=1)
            if end_dt < start_date or start_dt > end_date:
                continue
            number = o.get("number", "")
            summary = f"Odstávka {number}" if number else "Odstávka"
            desc = []
            for p in (o.get("sortedParts") or o.get("parts") or []):
                desc.append(p.get("description", ""))
            events.append(CalendarEvent(summary=summary, start=start_dt, end=end_dt, description="; ".join(desc)))
        return events


class CezCurrentSignalCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar showing which HDO signal is valid over time for the first OM.

    It renders events named by signal (e.g., "Signál A1") for their time ranges.
    The `event` property returns the currently active signal interval if any.
    """

    def __init__(self, hub: CezHub) -> None:
        super().__init__(hub.signals_coordinator)
        self._hub = hub
        self._attr_name = "HDO – aktuální signál"
        self._attr_unique_id = f"{hub.ean}_current_signal_calendar"

    @property
    def event(self) -> Optional[CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        signals: List[Dict[str, Any]] = data.get("signals", [])
        if not signals:
            return None
        now = dt_util.now()
        # Iterate intervals and return the first that covers now
        for s in signals:
            date_str = s.get("datum")
            if not date_str:
                continue
            try:
                day = dt.datetime.strptime(date_str, "%d.%m.%Y")
            except Exception:
                continue
            casy = s.get("casy", "")
            name = (
                s.get("nazevSignalu")
                or s.get("nazev")
                or s.get("signal")
                or s.get("name")
                or s.get("oznaceni")
                or "HDO signál"
            )
            for part in [p.strip() for p in casy.split(";") if p.strip()]:
                try:
                    start_s, end_s = [x.strip() for x in part.replace("–", "-").split("-")]
                    sdt = dt.datetime.combine(day.date(), dt.time.fromisoformat(start_s))
                    edt = dt.datetime.combine(day.date(), dt.time.fromisoformat(end_s))
                except Exception:
                    continue
                ha_tz = dt_util.get_time_zone(getattr(self._hub.hass.config, "time_zone", None)) or now.tzinfo
                if sdt.tzinfo is None:
                    sdt = sdt.replace(tzinfo=ha_tz)
                if edt.tzinfo is None:
                    edt = edt.replace(tzinfo=ha_tz)
                # Normalize into now's tz
                sdt = sdt.astimezone(now.tzinfo)
                edt = edt.astimezone(now.tzinfo)
                if edt <= sdt:
                    edt = edt + dt.timedelta(days=1)
                if sdt <= now <= edt:
                    return CalendarEvent(summary=f"Signál {name}", start=sdt, end=edt)
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        signals: List[Dict[str, Any]] = data.get("signals", [])
        if not signals:
            return []
        tz_ref = start_date.tzinfo or dt.timezone.utc
        ha_tz = dt_util.get_time_zone(getattr(hass.config, "time_zone", None)) or tz_ref

        # Build intervals grouped by signal name
        by_name: Dict[str, List[Tuple[dt.datetime, dt.datetime]]] = {}
        for s in signals:
            date_str = s.get("datum")
            if not date_str:
                continue
            try:
                day = dt.datetime.strptime(date_str, "%d.%m.%Y")
            except Exception:
                continue
            casy = s.get("casy", "")
            name = (
                s.get("nazevSignalu")
                or s.get("nazev")
                or s.get("signal")
                or s.get("name")
                or s.get("oznaceni")
                or "HDO signál"
            )
            for part in [p.strip() for p in casy.split(";") if p.strip()]:
                try:
                    start_s, end_s = [x.strip() for x in part.replace("–", "-").split("-")]
                    sdt = dt.datetime.combine(day.date(), dt.time.fromisoformat(start_s))
                    edt = dt.datetime.combine(day.date(), dt.time.fromisoformat(end_s))
                except Exception:
                    continue
                if sdt.tzinfo is None:
                    sdt = sdt.replace(tzinfo=ha_tz)
                if edt.tzinfo is None:
                    edt = edt.replace(tzinfo=ha_tz)
                sdt = sdt.astimezone(tz_ref)
                edt = edt.astimezone(tz_ref)
                if edt <= sdt:
                    edt = edt + dt.timedelta(days=1)
                by_name.setdefault(name, []).append((sdt, edt))

        events: List[CalendarEvent] = []
        for name, intervals in by_name.items():
            if not intervals:
                continue
            intervals.sort(key=lambda x: x[0])
            merged: List[Tuple[dt.datetime, dt.datetime]] = []
            for sdt, edt in intervals:
                if not merged:
                    merged.append((sdt, edt))
                    continue
                last_s, last_e = merged[-1]
                if sdt <= last_e:
                    if edt > last_e:
                        merged[-1] = (last_s, edt)
                else:
                    merged.append((sdt, edt))
            for sdt, edt in merged:
                if edt < start_date or sdt > end_date:
                    continue
                ev_start = max(sdt, start_date)
                ev_end = min(edt, end_date)
                events.append(CalendarEvent(summary=f"Signál {name}", start=ev_start, end=ev_end))
        return events
