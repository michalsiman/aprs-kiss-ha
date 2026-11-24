"""Building APRS information fields (APRS 1.0.1 / 1.2).

Parsing of received packets is left to aprslib (see parser.py); this module
only builds what we send: messages, acks, positions and status reports.
"""

from __future__ import annotations

import re

# APRS messages: at most 67 characters of text; no | ~ { in the text.
MAX_MESSAGE_TEXT = 67
MAX_STATUS_TEXT = 62
MAX_COMMENT = 43

# Software tocall for this integration. APRS assigns tocalls to software;
# APZ* is the experimental range, free to use.
TOCALL = "APZHAK"

_FORBIDDEN = re.compile(r"[|~{\r\n]")


def clean_text(text: str, limit: int) -> str:
    """Printable ASCII-ish text without APRS control characters, cut to `limit`."""
    text = _FORBIDDEN.sub("", text).strip()
    return text[:limit]


def addressee(call: str) -> str:
    """The 9-character addressee field of a message."""
    return call.upper().ljust(9)[:9]


def message(to: str, text: str, msg_id: str | None) -> str:
    """':ADDRESSEE:text{id'."""
    body = f":{addressee(to)}:{clean_text(text, MAX_MESSAGE_TEXT)}"
    return body + (f"{{{msg_id}" if msg_id else "")


def ack(to: str, msg_id: str) -> str:
    return f":{addressee(to)}:ack{msg_id}"


def reject(to: str, msg_id: str) -> str:
    return f":{addressee(to)}:rej{msg_id}"


def status(text: str) -> str:
    return ">" + clean_text(text, MAX_STATUS_TEXT)


def _lat(lat: float) -> str:
    hemi = "N" if lat >= 0 else "S"
    lat = abs(lat)
    deg = int(lat)
    minutes = (lat - deg) * 60
    if round(minutes, 2) >= 60:
        deg, minutes = deg + 1, 0.0
    return f"{deg:02d}{minutes:05.2f}{hemi}"


def _lon(lon: float) -> str:
    hemi = "E" if lon >= 0 else "W"
    lon = abs(lon)
    deg = int(lon)
    minutes = (lon - deg) * 60
    if round(minutes, 2) >= 60:
        deg, minutes = deg + 1, 0.0
    return f"{deg:03d}{minutes:05.2f}{hemi}"


def position(lat: float, lon: float, symbol: str = "/-", comment: str = "", messaging: bool = True) -> str:
    """Uncompressed position without timestamp: '=DDMM.mmN/DDDMM.mmE-comment'.

    `symbol` is the table character and the symbol code, e.g. '/-' (house),
    '/>' (car), '/[' (person). '=' says the station can receive messages.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Position out of range")
    if len(symbol) != 2:
        raise ValueError("Symbol must be two characters: table and code")
    kind = "=" if messaging else "!"
    return f"{kind}{_lat(lat)}{symbol[0]}{_lon(lon)}{symbol[1]}{clean_text(comment, MAX_COMMENT)}"


def message_id(counter: int) -> str:
    """Message number, 1–5 alphanumeric characters (APRS 1.0: up to 5)."""
    return str(counter % 100000)


MAX_MESSAGE_PARTS = 5


def message_parts(text: str, limit: int = MAX_MESSAGE_TEXT, max_parts: int = MAX_MESSAGE_PARTS) -> list[str]:
    """A text longer than one APRS message as several, each ending " 1/3", " 2/3", … (split between
    words where it can). A short text is one message, as it is. Too long: cut after max_parts."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return [text] if text else []
    for n in range(2, max_parts + 1):
        room = limit - len(f" {n}/{n}")
        parts, rest = [], text
        while rest and len(parts) < n:
            if len(rest) <= room:
                cut = len(rest)
            else:
                gap = rest.rfind(" ", 0, room + 1)
                cut = gap if gap > room // 2 else room
            parts.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if not rest or n == max_parts:
            return [f"{p} {i}/{len(parts)}" for i, p in enumerate(parts, 1)]
    return []
