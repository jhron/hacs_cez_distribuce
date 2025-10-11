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
    hub: CezHub = hass.data[DOMAIN]["legacy"] if isinstance(hass.data.get(DOMAIN), dict) and "legacy" in hass.data[
        DOMAIN] else hass.data[DOMAIN]
    # Build per-EAN entities
    entities = []
    points = getattr(hub, "points", None) or ([hub.data] if getattr(hub, "data", None) else [])
    for p in points:
        ean = (p.supply_point_detail or {}).get("ean")
        if not ean:
            continue
        entities.append(CezOutageCalendar(hub, ean))
        entities.append(CezCurrentSignalCalendar(hub, ean))
    # Fallback: if nothing created, add single default entities (for backward compat)
    if not entities:
        entities = [CezOutageCalendar(hub, hub.ean), CezCurrentSignalCalendar(hub, hub.ean)]
    async_add_entities(entities)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    hub: CezHub = hass.data[DOMAIN][entry.entry_id]
    entities = []
    points = getattr(hub, "points", None) or ([hub.data] if getattr(hub, "data", None) else [])
    for p in points:
        ean = (p.supply_point_detail or {}).get("ean")
        if not ean:
            continue
        entities.append(CezOutageCalendar(hub, ean))
        entities.append(CezCurrentSignalCalendar(hub, ean))
    if not entities:
        entities = [CezOutageCalendar(hub, hub.ean), CezCurrentSignalCalendar(hub, hub.ean)]
    async_add_entities(entities)


class CezOutageCalendar(CoordinatorEntity, CalendarEntity):
    def __init__(self, hub: CezHub, ean: Optional[str]) -> None:
        super().__init__(hub.outages_coordinator)
        self._hub = hub
        self._ean = ean
        self._attr_name = "ČEZ Odstávky"
        self._attr_unique_id = f"{ean}_outages_calendar" if ean else f"{hub.ean}_outages_calendar"

    @property
    def event(self) -> Optional[CalendarEvent]:
        # Minimal implementation. We don't compute a current event here;
        # calendars will still expose events via async_get_events.
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[
        CalendarEvent]:
        data = self.coordinator.data or {}
        if isinstance(data, list):
            outages: List[Dict[str, Any]] = data
        else:
            outages = data.get(self._ean, [])
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
            for p in (o.get("sortedParts") or o.get("parts") or []):
                desc = []
                main_location = p.get("description", "")
                for s in (p.get('sortedStreets') or p.get('streets') or [{'streetNumbers': {'': ''}}]):
                    street_name = s.get('streetName', '')
                    for n in s.get('streetNumbers', [{'': ''}]):
                        street_number = ''
                        if n.get('buildingId') or n.get('streetId'):
                            street_number = n.get('buildingId') + '/' + n.get('streetId')
                        if n.get('cadastralTerritoryCode') or n.get('parcelaId'):
                            street_number += ' ('
                            if n.get('cadastralTerritoryCode'):
                                street_number += 'k.ú ' + n.get('cadastralTerritoryCode')
                            if n.get('cadastralTerritoryCode') and n.get('parcelaId'):
                                street_number += ', '
                            if n.get('parcelaId'):
                                street_number += 'parc. č. ' + n.get('parcelaId')
                            street_number += ')'
                        desc.append(main_location + ', ' + street_name + ' ' + street_number)
                events.append(
                    CalendarEvent(summary=summary + ' - ' + main_location, start=start_dt, end=end_dt,
                                  description=";\n".join(desc),
                                  location=main_location))
        return events


class CezCurrentSignalCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar showing which HDO signal is valid over time for the specific OM (by EAN)."""

    def __init__(self, hub: CezHub, ean: Optional[str]) -> None:
        super().__init__(hub.signals_coordinator)
        self._hub = hub
        self._ean = ean
        self._attr_name = "HDO – aktuální signál"
        self._attr_unique_id = f"{ean}_current_signal_calendar" if ean else f"{hub.ean}_current_signal_calendar"

    @property
    def event(self) -> Optional[CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        if "signals" in data:
            signals: List[Dict[str, Any]] = data.get("signals", [])
        else:
            signals = (data.get(self._ean) or {}).get("signals", [])
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
                    # Build location string with EAN and address for this OM
                    location_parts: List[str] = []
                    if self._ean:
                        location_parts.append(f"EAN {self._ean}")
                    addr = build_location_address(self._hub, self._ean)
                    if addr:
                        location_parts.append(addr)
                    location = " – ".join(location_parts) if location_parts else None
                    return CalendarEvent(summary=f"Signál {name}", start=sdt, end=edt, location=location)
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime) -> List[
        CalendarEvent]:
        data: Dict[str, Any] = self.coordinator.data or {}
        # Support both legacy single-EAN responses and new map {ean: signals}
        if "signals" in data:
            signals: List[Dict[str, Any]] = data.get("signals", [])
        else:
            signals = (data.get(self._ean) or {}).get("signals", [])
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


def _address_from_detail(spd: Dict[str, Any]) -> Optional[str]:
    try:
        # Prefer nested address structure if present
        addr_node = spd.get("adresa") or spd.get("address")
        if isinstance(addr_node, dict):
            for key in ("adresaComplete", "complete", "full"):
                val = addr_node.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        # Compose from parts as fallback
        street = spd.get("ulice") or spd.get("uliceNazev") or spd.get("street")
        number = spd.get("cisloPopisne") or spd.get("cp") or spd.get("cisloDomovni") or spd.get("houseNumber")
        city = spd.get("mesto") or spd.get("obec") or spd.get("city")
        psc = spd.get("psc") or spd.get("zip") or spd.get("pscKod")
        parts: List[str] = []
        if street and number:
            parts.append(f"{street} {number}")
        elif street:
            parts.append(str(street))
        elif number:
            parts.append(str(number))
        locality: List[str] = []
        if psc:
            locality.append(str(psc))
        if city:
            locality.append(str(city))
        if locality:
            parts.append(", ".join(locality))
        addr = ", ".join([p for p in parts if p and str(p).strip()])
        return addr if addr else None
    except Exception:
        return None


def build_location_address(hub: CezHub, ean: Optional[str]) -> Optional[str]:
    # Find address for provided EAN across all points, fallback to first point
    try:
        if ean:
            for p in getattr(hub, "points", []) or []:
                spd = getattr(p, "supply_point_detail", {}) or {}
                if spd.get("ean") == ean:
                    return _address_from_detail(spd)
        # Fallback
        data = getattr(hub, "data", None)
        if data and data.supply_point_detail:
            return _address_from_detail(data.supply_point_detail)
    except Exception:
        return None
    return None
