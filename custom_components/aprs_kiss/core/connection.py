"""Connection to a KISS TNC over TCP or a serial port, with automatic reconnect.

How the bytes get to the TNC is a *transport*: a coroutine that opens a
(reader, writer) pair of asyncio streams. "tcp" and "serial" are built in;
platforms add their own with `register_transport` (Android USB host,
Bluetooth SPP/BLE, ...) without touching the KISS logic here.
The serial transport needs pyserial-asyncio-fast.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .ax25 import CMD_HARDWARE, CMD_PERSISTENCE, CMD_TXDELAY, KissDecoder, kiss_frame

_LOGGER = logging.getLogger(__name__)

RECONNECT_MIN = 2.0
RECONNECT_MAX = 60.0
# A TNC on a cable or Bluetooth: looking for it is cheap, and a radio plugged in should be found at once.
LOCAL_KINDS = {"usb", "serial", "bt", "ble"}
RECONNECT_LOCAL = 3.0


@dataclass
class TncSettings:
    """Where the TNC is and how to talk to it."""

    kind: str  # a registered transport: "tcp", "serial", ...
    host: str = ""
    port: int = 8001
    device: str = ""
    baudrate: int = 9600
    txdelay_ms: int | None = None  # sent to the TNC after connecting, if set
    persistence: int | None = None


Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]
Transport = Callable[[TncSettings], Awaitable[Streams]]


async def _open_tcp(s: TncSettings) -> Streams:
    return await asyncio.wait_for(asyncio.open_connection(s.host, s.port), timeout=10)


async def _open_serial(s: TncSettings) -> Streams:
    import serial_asyncio_fast  # noqa: PLC0415 - optional, only for serial TNCs

    if not s.device:
        raise OSError("No serial port chosen")
    try:
        return await serial_asyncio_fast.open_serial_connection(url=s.device, baudrate=s.baudrate)
    except Exception as err:  # noqa: BLE001 - serial.SerialException and OSError: said plainly, then retried
        text = str(err)
        if isinstance(err, FileNotFoundError) or "No such file" in text or "Errno 2" in text \
                or "FileNotFoundError" in text or "cannot find the file" in text:
            raise OSError(f"The serial port {s.device} is not there") from err
        if "Errno 5" in text or "(5," in text or "Input/output" in text or "configure port" in text:
            # e.g. /dev/ttyS0: a port the computer names but has no hardware behind
            raise OSError(f"The serial port {s.device} does not answer") from err
        if "Permission denied" in text or "Errno 13" in text or "PermissionError" in text or "Access is denied" in text:
            raise OSError(f"Not allowed to open {s.device}") from err
        raise OSError(text or type(err).__name__) from err


TRANSPORTS: dict[str, Transport] = {"tcp": _open_tcp, "serial": _open_serial}


def register_transport(kind: str, opener: Transport) -> None:
    """Make another way of reaching a TNC available under `kind`."""
    TRANSPORTS[kind] = opener


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

    async def _open(self) -> Streams:
        opener = TRANSPORTS.get(self._settings.kind)
        if opener is None:
            raise OSError(f"Unknown TNC connection type: {self._settings.kind}")
        return await opener(self._settings)

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while not self._stop.is_set():
            try:
                reader, writer = await self._open()
            except (OSError, asyncio.TimeoutError, ImportError) as err:
                self.last_error = str(err) or type(err).__name__
                _LOGGER.debug("KISS TNC not reachable (%s), retrying in %.0f s", self.last_error, delay)
                await self._sleep(delay)
                delay = RECONNECT_LOCAL if self._settings.kind in LOCAL_KINDS else min(delay * 2, RECONNECT_MAX)
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
        """Wait before trying again; stop() or retry_now() end the wait early."""
        self._wake = asyncio.Event()
        stop, wake = asyncio.ensure_future(self._stop.wait()), asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({stop, wake}, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            stop.cancel()
            wake.cancel()

    _wake: asyncio.Event | None = None

    def retry_now(self) -> None:
        """Not connected: try again at once (the app came back to the screen, a radio may be plugged in)."""
        if self._wake is not None and not self.connected:
            self._wake.set()

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

    async def send_hardware(self, payload: bytes) -> None:
        """A KISS SetHardware command (the TNC's own, e.g. a radio's frequency)."""
        await self._write(kiss_frame(payload, CMD_HARDWARE))

    async def send(self, ax25_frame: bytes) -> None:
        """Hand one AX.25 frame to the TNC for transmission."""
        await self._write(kiss_frame(ax25_frame))
