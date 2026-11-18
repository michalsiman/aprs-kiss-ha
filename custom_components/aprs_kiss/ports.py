"""Where the TNC is: the serial ports this computer has, and checking a new setting.

No Home Assistant imports. pyserial (a Home Assistant core dependency)
describes USB adapters; without it the usual device names are listed.
The stable /dev/serial/by-id/… name is preferred: it stays the same when
the radio is plugged in again or the ports are numbered differently.
"""

from __future__ import annotations

import glob
import os
from typing import Any

_FALLBACK_PATTERNS = ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/ttyAMA*", "/dev/ttyCH*", "/dev/rfcomm*")


def _by_id() -> dict[str, str]:
    """Real device path → its /dev/serial/by-id name."""
    names: dict[str, str] = {}
    for link in sorted(glob.glob("/dev/serial/by-id/*")):
        try:
            names.setdefault(os.path.realpath(link), link)
        except OSError:
            continue
    return names


def list_serial_ports() -> list[dict[str, str]]:
    """Ports as {"device": path to use, "label": what to show}. Blocking: run in an executor."""
    by_id = _by_id()
    ports: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        from serial.tools import list_ports  # noqa: PLC0415 - optional

        found = list(list_ports.comports())
    except Exception:  # noqa: BLE001 - pyserial missing or failing: fall back to names
        found = []
    for p in found:
        real = os.path.realpath(p.device)
        if real.startswith("/dev/ttyS") and not getattr(p, "vid", None):
            continue  # built-in serial ports without anything behind them
        device = by_id.get(real, p.device)
        parts = [x for x in (getattr(p, "manufacturer", None), getattr(p, "product", None) or p.description) if x and x != "n/a"]
        if getattr(p, "vid", None) is not None and getattr(p, "pid", None) is not None:
            parts.append(f"{p.vid:04x}:{p.pid:04x}")
        label = f"{os.path.basename(real)} – {' · '.join(parts)}" if parts else os.path.basename(real)
        ports.append({"device": device, "label": label})
        seen.add(real)
    for pattern in _FALLBACK_PATTERNS:
        for path in sorted(glob.glob(pattern)):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            ports.append({"device": by_id.get(real, path), "label": os.path.basename(real)})
    for real, link in by_id.items():
        if real not in seen:
            seen.add(real)
            ports.append({"device": link, "label": os.path.basename(link)})
    return ports


def connection_update(settings: dict[str, Any]) -> dict[str, Any]:
    """The connection part of panel settings, checked; empty when none was sent."""
    if "connection" not in settings:
        return {}
    kind = str(settings.get("connection") or "")
    if kind not in ("tcp", "serial"):
        raise ValueError("The connection is tcp or serial")
    out: dict[str, Any] = {"connection": kind}
    if kind == "tcp":
        host = str(settings.get("host") or "").strip()
        if not host:
            raise ValueError("tnc_host_required")
        port = int(settings.get("port") or 0)
        if not 1 <= port <= 65535:
            raise ValueError("The TNC port is 1–65535")
        out.update(host=host, port=port)
    else:
        device = str(settings.get("device") or "").strip()
        if not device.startswith("/dev/"):
            raise ValueError("tnc_device_required")
        baud = int(settings.get("baudrate") or 0)
        if not 1200 <= baud <= 1000000:
            raise ValueError("The speed is 1200–1000000 baud")
        out.update(device=device, baudrate=baud)
    return out
