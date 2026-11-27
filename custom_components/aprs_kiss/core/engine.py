"""Ties the TNC connection, the APRS station, APRS-IS and the terminal sessions together.

The standalone counterpart of the Home Assistant integration's hub.py. It knows
nothing about any user interface: everything that happens is announced to the
listeners added with `add_listener(callback)` as `callback(kind, data)`:

    "monitor"       {"line": str}                   one frame, TNC style
    "terminal"      {"entry": {...}}                text of a connected session
    "state"         {"remote": str, "state": str}   a session changed state
    "chat"          {"entry": {...}}                packet chat line
    "aprs_message"  {"message": {...}}              an APRS message in or out (history item)
    "message"       {...}                           an APRS message addressed to us (for notifications)
    "packet"        {...}                           every decoded APRS packet
    "update"        {}                              something in the status changed

All of it runs on one asyncio event loop; listeners are called on that loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import aprs as aprs_build
from . import thursday
from .aprsis import AprsIsClient, gate_to_is, passcode, third_party
from .ax25 import PF, U_DM, Address, Frame, frequency_command
from .bbs import BbsConfigError, BbsServer
from . import digipeater, tak, yapp
from .tracker import Tracker, course_speed, distance_m
from .station import _track as station_track
from . import vara as vara_mod
from .gps import GpsFix, GpsReader, PushedGps
from .config import MIN_BEACON_MINUTES, VERSION, Config, data_dir, load_state, save_state
from .connection import KissConnection, TncSettings
from .parser import parse
from .session import CONNECT_ATTEMPTS, CONNECTED, DISCONNECTED, Session
from .station import Station, StationConfig, TransmitRefused

_LOGGER = logging.getLogger(__name__)

MONITOR_LINES = 500
THURSDAY_LINES = 300
BBS_TICK_SECONDS = 20
THURSDAY_DUPLICATE_SECONDS = 15 * 60
TERMINAL_LINES = 2000
MESSAGE_HISTORY = 500
CHAT_LINES = 500
CHAT_DUPLICATE_SECONDS = 30
# A station counts as local (for gating internet messages to RF) if heard on RF this recently.
LOCAL_SECONDS = 1800
SAVE_DELAY = 5.0
# First character of an APRS information field (APRS 1.0.1, data type identifiers).
APRS_TYPES = set("!=/@;)`':>?<$_{}*#")
# Packet chat is text meant for people: frames to these, or to our own callsign. Automatic
# frames (a digipeater's "DX de ..." report to DX, station IDs to ID or BEACON) stay in the monitor.
CHAT_DESTINATIONS = {"CQ", "QST", "ALL"}

CHAT_MAX_BYTES = 256  # AX.25 N1: longer information fields are dropped by some TNCs


def chat_parts(text: str, limit: int = CHAT_MAX_BYTES) -> list[str]:
    """The chat text as the information fields of one or more UI frames (docs/CHAT.md).

    Each part fits in `limit` bytes of UTF-8, split at a space or line break where possible, and a part
    that would start with an APRS data type character gets a leading space, so receivers do not take
    it for APRS (they strip the space again).
    """
    parts: list[str] = []
    rest = text.strip()
    while rest:
        room = limit - 1  # keep a byte for the leading space a part may need
        if len(rest.encode("utf-8")) <= room:
            cut = len(rest)
        else:
            cut = 0
            for i in range(len(rest)):
                if len(rest[: i + 1].encode("utf-8")) > room:
                    break
                cut = i + 1
            gap = max(rest.rfind(" ", 0, cut), rest.rfind("\n", 0, cut))
            if gap > cut // 2:
                cut = gap
        part, rest = rest[:cut].rstrip(), rest[cut:].strip()
        if part:
            parts.append(" " + part if part[0] in APRS_TYPES else part)
    return parts


Listener = Callable[[str, dict[str, Any]], None]

__all__ = ["Engine", "TransmitRefused"]


class Engine:
    """One TNC with one callsign."""

    def __init__(self, config: Config, data_folder: Path | None = None) -> None:
        self.config = config
        self._folder = data_folder
        self._listeners: list[Listener] = []
        self._msg_counter = 0
        self.messages: deque[dict[str, Any]] = deque(maxlen=MESSAGE_HISTORY)
        self.monitor: deque[str] = deque(maxlen=MONITOR_LINES)
        self.monitor_rf: deque[str] = deque(maxlen=MONITOR_LINES)  # the same without APRS-IS lines
        self.terminal: deque[dict[str, Any]] = deque(maxlen=TERMINAL_LINES)
        self.chat: deque[dict[str, Any]] = deque(maxlen=CHAT_LINES)
        # #APRSThursday: the HOTG group's traffic and ANSRVR's answers, kept out of the inbox.
        self.thursday: deque[dict[str, Any]] = deque(maxlen=THURSDAY_LINES)
        self.thursday_joined = 0.0  # when we last sent a CQ to HOTG (0 = not in the group)
        self.thursday_cq = 0.0  # the last CQ, for the server's one-per-30-minutes rule
        self._thursday_recent: dict[str, float] = {}
        self._chat_recent: dict[str, float] = {}
        self.sessions: dict[str, Session] = {}
        # file transfers (YAPP over a connected link): the newest last; who is sending or receiving now
        self.transfers: deque[dict[str, Any]] = deque(maxlen=50)
        self._yapp: dict[str, Any] = {}  # remote -> yapp.Sender or yapp.Receiver
        self._offers: dict[str, Callable[[bool], None]] = {}
        self.igate_stats = {"rf_to_is": 0, "is_to_rf": 0, "is_messages": 0}
        self.digi_dedupe = digipeater.Dedupe()
        self.digipeated = 0
        self._tasks: set[asyncio.Task] = set()
        self._beacon_task: asyncio.Task | None = None
        self._tracker_task: asyncio.Task | None = None
        self.tracker = Tracker()
        self.my_track: dict[str, Any] = {}  # where we went (GPS), the map's trail for our own station
        self.bbs: BbsServer | None = None
        self.bbs_call: Address | None = None
        self.bbs_error = ""
        self.bbs_sessions: dict[str, Session] = {}
        self.gps: GpsReader | PushedGps | None = None
        self.vara: vara_mod.VaraClient | None = None
        # TAK: the stations heard (uid -> event), the GeoChat messages and the position loop
        self.tak_stations: dict[str, dict[str, Any]] = {}
        self.tak_chat: deque[dict[str, Any]] = deque(maxlen=CHAT_LINES)
        self._tak_task: asyncio.Task | None = None
        self.gps_error = ""
        self._gps_shown: tuple | None = None
        self._bbs_task: asyncio.Task | None = None
        self._save_handle: asyncio.TimerHandle | None = None
        self._loaded = False
        self.running = False
        self._build(tx_enabled=False)

    # ─── listeners ────────────────────────────────────────────────────────

    def add_listener(self, listener: Listener) -> Callable[[], None]:
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener) if listener in self._listeners else None

    def _emit(self, kind: str, data: dict[str, Any] | None = None) -> None:
        for listener in list(self._listeners):
            try:
                listener(kind, data or {})
            except Exception:  # noqa: BLE001 - a broken listener must not stop the radio
                _LOGGER.exception("Listener failed on %s", kind)

    # ─── building from the config ─────────────────────────────────────────

    @property
    def bbs_mode(self) -> bool:
        """BBS SERVER on: the radio sits on the BBS frequency and the app is only the BBS -
        no APRS, APRS-IS, iGate, beacon, messages, terminal or chat until it is switched off."""
        return bool(self.config.bbs_enabled and self.config.configured)

    @property
    def tak_mode(self) -> bool:
        """TAK on: the app is a TAK station over the radio (positions and GeoChat) and nothing else.
        BBS SERVER wins if both were switched on in the settings file."""
        return bool(self.config.tak_enabled and self.config.configured and not self.bbs_mode)

    @property
    def exclusive_mode(self) -> str:
        return "bbs" if self.bbs_mode else "tak" if self.tak_mode else ""

    def _not_in_bbs_mode(self) -> None:
        if self.bbs_mode:
            raise TransmitRefused("BBS SERVER is on: everything else is off")
        if self.tak_mode:
            raise TransmitRefused("TAK is on: everything else is off")

    def _build(self, tx_enabled: bool) -> None:
        conf = self.config
        self.me = Address.parse(conf.callsign or "NOCALL")
        bbs = bool((conf.bbs_enabled or conf.tak_enabled) and conf.configured)  # an exclusive mode
        self.accept_incoming = (conf.accept_incoming or conf.files_accept) and not bbs
        self.igate_rx = conf.igate_rx and not bbs
        self.igate_tx = conf.igate_tx and not bbs
        self.connection = KissConnection(
            TncSettings(kind=conf.connection, host=conf.host, port=int(conf.port), device=conf.device,
                        baudrate=int(conf.baudrate), txdelay_ms=conf.txdelay_ms or None),
            self._on_frame,
            self._on_connection_state,
        )
        self.station = Station(
            StationConfig(str(self.me), conf.paths(), conf.symbol, conf.comment),
            self.send_frame, parse, self._on_packet, self._on_message, self._on_update, self._next_msg_number,
        )
        self.station.tx_enabled = tx_enabled
        self._build_bbs()
        self._build_gps()
        self.vara = None
        if conf.vara_host and conf.configured and not self.exclusive_mode:
            self.vara = vara_mod.VaraClient(conf.vara_host, int(conf.vara_port or vara_mod.DEFAULT_PORT), str(self.me),
                                            self._vara_state, self._vara_text, self._on_update)
        self.aprsis: AprsIsClient | None = None
        if conf.aprsis_on and conf.callsign and not self.exclusive_mode:
            code = conf.aprsis_passcode or passcode(str(self.me))
            area = self._is_area()
            self.aprsis = AprsIsClient(
                conf.aprsis_host, int(conf.aprsis_port), str(self.me), int(code), area,
                f"aprs-kiss {VERSION}", self._on_is_line, self._on_is_state,
            )
            self.station.send_is = self._send_own_to_is

    _is_center: tuple[float, float] | None = None

    def _is_area(self) -> str:
        """APRS-IS filter: the stations within the chosen radius of where we are (the GPS fix or the
        position typed in). Without it the server sends nothing but our own traffic."""
        radius = int(self.config.aprsis_radius_km or 0)
        here = self.my_position()
        self._is_center = None  # not yet known: the first fix sets the area (a stale one would block that)
        if radius <= 0 or here is None:
            return ""
        self._is_center = here
        return f"r/{here[0]:.3f}/{here[1]:.3f}/{radius}"

    def set_is_radius(self, km: int) -> None:
        """Chosen on the map: the server is asked for the new area at once (no reconnecting)."""
        self.config.aprsis_radius_km = int(km)
        if self.aprsis:
            self.aprsis.set_filter(self._is_area())

    def _follow_is_area(self) -> None:
        """The GPS moved (or got its first fix): the APRS-IS area follows, past a tenth of its radius."""
        if not self.aprsis:
            return
        here = self.my_position()
        if here is None:
            return
        radius = int(self.config.aprsis_radius_km or 0)
        if self._is_center is not None:
            moved_km = ((here[0] - self._is_center[0]) * 111) ** 2 + ((here[1] - self._is_center[1]) * 72) ** 2
            if moved_km < (max(radius, 10) / 10) ** 2:
                return
        self.aprsis.set_filter(self._is_area())

    # ─── own position: typed in, or from a USB GPS module ────────────────

    def _build_gps(self) -> None:
        old = getattr(self, "gps", None)
        self.gps, self.gps_error, self._gps_shown = None, "", None
        conf = self.config
        if conf.gps_source == "phone" and not self.bbs_mode:
            self.gps = PushedGps(self._on_gps_fix, self._on_update)  # the app pushes the phone's fixes
            if isinstance(old, PushedGps):  # settings saved: where we are is still known (APRS-IS area, beacon)
                self.gps.fix, self.gps.connected = old.fix, old.connected
            return
        if conf.gps_source != "usb" or self.bbs_mode:
            return
        if not conf.gps_device:
            self.gps_error = "No GPS port chosen"
            return
        if conf.connection == "serial" and conf.device and conf.gps_device == conf.device:
            self.gps_error = "The GPS must be on another port than the TNC"
            return
        self.gps = GpsReader(conf.gps_device, int(conf.gps_baudrate or 0), self._on_gps_fix, self._on_update)

    def _on_gps_fix(self, fix: GpsFix) -> None:
        # Announce it only when something visible changes (about 1 m, the satellites, the fix).
        shown = (fix.usable(), round(fix.latitude or 0, 5), round(fix.longitude or 0, 5), fix.satellites)
        if fix.usable():
            station_track(self.my_track, time.time(), fix.latitude, fix.longitude)
        if shown != self._gps_shown:
            self._gps_shown = shown
            self._follow_is_area()
            self._emit("gps")
            self._on_update()

    def gps_fix(self) -> GpsFix | None:
        """The GPS fix when there is a usable one."""
        return self.gps.fix if self.gps and self.gps.fix.usable() else None

    def my_position(self) -> tuple[float, float] | None:
        """Where we are: the GPS fix when there is one, else the position typed in Settings."""
        fix = self.gps_fix()
        if fix:
            return fix.latitude, fix.longitude
        conf = self.config
        return (conf.latitude, conf.longitude) if conf.has_position else None

    def _position_comment(self, comment: str) -> str:
        """APRS altitude extension (/A=feet) when the GPS knows it."""
        fix = self.gps_fix()
        if not fix:
            return comment
        moving = course_speed(fix.course, fix.speed_kmh)  # "088/036": where we head and how fast
        if fix.altitude_m is not None:
            comment = f"/A={max(0, round(fix.altitude_m / 0.3048)):06d} {comment}".rstrip()
        return moving + comment

    # ─── TAK ──────────────────────────────────────────────────────────────

    @staticmethod
    def _monitor_line(frame: Frame) -> str:
        """TNC-style line; TAK frames (binary protobuf) are shown decoded."""
        if frame.is_ui and frame.destination.call == tak.DESTINATION:
            text = tak.monitor_text(frame.info)
            if text:
                return f"{frame.source}>{frame.destination} <UI>: {text}"
        return frame.monitor()

    @property
    def tak_uid(self) -> str:
        return str(self.me)

    @property
    def tak_callsign(self) -> str:
        return (self.config.tak_callsign or "").strip() or str(self.me)

    def _tak_frame(self, frame: Frame) -> None:
        try:
            ev = tak.decode(frame.info)
        except (ValueError, IndexError) as err:
            self._monitor(f"? TAK frame not understood ({err})")
            return
        if ev.uid == self.tak_uid or ev.uid.startswith(f"GeoChat.{self.tak_uid}."):
            return  # our own, back from a digipeater
        now = time.time()
        if ev.type == tak.TYPE_CHAT:
            chat = ev.extra
            to = chat.get("to") or "All"
            if to not in ("All", tak.ALL_CHAT, self.tak_uid):
                return  # a private message for someone else
            self._tak_chat_add({"time": now, "from": chat.get("sender") or str(frame.source),
                                "uid": ev.uid.split(".")[1] if ev.uid.count(".") >= 3 else str(frame.source),
                                "to": to, "text": chat.get("text", ""), "out": False})
            return
        if ev.lat == 0.0 and ev.lon == 0.0:
            return
        self.tak_stations[ev.uid] = {"uid": ev.uid, "callsign": ev.callsign or ev.uid, "type": ev.type,
                                     "team": ev.team, "role": ev.role, "lat": ev.lat, "lon": ev.lon,
                                     "hae": None if ev.hae >= tak.UNKNOWN else ev.hae, "speed": ev.speed,
                                     "course": ev.course, "battery": ev.battery, "stale": ev.stale_ms / 1000,
                                     "received": now, "via": str(frame.source)}
        self._emit("tak", {"uid": ev.uid})
        self._on_update()

    def _tak_chat_add(self, entry: dict[str, Any]) -> None:
        self.tak_chat.append(entry)
        self._emit("tak", {"chat": entry})

    async def _tak_send(self, event: tak.TakEvent) -> None:
        payload = event.encode()
        await self.send_frame(Frame(Address.parse(tak.DESTINATION), self.me, [], payload).encode())

    async def send_tak_position(self) -> None:
        """Our position as a TAK PLI: from the GPS when it has a fix (with altitude, speed and course)."""
        if not self.tak_mode:
            raise TransmitRefused("TAK is off")
        here = self.my_position()
        if not here:
            raise ValueError("No position set")
        fix = self.gps_fix()
        interval = max(1, int(self.config.tak_interval_min or 0) or 5)
        await self._tak_send(tak.pli(self.tak_uid, self.tak_callsign, *here, team=self.config.tak_team,
                                     role=self.config.tak_role,
                                     hae=fix.altitude_m if fix and fix.altitude_m is not None else None,
                                     speed=(fix.speed_kmh or 0) / 3.6 if fix else 0.0,
                                     course=(fix.course or 0) if fix else 0.0, stale_s=interval * 60 * 3))

    async def send_tak_chat(self, text: str, to_uid: str = "", to_callsign: str = "") -> None:
        """GeoChat to everybody, or to one station (its uid)."""
        if not self.tak_mode:
            raise TransmitRefused("TAK is off")
        text = text.strip()
        if not text:
            return
        for event in tak.geochat_events(self.tak_uid, self.tak_callsign, text, to_uid, to_callsign):
            await self._tak_send(event)
        self._tak_chat_add({"time": time.time(), "from": self.tak_callsign, "uid": self.tak_uid,
                            "to": to_uid or "All", "to_callsign": to_callsign, "text": text, "out": True})

    async def _tak_loop(self) -> None:
        await asyncio.sleep(5)  # let the TNC connect first
        while True:
            minutes = int(self.config.tak_interval_min or 0)
            if minutes > 0 and self.station.tx_enabled:
                with contextlib.suppress(TransmitRefused, ConnectionError, ValueError):
                    await self.send_tak_position()
            await asyncio.sleep(max(1, minutes) * 60)

    # ─── BBS server ───────────────────────────────────────────────────────

    def bbs_folder(self) -> Path:
        return (self._folder or data_dir()) / "bbs"

    def _build_bbs(self) -> None:
        self.bbs, self.bbs_call, self.bbs_error = None, None, ""
        conf = self.config
        if not (conf.bbs_enabled and conf.configured):
            return
        try:
            call = Address(self.me.call, int(conf.bbs_ssid))
            if call == self.me:
                raise BbsConfigError(f"The BBS needs another SSID than the station ({call})")
            self.bbs = BbsServer(self.bbs_folder(), str(call), VERSION, self._bbs_send, self._bbs_disconnect,
                                 lambda: self._emit("bbs"), conf.language or "en")
            self.bbs_call = call
        except (BbsConfigError, ValueError, OSError) as err:
            self.bbs_error = str(err)
            _LOGGER.warning("BBS server not started: %s", err)

    def bbs_reload(self) -> None:
        """Read bbs.toml again without dropping the connected users."""
        if self.bbs:
            self.bbs.reload()

    def _bbs_frame(self, frame: Frame, back: list[Address]) -> None:
        key = str(frame.source)
        sess = self.bbs_sessions.get(key)
        if sess is None or sess.state == DISCONNECTED:
            if frame.kind == "SABM" and self.station.tx_enabled and self.bbs and self.bbs.can_accept(key):
                sess = self._new_bbs_session(frame.source, back)
            else:
                if (frame.kind == "SABM" or (frame.command and frame.poll_final)) and self.station.tx_enabled:
                    reply = Frame(frame.source, self.bbs_call, back, b"", U_DM | (PF if frame.poll_final else 0),
                                  None, False)
                    self._spawn(self._send_quietly(reply.encode()))
                return
        sess.handle(frame)

    def _new_bbs_session(self, remote: Address, path: list[Address]) -> Session:
        key = str(remote)

        def on_text(text: str) -> None:
            if self.bbs:
                self.bbs.receive(key, text)

        def on_state(state: str, _reason: str) -> None:
            if not self.bbs:
                return
            if state == "connected":
                self.bbs.connected(key)
            elif state == DISCONNECTED:
                self.bbs.disconnected(key)
                self.bbs_sessions.pop(key, None)
            self._emit("bbs")

        sess = Session(self.bbs_call, remote, path, self.send_frame, on_text, on_state)
        self.bbs_sessions[key] = sess
        return sess

    def _bbs_send(self, remote: str, text: str) -> None:
        sess = self.bbs_sessions.get(remote)
        if sess:
            sess.send_text(text)

    def _bbs_disconnect(self, remote: str) -> None:
        sess = self.bbs_sessions.get(remote)
        if sess:
            sess.disconnect()

    async def _bbs_loop(self) -> None:
        while True:
            await asyncio.sleep(BBS_TICK_SECONDS)
            if not self.bbs:
                continue
            text = self.bbs.tick()
            if text and self.station.tx_enabled and self.bbs_call:
                frame = Frame(Address.parse("MAIL"), self.bbs_call, [], text.encode("utf-8"))
                with contextlib.suppress(TransmitRefused, ConnectionError):
                    await self.send_frame(frame.encode())

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._loaded:
            stored = await asyncio.to_thread(load_state, self._folder)
            self._msg_counter = int(stored.get("msg_counter", 0))
            self.thursday.extend(stored.get("thursday", []))
            for m in stored.get("messages", []):  # HOTG relays kept as messages by older versions: to Thursday
                if m.get("direction") == "in" and thursday.is_group_text(m.get("text", "")):
                    self.thursday.append({"time": m.get("time", 0), "from": m.get("from", ""), "kind": "in",
                                          "text": thursday.strip_prefix(m.get("text", "")), "via": m.get("via")})
                else:
                    self.messages.append(m)
            if len(self.thursday) > 1:
                ordered = sorted(self.thursday, key=lambda e: e.get("time", 0))
                self.thursday.clear()
                self.thursday.extend(ordered)
            self.thursday_joined = float(stored.get("thursday_joined", 0) or 0)
            self.thursday_cq = float(stored.get("thursday_cq", 0) or 0)
            self._loaded = True
        self.running = True
        if not self.config.configured:
            self._on_update()
            return  # nothing to connect to before the callsign is set
        await self.connection.start()
        if self.aprsis:
            await self.aprsis.start()
        if self.config.beacon_minutes and not self.exclusive_mode:
            self._beacon_task = asyncio.create_task(self._beacon_loop(), name="aprs_kiss_beacon")
        if not self.exclusive_mode:
            self._tracker_task = asyncio.create_task(self._tracker_loop(), name="aprs_kiss_tracker")
        if self.bbs:
            self._bbs_task = asyncio.create_task(self._bbs_loop(), name="aprs_kiss_bbs")
        if self.gps:
            await self.gps.start()
        if self.vara:
            await self.vara.start()
        if self.tak_mode:
            self._tak_task = asyncio.create_task(self._tak_loop(), name="aprs_kiss_tak")
        self._on_update()

    async def stop(self) -> None:
        self.running = False
        for s in self.sessions.values():
            s.close()
        self.sessions.clear()
        if self.gps:
            await self.gps.stop()
        if self.vara:
            await self.vara.stop()
        if self._tak_task:
            self._tak_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tak_task
            self._tak_task = None
        for s in self.bbs_sessions.values():
            s.close()
        self.bbs_sessions.clear()
        if self.bbs:
            self.bbs.conns.clear()
        if self._bbs_task:
            self._bbs_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bbs_task
            self._bbs_task = None
        if self._beacon_task:
            self._beacon_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._beacon_task
            self._beacon_task = None
        if self._tracker_task:
            self._tracker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tracker_task
            self._tracker_task = None
        for task in list(self._tasks):
            task.cancel()
        await self.station.close()
        if self.aprsis:
            await self.aprsis.stop()
        await self.connection.stop()
        await self.save()

    async def reconfigure(self, config: Config) -> None:
        """Apply new settings: stop, rebuild, start again. History and the Transmit switch stay."""
        tx = self.station.tx_enabled and config.callsign == self.config.callsign
        heard = self.station.heard
        await self.stop()
        self.config = config
        self._build(tx_enabled=tx)
        self.station.heard = heard  # the stations heard stay on the map and in the list
        await self.start()

    async def save(self) -> None:
        if self._save_handle:
            self._save_handle.cancel()
            self._save_handle = None
        await asyncio.to_thread(save_state, self._state(), self._folder)

    def _state(self) -> dict[str, Any]:
        return {"msg_counter": self._msg_counter, "messages": list(self.messages), "thursday": list(self.thursday),
                "thursday_joined": self.thursday_joined, "thursday_cq": self.thursday_cq}

    def _schedule_save(self) -> None:
        if self._save_handle:
            return
        loop = asyncio.get_running_loop()
        self._save_handle = loop.call_later(SAVE_DELAY, lambda: self._spawn(self.save()))

    def _spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _next_msg_number(self) -> int:
        self._msg_counter += 1
        self._schedule_save()
        return self._msg_counter

    # ─── status ───────────────────────────────────────────────────────────

    @property
    def tx_enabled(self) -> bool:
        return self.station.tx_enabled

    def set_tx(self, enabled: bool) -> None:
        self.station.tx_enabled = bool(enabled) and self.config.configured
        self._on_update()

    def status(self) -> dict[str, Any]:
        return {
            "callsign": str(self.me) if self.config.configured else "",
            "tnc_connected": self.connection.connected,
            "tnc_error": self.connection.last_error,
            "tx_enabled": self.station.tx_enabled,
            "aprsis": {
                "connected": self.aprsis.connected,
                "verified": self.aprsis.verified,
                "server": self.aprsis.server_name,
                "error": self.aprsis.last_error,
            } if self.aprsis else None,
            "igate_stats": dict(self.igate_stats),
            "digipeated": self.digipeated,
            "stats": dict(self.station.stats),
            "sessions": self.session_states(),
            "gps": {
                "connected": self.gps.connected,
                "fix": self.gps.fix.usable(),
                "satellites": self.gps.fix.satellites,
                "speed": self.gps.speed,
                "accuracy": self.gps.fix.accuracy_m,
                "phone": isinstance(self.gps, PushedGps),
                "error": self.gps.last_error,
            } if self.gps else ({"error": self.gps_error} if self.gps_error else None),
            "vara": {"link": self.vara.link_up, "error": self.vara.last_error, "state": self.vara.state,
                     "ptt": self.vara.ptt, "busy": self.vara.busy} if self.vara else None,
        }

    # ─── sending ──────────────────────────────────────────────────────────

    async def send_frame(self, raw: bytes) -> None:
        """Every transmission goes through here: refused while transmitting is off."""
        if not self.station.tx_enabled:
            raise TransmitRefused("Transmitting is switched off")
        await self.connection.send(raw)
        self._monitor(self._monitor_line(Frame.decode(raw)), outgoing=True)

    async def _send_quietly(self, raw: bytes) -> None:
        try:
            await self.send_frame(raw)
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Frame not sent: %s", err)

    # ─── receiving ────────────────────────────────────────────────────────

    def _on_frame(self, raw: bytes) -> None:
        try:
            frame = Frame.decode(raw)
        except ValueError as err:
            self._monitor(f"? undecodable frame ({err}): {raw.hex()}")
            return
        self._monitor(self._monitor_line(frame))
        if self.bbs_mode:
            if self.bbs_call and frame.destination == self.bbs_call and not frame.is_ui:
                self._bbs_frame(frame, [Address(d.call, d.ssid) for d in reversed(frame.path)])
            return  # only the BBS listens; APRS, chat and the terminal are off
        if self.tak_mode:
            if frame.is_ui and frame.destination.call == tak.DESTINATION:
                self._tak_frame(frame)
            return  # only TAK listens
        self._digipeat(frame)
        if frame.is_ui:
            if frame.destination.call == tak.DESTINATION:
                return  # TAK (binary protobuf), only in TAK mode; never an APRS station or chat
            self._chat_frame(frame)
            self.station.handle_frame(raw)
            return
        if frame.destination != self.me:
            return
        key = str(frame.source)
        sess = self.sessions.get(key)
        back = [Address(d.call, d.ssid) for d in reversed(frame.path)]
        if sess is None or sess.state == DISCONNECTED:
            if frame.kind == "SABM" and self.accept_incoming and self.station.tx_enabled:
                sess = self._new_session(frame.source, back)
            elif frame.kind == "SABM" or (frame.command and frame.poll_final):
                if self.station.tx_enabled:
                    reply = Frame(frame.source, self.me, back, b"", U_DM | (PF if frame.poll_final else 0), None, False)
                    self._spawn(self._send_quietly(reply.encode()))
                return
            elif sess is None:
                return
        sess.handle(frame)

    def _digipeat(self, frame: Frame) -> None:
        """Settings › Digipeater: repeat what the path asks of us (only with transmitting on)."""
        conf = self.config
        aliases = digipeater.parse_aliases(conf.digi_aliases)
        if not self.station.tx_enabled or (conf.digi_mode == "off" and not aliases):
            return
        out = digipeater.repeat(frame, self.me, conf.digi_mode, aliases, int(conf.digi_max_hops or 2))
        if out is not None and self.digi_dedupe.fresh(frame):
            self.digipeated += 1
            self._spawn(self._send_quietly(out.encode()))

    def _monitor(self, line: str, outgoing: bool = False) -> None:
        entry = f"{time.strftime('%H:%M:%S')} {'>>' if outgoing else '<<'} {line}"
        self.monitor.append(entry)
        if not line.startswith("[IS] "):
            self.monitor_rf.append(entry)
        self._emit("monitor", {"line": entry})

    def _on_packet(self, packet: dict[str, Any]) -> None:
        self._emit("packet", packet)
        if self.igate_rx and self.aprsis and self.aprsis.verified:
            src, _, rest = packet["raw"].partition(">")
            dst = rest.split(",", 1)[0].split(":", 1)[0]
            info = rest.split(":", 1)[1].encode("latin-1", "replace") if ":" in rest else b""
            line = gate_to_is(src, dst, list(packet.get("path", [])), info, str(self.me))
            if line:
                self._spawn(self._gate_up(line))

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

    def _on_is_state(self, connected: bool) -> None:
        self._on_update()

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
        self._spawn(self._gate_down(third_party(src, dst, info, str(self.me))))

    async def _gate_down(self, info: str) -> None:
        try:
            await self.station.send_info(info, rf=True, to_is=False)
            self.igate_stats["is_to_rf"] += 1
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Internet message not sent on RF: %s", err)
        self._on_update()

    # ─── beacon ───────────────────────────────────────────────────────────

    async def _beacon_loop(self) -> None:
        interval = max(MIN_BEACON_MINUTES, int(self.config.beacon_minutes)) * 60
        while True:
            await asyncio.sleep(interval)
            if not self.config.tracker_on:  # the tracker sends on its own while it runs
                await self.beacon()

    async def beacon(self) -> bool:
        """Our position: by radio while transmitting is on; over the internet only when chosen."""
        if self.exclusive_mode:
            return False
        position = self.my_position()
        if not position:
            _LOGGER.debug("Beacon not sent: no position set")
            return False
        try:
            await self.station.send_position(*position, self._position_comment(self.config.comment),
                                             to_is=self.config.beacon_is)
        except (TransmitRefused, ConnectionError) as err:
            _LOGGER.debug("Beacon not sent: %s", err)
            return False
        return True

    # ─── tracker: the GPS position sent by itself, at a fixed rate or "smart" ─────

    TRACKER_TICK = 2.0

    def _tracker_settings(self) -> None:
        c, t = self.config, self.tracker
        t.mode, t.fixed_minutes, t.profile, t.still_minutes = (c.tracker_mode, c.tracker_minutes,
                                                               c.tracker_profile, c.tracker_still_minutes)

    def set_tracking(self, on: bool) -> None:
        """Start (the first position goes out at once) or stop the tracker."""
        self.config.tracker_on = bool(on)
        self.tracker.last_time = None
        self._emit("tracker")
        self._on_update()

    def _can_send_position(self) -> bool:
        return self.station.tx_enabled or bool(self.config.beacon_is and self.aprsis and self.aprsis.connected)

    async def tracker_tick(self, now: float | None = None) -> str | None:
        """One look: send our position when it is time; why it was sent, or None."""
        if not self.config.tracker_on or self.exclusive_mode:
            return None
        fix = self.gps_fix()
        if not fix or not self._can_send_position():
            return None  # waits for the GPS, or for transmitting to be switched on
        self._tracker_settings()
        now = time.time() if now is None else now
        position = (fix.latitude, fix.longitude)
        why = self.tracker.why(now, fix.speed_kmh, fix.course, position)
        if why and await self.beacon():
            self.tracker.sent(now, fix.course, position)
            self._emit("tracker")
            return why
        return None

    async def _tracker_loop(self) -> None:
        while True:
            await asyncio.sleep(self.TRACKER_TICK)
            try:
                await self.tracker_tick()
            except Exception:  # noqa: BLE001 - the tracker keeps going
                _LOGGER.exception("Tracker")

    def tracker_status(self) -> dict[str, Any]:
        fix = self.gps_fix()
        now = time.time()
        return {"on": self.config.tracker_on, "gps": bool(fix), "can_send": self._can_send_position(),
                "last": self.tracker.last_time,
                "next_in": self.tracker.next_in(now, fix.speed_kmh if fix else None) if fix else None}

    async def send_position(self, lat: float | None = None, lon: float | None = None,
                            comment: str | None = None) -> None:
        self._not_in_bbs_mode()
        position = self.my_position()
        if lat is None or lon is None:
            if not position:
                raise ValueError("No position set")
            lat, lon = position
            comment = self._position_comment(self.config.comment if comment is None else comment)
        # over the internet too only when chosen (Settings › APRS-IS), like the beacon and the tracker
        await self.station.send_position(lat, lon, comment, to_is=self.config.beacon_is)

    async def set_radio_frequency(self, mhz: float | None) -> None:
        """Tune a radio with a built-in KISS TNC (VR-N76, UV-PRO, GA-5WB, firmware 0.7.11+) to `mhz`, or (None)
        back to its own frequency. Radios without the command ignore it."""
        self._not_in_bbs_mode()
        hz = None
        if mhz is not None:
            if not 30 <= mhz <= 1300:
                raise ValueError("frequency out of range")
            hz = round(mhz * 1_000_000)
        await self.connection.send_hardware(frequency_command(hz))

    async def send_status(self, text: str) -> None:
        self._not_in_bbs_mode()
        await self.station.send_status(text)

    # ─── APRS messages ────────────────────────────────────────────────────

    def _on_message(self, message: dict[str, Any]) -> None:
        if thursday.is_server(message["from"]) or thursday.is_group_text(message.get("text", "")):
            self._thursday_in(message)
            return
        item = {"direction": "in", "from": message["from"], "to": str(self.me), "text": message["text"],
                "time": message["received_at"], "msg_no": message.get("msg_no"), "via": message.get("via")}
        item.update(self._distance_to(message["from"]))  # how far the sender was when the message came
        self.messages.append(item)
        self._schedule_save()
        self._emit("message", message)
        self._emit("aprs_message", {"message": item})

    def _distance_to(self, call: str) -> dict[str, float]:
        """{"km": …, "bearing": …} from where we are to the station's last known position, or {}."""
        here = self.my_position()
        there = self.station.heard.get(call) or self.station.heard.get(call.upper()) or {}
        if not here or there.get("latitude") is None or there.get("longitude") is None:
            return {}
        lat1, lon1, lat2, lon2 = map(math.radians, (*here, there["latitude"], there["longitude"]))
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        return {"km": round(distance_m(*here, there["latitude"], there["longitude"]) / 1000, 2),
                "bearing": round(math.degrees(math.atan2(y, x)) % 360)}

    # ─── #APRSThursday ────────────────────────────────────────────────────

    def _thursday_in(self, message: dict[str, Any]) -> None:
        """A HOTG message passed on by ANSRVR (from the original sender), or ANSRVR's own answer."""
        now = message.get("received_at") or time.time()
        text = message.get("text", "")
        key = f"{message['from'].upper()}|{text}"
        for k in [k for k, t in self._thursday_recent.items() if now - t > THURSDAY_DUPLICATE_SECONDS]:
            del self._thursday_recent[k]
        if key in self._thursday_recent:  # the same relay heard by radio and over the internet
            return
        self._thursday_recent[key] = now
        server = thursday.is_server(message["from"])
        if server and text.lower().startswith("removed from"):
            self.thursday_joined = 0.0
        entry = {"time": now, "from": message["from"], "text": text if server else thursday.strip_prefix(text),
                 "kind": "server" if server else "in", "via": message.get("via")}
        self._thursday_add(entry)

    def _thursday_add(self, entry: dict[str, Any]) -> None:
        self.thursday.append(entry)
        self._schedule_save()
        self._emit("thursday", {"entry": entry})

    def thursday_member_until(self, now: float | None = None) -> float:
        """Until when ANSRVR keeps us in HOTG (0 = not a member)."""
        until = self.thursday_joined + thursday.MEMBER_SECONDS if self.thursday_joined else 0.0
        return until if until > (now or time.time()) else 0.0

    def thursday_wait(self, now: float | None = None) -> float:
        """Seconds before the server takes another CQ from us."""
        return max(0.0, self.thursday_cq + thursday.CQ_INTERVAL - (now or time.time()))

    async def send_thursday(self, text: str, via: str = "both") -> dict[str, Any]:
        """Check in: "CQ HOTG <text>" to ANSRVR, which passes it on to the group and adds us to it."""
        self._not_in_bbs_mode()
        if not text.strip():
            raise ValueError("Empty message")
        wait = self.thursday_wait()
        if wait:
            raise ValueError(f"ANSRVR takes one message every 30 minutes; wait {int(wait // 60) + 1} min")
        msg = await self.station.send_message(thursday.SERVER, thursday.compose(text), via=via)
        now = time.time()
        self.thursday_cq = self.thursday_joined = now
        self._thursday_add({"time": now, "from": str(self.me), "text": thursday.strip_prefix(msg.text),
                            "kind": "out", "msg_no": msg.msg_id, "via": via})
        return msg.as_dict()

    async def leave_thursday(self, via: str = "both") -> None:
        """Leave HOTG ("U HOTG"), so the group's messages stop coming."""
        self._not_in_bbs_mode()
        msg = await self.station.send_message(thursday.SERVER, f"U {thursday.GROUP}", via=via)
        self.thursday_joined = 0.0
        self._thursday_add({"time": time.time(), "from": str(self.me), "text": msg.text, "kind": "leave",
                            "msg_no": msg.msg_id, "via": via})

    def _on_connection_state(self, connected: bool) -> None:
        self._on_update()

    def _on_update(self) -> None:
        self._emit("update")

    async def send_aprs_message(self, to: str, text: str, via: str = "both") -> dict[str, Any]:
        self._not_in_bbs_mode()
        msg = await self.station.send_message(to, text, via=via)
        item = {"direction": "out", "from": str(self.me), "to": msg.to, "text": msg.text, "time": msg.created,
                "msg_no": msg.msg_id, "via": via}
        self.messages.append(item)
        self._schedule_save()
        self._emit("aprs_message", {"message": item})
        return msg.as_dict()

    def delete_conversation(self, call: str) -> int:
        """Forget all messages with this station (in and out); how many went."""
        call = call.upper()

        def party(m: dict[str, Any]) -> str:
            return (m["from"] if m["direction"] == "in" else m["to"]).upper()

        keep = [m for m in self.messages if party(m) != call]
        gone = len(self.messages) - len(keep)
        self.messages = deque(keep, maxlen=MESSAGE_HISTORY)
        if gone:
            self._schedule_save()
            self._on_update()
        return gone

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

        def on_data(data: bytes) -> None:
            """A file transfer once it starts (YAPP), otherwise text for the terminal."""
            if key not in self._yapp and data[:2] == yapp.SI and self.config.files_accept:
                self._start_receiving(key)
            handler = self._yapp.get(key)
            if handler is not None:
                handler.feed(data)
                return
            text = data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
            if text:
                on_text(text)

        def on_state(state: str, reason: str) -> None:
            if key in self._yapp:
                if state == CONNECTED:
                    handler = self._yapp[key]
                    if isinstance(handler, yapp.Sender) and handler.state == "new":
                        handler.start()
                elif state == DISCONNECTED:
                    self._transfer_link_gone(key, reason)
            else:
                self._terminal(key, "state", reason or state)
            self._emit("state", {"remote": key, "state": state})
            self._on_update()

        sess = Session(self.me, remote, path, self.send_frame, on_text, on_state)
        sess.on_data = on_data
        self.sessions[key] = sess
        return sess

    # ─── files (YAPP over a connected link) ───────────────────────────────

    def files_folder(self) -> Path:
        return (self._folder or data_dir()) / "files"

    def _transfer(self, key: str) -> dict[str, Any] | None:
        for t in reversed(self.transfers):
            if t["remote"] == key and t["state"] in ("connecting", "waiting", "offered", "sending", "receiving"):
                return t
        return None

    def _transfer_update(self, key: str, **changes: Any) -> None:
        t = self._transfer(key) or (self.transfers[-1] if self.transfers and self.transfers[-1]["remote"] == key else None)
        if t is not None:
            t.update(changes)
            if changes.get("state") in ("done", "refused", "cancelled", "failed"):
                t["ended"] = time.time()
                self._yapp.pop(key, None)
                self._offers.pop(key, None)
        self._emit("files", {"remote": key})
        self._on_update()

    def send_file(self, remote: str, name: str, data: bytes, path: str = "") -> None:
        """Connect to the station and send it a file (YAPP)."""
        self._not_in_bbs_mode()
        if not self.station.tx_enabled:
            raise TransmitRefused("Transmitting is switched off")
        if not self.connection.connected:
            raise ConnectionError("The TNC is not connected")
        addr = Address.parse(remote)
        key = str(addr)
        if key in self._yapp:
            raise ValueError(f"A file transfer with {key} is already running")
        name = yapp.safe_name(name)
        self.transfers.append({"remote": key, "direction": "out", "name": name, "size": len(data), "done": 0,
                               "offset": 0, "state": "connecting", "started": time.time(), "detail": ""})
        sess = self._new_session(addr, [Address.parse(p) for p in Config(path=path).paths()])

        def on_state(state: str, detail: str) -> None:
            changes: dict[str, Any] = {"state": state, "detail": detail}
            if state == "sending":
                changes["offset"] = int(detail or 0)
                changes["data_started"] = time.time()
                changes["acked_at_start"] = sess.acked_bytes
            self._transfer_update(key, **changes)
            if state in ("done", "refused", "cancelled"):
                self._spawn(self._hang_up(key))

        self._yapp[key] = yapp.Sender(name, data, sess.send_bytes, on_state)
        sess.connect()

    def transfer_progress(self, t: dict[str, Any]) -> int:
        """Bytes of the file the other side has (sending: acknowledged by the link)."""
        if t["direction"] == "out" and t["state"] == "sending":
            sess = self.sessions.get(t["remote"])
            if sess is not None:
                sent = sess.acked_bytes - t.get("acked_at_start", 0)
                return max(0, min(t["size"], t.get("offset", 0) + sent))
        return t.get("done", 0) if t["state"] != "done" else t["size"]

    def _start_receiving(self, key: str) -> None:
        sess = self.sessions[key]
        folder = self.files_folder()
        self.transfers.append({"remote": key, "direction": "in", "name": "", "size": 0, "done": 0, "offset": 0,
                               "state": "waiting", "started": time.time(), "detail": ""})

        def ask(name: str, size: int, answer: Callable[[bool], None]) -> None:
            self._offers[key] = answer
            self._transfer_update(key, name=name, size=size, state="offered")
            self._emit("file_offer", {"remote": key, "name": name, "size": size})
            # nobody answered in two minutes: refused
            asyncio.get_running_loop().call_later(120, lambda: self.answer_file(key, False))

        def on_state(state: str, detail: str) -> None:
            changes: dict[str, Any] = {"state": state}
            if state == "receiving":
                changes.update(offset=int(detail or 0), data_started=time.time())
            if state == "done":
                changes["path"] = detail
            elif detail and state != "offered":
                changes["detail"] = detail
            self._transfer_update(key, **changes)

        def on_progress(got: int, size: int) -> None:
            t = self._transfer(key)
            if t is not None:
                t["done"] = got
                self._emit("files", {"remote": key})

        self._yapp[key] = yapp.Receiver(folder, sess.send_bytes, ask, on_state, on_progress)

    def answer_file(self, remote: str, accept: bool) -> None:
        answer = self._offers.pop(remote, None)
        if answer:
            answer(accept)

    def cancel_transfer(self, remote: str) -> None:
        handler = self._yapp.get(remote)
        if handler is not None:
            handler.cancel()
            self._spawn(self._hang_up(remote))

    async def _hang_up(self, key: str) -> None:
        await asyncio.sleep(3)  # the last packets and their acknowledgements first
        sess = self.sessions.get(key)
        if sess is not None and sess.state == CONNECTED and key not in self._yapp:
            sess.disconnect()

    def _transfer_link_gone(self, key: str, reason: str) -> None:
        handler = self._yapp.pop(key, None)
        if isinstance(handler, yapp.Receiver):
            handler._close()  # noqa: SLF001 - the part received stays, to resume later
        t = self._transfer(key)
        if t is not None:
            self._transfer_update(key, state="failed", detail=reason or "link lost")

    def _terminal(self, remote: str, kind: str, text: str) -> None:
        entry = {"time": time.time(), "remote": remote, "kind": kind, "text": text}
        self.terminal.append(entry)
        self._emit("terminal", {"entry": entry})

    def connect(self, remote: str, path: str = "", via: str = "ax25") -> None:
        """Connect the terminal: over AX.25 packet through the TNC, or over VARA FM (via="vara")."""
        self._not_in_bbs_mode()
        if not self.station.tx_enabled:
            raise TransmitRefused("Transmitting is switched off")
        if via == "vara":
            if not self.vara or not self.vara.link_up:
                where = f"{self.config.vara_host}:{self.config.vara_port}" if self.config.vara_host else "(not set)"
                raise ConnectionError(f"VARA FM is not reachable at {where}")
            if self.vara.state != vara_mod.IDLE:
                raise ConnectionError("VARA is already in a session")
            key = str(Address.parse(remote))
            self.vara.remote = key
            self._spawn(self.vara.connect(key, Config(path=path).paths()))
            return
        if not self.connection.connected:
            raise ConnectionError("The TNC is not connected")
        addr = Address.parse(remote)
        paths = Config(path=path).paths()
        sess = self._new_session(addr, [Address.parse(p) for p in paths])
        sess.connect()

    def disconnect(self, remote: str) -> None:
        if self._vara_session(remote):
            self._spawn(self.vara.disconnect())
            return
        sess = self.sessions.get(str(Address.parse(remote)))
        if sess:
            sess.disconnect()

    def send_text(self, remote: str, text: str) -> None:
        if self._vara_session(remote):
            if self.vara.state != vara_mod.CONNECTED:
                raise ConnectionError("Not connected")
            self._spawn(self.vara.send(text))
            self._terminal(str(Address.parse(remote)), "tx", text)
            return
        key = str(Address.parse(remote))
        sess = self.sessions.get(key)
        if sess is None:
            raise ConnectionError("Not connected")
        sess.send_text(text)
        self._terminal(key, "tx", text)

    def session_states(self) -> dict[str, str]:
        states = {k: s.state for k, s in self.sessions.items() if s.state != DISCONNECTED}
        if self.vara and self.vara.state != vara_mod.IDLE and self.vara.remote:
            states[self.vara.remote] = self.vara.state
        return states

    def session_info(self, remote: str) -> dict[str, Any] | None:
        """State of a terminal connection, with its connect attempts while it is connecting."""
        if self._vara_session(remote):
            v = self.vara
            return {"state": v.state, "via": "vara", "ptt": v.ptt, "busy": v.busy, "buffer": v.buffer}
        sess = self.sessions.get(str(Address.parse(remote))) if remote else None
        if sess is None or sess.state == DISCONNECTED:
            return None
        return {"state": sess.state, "attempts": sess.attempts, "max_attempts": CONNECT_ATTEMPTS,
                "started": sess.connect_started, "last_attempt": sess.last_attempt}

    # ─── VARA FM sessions for the terminal ────────────────────────────────

    def _vara_session(self, remote: str) -> bool:
        try:
            key = str(Address.parse(remote))
        except ValueError:
            return False
        return bool(self.vara and self.vara.state != vara_mod.IDLE and self.vara.remote == key)

    def _vara_state(self, state: str, reason: str) -> None:
        if self.vara and self.vara.remote:
            self._terminal(self.vara.remote, "state", f"VARA: {reason}")
            self._emit("state", {"remote": self.vara.remote, "state": state})
        self._on_update()

    def _vara_text(self, text: str) -> None:
        if self.vara and self.vara.remote:
            self._terminal(self.vara.remote, "rx", text)

    # ─── chat (plain text in UI frames) ───────────────────────────────────

    @staticmethod
    def is_aprs(frame: Frame) -> bool:
        info = frame.info
        return frame.destination.call.startswith("AP") or (bool(info) and chr(info[0]) in APRS_TYPES)

    def _chat_frame(self, frame: Frame) -> None:
        # Packet chat only: APRS packets never show up in the chat.
        if not frame.info or frame.source == self.me or self.is_aprs(frame):
            return
        if frame.destination.call not in CHAT_DESTINATIONS and frame.destination != self.me:
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
        self._emit("chat", {"entry": entry})

    async def send_chat(self, text: str) -> None:
        """Packet chat: just the text in a UI frame to CQ, direct (no digipeaters, nothing of APRS)."""
        self._not_in_bbs_mode()
        text = text.strip()
        if not text:
            return
        for part in chat_parts(text):
            await self.send_unproto("CQ", part)
        self._chat_add({"time": time.time(), "from": str(self.me), "to": "CQ", "text": text, "out": True})

    async def send_unproto(self, destination: str, text: str, path: str = "") -> None:
        """A UI frame with plain text (classic unproto, e.g. to CQ or ID)."""
        self._not_in_bbs_mode()
        frame = Frame(Address.parse(destination or "CQ"), self.me,
                      [Address.parse(p) for p in Config(path=path).paths()], text.replace("\n", "\r").encode("utf-8"))
        await self.send_frame(frame.encode())
