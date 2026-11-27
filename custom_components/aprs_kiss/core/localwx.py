"""The weather around us: the average of the weather stations heard near our position.

Shown in the map's corner: temperature, and humidity and pressure when some station sends them.
Only stations within RADIUS_KM and reports younger than MAX_AGE_SECONDS count.
"""

from __future__ import annotations

from typing import Any

from .tracker import distance_m

RADIUS_KM = 20
MAX_AGE_SECONDS = 2 * 3600
REFRESH_SECONDS = 5 * 60  # the map asks again this often
FIELDS = ("temperature", "humidity", "pressure")


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def around(heard: dict[str, dict[str, Any]], here: tuple[float, float] | None, now: float,
           radius_km: float = RADIUS_KM, max_age: float = MAX_AGE_SECONDS) -> dict[str, Any] | None:
    """{"temperature": °C, "humidity": %, "pressure": hPa (each only when some station sends it),
    "stations": how many stations, "oldest": seconds since the oldest report used, "list": each station used,
    nearest first ({"call", "km", "age", "temperature", "humidity", "pressure"})}; None when no station
    near enough has sent a temperature recently (or we do not know where we are)."""
    if not here:
        return None
    sums: dict[str, list[float]] = {k: [] for k in FIELDS}
    stations, oldest = 0, 0.0
    used: list[dict[str, Any]] = []
    for call, entry in heard.items():
        wx = entry.get("weather")
        if not isinstance(wx, dict) or _number(wx.get("temperature")) is None:
            continue
        at = entry.get("weather_at") or entry.get("last_heard") or 0
        if now - at > max_age:
            continue
        lat, lon = entry.get("latitude"), entry.get("longitude")
        if lat is None or lon is None:
            continue
        metres = distance_m(here[0], here[1], lat, lon)
        if metres > radius_km * 1000:
            continue
        stations += 1
        oldest = max(oldest, now - at)
        one: dict[str, Any] = {"call": entry.get("call") or call, "km": metres / 1000, "age": now - at}
        for k in FIELDS:
            value = _number(wx.get(k))
            if value is not None and not (k == "humidity" and not 0 < value <= 100) \
                    and not (k == "pressure" and not 800 <= value <= 1100):
                sums[k].append(value)
                one[k] = value
        used.append(one)
    if not stations:
        return None
    result: dict[str, Any] = {k: sum(v) / len(v) for k, v in sums.items() if v}
    result["stations"] = stations
    result["oldest"] = oldest
    result["list"] = sorted(used, key=lambda s: s["km"])
    return result
