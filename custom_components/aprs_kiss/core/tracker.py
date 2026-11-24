"""The tracker: our position sent again and again while it runs, from the GPS.

Two ways to decide when:

- a fixed interval (every N minutes);
- smart beaconing ("SmartBeaconing", HamHUD; the same in APRSdroid, Yaesu/Kenwood radios and the
  LoRa APRS trackers): standing still, once in a long while; moving, more often the faster you go,
  between a slow and a fast rate; and at once when you turn a corner ("corner pegging"), so the track
  on the map follows the road.

Speeds are km/h, times seconds, angles degrees. The profiles are the usual ones of the LoRa APRS
trackers (walking, bike, car).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MODES = ("fixed", "smart")
FIXED_MINUTES = (1, 2, 3, 5, 10, 15, 30)
STILL_MINUTES = (10, 15, 20, 30, 60)


@dataclass(frozen=True)
class Profile:
    slow_speed: float  # below it we are standing (walking about counts as standing for a car)
    slow_rate: float  # moving slowly: at least this often
    fast_speed: float  # at and above it: the fast rate
    fast_rate: float
    turn_min: float  # corner pegging: the smallest turn that counts…
    turn_slope: float  # …plus this divided by the speed (a slow turn needs more angle)
    turn_time: float  # and not more often than this


PROFILES = {
    "walk": Profile(slow_speed=2, slow_rate=300, fast_speed=10, fast_rate=120, turn_min=25, turn_slope=80, turn_time=30),
    "bike": Profile(slow_speed=4, slow_rate=240, fast_speed=40, fast_rate=60, turn_min=12, turn_slope=60, turn_time=20),
    "car": Profile(slow_speed=8, slow_rate=180, fast_speed=90, fast_rate=60, turn_min=10, turn_slope=80, turn_time=15),
}


def _turn(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


@dataclass
class Tracker:
    mode: str = "fixed"
    fixed_minutes: float = 2
    profile: str = "car"
    still_minutes: float = 60
    last_time: float | None = None  # when our position went out
    last_course: float | None = None
    last_position: tuple[float, float] | None = None

    def rate(self, speed: float | None) -> float:
        """Seconds between beacons at this speed (no corner)."""
        if self.mode != "smart":
            return max(1.0, self.fixed_minutes) * 60
        p = PROFILES.get(self.profile, PROFILES["car"])
        if not speed or speed < p.slow_speed:
            return max(p.slow_rate, self.still_minutes * 60)  # standing still
        if speed >= p.fast_speed:
            return p.fast_rate
        return min(p.slow_rate, p.fast_rate * p.fast_speed / speed)

    def why(self, now: float, speed: float | None, course: float | None,
            position: tuple[float, float] | None = None) -> str | None:
        """Why to send now ("start", "time", "turn", "moved"), or None to wait."""
        if self.last_time is None:
            return "start"
        since = now - self.last_time
        if self.mode == "smart":
            p = PROFILES.get(self.profile, PROFILES["car"])
            moving = bool(speed and speed >= p.slow_speed)
            if moving and course is not None and self.last_course is not None and since >= p.turn_time:
                if _turn(course, self.last_course) > p.turn_min + p.turn_slope / speed:
                    return "turn"
            if (not moving and position and self.last_position and since >= p.slow_rate
                    and distance_m(*position, *self.last_position) > 500):
                return "moved"  # it said "standing" but we are far from the last report (no speed from the GPS)
        if since >= self.rate(speed):
            return "time"
        return None

    def sent(self, now: float, course: float | None, position: tuple[float, float] | None) -> None:
        self.last_time, self.last_course, self.last_position = now, course, position

    def next_in(self, now: float, speed: float | None) -> float:
        if self.last_time is None:
            return 0.0
        return max(0.0, self.rate(speed) - (now - self.last_time))


def course_speed(course: float | None, speed_kmh: float | None) -> str:
    """APRS course/speed data extension "CSE/SPD" (degrees, knots), or "" when standing."""
    if speed_kmh is None or speed_kmh < 1 or course is None:
        return ""
    cse = round(course) % 360 or 360  # 000 means "unknown", north is 360
    return f"{cse:03d}/{min(999, round(speed_kmh / 1.852)):03d}"
