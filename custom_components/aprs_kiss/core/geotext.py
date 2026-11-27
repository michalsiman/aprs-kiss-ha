"""Positions written in text (chat, APRS messages): finding them, and writing one.

Found are the ways people write a position: decimal degrees ("49.7475, 13.3776", "49.7475N 13.3776E"),
degrees and minutes or degrees, minutes and seconds with N/S E/W ("49°44.85'N 13°22.66'E",
"49°44'51"N 13°22'39"E"), APRS's own ("4944.85N/01322.66E") and a Maidenhead locator of six characters
("JO60UF"). Written is "QTH 49.74750, 13.37760": short, plain ASCII (an APRS message has 67 characters)
and understood by anyone.
"""

from __future__ import annotations

import re

_NUM = r"(\d{1,3}(?:[.,]\d+)?)"
_DECIMAL = re.compile(r"(?<![\w.])(-?\d{1,2}\.\d{3,})\s*°?\s*([NSns])?\s*[,;/ ]\s*(-?\d{1,3}\.\d{3,})\s*°?\s*([EWew])?(?![\w.])")
_DMS = re.compile(r"(\d{1,2})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|″|'')\s*([NSns])[,;/ ]*\s*"
                  r"(\d{1,3})\s*°\s*(\d{1,2})\s*['′]\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:\"|″|'')\s*([EWew])")
_DM = re.compile(r"(\d{1,2})\s*°\s*(\d{1,2}(?:[.,]\d+)?)\s*['′]?\s*([NSns])[,;/ ]*\s*(\d{1,3})\s*°\s*(\d{1,2}(?:[.,]\d+)?)\s*['′]?\s*([EWew])")
_APRS = re.compile(r"(?<!\d)(\d{2})(\d{2}\.\d{1,2})\s*([NS])\s*[/\\ ,]?\s*(\d{3})(\d{2}\.\d{1,2})\s*([EW])")
_LOCATOR = re.compile(r"(?<![A-Za-z0-9])([A-Ra-r]{2}\d{2}[A-Xa-x]{2})(?![A-Za-z0-9])")


def _f(text: str) -> float:
    return float(text.replace(",", "."))


def _ok(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def locator_to_position(loc: str) -> tuple[float, float]:
    """The middle of a six-character Maidenhead square."""
    loc = loc.upper()
    lon = (ord(loc[0]) - 65) * 20 + int(loc[2]) * 2 + (ord(loc[4]) - 65) / 12 + 1 / 24 - 180
    lat = (ord(loc[1]) - 65) * 10 + int(loc[3]) + (ord(loc[5]) - 65) / 24 + 1 / 48 - 90
    return round(lat, 5), round(lon, 5)


def find_positions(text: str) -> list[tuple[float, float]]:
    """Every position written in the text, in the order they come."""
    found: list[tuple[int, float, float]] = []
    taken: list[tuple[int, int]] = []

    def add(m: re.Match, lat: float, lon: float) -> None:
        if not _ok(lat, lon) or any(a < m.end() and m.start() < b for a, b in taken):
            return
        taken.append((m.start(), m.end()))
        found.append((m.start(), round(lat, 6), round(lon, 6)))

    for m in _DMS.finditer(text):
        lat = int(m[1]) + int(m[2]) / 60 + _f(m[3]) / 3600
        lon = int(m[5]) + int(m[6]) / 60 + _f(m[7]) / 3600
        add(m, -lat if m[4].upper() == "S" else lat, -lon if m[8].upper() == "W" else lon)
    for m in _DM.finditer(text):
        lat, lon = int(m[1]) + _f(m[2]) / 60, int(m[4]) + _f(m[5]) / 60
        add(m, -lat if m[3].upper() == "S" else lat, -lon if m[6].upper() == "W" else lon)
    for m in _APRS.finditer(text):
        lat, lon = int(m[1]) + float(m[2]) / 60, int(m[4]) + float(m[5]) / 60
        add(m, -lat if m[3] == "S" else lat, -lon if m[6] == "W" else lon)
    for m in _DECIMAL.finditer(text):
        lat, lon = float(m[1]), float(m[3])
        if m[2] and m[2].upper() == "S":
            lat = -abs(lat)
        if m[4] and m[4].upper() == "W":
            lon = -abs(lon)
        add(m, lat, lon)
    for m in _LOCATOR.finditer(text):
        if any(c.isdigit() for c in m[1][:2]) or not m[1][2:4].isdigit():
            continue
        add(m, *locator_to_position(m[1]))
    return [(lat, lon) for _, lat, lon in sorted(found)]


def write_position(lat: float, lon: float) -> str:
    return f"QTH {lat:.5f}, {lon:.5f}"


def position_to_locator(lat: float, lon: float) -> str:
    """The six-character Maidenhead locator of a position ("JO70XQ")."""
    lon = min(max(lon + 180, 0), 359.999999)
    lat = min(max(lat + 90, 0), 179.999999)
    return (chr(65 + int(lon // 20)) + chr(65 + int(lat // 10)) + str(int(lon % 20 // 2)) + str(int(lat % 10))
            + chr(97 + int(lon % 2 * 12)) + chr(97 + int(lat % 1 * 24))).upper()


# A radio amateur's callsign, maybe with an SSID: a prefix with a letter (OK, G, 2E, 9A…), a digit, 1–4 letters.
_CALL = re.compile(r"(?<![A-Z0-9/])((?:[A-Z]{1,2}|[0-9][A-Z]|[A-Z][0-9])[0-9][A-Z]{1,4}(?:-[0-9]{1,2})?)(?![A-Z0-9])",
                   re.IGNORECASE)


def find_callsigns(text: str) -> list[str]:
    """The callsigns a text mentions ("OK6DJ-6 11/25 7.52km WSW" → ["OK6DJ-6"]), upper case, each once,
    in the order they come."""
    seen: list[str] = []
    for m in _CALL.finditer(text or ""):
        call = m.group(1).upper()
        if call not in seen:
            seen.append(call)
    return seen


def resolve_callsign(call: str, heard: dict) -> str | None:
    """The heard station a mentioned callsign means, with a position: the callsign itself, or (said without
    the SSID, "OK1FRN") the most recently heard station with that base; None when none is known."""
    def placed(c: str) -> bool:
        e = heard.get(c)
        return bool(e) and e.get("latitude") is not None and e.get("longitude") is not None

    if placed(call):
        return call
    if "-" in call:
        return None
    best, when = None, -1.0
    for c, e in heard.items():
        if c.upper().split("-")[0] == call and placed(c) and (e.get("last_heard") or 0) > when:
            best, when = c, e.get("last_heard") or 0
    return best


def place_links(lat: float, lon: float, label: str = "") -> dict[str, str]:
    """Ways to hand a place to other apps: "geo" (Android: any map or navigation app – Google Maps,
    Mapy.com, Waze, OsmAnd – the system asks which), "apple" (iPhone: Apple Maps, navigating there),
    "osm" (a web page with the place), "text" (to share: the label, the coordinates, the locator, the link)."""
    from urllib.parse import quote  # noqa: PLC0415

    ll = f"{lat:.5f},{lon:.5f}"
    name = quote(label.replace("(", " ").replace(")", " ").strip()) if label else ""
    osm = f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map=16/{lat:.5f}/{lon:.5f}"
    head = f"{label}: " if label else ""
    return {
        "geo": f"geo:{ll}?q={ll}" + (f"({name})" if name else ""),
        "apple": f"https://maps.apple.com/?daddr={ll}" + (f"&q={name}" if name else ""),
        "osm": osm,
        "text": f"{head}{lat:.5f}, {lon:.5f} ({position_to_locator(lat, lon)})\n{osm}",
    }
