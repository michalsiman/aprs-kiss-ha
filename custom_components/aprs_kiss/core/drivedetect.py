"""You seem to be driving, with the tracker off: the phone app offers to switch it on.

From the GPS fixes: a speed of DRIVE_KMH or more for DRIVE_SECONDS, or (a phone that gives no speed)
DRIVE_METRES covered within DRIVE_WINDOW. A walk across the room or a jumpy fix does not count.
After asking, not again for SNOOZE_SECONDS (an hour), stops on the way or not. "Not today" is kept by the app.
"""

from __future__ import annotations

from collections import deque

from .tracker import distance_m

DRIVE_KMH = 10.0
DRIVE_SECONDS = 60
DRIVE_METRES = 400
DRIVE_WINDOW = 180
STANDING_KMH = 3.0
SNOOZE_SECONDS = 3600


class DriveDetector:
    def __init__(self, asked_at: float | None = None) -> None:
        self.moving_since: float | None = None
        self.asked_at = asked_at  # the last question, also from an earlier detector (tracker switched on and off)
        self.points: deque[tuple[float, float, float]] = deque()

    def update(self, now: float, lat: float, lon: float, speed_kmh: float | None) -> bool:
        """A new fix; True when it is time to ask."""
        self.points.append((now, lat, lon))
        while self.points and now - self.points[0][0] > DRIVE_WINDOW:
            self.points.popleft()
        first = self.points[0]
        covered = distance_m(first[1], first[2], lat, lon) if len(self.points) > 1 else 0.0
        fast = speed_kmh is not None and speed_kmh >= DRIVE_KMH
        standing = (speed_kmh is not None and speed_kmh < STANDING_KMH) or (speed_kmh is None and covered < 50
                                                                           and now - first[0] >= 60)
        if fast or covered >= DRIVE_METRES:
            if self.moving_since is None:
                self.moving_since = now
        elif standing:
            self.moving_since = None
        if self.asked_at is not None and now - self.asked_at < SNOOZE_SECONDS:
            return False
        driving = (self.moving_since is not None and now - self.moving_since >= DRIVE_SECONDS) or covered >= DRIVE_METRES
        if driving:
            self.asked_at = now
            return True
        return False
