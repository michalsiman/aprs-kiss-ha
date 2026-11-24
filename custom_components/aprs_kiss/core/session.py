"""AX.25 v2.0 connected mode (modulo 8) for a packet radio terminal.

A KISS TNC only sends and receives frames, so the link layer runs here:
SABM/UA to connect, I frames numbered N(S)/N(R) with a window of K frames,
RR/REJ acknowledgements, T1 retransmission (go-back-N) up to N2 tries, a T3
idle poll, and DISC/UA to disconnect. Incoming connections can be accepted.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

from .ax25 import (
    PF, PID_NO_LAYER3, S_REJ, S_RNR, S_RR, U_DISC, U_DM, U_SABM, U_UA, Address, Frame,
)

_LOGGER = logging.getLogger(__name__)

DISCONNECTED = "disconnected"
CONNECTING = "connecting"
CONNECTED = "connected"
DISCONNECTING = "disconnecting"

PACLEN = 128        # bytes of text per I frame
WINDOW = 4          # K: unacknowledged I frames at most
T1 = 12.0           # seconds to wait for an acknowledgement (1200 Bd, a digipeater or two)
T2 = 1.0            # delay before acknowledging, so several frames get one RR
T3 = 300.0          # idle link check
N2 = 8              # tries before the link is given up
CONNECT_ATTEMPTS = N2 + 1  # the first SABM and its retries


class Session:
    """One connection between our callsign and a remote station."""

    def __init__(
        self,
        me: Address,
        remote: Address,
        path: list[Address],
        send_frame: Callable[[bytes], Awaitable[None]],
        on_text: Callable[[str], None],
        on_state: Callable[[str, str], None],
    ) -> None:
        self.me = me
        self.remote = remote
        self.path = path
        self._send_frame = send_frame
        self._on_text = on_text
        self._on_state = on_state
        self.state = DISCONNECTED
        self.attempts = 0  # connect requests (SABM) sent for the current connection
        self.connect_started = self.last_attempt = 0.0
        self.vs = 0          # next N(S) to send
        self.vr = 0          # next N(S) expected
        self.va = 0          # oldest unacknowledged N(S)
        self._unacked: dict[int, bytes] = {}
        self._queue: list[bytes] = []
        self._retries = 0
        self._t1: asyncio.TimerHandle | None = None
        self._t2: asyncio.TimerHandle | None = None
        self._t3: asyncio.TimerHandle | None = None
        self._reject_sent = False
        self._peer_busy = False
        self._rx_partial = ""
        self.connected_at: float | None = None
        # binary use (a file transfer): when set, received data goes here as bytes instead of text
        self.on_data: Callable[[bytes], None] | None = None
        self.acked_bytes = 0  # data the other side has acknowledged (progress of a transfer)
        self._loop = asyncio.get_event_loop()

    # ─── frames ───────────────────────────────────────────────────────────

    def _frame(self, control: int, command: bool, info: bytes = b"") -> Frame:
        pid = PID_NO_LAYER3 if control & 0x01 == 0 else None
        return Frame(self.remote, self.me, list(self.path), info, control, pid, command)

    def _send(self, control: int, command: bool, info: bytes = b"") -> None:
        frame = self._frame(control, command, info)
        task = asyncio.ensure_future(self._send_frame(frame.encode()))
        task.add_done_callback(lambda t: t.exception() and _LOGGER.debug("Frame not sent: %s", t.exception()))

    def _set_state(self, state: str, reason: str = "") -> None:
        if state == self.state:
            return
        self.state = state
        self.connected_at = time.time() if state == CONNECTED else self.connected_at
        if state == DISCONNECTED:
            self._stop_timers()
            self._unacked.clear()
            self._queue.clear()
        self._on_state(state, reason)

    # ─── timers ───────────────────────────────────────────────────────────

    def _start_t1(self) -> None:
        if self._t1:
            self._t1.cancel()
        self._t1 = self._loop.call_later(T1, self._t1_expired)

    def _stop_t1(self) -> None:
        if self._t1:
            self._t1.cancel()
            self._t1 = None

    def _restart_t3(self) -> None:
        if self._t3:
            self._t3.cancel()
        if self.state == CONNECTED:
            self._t3 = self._loop.call_later(T3, self._t3_expired)

    def _stop_timers(self) -> None:
        for t in (self._t1, self._t2, self._t3):
            if t:
                t.cancel()
        self._t1 = self._t2 = self._t3 = None

    def _t1_expired(self) -> None:
        self._t1 = None
        self._retries += 1
        if self._retries > N2:
            self._send(U_DM | PF, command=False)
            tries = f" after {self.attempts} attempts" if self.state == CONNECTING else ""
            self._set_state(DISCONNECTED, f"link failure: no answer{tries}")
            return
        if self.state == CONNECTING:
            self._send(U_SABM | PF, command=True)
            self.attempts += 1
            self.last_attempt = time.time()
            # Same state, so tell the owner directly: the terminal shows each try with its time.
            self._on_state(self.state, f"connect attempt {self.attempts}/{CONNECT_ATTEMPTS} "
                                       f"at {time.strftime('%H:%M:%S', time.localtime(self.last_attempt))}")
        elif self.state == DISCONNECTING:
            self._send(U_DISC | PF, command=True)
        elif self.state == CONNECTED:
            # Ask where the other side is (RR with P); go-back-N on its answer.
            self._send(S_RR | PF | (self.vr << 5), command=True)
        self._start_t1()

    def _t3_expired(self) -> None:
        self._t3 = None
        if self.state == CONNECTED and not self._t1:
            self._retries = 0
            self._send(S_RR | PF | (self.vr << 5), command=True)
            self._start_t1()

    # ─── user actions ─────────────────────────────────────────────────────

    def connect(self) -> None:
        self.vs = self.vr = self.va = 0
        self._retries = 0
        self.attempts = 1
        self.connect_started = self.last_attempt = time.time()
        self._set_state(CONNECTING, f"connecting to {self.remote}")
        self._send(U_SABM | PF, command=True)
        self._start_t1()

    def disconnect(self) -> None:
        if self.state == DISCONNECTED:
            return
        if self.state == CONNECTING:
            self._set_state(DISCONNECTED, "cancelled")
            return
        self._retries = 0
        self._queue.clear()
        self._set_state(DISCONNECTING, "disconnecting")
        self._send(U_DISC | PF, command=True)
        self._start_t1()

    def send_text(self, text: str) -> None:
        """Queue text (a line ends with CR, as packet BBSes expect)."""
        if self.state != CONNECTED:
            raise ConnectionError("Not connected")
        data = text.replace("\r\n", "\r").replace("\n", "\r").encode("utf-8")
        for i in range(0, len(data), PACLEN):
            self._queue.append(data[i:i + PACLEN])
        self._pump()

    def send_bytes(self, data: bytes) -> None:
        """Queue data as it is (a file transfer)."""
        if self.state != CONNECTED:
            raise ConnectionError("Not connected")
        for i in range(0, len(data), PACLEN):
            self._queue.append(data[i:i + PACLEN])
        self._pump()

    def _pump(self) -> None:
        while self._queue and not self._peer_busy and (self.vs - self.va) % 8 < WINDOW:
            info = self._queue.pop(0)
            self._unacked[self.vs] = info
            self._send((self.vr << 5) | (self.vs << 1), command=True, info=info)
            self.vs = (self.vs + 1) % 8
            self._cancel_t2()  # the I frame carries our N(R)
            if not self._t1:
                self._start_t1()

    def _cancel_t2(self) -> None:
        if self._t2:
            self._t2.cancel()
            self._t2 = None

    # ─── incoming frames ──────────────────────────────────────────────────

    def handle(self, frame: Frame) -> None:
        kind = frame.kind
        if kind == "SABM":
            self.vs = self.vr = self.va = 0
            self._unacked.clear()
            self._retries = 0
            self._stop_t1()
            self._send(U_UA | (PF if frame.poll_final else 0), command=False)
            self._set_state(CONNECTED, f"connected to {self.remote}")
            self._restart_t3()
            return
        if kind == "DISC":
            self._send(U_UA | (PF if frame.poll_final else 0), command=False)
            self._set_state(DISCONNECTED, f"{self.remote} disconnected")
            return
        if kind == "UA":
            if self.state == CONNECTING:
                self._stop_t1()
                self._retries = 0
                self._set_state(CONNECTED, f"connected to {self.remote}")
                self._restart_t3()
            elif self.state == DISCONNECTING:
                self._set_state(DISCONNECTED, "disconnected")
            return
        if kind == "DM":
            if self.state == CONNECTING:
                self._set_state(DISCONNECTED, f"{self.remote} is busy or refuses connections")
            elif self.state != DISCONNECTED:
                self._set_state(DISCONNECTED, f"{self.remote} disconnected")
            return
        if self.state != CONNECTED:
            if frame.command and kind in ("I", "RR", "RNR", "REJ"):
                self._send(U_DM | (PF if frame.poll_final else 0), command=False)
            return
        self._restart_t3()
        if kind in ("I", "RR", "RNR", "REJ"):
            self._peer_busy = kind == "RNR"
            self._acknowledge(frame.nr, retransmit=kind == "REJ" or (not frame.command and frame.poll_final))
            if frame.command and frame.poll_final and kind != "I":
                self._send(S_RR | PF | (self.vr << 5), command=False)
        if kind == "I":
            self._receive_i(frame)
        self._pump()

    def _acknowledge(self, nr: int, retransmit: bool) -> None:
        # Frames va … nr-1 are acknowledged.
        while self.va != nr and self.va in self._unacked:
            self.acked_bytes += len(self._unacked.pop(self.va))
            self.va = (self.va + 1) % 8
            self._retries = 0
        if not self._unacked:
            self._stop_t1()
        if retransmit and self._unacked:
            # Go back N: send again everything from N(R).
            n = nr
            while n in self._unacked:
                self._send((self.vr << 5) | (n << 1), command=True, info=self._unacked[n])
                n = (n + 1) % 8
            self._start_t1()
        elif self._unacked and not self._t1:
            self._start_t1()

    def _receive_i(self, frame: Frame) -> None:
        if frame.ns != self.vr:
            if not self._reject_sent:
                self._reject_sent = True
                self._send(S_REJ | (self.vr << 5) | (PF if frame.poll_final else 0), command=False)
            return
        self._reject_sent = False
        self.vr = (self.vr + 1) % 8
        self._deliver(frame.info)
        if frame.poll_final:
            self._send(S_RR | PF | (self.vr << 5), command=False)
        elif not self._t2:
            self._t2 = self._loop.call_later(T2, self._send_rr)

    def _send_rr(self) -> None:
        self._t2 = None
        if self.state == CONNECTED:
            self._send(S_RR | (self.vr << 5), command=False)

    def _deliver(self, data: bytes) -> None:
        if self.on_data:
            self.on_data(data)
            return
        text = data.decode("utf-8", "replace").replace("\r\n", "\n").replace("\r", "\n")
        if text:
            self._on_text(text)

    def close(self) -> None:
        self._stop_timers()


__all__ = ["CONNECTED", "CONNECTING", "DISCONNECTED", "DISCONNECTING", "Session", "S_RNR"]
