"""APRS & Packet: APRS and a packet radio terminal through a KISS TNC."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .aprsis import licence_confirmed
from .const import CONF_APRSIS, CONF_LICENCE, DOMAIN, PANEL_STATIC, PANEL_URL
from .hub import Hub
from .station import TransmitRefused

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.DEVICE_TRACKER, Platform.SENSOR, Platform.SWITCH]
PANEL_PATH = "aprs-packet"

type AprsKissConfigEntry = ConfigEntry[Hub]


async def async_setup_entry(hass: HomeAssistant, entry: AprsKissConfigEntry) -> bool:
    hub = Hub(hass, entry)
    entry.runtime_data = hub
    await hub.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    bucket = hass.data.setdefault(DOMAIN, {})
    if not bucket.get("registered"):
        bucket["registered"] = True
        _register_services(hass)
        _register_ws(hass)
        await _register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AprsKissConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    await entry.runtime_data.async_stop()
    return ok


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _hub(hass: HomeAssistant, entry_id: str | None = None) -> Hub:
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if entry_id in (None, entry.entry_id):
            return entry.runtime_data
    raise ServiceValidationError("APRS & Packet is not set up")


async def _guard(coro):
    try:
        return await coro
    except TransmitRefused as err:
        raise HomeAssistantError(f"Not sent: {err}") from err
    except (ConnectionError, ValueError) as err:
        raise HomeAssistantError(f"Not sent: {err}") from err


# ─── services ─────────────────────────────────────────────────────────────

def _register_services(hass: HomeAssistant) -> None:
    entry_field = {vol.Optional("config_entry_id"): cv.string}

    async def send_message(call: ServiceCall) -> ServiceResponse:
        hub = _hub(hass, call.data.get("config_entry_id"))
        return await _guard(hub.send_aprs_message(call.data["to"], call.data["text"], call.data.get("via", "both")))

    async def send_position(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("config_entry_id"))
        lat = call.data.get("latitude", hass.config.latitude)
        lon = call.data.get("longitude", hass.config.longitude)
        await _guard(hub.station.send_position(lat, lon, call.data.get("comment")))

    async def send_status(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("config_entry_id"))
        await _guard(hub.station.send_status(call.data["text"]))

    async def send_unproto(call: ServiceCall) -> None:
        hub = _hub(hass, call.data.get("config_entry_id"))
        await _guard(hub.send_unproto(call.data.get("destination", "CQ"), call.data["text"], call.data.get("path", "")))

    hass.services.async_register(
        DOMAIN, "send_message", send_message,
        vol.Schema({**entry_field, vol.Required("to"): cv.string, vol.Required("text"): cv.string,
                    vol.Optional("via", default="both"): vol.In(["radio", "internet", "both"])}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, "send_position", send_position,
        vol.Schema({**entry_field, vol.Optional("latitude"): cv.latitude, vol.Optional("longitude"): cv.longitude,
                    vol.Optional("comment"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN, "send_status", send_status, vol.Schema({**entry_field, vol.Required("text"): cv.string}))
    hass.services.async_register(
        DOMAIN, "send_unproto", send_unproto,
        vol.Schema({**entry_field, vol.Optional("destination", default="CQ"): cv.string,
                    vol.Required("text"): cv.string, vol.Optional("path", default=""): cv.string}),
    )


# ─── WebSocket API for the panel ──────────────────────────────────────────

def _register_ws(hass: HomeAssistant) -> None:
    for handler in (ws_state, ws_connect, ws_disconnect, ws_send_text, ws_send_unproto, ws_send_message, ws_set_tx,
                    ws_send_chat, ws_get_settings, ws_set_settings, ws_serial_ports):
        websocket_api.async_register_command(hass, handler)


def _error(connection, msg_id, err: Exception) -> None:
    connection.send_error(msg_id, "not_sent", str(err))


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/state", vol.Optional("entry_id"): str})
@websocket_api.async_response
async def ws_state(hass, connection, msg):
    hub = _hub(hass, msg.get("entry_id"))
    connection.send_result(msg["id"], {
        "entry_id": hub.entry.entry_id,
        "callsign": str(hub.me),
        "tnc_connected": hub.connection.connected,
        "tx_enabled": hub.station.tx_enabled,
        "path": hub.conf.get("path", ""),
        "monitor": list(hub.monitor),
        "monitor_rf": list(hub.monitor_rf),
        "terminal": list(hub.terminal),
        "chat": list(hub.chat),
        "sessions": hub.session_states(),
        "messages": [{**m, "state": hub.message_state(m.get("msg_no")) if m["direction"] == "out" else None}
                     for m in hub.messages],
        "heard": list(hub.station.heard.values())[-100:],
    })


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/connect", vol.Required("remote"): str,
                                  vol.Optional("path", default=""): str, vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_connect(hass, connection, msg):
    try:
        _hub(hass, msg.get("entry_id")).connect(msg["remote"], msg["path"])
        connection.send_result(msg["id"], {})
    except (TransmitRefused, ConnectionError, ValueError) as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/disconnect", vol.Required("remote"): str,
                                  vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_disconnect(hass, connection, msg):
    try:
        _hub(hass, msg.get("entry_id")).disconnect(msg["remote"])
        connection.send_result(msg["id"], {})
    except ValueError as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/send_text", vol.Required("remote"): str,
                                  vol.Required("text"): str, vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_send_text(hass, connection, msg):
    try:
        _hub(hass, msg.get("entry_id")).send_text(msg["remote"], msg["text"])
        connection.send_result(msg["id"], {})
    except (ConnectionError, ValueError) as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/send_unproto", vol.Required("text"): str,
                                  vol.Optional("destination", default="CQ"): str, vol.Optional("path", default=""): str,
                                  vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_send_unproto(hass, connection, msg):
    try:
        await _hub(hass, msg.get("entry_id")).send_unproto(msg["destination"], msg["text"], msg["path"])
        connection.send_result(msg["id"], {})
    except (TransmitRefused, ConnectionError, ValueError) as err:
        _error(connection, msg["id"], err)


# Where the TNC is. Kept in the entry's data, as the setup put it there.
CONNECTION_KEYS = {"connection": str, "host": str, "port": int, "device": str, "baudrate": int}


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/serial_ports"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_serial_ports(hass, connection, msg):
    from .ports import list_serial_ports  # noqa: PLC0415

    connection.send_result(msg["id"], {"ports": await hass.async_add_executor_job(list_serial_ports)})


SETTINGS_KEYS = {
    "callsign": str, "path": str, "symbol": str, "comment": str, "beacon_minutes": int,
    "beacon_is": bool, "tracked_callsigns": str, "accept_incoming": bool, "txdelay_ms": int,
    "aprsis_enabled": bool, "aprsis_host": str, "aprsis_port": int, "aprsis_passcode": str,
    "aprsis_radius_km": int, "igate_rx": bool, "igate_tx": bool,
}


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/get_settings", vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_get_settings(hass, connection, msg):
    hub = _hub(hass, msg.get("entry_id"))
    conf = {**hub.entry.data, **hub.entry.options}
    out = {k: conf.get(k) for k in SETTINGS_KEYS}
    out["aprsis_enabled"] = bool(conf.get(CONF_APRSIS) and conf.get(CONF_LICENCE))
    out["aprsis"] = {
        "connected": bool(hub.aprsis and hub.aprsis.connected),
        "verified": bool(hub.aprsis and hub.aprsis.verified),
        "server": hub.aprsis.server_name if hub.aprsis else None,
        "error": hub.aprsis.last_error if hub.aprsis else None,
    } if hub.aprsis else None
    out["igate_stats"] = hub.igate_stats
    out.update({k: conf.get(k) for k in CONNECTION_KEYS})
    out["connection"] = conf.get("connection") or "tcp"
    out["tnc"] = {"connected": hub.connection.connected, "error": hub.connection.last_error}
    connection.send_result(msg["id"], out)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/set_settings", vol.Required("settings"): dict,
                                  vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_settings(hass, connection, msg):
    from .ax25 import Address  # noqa: PLC0415

    hub = _hub(hass, msg.get("entry_id"))
    entry = hub.entry
    new: dict[str, Any] = {}
    try:
        for key, value in msg["settings"].items():
            kind = SETTINGS_KEYS.get(key)
            if kind is None:
                continue
            new[key] = kind(value) if value is not None and value != "" else (False if kind is bool else ("" if kind is str else 0))
        if "callsign" in new:
            new["callsign"] = str(Address.parse(new["callsign"]))
        for p in (new.get("path") or "").replace(" ", ",").split(","):
            if p.strip():
                Address.parse(p)
        if "symbol" in new and len(new["symbol"]) != 2:
            raise ValueError("The symbol is two characters: table and code")
        if new.get("aprsis_passcode") and not str(new["aprsis_passcode"]).lstrip("-").isdigit():
            raise ValueError("The passcode is a number")
        from .ports import connection_update  # noqa: PLC0415

        tnc = connection_update(msg["settings"])
        conf = {**entry.data, **entry.options}
        was_on = bool(conf.get(CONF_APRSIS) and conf.get(CONF_LICENCE))
        if new.get(CONF_APRSIS) and not was_on:
            # Switching APRS-IS on needs the licence statement typed out.
            if not licence_confirmed(msg["settings"].get("licence_text")):
                raise ValueError("licence_required")
            new[CONF_LICENCE] = True
        elif not new.get(CONF_APRSIS, conf.get(CONF_APRSIS)):
            new[CONF_LICENCE] = False
    except (ValueError, TypeError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    options = {**entry.options, **new}
    update: dict[str, Any] = {"options": options}
    if tnc:
        update["data"] = {**entry.data, **tnc}
    if new.get("callsign") and new["callsign"] != entry.title:
        update["title"] = new["callsign"]
        update["unique_id"] = new["callsign"]
    connection.send_result(msg["id"], {"saved": True})
    hass.config_entries.async_update_entry(entry, **update)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/send_chat", vol.Required("text"): str,
                                  vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_send_chat(hass, connection, msg):
    try:
        await _hub(hass, msg.get("entry_id")).send_chat(msg["text"])
        connection.send_result(msg["id"], {})
    except (TransmitRefused, ConnectionError, ValueError) as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/send_message", vol.Required("to"): str,
                                  vol.Required("text"): str, vol.Optional("entry_id"): str,
                                  vol.Optional("via", default="both"): vol.In(["radio", "internet", "both"])})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_send_message(hass, connection, msg):
    try:
        result = await _hub(hass, msg.get("entry_id")).send_aprs_message(msg["to"], msg["text"], msg["via"])
        connection.send_result(msg["id"], result)
    except (TransmitRefused, ConnectionError, ValueError) as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command({vol.Required("type"): "aprs_kiss/set_tx", vol.Required("enabled"): bool,
                                  vol.Optional("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_set_tx(hass, connection, msg):
    hub = _hub(hass, msg.get("entry_id"))
    hub.station.tx_enabled = msg["enabled"]
    hub._on_update()  # noqa: SLF001 - the switch entity follows
    connection.send_result(msg["id"], {"tx_enabled": hub.station.tx_enabled})


# ─── panel ────────────────────────────────────────────────────────────────

async def _register_panel(hass: HomeAssistant) -> None:
    folder = Path(__file__).parent / "frontend"
    path = folder / "aprs-kiss-panel.js"
    # The panel and its bundled libraries (Leaflet) come from Home Assistant itself.
    await hass.http.async_register_static_paths([StaticPathConfig(PANEL_STATIC, str(folder), cache_headers=False)])
    version = await hass.async_add_executor_job(lambda: str(int(path.stat().st_mtime)) if path.exists() else "0")
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="aprs-kiss-panel",
        frontend_url_path=PANEL_PATH,
        module_url=f"{PANEL_URL}?v={version}",
        sidebar_title="APRS & Packet",
        sidebar_icon="mdi:radio-handheld",
        require_admin=True,
        config={},
    )


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if not hass.config_entries.async_entries(DOMAIN) or all(e.entry_id == entry.entry_id for e in hass.config_entries.async_entries(DOMAIN)):
        frontend.async_remove_panel(hass, PANEL_PATH)
        hass.data.get(DOMAIN, {}).pop("registered", None)


__all__: list[Any] = ["async_setup_entry", "async_unload_entry"]
