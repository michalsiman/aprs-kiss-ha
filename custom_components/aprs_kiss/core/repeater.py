"""Repeaters on the map: which stations are repeaters, and on what frequency they transmit.

Repeaters show up in APRS as the repeater symbol ("/r"), as objects named after their frequency
("439.350MO", "145.600-B") or with the frequency in the comment ("439.175MHz T077 -760", APRS 1.2
frequency format; SvxLink/EchoLink and D-Star/DMR gateways put "ER-OK0EB", "OK0PI  B" objects with
"439.27500MHz" in the comment).
"""

from __future__ import annotations

import re
from typing import Any

FREQ_RE = re.compile(r"(?<![\d.])(\d{2,4}\.\d{2,5})\s?MHz", re.I)
NAME_FREQ_RE = re.compile(r"^(\d{2,4}\.\d{1,5})")  # an object named after its frequency
SHIFT_RE = re.compile(r"(?:^|\s)(?:[+-]\d{3}\b|[+-]\d{1,2}\.\d+\s?MHz|T\d{3}\b|C\d{3}\b|Toff\b|R\d{2}[km]\b|1750)", re.I)
# a moving station telling where it listens ("145.500MHz" in APRSdroid, "QSY" on a Kenwood): not a repeater
MOBILE = set("><[bkuvjRUsY'XO=*afP")

BANDS = (  # (from MHz, to MHz, name)
    (28.0, 29.7, "10 m"), (50.0, 54.0, "6 m"), (70.0, 71.0, "4 m"), (144.0, 148.0, "2 m"),
    (219.0, 225.0, "1.25 m"), (420.0, 450.0, "70 cm"), (902.0, 928.0, "33 cm"), (1240.0, 1300.0, "23 cm"),
)
MODES = (("DMR", "DMR"), ("D-STAR", "D-Star"), ("DSTAR", "D-Star"), ("C4FM", "C4FM"), ("YSF", "C4FM"),
         ("FUSION", "C4FM"), ("NXDN", "NXDN"), ("P25", "P25"), ("TETRA", "TETRA"), ("M17", "M17"))


def band(mhz: float) -> str | None:
    for low, high, name in BANDS:
        if low <= mhz <= high:
            return name
    return None


def _plausible(value: str) -> float | None:
    try:
        mhz = float(value)
    except ValueError:
        return None
    return mhz if band(mhz) else None


def frequency(entry: dict[str, Any]) -> float | None:
    """The repeater's output frequency in MHz, from the object name or the comment."""
    if entry.get("object_of"):
        m = NAME_FREQ_RE.match(entry.get("call") or "")
        if m and (mhz := _plausible(m.group(1))):
            return mhz
    for text in (entry.get("comment"), entry.get("status")):
        if isinstance(text, str):
            for m in FREQ_RE.finditer(text):
                if mhz := _plausible(m.group(1)):
                    return mhz
    return None


def is_repeater(entry: dict[str, Any]) -> bool:
    if entry.get("symbol") == "r":
        return True  # the repeater symbol ("/r" antenna, also overlaid)
    if entry.get("symbol") in MOBILE and entry.get("symbol_table") == "/":
        return False
    if frequency(entry) is None:
        return False
    if entry.get("object_of"):
        return True  # an object with a frequency: what repeater lists and gateways send
    return bool(SHIFT_RE.search(entry.get("comment") or ""))  # a fixed station with offset or tone


def mode(entry: dict[str, Any]) -> str | None:
    text = f"{entry.get('call', '')} {entry.get('comment', '')}".upper()
    for key, name in MODES:
        if key in text:
            return name
    return None


def label(entry: dict[str, Any]) -> str | None:
    """"439.350 · 70 cm · DMR" for a repeater, None for anything else."""
    if not is_repeater(entry):
        return None
    mhz = frequency(entry)
    if mhz is None:
        return None
    text = f"{mhz:.4f}".rstrip("0")
    if len(text.split(".")[1]) < 3:
        text = f"{mhz:.3f}"
    parts = [text, band(mhz)]
    if m := mode(entry):
        parts.append(m)
    return " · ".join(p for p in parts if p)
