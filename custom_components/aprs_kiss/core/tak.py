"""TAK (ATAK, WinTAK, iTAK…): Cursor on Target events in TAK Protocol version 1 (protobuf).

Only what goes over the radio: a TakMessage with one CotEvent, framed as on a TAK mesh
(0xbf 0x01 0xbf, then the protobuf). The protobuf is written and read here by hand, no library:
the field numbers are those of takproto's .proto files (atakmap::commoncommo::v1).

On the air one event is the information field of an AX.25 UI frame to TAK; the source is the
sender's callsign. Amateur radio: nothing is encrypted.
"""

from __future__ import annotations

import re
import struct
import time
import uuid as uuidlib
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

from . import units

MESH_HEADER = b"\xbf\x01\xbf"
DESTINATION = "TAK"  # AX.25 destination of TAK frames
MAX_PAYLOAD = 220  # one event per frame: AX.25 N1 is 256, but LoRa KISS modems (MeshCore) carry 255 bytes with the header
UNKNOWN = 9999999.0  # TAK's "unknown" for hae, ce and le

TEAMS = ["White", "Yellow", "Orange", "Magenta", "Red", "Maroon", "Purple", "Dark Blue", "Blue",
         "Cyan", "Teal", "Green", "Dark Green", "Brown"]
ROLES = ["Team Member", "Team Lead", "HQ", "Sniper", "Medic", "Forward Observer", "RTO", "K9"]
TYPE_PLI = "a-f-G-U-C"  # a friendly ground unit (combat): what ATAK sends for its own position
TYPE_CHAT = "b-t-f"  # GeoChat
TYPE_SPOT = "b-m-p-s-m"  # a spot marker
ALL_CHAT = "All Chat Rooms"  # ATAK's room for everybody; the compact form on the air says "All"


# ─── protobuf, the few wire types TAK uses ──────────────────────────────────

def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _key(number: int, wire: int) -> bytes:
    return _varint(number << 3 | wire)


def _str(number: int, value: str) -> bytes:
    data = value.encode("utf-8")
    return _key(number, 2) + _varint(len(data)) + data if value else b""


def _msg(number: int, data: bytes) -> bytes:
    return _key(number, 2) + _varint(len(data)) + data if data else b""


def _uint(number: int, value: int) -> bytes:
    return _key(number, 0) + _varint(value) if value else b""


def _double(number: int, value: float) -> bytes:
    return _key(number, 1) + struct.pack("<d", value) if value else b""


def _fields(data: bytes):
    """(number, wire type, value) of each field; value is an int, a float or bytes."""
    i, n = 0, len(data)
    while i < n:
        key, i = _read_varint(data, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _read_varint(data, i)
        elif wire == 1:
            if i + 8 > n:
                raise ValueError("truncated double")
            value = struct.unpack_from("<d", data, i)[0]
            i += 8
        elif wire == 2:
            length, i = _read_varint(data, i)
            if i + length > n:
                raise ValueError("truncated field")
            value = data[i:i + length]
            i += length
        elif wire == 5:
            value = struct.unpack_from("<f", data, i)[0]
            i += 4
        else:
            raise ValueError(f"wire type {wire}")
        yield number, wire, value


def _read_varint(data: bytes, i: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if i >= len(data) or shift > 63:
            raise ValueError("bad varint")
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


# ─── the event ──────────────────────────────────────────────────────────────

@dataclass
class TakEvent:
    type: str
    uid: str
    lat: float
    lon: float
    hae: float = UNKNOWN
    ce: float = UNKNOWN
    le: float = UNKNOWN
    how: str = "m-g"
    time_ms: int = 0
    start_ms: int = 0
    stale_ms: int = 0
    callsign: str = ""
    endpoint: str = ""
    team: str = ""
    role: str = ""
    speed: float = 0.0
    course: float = 0.0
    battery: int = 0
    xml_detail: str = ""
    extra: dict = field(default_factory=dict)  # filled when read: chat fields and the like

    def encode(self) -> bytes:
        """The mesh-framed TakMessage for the air."""
        contact = _str(1, self.endpoint) + _str(2, self.callsign)
        group = _str(1, self.team) + _str(2, self.role)
        track = _double(1, self.speed) + _double(2, self.course)
        detail = (_str(1, self.xml_detail) + _msg(2, contact) + _msg(3, group) + _msg(5, _uint(1, self.battery))
                  + _msg(7, track))
        event = (_str(1, self.type) + _str(5, self.uid) + _uint(6, self.time_ms) + _uint(7, self.start_ms)
                 + _uint(8, self.stale_ms) + _str(9, self.how) + _double(10, self.lat) + _double(11, self.lon)
                 + _double(12, self.hae) + _double(13, self.ce) + _double(14, self.le) + _msg(15, detail))
        return MESH_HEADER + _msg(2, event)

    def stale(self, now: float | None = None) -> bool:
        return bool(self.stale_ms) and (now or time.time()) * 1000 > self.stale_ms


def decode(data: bytes) -> TakEvent:
    """A TakMessage, mesh-framed or bare. ValueError when it is not one."""
    if data.startswith(MESH_HEADER):
        data = data[len(MESH_HEADER):]
    elif data[:1] == b"\xbf":
        raise ValueError("not TAK Protocol version 1")
    event_bytes = next((v for n, w, v in _fields(data) if n == 2 and w == 2), None)
    if event_bytes is None:
        raise ValueError("no CotEvent")
    ev = TakEvent(type="", uid="", lat=0.0, lon=0.0)
    for number, wire, value in _fields(event_bytes):
        if wire == 2 and number in (1, 5, 9):
            setattr(ev, {1: "type", 5: "uid", 9: "how"}[number], value.decode("utf-8", "replace"))
        elif wire == 0 and number in (6, 7, 8):
            setattr(ev, {6: "time_ms", 7: "start_ms", 8: "stale_ms"}[number], value)
        elif wire == 1 and number in (10, 11, 12, 13, 14):
            setattr(ev, {10: "lat", 11: "lon", 12: "hae", 13: "ce", 14: "le"}[number], value)
        elif wire == 2 and number == 15:
            _read_detail(ev, value)
    if not ev.type or not ev.uid:
        raise ValueError("event without type or uid")
    if ev.type == TYPE_CHAT:
        ev.extra.update(read_chat(ev.xml_detail))
    return ev


def _read_detail(ev: TakEvent, data: bytes) -> None:
    for number, wire, value in _fields(data):
        if wire != 2:
            continue
        if number == 1:
            ev.xml_detail = value.decode("utf-8", "replace")
        elif number == 2:
            for n, w, v in _fields(value):
                if w == 2 and n == 1:
                    ev.endpoint = v.decode("utf-8", "replace")
                elif w == 2 and n == 2:
                    ev.callsign = v.decode("utf-8", "replace")
        elif number == 3:
            for n, w, v in _fields(value):
                if w == 2 and n == 1:
                    ev.team = v.decode("utf-8", "replace")
                elif w == 2 and n == 2:
                    ev.role = v.decode("utf-8", "replace")
        elif number == 5:
            for n, w, v in _fields(value):
                if w == 0 and n == 1:
                    ev.battery = v
        elif number == 7:
            for n, w, v in _fields(value):
                if w == 1 and n == 1:
                    ev.speed = v
                elif w == 1 and n == 2:
                    ev.course = v


# ─── the events we send ─────────────────────────────────────────────────────

def _times(stale_s: float, now: float | None = None) -> tuple[int, int, int]:
    ms = int((now or time.time()) * 1000)
    return ms, ms, ms + int(stale_s * 1000)


def pli(uid: str, callsign: str, lat: float, lon: float, team: str = "Cyan", role: str = "Team Member",
        hae: float | None = None, speed: float = 0.0, course: float = 0.0, stale_s: float = 600,
        now: float | None = None) -> TakEvent:
    """Our position, the way ATAK sends its own ("PLI")."""
    t, s, st = _times(stale_s, now)
    return TakEvent(TYPE_PLI, uid, lat, lon, hae=UNKNOWN if hae is None else hae, ce=10.0, le=10.0,
                    how="m-g", time_ms=t, start_ms=s, stale_ms=st, callsign=callsign, team=team, role=role,
                    speed=speed, course=course)


def geochat(uid: str, callsign: str, text: str, to_uid: str = "", to_callsign: str = "",
            now: float | None = None) -> TakEvent:
    """A GeoChat message to everybody or, with `to_uid`, to one station.

    Compact for the radio: ATAK's own GeoChat is about 500 bytes with its optional attributes, the
    position and the "All Chat Rooms" room name; this keeps the same elements (__chat, remarks)
    with only what a reader needs, so a message fits in one frame. read_chat() reads both forms.
    """
    room = to_uid or "All"
    t, s, st = _times(86400, now)
    detail = (f"<__chat chatroom={quoteattr(to_callsign or room)} senderCallsign={quoteattr(callsign)}/>"
              f"<remarks to={quoteattr(room)}>{escape(text)}</remarks>")
    return TakEvent(TYPE_CHAT, f"GeoChat.{uid}.{room}.{uuidlib.uuid4().hex[:6]}", 0.0, 0.0, hae=0.0, ce=0.0,
                    le=0.0, how="h-g-i-g-o", time_ms=t, start_ms=s, stale_ms=st, xml_detail=detail)


def geochat_events(uid: str, callsign: str, text: str, to_uid: str = "", to_callsign: str = "",
                   now: float | None = None) -> list[TakEvent]:
    """The text as one or more GeoChat events, each fitting in one frame, split between words."""
    events: list[TakEvent] = []
    rest = " ".join(text.split("\n")).strip()
    while rest:
        cut = len(rest)
        while cut > 1 and len(geochat(uid, callsign, rest[:cut], to_uid, to_callsign, now).encode()) > MAX_PAYLOAD:
            space = rest.rfind(" ", 0, cut - 1)
            cut = space if space > cut // 2 else cut - 1
        events.append(geochat(uid, callsign, rest[:cut].strip(), to_uid, to_callsign, now))
        rest = rest[cut:].strip()
    return events


def read_chat(xml_detail: str) -> dict[str, str]:
    """Sender, room and text of a GeoChat detail (as ATAK writes it)."""
    def attr(tag: str, name: str) -> str:
        m = re.search(rf"<{tag}\b[^>]*\b{name}=\"([^\"]*)\"", xml_detail)
        return _unescape(m.group(1)) if m else ""
    m = re.search(r"<remarks\b[^>]*>(.*?)</remarks>", xml_detail, re.S)
    return {"chatroom": attr("__chat", "chatroom"), "sender": attr("__chat", "senderCallsign"),
            "to": attr("remarks", "to"), "text": _unescape(m.group(1)) if m else ""}


def _unescape(text: str) -> str:
    return (text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
            .replace("&amp;", "&"))


def affiliation(cot_type: str) -> str:
    """'f' friend, 'h' hostile, 'n' neutral, 'u' unknown… from an atom type like a-f-G-U-C."""
    parts = cot_type.split("-")
    return parts[1] if len(parts) > 1 and parts[0] == "a" else ""


def describe(ev: TakEvent) -> str:
    """One readable line for the frame monitor."""
    if ev.type == TYPE_CHAT:
        c = ev.extra or read_chat(ev.xml_detail)
        return f"TAK GeoChat {c.get('sender') or ev.uid} → {c.get('to') or 'All'}: {c.get('text', '')}"
    who = ev.callsign or ev.uid
    team = ", ".join(x for x in (ev.team, ev.role) if x)
    speed = f" {units.current.speed(ev.speed * 3.6)}" if ev.speed else ""
    kind = "PLI" if ev.type.startswith("a-") else ev.type
    return f"TAK {kind} {who}{f' ({team})' if team else ''} {ev.lat:.5f} {ev.lon:.5f}{speed}"


def monitor_text(info: bytes) -> str | None:
    """The monitor line for a TAK frame's information field, None when it is not TAK."""
    if not info.startswith(MESH_HEADER):
        return None
    try:
        return describe(decode(info))
    except (ValueError, IndexError):
        return "TAK (not understood)"

