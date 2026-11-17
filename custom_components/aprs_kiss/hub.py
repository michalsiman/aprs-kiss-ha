"""Ties the TNC connection, the APRS station and the terminal sessions to Home Assistant."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta
from homeassistant.helpers.storage import Store

from . import aprs as aprs_build
from .aprsis import AprsIsClient, gate_to_is, passcode, third_party
from .ax25 import Address, Frame, PF, U_DM
from .connection import KissConnection, TncSettings
from .const import (
    CONF_APRSIS, CONF_LICENCE, CONF_APRSIS_HOST, CONF_APRSIS_PASSCODE, CONF_APRSIS_PORT, CONF_APRSIS_RADIUS,
    CONF_BEACON_IS, CONF_BEACON_MINUTES, CONF_IGATE_RX, CONF_IGATE_TX, DEFAULT_APRSIS_HOST, DEFAULT_APRSIS_PORT,
    DEFAULT_APRSIS_RADIUS, VERSION,
    CONF_ACCEPT_INCOMING, CONF_BAUDRATE, CONF_CALLSIGN, CONF_COMMENT, CONF_CONNECTION, CONF_DEVICE,
    CONF_HOST, CONF_PATH, CONF_PORT, CONF_SYMBOL, CONF_TXDELAY, DEFAULT_PATH, DEFAULT_PORT,
    DEFAULT_SYMBOL, DOMAIN, EVENT_MESSAGE, EVENT_PACKET, EVENT_TERMINAL, SIGNAL_UPDATE,
)
from .parser import parse
from .session import DISCONNECTED, Session
from .station import Station, StationConfig, TransmitRefused

_LOGGER = logging.getLogger(__name__)

MONITOR_LINES = 500
TERMINAL_LINES = 2000
MESSAGE_HISTORY = 200
# A station counts as local (for gating internet messages to RF) if heard on RF this recently.
LOCAL_SECONDS = 1800
MIN_BEACON_MINUTES = 10
CHAT_LINES = 500
CHAT_DUPLICATE_SECONDS = 30
# First character of an APRS information field (APRS 1.0.1, data type identifiers).
APRS_TYPES = set("!=/@;)`':>?<$_{}*#")


def _paths(text: str) -> list[str]:
    return [p.strip().upper() for p in (text or "").replace(" ", ",").split(",") if p.strip()]


class Hub:
    """One TNC with one callsign."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        conf = {**entry.data, **entry.options}
        self.conf = conf
        self.me = Address.parse(conf[CONF_CALLSIGN])
        self.connection = KissConnection(
            TncSettings(
                kind=conf.get(CONF_CONNECTION, "tcp"),
                host=conf.get(CONF_HOST, ""),
                port=int(conf.get(CONF_PORT, DEFAULT_PORT)),
                device=conf.get(CONF_DEVICE, ""),
                baudrate=int(conf.get(CONF_BAUDRATE, 9600)),
                txdelay_ms=conf.get(CONF_TXDELAY) or None,
            ),
            self._on_frame_threadsafe,
            self._on_connection_state,
        )
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._msg_counter = 0
        self.messages: deque[dict[str, Any]] = deque(maxlen=MESSAGE_HISTORY)
        self.monitor: deque[str] = deque(maxlen=MONITOR_LINES)
        self.terminal: deque[dict[str, Any]] = deque(maxlen=TERMINAL_LINES)
        self.chat: deque[dict[str, Any]] = deque(maxlen=CHAT_LINES)
        self._chat_recent: dict[str, float] = {}
        self.sessions: dict[str, Session] = {}
        self.accept_incoming = bool(conf.get(CONF_ACCEPT_INCOMING, False))
        self.station = Station(
            StationConfig(str(self.me), _paths(conf.get(CONF_PATH, DEFAULT_PATH)),
                          conf.get(CONF_SYMBOL, DEFAULT_SYMBOL), conf.get(CONF_COMMENT, "")),
            self.send_frame, parse, self._on_packet, self._on_message, self._on_update, self._next_msg_number,
        )
        self.igate_rx = bool(conf.get(CONF_IGATE_RX, False))
        self.igate_tx = bool(conf.get(CONF_IGATE_TX, False))
        self.igate_stats = {"rf_to_is": 0, "is_to_rf": 0, "is_messages": 0}
        self.aprsis: AprsIsClient | None = None
        if conf.get(CONF_APRSIS) and conf.get(CONF_LICENCE):
            lat, lon = hass.config.latitude, hass.config.longitude
            radius = int(conf.get(CONF_APRSIS_RADIUS, DEFAULT_APRSIS_RADIUS) or 0)
            code = conf.get(CONF_APRSIS_PASSCODE) or passcode(str(self.me))
            self.aprsis = AprsIsClient(
                conf.get(CONF_APRSIS_HOST) or DEFAULT_APRSIS_HOST,
                int(conf.get(CONF_APRSIS_PORT) or DEFAULT_APRSIS_PORT),
                str(self.me), int(code),
                f"r/{lat:.3f}/{lon:.3f}/{radius}" if radius > 0 else "",
                f"aprs-kiss-ha {VERSION}",
                self._on_is_line, self._on_is_state,
            )
            self.station.send_is = self._send_own_to_is
        self._beacon_unsub = None

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self._msg_counter = int(stored.get("msg_counter", 0))
        self.messages.extend(stored.get("messages", []))
        await self.connection.start()
        if self.aprsis:
            await self.aprsis.start()
        minutes = int(self.conf.get(CONF_BEACON_MINUTES, 0) or 0)
        if minutes:
            self._beacon_unsub = async_track_time_interval(
                self.hass, self._beacon, timedelta(minutes=max(MIN_BEACON_MINUTES, minutes)))

    async def async_stop(self) -> None:
        for s in self.sessions.values():
            s.close()
        if self._beacon_unsub:
            self._beacon_unsub()
        await self.station.close()
        if self.aprsis:
            await self.aprsis.stop()
        await self.connection.stop()
        await self._save()

    async def _save(self) -> None:
        await self._store.async_save({"msg_counter": self._msg_counter, "messages": list(self.messages)})

    def _schedule_save(self) -> None:
        self._store.async_delay_save(lambda: {"msg_counter": self._msg_counter, "messages": list(self.messages)}, 5)

    def _next_msg_number(self) -> int:
        self._msg_counter += 1
        self._schedule_save()
        return self._msg_counter

    # ─── sending ──────────────────────────────────────────────────────────

    async def send_frame(self, raw: bytes) -> None:
        """Every transmission goes through here: refused while transmitting is off."""
        if not self.station.tx_enabled:
            raise TransmitRefused("Transmitting is switched off")
        await self.connection.send(raw)
        self._monitor(Frame.decode(raw).monitor(), outgoing=True)

    # ─── receiving ────────────────────────────────────────────────────────

    def _on_frame_threadsafe(self, raw: bytes) -> None:
        self.hass.loop.call_soon_threadsafe(self._on_frame, raw)

    @callback
    def _on_frame(self, raw: bytes) -> None:
        try:
            frame = Frame.decode(raw)
        except ValueError as err:
            self._monitor(f"? undecodable frame ({err}): {raw.hex()}")
            return
        self._monitor(frame.monitor())
        if frame.is_ui:
            self._chat_frame(frame)
            self.station.handle_frame(raw)
            return
        if frame.destination != self.me:
            return
        key = str(frame.source)
        sess = self.sessions.get(key)
        if sess is None or sess.state == DISCONNECTED:
            if frame.kind == "SABM" and self.accept_incoming and self.station.tx_enabled:
                sess = self._new_session(frame.source, [Address(d.call, d.ssid) for d in reversed(frame.path)])
            elif frame.kind == "SABM" or (frame.command and frame.poll_final):
                if self.station.tx_enabled:
                    reply = Frame(frame.source, self.me, [Address(d.call, d.ssid) for d in reversed(frame.path)],
                                  b"", U_DM | (PF if frame.poll_final else 0), None, False)
                    self.hass.async_create_task(self._send_quietly(reply.encode()))
                return
            elif sess is None:
                return
        sess.handle(frame)

    async def _send_quietly(self, raw: bytes) -> None:
        try:
            await self.send_frame(raw)
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Frame not sent: %s", err)

    def _monitor(self, line: str, outgoing: bool = False) -> None:
        entry = f"{time.strftime('%H:%M:%S')} {'>>' if outgoing else '<<'} {line}"
        self.monitor.append(entry)
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "monitor", "line": entry})

    @callback
    def _on_packet(self, packet: dict[str, Any]) -> None:
        self.hass.bus.async_fire(EVENT_PACKET, {"entry_id": self.entry.entry_id, **packet})
        if self.igate_rx and self.aprsis and self.aprsis.verified:
            src, _, rest = packet["raw"].partition(">")
            dst = rest.split(",", 1)[0].split(":", 1)[0]
            info = rest.split(":", 1)[1].encode("latin-1", "replace") if ":" in rest else b""
            line = gate_to_is(src, dst, [p for p in packet.get("path", [])], info, str(self.me))
            if line:
                self.hass.async_create_task(self._gate_up(line))

    async def _gate_up(self, line: str) -> None:
        if self.aprsis and await self.aprsis.send(line):
            self._monitor(f"[IS] {line}", outgoing=True)
            self.igate_stats["rf_to_is"] += 1
            self._on_update()

    # ─── APRS-IS ──────────────────────────────────────────────────────────

    async def _send_own_to_is(self, info: str) -> bool:
        if not self.aprsis or not self.aprsis.verified:
            return False
        line = f"{self.me}>{aprs_build.TOCALL},TCPIP*:{info}"
        sent = await self.aprsis.send(line)
        if sent:
            self._monitor(f"[IS] {line}", outgoing=True)
        return sent

    @callback
    def _on_is_state(self, connected: bool) -> None:
        self._on_update()

    @callback
    def _on_is_line(self, line: str, garbled: bool = False) -> None:
        self._monitor(f"[IS] {line}")
        packet = parse(line)
        packet["raw"] = line
        if garbled:
            packet["garbled"] = True
        head = line.partition(":")[0]
        packet["path"] = head.split(",")[1:] or ["TCPIP"]
        src = packet.get("from", "")
        if self.station.handle_is_packet(packet):
            self.igate_stats["is_messages"] += 1
            return
        if not self.igate_tx or packet.get("format") != "message":
            return
        to = (packet.get("addresse") or "").strip().upper()
        local = self.station.heard.get(to)
        now = time.time()
        if not local or now - local.get("last_rf", 0) > LOCAL_SECONDS:  # heard by the radio lately
            return
        src_local = self.station.heard.get(src.upper())
        if src_local and now - src_local.get("last_rf", 0) < LOCAL_SECONDS:
            return  # the sender is on RF itself
        head, _, info = line.partition(":")
        dst = head.split(">", 1)[1].split(",", 1)[0] if ">" in head else "APRS"
        self.hass.async_create_task(self._gate_down(third_party(src, dst, info, str(self.me))))

    async def _gate_down(self, info: str) -> None:
        try:
            await self.station.send_info(info, rf=True, to_is=False)
            self.igate_stats["is_to_rf"] += 1
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Internet message not sent on RF: %s", err)
        self._on_update()

    async def _beacon(self, _now=None) -> None:
        try:
            # By radio while transmitting is on; over the internet only when chosen in Settings.
            await self.station.send_position(self.hass.config.latitude, self.hass.config.longitude,
                                             to_is=bool(self.conf.get(CONF_BEACON_IS)))
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Beacon not sent: %s", err)

    @callback
    def _on_message(self, message: dict[str, Any]) -> None:
        item = {"direction": "in", "from": message["from"], "to": str(self.me), "text": message["text"],
                "time": message["received_at"], "msg_no": message.get("msg_no")}
        self.messages.append(item)
        self._schedule_save()
        self.hass.bus.async_fire(EVENT_MESSAGE, {"entry_id": self.entry.entry_id, **message})
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "aprs_message", "message": item})

    @callback
    def _on_connection_state(self, connected: bool) -> None:
        self.hass.loop.call_soon_threadsafe(self._on_update)

    @callback
    def _on_update(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(self.entry.entry_id))

    # ─── APRS messages ────────────────────────────────────────────────────

    async def send_aprs_message(self, to: str, text: str, via: str = "both") -> dict[str, Any]:
        msg = await self.station.send_message(to, text, via=via)
        item = {"direction": "out", "from": str(self.me), "to": msg.to, "text": msg.text, "time": msg.created,
                "msg_no": msg.msg_id, "via": via}
        self.messages.append(item)
        self._schedule_save()
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "aprs_message", "message": item})
        return msg.as_dict()

    def message_state(self, msg_no: str | None) -> str | None:
        msg = self.station.outgoing.get(str(msg_no)) if msg_no else None
        return msg.state if msg else None

    # ─── terminal sessions ────────────────────────────────────────────────

    def _new_session(self, remote: Address, path: list[Address]) -> Session:
        key = str(remote)
        old = self.sessions.pop(key, None)
        if old:
            old.close()

        def on_text(text: str) -> None:
            self._terminal(key, "rx", text)

        def on_state(state: str, reason: str) -> None:
            self._terminal(key, "state", reason or state)
            self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "state",
                                                      "remote": key, "state": state})
            self._on_update()

        sess = Session(self.me, remote, path, self.send_frame, on_text, on_state)
        self.sessions[key] = sess
        return sess

    def _terminal(self, remote: str, kind: str, text: str) -> None:
        entry = {"time": time.time(), "remote": remote, "kind": kind, "text": text}
        self.terminal.append(entry)
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "terminal", "entry": entry})

    def connect(self, remote: str, path: str = "") -> None:
        if not self.station.tx_enabled:
            raise TransmitRefused("Transmitting is switched off")
        if not self.connection.connected:
            raise ConnectionError("The TNC is not connected")
        addr = Address.parse(remote)
        sess = self._new_session(addr, [Address.parse(p) for p in _paths(path)])
        sess.connect()

    def disconnect(self, remote: str) -> None:
        sess = self.sessions.get(str(Address.parse(remote)))
        if sess:
            sess.disconnect()

    def send_text(self, remote: str, text: str) -> None:
        key = str(Address.parse(remote))
        sess = self.sessions.get(key)
        if sess is None:
            raise ConnectionError("Not connected")
        sess.send_text(text)
        self._terminal(key, "tx", text)

    # ─── chat (plain text in UI frames) ───────────────────────────────────

    @staticmethod
    def is_aprs(frame: Frame) -> bool:
        info = frame.info
        return frame.destination.call.startswith("AP") or (bool(info) and chr(info[0]) in APRS_TYPES)

    def _chat_frame(self, frame: Frame) -> None:
        # Packet chat only: APRS packets never show up in the chat.
        if not frame.info or frame.source == self.me or self.is_aprs(frame):
            return
        now = time.time()
        key = f"{frame.source}|{frame.info!r}"
        for k in [k for k, t in self._chat_recent.items() if now - t > CHAT_DUPLICATE_SECONDS]:
            del self._chat_recent[k]
        if key in self._chat_recent:
            return
        self._chat_recent[key] = now
        text = frame.info.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n").strip()
        prefix = f"{frame.source}: "
        if text.upper().startswith(prefix.upper()):
            text = text[len(prefix):]
        self._chat_add({"time": now, "from": str(frame.source), "to": str(frame.destination),
                        "text": text, "out": False})

    def _chat_add(self, entry: dict[str, Any]) -> None:
        self.chat.append(entry)
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "chat", "entry": entry})

    async def send_chat(self, text: str) -> None:
        """Packet chat: just the text in a UI frame to CQ, direct (no digipeaters, nothing of APRS).
        Our callsign is the frame's source, so the text carries nothing else."""
        text = text.strip()
        if not text:
            return
        await self.send_unproto("CQ", text)
        self._chat_add({"time": time.time(), "from": str(self.me), "to": "CQ",
                        "text": text, "out": True})

    async def send_unproto(self, destination: str, text: str, path: str = "") -> None:
        """A UI frame with plain text (classic unproto, e.g. to CQ or ID)."""
        frame = Frame(Address.parse(destination or "CQ"), self.me,
                      [Address.parse(p) for p in _paths(path)], text.replace("\n", "\r").encode("utf-8"))
        await self.send_frame(frame.encode())

    def session_states(self) -> dict[str, str]:
        return {k: s.state for k, s in self.sessions.items() if s.state != DISCONNECTED}
