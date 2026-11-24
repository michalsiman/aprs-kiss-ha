"""Station profiles: one callsign, up to three SSIDs, each with its own symbol (OK1ABC-9 a car,
OK1ABC-7 a handheld, OK1ABC a house). One is active: everything goes out under it (position,
messages, terminal, chat, …). The active one is also in `callsign` and `symbol`, so the rest of the
app does not need to know about profiles.

Stored in Config.profiles as JSON: [{"ssid": 9, "symbol": "/>"}, …], the active one in Config.profile.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config

MAX = 3


def split_call(callsign: str) -> tuple[str, int]:
    base, _, ssid = (callsign or "").strip().upper().partition("-")
    try:
        return base, int(ssid) if ssid else 0
    except ValueError:
        return base, 0


def full_call(base: str, ssid: int) -> str:
    return f"{base}-{ssid}" if base and ssid else base


def load(conf: Config) -> list[dict[str, Any]]:
    """The profiles; without any saved, the one the settings have (callsign's SSID and symbol)."""
    out: list[dict[str, Any]] = []
    try:
        raw = json.loads(conf.profiles) if conf.profiles else []
    except ValueError:
        raw = []
    seen = set()
    for p in raw if isinstance(raw, list) else []:
        try:
            ssid, symbol = int(p.get("ssid", 0)), str(p.get("symbol") or "/-")
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= ssid <= 15 and ssid not in seen and len(symbol) == 2:
            seen.add(ssid)
            out.append({"ssid": ssid, "symbol": symbol})
    if not out:
        out = [{"ssid": split_call(conf.callsign)[1], "symbol": conf.symbol or "/-"}]
    return out[:MAX]


def dump(items: list[dict[str, Any]]) -> str:
    return json.dumps([{"ssid": int(p["ssid"]), "symbol": p["symbol"]} for p in items[:MAX]])


def normalize(conf: Config) -> None:
    """callsign and symbol are the active profile's (called by Config.validate)."""
    items = load(conf)
    if not 0 <= conf.profile < len(items):
        conf.profile = 0
    if len(items) == 1 and not conf.profiles:
        return  # nobody made profiles: the settings as they are
    base, _ssid = split_call(conf.callsign)
    active = items[conf.profile]
    conf.callsign = full_call(base, active["ssid"])
    conf.symbol = active["symbol"]
    conf.profiles = dump(items)


def switch(conf: Config, index: int) -> Config:
    """A copy of the settings with another profile active."""
    items = load(conf)
    if not 0 <= index < len(items):
        raise ValueError(index)
    new = replace(conf, profiles=dump(items), profile=index)
    normalize(new)
    return new
