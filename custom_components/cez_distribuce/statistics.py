"""Statistics helper for ČEZ Distribuce integration.

Imports historical meter readings (VT, NT, and total) directly into Home Assistant's
long-term statistics using async_add_external_statistics with the actual reading timestamp.
"""
from __future__ import annotations

from datetime import datetime, time
import logging
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMetaData,
)
try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:
    StatisticMeanType = None  # type: ignore[assignment]
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _parse_float(val: Any) -> Optional[float]:
    """Parse string or numeric value from portal to float."""
    if val is None:
        return None
    try:
        return round(float(str(val).strip()), 3)
    except (ValueError, TypeError):
        return None


def _parse_reading_date(val: Any) -> Optional[datetime]:
    """Parse date or datetime string to a timezone-aware UTC datetime.

    Dates (e.g. '2026-06-30') are converted to start-of-day in the local timezone,
    then represented in UTC.
    """
    if not val or not isinstance(val, str):
        return None
    cleaned = val.strip()

    parsed_dt = dt_util.parse_datetime(cleaned)
    if parsed_dt is not None:
        # HA recorder requires top-of-the-hour timestamps (minutes and seconds = 0)
        parsed_dt = parsed_dt.replace(minute=0, second=0, microsecond=0)
        if parsed_dt.tzinfo is not None:
            return dt_util.as_utc(parsed_dt)
        return dt_util.as_utc(parsed_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE))

    parsed_d = dt_util.parse_date(cleaned)
    if parsed_d is not None:
        local_dt = datetime.combine(parsed_d, time(0, 0, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return dt_util.as_utc(local_dt)

    return None


def _build_meta(statistic_id: str, name: str) -> StatisticMetaData:
    """Build StatisticMetaData with backwards compatibility across HA versions."""
    meta: Dict[str, Any] = {
        "has_mean": False,
        "has_sum": True,
        "name": name,
        "source": DOMAIN,
        "statistic_id": statistic_id,
        "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
    }
    if StatisticMeanType is not None:
        meta["mean_type"] = StatisticMeanType.NONE
    meta["unit_class"] = "energy"
    return meta  # type: ignore[return-value]


def build_statistics_for_readings(
    ean: str, readings: List[Dict[str, Any]]
) -> Dict[str, Tuple[StatisticMetaData, List[StatisticData]]]:
    """Build StatisticMetaData and sorted StatisticData lists for VT, NT and Total.

    Deduplicates entries with the same timestamp and sorts them chronologically.
    Returns a dictionary with keys 'vt', 'nt', 'total'.
    """
    vt_datapoints: Dict[datetime, StatisticData] = {}
    nt_datapoints: Dict[datetime, StatisticData] = {}
    total_datapoints: Dict[datetime, StatisticData] = {}

    for item in readings:
        if not isinstance(item, dict):
            continue

        start_dt = _parse_reading_date(item.get("datumOdectu"))
        if start_dt is None:
            continue

        vt = _parse_float(item.get("stavVt"))
        nt = _parse_float(item.get("stavNt"))

        if vt is not None:
            vt_datapoints[start_dt] = StatisticData(start=start_dt, state=vt, sum=vt)

        if nt is not None:
            nt_datapoints[start_dt] = StatisticData(start=start_dt, state=nt, sum=nt)

        if vt is not None and nt is not None:
            tot = round(vt + nt, 3)
            total_datapoints[start_dt] = StatisticData(start=start_dt, state=tot, sum=tot)

    # Sort each list chronologically by start timestamp
    sorted_vt = [vt_datapoints[ts] for ts in sorted(vt_datapoints.keys())]
    sorted_nt = [nt_datapoints[ts] for ts in sorted(nt_datapoints.keys())]
    sorted_total = [total_datapoints[ts] for ts in sorted(total_datapoints.keys())]

    return {
        "vt": (_build_meta(f"{DOMAIN}:{ean}_vt", f"ČEZ Stav VT – EAN {ean}"), sorted_vt),
        "nt": (_build_meta(f"{DOMAIN}:{ean}_nt", f"ČEZ Stav NT – EAN {ean}"), sorted_nt),
        "total": (_build_meta(f"{DOMAIN}:{ean}_total", f"ČEZ Stav celkem – EAN {ean}"), sorted_total),
    }


def async_import_readings_statistics(
    hass: HomeAssistant, ean: str, readings: List[Dict[str, Any]]
) -> None:
    """Import readings into Home Assistant external statistics."""
    if not ean or not readings:
        return

    try:
        stats_map = build_statistics_for_readings(ean, readings)
        for kind, (metadata, stats) in stats_map.items():
            if stats:
                async_add_external_statistics(hass, metadata, stats)
                _LOGGER.debug(
                    "Imported %d statistics points for %s (%s)",
                    len(stats),
                    metadata["statistic_id"],
                    kind,
                )
    except Exception as err:
        _LOGGER.error("Failed to import statistics for EAN %s: %s", ean, err)
