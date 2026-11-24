"""A USB GPS module as the source of our position: NMEA 0183 over a serial port.

Cheap modules (u-blox, VK-172, BU-353…) show up as a serial port and send NMEA sentences,
usually at 9600 or 4800 Bd. We read RMC (position, speed, course, validity) and GGA (fix
quality, satellites, altitude). With the speed set to 0 the reader tries the usual speeds
until it sees sentences with a good checksum.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

BAUDRATES = (9600, 4800, 38400, 115200)  # tried in this order when the speed is automatic
DETECT_SECONDS = 3.0  # time to wait for a good sentence at one speed
FIX_MAX_AGE = 10.0  # seconds: an older fix is no fix
RECONNECT_SECONDS = 5.0


@dataclass
class GpsFix:
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    speed_kmh: float | None = None
    course: float | None = None
    satellites: int = 0
    quality: int = 0  # GGA fix quality: 0 none, 1 GPS, 2 DGPS…
    valid: bool = False  # RMC status A
    time: float = 0.0  # when it was received (our clock)
    accuracy_m: float | None = None  # the phone's estimate; NMEA modules leave it empty
    max_age: float = FIX_MAX_AGE

    def usable(self, now: float | None = None) -> bool:
        return (self.valid and self.latitude is not None and self.longitude is not None
                and (now or time.time()) - self.time <= self.max_age)


def checksum_ok(line: str) -> bool:
    """'$GPRMC,...*hh': XOR of everything between $ and * equals hh."""
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, given = line[1:].partition("*")
    value = 0
    for ch in body:
        value ^= ord(ch)
    try:
        return value == int(given[:2], 16)
    except ValueError:
        return False


def _coord(value: str, hemi: str, degree_digits: int) -> float | None:
    if not value or not hemi:
        return None
    try:
        degrees = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError:
        return None
    result = degrees + minutes / 60
    return -result if hemi in ("S", "W") else result


def _float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def parse_sentence(line: str, fix: GpsFix, now: float | None = None) -> bool:
    """Update `fix` from one NMEA sentence (any talker: GP, GN, GL, GA…). True when it was used."""
    line = line.strip()
    if not checksum_ok(line):
        return False
    fields = line[1:].split("*")[0].split(",")
    kind = fields[0][2:]
    now = now or time.time()
    if kind == "RMC" and len(fields) >= 10:
        fix.valid = fields[2] == "A"
        lat, lon = _coord(fields[3], fields[4], 2), _coord(fields[5], fields[6], 3)
        if fix.valid and lat is not None and lon is not None:
            fix.latitude, fix.longitude = lat, lon
            knots = _float(fields[7])
            fix.speed_kmh = round(knots * 1.852, 1) if knots is not None else None
            fix.course = _float(fields[8])
            fix.time = now
        return True
    if kind == "GGA" and len(fields) >= 10:
        try:
            fix.quality = int(fields[6] or 0)
            fix.satellites = int(fields[7] or 0)
        except ValueError:
            return False
        if fix.quality > 0:
            fix.altitude_m = _float(fields[9])
        return True
    return kind in ("GSA", "GSV", "VTG", "GLL", "ZDA", "TXT")  # a GPS talking, but nothing we need


Opener = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


async def _open_serial(device: str, baudrate: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    import serial_asyncio_fast  # noqa: PLC0415 - only with a GPS

    return await serial_asyncio_fast.open_serial_connection(url=device, baudrate=baudrate)


class GpsReader:
    """Reads a GPS module, finds its speed when asked to, reconnects when it is unplugged."""

    def __init__(self, device: str, baudrate: int, on_fix: Callable[[GpsFix], None],
                 on_state: Callable[[], None] | None = None, opener: Opener = _open_serial) -> None:
        self.device = device
        self.baudrate = baudrate  # 0 = automatic
        self.fix = GpsFix()
        self.connected = False
        self.speed: int | None = None  # the speed in use
        self.last_error = ""
        self._on_fix, self._on_state, self._open = on_fix, on_state, opener
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not self._task:
            self._task = asyncio.create_task(self._run(), name="aprs_kiss_gps")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._set(False)

    def _set(self, connected: bool) -> None:
        if connected != self.connected:
            self.connected = connected
            if self._on_state:
                self._on_state()

    async def _run(self) -> None:
        while True:
            speeds = [self.baudrate] if self.baudrate else list(BAUDRATES)
            for speed in speeds:
                try:
                    reader, writer = await self._open(self.device, speed)
                except (OSError, ImportError, asyncio.TimeoutError) as err:
                    self.last_error = str(err) or type(err).__name__
                    break  # the port is not there: wait and try again
                try:
                    if await self._read(reader, speed, detect=not self.baudrate):
                        return
                except (OSError, ConnectionError) as err:
                    self.last_error = str(err) or type(err).__name__
                    _LOGGER.info("GPS lost: %s", self.last_error)
                finally:
                    writer.close()
                    self._set(False)
            await asyncio.sleep(RECONNECT_SECONDS)

    async def _read(self, reader: asyncio.StreamReader, speed: int, detect: bool) -> bool:
        """Read sentences until the port goes away; while detecting, give up on a speed with no good sentence."""
        deadline = time.monotonic() + DETECT_SECONDS if detect else None
        buffer = b""
        while True:
            timeout = max(0.1, deadline - time.monotonic()) if deadline else None
            try:
                chunk = await asyncio.wait_for(reader.read(1024), timeout) if timeout else await reader.read(1024)
            except asyncio.TimeoutError:
                return False  # nothing sensible at this speed
            if not chunk:
                raise ConnectionError("GPS closed the port")
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            if len(buffer) > 512:
                buffer = b""  # not NMEA at this speed
            for raw in lines:
                line = raw.decode("ascii", "replace")
                if parse_sentence(line, self.fix):
                    if not self.connected:
                        self.speed, self.last_error, deadline = speed, "", None
                        self._set(True)
                        _LOGGER.info("GPS on %s at %d Bd", self.device, speed)
                    if line.lstrip("$")[2:5] in ("RMC", "GGA"):
                        self._on_fix(self.fix)
            if deadline and time.monotonic() > deadline and not self.connected:
                return False


PHONE_FIX_MAX_AGE = 600.0  # a phone reports only when it moves: its last fix stays good a while


class PushedGps:
    """A GPS whose fixes are handed in from outside: the phone's own location service.

    The app asks the platform (Android, iOS) for the location and calls `push` with each one;
    the engine treats it like the USB module (same `fix`, `connected`, `last_error`).
    """

    speed: int | None = None  # no serial speed here

    def __init__(self, on_fix: Callable[[GpsFix], None], on_state: Callable[[], None] | None = None) -> None:
        self.fix = GpsFix(max_age=PHONE_FIX_MAX_AGE)
        self.connected = False
        self.last_error = ""
        self._on_fix, self._on_state = on_fix, on_state

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        self.set_state(False)

    def set_state(self, connected: bool, error: str = "") -> None:
        """The location service works (permission given, location on), or why not."""
        if (connected, error) != (self.connected, self.last_error):
            self.connected, self.last_error = connected, error
            if self._on_state:
                self._on_state()

    def push(self, latitude: float, longitude: float, altitude_m: float | None = None,
             speed_ms: float | None = None, course: float | None = None, accuracy_m: float | None = None) -> None:
        fix = self.fix
        fix.latitude, fix.longitude = latitude, longitude
        fix.altitude_m = altitude_m or None  # 0.0 means "not known" on phones
        fix.speed_kmh = speed_ms * 3.6 if speed_ms else None
        fix.course = course if speed_ms else None
        fix.accuracy_m = accuracy_m or None
        fix.valid, fix.quality, fix.time = True, 1, time.time()
        self.set_state(True)
        self._on_fix(fix)
