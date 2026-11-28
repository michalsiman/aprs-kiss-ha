"""Station telemetry (APRS 1.01 ch. 13): what the digipeater and iGate did, sent every few minutes.

Five numbers per interval – packets heard by radio, packets digipeated, packets gated RF→internet and
internet→RF, and the farthest station heard directly (not through a digipeater), in km – and eight bits:
digipeater on, iGate on, APRS-IS connected, transmitting on. aprs.fi draws them as graphs
(aprs.fi/telemetry/a/CALL).

  T#042,57,12,40,0,38,11110000
  :OK1SIM-10:PARM.RxPkts,Digi,RF>IS,IS>RF,MaxKm,Digi,IGate,Inet,TX
  :OK1SIM-10:UNIT.pkt,pkt,pkt,pkt,km,on,on,on,on
  :OK1SIM-10:EQNS.0,1,0,0,1,0,0,1,0,0,1,0,0,1,0
  :OK1SIM-10:BITS.11111111,APRS & Packet station

The four definition messages tell receivers what the numbers mean; they go with the first report and then
with every DEFINITIONS_EVERY-th one. Counts are plain integers: aprs.fi and the newer clients take numbers
above the original 0–255.
"""

from __future__ import annotations

from typing import Any

MINUTES = (10, 20, 30, 60)
DEFAULT_MINUTES = 20
DEFINITIONS_EVERY = 6  # with a report every 20 minutes, the definitions every 2 hours
MAX_KM = 1500  # farther than this "heard directly" is a wrong position, not a record
TITLE = "APRS & Packet station"

# names and units within the lengths APRS 1.01 allows per channel (analog 7,7,6,6,5; bits 6,5,4,4,…)
PARM = ("RxPkts", "Digi", "RF>IS", "IS>RF", "MaxKm", "Digi", "IGate", "Inet", "TX")
UNIT = ("pkt", "pkt", "pkt", "pkt", "km", "on", "on", "on", "on")


def addressee(call: str) -> str:
    return call.upper().ljust(9)[:9]


def definitions(call: str) -> list[str]:
    """The PARM, UNIT, EQNS and BITS messages (information fields) for our callsign."""
    to = addressee(call)
    return [f":{to}:PARM.{','.join(PARM)}",
            f":{to}:UNIT.{','.join(UNIT)}",
            f":{to}:EQNS.{','.join(['0,1,0'] * 5)}",
            f":{to}:BITS.11111111,{TITLE}"]


def report(seq: int, values: list[float], bits: list[bool]) -> str:
    """T#sss,a1,a2,a3,a4,a5,bbbbbbbb"""
    nums = ",".join(str(max(0, int(round(v)))) for v in values[:5])
    flags = "".join("1" if b else "0" for b in (list(bits) + [False] * 8)[:8])
    return f"T#{seq % 1000:03d},{nums},{flags}"


class Counter:
    """The interval's numbers: totals the engine keeps anyway are read as differences from the last report;
    the farthest direct station is kept here."""

    def __init__(self) -> None:
        self.seq = 0
        self.sent = 0  # reports sent since the start (definitions with the first one)
        self.base: dict[str, int] | None = None
        self.max_km = 0.0
        self.last: dict[str, Any] = {}  # the last report sent, for the settings screen

    def heard_direct(self, km: float | None) -> None:
        if km is not None and km > self.max_km:
            self.max_km = km

    def start(self, totals: dict[str, int]) -> None:
        """The interval starts now (the first one when the engine starts)."""
        self.base = dict(totals)
        self.max_km = 0.0

    def values(self, totals: dict[str, int]) -> list[float]:
        base = self.base or {}
        delta = [max(0, totals.get(k, 0) - base.get(k, 0)) for k in ("received", "digipeated", "rf_to_is", "is_to_rf")]
        return [*delta, round(self.max_km)]

    def due_definitions(self) -> bool:
        return self.sent % DEFINITIONS_EVERY == 0
