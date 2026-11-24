"""Setup in the UI: where the TNC is, then the station."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .core.ax25 import Address
from .ports import list_serial_ports
from .const import (
    CONF_ACCEPT_INCOMING, CONF_BAUDRATE, CONF_CALLSIGN, CONF_COMMENT, CONF_CONNECTION, CONF_DEVICE,
    CONF_HOST, CONF_PATH, CONF_PORT, CONF_SYMBOL, CONF_TRACKED, CONF_TXDELAY, DEFAULT_PATH, DEFAULT_PORT,
    DEFAULT_SYMBOL, DOMAIN,
)


def _station_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_CALLSIGN, default=defaults.get(CONF_CALLSIGN, "")): str,
        vol.Optional(CONF_PATH, default=defaults.get(CONF_PATH, DEFAULT_PATH)): str,
        vol.Optional(CONF_SYMBOL, default=defaults.get(CONF_SYMBOL, DEFAULT_SYMBOL)): str,
        vol.Optional(CONF_COMMENT, default=defaults.get(CONF_COMMENT, "")): str,
        vol.Optional(CONF_ACCEPT_INCOMING, default=defaults.get(CONF_ACCEPT_INCOMING, False)): bool,
    })


BAUD_RATES = [1200, 4800, 9600, 19200, 38400, 57600, 115200]


def _tcp_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(int, vol.Range(1, 65535)),
    })


def _serial_schema(ports: list[dict[str, str]], defaults: dict[str, Any]) -> vol.Schema:
    """A port picked from the ones found, or typed in; the speed from the usual ones."""
    current = defaults.get(CONF_DEVICE) or (ports[0]["device"] if ports else "")
    options = [selector.SelectOptionDict(value=p["device"], label=p["label"]) for p in ports]
    if current and all(p["device"] != current for p in ports):
        options.append(selector.SelectOptionDict(value=current, label=current))
    return vol.Schema({
        vol.Required(CONF_DEVICE, default=current): selector.SelectSelector(selector.SelectSelectorConfig(
            options=options, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN)),
        vol.Required(CONF_BAUDRATE, default=str(defaults.get(CONF_BAUDRATE, 115200))): selector.SelectSelector(
            selector.SelectSelectorConfig(options=[str(b) for b in BAUD_RATES], custom_value=True,
                                          mode=selector.SelectSelectorMode.DROPDOWN)),
    })


def _check_serial(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not str(data.get(CONF_DEVICE) or "").startswith("/dev/"):
        errors[CONF_DEVICE] = "invalid_device"
    try:
        if not 1200 <= int(data.get(CONF_BAUDRATE) or 0) <= 1000000:
            raise ValueError
    except ValueError:
        errors[CONF_BAUDRATE] = "invalid_baudrate"
    return errors


def _check_station(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    try:
        Address.parse(data[CONF_CALLSIGN])
    except ValueError:
        errors[CONF_CALLSIGN] = "invalid_callsign"
    try:
        for p in (data.get(CONF_PATH) or "").replace(" ", ",").split(","):
            if p.strip():
                Address.parse(p)
    except ValueError:
        errors[CONF_PATH] = "invalid_path"
    if len(data.get(CONF_SYMBOL) or "") != 2:
        errors[CONF_SYMBOL] = "invalid_symbol"
    return errors


class AprsKissConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["tcp", "serial"])

    async def async_step_tcp(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {CONF_CONNECTION: "tcp", **user_input}
            return await self.async_step_station()
        return self.async_show_form(step_id="tcp", data_schema=_tcp_schema({}))

    async def async_step_serial(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_serial(user_input)
            if not errors:
                self._data = {CONF_CONNECTION: "serial", CONF_DEVICE: user_input[CONF_DEVICE],
                              CONF_BAUDRATE: int(user_input[CONF_BAUDRATE])}
                return await self.async_step_station()
        ports = await self.hass.async_add_executor_job(list_serial_ports)
        return self.async_show_form(step_id="serial", data_schema=_serial_schema(ports, user_input or {}), errors=errors)

    # ─── change where the TNC is, keeping the station ─────────────────────

    async def async_step_reconfigure(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="reconfigure", menu_options=["reconfigure_tcp", "reconfigure_serial"])

    async def async_step_reconfigure_tcp(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            return self.async_update_reload_and_abort(entry, data_updates={CONF_CONNECTION: "tcp", **user_input})
        return self.async_show_form(step_id="reconfigure_tcp", data_schema=_tcp_schema(dict(entry.data)))

    async def async_step_reconfigure_serial(self, user_input=None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_serial(user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={
                    CONF_CONNECTION: "serial", CONF_DEVICE: user_input[CONF_DEVICE],
                    CONF_BAUDRATE: int(user_input[CONF_BAUDRATE])})
        ports = await self.hass.async_add_executor_job(list_serial_ports)
        return self.async_show_form(step_id="reconfigure_serial",
                                    data_schema=_serial_schema(ports, user_input or dict(entry.data)), errors=errors)

    async def async_step_station(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_CALLSIGN] = user_input[CONF_CALLSIGN].strip().upper()
            errors = _check_station(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_CALLSIGN])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_CALLSIGN], data={**self._data, **user_input})
        return self.async_show_form(step_id="station", data_schema=_station_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return AprsKissOptionsFlow()


class AprsKissOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_CALLSIGN] = current[CONF_CALLSIGN]
            errors = _check_station(user_input)
            if not errors:
                user_input.pop(CONF_CALLSIGN)
                return self.async_create_entry(data=user_input)
        schema = vol.Schema({
            vol.Optional(CONF_PATH, default=current.get(CONF_PATH, DEFAULT_PATH)): str,
            vol.Optional(CONF_SYMBOL, default=current.get(CONF_SYMBOL, DEFAULT_SYMBOL)): str,
            vol.Optional(CONF_COMMENT, default=current.get(CONF_COMMENT, "")): str,
            vol.Optional(CONF_TRACKED, default=current.get(CONF_TRACKED, "")): str,
            vol.Optional(CONF_ACCEPT_INCOMING, default=current.get(CONF_ACCEPT_INCOMING, False)): bool,
            vol.Optional(CONF_TXDELAY, default=current.get(CONF_TXDELAY, 0)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1000, step=10, unit_of_measurement="ms",
                                              mode=selector.NumberSelectorMode.BOX)),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
