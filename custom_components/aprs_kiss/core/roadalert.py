"""Road incidents ahead: while the tracker runs, a warning for an incident on the way we are going.
The same for other moving stations: one ahead of us on our way (we catch it up, or it comes towards us).

Where we will drive is not known (no route), so "ahead" is a lobe in front of us: as far as the chosen
distance straight ahead, shorter the more an incident is off to the side (we may turn), and never
behind us. Its shape follows the speed: slowly (a town, many turns) the lobe is wide, fast (a main
road or a motorway, a turn now and then) it is long and narrow. Right next to us, in front, anything
counts. Each incident is announced once; again only after REPEAT_SECONDS, if it is still ahead.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

from .mapfilter import MOVING_SECONDS, is_moving, is_road, is_weather

DISTANCES_KM = (2, 5, 10, 20)
MIN_SPEED_KMH = 5.0  # slower than this the heading from the GPS means nothing
TOWN_KMH = 30.0  # at or below: the widest lobe…
FAST_KMH = 90.0  # …at or above: the narrowest
WIDE, NARROW = 1.0, 4.0  # the lobe's exponent (see reach)
NEAR_KM = 0.5  # closer than this and in front of us: always
REPEAT_SECONDS = 30 * 60
INCIDENT_MAX_AGE = 3 * 3600  # older reports are not news any more
STATION_MAX_AGE = MOVING_SECONDS  # a moving station's position older than this: it is elsewhere by now
SAME_WAY_DEG = 45  # its course this close to ours: it goes our way; this close to the opposite: towards us
HEADING_MIN_M = 60  # from our own track: the last two points at least this far apart


def offset_km(lat: float, lon: float, lat2: float, lon2: float) -> tuple[float, float]:
    """(east, north) km from the first point to the second (flat Earth is fine for a few tens of km)."""
    north = (lat2 - lat) * 111.195
    east = (lon2 - lon) * 111.195 * math.cos(math.radians((lat + lat2) / 2))
    return east, north


def sharpness(speed_kmh: float | None) -> float:
    """The lobe's exponent: WIDE in a town, NARROW fast, in between in between (unknown: in between)."""
    if speed_kmh is None:
        return (WIDE + NARROW) / 2
    share = min(1.0, max(0.0, (speed_kmh - TOWN_KMH) / (FAST_KMH - TOWN_KMH)))
    return WIDE + share * (NARROW - WIDE)


def reach(angle_deg: float, radius_km: float, speed_kmh: float | None) -> float:
    """How far the lobe goes at this angle off our heading: the whole distance straight ahead, less
    to the sides, nothing behind. r = R·((1 + cos a) / 2)^k. With 5 km: in a town (k = 1) 4.7 km at 30°,
    2.5 km at 90°; on a motorway (k = 4) 3.8 km at 30°, 0.3 km at 90°."""
    if abs(angle_deg) > 90:
        return 0.0
    return radius_km * ((1 + math.cos(math.radians(angle_deg))) / 2) ** sharpness(speed_kmh)


def ahead(lat: float, lon: float, course: float, lat2: float, lon2: float, radius_km: float,
          speed_kmh: float | None = None) -> tuple[float, float] | None:
    """(km away, km to the side: + right, - left) when the point is in the lobe, else None."""
    east, north = offset_km(lat, lon, lat2, lon2)
    c = math.radians(course)
    along = east * math.sin(c) + north * math.cos(c)
    side = east * math.cos(c) - north * math.sin(c)
    if along < 0:
        return None  # behind us
    dist = math.hypot(along, side)
    angle = math.degrees(math.atan2(side, along))
    if dist <= NEAR_KM or dist <= reach(angle, radius_km, speed_kmh):
        return dist, side
    return None


def heading(fix_course: float | None, fix_speed: float | None, track: list | None) -> float | None:
    """Where we are going: the GPS course when moving, else from the last two places of our own track."""
    if fix_course is not None and fix_speed is not None and fix_speed >= MIN_SPEED_KMH:
        return fix_course % 360
    if track and len(track) >= 2:
        (_t1, lat1, lon1), (_t2, lat2, lon2) = track[-2][:3], track[-1][:3]
        east, north = offset_km(lat1, lon1, lat2, lon2)
        if math.hypot(east, north) * 1000 >= HEADING_MIN_M:
            return math.degrees(math.atan2(east, north)) % 360
    return None


def _base(call: str) -> str:
    return call.split("-")[0].upper()


def moving_station(mine: str) -> Callable[[dict[str, Any], float], bool]:
    """Which stations count for the "moving station ahead" warning: moving lately, not our own
    (any SSID of our callsign), not an incident or a weather station."""
    me = _base(mine) if mine else ""

    def want(entry: dict[str, Any], now: float) -> bool:
        if (me and _base(entry.get("call", "")) == me) or entry.get("object_of") or is_road(entry) or is_weather(entry):
            return False
        return is_moving(entry, now, new_counts=False)
    return want


def incident(entry: dict[str, Any], _now: float) -> bool:
    return is_road(entry)


def relation(our_course: float, entry: dict[str, Any]) -> str | None:
    """"same" (it goes our way: we catch it up), "towards" (it comes towards us), "across", or None
    when its course is not known."""
    course, speed = entry.get("course"), entry.get("speed")
    if course is None or not speed or speed < 3:
        return None
    d = abs(course - our_course) % 360
    d = 360 - d if d > 180 else d
    return "same" if d <= SAME_WAY_DEG else "towards" if d >= 180 - SAME_WAY_DEG else "across"


class RoadAlerts:
    def __init__(self) -> None:
        self.told: dict[str, float] = {}  # incident -> when we warned about it

    def check(self, now: float, lat: float, lon: float, course: float | None,
              stations: Iterable[dict[str, Any]], radius_km: float,
              speed_kmh: float | None = None, want: Callable[[dict[str, Any], float], bool] = incident,
              max_age: float = INCIDENT_MAX_AGE) -> list[tuple[dict[str, Any], float, float]]:
        """New incidents (or what `want` picks) ahead: [(station, km away, km to the side)], nearest first."""
        if course is None:
            return []
        found = []
        for e in stations:
            if e.get("latitude") is None or e.get("longitude") is None or not want(e, now):
                continue
            if now - (e.get("last_heard") or 0) > max_age:
                continue
            if now - self.told.get(e["call"], -REPEAT_SECONDS) < REPEAT_SECONDS:
                continue
            where = ahead(lat, lon, course, e["latitude"], e["longitude"], radius_km, speed_kmh)
            if where:
                found.append((e, *where))
        for e, _a, _s in found:
            self.told[e["call"]] = now
        return sorted(found, key=lambda f: f[1])
