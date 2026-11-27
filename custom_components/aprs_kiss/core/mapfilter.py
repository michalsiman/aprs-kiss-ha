"""Which stations the map shows: everything, or only some kinds (several kinds can be on at once).

- weather: weather stations (a weather report, or the weather symbol);
- moving: stations that moved in the last MOVING_SECONDS. A station not seen long enough to know
  (heard for the first time a moment ago) is shown until it is clear it stands still;
- repeater: repeaters (the repeater symbol, or a frequency with offset or tone; see repeater.py);
- road: traffic incidents and road trouble (crash, emergency, work zone, flooding, fog, snow and ice),
  mostly objects put on APRS-IS by traffic-info gateways.

A station is shown when it is any of the chosen kinds. No kind chosen: all stations.

And how far (in_reach): stations heard on the radio up to RF_KM (0 = no limit, the default); stations
only from the internet up to the APRS-IS radius (the server is asked for that area too).
"""

from __future__ import annotations

from typing import Any

from .repeater import is_repeater
from .tracker import distance_m

KINDS = ("weather", "moving", "repeater", "road")
MOVING_SECONDS = 10 * 60
MOVING_KMH = 3.0  # a reported speed above this, lately: it moves
IS_KM = (20, 50, 100)  # the map's choices for the APRS-IS radius
RF_KM = (20, 50, 100, 0)  # …and for stations heard on the radio (0 = no limit)

# symbol codes (alternate table, also with an overlay character)
ROAD_ALTERNATE = set("'!jw{*eB")
WEATHER_CODES = {"_"}  # weather station / weather site, either table
WEATHER_PRIMARY = {"W"}  # National Weather Service site


def parse(value: str) -> set[str]:
    return {k for k in (value or "").replace(" ", "").split(",") if k in KINDS}


def join(kinds: set[str]) -> str:
    return ",".join(k for k in KINDS if k in kinds)


def _alternate(table: str | None) -> bool:
    return bool(table) and table != "/"  # "\" or an overlay character (a letter or digit)


def is_weather(entry: dict[str, Any]) -> bool:
    code, table = entry.get("symbol"), entry.get("symbol_table")
    if isinstance(entry.get("weather"), dict) and entry["weather"]:
        return True
    return code in WEATHER_CODES or (code in WEATHER_PRIMARY and table == "/") or (code == "W" and _alternate(table))


def is_road(entry: dict[str, Any]) -> bool:
    return _alternate(entry.get("symbol_table")) and (entry.get("symbol") or "") in ROAD_ALTERNATE


def is_moving(entry: dict[str, Any], now: float, new_counts: bool = True) -> bool:
    """Moved lately (the track has a new place), or says it drives; or too new to know yet."""
    track = entry.get("track") or ()
    if len(track) >= 2 and now - track[-2][0] <= MOVING_SECONDS:
        return True  # it was still at the previous place a moment ago, and now is elsewhere
    recent = now - (entry.get("last_heard") or 0) <= MOVING_SECONDS
    if recent and (entry.get("speed") or 0) > MOVING_KMH and not entry.get("weather"):
        return True
    first = entry.get("first_heard")
    return new_counts and first is not None and now - first < MOVING_SECONDS  # not known yet: shown until it stays put


def shown(entry: dict[str, Any], kinds: set[str], now: float) -> bool:
    if not kinds:
        return True
    return (("weather" in kinds and is_weather(entry))
            or ("road" in kinds and is_road(entry))
            or ("repeater" in kinds and is_repeater(entry))
            or ("moving" in kinds and is_moving(entry, now)))


def in_reach(entry: dict[str, Any], here: tuple[float, float] | None, is_km: int, rf_km: int) -> bool:
    """Near enough to show: radio stations within rf_km, internet-only ones within is_km (0 = no limit).
    Where we are not known: all."""
    limit = rf_km if entry.get("last_rf") else is_km
    if not limit or here is None or entry.get("latitude") is None or entry.get("longitude") is None:
        return True
    return distance_m(here[0], here[1], entry["latitude"], entry["longitude"]) <= limit * 1000
