"""Winlink e-mail over APRS: APRSLink, the gateway WLNK-1.

Everything is an APRS message to WLNK-1, its answers come back as messages:

- login: any text starts it; WLNK-1 answers with three digits, positions of characters in the Winlink
  password (1 = the first). The answer is six characters: those three characters, in that order, and three
  more of our own (Winlink's example: password ABC123, challenge 425 → 1B2AZ5). The password itself never goes
  on air. A login holds about two hours.
- L: the list of waiting messages (5 at most, numbered); R# read, Y# reply, F# addr forward, K# delete.
- SP address subject: a new e-mail; every following message to WLNK-1 is a line of its body, /EX sends it
  (P plays back what is written so far). SMS address text: a one-line e-mail.
- A name=address: an alias, AL lists them; G# the nearest Winlink RMS gateways; I about APRSLink; ? help.

A Winlink account (callsign and password) must exist first: made with Winlink Express or Pat, not here.
"""

from __future__ import annotations

import random
import re
import string

GATEWAY = "WLNK-1"
LOGIN_SECONDS = 2 * 3600  # a login holds this long
CHALLENGE_SECONDS = 120  # the challenge is expected this soon after asking for it
LOGIN_TEXT = "LOGIN"  # any text starts the login; this one says what it is
BODY_LIMIT = 67  # one APRS message

_CHALLENGE = re.compile(r"(?<![0-9])([1-9][0-9]{2})(?![0-9])")


def is_gateway(call: str) -> bool:
    return (call or "").upper().strip() == GATEWAY


def find_challenge(text: str) -> str | None:
    """The three digits of a login challenge in WLNK-1's message ("Login [425]:" → "425"), or None."""
    found = _CHALLENGE.findall(text or "")
    return found[0] if len(found) == 1 else None


def answer(challenge: str, password: str, rnd: random.Random | None = None) -> str:
    """The six characters that answer a challenge: the password's characters at the three positions, in that
    order, then three random ones. ValueError when the password is too short for the challenge."""
    if not password:
        raise ValueError("no Winlink password")
    picked = []
    for digit in challenge:
        pos = int(digit)
        if pos < 1 or pos > len(password):
            raise ValueError("the Winlink password is shorter than the challenge asks")
        picked.append(password[pos - 1])
    rnd = rnd or random.SystemRandom()
    extra = "".join(rnd.choice(string.ascii_uppercase + string.digits) for _ in range(3))
    return "".join(picked) + extra


def body_lines(text: str, limit: int = BODY_LIMIT) -> list[str]:
    """A text for WLNK-1 as messages: each line of it one message, a long line cut between words. No
    "1/3" numbering (that would end up in the e-mail)."""
    out: list[str] = []
    for line in (text or "").splitlines():
        line = " ".join(line.split())
        while len(line) > limit:
            gap = line.rfind(" ", 0, limit + 1)
            cut = gap if gap > limit // 2 else limit
            out.append(line[:cut].strip())
            line = line[cut:].strip()
        if line:
            out.append(line)
    return out


class Session:
    """Where the login is: asked for (waiting for the challenge), answered (logged in for two hours)."""

    def __init__(self) -> None:
        self.asked_at: float | None = None
        self.logged_until: float = 0.0

    def ask(self, now: float) -> None:
        self.asked_at = now

    def waiting(self, now: float) -> bool:
        return self.asked_at is not None and now - self.asked_at <= CHALLENGE_SECONDS

    def challenge_in(self, text: str, now: float) -> str | None:
        """The challenge, when this message from WLNK-1 is the answer to our login request."""
        if not self.waiting(now):
            return None
        return find_challenge(text)

    def answered(self, now: float) -> None:
        self.asked_at = None
        self.logged_until = now + LOGIN_SECONDS

    def logged_in(self, now: float) -> bool:
        return now < self.logged_until

    def logout(self) -> None:
        self.asked_at = None
        self.logged_until = 0.0
