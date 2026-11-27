"""A received packet in a few words, for lists of frames (the station server's display): its kind and what
it says."""

from __future__ import annotations

from typing import Any

KINDS = {
    "uncompressed": "position", "compressed": "position", "mic-e": "mic_e", "object": "object", "item": "item",
    "message": "message", "status": "status", "wx": "weather", "telemetry-message": "telemetry",
    "thirdparty": "thirdparty", "bulletin": "bulletin", "announcement": "bulletin", "group-bulletin": "bulletin",
}


def kind(packet: dict[str, Any]) -> str:
    """'position', 'mic_e', 'object', 'item', 'message', 'status', 'weather', 'telemetry', 'thirdparty',
    'bulletin' or 'other'."""
    fmt = packet.get("format") or ""
    if packet.get("weather") and fmt in ("uncompressed", "compressed", "wx"):
        return "weather"
    if packet.get("telemetry"):
        return "telemetry"
    return KINDS.get(fmt, "other")


def _place(packet: dict[str, Any]) -> str:
    lat, lon = packet.get("latitude"), packet.get("longitude")
    return f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else ""


def _info(packet: dict[str, Any]) -> str:
    raw = packet.get("raw") or ""
    return raw.split(":", 1)[1] if ":" in raw else packet.get("text", "")


def summary(packet: dict[str, Any], weather=None) -> str:
    """What the packet says: a position with its comment, a message with its addressee, a status… `weather`
    (a function of the weather dict) words a weather report; without it the raw values go."""
    k = kind(packet)
    parts: list[str] = []
    if k == "thirdparty" and isinstance(packet.get("thirdparty"), dict):
        inner = packet["thirdparty"]
        return f"{inner.get('from', '?')}: {summary(inner, weather)}"
    if k in ("object", "item"):
        name = (packet.get("object_name") or "").strip()
        parts.append(name + ("" if packet.get("alive", True) else " ✕"))
    if k == "message":
        to = (packet.get("addresse") or "").strip()
        if packet.get("response") in ("ack", "rej"):
            return f"{packet['response']} {packet.get('msgNo', '')} → {to}".strip()
        return f"→ {to}: {packet.get('message_text', '')}"
    if k == "bulletin":
        line = packet.get("bid") or packet.get("aid") or ""
        return f"BLN{line}{packet.get('identifier') or ''}: {packet.get('message_text', '')}"
    if k == "status":
        return packet.get("status") or _info(packet)
    if k == "weather" and packet.get("weather"):
        w = packet["weather"]
        parts.append(weather(w) if weather else ", ".join(f"{a}={b}" for a, b in w.items()))
    place = _place(packet)
    if place:
        parts.append(place)
    comment = (packet.get("comment") or "").strip()
    if comment:
        parts.append(comment)
    return " · ".join(p for p in parts if p) or _info(packet)
