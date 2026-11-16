# Changelog

## [0.2.1] - 2026-11-16

- The whole panel follows Home Assistant's theme, light or dark: the terminal, the monitor and the map labels no longer have fixed dark colours.
- New screenshots of all four tabs, light and dark (the README shows the one matching your GitHub theme).

## [0.2.0] - 2026-11-16

- Everything the panel uses comes from Home Assistant: Leaflet is bundled with the integration, and map tiles come through Home Assistant's tile proxy (`/api/map_tiles`, HA 2026.11+) instead of the browser fetching CDN files and OpenStreetMap tiles itself (which OpenStreetMap blocked).
- Chat tab: type and press Enter, the text goes to everyone as an unproto UI frame starting with your callsign; everything others type on the frequency is listed below (APRS packets hidden unless switched on).
- README: automations from a tracked station entering a zone.
- Simulator: plain-text CQ traffic and replies to chat.

## [0.1.1] - 2026-11-16

- Requirement aprslib as a minimum version (aprslib>=0.7.2), as Home Assistant requires for packages it also uses.

## [0.1.0] - 2026-11-16

First release.

- KISS TNC over TCP or a serial port, reconnecting by itself (radios may reset their USB port at key-up).
- APRS: receive and decode (aprslib) positions, Mic-E, weather, status, objects and messages; messages to us are acknowledged; send messages repeated until acknowledged, position and status; duplicates from digipeaters are dropped; transmit limits.
- Packet radio terminal: AX.25 v2.0 connected mode (window 4, retransmission, REJ, idle check), unproto text, optional incoming connections.
- Panel "APRS & Packet": terminal, frame monitor, APRS with a map of stations heard, messages and weather.
- Entities, services (send_message, send_position, send_status, send_unproto) and events (aprs_kiss_message, aprs_kiss_packet).
- KISS serial ↔ TCP bridge (Python standard library) with a systemd unit, and a simulated TNC for testing without a radio.
