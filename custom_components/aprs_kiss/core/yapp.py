"""YAPP: sending a file over a connected AX.25 link (the classic packet radio file transfer).

YAPP (Jeff Jacobsen WA7MBL) is understood by BPQ/LinBPQ, WinPack, Paxon and others. The link itself
(AX.25 connected mode, session.py) already acknowledges and repeats frames, so YAPP only has to say
what is coming and when it is done:

    sender                      receiver
    SI  ENQ 01            ->
                          <-    RR  ACK 01            ready
    HD  SOH len name\\0size\\0 ->
                          <-    RF  ACK 02            send it      (or NR  NAK len reason: refused,
                                                                    or RE  NAK len R\\0offset\\0: resume)
    DT  STX len data …    ->                          (len 0 = 256 bytes)
    EF  ETX 01            ->
                          <-    AF  ACK 03
    ET  EOT 01            ->
                          <-    AT  ACK 04
    either side: CN  CAN len reason  ->  CA  ACK 05

Resuming (from YAPP-C): a receiver that already has the first part of the file answers the header with
RE and the number of bytes it has; the sender goes on from there. No checksums: the link has them.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

ENQ, SOH, STX, ETX, EOT, ACK, NAK, CAN = 0x05, 0x01, 0x02, 0x03, 0x04, 0x06, 0x15, 0x18
BLOCK = 250  # data bytes per DT packet (YAPP allows up to 256)

SI = bytes([ENQ, 0x01])
RR = bytes([ACK, 0x01])
RF = bytes([ACK, 0x02])
AF = bytes([ACK, 0x03])
AT = bytes([ACK, 0x04])
CA = bytes([ACK, 0x05])
EF = bytes([ETX, 0x01])
ET = bytes([EOT, 0x01])


def _with_len(kind: int, body: bytes) -> bytes:
    return bytes([kind, len(body)]) + body


def header(name: str, size: int) -> bytes:
    return _with_len(SOH, name.encode("utf-8")[:200] + b"\0" + str(size).encode() + b"\0")


def data_packets(data: bytes) -> list[bytes]:
    return [bytes([STX, len(data[i:i + BLOCK]) % 256]) + data[i:i + BLOCK] for i in range(0, len(data), BLOCK)]


def cancel(reason: str) -> bytes:
    return _with_len(CAN, reason.encode("utf-8")[:200])


def refuse(reason: str) -> bytes:
    return _with_len(NAK, reason.encode("utf-8")[:200])


def resume(offset: int) -> bytes:
    return _with_len(NAK, b"R\0" + str(offset).encode() + b"\0")


class Parser:
    """Bytes as they come over the link (packets may be split or joined) -> whole YAPP packets."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """[(kind, body)]: for the two-byte packets body is the second byte."""
        self.buf += data
        out = []
        while len(self.buf) >= 2:
            kind, n = self.buf[0], self.buf[1]
            if kind in (ENQ, ACK, ETX, EOT):
                out.append((kind, bytes([n])))
                del self.buf[:2]
                continue
            if kind in (SOH, NAK, CAN, STX):
                length = n or (256 if kind == STX else 0)
                if len(self.buf) < 2 + length:
                    break
                out.append((kind, bytes(self.buf[2:2 + length])))
                del self.buf[:2 + length]
                continue
            del self.buf[:1]  # not YAPP: skip a byte and look again
        return out


def safe_name(name: str) -> str:
    """Only the file's own name, nothing that leads out of the folder."""
    name = os.path.basename(name.replace("\\", "/")).strip().lstrip(".")
    return "".join(c for c in name if c.isprintable() and c not in '<>:"|?*') or "file"


# ─── the two ends ────────────────────────────────────────────────────────────

Send = Callable[[bytes], None]


class Sender:
    """Sends one file. send(bytes) writes to the link; on_state(state, detail) tells what happens:
    "waiting" (for the other side), "sending", "done", "refused", "cancelled"."""

    def __init__(self, name: str, data: bytes, send: Send, on_state: Callable[[str, str], None]) -> None:
        self.name, self.data, self.send, self.on_state = name, data, send, on_state
        self.parser = Parser()
        self.offset = 0  # where the data starts (a resumed transfer starts further on)
        self.state = "new"

    @property
    def size(self) -> int:
        return len(self.data)

    def start(self) -> None:
        """The link is up: say a file is coming."""
        self.state = "waiting"  # the state first: the answer may come back before send() returns
        self.on_state("waiting", "")
        self.send(SI)

    def cancel(self, reason: str = "cancelled") -> None:
        if self.state not in ("done", "refused", "cancelled"):
            self.state = "cancelled"
            self.on_state("cancelled", reason)
            self.send(cancel(reason))

    def feed(self, data: bytes) -> None:
        for kind, body in self.parser.feed(data):
            self._packet(kind, body)

    def _packet(self, kind: int, body: bytes) -> None:
        code = body[:1]
        if kind == ACK and code == b"\x01" and self.state == "waiting":  # RR: here is the header
            self.send(header(self.name, self.size))
        elif kind == ACK and code == b"\x02" and self.state == "waiting":  # RF: send it
            self._send_data(0)
        elif kind == NAK and body.startswith(b"R\0") and self.state == "waiting":  # resume
            try:
                offset = int(body[2:].split(b"\0")[0] or b"0")
            except ValueError:
                offset = 0
            self._send_data(max(0, min(offset, self.size)))
        elif kind == NAK and self.state == "waiting":  # NR: refused
            self.state = "refused"
            self.on_state("refused", body.decode("utf-8", "replace"))
        elif kind == ACK and code == b"\x03" and self.state == "sending":  # AF: got it all
            self.state = "ending"
            self.send(ET)
        elif kind == ACK and code == b"\x04" and self.state == "ending":  # AT
            self.state = "done"
            self.on_state("done", "")
        elif kind == CAN:
            self.state = "cancelled"
            self.on_state("cancelled", body.decode("utf-8", "replace"))
            self.send(CA)

    def _send_data(self, offset: int) -> None:
        self.offset = offset
        self.state = "sending"
        self.on_state("sending", str(offset))
        for packet in data_packets(self.data[offset:]):
            self.send(packet)
        self.send(EF)


class Receiver:
    """Receives one file into `folder`. ask(name, size, answer) is called when the header comes:
    answer(True) takes it, answer(False) refuses. on_state: "offered", "receiving", "done", "refused",
    "cancelled"; on_progress(bytes so far, size)."""

    def __init__(self, folder: Path, send: Send, ask: Callable[[str, int, Callable[[bool], None]], None],
                 on_state: Callable[[str, str], None], on_progress: Callable[[int, int], None]) -> None:
        self.folder, self.send, self.ask, self.on_state, self.on_progress = folder, send, ask, on_state, on_progress
        self.parser = Parser()
        self.state = "new"
        self.name, self.size, self.got = "", 0, 0
        self._file = None
        self.path: Path | None = None

    @property
    def part(self) -> Path:
        return self.folder / (self.name + ".part")

    def feed(self, data: bytes) -> None:
        for kind, body in self.parser.feed(data):
            self._packet(kind, body)

    def cancel(self, reason: str = "cancelled") -> None:
        if self.state not in ("done", "refused", "cancelled"):
            self._close()
            self.state = "cancelled"
            self.on_state("cancelled", reason)
            self.send(cancel(reason))

    def _packet(self, kind: int, body: bytes) -> None:
        code = body[:1]
        if kind == ENQ and code == b"\x01":  # SI
            self.state = "ready"  # the state first: the answer may come back before send() returns
            self.send(RR)
        elif kind == SOH and self.state == "ready":
            fields = body.split(b"\0")
            self.name = safe_name(fields[0].decode("utf-8", "replace"))
            try:
                self.size = int(fields[1] or b"0") if len(fields) > 1 else 0
            except ValueError:
                self.size = 0
            self.state = "offered"
            self.on_state("offered", self.name)
            self.ask(self.name, self.size, self._answer)
        elif kind == STX and self.state == "receiving":
            self._file.write(body)
            self.got += len(body)
            self.on_progress(self.got, self.size)
        elif kind == ETX and self.state == "receiving":  # EF
            self._close()
            target = self.folder / self.name
            n = 2
            while target.exists():
                stem, dot, ext = self.name.rpartition(".")
                target = self.folder / (f"{stem}-{n}.{ext}" if dot else f"{self.name}-{n}")
                n += 1
            self.part.rename(target)
            self.path = target
            self.state = "ending"
            self.send(AF)
        elif kind == EOT and self.state == "ending":  # ET
            self.state = "done"
            self.on_state("done", str(self.path))
            self.send(AT)
        elif kind == CAN:
            self._close()
            self.state = "cancelled"
            self.on_state("cancelled", body.decode("utf-8", "replace"))
            self.send(CA)

    def _answer(self, yes: bool) -> None:
        if self.state != "offered":
            return
        if not yes:
            self.state = "refused"
            self.on_state("refused", "")
            self.send(refuse("refused"))
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        have = self.part.stat().st_size if self.part.exists() else 0
        resuming = 0 < have < self.size  # the first part is here from an interrupted transfer
        self._file = open(self.part, "ab" if resuming else "wb")  # noqa: SIM115 - kept open for the transfer
        self.got = have if resuming else 0
        self.state = "receiving"
        self.on_state("receiving", str(self.got))
        self.on_progress(self.got, self.size)
        self.send(resume(have) if resuming else RF)

    def _close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
