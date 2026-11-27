"""#APRSThursday: a weekly net run through the ANSRVR group server.

Every Thursday, 00:00-23:59 UTC, stations send an APRS message to ANSRVR with the text
"CQ HOTG <text>". The server acknowledges it, answers "Message has been sent to HOTG" and
passes the text on, as an unnumbered message from the original sender, to every station that
sent to HOTG in the last 12 hours. "U HOTG" leaves the group. One CQ per 30 minutes.
See https://aprs.to/events/aprs_thursday/about/ and https://aprs-is.net/CQSrvr.aspx.
"""

from __future__ import annotations

import datetime as dt

from . import aprs

SERVER = "ANSRVR"
GROUP = "HOTG"
PREFIX = f"CQ {GROUP} "
MAX_TEXT = aprs.MAX_MESSAGE_TEXT - len(PREFIX)  # room left for the user's own words
MEMBER_SECONDS = 12 * 3600  # the server forgets a station after 12 hours without a CQ
CQ_INTERVAL = 30 * 60  # the server takes one CQ per station every 30 minutes
MAP_URL = "https://aprs.to/events/aprs_thursday/"
THURSDAY = 3  # datetime.weekday()


def _utc(ts: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc)


def is_active(now: float) -> bool:
    """True during Thursday in UTC."""
    return _utc(now).weekday() == THURSDAY


def window(now: float) -> tuple[float, float]:
    """Start and end (timestamps) of the running net, or of the next one."""
    day = _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    start = day + dt.timedelta(days=(THURSDAY - day.weekday()) % 7)
    if start + dt.timedelta(days=1) <= _utc(now):
        start += dt.timedelta(days=7)
    return start.timestamp(), (start + dt.timedelta(days=1)).timestamp()


def compose(text: str) -> str:
    """The message text for ANSRVR: the group prefix and the user's words, cut to fit."""
    return PREFIX + " ".join(text.split())[:MAX_TEXT]


RELAYED = f"N:{GROUP}"  # how ANSRVR passes on another member's message: "N:HOTG Hello from …"


def _group_prefix(text: str) -> str | None:
    up = text.strip().upper()
    for prefix in (PREFIX.strip(), RELAYED):
        if up.startswith(prefix) and (len(up) == len(prefix) or not up[len(prefix)].isalnum()):
            return prefix
    return None


def is_group_text(text: str) -> bool:
    """A HOTG message: one relayed from another station ("N:HOTG …"), or our own ("CQ HOTG …")."""
    return _group_prefix(text) is not None


def strip_prefix(text: str) -> str:
    prefix = _group_prefix(text)
    return text.strip()[len(prefix):].strip() if prefix else text.strip()


def is_server(call: str) -> bool:
    return call.split("-")[0].upper() == SERVER
