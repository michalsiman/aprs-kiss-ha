"""Last packet, last message for us, stations heard, counters."""

from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory

from .entity import AprsKissEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    hub = entry.runtime_data
    async_add_entities([
        LastPacket(hub, "last_packet"),
        LastMessage(hub, "last_message"),
        StationsHeard(hub, "stations_heard"),
        Counter(hub, "packets_received", "received"),
        Counter(hub, "frames_sent", "sent"),
    ])


class LastPacket(AprsKissEntity, SensorEntity):
    _attr_icon = "mdi:access-point"

    @property
    def native_value(self):
        p = self.hub.station.last_packet
        return p["from"] if p else None

    @property
    def extra_state_attributes(self):
        p = self.hub.station.last_packet or {}
        keep = ("from", "to", "format", "path", "latitude", "longitude", "comment", "status", "raw")
        return {k: p[k] for k in keep if k in p}


class LastMessage(AprsKissEntity, SensorEntity):
    _attr_icon = "mdi:message-text"

    @property
    def native_value(self):
        m = self.hub.station.last_message
        return m["text"][:255] if m else None

    @property
    def extra_state_attributes(self):
        m = self.hub.station.last_message or {}
        out = {k: m[k] for k in ("from", "msg_no", "path") if k in m}
        if "received_at" in m:
            out["received_at"] = datetime.fromtimestamp(m["received_at"], timezone.utc).isoformat()
        return out


class StationsHeard(AprsKissEntity, SensorEntity):
    _attr_icon = "mdi:account-group"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return sum(1 for e in self.hub.station.heard.values() if "last_rf" in e)  # by the radio


class Counter(AprsKissEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, key, stat):
        super().__init__(hub, key)
        self._stat = stat

    @property
    def native_value(self):
        return self.hub.station.stats[self._stat]


__all__ = ["SensorDeviceClass"]
