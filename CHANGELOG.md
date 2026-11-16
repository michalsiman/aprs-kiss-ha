# Changelog

## [0.1.0] - 2026-11-16

First release.

- KISS TNC over TCP or a serial port, reconnecting by itself (radios may reset their USB port at key-up).
- APRS: receive and decode (aprslib) positions, Mic-E, weather, status, objects and messages; messages to us are acknowledged; send messages repeated until acknowledged, position and status; duplicates from digipeaters are dropped; transmit limits.
- Packet radio terminal: AX.25 v2.0 connected mode (window 4, retransmission, REJ, idle check), unproto text, optional incoming connections.
- Panel "APRS & Packet": terminal, frame monitor, APRS with a map of stations heard, messages and weather.
- Entities, services (send_message, send_position, send_status, send_unproto) and events (aprs_kiss_message, aprs_kiss_packet).
- KISS serial ↔ TCP bridge (Python standard library) with a systemd unit, and a simulated TNC for testing without a radio.
