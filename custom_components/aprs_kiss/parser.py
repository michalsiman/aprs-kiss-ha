"""APRS packet parsing with aprslib, made safe for Home Assistant events."""

from __future__ import annotations

from typing import Any

import aprslib
from aprslib.exceptions import ParseError, UnknownFormat

KEEP = (
    "from", "to", "via", "format", "latitude", "longitude", "symbol", "symbol_table", "comment",
    "speed", "course", "altitude", "posambiguity", "messagecapable", "status", "addresse",
    "message_text", "msgNo", "response", "object_name", "alive", "weather", "telemetry", "mbits",
    "mtype", "timestamp", "raw_timestamp", "text",
)


def parse(tnc2: str) -> dict[str, Any]:
    """The packet as a plain dict; unknown formats keep at least sender and text."""
    try:
        packet = aprslib.parse(tnc2)
    except (ParseError, UnknownFormat) as err:
        src, _, rest = tnc2.partition(">")
        return {"from": src, "format": "unknown", "text": rest.partition(":")[2], "error": str(err)}
    out = _keep(packet)
    inner = packet.get("subpacket")
    if packet.get("format") == "thirdparty" and isinstance(inner, dict) and inner.get("from"):
        # "}" third-party traffic, typically an iGate putting an internet packet on the air:
        # the station that matters, its position or a message for us, is inside.
        out["thirdparty"] = {**_keep(inner), "raw": inner.get("raw", ""), "path": list(inner.get("path") or [])}
    return out


def _keep(packet: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in KEEP:
        if key in packet and packet[key] is not None:
            value = packet[key]
            if isinstance(value, bytes):
                value = value.decode("latin-1")
            out[key] = value
    return out
