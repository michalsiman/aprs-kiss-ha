"""Ties the shared engine (core/, the same as the standalone app's) to Home Assistant.

Everything about the radio lives in core.Engine: the TNC, APRS, APRS-IS and the iGate, the digipeater,
BBS SERVER, TAK, a USB GPS, #APRSThursday, terminal sessions and chat. The hub gives it the settings
(the config entry, our position from Home Assistant's home) and a folder under /config, and passes what
happens on to Home Assistant: the dispatcher for the entities, events on the bus for the panel and for
automations.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN, EVENT_MESSAGE, EVENT_PACKET, EVENT_TERMINAL, SIGNAL_UPDATE, VERSION
from .core.config import Config, save_state
from .core.engine import Engine

_LOGGER = logging.getLogger(__name__)

# what the panel follows live (EVENT_TERMINAL with this "kind")
PANEL_EVENTS = {"monitor", "terminal", "state", "chat", "aprs_message", "thursday", "tak", "bbs", "gps", "bulletin"}
# APRS-IS's "software" field: the integration, not the app
SOFTWARE = f"aprs-kiss-ha {VERSION}"


def make_config(hass: HomeAssistant, conf: dict[str, Any]) -> Config:
    """The engine's settings from the config entry; our position is Home Assistant's home."""
    config = Config.from_dict(conf)
    config.latitude, config.longitude = hass.config.latitude, hass.config.longitude
    config.language = "cs" if (hass.config.language or "").startswith("cs") else "en"
    # nothing of the app's own: no tracker (Home Assistant's home does not move), one SSID
    config.tracker_on = False
    config.profiles, config.profile = "", 0
    try:
        config.validate()
    except ValueError as err:
        _LOGGER.warning("Settings: %s", err)
    return config


class Hub(Engine):
    """One TNC with one callsign, as a Home Assistant config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.conf = {**entry.data, **entry.options}
        self.folder = Path(hass.config.path(DOMAIN))
        super().__init__(make_config(hass, self.conf), self.folder)
        self.add_listener(self._forward)

    _bbs_ready = False

    def _build_bbs(self) -> None:
        """The BBS reads its files: not in Home Assistant's event loop, async_start does it in an executor."""
        if self._bbs_ready:
            super()._build_bbs()
        else:
            self.bbs, self.bbs_call, self.bbs_error = None, None, ""

    def _build(self, tx_enabled: bool) -> None:
        super()._build(tx_enabled)
        if self.aprsis:
            self.aprsis.software = SOFTWARE

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self.folder.mkdir, 0o755, True, True)
        await self._migrate_store()
        self._bbs_ready = True
        await self.hass.async_add_executor_job(self._build_bbs)
        # the stations heard stay when the integration reloads (settings saved)
        heard = self.hass.data.setdefault(DOMAIN, {}).setdefault("heard", {}).pop(self.entry.entry_id, None)
        if heard:
            self.station.heard.update(heard)
        await self.start()

    async def async_stop(self) -> None:
        self.hass.data.setdefault(DOMAIN, {}).setdefault("heard", {})[self.entry.entry_id] = self.station.heard
        await self.stop()

    async def _migrate_store(self) -> None:
        """Up to 0.3.x the messages were in Home Assistant's storage; now in /config/aprs_kiss/state.json."""
        if await self.hass.async_add_executor_job((self.folder / "state.json").exists):
            return
        store = Store(self.hass, 1, f"{DOMAIN}.{self.entry.entry_id}")
        old = await store.async_load()
        if old:
            await self.hass.async_add_executor_job(save_state, {"msg_counter": old.get("msg_counter", 0),
                                                                "messages": old.get("messages", [])}, self.folder)
            await store.async_remove()
            _LOGGER.info("Message history moved to %s", self.folder / "state.json")

    # ─── what happens goes to Home Assistant ──────────────────────────────

    def _forward(self, kind: str, data: dict[str, Any]) -> None:
        entry_id = self.entry.entry_id
        if kind == "update":
            async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(entry_id))
        elif kind == "packet":
            self.hass.bus.async_fire(EVENT_PACKET, {"entry_id": entry_id, **data})
        elif kind == "message":
            self.hass.bus.async_fire(EVENT_MESSAGE, {"entry_id": entry_id, **data})
        if kind in PANEL_EVENTS:
            self.hass.bus.async_fire(EVENT_TERMINAL, {"entry_id": entry_id, "kind": kind, **data})
