"""APRS digipeater (the "New-N paradigm", as Direwolf and most APRS digipeaters do it).

What gets repeated, looking at the first path entry not yet used (no H bit):

- our own callsign or one of our aliases (e.g. RELAY): any frame, the entry becomes MYCALL* (H bit);
- WIDE1-1 (mode "fillin" or "wide"): becomes MYCALL* – the fill-in digipeater of home stations;
- WIDEn-N, n = 2…max_hops (mode "wide"): MYCALL* is inserted before it and N goes down by one;
  at N = 0 the entry becomes WIDEn* (used up). WIDE2-2 -> MYCALL*,WIDE2-1; WIDE2-1 -> MYCALL*,WIDE2*.
  Paths asking for more hops than max_hops (WIDE7-7 …) are not repeated.

Never repeated: our own frames, frames we already repeated (our call with the H bit in the path),
and the same frame (source, destination, information) again within DEDUPE_SECONDS.
"""

from __future__ import annotations

import re
import time
from dataclasses import replace

from .ax25 import Address, Frame

DEDUPE_SECONDS = 30.0
MAX_PATH = 8  # AX.25 allows 8 digipeaters
MODES = ("off", "fillin", "wide")
_WIDE = re.compile(r"WIDE([1-7])$")


def parse_aliases(text: str) -> list[Address]:
    out = []
    for item in (text or "").replace(";", ",").replace(" ", ",").split(","):
        if item.strip():
            try:
                out.append(Address.parse(item))
            except ValueError:
                continue
    return out


def _same(a: Address, b: Address) -> bool:
    return a.call == b.call and a.ssid == b.ssid


def repeat(frame: Frame, me: Address, mode: str, aliases: list[Address] = (), max_hops: int = 2) -> Frame | None:
    """The frame to send on, or None when this digipeater does not repeat it."""
    if mode not in MODES or _same(frame.source, me):
        return None
    if any(d.repeated and _same(d, me) for d in frame.path):
        return None  # it went through us already
    index = next((i for i, d in enumerate(frame.path) if not d.repeated), None)
    if index is None:
        return None
    nxt = frame.path[index]
    used_me = Address(me.call, me.ssid, True)
    path = list(frame.path)
    if _same(nxt, me) or any(_same(nxt, a) for a in aliases):
        path[index] = used_me  # addressed to us by name: any frame, also connected mode
        return replace(frame, path=path)
    if mode == "off" or not frame.is_ui:
        return None
    m = _WIDE.match(nxt.call)
    if not m:
        return None
    n, remaining = int(m.group(1)), nxt.ssid
    if not 1 <= remaining <= n:
        return None
    if n == 1:
        path[index] = used_me  # WIDE1-1: the fill-in digipeater
        return replace(frame, path=path)
    if mode != "wide" or n > max_hops:
        return None
    left = remaining - 1
    rest = Address(nxt.call, left, left == 0)  # WIDEn-(N-1), or WIDEn* when used up
    if len(path) >= MAX_PATH:
        path[index] = rest if left else used_me  # no room to trace our call
    else:
        path[index:index + 1] = [used_me, rest]
    return replace(frame, path=path)


class Dedupe:
    """Remembers what was repeated, so the same frame heard again from another digipeater is not."""

    def __init__(self, seconds: float = DEDUPE_SECONDS) -> None:
        self.seconds = seconds
        self._seen: dict[tuple, float] = {}

    def fresh(self, frame: Frame, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._seen = {k: t for k, t in self._seen.items() if now - t < self.seconds}
        key = (frame.source.call, frame.source.ssid, frame.destination.call, frame.destination.ssid, frame.info)
        if key in self._seen:
            return False
        self._seen[key] = now
        return True
