"""Offline unit tests for the ČEZ Distribuce calendar entities.

Uses lightweight dummy hub/coordinator stubs rather than a full HA runtime so
the parsing/merging logic in calendar.py can be exercised quickly.
"""
import datetime as dt

from types import SimpleNamespace

from custom_components.cez_distribuce.calendar import (
    CezCurrentSignalCalendar,
    CezOutageCalendar,
)


class DummyCoordinator:
    """Minimal stand-in for DataUpdateCoordinator.

    CoordinatorEntity stores the coordinator in ``__init__``; the listener
    subscription only happens later in ``async_added_to_hass`` (never called
    in these tests), so a stub with ``data`` is enough.
    """

    def __init__(self, data):
        self.data = data

    def async_add_listener(self, update_callback, context=None):
        # DataUpdateCoordinator.async_add_listener takes (callback, context)
        # and must return an unsubscribe callable.
        return lambda: None


class DummyHub(SimpleNamespace):
    pass


async def test_current_signal_calendar_merges_overlaps_and_filters_window():
    # Signals for a single day with overlaps and duplicates, all sharing one
    # signal name. The merge logic in CezCurrentSignalCalendar.async_get_events
    # should collapse them into 5 disjoint intervals.
    day = "10.10.2025"
    signals_payload = {
        "signals": [
            {"datum": day, "nazevSignalu": "NT",
             "casy": "00:00 - 05:35; 06:30 - 08:55; 09:54 - 15:16; 16:15 - 20:16; 22:10 - 23:51"},
            # Overlapping/duplicate fragments that should be merged away
            {"datum": day, "nazevSignalu": "NT",
             "casy": "01:10 - 05:11; 06:30 - 08:55; 09:54 - 15:16; 16:15 - 20:16"},
        ]
    }

    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone="Europe/Prague")

    # The signals coordinator stores data keyed by EAN (see CezHub._update_signals)
    hub = DummyHub(
        ean="123",
        signals_coordinator=DummyCoordinator({"123": signals_payload}),
        hass=hass,
    )

    cal = CezCurrentSignalCalendar(hub, "123")

    # Query a window that covers the whole day in UTC (calendar normalizes)
    start = dt.datetime(2025, 10, 9, 22, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2025, 10, 11, 0, 0, tzinfo=dt.timezone.utc)

    events = await cal.async_get_events(hass, start, end)

    # Expect merged, non-duplicated intervals -> should be 5 events
    assert len(events) == 5
    # Basic sanity: all summaries are the same and within range
    for ev in events:
        assert ev.summary == "Signál NT"
        assert start <= ev.start <= end
        assert start <= ev.end <= end
        assert ev.end > ev.start


async def test_current_signal_calendar_event_returns_active_interval():
    # Build an interval that definitely covers "now" as HA sees it.
    # CezCurrentSignalCalendar.event compares against dt_util.now(), which in
    # the test runtime is UTC; the interval times are interpreted in the hub's
    # configured time zone (Europe/Prague). To stay independent of DST offsets
    # we build a wide interval spanning most of the day.
    from homeassistant.util import dt as dt_util

    now = dt_util.now()
    # Use the same calendar day the runtime "now" falls on, expressed in the
    # hub's local timezone, so the strptime("%d.%m.%Y") match works.
    ha_tz = dt_util.get_time_zone("Europe/Prague") or now.tzinfo
    now_local = now.astimezone(ha_tz)
    today = now_local.strftime("%d.%m.%Y")
    # Wide window around the current local time
    start_local = (now_local - dt.timedelta(hours=2)).time().replace(second=0, microsecond=0)
    end_local = (now_local + dt.timedelta(hours=2)).time().replace(second=0, microsecond=0)

    signals_payload = {
        "signals": [
            {"datum": today,
             "casy": f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}",
             "nazevSignalu": "A1"},
        ]
    }

    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone="Europe/Prague")

    # Coordinator data is keyed by EAN
    hub = DummyHub(
        ean="123",
        signals_coordinator=DummyCoordinator({"123": signals_payload}),
        hass=hass,
    )

    cal = CezCurrentSignalCalendar(hub, "123")

    ev = cal.event
    assert ev is not None
    assert ev.summary == "Signál A1"
    assert ev.start < ev.end


async def test_outage_calendar_parses_and_handles_midnight_cross():
    # Outage starting in the evening and ending after midnight
    outages_for_ean = [
        {
            "dateFormatted": "29.10.2025",
            "timeFormatted": "22:00 - 01:00",  # next day end
            "number": "12345",
            "sortedParts": [{"description": "Plánovaná odstávka"}],
        }
    ]

    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone="Europe/Prague")

    # Coordinator data is keyed by EAN (see CezHub._update_outages)
    hub = DummyHub(
        ean="123",
        outages_coordinator=DummyCoordinator({"123": outages_for_ean}),
    )

    cal = CezOutageCalendar(hub, "123")

    start = dt.datetime(2025, 10, 29, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2025, 10, 30, 23, 59, tzinfo=dt.timezone.utc)

    events = await cal.async_get_events(hass, start, end)
    assert len(events) == 1
    ev = events[0]
    assert ev.summary.startswith("Odstávka")
    assert ev.description and "Plánovaná odstávka" in ev.description
    assert start <= ev.start < ev.end <= end
