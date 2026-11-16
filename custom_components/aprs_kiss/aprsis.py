"""APRS-IS client and iGate rules. No Home Assistant imports.

APRS-IS (https://www.aprs-is.net) is the internet side of APRS: a TCP
connection to a server (port 14580 takes a filter), a login line with the
callsign and its passcode, then one packet per line in TNC2 form.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable

_LOGGER = logging.getLogger(__name__)

DEFAULT_SERVER = "euro.aprs2.net"
DEFAULT_PORT = 14580
RECONNECT_MIN = 5.0
RECONNECT_MAX = 300.0
KEEPALIVE = 120.0  # seconds without a line from the server before reconnecting is considered

# Path elements that must not be gated from RF to the internet (APRS-IS iGate rules).
NO_GATE = {"TCPIP", "TCPXX", "NOGATE", "RFONLY"}


# What the user types to confirm a licence before APRS-IS is switched on (compared
# without case, accents, extra spaces or a final full stop).
LICENCE_STATEMENTS = (
    "mam platnou radioamaterskou licenci",
    "i hold a valid amateur radio licence",
    "i hold a valid amateur radio license",
)


def licence_confirmed(text: str | None) -> bool:
    """True when `text` is the licence statement, in Czech or English."""
    import unicodedata  # noqa: PLC0415

    plain = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = " ".join(plain.lower().split()).rstrip(".!").strip()
    return plain in LICENCE_STATEMENTS


def decode_line(raw: bytes) -> tuple[str, bool]:
    """An APRS-IS line as text, and whether it looks garbled.

    Lines are UTF-8 nowadays (Czech comments and the like); older software sends
    Latin-1. A line that is neither, with several stray high bytes or control
    characters, is usually a packet a (LoRa) iGate received with bit errors.
    """
    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    high = sum(1 for b in raw if b >= 0x80)
    control = any(b < 0x20 or 0x7F <= b < 0xA0 for b in raw)
    return text, control or high >= 3


def passcode(callsign: str) -> int:
    """The APRS-IS passcode of a callsign (the SSID does not matter)."""
    call = callsign.split("-")[0].upper()
    code = 0x73E2
    for i in range(0, len(call), 2):
        code ^= ord(call[i]) << 8
        if i + 1 < len(call):
            code ^= ord(call[i + 1])
    return code & 0x7FFF


def gate_to_is(source: str, destination: str, path: list[str], info: bytes, igate: str) -> str | None:
    """The line to send to APRS-IS for a packet heard on RF, or None when it must not be gated."""
    plain = [p.rstrip("*").upper() for p in path]
    if any(p in NO_GATE or p.startswith("Q") and len(p) == 3 for p in plain):
        return None
    if not info or info[:1] in (b"?",):
        return None  # queries stay local
    if info[:1] == b"}":
        inner = info[1:].split(b":", 1)[0].upper()
        if b"TCPIP" in inner or b"TCPXX" in inner:
            return None  # third-party traffic that came from the internet
    try:
        text = info.decode("latin-1")
    except UnicodeDecodeError:
        return None
    if "\r" in text or "\n" in text:
        text = text.split("\r")[0].split("\n")[0]
    via = "".join(f",{p}" for p in path)
    return f"{source}>{destination}{via},qAR,{igate}:{text}"


def third_party(line_source: str, line_destination: str, info: str, igate: str) -> str:
    """Info field for transmitting an internet packet on RF (APRS 1.0 third-party format)."""
    return f"}}{line_source}>{line_destination},TCPIP,{igate}*:{info}"


class AprsIsClient:
    """Keeps an APRS-IS connection up; received lines go to `on_line`."""

    def __init__(
        self,
        host: str,
        port: int,
        callsign: str,
        code: int,
        filter_: str,
        software: str,
        on_line: Callable[[str, bool], None],
        on_state: Callable[[bool], None],
    ) -> None:
        self.host = host
        self.port = port
        self.callsign = callsign
        self.code = code
        self.filter = filter_
        self.software = software
        self._on_line = on_line
        self._on_state = on_state
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.connected = False
        self.verified = False
        self.server_name: str | None = None
        self.last_error: str | None = None
        self.lines_in = 0
        self.lines_out = 0

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="aprs_kiss_aprsis")

    async def stop(self) -> None:
        self._stop.set()
        if self._writer is not None:
            self._writer.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        self._set(False)

    def _set(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            if not connected:
                self.verified = False
            self._on_state(connected)

    async def _run(self) -> None:
        delay = RECONNECT_MIN
        while not self._stop.is_set():
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 15)
            except (OSError, asyncio.TimeoutError) as err:
                self.last_error = str(err) or type(err).__name__
                await self._sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)
                continue
            self._writer = writer
            login = f"user {self.callsign} pass {self.code} vers {self.software}"
            if self.filter:
                login += f" filter {self.filter}"
            writer.write((login + "\r\n").encode())
            await writer.drain()
            self._set(True)
            delay = RECONNECT_MIN
            try:
                while not self._stop.is_set():
                    raw = await asyncio.wait_for(reader.readline(), KEEPALIVE * 2)
                    if not raw:
                        raise ConnectionResetError("server closed the connection")
                    line, garbled = decode_line(raw.rstrip(b"\r\n"))
                    if line.startswith("#"):
                        if "logresp" in line:
                            self.verified = " verified" in line and "unverified" not in line
                            parts = line.split("server")
                            self.server_name = parts[-1].strip() if len(parts) > 1 else None
                            self._on_state(True)
                        continue
                    self.lines_in += 1
                    try:
                        self._on_line(line, garbled)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception("Error handling an APRS-IS line")
            except (OSError, asyncio.TimeoutError, ConnectionError) as err:
                self.last_error = str(err) or type(err).__name__
                _LOGGER.info("APRS-IS connection lost: %s", self.last_error)
            finally:
                self._writer = None
                with contextlib.suppress(Exception):
                    writer.close()
                self._set(False)
            await self._sleep(RECONNECT_MIN)

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)

    async def send(self, line: str) -> bool:
        if self._writer is None or not self.verified:
            return False
        self._writer.write((line + "\r\n").encode("latin-1", "replace"))
        await self._writer.drain()
        self.lines_out += 1
        return True
