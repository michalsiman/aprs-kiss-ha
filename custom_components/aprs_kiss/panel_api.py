"""WebSocket commands for the panel's newer screens: BBS SERVER, TAK, #APRSThursday, the exclusive
modes (BBS or TAK instead of APRS) and the map's own data (our GPS track, the stations heard).

The radio side is the shared engine (core/); this only reads it and passes the panel's requests on.
"""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .core.bbs import BbsConfigError
from .core.bbs.storage import load_settings, prepare_folder, read_text, update_settings, write_text
from .core.services import SERVICES
from .core.spotting import (CAMILLA, GATEWAY_NAMES, MODES, PROGRAM_GATEWAYS, PROGRAMS, REFERENCE, Spot, SpotError,
                            build as build_spot)
from .core.station import TransmitRefused

# The safety sentences, as the panel shows them (case, accents and spaces do not matter).
SENTENCES = {
    "bbs": ("BBS SERVER must have another frequency than APRS", "BBS SERVER musí mít jinou frekvenci než APRS"),
    "tak": ("TAK must have another frequency than APRS", "TAK musí mít jinou frekvenci než APRS"),
}
BBS_LIMITS = {"max_sessions": 1, "idle_timeout_sec": 10, "max_tx_min": 0, "max_messages": 0}  # field: lowest value
HEARD_FOR_PANEL = 600  # the most recently heard stations the map gets


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text.lower()).strip(" .!")


def sentence_ok(mode: str, text: str) -> bool:
    return bool(_plain(text)) and _plain(text) in {_plain(s) for s in SENTENCES[mode]}


def register(hass: HomeAssistant, hub_of) -> None:
    """hub_of(hass, entry_id) -> the Hub (raises when there is none)."""

    def error(connection, msg_id, err: Exception) -> None:
        connection.send_error(msg_id, "not_sent", str(err))

    # ─── the panel's live data beyond the basic state ─────────────────────

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/extra", vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_extra(hass, connection, msg):
        hub = hub_of(hass, msg.get("entry_id"))
        now = time.time()
        connection.send_result(msg["id"], {
            "mode": hub.exclusive_mode,
            "status": hub.status(),
            "position": hub.my_position(),
            "symbol": hub.config.symbol,
            "tracked": [c.strip().upper() for c in (hub.config.tracked_callsigns or "").replace(";", ",").split(",")
                        if c.strip()],
            "beacon_is": hub.config.beacon_is,
            "my_track": hub.my_track.get("track", []),
            "heard": list(hub.station.heard.values())[-HEARD_FOR_PANEL:],
            "digipeated": hub.digipeated,
            "thursday": list(hub.thursday),
            "thursday_member_until": hub.thursday_member_until(now),
            "thursday_wait": hub.thursday_wait(now),
            "tak": {"callsign": hub.tak_callsign, "uid": hub.tak_uid, "stations": list(hub.tak_stations.values()),
                    "chat": list(hub.tak_chat)} if hub.tak_mode else None,
        })

    # ─── BBS SERVER or TAK instead of APRS ────────────────────────────────

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/set_mode",
                                      vol.Required("mode"): vol.In(["", "bbs", "tak"]),
                                      vol.Optional("sentence", default=""): str, vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_mode(hass, connection, msg):
        hub = hub_of(hass, msg.get("entry_id"))
        entry, mode = hub.entry, msg["mode"]
        options = {**entry.options}
        if mode:
            key = f"{mode}_sentence_ok"
            if not ({**entry.data, **options}.get(key) or sentence_ok(mode, msg["sentence"])):
                connection.send_error(msg["id"], "invalid", "sentence_required")
                return
            options[key] = True  # typed once: not asked again
        options["bbs_enabled"], options["tak_enabled"] = mode == "bbs", mode == "tak"
        connection.send_result(msg["id"], {"mode": mode})
        hass.config_entries.async_update_entry(entry, options=options)  # the integration reloads

    # ─── BBS SERVER ───────────────────────────────────────────────────────

    def bbs_state(hub) -> dict[str, Any]:
        folder = hub.bbs_folder()
        prepare_folder(folder, hub.config.language)
        try:
            st = load_settings(folder)
            settings = {k: getattr(st, k) for k in BBS_LIMITS}
        except BbsConfigError as err:
            settings = {"error": str(err)}
        bbs, now = hub.bbs, time.time()
        return {
            "on": hub.bbs_mode, "error": hub.bbs_error, "call": bbs.call if bbs else None,
            "ssid": hub.config.bbs_ssid, "folder": str(folder),
            "conns": [{"remote": c.remote, "minutes": int((now - c.since) // 60)} for c in bbs.conns.values()] if bbs else [],
            "messages": list(reversed(bbs.rows())) if bbs else [],
            "log": list(bbs.log) if bbs else [],
            "settings": settings, "welcome": read_text(folder, "welcome.txt"),
        }

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/bbs", vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_bbs(hass, connection, msg):
        hub = hub_of(hass, msg.get("entry_id"))
        connection.send_result(msg["id"], await hass.async_add_executor_job(bbs_state, hub))

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/bbs_delete", vol.Required("number"): int,
                                      vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_bbs_delete(hass, connection, msg):
        hub = hub_of(hass, msg.get("entry_id"))
        ok = bool(hub.bbs) and await hass.async_add_executor_job(hub.bbs.sysop_delete, msg["number"])
        connection.send_result(msg["id"], {"deleted": ok})

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/bbs_settings", vol.Required("settings"): dict,
                                      vol.Optional("welcome"): str, vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_bbs_settings(hass, connection, msg):
        """The limits and the welcome text, written into bbs.toml and welcome.txt; a running BBS reads them again."""
        hub = hub_of(hass, msg.get("entry_id"))
        try:
            values = {}
            for key, low in BBS_LIMITS.items():
                if key in msg["settings"]:
                    value = int(msg["settings"][key])
                    if value < low:
                        raise ValueError(f"{key} >= {low}")
                    values[("limits", key)] = value

            def write() -> None:
                folder = hub.bbs_folder()
                prepare_folder(folder, hub.config.language)
                update_settings(folder, values)
                if msg.get("welcome") is not None:
                    write_text(folder, "welcome.txt", msg["welcome"])
                hub.bbs_reload()

            await hass.async_add_executor_job(write)
        except (ValueError, TypeError, BbsConfigError, OSError) as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], {"saved": True})

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/bbs_reload", vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_bbs_reload(hass, connection, msg):
        hub = hub_of(hass, msg.get("entry_id"))
        try:
            await hass.async_add_executor_job(hub.bbs_reload)
        except BbsConfigError as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], {})

    # ─── TAK ──────────────────────────────────────────────────────────────

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/tak_position", vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_tak_position(hass, connection, msg):
        try:
            await hub_of(hass, msg.get("entry_id")).send_tak_position()
            connection.send_result(msg["id"], {})
        except (TransmitRefused, ConnectionError, ValueError) as err:
            error(connection, msg["id"], err)

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/tak_chat", vol.Required("text"): str,
                                      vol.Optional("to_uid", default=""): str,
                                      vol.Optional("to_callsign", default=""): str, vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_tak_chat(hass, connection, msg):
        try:
            await hub_of(hass, msg.get("entry_id")).send_tak_chat(msg["text"], msg["to_uid"], msg["to_callsign"])
            connection.send_result(msg["id"], {})
        except (TransmitRefused, ConnectionError, ValueError) as err:
            error(connection, msg["id"], err)

    # ─── #APRSThursday ────────────────────────────────────────────────────

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/thursday_send", vol.Required("text"): str,
                                      vol.Optional("via", default="both"): vol.In(["radio", "internet", "both"]),
                                      vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_thursday_send(hass, connection, msg):
        try:
            result = await hub_of(hass, msg.get("entry_id")).send_thursday(msg["text"], msg["via"])
            connection.send_result(msg["id"], result)
        except (TransmitRefused, ConnectionError, ValueError) as err:
            error(connection, msg["id"], err)

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/thursday_leave",
                                      vol.Optional("via", default="both"): vol.In(["radio", "internet", "both"]),
                                      vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_thursday_leave(hass, connection, msg):
        try:
            await hub_of(hass, msg.get("entry_id")).leave_thursday(msg["via"])
            connection.send_result(msg["id"], {})
        except (TransmitRefused, ConnectionError, ValueError) as err:
            error(connection, msg["id"], err)

    # ─── self-spotting an activation, and the services that answer a message ─

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/spot_options"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_spot_options(hass, connection, msg):
        """What the Spot dialog offers (the same tables the app uses), and the services list."""
        connection.send_result(msg["id"], {
            "programs": list(PROGRAMS),
            "gateways": {p: list(g) for p, g in PROGRAM_GATEWAYS.items()},
            "gateway_names": GATEWAY_NAMES,
            "modes": {g: list(m) for g, m in MODES.items()},
            "examples": {p: example for p, (_pattern, example) in REFERENCE.items()},
            "camilla": CAMILLA,
            "services": [{"call": s.call, "key": s.key, "commands": list(s.commands)} for s in SERVICES],
        })

    @websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/spot_build", vol.Required("program"): str,
                                      vol.Optional("reference", default=""): str,
                                      vol.Optional("frequency", default=""): str,
                                      vol.Optional("mode", default=""): str, vol.Optional("comment", default=""): str,
                                      vol.Optional("gateway", default=""): str, vol.Optional("test", default=False): bool,
                                      vol.Optional("entry_id"): str})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_spot_build(hass, connection, msg):
        """The message a spot makes (addressee and text), or why it cannot go; sending is send_message."""
        hub = hub_of(hass, msg.get("entry_id"))
        spot = Spot(msg["program"], msg["reference"], msg["frequency"], msg["mode"], msg["comment"], msg["gateway"],
                    msg["test"])
        try:
            to, text = build_spot(spot, str(hub.me))
            connection.send_result(msg["id"], {"to": to, "text": text})
        except SpotError as err:
            connection.send_result(msg["id"], {"error": err.code, "example": err.example})

    for handler in (ws_extra, ws_set_mode, ws_bbs, ws_bbs_delete, ws_bbs_settings, ws_bbs_reload,
                    ws_tak_position, ws_tak_chat, ws_thursday_send, ws_thursday_leave, ws_spot_options,
                    ws_spot_build):
        websocket_api.async_register_command(hass, handler)
