# Changelog

## [Unreleased]

- **The same engine as the APRS & Packet app** (copied into `core/` by `tools/sync_core.py`), so fixes and new features come to both. The message history moves from Home Assistant's storage to `/config/aprs_kiss/state.json` by itself.
- **Map**: each station is its APRS symbol on a light disc with its callsign; stations that would cover each other move apart with a thin line to where they really are; **trails** (the last half hour); **filters** (weather stations, moving stations, repeaters, road incidents); **repeaters show their frequency**, band and digital mode; APRS **objects** are places of their own; impossible jumps in a track start it again.
- **Offline maps**: a basic map bundled (borders, motorways and roads, towns, peaks) and your own raster maps (MBTiles, PMTiles, RMaps, a ZIP of tiles, or a .zip/.7z of them) uploaded in Settings or copied into `/config/aprs_kiss/maps`. The map's layer button switches between online, your maps and the basic one.
- **One switch "Send over the internet too"** (APRS-IS card): the position (button, regular) and messages go to APRS-IS as well; messages can still choose radio, both or internet.
- **Digipeater** (fill-in or wide, aliases), **USB GPS** (NMEA) as our position, **#APRSThursday** tab, **BBS SERVER** and **TAK** modes (each instead of APRS, switched on with a safety sentence).
- **Spot** (APRS tab): self-spotting a SOTA, POTA, WWFF, SIOTA, GMA, WCA, IOTA or lighthouse activation through APRS2SOTA, Camilla (DL0QW-12) or APSPOT, checked and shown before it goes – the same as in the app.
- **Services** (APRS tab): FIND, REPEAT, WXNOW, UTC, satellite passes (9M2PJU-4) and e-mail (MAILMY), one click puts the command in the message line.
- Core synced with the app's 1.7.0: each weather station keeps the time of its weather report (not just of its last packet), callsigns and web links are found in message texts, and the app's units (km or miles, °C or °F, hPa or inHg) and weather-around-you helpers are in the core for the panel to use.
- Core synced with the app's 1.9.0: **position privacy** in the core (a less exact position – about 200 m to 110 km – and speed, course and altitude left out if wished; EMERGENCY always exact), **bulletins** received by radio and from APRS-IS (the server is asked for them) and kept with the history, Mic-E with EMERGENCY, Winlink (APRSLink) login helpers, and frames described in a few words for lists.
- A serial TNC that is not there or does not answer is said plainly (not there, not answering, not allowed – the dialout group) instead of a bare "Could not configure port".

## [0.3.8] - 2026-11-22

- Chat shows only text meant for people: frames to CQ, QST, ALL or your own callsign. Automatic frames, such as a digipeater's "DX de …" report of the farthest station it heard or station IDs, stay in the monitor.

## [0.3.7] - 2026-11-22

- Third-party packets (`}`), which an iGate uses to put an internet station on the air, are now unpacked: the station inside shows on the map at its position, with *iGate OK0XYZ* in its popup and in the station list until your radio hears it directly.
- Messages for you that an iGate relays from the internet by radio are now received and acknowledged (the ack goes back by radio for the iGate to pass on). Before, they were dropped unless APRS-IS was also connected.
- Monitor: the radio's frames are kept apart from APRS-IS lines, so with *From the internet (APRS-IS)* switched off a busy APRS-IS feed no longer pushes them out of the history.

## [0.3.6] - 2026-11-19

- The *APRS-IS connected* sensor no longer carries the line and iGate counters (lines in and out, RF→IS, IS→RF, messages). They grew with every packet heard, and each change was a new row in Home Assistant's database (about 3,700 a day, while the connection itself changed a few times in ten days). The sensor keeps the server, the host and the last error; the counters stay in the panel's Settings.

## [0.3.5] - 2026-11-19

- Settings: new *TNC connection* card at the top: network (address and port) or USB / serial port, picked from the ports found on the Home Assistant machine (Search again; *Other* to type a path) with the speed. Saving restarts the integration with the new connection. The card also shows whether the TNC is connected and the last error.
- The setup step for a serial TNC lists the ports found (the stable /dev/serial/by-id/… name first) instead of a bare text field, and the speed defaults to 115200.
- *Reconfigure* in Settings → Devices & services changes where the TNC is (network or USB / serial) without removing the integration.

## [0.3.4] - 2026-11-17

- Settings: the licence sentence field showed even with APRS-IS already on; it appears again only while switching APRS-IS on.
- README: installing from the Home Assistant Marketplace, with a button that adds the repository in one click.
- New Settings screenshots.
- Settings: *Send it regularly over the internet too (APRS-IS)* under the position interval. The regular position goes by radio while Transmit is on, and to APRS-IS only with this box ticked (before, it always went to APRS-IS when connected). Off by default. The *Send position* button still goes both ways.

## [0.3.3] - 2026-11-16

- Stations from APRS-IS: when several iGates send the same packet within a minute, the first copy is kept (later copies often carry an iGate's own additions, such as LoRa signal reports that break the weather data); packets received with bit errors no longer overwrite a station's comment, weather or position.
- APRS-IS lines are read as UTF-8 (Latin-1 as a fallback), so accented letters in comments show correctly.
- No lone 🌡 for a station without weather data.
- APRS map: the station popup is smaller (it scrolls inside when long) and the map moves so it stays clear of the zoom buttons; on a phone it no longer covers the map.

## [0.3.2] - 2026-11-16

- Chat is plain packet chat, nothing of APRS: no *To* and *via* fields, the text goes out as it is (no `CALL:` prefix, your callsign is the frame's sender) in a UI frame to `CQ`, direct, without digipeaters. APRS packets never appear in the chat, so the *Show APRS packets* switch is gone.
- APRS-IS is off by default, and switching it on asks you to type *I hold a valid amateur radio licence* (*mám platnou radioamatérskou licenci*); the integration checks it too. An installation that had APRS-IS on without this statement starts with it off.
- APRS tab on a phone: the message form and the map stay in place under the header; only the messages and stations heard scroll below them.
- APRS-IS packets show in the Monitor, marked `[IS]` (received and sent), and their stations on the map and in *Stations heard*, marked 🌐 and purple until the radio hears them itself. The *Stations heard* sensor still counts only stations heard by the radio, and the iGate decides who is local by the radio alone. Tracked callsigns also follow positions from APRS-IS.
- APRS tab: new packets only refresh the lists and the map markers. The map keeps the zoom and position you chose (also after switching tabs), the lists keep their scroll, and a message being typed is not lost.
- Monitor: a *From the internet (APRS-IS)* switch shows or hides the `[IS]` lines (remembered in the browser).
- APRS messages: choose 📻 Radio or 🌐 Internet (APRS-IS) next to the message in the panel (remembered; radio by default while transmitting is on); retries go the same way. The `send_message` service has a `via` option: `radio`, `internet` or `both` (default, as before).
- Settings: as soon as something changes, *Changes are not saved yet: press Save* appears and the Save button is highlighted, so a change (such as switching APRS-IS off) isn't left unsaved by mistake.
- After an update a banner at the top says a new version is installed, with a *Reload page* button (as in MeshCore Chattx): no need to close the Home Assistant app. It is checked when Home Assistant reconnects after its restart and when the app comes back to the foreground.
- The panel keeps receiving live updates after you open another page of Home Assistant and come back.

## [0.3.1] - 2026-11-16

- Settings: a clear *APRS-IS password (passcode)* field with Show/Hide; empty means computed from the callsign.
- The panel works well on a phone:
  - the header with the ☰ button (opens Home Assistant's sidebar), the TNC and Transmit status and the tabs always stays on top; the panel is pinned to the screen and only the content below the header scrolls;
  - with the on-screen keyboard open (Chat, Terminal) the panel fits the visible part of the screen (as in MeshCore Chattx): the input sits right above the keyboard, the latest lines above it;
  - Settings is a gear icon at the end of the tab bar, so all tabs fit;
  - forms take one column and never get wider than the screen, inputs don't make iOS zoom, the APRS map and message list fit the screen.
- No error when the panel script is loaded twice (e.g. the app kept an older copy).
- New screenshots, including a phone, light and dark.

## [0.3.0] - 2026-11-16

- Settings tab: callsign and SSID with the usual meaning of each SSID, the APRS icon from the 30 most common symbols, comment, path, a regular position beacon (every N minutes, at least 10), tracked callsigns, incoming connections, TX delay. Saving restarts the integration with the new settings.
- APRS-IS: login with the passcode computed from the callsign (not shown), a range filter around home, reconnecting by itself. Messages to you from the internet arrive in Home Assistant and are acknowledged over the internet; your own packets go to APRS-IS too, so messaging works through the internet also with transmitting off.
- iGate: RF → APRS-IS following the iGate rules (no NOGATE, RFONLY, TCPIP, TCPXX, queries or third-party internet traffic), and APRS-IS → RF for messages to stations heard on RF in the last 30 minutes, in the third-party format. Both off by default.
- Entity *APRS-IS connected* with the server and counters.
- New screenshots including Settings, light and dark.

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
