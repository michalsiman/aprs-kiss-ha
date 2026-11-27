"""The APRS station: receive, acknowledge, send with retries.

The engine (engine.py) gives it callbacks for packets,
messages and state changes, and a way to send frames.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import logging
import re
import time
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from . import aprs
from .ax25 import Address, Frame

_LOGGER = logging.getLogger(__name__)

# A packet heard again (digipeated copies) within this time is a duplicate.
DUPLICATE_SECONDS = 30
# A message heard again (the sender retrying) within this time is not shown again.
MESSAGE_DUPLICATE_SECONDS = 600
# Outgoing message retries until an ack: seconds after the previous try.
RETRY_DELAYS = (30, 60, 120, 240)
# Transmit limits: at least this gap between frames, at most this many per 10 minutes.
MIN_TX_GAP = 3.0
MAX_TX_PER_10_MIN = 30
MAX_HEARD = 500
IS_COPIES_SECONDS = 60  # copies of one packet through several iGates arrive within this time
TRACK_SECONDS = 3600  # where each station was in the last hour, kept in memory only (the map's trails)
TRACK_POINTS = 120
TRACK_MIN_MOVE_DEG = 0.0003  # about 30 m: a new point only when the station really moved


@dataclass
class StationConfig:
    callsign: str
    path: list[str] = field(default_factory=lambda: ["WIDE1-1", "WIDE2-1"])
    symbol: str = "/-"
    comment: str = ""


@dataclass
class OutgoingMessage:
    msg_id: str
    to: str
    text: str
    created: float
    tries: int = 0
    state: str = "pending"  # pending, acked, rejected, failed
    acked_at: float | None = None
    via: str = "both"  # radio, internet or both

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.msg_id, "to": self.to, "text": self.text, "state": self.state,
                "tries": self.tries, "created": self.created, "acked_at": self.acked_at, "via": self.via}


# Where a message goes: arguments for send_info.
VIA = {"radio": {"rf": True, "to_is": False}, "internet": {"rf": False, "to_is": True}, "both": {"rf": True, "to_is": True}}


class TransmitRefused(Exception):
    """Transmitting is switched off or the limit was reached."""


class Station:
    """One APRS station on one TNC."""

    def __init__(
        self,
        config: StationConfig,
        send_frame: Callable[[bytes], Awaitable[None]],
        parse: Callable[[str], dict[str, Any]],
        on_packet: Callable[[dict[str, Any]], None],
        on_message: Callable[[dict[str, Any]], None],
        on_update: Callable[[], None],
        next_msg_number: Callable[[], int],
    ) -> None:
        self.config = config
        self.me = Address.parse(config.callsign)
        self._path = [Address.parse(p) for p in config.path if p.strip()]
        self._send_frame = send_frame
        self._parse = parse
        self._on_packet = on_packet
        self._on_message = on_message
        self._on_update = on_update
        self._next_msg_number = next_msg_number
        self.tx_enabled = False
        # Set by the hub when APRS-IS is connected: sends one info field from us to APRS-IS.
        self.send_is: Callable[[str], Awaitable[bool]] | None = None
        self.heard: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.outgoing: OrderedDict[str, OutgoingMessage] = OrderedDict()
        self.last_packet: dict[str, Any] | None = None
        self.last_message: dict[str, Any] | None = None
        self.stats = {"received": 0, "duplicates": 0, "decode_errors": 0, "sent": 0,
                      "refused": 0, "digipeated_own": 0, "messages_received": 0}
        self._recent: dict[str, float] = {}
        self._recent_msgs: dict[tuple[str, str], float] = {}
        self._tx_times: deque[float] = deque()
        self._tx_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    # ─── receive ──────────────────────────────────────────────────────────

    def handle_frame(self, raw: bytes) -> None:
        try:
            frame = Frame.decode(raw)
        except ValueError as err:
            self.stats["decode_errors"] += 1
            _LOGGER.debug("Undecodable AX.25 frame (%s): %s", err, raw.hex())
            return
        now = time.time()
        tnc2 = frame.tnc2()
        key = f"{frame.source}>{frame.info!r}"
        self._expire(now)
        if key in self._recent:
            self.stats["duplicates"] += 1
            return
        self._recent[key] = now
        if frame.source == self.me:
            # Our own packet coming back from a digipeater.
            self.stats["digipeated_own"] += 1
            self._on_update()
            return
        self.stats["received"] += 1
        packet = self._parse(tnc2)
        packet.setdefault("from", str(frame.source))
        packet.setdefault("to", str(frame.destination))
        packet["raw"] = tnc2
        packet["path"] = [f"{d}{'*' if d.repeated else ''}" for d in frame.path]
        packet["received_at"] = now
        self.last_packet = packet
        self._remember_station(packet, now)
        self._on_packet(packet)
        if packet.get("format") == "message" and self._for_me(packet.get("addresse")):
            self._handle_message(packet, now, via_is=False)
        inner = packet.get("thirdparty")
        if isinstance(inner, dict) and inner.get("from") and inner["from"] != self.me:
            # An iGate (or a gateway) relayed this station to our radio. Its position goes on the
            # map and a message for us is ours: the ack goes back by radio for the iGate to pass on.
            inner = {**inner, "gated_by": str(frame.source), "received_at": now}
            self._remember_station(inner, now)
            if inner.get("format") == "message" and self._for_me(inner.get("addresse")):
                self._handle_message(inner, now, via_is=False)
        self._on_update()

    def handle_is_packet(self, packet: dict[str, Any]) -> bool:
        """A packet from APRS-IS; True when it was a message for us (handled here).
        Other packets only add the sender to the stations heard, marked as heard over the internet."""
        now = time.time()
        packet.setdefault("path", ["TCPIP"])
        if packet.get("from") and packet.get("format") != "message":
            self._remember_station(packet, now, via="is")
            self._on_update()
        if packet.get("format") != "message" or not self._for_me(packet.get("addresse")):
            return False
        self._handle_message(packet, now, via_is=True)
        self._on_update()
        return True

    def _for_me(self, addressee: str | None) -> bool:
        return bool(addressee) and addressee.strip().upper() == str(self.me)

    def _remember_station(self, packet: dict[str, Any], now: float, via: str = "rf") -> None:
        """Note a station; `via` is "rf" (heard by the radio) or "is" (seen on APRS-IS).

        An APRS object (a repeater, an event, …) is a place of its own, under its own name: kept under
        the sender's callsign it moved the sender between all its objects (and drew trails across the
        country). A killed object goes away."""
        call = packet["from"]
        owner = None
        if packet.get("format") == "object" and (packet.get("object_name") or "").strip():
            owner, call = call, packet["object_name"].strip()
            if packet.get("alive") is False:
                self.heard.pop(call, None)
                return
        entry = self.heard.pop(call, None) or {"call": call, "count": 0, "first_heard": now}
        if owner:
            entry["object_of"] = owner
        entry["count"] += 1
        previous = max(entry.get("last_is") or 0, entry.get("last_rf") or 0)
        entry["last_heard"] = now
        entry[f"last_{via}"] = now
        if packet.get("garbled") or (via == "is" and previous and now - previous < IS_COPIES_SECONDS):
            # A packet received with bit errors, or another copy of the same packet that a
            # different iGate sent a few seconds later (often with its own additions, such
            # as LoRa signal reports): keep what the first copy said.
            self.heard[call] = entry
            return
        if via == "rf" or "last_rf" not in entry:
            # The radio path says more about the station than an internet path.
            entry["last_raw"] = packet["raw"]
            entry["path"] = packet["path"]
        if via == "rf":
            if packet.get("gated_by"):
                entry["gated_by"] = packet["gated_by"]  # heard only as relayed by this iGate
            else:
                entry.pop("gated_by", None)
        for k in ("latitude", "longitude", "symbol", "symbol_table", "comment", "speed", "course", "altitude", "status", "weather"):
            if packet.get(k) not in (None, {}, ""):
                entry[k] = packet[k]
        if packet.get("latitude") is not None and packet.get("longitude") is not None:
            _track(entry, now, packet["latitude"], packet["longitude"])
        weather = packet.get("weather")
        if isinstance(weather, dict):
            weather = dict(weather)
            # In a weather report "course/speed" is wind direction and speed in mph;
            # aprslib reads it as course and knots converted to km/h.
            if packet.get("course") is not None:
                weather.setdefault("wind_direction", packet["course"])
            if packet.get("speed") is not None:
                weather.setdefault("wind_speed", round(packet["speed"] / 1.852 * 0.44704, 2))
            entry["weather"] = weather
            entry["weather_at"] = now  # the weather report itself: a station may also send other packets
            entry.pop("speed", None)
            entry.pop("course", None)
        self.heard[call] = entry
        while len(self.heard) > MAX_HEARD:
            self.heard.popitem(last=False)

    def _handle_message(self, packet: dict[str, Any], now: float, via_is: bool = False) -> None:
        sender = packet["from"]
        text = aprs.fix_mojibake(packet.get("message_text", ""))
        response = packet.get("response")
        if response in ("ack", "rej"):
            msg = self.outgoing.get(str(packet.get("msgNo", "")))
            if msg and msg.to.upper() == sender.upper() and msg.state == "pending":
                msg.state = "acked" if response == "ack" else "rejected"
                msg.acked_at = now
                _LOGGER.debug("Message %s to %s %s", msg.msg_id, msg.to, msg.state)
            return
        msg_no = packet.get("msgNo")
        if not msg_no and re.fullmatch(r"(ack|rej)\S{1,6}", text.strip()):
            # an ack/rej whose message number is broken (non-ASCII, too long): not a message to show
            _LOGGER.debug("Malformed %s from %s: %r", text[:3], sender, text)
            return
        if msg_no:
            # Acknowledge every copy, also repeated ones: the sender did not hear our ack.
            self._spawn(self._send_ack(sender, str(msg_no), via_is))
            dkey = (sender.upper(), str(msg_no))
            if dkey in self._recent_msgs:
                return
            self._recent_msgs[dkey] = now
        self.stats["messages_received"] += 1
        self.last_message = {"from": sender, "text": text, "msg_no": msg_no, "received_at": now,
                             "path": packet["path"], "raw": packet.get("raw", ""), "via": "internet" if via_is else "radio"}
        self._on_message(self.last_message)

    def _expire(self, now: float) -> None:
        for k in [k for k, t in self._recent.items() if now - t > DUPLICATE_SECONDS]:
            del self._recent[k]
        for k in [k for k, t in self._recent_msgs.items() if now - t > MESSAGE_DUPLICATE_SECONDS]:
            del self._recent_msgs[k]

    # ─── transmit ─────────────────────────────────────────────────────────

    def _check_limit(self, now: float) -> None:
        while self._tx_times and now - self._tx_times[0] > 600:
            self._tx_times.popleft()
        if len(self._tx_times) >= MAX_TX_PER_10_MIN:
            raise TransmitRefused(f"Transmit limit reached ({MAX_TX_PER_10_MIN} frames per 10 minutes)")

    async def send_info(self, info: str, rf: bool = True, to_is: bool = True) -> None:
        """Send one APRS information field from our callsign: on RF (over the configured
        path) while transmitting is on, and to APRS-IS while connected. Third-party
        packets from the internet go on RF only; acks to internet messages only to APRS-IS.
        """
        sent_is = False
        if to_is and self.send_is is not None:
            try:
                sent_is = await self.send_is(info)
            except (OSError, ConnectionError) as err:
                _LOGGER.debug("Not sent to APRS-IS: %s", err)
        if not rf or not self.tx_enabled:
            if sent_is:
                self.stats["sent_is"] = self.stats.get("sent_is", 0) + 1
                self._on_update()
                return
            self.stats["refused"] += 1
            raise TransmitRefused("Transmitting is switched off" if rf else "APRS-IS is not connected")
        async with self._tx_lock:
            now = time.monotonic()
            self._check_limit(now)
            if self._tx_times and now - self._tx_times[-1] < MIN_TX_GAP:
                await asyncio.sleep(MIN_TX_GAP - (now - self._tx_times[-1]))
            frame = Frame(Address.parse(aprs.TOCALL), self.me, list(self._path), info.encode("latin-1", "replace"))
            await self._send_frame(frame.encode())
            self._tx_times.append(time.monotonic())
            self.stats["sent"] += 1
            _LOGGER.debug("Sent %s", frame.tnc2())
        self._on_update()

    async def _send_ack(self, to: str, msg_no: str, via_is: bool = False) -> None:
        try:
            await self.send_info(aprs.ack(to, msg_no), rf=not via_is, to_is=via_is)
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Ack to %s not sent: %s", to, err)

    async def send_message(self, to: str, text: str, want_ack: bool = True, via: str = "both") -> OutgoingMessage:
        """Send a message; with an id it is repeated until the recipient acknowledges it.
        `via`: "radio" (RF only), "internet" (APRS-IS only) or "both"."""
        if via not in VIA:
            raise ValueError(f"via must be one of {', '.join(VIA)}")
        to = str(Address.parse(to))
        msg_id = aprs.message_id(self._next_msg_number()) if want_ack else ""
        msg = OutgoingMessage(msg_id or f"noack-{time.time():.0f}", to, aprs.clean_text(text, aprs.MAX_MESSAGE_TEXT), time.time(), via=via)
        info = aprs.message(to, msg.text, msg_id or None)
        await self.send_info(info, **VIA[via])
        msg.tries = 1
        if want_ack:
            self.outgoing[msg.msg_id] = msg
            while len(self.outgoing) > 50:
                self.outgoing.popitem(last=False)
            self._spawn(self._retry(msg, info))
        else:
            msg.state = "sent"
        self._on_update()
        return msg

    async def _retry(self, msg: OutgoingMessage, info: str) -> None:
        for delay in RETRY_DELAYS:
            await asyncio.sleep(delay)
            if msg.state != "pending":
                break
            try:
                await self.send_info(info, **VIA[msg.via])
                msg.tries += 1
            except (TransmitRefused, ConnectionError) as err:
                _LOGGER.debug("Retry of message %s not sent: %s", msg.msg_id, err)
            self._on_update()
        else:
            await asyncio.sleep(RETRY_DELAYS[-1])
        if msg.state == "pending":
            msg.state = "failed"
        self._on_update()

    async def send_position(self, lat: float, lon: float, comment: str | None = None,
                            rf: bool = True, to_is: bool = True) -> None:
        await self.send_info(aprs.position(lat, lon, self.config.symbol, self.config.comment if comment is None else comment),
                             rf=rf, to_is=to_is)

    async def send_status(self, text: str) -> None:
        await self.send_info(aprs.status(text))

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


TRACK_MAX_KMH = 400  # faster than this between two positions: not one moving station
TRACK_SLACK_KM = 2  # GPS jitter and rounding allowed on top


def _impossible(last: list, now: float, lat: float, lon: float) -> bool:
    dlat = math.radians(lat - last[1])
    dlon = math.radians(lon - last[2]) * math.cos(math.radians((lat + last[1]) / 2))
    km = 6371.0 * math.hypot(dlat, dlon)
    return km > TRACK_SLACK_KM + TRACK_MAX_KMH * max(0.0, now - last[0]) / 3600


def _track(entry: dict[str, Any], now: float, lat: float, lon: float) -> None:
    """Add a position to the station's last hour, when it moved; older points drop out."""
    track = entry.setdefault("track", [])
    if track and _impossible(track[-1], now, lat, lon):
        track.clear()  # a jump no vehicle makes (a wrong position, a shared callsign): start again here
    if track and abs(track[-1][1] - lat) < TRACK_MIN_MOVE_DEG and abs(track[-1][2] - lon) < TRACK_MIN_MOVE_DEG:
        track[-1][0] = now  # still there: just when it was last seen there
    else:
        track.append([now, lat, lon])
    while track and (now - track[0][0] > TRACK_SECONDS or len(track) > TRACK_POINTS):
        track.pop(0)
