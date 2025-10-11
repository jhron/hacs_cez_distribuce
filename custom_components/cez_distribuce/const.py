"""Constants for the ČEZ Distribuce Home Assistant integration.

These values define the integration domain, config keys and default refresh
intervals (in minutes) for the different data groups fetched from the portal.
"""
DOMAIN = "cez_distribuce"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
DEFAULT_SCAN_INTERVAL_SIGNALS_MIN = 1440
DEFAULT_SCAN_INTERVAL_OUTAGES_MIN = 1440
DEFAULT_SCAN_INTERVAL_READINGS_MIN = 5
