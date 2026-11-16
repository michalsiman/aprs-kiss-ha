"""Setup in the UI: where the TNC is, then the station."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .ax25 import Address
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
        return self.async_show_form(step_id="tcp", data_schema=vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(1, 65535)),
        }))

    async def async_step_serial(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._data = {CONF_CONNECTION: "serial", **user_input}
            return await self.async_step_station()
        return self.async_show_form(step_id="serial", data_schema=vol.Schema({
            vol.Required(CONF_DEVICE): str,
            vol.Required(CONF_BAUDRATE, default=9600): vol.All(int, vol.Range(1200, 1000000)),
        }))

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
