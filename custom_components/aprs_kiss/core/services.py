"""Services on APRS-IS that answer an APRS message (from the registry at aprs.hemna.com).

Each is a callsign to write to, with the commands worth a button; the answer comes back as a message in that
conversation. Sent by radio like any message: an iGate in range passes it on.

- FIND: the callsign of a station → when and where it was last heard, through which iGate, its locator.
- REPEAT (RepeaterBook): "n [count] [band] [+filter]" → the repeaters nearest to our last position beacon,
  e.g. "n 3 70cm", "n 5 2m +echolink"; the band is 2m when left out, 1 repeater, 10 at most.
- WXNOW: "nearest" → the weather from the nearest weather station.
- UTC: "TIME" → the exact time.
- 9M2PJU-4: "satpass iss" (passes of a satellite over us), "riseset" (sun and moon), "whereami", "help".
- MAILMY (9M2PJU): "EMAIL <address> <text>", ended by "SEND" → an e-mail; 5 an hour.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    call: str
    key: str  # the description's message key
    commands: tuple[str, ...]  # put into the message field; "" = type it (a callsign, an address)


SERVICES = (
    Service("FIND", "svc_find", ("",)),
    Service("REPEAT", "svc_repeat", ("n 3 2m", "n 3 70cm", "n 3 2m +echolink")),
    Service("WXNOW", "svc_wxnow", ("nearest",)),
    Service("UTC", "svc_utc", ("TIME",)),
    Service("9M2PJU-4", "svc_sat", ("satpass iss", "riseset", "whereami", "help")),
    Service("MAILMY", "svc_mail", ("EMAIL ", "SEND")),
)
