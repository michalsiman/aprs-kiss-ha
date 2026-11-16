#!/usr/bin/env python3
"""KISS serial ↔ TCP bridge (Python standard library only).

Shares a KISS TNC on a USB serial port (e.g. a Quansheng UV-K1/UV-K5 V3 with
the F4HWN KISS TNC app) as a KISS TCP server, so Home Assistant or any KISS
client on the network can use it.

- Bytes are passed through unchanged in both directions (KISS framing stays).
- One client at a time; a new client replaces the old one.
- The serial port is reopened whenever it disappears: radios can reset their
  USB port at key-up, and the device comes back after a moment.
- Only clients from --allow addresses are accepted (default: any).

Example:
  kiss_tcp_bridge.py --device /dev/serial/by-id/usb-...-if00 --port 8001 --allow 192.168.0.24
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import os
import termios
import time

LOG = logging.getLogger("kiss-bridge")


class SerialPort:
    """A raw, non-blocking serial port read through the event loop."""

    def __init__(self, device: str, baud: int) -> None:
        self.device = device
        self.baud = baud
        self.fd: int | None = None

    def open(self) -> None:
        fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(fd)
        attrs[0] = 0                                  # iflag: raw
        attrs[1] = 0                                  # oflag: raw
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0                                  # lflag: no echo, no canonical mode
        speed = getattr(termios, f"B{self.baud}", termios.B115200)
        attrs[4] = attrs[5] = speed
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        termios.tcflush(fd, termios.TCIOFLUSH)
        self.fd = fd

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


class Bridge:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.serial = SerialPort(args.device, args.baud)
        self.client: asyncio.StreamWriter | None = None
        self.serial_up = asyncio.Event()
        self.stats = {"to_radio": 0, "from_radio": 0, "serial_reopens": 0}
        self.allow = [ipaddress.ip_network(a, strict=False) for a in args.allow] if args.allow else []

    # ─── serial side ──────────────────────────────────────────────────────

    async def serial_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            try:
                self.serial.open()
            except OSError as err:
                if self.serial_up.is_set() or self.stats["serial_reopens"] == 0:
                    LOG.warning("Serial port %s not available (%s), waiting", self.args.device, err)
                self.serial_up.clear()
                await asyncio.sleep(2)
                continue
            self.stats["serial_reopens"] += 1
            LOG.info("Serial port %s open", self.args.device)
            self.serial_up.set()
            lost = loop.create_future()

            def readable() -> None:
                try:
                    data = os.read(self.serial.fd, 4096)
                except OSError as err:
                    if not lost.done():
                        lost.set_result(err)
                    return
                if not data:
                    # A closed USB device reads as end of file.
                    if not lost.done():
                        lost.set_result("end of file")
                    return
                self.stats["from_radio"] += len(data)
                if self.client is not None:
                    self.client.write(data)

            loop.add_reader(self.serial.fd, readable)
            reason = await lost
            loop.remove_reader(self.serial.fd)
            self.serial.close()
            self.serial_up.clear()
            LOG.warning("Serial port lost (%s), reopening", reason)
            await asyncio.sleep(1)

    def write_serial(self, data: bytes) -> None:
        if self.serial.fd is None:
            LOG.debug("Dropped %d bytes: serial port not open", len(data))
            return
        view = memoryview(data)
        deadline = time.monotonic() + 2
        while view and time.monotonic() < deadline:
            try:
                n = os.write(self.serial.fd, view)
                view = view[n:]
                self.stats["to_radio"] += n
            except BlockingIOError:
                time.sleep(0.005)
            except OSError as err:
                LOG.warning("Write to serial failed: %s", err)
                return

    # ─── TCP side ─────────────────────────────────────────────────────────

    def allowed(self, peer: str) -> bool:
        if not self.allow:
            return True
        ip = ipaddress.ip_address(peer)
        return any(ip in net for net in self.allow)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")[0]
        if not self.allowed(peer):
            LOG.warning("Refused client %s", peer)
            writer.close()
            return
        if self.client is not None:
            LOG.info("New client %s replaces the previous one", peer)
            self.client.close()
        self.client = writer
        LOG.info("Client %s connected", peer)
        try:
            while data := await reader.read(4096):
                self.write_serial(data)
        except (ConnectionError, OSError):
            pass
        finally:
            if self.client is writer:
                self.client = None
            writer.close()
            LOG.info("Client %s disconnected", peer)

    async def stats_loop(self) -> None:
        while True:
            await asyncio.sleep(3600)
            LOG.info("Stats: %s", self.stats)

    async def run(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.args.bind, self.args.port)
        LOG.info("KISS TCP server on %s:%d for %s", self.args.bind, self.args.port, self.args.device)
        async with server:
            await asyncio.gather(server.serve_forever(), self.serial_loop(), self.stats_loop())


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", required=True, help="serial device, best a /dev/serial/by-id/... path")
    p.add_argument("--baud", type=int, default=115200, help="ignored by USB CDC radios (default 115200)")
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--allow", action="append", default=[], help="client address or network (repeatable)")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(Bridge(args).run())


if __name__ == "__main__":
    main()
