"""Transmit on/off. Off after the first setup; the last state is kept over restarts."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import AprsKissEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([TransmitSwitch(entry.runtime_data, "transmit")])


class TransmitSwitch(AprsKissEntity, SwitchEntity, RestoreEntity):
    _attr_icon = "mdi:radio-tower"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        self.hub.station.tx_enabled = bool(last and last.state == "on")

    @property
    def is_on(self) -> bool:
        return self.hub.station.tx_enabled

    async def async_turn_on(self, **kwargs) -> None:
        self.hub.station.tx_enabled = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self.hub.station.tx_enabled = False
        for sess in list(self.hub.sessions.values()):
            sess.close()
        self.async_write_ha_state()
