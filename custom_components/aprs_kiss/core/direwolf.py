"""Direwolf as the sound-card modem: the app writes its configuration, starts it and talks KISS to it over TCP.

Direwolf (WB2OSZ) is a software TNC: AFSK 1200 Bd from the radio's audio through a sound card (an AIOC cable,
a DigiRig, a SignaLink, any USB sound card), PTT by the sound card's GPIO (CM108), a serial port's RTS or DTR,
or the radio's VOX. It runs as a separate program; this module finds it, writes direwolf.conf in the app's data
folder, starts it (connection "direwolf"), keeps the end of its output for the settings, and stops it with the
engine. The KISS link itself is plain TCP to 127.0.0.1.

Not on phones (there is no Direwolf for Android or iOS), and not from inside a Flatpak sandbox: there Direwolf
is started by hand and the app connects with "KISS over TCP/IP".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

from .connection import Streams, TncSettings, register_transport

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 8101  # not Direwolf's own 8001: one started by hand may already be there
CONFIG_NAME = "direwolf.conf"
START_SECONDS = 15.0  # Direwolf opens the sound card and its KISS port within this
LOG_LINES = 300

_WINDOWS_PLACES = (r"C:\direwolf\direwolf.exe", r"C:\Program Files\direwolf\direwolf.exe",
                   r"C:\Program Files (x86)\direwolf\direwolf.exe")
_MAC_PLACES = ("/opt/homebrew/bin/direwolf", "/usr/local/bin/direwolf")


def in_flatpak() -> bool:
    return os.path.exists("/.flatpak-info")


def find_binary(path: str = "") -> str | None:
    """Direwolf's program: the path given in the settings, else on PATH or in the usual places."""
    if path:
        return path if os.path.isfile(path) else None
    found = shutil.which("direwolf")
    if found:
        return found
    places = _WINDOWS_PLACES if sys.platform == "win32" else _MAC_PLACES if sys.platform == "darwin" else ()
    return next((p for p in places if os.path.isfile(p)), None)


def sound_cards() -> list[tuple[str, str]]:
    """(ADEVICE value, name) of the sound cards on Linux ("plughw:1,0", "USB Audio Device"); [] elsewhere
    (Direwolf on Windows and macOS takes the system's default or a number / name typed in)."""
    if not sys.platform.startswith("linux") or not shutil.which("arecord"):
        return []
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5,
                             env={**os.environ, "LC_ALL": "C"}).stdout  # its English list, not "karta 1: …"
    except (OSError, subprocess.SubprocessError):
        return []
    cards = []
    for m in re.finditer(r"^card (\d+): [^[]*\[([^\]]*)\], device (\d+): [^[]*\[([^\]]*)\]", out, re.M):
        cards.append((f"plughw:{m.group(1)},{m.group(3)}", f"{m.group(2)} – {m.group(4)}"))
    return cards


def make_config(callsign: str, adevice: str, ptt: str, port: int) -> str:
    """direwolf.conf: one channel, 1200 Bd AFSK, KISS on `port` (AGW off).
    ptt: "" = VOX (no PTT line), "CM108" (the sound card's GPIO), "RTS:/dev/ttyUSB0" or "DTR:COM3"."""
    lines = ["# Written by APRS & Packet; changed in the app's Settings › TNC connection, not here.",
             *( [f"ADEVICE {adevice}"] if adevice else [] ),
             "ACHANNELS 1", "CHANNEL 0", f"MYCALL {callsign or 'N0CALL'}", "MODEM 1200"]
    if ptt == "CM108":
        lines.append("PTT CM108")
    elif ptt.startswith(("RTS:", "DTR:")) and len(ptt) > 4:
        lines.append(f"PTT {ptt[4:]} {ptt[:3]}")
    lines += ["AGWPORT 0", f"KISSPORT {int(port)}", ""]
    return "\n".join(lines)


class Direwolf:
    """The one Direwolf the app starts."""

    def __init__(self) -> None:
        self.binary = ""
        self.config_text = ""
        self.config_path: Path | None = None
        self.proc: asyncio.subprocess.Process | None = None
        self.log: deque[str] = deque(maxlen=LOG_LINES)
        self._reader: asyncio.Task | None = None

    def configure(self, binary: str, config_text: str, folder: Path) -> None:
        self.binary, self.config_text, self.config_path = binary, config_text, folder / CONFIG_NAME

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    async def start(self) -> None:
        if self.running:
            return
        if in_flatpak():
            raise OSError("Direwolf cannot be started from the Flatpak: start it yourself and use KISS over TCP/IP")
        if not self.binary:
            raise OSError("Direwolf is not installed")
        assert self.config_path is not None
        await asyncio.to_thread(self.config_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(self.config_path.write_text, self.config_text, "utf-8")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: no console window
        self.log.append(f"$ {self.binary} -c {self.config_path} -t 0")
        self.proc = await asyncio.create_subprocess_exec(
            self.binary, "-c", str(self.config_path), "-t", "0", stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL, creationflags=flags)
        self._reader = asyncio.ensure_future(self._read(self.proc))

    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                self.log.append(text)
        code = await proc.wait()
        self.log.append(f"Direwolf ended ({code})")

    def last_error(self) -> str:
        for line in reversed(self.log):
            if re.search(r"error|could not|can't|cannot|not found|failed", line, re.I):
                return line
        return self.log[-1] if self.log else "Direwolf did not start"

    async def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
            self._reader = None


MODEM = Direwolf()


async def _open(s: TncSettings) -> Streams:
    """Start Direwolf (once) and connect to its KISS port as soon as it listens."""
    await MODEM.start()
    loop = asyncio.get_running_loop()
    end = loop.time() + START_SECONDS
    while True:
        if not MODEM.running:
            raise OSError(f"Direwolf stopped: {MODEM.last_error()}")
        try:
            return await asyncio.wait_for(asyncio.open_connection("127.0.0.1", s.port), timeout=3)
        except (OSError, asyncio.TimeoutError):
            if loop.time() > end:
                raise OSError(f"Direwolf does not answer on port {s.port}: {MODEM.last_error()}") from None
            await asyncio.sleep(0.5)


register_transport("direwolf", _open)
