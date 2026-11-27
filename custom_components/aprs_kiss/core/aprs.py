"""Building APRS information fields (APRS 1.0.1 / 1.2).

Parsing of received packets is left to aprslib (see parser.py); this module
only builds what we send: messages, acks, positions and status reports.
"""

from __future__ import annotations

import math
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


# Position ambiguity (APRS 1.01, chapter 6): the last digits of the minutes left out, the position only
# says the square it is in. Level -> the hidden part in minutes (0.1', 1', 10', a whole degree) and about
# how far the real position may be from what others see.
AMBIGUITY_MINUTES = {0: 0.01, 1: 0.1, 2: 1.0, 3: 10.0, 4: 60.0}
AMBIGUITY_KM = {0: 0.0, 1: 0.2, 2: 2.0, 3: 20.0, 4: 110.0}


def _cut(value: float, level: int) -> float:
    """|value| in degrees cut down to the square of `level` (its corner, never rounded up into the next)."""
    step = AMBIGUITY_MINUTES[level] / 60
    return math.floor(abs(value) / step + 1e-9) * step


def blur(lat: float, lon: float, level: int) -> tuple[float, float]:
    """The middle of the square an ambiguous position stands for (what a map shows; for TAK, which has
    no ambiguity of its own). Level 0: as it is."""
    if not level:
        return lat, lon
    half = AMBIGUITY_MINUTES[level] / 120
    return (math.copysign(min(_cut(lat, level) + half, 90.0), lat),
            math.copysign(min(_cut(lon, level) + half, 180.0), lon))


def _hide(text: str, level: int) -> str:
    """'4946.12N' with the last `level` digits as spaces: '4946.1 N', '4946.  N', '494 .  N', '49  .  N'."""
    chars, hidden = list(text), 0
    for i in range(len(chars) - 2, -1, -1):
        if hidden == level:
            break
        if chars[i].isdigit():
            chars[i], hidden = " ", hidden + 1
    return "".join(chars)


def position(lat: float, lon: float, symbol: str = "/-", comment: str = "", messaging: bool = True,
             ambiguity: int = 0) -> str:
    """Uncompressed position without timestamp: '=DDMM.mmN/DDDMM.mmE-comment'.

    `symbol` is the table character and the symbol code, e.g. '/-' (house),
    '/>' (car), '/[' (person). '=' says the station can receive messages.
    `ambiguity` 1–4: the position less exact (see AMBIGUITY_MINUTES), the hidden digits sent as spaces.
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Position out of range")
    if len(symbol) != 2:
        raise ValueError("Symbol must be two characters: table and code")
    if ambiguity not in AMBIGUITY_MINUTES:
        raise ValueError("Ambiguity is 0–4")
    kind = "=" if messaging else "!"
    if ambiguity:
        lat_t = _hide(_lat(math.copysign(_cut(lat, ambiguity), lat)), ambiguity)
        lon_t = _hide(_lon(math.copysign(_cut(lon, ambiguity), lon)), ambiguity)
    else:
        lat_t, lon_t = _lat(lat), _lon(lon)
    return f"{kind}{lat_t}{symbol[0]}{lon_t}{symbol[1]}{clean_text(comment, MAX_COMMENT)}"


def fix_mojibake(text: str) -> str:
    """UTF-8 read as Latin-1 (or cp1252) somewhere on the way ("TURKÄ°YE" for "TURKİYE"): put it right.
    Only when the whole text then reads as UTF-8 and something changed; anything else stays as it was."""
    if not any("\u00c2" <= c <= "\u00f4" for c in text):
        return text
    for wrong in ("latin-1", "cp1252"):  # cp1252: Windows' Latin-1 ("ÄŸ" for "ğ")
        try:
            return text.encode(wrong).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return text


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


# ─── Mic-E: the position packed into the destination address (shorter on air) ─────

# The status (message bits A, B, C – 1 = 'P'…'Y' in the destination's first three characters).
MIC_E_STATUS = {
    "off_duty": "111", "en_route": "110", "in_service": "101", "returning": "100",
    "committed": "011", "special": "010", "priority": "001", "emergency": "000",
}


def _mic_e_char(digit: int, flag: bool) -> str:
    return chr(ord("P") + digit) if flag else str(digit)


def _b91(value: int, width: int) -> str:
    out = ""
    for _ in range(width):
        out = chr(33 + value % 91) + out
        value //= 91
    return out


def mic_e(lat: float, lon: float, symbol: str = "/>", status: str = "en_route", course: float | None = None,
          speed_kmh: float | None = None, altitude_m: float | None = None, comment: str = "",
          ambiguity: int = 0) -> tuple[str, str]:
    """(destination, information field) of a Mic-E position (APRS 1.01, chapter 10): the latitude, the
    status ("emergency" among them) and N/S, W/E and the longitude offset go into the destination; the
    longitude, speed, course and symbol into 8 bytes of the information field; the altitude as base-91 'xxx}'."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Position out of range")
    if len(symbol) != 2:
        raise ValueError("Symbol must be two characters: table and code")
    if ambiguity not in AMBIGUITY_MINUTES:
        raise ValueError("Ambiguity is 0–4")
    bits = MIC_E_STATUS[status]
    alat, alon = (_cut(lat, ambiguity), _cut(lon, ambiguity)) if ambiguity else (abs(lat), abs(lon))
    hundredths = min(round(alat * 6000), 90 * 6000 - 1)  # in 1/100 minutes
    digits = f"{hundredths // 6000:02d}{hundredths % 6000 // 100:02d}{hundredths % 100:02d}"
    lon_h = min(round(alon * 6000), 180 * 6000 - 1)
    deg, mins, hund = lon_h // 6000, lon_h % 6000 // 100, lon_h % 100
    offset = deg < 10 or deg >= 100
    flags = (bits[0] == "1", bits[1] == "1", bits[2] == "1", lat >= 0, offset, lon < 0)
    # a hidden digit: 'Z' (a space with the flag set) or 'L' (a space without it); the receiver hides the
    # same digits of the longitude (cut down above, so nothing more exact goes out)
    dest = "".join(("Z" if flag else "L") if i >= 6 - ambiguity else _mic_e_char(int(d), flag)
                   for i, (d, flag) in enumerate(zip(digits, flags)))
    if deg < 10:
        d = deg + 90
    elif deg < 100:
        d = deg
    elif deg < 110:
        d = deg - 20
    else:
        d = deg - 100
    m = mins + 60 if mins < 10 else mins
    knots = 0 if speed_kmh is None else min(799, max(0, round(speed_kmh / 1.852)))
    crs = 0 if course is None else round(course) % 360
    tens = knots // 10
    sp = tens + 80 if tens < 20 else tens
    dc = (knots % 10) * 10 + crs // 100
    if dc < 4:
        dc += 4  # course + 400 (read back as is): keeps the byte out of the control characters
    se = crs % 100
    info = "`" + "".join(chr(v + 28) for v in (d, m, hund, sp, dc, se)) + symbol[1] + symbol[0]
    if altitude_m is not None:
        info += _b91(max(0, min(round(altitude_m) + 10000, 91 ** 3 - 1)), 3) + "}"
    return dest, info + clean_text(comment, MAX_COMMENT)
