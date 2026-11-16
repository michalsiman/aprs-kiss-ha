"""TNC link state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import AprsKissEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([TncConnected(entry.runtime_data, "tnc_connected")])


class TncConnected(AprsKissEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return self.hub.connection.connected

    @property
    def extra_state_attributes(self):
        c = self.hub.connection
        return {"reconnects": c.reconnects, "last_error": c.last_error}
