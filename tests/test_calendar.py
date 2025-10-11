import datetime as dt
import pytest

from types import SimpleNamespace

from custom_components.cez_distribuce.calendar import (
    CezOutageCalendar,
    CezCurrentSignalCalendar,
)


class DummyCoordinator:
    def __init__(self, data):
        self.data = data

    def async_add_listener(self, _cb):
        # CoordinatorEntity expects an unsubscribe callback
        return lambda: None


class DummyHub(SimpleNamespace):
    pass


@pytest.mark.asyncio
async def test_tariff_calendar_merges_overlaps_and_filters_window():
    # Signals for a single day with overlaps and duplicates
    day = "10.10.2025"
    signals = {
        "signals": [
            {"datum": day, "casy": "00:00 - 05:35; 06:30 - 08:55; 09:54 - 15:16; 16:15 - 20:16; 22:10 - 23:51"},
            # Overlapping/duplicate fragments that should be merged away
            {"datum": day, "casy": "01:10 - 05:11; 06:30 - 08:55; 09:54 - 15:16; 16:15 - 20:16"},
        ]
    }

    # Prepare hub/coordinator and hass with timezone
    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone="Europe/Prague")

    hub = DummyHub(
        ean="123",
        signals_coordinator=DummyCoordinator(signals),
    )

    cal = CezTariffCalendar(hub)

    # Query a window that covers the whole day in UTC (calendar normalizes)
    start = dt.datetime(2025, 10, 9, 22, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2025, 10, 11, 0, 0, tzinfo=dt.timezone.utc)

    events = await cal.async_get_events(hass, start, end)

    # Expect merged, non-duplicated intervals -> should be 5 events
    assert len(events) == 5
    # Basic sanity: all summaries are the same and within range
    for ev in events:
        assert ev.summary == "Nízký tarif"
        assert start <= ev.start <= end
        assert start <= ev.end <= end
        assert ev.end > ev.start


@pytest.mark.asyncio
async def test_current_signal_calendar_event_returns_active_interval():
    # Build signals where one interval around now exists
    today = dt.datetime.now().strftime("%d.%m.%Y")
    now_local = dt.datetime.now().astimezone()
    start_local = (now_local - dt.timedelta(minutes=10)).time().replace(second=0, microsecond=0)
    end_local = (now_local + dt.timedelta(minutes=10)).time().replace(second=0, microsecond=0)

    signals = {
        "signals": [
            {"datum": today, "casy": f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}", "nazevSignalu": "A1"},
        ]
    }

    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone=str(now_local.tzinfo) if now_local.tzinfo else "Europe/Prague")

    hub = DummyHub(
        ean="123",
        signals_coordinator=DummyCoordinator(signals),
        hass=hass,
    )

    cal = CezCurrentSignalCalendar(hub)

    ev = cal.event
    assert ev is not None
    assert ev.summary == "Signál A1"
    assert ev.start < ev.end


@pytest.mark.asyncio
async def test_outage_calendar_parses_and_handles_midnight_cross():
    # Outage starting in the evening and ending after midnight
    outages = [
        {
            "dateFormatted": "29.10.2025",
            "timeFormatted": "22:00 - 01:00",  # next day end
            "number": "12345",
            "sortedParts": [{"description": "Plánovaná odstávka"}],
        }
    ]

    hass = SimpleNamespace()
    hass.config = SimpleNamespace(time_zone="Europe/Prague")

    hub = DummyHub(
        ean="123",
        outages_coordinator=DummyCoordinator(outages),
    )

    cal = CezOutageCalendar(hub)

    start = dt.datetime(2025, 10, 29, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(2025, 10, 30, 23, 59, tzinfo=dt.timezone.utc)

    events = await cal.async_get_events(hass, start, end)
    assert len(events) == 1
    ev = events[0]
    assert ev.summary.startswith("Odstávka")
    assert ev.description and "Plánovaná odstávka" in ev.description
    assert start <= ev.start < ev.end <= end
