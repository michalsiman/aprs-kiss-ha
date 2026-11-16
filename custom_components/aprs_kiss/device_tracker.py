"""Stations from the tracked list, placed where their last position packet said."""

from __future__ import annotations

from homeassistant.components.device_tracker import SourceType, TrackerEntity

from .const import CONF_TRACKED
from .entity import AprsKissEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    hub = entry.runtime_data
    calls = [c.strip().upper() for c in ({**entry.data, **entry.options}.get(CONF_TRACKED) or "").split(",") if c.strip()]
    async_add_entities([StationTracker(hub, call) for call in calls])


class StationTracker(AprsKissEntity, TrackerEntity):
    _attr_icon = "mdi:radio-handheld"

    def __init__(self, hub, call: str) -> None:
        super().__init__(hub, f"tracker_{call.lower().replace('-', '_')}")
        self._call = call
        self._attr_translation_key = None
        self._attr_name = call

    @property
    def _entry(self):
        return self.hub.station.heard.get(self._call, {})

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self):
        return self._entry.get("latitude")

    @property
    def longitude(self):
        return self._entry.get("longitude")

    @property
    def location_accuracy(self) -> int:
        return 20

    @property
    def extra_state_attributes(self):
        e = self._entry
        out = {k: e[k] for k in ("comment", "speed", "course", "altitude", "last_heard", "last_rf", "last_is", "path") if k in e}
        out.update({f"wx_{k}": v for k, v in (e.get("weather") or {}).items()})
        return out
