"""Ties the TNC connection, the APRS station and the terminal sessions to Home Assistant."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .ax25 import Address, Frame, PF, U_DM
from .connection import KissConnection, TncSettings
from .const import (
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

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        stored = await self._store.async_load() or {}
        self._msg_counter = int(stored.get("msg_counter", 0))
        self.messages.extend(stored.get("messages", []))
        await self.connection.start()

    async def async_stop(self) -> None:
        for s in self.sessions.values():
            s.close()
        await self.station.close()
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

    async def send_aprs_message(self, to: str, text: str) -> dict[str, Any]:
        msg = await self.station.send_message(to, text)
        item = {"direction": "out", "from": str(self.me), "to": msg.to, "text": msg.text, "time": msg.created,
                "msg_no": msg.msg_id}
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
        if not frame.info or frame.source == self.me:
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
                        "text": text, "aprs": self.is_aprs(frame), "out": False})

    def _chat_add(self, entry: dict[str, Any]) -> None:
        self.chat.append(entry)
        self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": self.entry.entry_id, "kind": "chat", "entry": entry})

    async def send_chat(self, text: str, destination: str = "CQ", path: str = "") -> None:
        """Plain text to everyone: '<our call>: text' in a UI frame."""
        text = text.strip()
        if not text:
            return
        await self.send_unproto(destination or "CQ", f"{self.me}: {text}", path)
        self._chat_add({"time": time.time(), "from": str(self.me), "to": (destination or "CQ").upper(),
                        "text": text, "aprs": False, "out": True})

    async def send_unproto(self, destination: str, text: str, path: str = "") -> None:
        """A UI frame with plain text (classic unproto, e.g. to CQ or ID)."""
        frame = Frame(Address.parse(destination or "CQ"), self.me,
                      [Address.parse(p) for p in _paths(path)], text.replace("\n", "\r").encode("utf-8"))
        await self.send_frame(frame.encode())

    def session_states(self) -> dict[str, str]:
        return {k: s.state for k, s in self.sessions.items() if s.state != DISCONNECTED}
