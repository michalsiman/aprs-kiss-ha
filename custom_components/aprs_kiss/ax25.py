"""KISS framing and AX.25 UI frames (pure Python, no Home Assistant imports).

KISS (http://www.ax25.net/kiss.aspx): frames are delimited by FEND; FEND and
FESC inside a frame are escaped. The first byte of a frame is the port (high
nibble) and the command (low nibble); command 0 carries an AX.25 frame.

AX.25 UI frame as used by APRS: destination, source and up to 8 digipeater
addresses (7 bytes each: 6 shifted ASCII characters and an SSID byte), then
control 0x03 and PID 0xF0, then the information field. KISS carries no FCS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

CMD_DATA = 0x00
CMD_TXDELAY = 0x01
CMD_PERSISTENCE = 0x02

CONTROL_UI = 0x03
PID_NO_LAYER3 = 0xF0

MAX_DIGIPEATERS = 8


def kiss_escape(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        if b == FEND:
            out += bytes((FESC, TFEND))
        elif b == FESC:
            out += bytes((FESC, TFESC))
        else:
            out.append(b)
    return bytes(out)


def kiss_unescape(data: bytes) -> bytes:
    out = bytearray()
    escaped = False
    for b in data:
        if escaped:
            out.append(FEND if b == TFEND else FESC if b == TFESC else b)
            escaped = False
        elif b == FESC:
            escaped = True
        else:
            out.append(b)
    return bytes(out)


def kiss_frame(payload: bytes, command: int = CMD_DATA, port: int = 0) -> bytes:
    """One KISS frame, FEND on both ends."""
    return bytes((FEND, ((port & 0x0F) << 4) | (command & 0x0F))) + kiss_escape(payload) + bytes((FEND,))


class KissDecoder:
    """Collects bytes from a stream and returns complete data frames."""

    MAX_FRAME = 4096

    def __init__(self) -> None:
        self._buf = bytearray()
        self._in_frame = False

    def feed(self, data: bytes) -> list[bytes]:
        frames: list[bytes] = []
        for b in data:
            if b == FEND:
                if self._in_frame and self._buf:
                    raw = kiss_unescape(bytes(self._buf))
                    # Data frames only (command 0); TNC parameter echoes are ignored.
                    if raw and raw[0] & 0x0F == CMD_DATA and len(raw) > 1:
                        frames.append(raw[1:])
                self._buf.clear()
                self._in_frame = True
                continue
            if self._in_frame:
                self._buf.append(b)
                if len(self._buf) > self.MAX_FRAME:
                    self._buf.clear()
                    self._in_frame = False
        return frames


@dataclass(frozen=True)
class Address:
    """A callsign with SSID, e.g. OK1SIM-7."""

    call: str
    ssid: int = 0
    repeated: bool = False  # the H bit of a digipeater address

    @classmethod
    def parse(cls, text: str) -> Address:
        text = text.strip().upper()
        repeated = text.endswith("*")
        text = text.rstrip("*")
        call, _, ssid = text.partition("-")
        if not call or len(call) > 6 or not call.isalnum():
            raise ValueError(f"Not a callsign: {text!r}")
        n = int(ssid) if ssid else 0
        if not 0 <= n <= 15:
            raise ValueError(f"SSID out of range: {text!r}")
        return cls(call, n, repeated)

    def __str__(self) -> str:
        return self.call + (f"-{self.ssid}" if self.ssid else "")

    def encode(self, last: bool, command: bool = False) -> bytes:
        out = bytearray((ord(c) << 1) for c in self.call.ljust(6))
        ssid = 0x60 | (self.ssid << 1)
        if self.repeated or command:
            ssid |= 0x80
        if last:
            ssid |= 0x01
        out.append(ssid)
        return bytes(out)

    @classmethod
    def decode(cls, data: bytes) -> tuple[Address, bool]:
        """The address and whether it is the last one."""
        call = "".join(chr(b >> 1) for b in data[:6]).strip()
        ssid_byte = data[6]
        return cls(call, (ssid_byte >> 1) & 0x0F, bool(ssid_byte & 0x80)), bool(ssid_byte & 0x01)


# Control field (modulo 8). I frames: N(R)<<5 | P<<4 | N(S)<<1 | 0.
# S frames: N(R)<<5 | P/F<<4 | type | 01. U frames: type bits | P/F<<4 | 11.
S_RR = 0x01
S_RNR = 0x05
S_REJ = 0x09
U_SABM = 0x2F
U_DISC = 0x43
U_DM = 0x0F
U_UA = 0x63
U_FRMR = 0x87
U_UI = 0x03
PF = 0x10


def frame_kind(control: int) -> str:
    """'I', 'RR', 'RNR', 'REJ', 'SABM', 'DISC', 'DM', 'UA', 'FRMR', 'UI' or 'U?'."""
    if control & 0x01 == 0:
        return "I"
    if control & 0x03 == 0x01:
        return {S_RR: "RR", S_RNR: "RNR", S_REJ: "REJ"}.get(control & 0x0F, "S?")
    return {U_SABM: "SABM", U_DISC: "DISC", U_DM: "DM", U_UA: "UA", U_FRMR: "FRMR", U_UI: "UI"}.get(control & ~PF, "U?")


@dataclass
class Frame:
    """An AX.25 frame (version 2.0, modulo 8). APRS uses UI frames only."""

    destination: Address
    source: Address
    path: list[Address] = field(default_factory=list)
    info: bytes = b""
    control: int = CONTROL_UI
    pid: int | None = PID_NO_LAYER3
    command: bool = True  # AX.25 v2: command frames set the C bit of the destination

    @property
    def kind(self) -> str:
        return frame_kind(self.control)

    @property
    def is_ui(self) -> bool:
        return self.kind == "UI"

    @property
    def poll_final(self) -> bool:
        return bool(self.control & PF)

    @property
    def ns(self) -> int:
        return (self.control >> 1) & 0x07

    @property
    def nr(self) -> int:
        return (self.control >> 5) & 0x07

    def encode(self) -> bytes:
        if len(self.path) > MAX_DIGIPEATERS:
            raise ValueError("Too many digipeaters")
        out = bytearray()
        out += self.destination.encode(last=False, command=self.command)
        out += self.source.encode(last=not self.path, command=not self.command)
        for i, digi in enumerate(self.path):
            out += digi.encode(last=i == len(self.path) - 1)
        out.append(self.control)
        if self.kind in ("I", "UI"):
            out.append(PID_NO_LAYER3 if self.pid is None else self.pid)
            out += self.info
        return bytes(out)

    @classmethod
    def decode(cls, data: bytes) -> Frame:
        if len(data) < 15:
            raise ValueError("Frame too short")
        addresses: list[Address] = []
        raw_ssid: list[int] = []
        pos = 0
        while True:
            if pos + 7 > len(data):
                raise ValueError("Address field runs past the frame")
            addr, last = Address.decode(data[pos:pos + 7])
            addresses.append(addr)
            raw_ssid.append(data[pos + 6])
            pos += 7
            if last:
                break
            if len(addresses) > 2 + MAX_DIGIPEATERS:
                raise ValueError("Too many addresses")
        if len(addresses) < 2 or pos >= len(data):
            raise ValueError("Missing source address or control field")
        control = data[pos]
        pos += 1
        kind = frame_kind(control)
        pid = None
        info = b""
        if kind in ("I", "UI"):
            if pos >= len(data):
                raise ValueError("Missing PID")
            pid = data[pos]
            info = data[pos + 1:]
        destination = Address(addresses[0].call, addresses[0].ssid)
        source = Address(addresses[1].call, addresses[1].ssid)
        command = bool(raw_ssid[0] & 0x80) and not raw_ssid[1] & 0x80
        return cls(destination, source, addresses[2:], info, control, pid, command)

    def tnc2(self) -> str:
        """The frame in TNC2 text form, as aprslib parses it (UI frames)."""
        path = "".join(f",{d}{'*' if d.repeated else ''}" for d in self.path)
        return f"{self.source}>{self.destination}{path}:" + self.info.decode("latin-1")

    def monitor(self) -> str:
        """A one-line monitor view like classic TNCs: 'OK1ABC>OK0BBS,WIDE1-1* <I C S2 R1>: text'."""
        path = "".join(f",{d}{'*' if d.repeated else ''}" for d in self.path)
        kind = self.kind
        cr = "C" if self.command else "R"
        detail = kind
        if kind == "I":
            detail = f"I {cr} S{self.ns} R{self.nr}"
        elif kind in ("RR", "RNR", "REJ"):
            detail = f"{kind} {cr} R{self.nr}"
        elif kind != "UI":
            detail = f"{kind} {cr}"
        if self.poll_final and kind != "UI":
            detail += " P" if self.command else " F"
        text = self.info.decode("utf-8", "replace").replace("\r", "\n") if self.info else ""
        return f"{self.source}>{self.destination}{path} <{detail}>" + (f": {text}" if text else "")
