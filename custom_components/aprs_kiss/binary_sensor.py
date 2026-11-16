"""TNC link state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory

from .entity import AprsKissEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    hub = entry.runtime_data
    entities = [TncConnected(hub, "tnc_connected")]
    if hub.aprsis:
        entities.append(AprsIsConnected(hub, "aprsis_connected"))
    async_add_entities(entities)


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


class AprsIsConnected(AprsKissEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return bool(self.hub.aprsis and self.hub.aprsis.verified)

    @property
    def extra_state_attributes(self):
        c = self.hub.aprsis
        return {"server": c.server_name, "host": c.host, "last_error": c.last_error,
                "lines_in": c.lines_in, "lines_out": c.lines_out, **self.hub.igate_stats} if c else {}
