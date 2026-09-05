"""Unit tests for ČEZ Distribuce statistics helper."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.const import UnitOfEnergy

from custom_components.cez_distribuce.const import DOMAIN
from custom_components.cez_distribuce.statistics import (
    _parse_float,
    _parse_reading_date,
    async_import_readings_statistics,
    build_statistics_for_readings,
)

EAN = "8591824001234567"


def test_parse_float():
    assert _parse_float("   2865.00000000000000") == 2865.0
    assert _parse_float(100.5) == 100.5
    assert _parse_float(0) == 0.0
    assert _parse_float(None) is None
    assert _parse_float("invalid") is None


def test_parse_reading_date():
    # Plain date string -> converted to UTC datetime with minute=0, second=0
    dt1 = _parse_reading_date("2026-06-30")
    assert isinstance(dt1, datetime)
    assert dt1.tzinfo is not None
    assert dt1.minute == 0
    assert dt1.second == 0
    assert dt1.microsecond == 0

    # ISO datetime string -> minute and second zeroed out
    dt2 = _parse_reading_date("2026-06-30T14:35:20+02:00")
    assert isinstance(dt2, datetime)
    assert dt2.minute == 0
    assert dt2.second == 0
    assert dt2.hour == 12  # 14:00 in +02:00 is 12:00 UTC

    # Invalid values
    assert _parse_reading_date(None) is None
    assert _parse_reading_date("") is None
    assert _parse_reading_date("not-a-date") is None


def test_build_statistics_for_readings():
    readings = [
        # Out of order to verify sorting
        {"datumOdectu": "2026-06-30", "stavVt": "  300.0", "stavNt": "  150.0"},
        {"datumOdectu": "2026-05-31", "stavVt": "200.0", "stavNt": "100.0"},
    ]

    stats_map = build_statistics_for_readings(EAN, readings)

    assert set(stats_map.keys()) == {"vt", "nt", "total"}

    # Check VT
    vt_meta, vt_stats = stats_map["vt"]
    assert vt_meta["statistic_id"] == f"{DOMAIN}:{EAN}_vt"
    assert vt_meta["source"] == DOMAIN
    assert vt_meta["has_sum"] is True
    assert vt_meta["mean_type"] == StatisticMeanType.NONE
    assert vt_meta["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR
    assert vt_meta["unit_class"] == "energy"
    assert len(vt_stats) == 2
    # Verify chronological order: May 31 first, then June 30
    assert vt_stats[0]["sum"] == 200.0
    assert vt_stats[0]["state"] == 200.0
    assert vt_stats[1]["sum"] == 300.0
    assert vt_stats[1]["state"] == 300.0
    assert vt_stats[0]["start"] < vt_stats[1]["start"]

    # Check NT
    nt_meta, nt_stats = stats_map["nt"]
    assert nt_meta["statistic_id"] == f"{DOMAIN}:{EAN}_nt"
    assert len(nt_stats) == 2
    assert nt_stats[0]["sum"] == 100.0
    assert nt_stats[1]["sum"] == 150.0

    # Check Total
    tot_meta, tot_stats = stats_map["total"]
    assert tot_meta["statistic_id"] == f"{DOMAIN}:{EAN}_total"
    assert len(tot_stats) == 2
    assert tot_stats[0]["sum"] == 300.0
    assert tot_stats[1]["sum"] == 450.0


def test_build_statistics_deduplication():
    readings = [
        {"datumOdectu": "2026-06-30", "stavVt": "100.0", "stavNt": "50.0"},
        {"datumOdectu": "2026-06-30", "stavVt": "105.0", "stavNt": "55.0"},
    ]
    stats_map = build_statistics_for_readings(EAN, readings)
    _, vt_stats = stats_map["vt"]
    # Only one datapoint for the same date
    assert len(vt_stats) == 1
    assert vt_stats[0]["sum"] == 105.0


def test_async_import_readings_statistics():
    hass = MagicMock()
    readings = [{"datumOdectu": "2026-06-30", "stavVt": "100.0", "stavNt": "50.0"}]

    with patch(
        "custom_components.cez_distribuce.statistics.async_add_external_statistics"
    ) as mock_add:
        async_import_readings_statistics(hass, EAN, readings)
        assert mock_add.call_count == 3  # vt, nt, total

    # Empty data should not call async_add_external_statistics
    with patch(
        "custom_components.cez_distribuce.statistics.async_add_external_statistics"
    ) as mock_add:
        async_import_readings_statistics(hass, EAN, [])
        assert mock_add.call_count == 0
        async_import_readings_statistics(hass, "", readings)
        assert mock_add.call_count == 0
