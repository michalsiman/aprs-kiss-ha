"""Connection to a KISS TNC over TCP or a serial port, with automatic reconnect.

No Home Assistant imports, so it can be tested on its own. The serial
transport needs pyserial-asyncio-fast (a Home Assistant core dependency).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from .ax25 import CMD_PERSISTENCE, CMD_TXDELAY, KissDecoder, kiss_frame

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 2.0
RECONNECT_MAX = 60.0


@dataclass
class TncSettings:
    """Where the TNC is and how to talk to it."""

    kind: str  # "tcp" or "serial"
    host: str = ""
    port: int = 8001
    device: str = ""
    baudrate: int = 9600
    txdelay_ms: int | None = None  # sent to the TNC after connecting, if set
    persistence: int | None = None


class KissConnection:
    """Keeps a KISS link up and hands received AX.25 frames to `on_frame`."""

    def __init__(
        self,
        settings: TncSettings,
        on_frame: Callable[[bytes], None],
        on_state: Callable[[bool], None] | None = None,
    ) -> None:
        self._settings = settings
        self._on_frame = on_frame
        self._on_state = on_state
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.connected = False
        self.connected_since: float | None = None
        self.reconnects = 0
        self.last_error: str | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="aprs_kiss_connection")

    async def stop(self) -> None:
        self._stop.set()
        if self._writer is not None:
            self._writer.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._set_state(False)

    def _set_state(self, connected: bool) -> None:
        if connected == self.connected:
            return
        self.connected = connected
        self.connected_since = time.time() if connected else None
        if self._on_state:
            self._on_state(connected)

    async def _open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        s = self._settings
        if s.kind == "serial":
            import serial_asyncio_fast  # noqa: PLC0415 - optional, only for serial TNCs

            return await serial_asyncio_fast.open_serial_connection(url=s.device, baudrate=s.baudrate)
        return await asyncio.wait_for(asyncio.open_connection(s.host, s.port), timeout=10)

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while not self._stop.is_set():
            try:
                reader, writer = await self._open()
            except (OSError, asyncio.TimeoutError, ImportError) as err:
                self.last_error = str(err) or type(err).__name__
                _LOGGER.debug("KISS TNC not reachable (%s), retrying in %.0f s", self.last_error, delay)
                await self._sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)
                continue
            self._writer = writer
            self.last_error = None
            delay = RECONNECT_MIN
            self._set_state(True)
            _LOGGER.info("Connected to KISS TNC")
            await self._send_parameters()
            decoder = KissDecoder()
            try:
                while not self._stop.is_set():
                    data = await reader.read(1024)
                    if not data:
                        raise ConnectionResetError("TNC closed the connection")
                    for frame in decoder.feed(data):
                        try:
                            self._on_frame(frame)
                        except Exception:  # noqa: BLE001 - one bad frame must not drop the link
                            _LOGGER.exception("Error handling a received frame")
            except (OSError, ConnectionError) as err:
                self.last_error = str(err) or type(err).__name__
                _LOGGER.warning("KISS TNC connection lost: %s", self.last_error)
            finally:
                self._writer = None
                with contextlib.suppress(Exception):
                    writer.close()
                self._set_state(False)
            if not self._stop.is_set():
                self.reconnects += 1
                await self._sleep(RECONNECT_MIN)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)

    async def _send_parameters(self) -> None:
        s = self._settings
        if s.txdelay_ms is not None:
            await self._write(kiss_frame(bytes((max(0, min(255, s.txdelay_ms // 10)),)), CMD_TXDELAY))
        if s.persistence is not None:
            await self._write(kiss_frame(bytes((max(0, min(255, s.persistence)),)), CMD_PERSISTENCE))

    async def _write(self, data: bytes) -> None:
        if self._writer is None:
            raise ConnectionError("KISS TNC is not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def send(self, ax25_frame: bytes) -> None:
        """Hand one AX.25 frame to the TNC for transmission."""
        await self._write(kiss_frame(ax25_frame))
