# Changelog

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
