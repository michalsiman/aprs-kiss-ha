"""Send our position (Home Assistant's home) once."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import AprsKissEntity
from .station import TransmitRefused


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([BeaconButton(entry.runtime_data, "send_position")])


class BeaconButton(AprsKissEntity, ButtonEntity):
    _attr_icon = "mdi:map-marker-radius"

    async def async_press(self) -> None:
        try:
            await self.hub.station.send_position(self.hass.config.latitude, self.hass.config.longitude)
        except (TransmitRefused, ConnectionError) as err:
            raise HomeAssistantError(f"Not sent: {err}") from err
