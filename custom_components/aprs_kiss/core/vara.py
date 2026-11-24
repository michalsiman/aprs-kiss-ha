"""VARA FM as a modem for the terminal: one connected session at a time, over VARA's TCP interface.

VARA (EA5HVK) runs on its own (Windows, or Wine on Linux) with the radio on a sound card such as
an AIOC cable. We talk to its command port (8300 by default) with text commands ending in CR and
pass the session's data through the data port (command port + 1). See "VARA Protocol Native TNC
Commands" (EA5HVK, 2022): MYCALL, LISTEN, CONNECT src dst [via d1 d2], DISCONNECT, ABORT; VARA
answers OK/WRONG and reports CONNECTED, DISCONNECTED, PENDING, BUFFER, PTT, BUSY, IAMALIVE…
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8300
RECONNECT_SECONDS = 10.0

IDLE, CONNECTING, CONNECTED, DISCONNECTING = "idle", "connecting", "connected", "disconnecting"


class VaraClient:
    """Keeps the TCP link to VARA up and runs one session through it.

    on_state(state, reason): the session changed (connecting, connected, idle…), with a readable reason.
    on_text(text): data received in the session.
    on_status(): VARA's link or flags (busy, PTT, buffer) changed.
    """

    def __init__(self, host: str, port: int, mycall: str, on_state: Callable[[str, str], None],
                 on_text: Callable[[str], None], on_status: Callable[[], None] | None = None) -> None:
        self.host, self.port, self.mycall = host, int(port or DEFAULT_PORT), mycall.upper()
        self._on_state, self._on_text, self._on_status = on_state, on_text, on_status
        self.link_up = False  # TCP to VARA
        self.last_error = ""
        self.state = IDLE
        self.remote = ""
        self.busy = self.ptt = False
        self.buffer = 0
        self._cmd_w: asyncio.StreamWriter | None = None
        self._data_w: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._run(), name="aprs_kiss_vara")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._close()

    def _close(self) -> None:
        for w in (self._cmd_w, self._data_w):
            if w:
                with contextlib.suppress(Exception):
                    w.close()
        self._cmd_w = self._data_w = None
        if self.link_up:
            self.link_up = False
            self._status()
        if self.state != IDLE:
            self._set(IDLE, "VARA link lost")

    async def _run(self) -> None:
        while True:
            try:
                cmd_r, self._cmd_w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 10)
                data_r, self._data_w = await asyncio.wait_for(asyncio.open_connection(self.host, self.port + 1), 10)
            except (OSError, asyncio.TimeoutError) as err:
                self.last_error = str(err) or type(err).__name__
                self._close()
                await asyncio.sleep(RECONNECT_SECONDS)
                continue
            self.link_up, self.last_error = True, ""
            self._status()
            await self.command(f"MYCALL {self.mycall}")
            await self.command("LISTEN OFF")
            readers = [asyncio.create_task(self._read_cmd(cmd_r)), asyncio.create_task(self._read_data(data_r))]
            try:
                await asyncio.wait(readers, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in readers:
                    t.cancel()
                self.last_error = self.last_error or "VARA closed the connection"
                self._close()
            await asyncio.sleep(RECONNECT_SECONDS)

    async def _read_cmd(self, reader: asyncio.StreamReader) -> None:
        buf = b""
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                return
            buf += chunk.replace(b"\n", b"\r")
            while b"\r" in buf:
                line, buf = buf.split(b"\r", 1)
                if line.strip():
                    self._line(line.decode("ascii", "replace").strip())

    async def _read_data(self, reader: asyncio.StreamReader) -> None:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                return
            self._on_text(chunk.decode("utf-8", "replace"))

    # ─── VARA → us ────────────────────────────────────────────────────────

    def _line(self, line: str) -> None:
        word, _, rest = line.partition(" ")
        word = word.upper()
        if word == "CONNECTED":
            parts = rest.split()
            self.remote = parts[1] if len(parts) > 1 else self.remote
            self._set(CONNECTED, f"connected to {self.remote}")
        elif word == "DISCONNECTED":
            self.buffer = 0
            self._set(IDLE, "disconnected")
        elif word == "PENDING":
            self._set(self.state, "connect request on the air")
        elif word == "CANCELPENDING":
            if self.state == CONNECTING:
                self._set(IDLE, "no answer")
        elif word == "BUFFER":
            with contextlib.suppress(ValueError):
                self.buffer = int(rest.strip() or 0)
            self._status()
        elif word == "PTT":
            self.ptt = rest.strip().upper() == "ON"
            self._status()
        elif word == "BUSY":
            self.busy = rest.strip().upper() == "ON"
            self._status()
        elif word == "WRONG":
            _LOGGER.info("VARA refused a command")
            if self.state == CONNECTING:
                self._set(IDLE, "VARA refused the connect command")
        elif word == "MISSING":
            self.last_error = line
            self._status()

    def _set(self, state: str, reason: str) -> None:
        self.state = state
        self._on_state(state, reason)

    def _status(self) -> None:
        if self._on_status:
            self._on_status()

    # ─── us → VARA ────────────────────────────────────────────────────────

    async def command(self, text: str) -> None:
        if not self._cmd_w:
            raise ConnectionError(f"VARA is not reachable at {self.host}:{self.port}")
        self._cmd_w.write(text.encode("ascii", "replace") + b"\r")
        await self._cmd_w.drain()

    async def connect(self, remote: str, via: list[str] | None = None) -> None:
        if self.state != IDLE:
            raise ConnectionError("VARA is already in a session")
        self.remote = remote.upper()
        digis = f" via {' '.join(d.upper() for d in via)}" if via else ""
        await self.command(f"CONNECT {self.mycall} {self.remote}{digis}")
        self._set(CONNECTING, f"connecting to {self.remote} over VARA FM")

    async def disconnect(self) -> None:
        """A clean end of the session; while still connecting, stop trying at once."""
        if self.state == CONNECTING:
            await self.command("ABORT")
            self._set(IDLE, "cancelled")
        elif self.state == CONNECTED:
            await self.command("DISCONNECT")
            self._set(DISCONNECTING, "disconnecting")

    async def send(self, text: str) -> None:
        if self.state != CONNECTED or not self._data_w:
            raise ConnectionError("Not connected")
        self._data_w.write(text.replace("\n", "\r").encode("utf-8"))
        await self._data_w.drain()
