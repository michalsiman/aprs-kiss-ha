"""Self-spotting an outdoor activation (SOTA, POTA, WWFF, SIOTA) with an APRS message to a gateway.

Sent by radio over APRS: any iGate in range passes the message to the gateway on APRS-IS (straight over
the internet too, when the station has it and it is chosen). Two gateways:

- APRS2SOTA (sotaspots.co.uk, G0LGS) - SOTA only, posts to SOTAwatch. Message to "APRS2SOTA" (or "SOTA"):
  "<summit> <freq> <mode> [callsign] [comment]", e.g. "OK/PL-001 145.500 FM OK1SIM CQ SOTA". The callsign
  must be registered with the gateway's operator first (an email). Modes AM CW DATA DV FM SSB OTHER.
  Answers "Spotted: …", "Dupe: …", "Error: …" or "Sorry: …"; 5 requests per 5 minutes.
- APSPOT (apspot.radio, VK) - SOTA, POTA, WWFF and SIOTA; posts to SOTAwatch, pota.app and ParksnPeaks.
  Message to "APSPOT": "! <program> <reference> <freq in MHz> <mode> [comment]", e.g.
  "! POTA CZ-0001 7.144 SSB CQ"; the callsign is the sender's. Modes SSB CW FM AM DATA (FT8 too for POTA,
  though it has been refused: sent as DATA here). An account on the target site is needed;
  "aptest" in the comment gets a simulated answer without posting.
- Camilla (gma.rocks, DL0QW-12) - GMA summits, WCA castles, WWFF, IOTA islands, lighthouses and SOTA (a SOTA
  summit is spotted on SOTAwatch too). Message to "DL0QW-12": "<callsign> <reference> <freq> <mode> [comment]",
  e.g. "OK1SIM OKFF-0001 7.0345 CW qrv"; kHz or MHz. Registered GMA users only (free, gma.rocks); it always
  answers a spot it posted.

An APRS message carries up to 67 characters: the comment is shortened to fit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .aprs import MAX_MESSAGE_TEXT

PROGRAMS = ("SOTA", "POTA", "WWFF", "SIOTA", "GMA", "WCA", "IOTA", "LH")
CAMILLA = "DL0QW-12"
GATEWAYS = ("APRS2SOTA", "APSPOT", CAMILLA)
GATEWAY_NAMES = {"APRS2SOTA": "APRS2SOTA", "APSPOT": "APSPOT", CAMILLA: "Camilla (GMA)"}
# the gateways for each program, the default first
PROGRAM_GATEWAYS = {
    "SOTA": ("APRS2SOTA", CAMILLA, "APSPOT"),
    "POTA": ("APSPOT",),
    "WWFF": (CAMILLA, "APSPOT"),
    "SIOTA": ("APSPOT",),
    "GMA": (CAMILLA,), "WCA": (CAMILLA,), "IOTA": (CAMILLA,), "LH": (CAMILLA,),
}
MODES = {
    "APRS2SOTA": ("SSB", "CW", "FM", "AM", "DATA", "DV", "OTHER"),
    "APSPOT": ("SSB", "CW", "FM", "AM", "DATA"),
    CAMILLA: ("SSB", "CW", "FM", "AM", "DATA", "DV"),
}
# what each program's references look like, and an example (shown when one looks wrong)
REFERENCE = {
    "SOTA": (re.compile(r"^[A-Z0-9]{1,4}/[A-Z0-9]{2}-\d{3}$"), "OK/PL-001"),
    "POTA": (re.compile(r"^[A-Z0-9]{1,4}-\d{4,5}$"), "CZ-0001"),
    "WWFF": (re.compile(r"^[A-Z0-9]{1,4}FF-\d{4}$"), "OKFF-0001"),
    "SIOTA": (re.compile(r"^[A-Z0-9/-]{3,16}$"), "VK-ABC3"),
    "GMA": (re.compile(r"^[A-Z0-9]{1,4}/[A-Z0-9]{2,3}-\d{3,4}$|^[A-Z0-9]{1,4}FF-\d{4}$"), "DA/TH-001"),
    "WCA": (re.compile(r"^[A-Z0-9]{1,4}-\d{5}$"), "OK-00001"),
    "IOTA": (re.compile(r"^(AF|AN|AS|EU|NA|OC|SA)-\d{3}$"), "EU-001"),
    "LH": (re.compile(r"^[A-Z0-9/-]{4,12}$"), "FRA-001"),
}
# the address our own station shows: the SOTA gateway wants no SSID ("OK1SIM", "OK1SIM/P")
_SSID = re.compile(r"-\d{1,2}$")


class SpotError(ValueError):
    """A spot that cannot go: `code` is the message key, `example` fills it."""

    def __init__(self, code: str, example: str = "") -> None:
        super().__init__(code)
        self.code, self.example = code, example


@dataclass
class Spot:
    program: str
    reference: str
    frequency: str  # as typed: MHz ("7.032"), or kHz ("7032") which is turned into MHz
    mode: str
    comment: str = ""
    gateway: str = ""  # "" = the default for the program
    test: bool = False


def gateways_for(program: str) -> tuple[str, ...]:
    return PROGRAM_GATEWAYS.get(program, ("APSPOT",))


def default_gateway(program: str) -> str:
    return gateways_for(program)[0]


def normalize_reference(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").upper())


def mhz(text: str) -> str:
    """The frequency in MHz as the gateways want it: "7.032", "145.5"; kHz (> 1000) is converted."""
    raw = (text or "").strip().lower().replace(",", ".")
    raw = re.sub(r"\s*(mhz|mh|m)$", "", raw)
    khz = raw.endswith("khz") or raw.endswith("k")
    raw = re.sub(r"\s*(khz|k)$", "", raw)
    try:
        value = float(raw)
    except ValueError:
        raise SpotError("spot_bad_freq") from None
    if khz or value >= 1000:
        value /= 1000
    if not 0.1 <= value <= 300000:
        raise SpotError("spot_bad_freq")
    return f"{value:.4f}".rstrip("0").rstrip(".")


def base_call(call: str) -> str:
    return _SSID.sub("", (call or "").strip().upper())


def build(spot: Spot, mycall: str) -> tuple[str, str]:
    """(addressee, message text) for the spot; SpotError when something does not look right."""
    program = spot.program.upper()
    if program not in PROGRAMS:
        raise SpotError("spot_bad_program")
    gateway = spot.gateway if spot.gateway in gateways_for(program) else default_gateway(program)
    ref = normalize_reference(spot.reference)
    pattern, example = REFERENCE[program]
    if not pattern.match(ref):
        raise SpotError("spot_bad_ref", example)
    freq = mhz(spot.frequency)
    mode = (spot.mode or "").strip().upper()
    if mode in ("FT8", "FT4", "PSK", "RTTY", "JS8"):
        mode = "DATA"
    if mode not in MODES[gateway]:
        mode = "OTHER" if gateway == "APRS2SOTA" else "DATA"
    comment = " ".join((spot.comment or "").split())
    if spot.test:
        # APSPOT answers as if posted ("aptest"); APRS2SOTA marks the spot as a test on SOTAwatch
        comment = ("aptest " if gateway == "APSPOT" else "TEST ") + comment  # Camilla: posted, marked TEST
    if gateway == "APRS2SOTA":
        head = f"{ref} {freq} {mode} {base_call(mycall)}"
    elif gateway == CAMILLA:
        head = f"{base_call(mycall)} {ref} {freq} {mode}"
    else:
        head = f"! {program} {ref} {freq} {mode}"
    room = MAX_MESSAGE_TEXT - len(head) - 1
    comment = comment.strip()[:max(0, room)].rstrip()
    return gateway, f"{head} {comment}".rstrip()
