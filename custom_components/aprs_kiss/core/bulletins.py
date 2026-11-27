"""APRS bulletins (APRS 1.01, chapter 14): messages to everybody, with no acknowledgement.

The addressee says what it is: BLN0–BLN9 a bulletin (news for the next few hours), BLNA–BLNZ an
announcement (something coming, kept for days), BLNn plus up to five characters a bulletin to a group
("BLN1WX", "BLN2CLUB"), NWS-… a weather service alert. The sender repeats it – often at first, then
less often – because nobody confirms it; a newer text with the same addressee replaces the older one.
"""

from __future__ import annotations

import re
import time
from typing import Any

from . import aprs

LINES = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GROUP_RE = re.compile(r"[A-Z0-9]{0,5}")
MAX_TEXT = aprs.MAX_MESSAGE_TEXT
# How long received ones stay on the board after they were last heard.
KEEP_SECONDS = {"bulletin": 12 * 3600, "group": 12 * 3600, "announcement": 4 * 86400, "nws": 12 * 3600}
MAX_KEPT = 300
# Our own: the gaps between the copies (seconds) – quick at first for those who missed it, then steady.
FIRST_GAPS = (60, 300, 600)
STEADY_GAP = {"bulletin": 1200, "announcement": 3600}
HOURS = (1, 4, 12, 24, 48)  # how long ours goes out (picked when sending)
DEFAULT_HOURS = {"bulletin": 4, "announcement": 24}


def addressee(line: str, group: str = "") -> str:
    """'BLN1', 'BLNA', 'BLN2WX'."""
    line, group = line.strip().upper(), group.strip().upper()
    if len(line) != 1 or line not in LINES:
        raise ValueError("The bulletin line is one character, 0–9 or A–Z")
    if not GROUP_RE.fullmatch(group):
        raise ValueError("The group is up to five letters or digits")
    if group and not line.isdigit():
        raise ValueError("A group bulletin has a digit (BLN0–BLN9)")
    return f"BLN{line}{group}"


def kind_of(addr: str) -> str:
    """'bulletin', 'announcement', 'group', 'nws' or '' (not a bulletin)."""
    addr = addr.strip().upper()
    if addr.startswith("NWS-") or addr.startswith("NWS_"):
        return "nws"
    if not addr.startswith("BLN") or len(addr) < 4 or addr[3] not in LINES:
        return ""
    if len(addr) > 4:
        return "group" if addr[3].isdigit() and GROUP_RE.fullmatch(addr[4:]) else ""
    return "bulletin" if addr[3].isdigit() else "announcement"


def from_packet(packet: dict[str, Any]) -> dict[str, Any] | None:
    """A received bulletin as {"from", "addressee", "kind", "line", "group", "text"}, or None."""
    fmt = packet.get("format")
    if fmt in ("bulletin", "announcement", "group-bulletin"):
        line = str(packet.get("bid") or packet.get("aid") or "")
        group = str(packet.get("identifier") or "").strip().upper()
        if not line:
            return None
        addr = f"BLN{line}{group}"
    elif fmt == "message" and kind_of(packet.get("addresse") or "") == "nws":
        addr, line, group = packet["addresse"].strip().upper(), "", ""
    else:
        return None
    sender = str(packet.get("from") or "").upper()
    text = aprs.fix_mojibake(str(packet.get("message_text") or "")).strip()
    if not sender or not text:
        return None
    text = re.sub(r"\{[A-Za-z0-9]{1,5}\}?$", "", text).rstrip()  # a message number some senders add anyway
    return {"from": sender, "addressee": addr, "kind": kind_of(addr), "line": line, "group": group, "text": text}


class Board:
    """The bulletins heard (one per sender and addressee: the newest text) and our own, still going out."""

    def __init__(self) -> None:
        self.heard: list[dict[str, Any]] = []
        self.mine: list[dict[str, Any]] = []

    # ─── heard ───────────────────────────────────────────────────────────

    def add(self, item: dict[str, Any], now: float, via: str, km: float | None = None) -> dict[str, Any] | None:
        """A bulletin heard; returns the entry when it is new or its text changed (worth showing), else None
        (a repeat: only its time moves)."""
        for e in self.heard:
            if e["from"] == item["from"] and e["addressee"] == item["addressee"]:
                e["last"], e["count"] = now, e.get("count", 1) + 1
                if via == "radio":
                    e["via"] = "radio"  # heard by radio once: it is local
                if km is not None:
                    e["km"] = km
                if e["text"] == item["text"]:
                    return None
                e.update(text=item["text"], time=now, read=False)
                self.heard.remove(e)
                self.heard.append(e)
                return e
        entry = {**item, "time": now, "last": now, "count": 1, "via": via, "read": False}
        if km is not None:
            entry["km"] = km
        self.heard.append(entry)
        del self.heard[:-MAX_KEPT]
        return entry

    def expire(self, now: float) -> bool:
        keep = [e for e in self.heard if now - e.get("last", e.get("time", 0)) < KEEP_SECONDS.get(e.get("kind"), 43200)]
        changed = len(keep) != len(self.heard)
        self.heard = keep
        mine = [m for m in self.mine if m.get("until", 0) > now]
        changed |= len(mine) != len(self.mine)
        self.mine = mine
        return changed

    def remove(self, sender: str, addr: str) -> None:
        self.heard = [e for e in self.heard if not (e["from"] == sender and e["addressee"] == addr)]

    @staticmethod
    def shown(entry: dict[str, Any], km_limit: int) -> bool:
        """On the board with this distance limit (0 = all): heard by radio – near by nature – or the sender
        known to be within the limit."""
        if not km_limit or entry.get("via") == "radio":
            return True
        km = entry.get("km")
        return km is not None and km <= km_limit

    def unread(self, km_limit: int) -> int:
        return sum(1 for e in self.heard if not e.get("read") and self.shown(e, km_limit))

    def mark_read(self) -> bool:
        changed = False
        for e in self.heard:
            if not e.get("read"):
                e["read"], changed = True, True
        return changed

    # ─── ours ────────────────────────────────────────────────────────────

    def start(self, addr: str, text: str, via: str, hours: float, now: float) -> dict[str, Any]:
        """Our bulletin, from now for `hours` (replaces ours with the same addressee)."""
        text = aprs.clean_text(text, MAX_TEXT).strip()
        if not text:
            raise ValueError("The bulletin has no text")
        if not 0 < hours <= 7 * 24:
            raise ValueError("Hours out of range")
        self.mine = [m for m in self.mine if m["addressee"] != addr]
        entry = {"addressee": addr, "kind": kind_of(addr), "text": text, "via": via, "created": now,
                 "until": now + hours * 3600, "sent": 0, "next": now, "last_sent": None}
        self.mine.append(entry)
        return entry

    def stop(self, addr: str) -> None:
        self.mine = [m for m in self.mine if m["addressee"] != addr]

    def due(self, now: float) -> list[dict[str, Any]]:
        return [m for m in self.mine if m["next"] <= now < m["until"]]

    @staticmethod
    def gap(entry: dict[str, Any]) -> float:
        """Seconds to the next copy after `entry["sent"]` copies."""
        n = entry["sent"]
        if n - 1 < len(FIRST_GAPS):
            return FIRST_GAPS[max(0, n - 1)]
        return STEADY_GAP["announcement" if entry.get("kind") == "announcement" else "bulletin"]

    def sent(self, entry: dict[str, Any], now: float) -> None:
        entry["sent"] += 1
        entry["last_sent"] = now
        entry["next"] = now + self.gap(entry)

    def failed(self, entry: dict[str, Any], now: float) -> None:
        """Not sent (transmitting off, the limit): tried again in a minute."""
        entry["next"] = now + 60

    # ─── storage ─────────────────────────────────────────────────────────

    def state(self) -> dict[str, Any]:
        return {"heard": list(self.heard), "mine": list(self.mine)}

    def load(self, stored: dict[str, Any] | None, now: float | None = None) -> None:
        stored = stored or {}
        self.heard = [e for e in stored.get("heard", []) if isinstance(e, dict) and e.get("from")]
        self.mine = [m for m in stored.get("mine", []) if isinstance(m, dict) and m.get("addressee")]
        self.expire(time.time() if now is None else now)
