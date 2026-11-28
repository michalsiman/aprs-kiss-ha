/* APRS & Packet panel: packet radio terminal, frame monitor and APRS messages. No build step. */

// Everything the panel needs comes from Home Assistant: Leaflet is bundled with
// the integration, and map tiles come through Home Assistant's tile proxy.
import { StationMap, MAP_CSS, symbolInfo, repeaterLabel } from './aprs-map.js';

const LEAFLET_JS = new URL('vendor/leaflet-src.esm.js', import.meta.url).href;
const LEAFLET_CSS = new URL('vendor/leaflet.css', import.meta.url).href;
const TILE_TOKEN_REFRESH_MS = 20 * 60 * 1000;

// SSID conventions (APRS SSID recommendations by Bob Bruninga, WB4APR).
const SSIDS = {
  en: ['0 – home station, primary', '1 – generic additional station, digi, mobile, wx', '2 – generic additional station', '3 – generic additional station',
    '4 – generic additional station', '5 – other networks (D-STAR, iPhone, Android…)', '6 – special activity, satellite, camping', '7 – handheld, walkie-talkie',
    '8 – boat, sailboat, RV, second main mobile', '9 – primary mobile (car)', '10 – internet, iGate, EchoLink, Winlink', '11 – balloon, aircraft, spacecraft',
    '12 – APRStt, DTMF, one-way tracker', '13 – weather station', '14 – truck', '15 – generic additional station'],
  cs: ['0 – domácí stanice, hlavní', '1 – další stanice, digi, mobil, meteo', '2 – další stanice', '3 – další stanice',
    '4 – další stanice', '5 – jiné sítě (D-STAR, iPhone, Android…)', '6 – zvláštní akce, satelit, kempování', '7 – ruční stanice (ručka)',
    '8 – loď, karavan, druhé auto', '9 – hlavní mobilní (auto)', '10 – internet, iGate, EchoLink, Winlink', '11 – balón, letadlo, kosmická loď',
    '12 – APRStt, DTMF, jednosměrný tracker', '13 – meteostanice', '14 – nákladní auto', '15 – další stanice'],
};

// The APRS symbols people use most (table + code), with an emoji to recognise them.
const SYMBOLS = [
  ['/-', '🏠', 'House', 'Dům'], ['/>', '🚗', 'Car', 'Auto'], ['/[', '🚶', 'Person (jogger)', 'Osoba (chodec)'],
  ['/b', '🚲', 'Bicycle', 'Kolo'], ['/<', '🏍️', 'Motorcycle', 'Motorka'], ['/k', '🛻', 'Pickup truck', 'Pick-up'],
  ['/u', '🚚', 'Truck (18-wheeler)', 'Kamion'], ['/v', '🚐', 'Van', 'Dodávka'], ['/j', '🚙', 'Jeep', 'Terénní auto'],
  ['/R', '🚌', 'Recreational vehicle', 'Obytný vůz'], ['/U', '🚌', 'Bus', 'Autobus'], ['/s', '🚤', 'Ship, power boat', 'Loď (motorová)'],
  ['/Y', '⛵', 'Yacht (sail)', 'Plachetnice'], ['/\'', '✈️', 'Small aircraft', 'Malé letadlo'], ['/X', '🚁', 'Helicopter', 'Vrtulník'],
  ['/O', '🎈', 'Balloon', 'Balón'], ['/;', '⛺', 'Campground, portable', 'Kemp, portable'], ['/y', '📡', 'House with yagi', 'Dům s anténou'],
  ['/r', '🗼', 'Antenna, repeater', 'Anténa, převaděč'], ['/#', '🔁', 'Digipeater', 'Digipeater'], ['I&', '🌐', 'iGate (RX and TX)', 'iGate (RX i TX)'],
  ['R&', '📥', 'iGate, receive only', 'iGate jen příjem'], ['/_', '🌦️', 'Weather station', 'Meteostanice'], ['/a', '🚑', 'Ambulance', 'Sanitka'],
  ['/f', '🚒', 'Fire truck', 'Hasiči'], ['/+', '➕', 'Red Cross', 'Červený kříž'], ['/h', '🏥', 'Hospital', 'Nemocnice'],
  ['/o', '🏢', 'EOC (emergency centre)', 'Krizové centrum'], ['/E', '👁️', 'Eyeball (event)', 'Akce, pozorování'], ['/$', '☎️', 'Phone', 'Telefon'],
];

// Material Design Icons "cog" (Apache 2.0), the icon Home Assistant uses for settings.
const COG = 'M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.67 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z';

const TEXTS = {
  en: {
    tncCard: 'TNC connection', tncKind: 'Connection', tncTcp: 'Network (KISS over TCP)', tncSerial: 'USB or serial port', tncHost: 'Address', tncPort: 'Port', tncDevice: 'Port', tncOther: 'Other (type the path)…', tncNone: 'No port found. Plug the radio in and press Search again.', tncSearch: 'Search again', tncBaud: 'Speed (baud)', tncBaudHint: 'USB radios (such as a Quansheng with the KISS TNC) ignore the speed; leave 115200.', tncDevicePh: '/dev/serial/by-id/…', tncHostRequired: 'Enter the TNC address.', tncDeviceRequired: 'Pick a port, or type its path starting with /dev/.', tncState: 'TNC', tncOnline: 'connected', tncOffline: 'not connected', tncHint: 'A port of the computer Home Assistant runs on. A radio plugged into another computer is reached over the network through a KISS TCP bridge.', settings: 'Settings', callsign: 'Callsign', ssid: 'SSID', symbol: 'Icon (APRS symbol)', comment: 'Position comment', path: 'Digipeater path', beacon: 'Send position every (minutes, 0 = off, at least 10)', beaconIs: 'Send it regularly over the internet too (APRS-IS)', beaconHint: 'By radio while Transmit is on; over the internet only with this box ticked and APRS-IS connected. The position is Home Assistant\'s home, visible to everyone on aprs.fi.', tracked: 'Callsigns to track on the map', incoming: 'Accept incoming packet connections', txdelay: 'TX delay sent to the TNC (ms, 0 = leave)', station: 'Station', aprsis: 'APRS-IS (internet)', aprsisOn: 'Connect to APRS-IS', server: 'Server', port: 'Port', passcode: 'APRS-IS password (passcode)', licenceAsk: 'APRS-IS is for licensed radio amateurs only. To switch it on, type:', licenceText: 'I hold a valid amateur radio licence', licenceRequired: 'To switch APRS-IS on, type the sentence about your licence exactly as shown.', show: 'Show', hide: 'Hide', passHint: 'Empty: computed from your callsign (the standard APRS-IS passcode). Enter your own if you were given a different one.', passOwn: 'Your own passcode is saved. Clear the field to compute it from the callsign.', radius: 'Receive packets within (km of home, 0 = none)', igateRx: 'iGate: send packets heard on the radio to APRS-IS', igateTx: 'iGate: send internet messages to local stations by radio', unsaved: 'Changes are not saved yet: press Save.', save: 'Save', saved: 'Saved; the integration restarts with the new settings.', isState: 'APRS-IS', verified: 'logged in', unverified: 'connected, not verified (check the passcode)', disconnectedIs: 'not connected', passAuto: 'computed automatically', igateHint: 'Sending to APRS-IS needs no transmitter; gating to the radio needs Transmit on and a licence.', ssidHint: 'Usual meanings of the SSID:',
    newVersion: 'A new version of APRS & Packet is installed. Reload the page to use it.', reload: 'Reload page',
    chat: 'Chat', chatHint: 'Packet chat: Enter sends the text to everyone on the frequency as it is (a UI frame to CQ, direct).', chatPh: 'Write a message', chatEmpty: 'Nothing heard yet.',
    viaIs: 'only over the internet (APRS-IS)', isLegend: '🌐 = only over the internet (APRS-IS), not heard by the radio',
    terminal: 'Terminal', monitor: 'Monitor', aprs: 'APRS', tnc: 'TNC', online: 'connected', offline: 'not connected',
    tx: 'Transmit', on: 'on', off: 'off', connectTo: 'Connect to', via: 'via', connect: 'Connect', disconnect: 'Disconnect',
    unproto: 'Unproto', unprotoTo: 'Unproto to', send: 'Send', typeLine: 'Type and press Enter',
    notConnected: 'Not connected. Enter a callsign and press Connect, or switch to unproto.',
    showIs: 'From the internet (APRS-IS)', viaRadio: 'Radio', viaNet: 'Internet', viaTitle: 'Send the message by radio or over the internet (APRS-IS)', errTxOff: 'Transmitting is off: switch it on, or send over the internet.', errIsOff: 'APRS-IS is not connected (Settings), or send by radio.',
    pause: 'Pause', clear: 'Clear', to: 'To', message: 'Message', messages: 'Messages', heard: 'Stations heard',
    lastHeard: 'Last heard', position: 'Position', comment: 'Comment', noMessages: 'No messages yet.', map: 'Map', mapOffline: 'Map tiles are not available: they come through Home Assistant (2026.11 or newer), which needs internet.', you: 'You',
    txOffHint: 'Transmitting is off. Switch it on to connect or send.', state: { pending: 'waiting for ack', acked: 'acknowledged', rejected: 'rejected', failed: 'no ack', sent: 'sent' },
  },
  cs: {
    tncCard: 'Připojení TNC', tncKind: 'Připojení', tncTcp: 'Síť (KISS přes TCP)', tncSerial: 'USB nebo sériový port', tncHost: 'Adresa', tncPort: 'Port', tncDevice: 'Port', tncOther: 'Jiný (napsat cestu)…', tncNone: 'Žádný port nenalezen. Připoj rádio a klikni na Hledat znovu.', tncSearch: 'Hledat znovu', tncBaud: 'Rychlost (baud)', tncBaudHint: 'Rádia s USB (třeba Quansheng s KISS TNC) rychlost nepoužívají, nech 115200.', tncDevicePh: '/dev/serial/by-id/…', tncHostRequired: 'Zadej adresu TNC.', tncDeviceRequired: 'Vyber port, nebo napiš jeho cestu začínající /dev/.', tncState: 'TNC', tncOnline: 'připojeno', tncOffline: 'nepřipojeno', tncHint: 'Port počítače, na kterém běží Home Assistant. Rádio připojené k jinému počítači se připojuje sítí přes KISS TCP most.', settings: 'Nastavení', callsign: 'Značka', ssid: 'SSID', symbol: 'Ikona (APRS symbol)', comment: 'Komentář k poloze', path: 'Cesta přes digipeatery', beacon: 'Posílat polohu každých (minut, 0 = ne, nejméně 10)', beaconIs: 'Posílat pravidelně i přes internet (APRS-IS)', beaconHint: 'Rádiem, když je zapnuté vysílání; přes internet jen se zaškrtnutím a připojeným APRS-IS. Poloha je domov z Home Assistantu, na aprs.fi ji uvidí každý.', tracked: 'Značky sledované na mapě', incoming: 'Přijímat příchozí packet spojení', txdelay: 'TX delay pro TNC (ms, 0 = neměnit)', station: 'Stanice', aprsis: 'APRS-IS (internet)', aprsisOn: 'Připojit se k APRS-IS', server: 'Server', port: 'Port', passcode: 'Heslo pro APRS-IS (passcode)', licenceAsk: 'APRS-IS je jen pro radioamatéry s licencí. Pro zapnutí napiš:', licenceText: 'mám platnou radioamatérskou licenci', licenceRequired: 'Pro zapnutí APRS-IS napiš větu o licenci přesně tak, jak je uvedená.', show: 'Zobrazit', hide: 'Skrýt', passHint: 'Prázdné: spočítá se z tvé značky (standardní passcode APRS-IS). Zadej vlastní, pokud ti bylo přiděleno jiné.', passOwn: 'Je uložené tvoje vlastní heslo. Smazáním pole se bude počítat ze značky.', radius: 'Přijímat pakety do (km od domova, 0 = žádné)', igateRx: 'iGate: posílat pakety slyšené rádiem do APRS-IS', igateTx: 'iGate: zprávy z internetu pro místní stanice vysílat rádiem', unsaved: 'Změny ještě nejsou uložené: klikni na Uložit.', save: 'Uložit', saved: 'Uloženo; integrace se restartuje s novým nastavením.', isState: 'APRS-IS', verified: 'přihlášeno', unverified: 'připojeno, neověřeno (zkontroluj passcode)', disconnectedIs: 'nepřipojeno', passAuto: 'spočítá se automaticky', igateHint: 'Posílání do APRS-IS nepotřebuje vysílač; brána do rádia potřebuje zapnuté vysílání a licenci.', ssidHint: 'Obvyklé významy SSID:',
    newVersion: 'Je nainstalovaná nová verze APRS & Packet. Načti stránku znovu, aby se použila.', reload: 'Načíst znovu',
    chat: 'Chat', chatHint: 'Packetový chat: Enter odešle text tak, jak je, všem na kmitočtu (UI rámec na CQ, přímo).', chatPh: 'Napiš zprávu', chatEmpty: 'Zatím nic nepřišlo.',
    viaIs: 'jen přes internet (APRS-IS)', isLegend: '🌐 = jen přes internet (APRS-IS), rádio ji neslyšelo',
    terminal: 'Terminál', monitor: 'Monitor', aprs: 'APRS', tnc: 'TNC', online: 'připojeno', offline: 'nepřipojeno',
    tx: 'Vysílání', on: 'zapnuto', off: 'vypnuto', connectTo: 'Připojit k', via: 'přes', connect: 'Připojit', disconnect: 'Odpojit',
    unproto: 'Unproto', unprotoTo: 'Unproto na', send: 'Odeslat', typeLine: 'Napiš a stiskni Enter',
    notConnected: 'Nepřipojeno. Zadej značku a stiskni Připojit, nebo přepni na unproto.',
    showIs: 'Z internetu (APRS-IS)', viaRadio: 'Rádio', viaNet: 'Internet', viaTitle: 'Poslat zprávu rádiem, nebo přes internet (APRS-IS)', errTxOff: 'Vysílání je vypnuté: zapni ho, nebo pošli přes internet.', errIsOff: 'APRS-IS není připojené (Nastavení), nebo pošli rádiem.',
    pause: 'Pozastavit', clear: 'Vymazat', to: 'Komu', message: 'Zpráva', messages: 'Zprávy', heard: 'Slyšené stanice',
    lastHeard: 'Naposledy', position: 'Poloha', comment: 'Komentář', noMessages: 'Zatím žádné zprávy.', map: 'Mapa', mapOffline: 'Mapový podklad není k dispozici: chodí přes Home Assistant (2026.11 nebo novější), který potřebuje internet.', you: 'Ty',
    txOffHint: 'Vysílání je vypnuté. Zapni ho, abys mohl připojit nebo odeslat.', state: { pending: 'čeká na potvrzení', acked: 'potvrzeno', rejected: 'odmítnuto', failed: 'nepotvrzeno', sent: 'odesláno' },
  },
};

// Texts of the screens that came with the shared engine (map, digipeater, GPS, BBS SERVER, TAK, #APRSThursday).
Object.assign(TEXTS.en, {
  bulletins: 'Bulletins', blnReach: 'From', blnAll: 'anywhere', blnWithin: 'within {km} km', blnMine: 'Mine, going out', blnHeard: 'Heard',
  blnEmpty: 'No bulletins around yet. Clubs, nets and weather services send them – by radio and, with APRS-IS, over the internet.',
  blnHidden: 'No bulletins within this distance ({n} further away or from stations whose position is not known).',
  blnNew: 'New bulletin', blnKindB: 'Bulletin (BLN0–9, news for hours)', blnKindA: 'Announcement (BLNA–Z, an event, for days)',
  blnLine: 'Number', blnGroup: 'Group (optional)', blnHours: 'Send for', blnText: 'Text', blnSend: 'Send', blnStop: 'Stop',
  blnDelete: 'Delete', blnSent: 'sent {n}×', blnNext: 'next in {m} min', blnUntil: 'until {t}', blnTimes: 'heard {n}×', blnNewTag: 'NEW',
  blnAnn: 'announcement', blnRadio: 'radio', blnNet: 'internet',
  blnAbout: 'Bulletins are APRS messages to everybody: BLN0–BLN9 news for the next few hours (a net tonight, a repeater down), BLNA–BLNZ announcements (a hamfest, a contest) kept for days, BLN1WX and the like a bulletin to a group, NWS-… weather alerts. Nobody acknowledges them, so the sender repeats them; yours go out at once, then after 1, 5 and 10 min and every 20 min (an announcement every hour) until the time is up or you stop it. A new text with the same number replaces the old one.',
  telTitle: 'Station telemetry', telVia: 'Send telemetry', telOff: 'Off', telInternet: 'Over the internet', telRadio: 'By radio', telBoth: 'By radio and internet', telMinutes: 'Every', telGraphs: 'Graphs on aprs.fi',
  telHint: 'For a digipeater or an iGate: every interval five numbers go out – packets heard by radio, digipeated, gated radio → internet and internet → radio, and the farthest station heard directly (without a digipeater) in km – and aprs.fi draws graphs of them. Over the internet it costs nothing on the air.',
  privTitle: 'Position privacy', privAmbiguity: 'How exact my position goes out', privExact: 'Exact',
  privAbout: 'Less exact – about {dist}', privMotion: 'Send speed and course', privAltitude: 'Send altitude',
  privHint: 'Less exact: the last digits of the position are left out (APRS position ambiguity), maps show only the square you are in. It applies to the beacon and the position button. EMERGENCY always goes exact, with speed and altitude – help has to find you.',
  mapSource: 'Base map', mapAuto: 'Automatic (online, else offline)', mapOnline: 'Online (OpenStreetMap)', mapImported: 'My offline maps',
  mapNoImported: 'My offline maps (none uploaded)', mapBasic: 'Basic offline map (borders, roads, towns)',
  filter: 'Filter stations', filterOn: 'Shown only', filterAll: 'Show all stations', trails: 'Trails (where stations went in the last half hour)',
  filter_weather: 'Weather stations only', filter_moving: 'Moving only (moved in the last 10 min)', filter_repeater: 'Repeaters only (with their frequency)',
  filter_road: 'Road incidents only (crashes, work zones, floods…)', filter_weather_short: 'weather', filter_moving_short: 'moving',
  filter_repeater_short: 'repeaters', filter_road_short: 'road incidents',
  beaconIs: 'Send over the internet too (APRS-IS): my position (button and regular) and messages',
  beaconHint: 'By radio while Transmit is on. With this ticked, your position and messages also go to APRS-IS (when connected); with Transmit off, over the internet only. The position is Home Assistant\'s home (or the USB GPS), visible to everyone on aprs.fi.',
  digi: 'Digipeater', digiMode: 'Repeat packets', digiOff: 'Off', digiFillin: 'Fill-in (WIDE1-1 only)', digiWide: 'Wide (WIDEn-N)', digiHops: 'Most hops a path may ask for', digiAliases: 'Also repeat for (aliases, e.g. RELAY)',
  digiHint: 'Only with Transmit on. A fill-in digipeater helps nearby stations reach a big digi; a wide one is for a well-placed station agreed with others.',
  gps: 'GPS', gpsSource: 'My position from', gpsHome: 'Home Assistant\'s home', gpsUsb: 'USB GPS module (NMEA)', gpsDevice: 'GPS port', gpsBaud: 'Speed', gpsAuto: 'Automatic',
  gpsHint: 'Cheap USB GPS modules (u-blox, VK-172…) send NMEA at 9600 or 4800 Bd. With a fix, the map and the position use the GPS (and its altitude); without one, Home Assistant\'s home.',
  gpsState: 'GPS', gpsFix: 'fix', gpsNoFix: 'no fix', gpsSats: 'satellites',
  modes: 'BBS SERVER and TAK', modeHint: 'Each turns the integration into something else on another frequency: everything of APRS (APRS-IS, iGate, messages, terminal, chat) stops until it is switched off.',
  bbsSsid: 'BBS SERVER SSID', takCallsign: 'TAK callsign (empty: your callsign)', takTeam: 'Team (colour)', takRole: 'Role', takInterval: 'Send my TAK position every (minutes, 0 = only with the button)',
  maps: 'Offline maps', mapsHint: 'Your own raster maps for when there is no internet: MBTiles, PMTiles, RMaps .sqlitedb, a ZIP of tiles (z/x/y), or a .zip/.7z with such files. Vector maps (.pbf) cannot be shown. They are kept in', mapsUpload: 'Upload a map…', mapsUploading: 'Uploading…', mapsNone: 'No offline maps yet.', mapsRemove: 'Remove', mapsRescan: 'Look again', mapsFailed: 'Cannot be shown',
  mapErr: { vector: 'a vector map (not supported)', unknown: 'not a map file', empty: 'no maps inside', no7z: '7-Zip is not installed', read: 'cannot be read' },
  thursday: 'Thursday', thAbout: 'Every Thursday (UTC) radio amateurs all over the world send a short message to the HOTG group. ANSRVR passes it on to everyone who wrote to the group in the last 12 hours, and sends you theirs.',
  thRf: 'By radio, replies reach you only through an iGate that gates internet messages to the radio; over the internet (APRS-IS) it always works.',
  thPh: 'Your message to the group (e.g. where you are, what rig)', thSend: 'Send to HOTG', thLeave: 'Leave the group', thEmpty: 'No HOTG messages yet.',
  thMember: 'You are in the HOTG group until', thNotMember: 'Not in the HOTG group: your first message adds you to it', thWait: 'Next message possible in', thMap: 'Map and check-ins (aprs.to)',
  thRunning: 'Running now (Thursday UTC)', thNext: 'Next one: Thursday 00:00 UTC',
  bbs: 'BBS', bbsOn: 'BBS SERVER on', bbsOff: 'BBS SERVER is off. Switching it on turns the integration into a packet BBS: everything else (APRS, APRS-IS, iGate, position, messages, terminal, chat) stops until you switch it off.',
  bbsRunning: 'Running as', bbsConnected: 'Connected', bbsNobody: 'Nobody connected.', bbsMessages: 'Messages', bbsNoMessages: 'No messages yet.', bbsLog: 'Log', bbsDelete: 'Delete',
  bbsSettings: 'BBS settings', bbsSessions: 'Clients at the same time', bbsIdle: 'Disconnect after inactivity (seconds)', bbsTx: 'Maximum TX time per connection (minutes, 0 = no limit)',
  bbsMax: 'Maximum stored messages (0 = no limit)', bbsWelcome: 'Welcome message ({name}, {bbs}, {new}… are filled in)', bbsMore: 'More options (access, beacon, how long messages are kept) are in bbs.toml in the folder', bbsReload: 'Reload bbs.toml',
  bbsTxNeeded: 'Switch Transmit on, otherwise the BBS cannot answer.', bbsConfirmTitle: 'Switch BBS SERVER on?',
  bbsConfirmAsk: 'While the BBS runs, everything else is off. Tune the radio to a packet channel (e.g. 144.8125-144.9625 MHz), never to the APRS frequency 144.800. To switch it on, type:',
  bbsSentence: 'BBS SERVER must have another frequency than APRS',
  tak: 'TAK', takOn: 'TAK on', takOff: 'TAK is off. Switching it on turns the integration into a TAK station over the radio (ATAK-compatible positions and GeoChat): everything else stops until you switch it off.',
  takRunning: 'Running as', takStations: 'Stations', takNoStations: 'No TAK stations heard yet.', takChat: 'GeoChat', takEverybody: 'Everybody', takSendPos: 'Send my position', takNoChat: 'No messages yet.',
  takConfirmTitle: 'Switch TAK on?', takConfirmAsk: 'While TAK runs, everything else is off. Tune the radio to a channel agreed with your team, never to the APRS frequency 144.800. Amateur radio: nothing is encrypted. To switch it on, type:',
  takSentence: 'TAK must have another frequency than APRS', sentenceWrong: 'Type the sentence exactly as shown.', switchOn: 'Switch on', cancel: 'Cancel',
  exclusive: 'is on: APRS, messages, terminal and chat are off.', switchOff: 'Switch off', digipeated: 'digipeated',
});
Object.assign(TEXTS.cs, {
  bulletins: 'Nástěnka', blnReach: 'Odkud', blnAll: 'odkudkoli', blnWithin: 'do {km} km', blnMine: 'Moje, vysílají se', blnHeard: 'Zachycené',
  blnEmpty: 'Zatím tu nejsou žádné bulletiny. Posílají je kluby, kroužky a meteoslužby – chodí rádiem a s APRS-IS i z internetu.',
  blnHidden: 'V této vzdálenosti nejsou žádné bulletiny (dalších {n} je dál nebo od stanic s neznámou polohou).',
  blnNew: 'Nový bulletin', blnKindB: 'Bulletin (BLN0–9, zprávy na pár hodin)', blnKindA: 'Oznámení (BLNA–Z, akce, na dny)',
  blnLine: 'Číslo', blnGroup: 'Skupina (nepovinné)', blnHours: 'Vysílat', blnText: 'Text', blnSend: 'Odeslat', blnStop: 'Zastavit',
  blnDelete: 'Smazat', blnSent: 'odesláno {n}×', blnNext: 'další za {m} min', blnUntil: 'do {t}', blnTimes: 'slyšeno {n}×', blnNewTag: 'NOVÉ',
  blnAnn: 'oznámení', blnRadio: 'rádiem', blnNet: 'internet',
  blnAbout: 'Bulletiny jsou APRS zprávy pro všechny: BLN0–BLN9 novinky na pár hodin (dnešní kroužek, nefunkční převaděč), BLNA–BLNZ oznámení akcí (setkání, závod) platná i několik dní, BLN1WX a podobné bulletin pro skupinu, NWS-… meteorologické výstrahy. Nikdo je nepotvrzuje, proto je odesílatel opakuje; tvoje odejdou hned, pak po 1, 5 a 10 min a dál každých 20 min (oznámení jednou za hodinu), dokud čas nevyprší nebo je nezastavíš. Nový text se stejným číslem nahradí starý.',
  telTitle: 'Telemetrie stanice', telVia: 'Posílat telemetrii', telOff: 'Vypnuto', telInternet: 'Internetem', telRadio: 'Rádiem', telBoth: 'Rádiem i internetem', telMinutes: 'Každých', telGraphs: 'Grafy na aprs.fi',
  telHint: 'Pro digipeater nebo iGate: každý interval odejde pět čísel – pakety přijaté rádiem, přeposlané digipeaterem, poslané z rádia na internet a z internetu do rádia a nejvzdálenější stanice slyšená přímo (bez digipeateru) v km – a aprs.fi z nich kreslí grafy. Přes internet to v éteru nic nestojí.',
  privTitle: 'Soukromí polohy', privAmbiguity: 'Jak přesně posílat moji polohu', privExact: 'Přesně',
  privAbout: 'Méně přesně – asi {dist}', privMotion: 'Posílat rychlost a směr', privAltitude: 'Posílat nadmořskou výšku',
  privHint: 'Méně přesně: poslední číslice polohy se vynechají (APRS position ambiguity), mapy ukážou jen čtverec, ve kterém jsi. Platí pro maják i tlačítko polohy. NOUZE jde vždy přesně, s rychlostí i výškou – pomoc tě musí najít.',
  mapSource: 'Mapový podklad', mapAuto: 'Automaticky (online, jinak offline)', mapOnline: 'Online (OpenStreetMap)', mapImported: 'Moje offline mapy',
  mapNoImported: 'Moje offline mapy (žádné nahrané)', mapBasic: 'Základní offline mapa (hranice, silnice, města)',
  filter: 'Filtr stanic', filterOn: 'Zobrazeno jen', filterAll: 'Zobrazit všechny stanice', trails: 'Ocásky (kudy stanice jely za poslední půlhodinu)',
  filter_weather: 'Jen meteostanice', filter_moving: 'Jen pohybující se (pohnuly se za posledních 10 min)', filter_repeater: 'Jen převaděče (s jejich kmitočtem)',
  filter_road: 'Jen dopravní problémy (nehody, práce na silnici, povodně…)', filter_weather_short: 'meteostanice', filter_moving_short: 'pohybující se',
  filter_repeater_short: 'převaděče', filter_road_short: 'dopravní problémy',
  beaconIs: 'Posílat i přes internet (APRS-IS): moji polohu (tlačítkem i pravidelně) a zprávy',
  beaconHint: 'Rádiem, když je zapnuté vysílání. Se zaškrtnutím jde poloha i zprávy také do APRS-IS (když je připojené); s vypnutým vysíláním jen přes internet. Poloha je domov z Home Assistantu (nebo USB GPS), na aprs.fi ji uvidí každý.',
  digi: 'Digipeater', digiMode: 'Opakovat pakety', digiOff: 'Vypnuto', digiFillin: 'Fill-in (jen WIDE1-1)', digiWide: 'Široký (WIDEn-N)', digiHops: 'Nejvíc skoků, o které si cesta může říct', digiAliases: 'Opakovat i pro (aliasy, např. RELAY)',
  digiHint: 'Jen se zapnutým vysíláním. Fill-in digipeater pomáhá stanicím v okolí dosáhnout na velký digi; široký je pro dobře umístěnou stanici domluvenou s ostatními.',
  gps: 'GPS', gpsSource: 'Moje poloha z', gpsHome: 'Domov z Home Assistantu', gpsUsb: 'USB GPS modul (NMEA)', gpsDevice: 'Port GPS', gpsBaud: 'Rychlost', gpsAuto: 'Automaticky',
  gpsHint: 'Levné USB GPS moduly (u-blox, VK-172…) posílají NMEA rychlostí 9600 nebo 4800 Bd. S fixem používá mapa i poloha GPS (i výšku), bez fixu domov z Home Assistantu.',
  gpsState: 'GPS', gpsFix: 'fix', gpsNoFix: 'bez fixu', gpsSats: 'satelitů',
  modes: 'BBS SERVER a TAK', modeHint: 'Každý z nich udělá z integrace něco jiného na jiném kmitočtu: vše z APRS (APRS-IS, iGate, zprávy, terminál, chat) stojí, dokud se nevypne.',
  bbsSsid: 'SSID pro BBS SERVER', takCallsign: 'Volací znak v TAK (prázdné: tvoje značka)', takTeam: 'Tým (barva)', takRole: 'Role', takInterval: 'Posílat moji TAK polohu každých (minut, 0 = jen tlačítkem)',
  maps: 'Offline mapy', mapsHint: 'Vlastní rastrové mapy pro chvíle bez internetu: MBTiles, PMTiles, RMaps .sqlitedb, ZIP dlaždic (z/x/y), nebo .zip/.7z s takovými soubory. Vektorové mapy (.pbf) zobrazit neumí. Ukládají se do', mapsUpload: 'Nahrát mapu…', mapsUploading: 'Nahrávám…', mapsNone: 'Zatím žádné offline mapy.', mapsRemove: 'Odebrat', mapsRescan: 'Hledat znovu', mapsFailed: 'Nejde zobrazit',
  mapErr: { vector: 'vektorová mapa (nepodporováno)', unknown: 'není to mapa', empty: 'uvnitř nejsou mapy', no7z: '7-Zip není nainstalovaný', read: 'nejde přečíst' },
  thursday: 'Čtvrtek', thAbout: 'Každý čtvrtek (UTC) posílají radioamatéři z celého světa krátkou zprávu do skupiny HOTG. ANSRVR ji předá všem, kdo do skupiny psali za posledních 12 hodin, a tobě pošle ty jejich.',
  thRf: 'Rádiem k tobě odpovědi dojdou jen přes iGate, který posílá zprávy z internetu do rádia; přes internet (APRS-IS) to funguje vždy.',
  thPh: 'Tvoje zpráva pro skupinu (např. odkud vysíláš, s čím)', thSend: 'Poslat do HOTG', thLeave: 'Odhlásit ze skupiny', thEmpty: 'Zatím žádné zprávy HOTG.',
  thMember: 'Jsi ve skupině HOTG do', thNotMember: 'Nejsi ve skupině HOTG: první zpráva tě do ní přidá', thWait: 'Další zprávu můžeš poslat za', thMap: 'Mapa a zapojení (aprs.to)',
  thRunning: 'Právě probíhá (čtvrtek UTC)', thNext: 'Další: čtvrtek 00:00 UTC',
  bbs: 'BBS', bbsOn: 'BBS SERVER zapnutý', bbsOff: 'BBS SERVER je vypnutý. Po zapnutí se z integrace stane packet BBS: všechno ostatní (APRS, APRS-IS, iGate, poloha, zprávy, terminál, chat) přestane fungovat, dokud ho nevypneš.',
  bbsRunning: 'Běží jako', bbsConnected: 'Připojení', bbsNobody: 'Nikdo není připojený.', bbsMessages: 'Zprávy', bbsNoMessages: 'Zatím žádné zprávy.', bbsLog: 'Log', bbsDelete: 'Smazat',
  bbsSettings: 'Nastavení BBS', bbsSessions: 'Počet klientů najednou', bbsIdle: 'Odpojit po nečinnosti (sekundy)', bbsTx: 'Maximální TX čas na jedno spojení (minuty, 0 = bez omezení)',
  bbsMax: 'Maximum uložených zpráv (0 = bez omezení)', bbsWelcome: 'Uvítací zpráva ({name}, {bbs}, {new}… se doplní)', bbsMore: 'Další volby (přístup, beacon, jak dlouho držet zprávy) jsou v bbs.toml ve složce', bbsReload: 'Načíst bbs.toml znovu',
  bbsTxNeeded: 'Zapni Vysílání, jinak BBS nemůže odpovídat.', bbsConfirmTitle: 'Zapnout BBS SERVER?',
  bbsConfirmAsk: 'Dokud BBS běží, je všechno ostatní vypnuté. Nalaď rádio na packetový kanál (např. 144.8125-144.9625 MHz), nikdy ne na APRS kmitočet 144.800. Pro zapnutí napiš:',
  bbsSentence: 'BBS SERVER musí mít jinou frekvenci než APRS',
  tak: 'TAK', takOn: 'TAK zapnutý', takOff: 'TAK je vypnutý. Po zapnutí se z integrace stane TAK stanice přes rádio (polohy a GeoChat kompatibilní s ATAK): všechno ostatní přestane fungovat, dokud ho nevypneš.',
  takRunning: 'Běží jako', takStations: 'Stanice', takNoStations: 'Zatím žádné TAK stanice.', takChat: 'GeoChat', takEverybody: 'Všem', takSendPos: 'Poslat moji polohu', takNoChat: 'Zatím žádné zprávy.',
  takConfirmTitle: 'Zapnout TAK?', takConfirmAsk: 'Dokud TAK běží, je všechno ostatní vypnuté. Nalaď rádio na kanál domluvený s týmem, nikdy ne na APRS kmitočet 144.800. Radioamatérský provoz: nic se nešifruje. Pro zapnutí napiš:',
  takSentence: 'TAK musí mít jinou frekvenci než APRS', sentenceWrong: 'Napiš větu přesně tak, jak je uvedená.', switchOn: 'Zapnout', cancel: 'Zrušit',
  exclusive: 'je zapnutý: APRS, zprávy, terminál a chat jsou vypnuté.', switchOff: 'Vypnout', digipeated: 'digipeatováno',
});

/** APRS weather (aprslib units: °C, m/s, mm, hPa, %) as a short line. */
// Spot and Services in the APRS tab: the same texts as the app (aprs-kiss-app i18n)
TEXTS.en.app = {"spot_button": "Spot", "spot_title": "Self-spot an activation (SOTA, POTA, WWFF, GMA…)", "spot_program": "Program", "spot_gateway": "Gateway", "spot_ref": "Reference", "spot_freq": "Frequency (MHz)", "spot_mode": "Mode", "spot_comment": "Comment (optional)", "spot_test": "Test only", "spot_hint_aprs2sota": "APRS2SOTA posts the spot on SOTAwatch. Register your callsign with its operator first (sotaspots.co.uk). The answer (Spotted / Error) comes as a message in its conversation. A test spot is posted marked as TEST.", "spot_hint_apspot": "APSPOT posts the spot on pota.app, SOTAwatch or ParksnPeaks; you need an account there. The answer comes as a message in its conversation. A test spot is only answered, not posted.", "spot_hint_camilla": "Camilla (DL0QW-12, gma.rocks) posts the spot on GMA, and a SOTA summit on SOTAwatch too: summits, castles (WCA), WWFF, islands (IOTA), lighthouses. For registered GMA users only (free at gma.rocks). It answers with a message in its conversation. A test spot is posted marked as TEST.", "spot_send": "Send spot", "spot_bad_ref": "The reference does not look right, e.g. {example}", "spot_bad_freq": "Frequency in MHz, e.g. 7.032 or 145.500", "spot_bad_program": "Pick a program", "spot_lighthouse": "Lighthouse", "services_button": "Services", "services_title": "Services on APRS", "services_hint": "Each one answers a message: pick a command, it goes to the message field, send it. The answer comes back in that conversation.", "svc_type": "Type…", "svc_find": "Where a station was last heard: send its callsign. Answers the time, the iGate, the distance and the locator.", "svc_repeat": "Repeaters nearest to your last position beacon.", "svc_wxnow": "Weather from the weather station nearest to you.", "svc_utc": "The exact time (UTC).", "svc_sat": "Satellite passes over you (satpass iss, satpass so-50), sunrise and sunset, where you are.", "svc_mail": "E-mail from the radio: EMAIL address text, as many messages as needed, then SEND. 5 an hour."};
TEXTS.cs.app = {"spot_button": "Spot", "spot_title": "Ohlásit aktivaci (SOTA, POTA, WWFF, GMA…)", "spot_program": "Program", "spot_gateway": "Brána", "spot_ref": "Reference", "spot_freq": "Kmitočet (MHz)", "spot_mode": "Druh provozu", "spot_comment": "Poznámka (nepovinná)", "spot_test": "Jen zkouška", "spot_hint_aprs2sota": "APRS2SOTA vystaví spot na SOTAwatch. Značku je potřeba nejdřív zaregistrovat u jejího provozovatele (sotaspots.co.uk). Odpověď (Spotted / Error) přijde jako zpráva v její konverzaci. Zkušební spot se vystaví označený jako TEST.", "spot_hint_apspot": "APSPOT vystaví spot na pota.app, SOTAwatch nebo ParksnPeaks; je potřeba tam mít účet. Odpověď přijde jako zpráva v její konverzaci. Na zkušební spot jen odpoví, nic nevystaví.", "spot_hint_camilla": "Camilla (DL0QW-12, gma.rocks) vystaví spot na GMA a SOTA vrchol i na SOTAwatch: vrcholy, hrady (WCA), WWFF, ostrovy (IOTA), majáky. Jen pro registrované uživatele GMA (zdarma na gma.rocks). Odpoví zprávou v její konverzaci. Zkušební spot se vystaví označený jako TEST.", "spot_send": "Odeslat spot", "spot_bad_ref": "Reference nevypadá správně, např. {example}", "spot_bad_freq": "Kmitočet v MHz, např. 7.032 nebo 145.500", "spot_bad_program": "Vyber program", "spot_lighthouse": "Maják", "services_button": "Služby", "services_title": "Služby na APRS", "services_hint": "Každá odpoví na zprávu: vyber příkaz, vloží se do pole zprávy, pošli ho. Odpověď přijde do té konverzace.", "svc_type": "Napsat…", "svc_find": "Kde byla stanice naposledy slyšet: pošli její značku. Odpoví čas, iGate, vzdálenost a lokátor.", "svc_repeat": "Převaděče nejblíž tvé poslední poloze.", "svc_wxnow": "Počasí z meteostanice nejblíž tobě.", "svc_utc": "Přesný čas (UTC).", "svc_sat": "Přelety satelitů nad tebou (satpass iss, satpass so-50), východ a západ slunce, kde jsi.", "svc_mail": "E-mail z rádia: EMAIL adresa text, klidně víc zpráv, nakonec SEND. 5 za hodinu."};
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (m, k) => (values[k] ?? m));

const wxText = (w) => {
  if (!w) return '';
  const parts = [];
  if (w.temperature != null) parts.push(`${w.temperature.toFixed(1)} °C`);
  if (w.humidity != null) parts.push(`${w.humidity} %`);
  if (w.pressure != null) parts.push(`${w.pressure.toFixed(1)} hPa`);
  if (w.wind_speed != null) parts.push(`${(w.wind_speed * 3.6).toFixed(0)} km/h${w.wind_direction != null ? ' ' + w.wind_direction + '°' : ''}${w.wind_gust != null ? ' (' + (w.wind_gust * 3.6).toFixed(0) + ')' : ''}`);
  if (w.rain_1h != null) parts.push(`☔ ${w.rain_1h.toFixed(1)} mm/h`);
  if (w.luminosity != null) parts.push(`☀ ${w.luminosity} W/m²`);
  return parts.join(' · ');
};

// TAK teams and roles (core/tak.py)
const TAK_TEAMS = ['White', 'Yellow', 'Orange', 'Magenta', 'Red', 'Maroon', 'Purple', 'Dark Blue', 'Blue', 'Cyan', 'Teal', 'Green', 'Dark Green', 'Brown'];
const TAK_ROLES = ['Team Member', 'Team Lead', 'HQ', 'Sniper', 'Medic', 'Forward Observer', 'RTO', 'K9'];

const isIsLine = (line) => / (<<|>>) \[IS\] /.test(line);  // a monitor line from or to APRS-IS
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const time = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

class AprsKissPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._tab = localStorage.getItem('aprs-kiss-tab') || 'terminal';
    this._state = null;
    this._remote = localStorage.getItem('aprs-kiss-remote') || '';
    this._path = localStorage.getItem('aprs-kiss-path') || '';
    this._unproto = false;
    this._unprotoTo = 'CQ';
    this._paused = false;
    this._monIs = localStorage.getItem('aprs-kiss-mon-is') !== '0';  // APRS-IS lines in the monitor
    this._error = '';
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._t = TEXTS[(hass.language || 'en').startsWith('cs') ? 'cs' : 'en'];
    if (first) this._init();
  }

  set narrow(v) {
    this._narrow = v;
    this._fitViewport();
    if (this._state) this._renderHeader();
  }

  // Same approach as MeshCore Chattx: while the on-screen keyboard is open, pin the
  // whole panel to the visible part of the screen, so the header with Home Assistant's
  // menu button and the tabs stay on top and the input sits right above the keyboard.
  _fitViewport() {
    const vv = window.visualViewport;
    if (!vv) return;
    if (vv.scale > 1.01) { this._unpin(); return; }   // pinch zoom, not the keyboard
    if (Math.abs(vv.width - (this._vvWidth || 0)) > 1) { this._vvWidth = vv.width; this._vvFull = vv.height; }
    this._vvFull = Math.max(this._vvFull || 0, vv.height);
    const keyboard = this._vvFull - vv.height >= 120;
    // On a phone the panel is always pinned to the screen: the page itself never scrolls,
    // only the content under the header does, so the header can't be scrolled away.
    if (!keyboard && !this._narrow) { this._unpin(); return; }
    this._pinned = true;
    Object.assign(this.style, { position: 'fixed', top: `${vv.offsetTop}px`, left: '0', width: '100%', height: `${vv.height}px` });
    this.shadowRoot.querySelector('.page')?.classList.toggle('kbd', keyboard && !!this._narrow);
  }

  _unpin() {
    if (!this._pinned) return;
    this._pinned = false;
    for (const k of ['position', 'top', 'left', 'width', 'height']) this.style.removeProperty(k);
    this.shadowRoot.querySelector('.page')?.classList.remove('kbd');
    window.scrollTo(0, 0);
  }

  connectedCallback() {
    if (!this._onVv && window.visualViewport) {
      this._onVv = () => this._fitViewport();
      window.visualViewport.addEventListener('resize', this._onVv);
      window.visualViewport.addEventListener('scroll', this._onVv);
      this._fitViewport();
    }
    if (this._hass && this.shadowRoot.querySelector('main')) this._attach();
  }

  // Like MeshCore Chattx: after an update Home Assistant serves the panel under a new
  // ?v= (the file's time); a page that still runs the old copy offers a reload.
  async _checkForUpdate() {
    try {
      const panels = await this._hass.callWS({ type: 'get_panels' });
      const url = panels?.['aprs-packet']?.config?._panel_custom?.module_url;
      const served = url && new URL(url, location.href).searchParams.get('v');
      const mine = new URL(import.meta.url).searchParams.get('v');
      this._updateAvailable = !!(served && mine && served !== mine);
    } catch (err) {
      return;
    }
    this._renderUpdate();
  }

  _renderUpdate() {
    const box = this.shadowRoot.querySelector('.update');
    if (!box) return;
    box.hidden = !this._updateAvailable;
    if (this._updateAvailable && !box.firstChild) {
      box.innerHTML = `<span>${this._t.newVersion}</span><button type="button">${this._t.reload}</button>`;
      box.querySelector('button').addEventListener('click', () => window.location.reload());
    }
  }

  async _init() {
    this._renderShell();
    await this._attach();
  }

  // Listeners while the panel is on screen; Home Assistant detaches the panel when
  // another one is opened and attaches the same element again on the way back.
  async _attach() {
    if (this._attached) return;
    this._attached = true;
    this._onReady = () => { this._load(); this._checkForUpdate(); };
    this._hass.connection.addEventListener?.('ready', this._onReady);
    this._onVisible = () => { if (document.visibilityState === 'visible') this._checkForUpdate(); };
    document.addEventListener('visibilitychange', this._onVisible);
    this._checkForUpdate();
    await this._load();
    const unsub = await this._hass.connection.subscribeEvents((e) => this._onEvent(e.data), 'aprs_kiss_terminal');
    const unsubState = await this._hass.connection.subscribeEvents(() => this._loadSoon(), 'state_changed');
    if (!this._attached) { unsub(); unsubState(); return; }  // detached meanwhile
    this._unsub = unsub;
    this._unsubState = unsubState;
  }

  disconnectedCallback() {
    this._attached = false;
    if (this._onVisible) document.removeEventListener('visibilitychange', this._onVisible);
    if (this._onReady) this._hass?.connection.removeEventListener?.('ready', this._onReady);
    this._onVisible = this._onReady = null;
    if (this._onVv) {
      window.visualViewport.removeEventListener('resize', this._onVv);
      window.visualViewport.removeEventListener('scroll', this._onVv);
      this._onVv = null;
      this._unpin();
    }
    this._unsub?.();
    this._unsubState?.();
    this._unsub = this._unsubState = null;
  }

  async _ws(msg) {
    this._error = '';
    try {
      return await this._hass.callWS({ ...msg, entry_id: this._state?.entry_id });
    } catch (err) {
      this._error = err.message || String(err);
      this._render();
      return null;
    }
  }

  async _load() {
    try {
      this._state = await this._hass.callWS({ type: 'aprs_kiss/state' });
      this._extra = await this._hass.callWS({ type: 'aprs_kiss/extra', entry_id: this._state.entry_id });
    } catch (err) {
      this._error = err.message || String(err);
    }
    if (this._extra?.mode && !['monitor', 'settings', this._extra.mode].includes(this._tab)) this._tab = this._extra.mode;
    this._render();
  }

  async _loadExtra() {
    try {
      this._extra = await this._hass.callWS({ type: 'aprs_kiss/extra', entry_id: this._state.entry_id });
    } catch { /* keep the last */ }
  }

  _extraSoon(then) {
    clearTimeout(this._extraTimer);
    this._extraTimer = setTimeout(async () => { await this._loadExtra(); then?.(); }, 800);
  }

  _loadSoon() {
    clearTimeout(this._loadTimer);
    this._loadTimer = setTimeout(() => this._loadStatus(), 1500);
  }

  async _loadStatus() {
    if (!this._state) return;
    try {
      const s = await this._hass.callWS({ type: 'aprs_kiss/state', entry_id: this._state.entry_id });
      Object.assign(this._state, { tnc_connected: s.tnc_connected, tx_enabled: s.tx_enabled, sessions: s.sessions, messages: s.messages, heard: s.heard });
      await this._loadExtra();
      this._renderHeader();
      if (this._tab === 'aprs') this._updateAprs();
      else if (['bbs', 'tak', 'thursday', 'bulletins'].includes(this._tab)) this._refreshTab?.();
    } catch { /* keep the last state */ }
  }

  _onEvent(d) {
    if (!this._state || d.entry_id !== this._state.entry_id) return;
    if (d.kind === 'monitor') {
      this._state.monitor.push(d.line);
      if (this._state.monitor.length > 500) this._state.monitor.shift();
      if (!isIsLine(d.line)) {  // radio lines kept apart, so a busy APRS-IS feed cannot push them out
        (this._state.monitor_rf ||= []).push(d.line);
        if (this._state.monitor_rf.length > 500) this._state.monitor_rf.shift();
      }
      if (this._tab === 'monitor' && !this._paused) this._appendMonitor(d.line);
    } else if (d.kind === 'terminal') {
      this._state.terminal.push(d.entry);
      if (this._tab === 'terminal' && d.entry.remote === this._remoteKey()) this._appendTerminal(d.entry);
    } else if (d.kind === 'state') {
      if (d.state === 'disconnected') delete this._state.sessions[d.remote];
      else this._state.sessions[d.remote] = d.state;
      this._renderHeader();
      if (this._tab === 'terminal') this._renderTerminalControls();
    } else if (d.kind === 'chat') {
      this._state.chat = this._state.chat || [];
      this._state.chat.push(d.entry);
      if (this._tab === 'chat') this._appendChat(d.entry);
    } else if (d.kind === 'aprs_message') {
      this._state.messages.push(d.message);
      if (this._tab === 'aprs') this._render();
    } else if (['thursday', 'tak', 'bbs', 'gps', 'bulletin'].includes(d.kind)) {
      this._extraSoon(() => {
        if (this._tab === d.kind || (d.kind === 'gps' && this._tab === 'aprs') || (d.kind === 'bulletin' && this._tab === 'bulletins')) this._refreshTab?.();
      });
    }
  }

  _remoteKey() {
    return this._remote.trim().toUpperCase().replace(/-0$/, '');
  }

  _renderShell() {
    this.shadowRoot.innerHTML = `
      <link rel="stylesheet" href="${LEAFLET_CSS}">
      <style>
        :host { display: block; height: 100%; overscroll-behavior: none; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
        .page { display: flex; flex-direction: column; height: 100%; min-height: 0; max-width: 1100px; margin: 0 auto; box-sizing: border-box; padding: 12px 16px; gap: 10px; }
        /* Like a Home Assistant dashboard: the header with the menu button and the tabs stay on top while the rest scrolls. */
        .top { position: sticky; top: 0; z-index: 10; display: flex; flex-direction: column; gap: 10px; flex-shrink: 0;
               margin: -12px -16px 0; padding: calc(12px + env(safe-area-inset-top, 0px)) 16px 0; background: var(--primary-background-color); }
        .update { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 10px; background: var(--warning-color, #ff9800); color: #000; font-size: 14px; }
        [hidden] { display: none !important; }  /* also over display: flex of .field and others */ .update span { flex: 1; }
        .update button { padding: 6px 12px; border: none; border-radius: 6px; background: rgba(0, 0, 0, 0.8); color: #fff; font: inherit; cursor: pointer; white-space: nowrap; }
        header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
        h1 { font-size: 20px; margin: 0 8px 0 0; font-weight: 500; }
        .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 14px; font-size: 13px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
        .dot { width: 9px; height: 9px; border-radius: 50%; background: #9e9e9e; }
        .dot.ok { background: #43a047; } .dot.bad { background: #e53935; }
        button.chip { cursor: pointer; color: inherit; font: inherit; font-size: 13px; }
        button.chip.tx-on { background: rgba(229, 57, 53, 0.15); border-color: #e53935; }
        nav { display: flex; gap: 4px; border-bottom: 1px solid var(--divider-color); }
        nav button { background: none; border: none; padding: 8px 14px; font: inherit; color: var(--secondary-text-color); cursor: pointer; border-bottom: 2px solid transparent; }
        nav button.gear { margin-left: auto; display: inline-flex; align-items: center; padding: 6px 12px; }
        nav button.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
        main { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
        .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
        input, select { font: inherit; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
        input.call { width: 120px; text-transform: uppercase; } input.path { width: 160px; text-transform: uppercase; }
        button.btn { font: inherit; padding: 7px 14px; border-radius: 8px; border: none; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
        label.btn { display: inline-block; font: inherit; padding: 7px 14px; border-radius: 8px; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
        button.btn.save.dirty { box-shadow: 0 0 0 3px rgba(255, 152, 0, 0.6); }
        .warn { color: var(--warning-color, #ff9800); }
        button.btn.secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
        button.btn:disabled { opacity: 0.5; cursor: default; }
        pre { flex: 1; min-height: 200px; margin: 0; overflow: auto; padding: 10px 12px; border-radius: 10px; background: var(--code-editor-background-color, var(--card-background-color)); color: var(--primary-text-color); border: 1px solid var(--divider-color); font: 13px/1.45 ui-monospace, 'DejaVu Sans Mono', Menlo, Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
        .chatlog { flex: 1; min-height: 200px; overflow: auto; padding: 8px 10px; border-radius: 10px; background: var(--card-background-color); border: 1px solid var(--divider-color); font-size: 14px; }
        .chatline { padding: 3px 0; line-height: 1.4; word-break: break-word; }
        .chatline .t { color: var(--secondary-text-color); font-size: 12px; margin-right: 6px; font-variant-numeric: tabular-nums; }
        .chatline .c { font-weight: 600; margin-right: 4px; }
        .chatline.out .c { color: var(--primary-color); }
        .chatline .to { color: var(--secondary-text-color); font-size: 12px; margin-right: 4px; }
        .form { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); gap: 12px; overflow: auto; padding-bottom: 12px; }
        .form .card { display: flex; flex-direction: column; gap: 10px; overflow: visible; min-height: auto; min-width: 0; }
        .form input:not([type=checkbox]), .form select { width: 100%; min-width: 0; box-sizing: border-box; } .form .callrow input { width: auto; } .form .callrow select { width: 90px; flex: none; }
        .form { align-content: start; } .callrow input.f-pass { text-transform: none; } .form .callrow select.f-device { flex: 1; width: auto; min-width: 0; }
        .field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
        .field input, .field select { color: var(--primary-text-color); }
        .field.check { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); font-size: 14px; }
        .callrow { display: flex; gap: 8px; } .callrow input { flex: 1; text-transform: uppercase; } .callrow select { width: 90px; }
        .ok { color: var(--success-color, #43a047); font-size: 13px; }
        pre .tx { color: var(--primary-color); } pre .st { color: var(--warning-color, #ef6c00); font-style: italic; } pre .out { color: var(--success-color, #2e7d32); }
        .line { display: flex; gap: 8px; } .line input { flex: 1; font-family: ui-monospace, monospace; }
        .hint { font-size: 13px; color: var(--secondary-text-color); }
        .tool { display: flex; flex-direction: column; gap: 10px; } .tool h2 { margin: 0; }
        .tool label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
        .tool label.check { flex-direction: row; align-items: center; } .tool label.grow { flex: 1; } .tool label.grow input { width: 100%; box-sizing: border-box; }
        .tool .svc { display: flex; flex-direction: column; gap: 4px; } .tool .svc .row { gap: 6px; }
        .mono { font-family: ui-monospace, 'DejaVu Sans Mono', Menlo, Consolas, monospace; font-size: 13px; word-break: break-word; }
        .error { color: var(--error-color, #db4437); font-size: 13px; }
        .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
        @media (max-width: 800px) { .cols { grid-template-columns: 1fr; } }
        .card { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 12px; padding: 10px 12px; overflow: auto; min-height: 0; }
        .card h2 { font-size: 15px; margin: 0 0 8px; font-weight: 500; }
        .msg { padding: 6px 8px; border-radius: 8px; margin-bottom: 6px; background: var(--secondary-background-color); font-size: 14px; }
        .msg.out { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); }
        .msg small { color: var(--secondary-text-color); display: block; font-size: 12px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        td, th { text-align: left; padding: 4px 6px; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
        th { color: var(--secondary-text-color); font-weight: 500; }
        .map { height: 380px; border-radius: 10px; overflow: hidden; position: relative; z-index: 0; }
        .menu:empty { display: none; }
        .menu { margin: -8px 0 -8px -8px; color: var(--primary-text-color); }
        nav { overflow-x: auto; scrollbar-width: none; flex-shrink: 0; }
        nav::-webkit-scrollbar { display: none; }
        nav button { flex-shrink: 0; white-space: nowrap; }
        .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; flex: none; }
        .seg button { font: inherit; font-size: 14px; padding: 7px 10px; border: none; background: var(--card-background-color); color: var(--secondary-text-color); cursor: pointer; white-space: nowrap; }
        .seg button + button { border-left: 1px solid var(--divider-color); }
        .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .msgrow .to { width: 120px; } .msgrow .text { flex: 1; min-width: 160px; }
        main.scroll { overflow-y: auto; }
        main.scroll .cols { flex: none; } main.scroll .card { flex-shrink: 0; }
        @media (max-width: 600px) {
          .page { padding: 8px 10px; gap: 8px; }
          main { overflow-y: auto; overscroll-behavior: contain; }
          pre, .chatlog { min-height: 120px; }
          .top { margin: -8px -10px 0; padding: calc(8px + env(safe-area-inset-top, 0px)) 10px 0; gap: 8px; }
          h1 { font-size: 17px; }
          .chip { font-size: 12px; padding: 3px 8px; }
          nav button { padding: 8px 10px; }
          input, select, textarea { font-size: 16px; }  /* no zoom on iPhone */
          .controls label { display: flex; align-items: center; gap: 6px; flex: 1 1 140px; }
          .controls input { flex: 1; width: auto; min-width: 0; }
          .row label { flex: 1 1 140px; display: flex; align-items: center; gap: 6px; } .row label input { flex: 1; min-width: 0; width: auto; }
          .controls label input[type=checkbox], .row label input[type=checkbox] { flex: none; width: auto; }
          .msgrow { flex-wrap: wrap; } .msgrow .to { width: auto; flex: 1 1 40%; min-width: 0; } .msgrow .text { min-width: 0; flex: 1 1 60%; } .msgrow .btn { flex: none; }
          /* APRS on a phone: the message form and the map stay put, only the lists below scroll. */
          main.aprs { overflow: hidden; }
          main.aprs .cols { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; display: flex; flex-direction: column; }
          main.aprs .cols .card { flex-shrink: 0; overflow: visible; }
          main.aprs .msgs { max-height: none; }
          main.aprs .map { height: 220px; }
          pre { font-size: 12px; padding: 8px; }
          .map { height: 260px; }
          .msgs { max-height: 50vh; }
          .pos { display: none; }
          table { font-size: 12px; } td, th { padding: 4px; }
          .form { grid-template-columns: minmax(0, 1fr); }
          .chatline { font-size: 14px; }
          .line .btn { padding: 7px 12px; }
        }
        .page.kbd .hint { display: none; }
        .page.kbd pre, .page.kbd .chatlog { min-height: 60px; }
        .aprs-pop .leaflet-popup-content { margin: 8px 10px; font-size: 12px; line-height: 1.35; word-break: break-word; }
        .aprs-pop .leaflet-popup-content small { font-size: 11px; color: #666; }
        .leaflet-container { background: var(--secondary-background-color); font: inherit; }
        .leaflet-tooltip.call-label { background: var(--card-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color) !important; box-shadow: 0 1px 3px rgba(0,0,0,.3); padding: 1px 5px; font-size: 11px; }
        .wx { display: inline-block; }
        td:nth-child(-n+2) { white-space: nowrap; }
        .call-label::before { display: none; }
        ${MAP_CSS}
        .map { height: 480px; }
        textarea { font: 13px/1.4 ui-monospace, monospace; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); width: 100%; box-sizing: border-box; }
        .banner { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 10px; background: rgba(255, 152, 0, 0.18); border: 1px solid var(--warning-color, #ff9800); font-size: 14px; }
        .dialog-back { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 16px; }
        .dialog { background: var(--card-background-color); color: var(--primary-text-color); border-radius: 14px; padding: 16px 18px; max-width: 520px; width: 100%; display: flex; flex-direction: column; gap: 10px; box-shadow: 0 4px 24px rgba(0,0,0,.4); }
        .dialog h3 { margin: 0; font-size: 18px; font-weight: 500; }
        .list-row { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--divider-color); font-size: 14px; }
        .list-row .grow { flex: 1; min-width: 0; }
        .list-row small { color: var(--secondary-text-color); display: block; font-size: 12px; }
        .mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; word-break: break-word; }
      </style>

      <div class="page"><div class="top"><div class="update" hidden></div><header></header><nav></nav></div><main></main></div>`;
  }

  _render() {
    if (!this.shadowRoot.querySelector('main')) this._renderShell();
    this._renderHeader();
    const t = this._t;
    const nav = this.shadowRoot.querySelector('nav');
    const mode = this._extra?.mode || '';
    // BBS SERVER or TAK on: only that, the monitor and the settings
    const tabs = mode ? [mode, 'monitor', 'settings'] : ['chat', 'terminal', 'monitor', 'aprs', 'bulletins', 'thursday', 'settings'];
    if (!tabs.includes(this._tab)) this._tab = tabs[0];
    nav.innerHTML = tabs.map((k) => k === 'settings'
      ? `<button data-tab="${k}" class="gear ${this._tab === k ? 'active' : ''}" title="${t[k]}" aria-label="${t[k]}"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="${COG}"/></svg></button>`
      : `<button data-tab="${k}" class="${this._tab === k ? 'active' : ''}">${t[k]}</button>`).join('');
    nav.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      this._tab = b.dataset.tab;
      localStorage.setItem('aprs-kiss-tab', this._tab);
      this._render();
    }));
    const main = this.shadowRoot.querySelector('main');
    main.classList.remove('scroll', 'aprs');
    if (!this._state) {
      main.innerHTML = `<div class="error">${esc(this._error)}</div>`;
      return;
    }
    this._refreshTab = null;
    if (this._tab === 'settings') this._renderSettings(main);
    else if (this._tab === 'thursday') this._renderThursday(main);
    else if (this._tab === 'bulletins') this._renderBulletins(main);
    else if (this._tab === 'bbs') this._renderBbs(main);
    else if (this._tab === 'tak') this._renderTak(main);
    else if (this._tab === 'chat') this._renderChat(main);
    else if (this._tab === 'terminal') this._renderTerminal(main);
    else if (this._tab === 'monitor') this._renderMonitor(main);
    else this._renderAprs(main);
  }

  _renderHeader() {
    const t = this._t;
    const s = this._state;
    const header = this.shadowRoot.querySelector('header');
    if (!header) return;
    if (!s) {
      header.innerHTML = '<h1>APRS & Packet</h1>';
      return;
    }
    const sessions = Object.entries(s.sessions || {}).map(([k, v]) => `${k}: ${v}`).join(', ');
    header.innerHTML = `
      <span class="menu"></span>
      <h1>APRS & Packet · ${esc(s.callsign)}</h1>
      <span class="chip"><span class="dot ${s.tnc_connected ? 'ok' : 'bad'}"></span>${t.tnc} ${s.tnc_connected ? t.online : t.offline}</span>
      <button class="chip ${s.tx_enabled ? 'tx-on' : ''}" id="tx"><span class="dot ${s.tx_enabled ? 'bad' : ''}"></span>${t.tx}: ${s.tx_enabled ? t.on : t.off}</button>
      ${this._gpsChip()}
      ${sessions ? `<span class="chip">${esc(sessions)}</span>` : ''}`;
    if (this._narrow) {
      // On a phone Home Assistant hides its sidebar: this button opens it.
      const menu = document.createElement('ha-menu-button');
      menu.hass = this._hass;
      menu.narrow = true;
      header.querySelector('.menu').appendChild(menu);
    }
    header.querySelector('#tx').addEventListener('click', async () => {
      const r = await this._ws({ type: 'aprs_kiss/set_tx', enabled: !s.tx_enabled });
      if (r) { s.tx_enabled = r.tx_enabled; this._render(); }
    });
  }

  // ─── terminal ────────────────────────────────────────────────────────

  _renderTerminal(main) {
    const t = this._t;
    main.innerHTML = `
      <div class="row controls"></div>
      <pre class="term"></pre>
      <div class="line"><input class="input" placeholder="${t.typeLine}" autocomplete="off"><button class="btn send">${t.send}</button></div>
      <div class="hint status"></div><div class="error">${esc(this._error)}</div>`;
    this._renderTerminalControls();
    const pre = main.querySelector('.term');
    pre.innerHTML = '';
    for (const e of this._state.terminal) if (e.remote === this._remoteKey()) this._appendTerminal(e, pre);
    const input = main.querySelector('.input');
    const send = () => this._sendLine(input);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
    main.querySelector('.send').addEventListener('click', send);
    input.focus();
  }

  _renderTerminalControls() {
    const t = this._t;
    const box = this.shadowRoot.querySelector('.controls');
    if (!box) return;
    const st = this._state.sessions?.[this._remoteKey()];
    const busy = st === 'connected' || st === 'connecting' || st === 'disconnecting';
    box.innerHTML = this._unproto
      ? `<label>${t.unprotoTo} <input class="call dest" value="${esc(this._unprotoTo)}"></label>
         <label>${t.via} <input class="path" value="${esc(this._path)}" placeholder="WIDE1-1"></label>
         <button class="btn secondary toggle">${t.terminal}</button>`
      : `<label>${t.connectTo} <input class="call remote" value="${esc(this._remote)}" placeholder="OK0BBS" ${busy ? 'disabled' : ''}></label>
         <label>${t.via} <input class="path" value="${esc(this._path)}" placeholder="OK0DIG" ${busy ? 'disabled' : ''}></label>
         ${busy ? `<button class="btn secondary disc">${t.disconnect}</button>` : `<button class="btn conn">${t.connect}</button>`}
         <button class="btn secondary toggle">${t.unproto}</button>`;
    const status = this.shadowRoot.querySelector('.status');
    if (status) status.textContent = !this._state.tx_enabled ? t.txOffHint : (!this._unproto && st !== 'connected' ? t.notConnected : '');
    box.querySelector('.remote')?.addEventListener('change', (e) => {
      this._remote = e.target.value.trim().toUpperCase();
      localStorage.setItem('aprs-kiss-remote', this._remote);
      this._renderTerminal(this.shadowRoot.querySelector('main'));
    });
    box.querySelector('.dest')?.addEventListener('change', (e) => { this._unprotoTo = e.target.value.trim().toUpperCase() || 'CQ'; });
    box.querySelector('.path')?.addEventListener('change', (e) => {
      this._path = e.target.value.trim().toUpperCase();
      localStorage.setItem('aprs-kiss-path', this._path);
    });
    box.querySelector('.conn')?.addEventListener('click', async () => {
      const r = box.querySelector('.remote');
      this._remote = r.value.trim().toUpperCase();
      this._path = box.querySelector('.path').value.trim().toUpperCase();
      localStorage.setItem('aprs-kiss-remote', this._remote);
      localStorage.setItem('aprs-kiss-path', this._path);
      if (await this._ws({ type: 'aprs_kiss/connect', remote: this._remote, path: this._path })) {
        this._state.sessions[this._remoteKey()] = 'connecting';
      }
      this._renderTerminal(this.shadowRoot.querySelector('main'));
    });
    box.querySelector('.disc')?.addEventListener('click', () => this._ws({ type: 'aprs_kiss/disconnect', remote: this._remote }));
    box.querySelector('.toggle').addEventListener('click', () => {
      this._unproto = !this._unproto;
      this._renderTerminalControls();
    });
  }

  async _sendLine(input) {
    const text = input.value;
    if (!text.trim() && !this._unproto) {
      // An empty line still sends a CR, BBSes use it.
    }
    input.value = '';
    if (this._unproto) {
      if (!text.trim()) return;
      const ok = await this._ws({ type: 'aprs_kiss/send_unproto', destination: this._unprotoTo, text, path: this._path });
      if (ok) this._appendTerminal({ time: Date.now() / 1000, kind: 'out', text: `[${this._unprotoTo}] ${text}\n` });
      return;
    }
    await this._ws({ type: 'aprs_kiss/send_text', remote: this._remote, text: text + '\n' });
  }

  _appendTerminal(e, pre = this.shadowRoot.querySelector('.term')) {
    if (!pre) return;
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    const span = document.createElement('span');
    if (e.kind === 'tx') { span.className = 'tx'; span.textContent = e.text.split('\n').filter((l, i, a) => l || i < a.length - 1).map((l) => `> ${l}`).join('\n') + '\n'; }
    else if (e.kind === 'state') { span.className = 'st'; span.textContent = `*** ${time(e.time)} ${e.text}\n`; }
    else if (e.kind === 'out') { span.className = 'out'; span.textContent = e.text; }
    else span.textContent = e.text;
    pre.appendChild(span);
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }

  // ─── settings ────────────────────────────────────────────────────────

  async _renderSettings(main) {
    const t = this._t;
    const cs = (this._hass.language || '').startsWith('cs');
    main.classList.add('scroll');
    main.innerHTML = '<div class="hint">…</div>';
    const st = await this._ws({ type: 'aprs_kiss/get_settings' });
    if (!st) { main.innerHTML = `<div class="error">${esc(this._error)}</div>`; return; }
    const [base, ssid] = (st.callsign || '').split('-');
    const sym = st.symbol || '/-';
    const known = SYMBOLS.some((x) => x[0] === sym);
    const is = st.aprsis;
    const isLine = !st.aprsis_enabled ? '' : `<div class="hint">${t.isState}: ${is?.verified ? `<span class="ok">${t.verified}</span> ${esc(is.server || '')}` : is?.connected ? t.unverified : t.disconnectedIs + (is?.error ? ` (${esc(is.error)})` : '')}
      · RF→IS ${st.igate_stats.rf_to_is} · IS→RF ${st.igate_stats.is_to_rf} · ✉ ${st.igate_stats.is_messages}</div>`;
    main.innerHTML = `
      <div class="form">
        <div class="card"><h2>${t.tncCard}</h2>
          <div class="hint">${t.tncState}: ${st.tnc?.connected ? `<span class="ok">${t.tncOnline}</span>` : t.tncOffline + (st.tnc?.error ? ` (${esc(st.tnc.error)})` : '')}</div>
          <label class="field">${t.tncKind}
            <select class="f-conn"><option value="tcp" ${st.connection !== 'serial' ? 'selected' : ''}>${t.tncTcp}</option>
            <option value="serial" ${st.connection === 'serial' ? 'selected' : ''}>${t.tncSerial}</option></select></label>
          <div class="f-tcp-box">
            <label class="field">${t.tncHost}<input class="f-tnc-host" value="${esc(st.host || '')}" placeholder="192.168.0.10" autocomplete="off"></label>
            <label class="field">${t.tncPort}<input class="f-tnc-port" type="number" min="1" max="65535" value="${st.port || 8001}"></label>
          </div>
          <div class="f-serial-box">
            <label class="field">${t.tncDevice}
              <div class="callrow"><select class="f-device"></select>
              <button type="button" class="btn secondary f-search">${t.tncSearch}</button></div></label>
            <div class="hint f-ports-none" hidden>${t.tncNone}</div>
            <label class="field f-device-own-box" hidden><input class="f-device-own" value="" placeholder="${t.tncDevicePh}" autocomplete="off"></label>
            <label class="field">${t.tncBaud}
              <select class="f-baud">${[1200, 4800, 9600, 19200, 38400, 57600, 115200].map((b) => `<option value="${b}" ${(st.baudrate || 115200) === b ? 'selected' : ''}>${b}</option>`).join('')}
              ${[1200, 4800, 9600, 19200, 38400, 57600, 115200].includes(st.baudrate || 115200) ? '' : `<option value="${st.baudrate}" selected>${st.baudrate}</option>`}</select>
              <span>${t.tncBaudHint}</span></label>
            <div class="hint">${t.tncHint}</div>
          </div>
        </div>
        <div class="card"><h2>${t.station}</h2>
          <label class="field">${t.callsign}
            <div class="callrow"><input class="f-call" value="${esc(base || '')}" maxlength="6">
            <select class="f-ssid">${SSIDS[cs ? 'cs' : 'en'].map((label, i) => `<option value="${i}" ${Number(ssid || 0) === i ? 'selected' : ''}>-${i}</option>`).join('')}</select></div>
            <span class="ssid-meaning">${esc(SSIDS[cs ? 'cs' : 'en'][Number(ssid || 0)])}</span></label>
          <label class="field">${t.symbol}
            <select class="f-symbol">${SYMBOLS.map(([code, emoji, en, czech]) => `<option value="${esc(code)}" ${code === sym ? 'selected' : ''}>${emoji} ${esc(cs ? czech : en)} (${esc(code)})</option>`).join('')}
            ${known ? '' : `<option value="${esc(sym)}" selected>${esc(sym)}</option>`}</select></label>
          <label class="field">${t.comment}<input class="f-comment" maxlength="43" value="${esc(st.comment || '')}"></label>
          <label class="field">${t.path}<input class="f-path" value="${esc(st.path || '')}" placeholder="WIDE1-1,WIDE2-1"></label>
          <label class="field">${t.beacon}<input class="f-beacon" type="number" min="0" max="1440" value="${st.beacon_minutes || 0}"></label>
          <label class="field">${t.tracked}<input class="f-tracked" value="${esc(st.tracked_callsigns || '')}" placeholder="OK1SIM-9, OK1ABC-7"></label>
          <label class="field check"><input type="checkbox" class="f-incoming" ${st.accept_incoming ? 'checked' : ''}> ${t.incoming}</label>
          <label class="field">${t.txdelay}<input class="f-txdelay" type="number" min="0" max="1000" step="10" value="${st.txdelay_ms || 0}"></label>
        </div>
        <div class="card"><h2>${t.privTitle}</h2>
          <label class="field">${t.privAmbiguity}
            <select class="f-amb">${[[0, t.privExact], [1, t.privAbout.replace('{dist}', '200 m')], [2, t.privAbout.replace('{dist}', '2 km')], [3, t.privAbout.replace('{dist}', '20 km')], [4, t.privAbout.replace('{dist}', '110 km')]].map(([v, l]) => `<option value="${v}" ${(st.position_ambiguity || 0) === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="field check"><input type="checkbox" class="f-motion" ${st.send_motion !== false ? 'checked' : ''}> ${t.privMotion}</label>
          <label class="field check"><input type="checkbox" class="f-alt" ${st.send_altitude !== false ? 'checked' : ''}> ${t.privAltitude}</label>
          <div class="hint">${t.privHint}</div>
        </div>
        <div class="card"><h2>${t.aprsis}</h2>
          <label class="field check"><input type="checkbox" class="f-is" ${st.aprsis_enabled ? 'checked' : ''}> ${t.aprsisOn}</label>
          <label class="field f-licence-box" hidden>${t.licenceAsk} <b>${t.licenceText}</b>
            <input class="f-licence" autocomplete="off" placeholder="${t.licenceText}"></label>
          ${isLine}
          <label class="field">${t.server}<input class="f-host" value="${esc(st.aprsis_host || 'euro.aprs2.net')}"></label>
          <label class="field">${t.port}<input class="f-port" type="number" value="${st.aprsis_port || 14580}"></label>
          <label class="field">${t.passcode}
            <div class="callrow"><input class="f-pass" value="${esc(st.aprsis_passcode || '')}" placeholder="${t.passAuto}" type="password" inputmode="numeric" autocomplete="off">
            <button type="button" class="btn secondary f-showpass">${t.show}</button></div>
            <span>${st.aprsis_passcode ? t.passOwn : t.passHint}</span></label>
          <label class="field check"><input type="checkbox" class="f-beacon-is" ${st.beacon_is ? 'checked' : ''}> ${t.beaconIs}</label>
          <div class="hint">${t.beaconHint}</div>
          <label class="field">${t.radius}<input class="f-radius" type="number" min="0" max="500" value="${st.aprsis_radius_km ?? 50}"></label>
          <label class="field check"><input type="checkbox" class="f-irx" ${st.igate_rx ? 'checked' : ''}> ${t.igateRx}</label>
          <label class="field check"><input type="checkbox" class="f-itx" ${st.igate_tx ? 'checked' : ''}> ${t.igateTx}</label>
          <div class="hint">${t.igateHint}</div>
        </div>
        <div class="card"><h2>${t.digi}</h2>
          <label class="field">${t.digiMode}
            <select class="f-digi">${[['off', t.digiOff], ['fillin', t.digiFillin], ['wide', t.digiWide]].map(([k, l]) => `<option value="${k}" ${(st.digi_mode || 'off') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="field">${t.digiHops}<select class="f-digi-hops">${[1, 2, 3].map((n) => `<option value="${n}" ${(st.digi_max_hops || 2) === n ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <label class="field">${t.digiAliases}<input class="f-digi-alias" value="${esc(st.digi_aliases || '')}" placeholder="RELAY" style="text-transform:uppercase"></label>
          <div class="hint">${t.digiHint}${this._extra?.digipeated ? ` · ${t.digipeated}: ${this._extra.digipeated}` : ''}</div>
        </div>
        <div class="card"><h2>${t.telTitle}</h2>
          <label class="field">${t.telVia}
            <select class="f-tel">${[['', t.telOff], ['internet', t.telInternet], ['radio', t.telRadio], ['both', t.telBoth]].map(([v, l]) => `<option value="${v}" ${(st.telemetry_via || '') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="field">${t.telMinutes}
            <select class="f-tel-min">${[10, 20, 30, 60].map(v => `<option value="${v}" ${(st.telemetry_minutes || 20) === v ? 'selected' : ''}>${v} min</option>`).join('')}</select></label>
          <div class="hint">${t.telHint}${st.callsign ? ` <a href="https://aprs.fi/telemetry/a/${esc(st.callsign)}" target="_blank" rel="noopener">${t.telGraphs}</a>` : ''}</div>
        </div>
        <div class="card"><h2>${t.gps}</h2>
          <label class="field">${t.gpsSource}
            <select class="f-gps"><option value="manual" ${st.gps_source !== 'usb' ? 'selected' : ''}>${t.gpsHome}</option>
            <option value="usb" ${st.gps_source === 'usb' ? 'selected' : ''}>${t.gpsUsb}</option></select></label>
          <div class="f-gps-box">
            <label class="field">${t.gpsDevice}<div class="callrow"><select class="f-gps-device"></select>
              <button type="button" class="btn secondary f-gps-search">${t.tncSearch}</button></div></label>
            <label class="field">${t.gpsBaud}<select class="f-gps-baud">${[[0, t.gpsAuto], [4800, 4800], [9600, 9600], [38400, 38400], [115200, 115200]].map(([v, l]) => `<option value="${v}" ${(st.gps_baudrate || 0) === v ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
            ${st.gps ? `<div class="hint">${t.gpsState}: ${st.gps.error ? `<span class="error">${esc(st.gps.error)}</span>` : st.gps.fix ? `<span class="ok">${t.gpsFix}</span> · ${st.gps.satellites ?? '?'} ${t.gpsSats}` : t.gpsNoFix}</div>` : ''}
          </div>
          <div class="hint">${t.gpsHint}</div>
        </div>
        <div class="card"><h2>${t.modes}</h2>
          <div class="hint">${t.modeHint}</div>
          <div class="row"><button type="button" class="btn ${st.mode === 'bbs' ? '' : 'secondary'} f-mode-bbs">${st.mode === 'bbs' ? t.switchOff + ' BBS SERVER' : t.switchOn + ' BBS SERVER'}</button>
            <button type="button" class="btn ${st.mode === 'tak' ? '' : 'secondary'} f-mode-tak">${st.mode === 'tak' ? t.switchOff + ' TAK' : t.switchOn + ' TAK'}</button></div>
          <label class="field">${t.bbsSsid}<select class="f-bbs-ssid">${Array.from({ length: 15 }, (_, i) => i + 1).map((n) => `<option value="${n}" ${(st.bbs_ssid || 1) === n ? 'selected' : ''}>-${n}</option>`).join('')}</select></label>
          <label class="field">${t.takCallsign}<input class="f-tak-call" value="${esc(st.tak_callsign || '')}" style="text-transform:uppercase"></label>
          <label class="field">${t.takTeam}<select class="f-tak-team">${TAK_TEAMS.map((x) => `<option ${(st.tak_team || 'Cyan') === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
          <label class="field">${t.takRole}<select class="f-tak-role">${TAK_ROLES.map((x) => `<option ${(st.tak_role || 'Team Member') === x ? 'selected' : ''}>${x}</option>`).join('')}</select></label>
          <label class="field">${t.takInterval}<input class="f-tak-int" type="number" min="0" max="120" value="${st.tak_interval_min ?? 2}"></label>
        </div>
        <div class="card maps-card"><h2>${t.maps}</h2><div class="maps-body hint">…</div></div>
      </div>
      <div class="row"><button class="btn save">${t.save}</button><span class="msg-saved"></span><span class="error">${esc(this._error)}</span></div>`;
    const q = (c) => main.querySelector(c);
    // TNC connection: show the fields of the chosen kind; ports are looked up on the HA machine.
    const connBoxes = () => {
      const serial = q('.f-conn').value === 'serial';
      q('.f-tcp-box').hidden = serial;
      q('.f-serial-box').hidden = !serial;
    };
    const ownBox = () => { q('.f-device-own-box').hidden = q('.f-device').value !== '__own'; };
    const loadPorts = async () => {
      const keep = q('.f-device').value && q('.f-device').value !== '__own' ? q('.f-device').value : (st.device || '');
      let ports = [];
      try { ports = (await this._hass.callWS({ type: 'aprs_kiss/serial_ports' })).ports || []; } catch (e) { ports = []; }
      const known = ports.some((p) => p.device === keep);
      q('.f-device').innerHTML = ports.map((p) => `<option value="${esc(p.device)}" ${p.device === keep ? 'selected' : ''}>${esc(p.label)}</option>`).join('')
        + (keep && !known ? `<option value="${esc(keep)}" selected>${esc(keep)}</option>` : '')
        + `<option value="__own" ${!ports.length && !keep ? 'selected' : ''}>${t.tncOther}</option>`;
      q('.f-ports-none').hidden = ports.length > 0;
      ownBox();
    };
    q('.f-conn').addEventListener('change', () => { connBoxes(); if (q('.f-conn').value === 'serial') loadPorts(); });
    q('.f-device').addEventListener('change', () => { ownBox(); if (!q('.f-device-own-box').hidden) q('.f-device-own').focus(); });
    q('.f-search').addEventListener('click', loadPorts);
    connBoxes();
    loadPorts();
    // USB GPS: its port from the same list as the TNC's
    const gpsBox = () => { q('.f-gps-box').hidden = q('.f-gps').value !== 'usb'; };
    const loadGpsPorts = async () => {
      const keep = q('.f-gps-device').value || st.gps_device || '';
      let ports = [];
      try { ports = (await this._hass.callWS({ type: 'aprs_kiss/serial_ports' })).ports || []; } catch (e) { ports = []; }
      q('.f-gps-device').innerHTML = ports.map((p) => `<option value="${esc(p.device)}" ${p.device === keep ? 'selected' : ''}>${esc(p.label)}</option>`).join('')
        + (keep && !ports.some((p) => p.device === keep) ? `<option value="${esc(keep)}" selected>${esc(keep)}</option>` : '');
    };
    q('.f-gps').addEventListener('change', () => { gpsBox(); if (q('.f-gps').value === 'usb') loadGpsPorts(); });
    q('.f-gps-search').addEventListener('click', loadGpsPorts);
    gpsBox();
    if (q('.f-gps').value === 'usb') loadGpsPorts();
    q('.f-mode-bbs').addEventListener('click', () => this._setMode(st.mode === 'bbs' ? '' : 'bbs'));
    q('.f-mode-tak').addEventListener('click', () => this._setMode(st.mode === 'tak' ? '' : 'tak'));
    this._renderMapsCard(q('.maps-body'));
    q('.f-showpass').addEventListener('click', () => {
      const f = q('.f-pass');
      f.type = f.type === 'password' ? 'text' : 'password';
      q('.f-showpass').textContent = f.type === 'password' ? t.show : t.hide;
    });
    // Switching APRS-IS on asks for the licence statement (checked again by the integration).
    const licenceBox = () => { q('.f-licence-box').hidden = !(q('.f-is').checked && !st.aprsis_enabled); };
    q('.f-is').addEventListener('change', () => { licenceBox(); if (!q('.f-licence-box').hidden) q('.f-licence').focus(); });
    // Nothing applies until Save: say so as soon as something changes.
    const markDirty = () => {
      q('.save').classList.add('dirty');
      q('.msg-saved').innerHTML = `<span class="warn">${t.unsaved}</span>`;
    };
    main.querySelector('.form').addEventListener('input', markDirty);
    main.querySelector('.form').addEventListener('change', markDirty);
    q('.f-ssid').addEventListener('change', (e) => { q('.ssid-meaning').textContent = SSIDS[cs ? 'cs' : 'en'][Number(e.target.value)]; });
    q('.save').addEventListener('click', async () => {
      const call = q('.f-call').value.trim().toUpperCase();
      const ssidVal = Number(q('.f-ssid').value);
      const settings = {
        callsign: ssidVal ? `${call}-${ssidVal}` : call,
        symbol: q('.f-symbol').value, comment: q('.f-comment').value, path: q('.f-path').value.trim().toUpperCase(),
        beacon_minutes: Number(q('.f-beacon').value) || 0, beacon_is: q('.f-beacon-is').checked, tracked_callsigns: q('.f-tracked').value.trim().toUpperCase(),
        accept_incoming: q('.f-incoming').checked, txdelay_ms: Number(q('.f-txdelay').value) || 0,
        aprsis_enabled: q('.f-is').checked, aprsis_host: q('.f-host').value.trim(), aprsis_port: Number(q('.f-port').value) || 14580,
        aprsis_passcode: q('.f-pass').value.trim(), aprsis_radius_km: Number(q('.f-radius').value) || 0,
        igate_rx: q('.f-irx').checked, igate_tx: q('.f-itx').checked,
        position_ambiguity: Number(q('.f-amb').value) || 0, send_motion: q('.f-motion').checked, send_altitude: q('.f-alt').checked,
        telemetry_via: q('.f-tel').value, telemetry_minutes: Number(q('.f-tel-min').value) || 20,
        digi_mode: q('.f-digi').value, digi_max_hops: Number(q('.f-digi-hops').value) || 2, digi_aliases: q('.f-digi-alias').value.trim().toUpperCase(),
        gps_source: q('.f-gps').value, gps_device: q('.f-gps').value === 'usb' ? q('.f-gps-device').value : (st.gps_device || ''),
        gps_baudrate: Number(q('.f-gps-baud').value) || 0,
        bbs_ssid: Number(q('.f-bbs-ssid').value) || 1, tak_callsign: q('.f-tak-call').value.trim().toUpperCase(),
        tak_team: q('.f-tak-team').value, tak_role: q('.f-tak-role').value, tak_interval_min: Number(q('.f-tak-int').value) || 0,
        licence_text: q('.f-licence').value,
        connection: q('.f-conn').value,
        host: q('.f-tnc-host').value.trim(), port: Number(q('.f-tnc-port').value) || 0,
        device: q('.f-device').value === '__own' ? q('.f-device-own').value.trim() : q('.f-device').value,
        baudrate: Number(q('.f-baud').value) || 115200,
      };
      // Errors stay next to the button; re-rendering would lose what was typed.
      const err = main.querySelector('.row .error');
      err.textContent = '';
      let r = null;
      try {
        r = await this._hass.callWS({ type: 'aprs_kiss/set_settings', settings, entry_id: this._state?.entry_id });
      } catch (e) {
        const text = e.message || String(e);
        err.textContent = /licence_required/.test(text) ? t.licenceRequired
          : /tnc_host_required/.test(text) ? t.tncHostRequired
            : /tnc_device_required/.test(text) ? t.tncDeviceRequired : text;
        if (/licence_required/.test(text)) { licenceBox(); q('.f-licence').focus(); }
        return;
      }
      if (r) {
        q('.save').classList.remove('dirty');
        q('.msg-saved').innerHTML = `<span class="ok">${t.saved}</span>`;
        setTimeout(async () => { await this._load(); }, 4000);
      }
    });
  }

  // ─── chat ────────────────────────────────────────────────────────────

  _renderChat(main) {
    const t = this._t;
    main.innerHTML = `
      <div class="chatlog"></div>
      <div class="line"><input class="chatinput" placeholder="${t.chatPh}" autocomplete="off" maxlength="200"><button class="btn chatsend">${t.send}</button></div>
      <div class="hint">${this._state.tx_enabled ? t.chatHint : t.txOffHint}</div>
      <div class="error">${esc(this._error)}</div>`;
    const log = main.querySelector('.chatlog');
    const lines = (this._state.chat || []).filter((e) => !e.aprs);
    if (!lines.length) log.innerHTML = `<div class="hint">${t.chatEmpty}</div>`;
    for (const e of lines) this._appendChat(e, log);
    log.scrollTop = log.scrollHeight;
    const input = main.querySelector('.chatinput');
    const send = async () => {
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      const ok = await this._ws({ type: 'aprs_kiss/send_chat', text });
      if (!ok) input.value = text;
    };
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); send(); } });
    main.querySelector('.chatsend').addEventListener('click', send);
    input.focus();
  }

  _appendChat(e, log = this.shadowRoot.querySelector('.chatlog')) {
    if (!log || e.aprs) return;
    log.querySelector(':scope > .hint')?.remove();
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    const div = document.createElement('div');
    div.className = `chatline${e.out ? ' out' : ''}`;
    const to = e.to && !['CQ', 'APRS'].includes(e.to) && !e.to.startsWith('AP') ? `<span class="to">→ ${esc(e.to)}</span>` : '';
    div.innerHTML = `<span class="t">${time(e.time)}</span><span class="c">${esc(e.from)}:</span>${to}${esc(e.text)}`;
    log.appendChild(div);
    if (atBottom) log.scrollTop = log.scrollHeight;
  }

  // ─── monitor ─────────────────────────────────────────────────────────

  _renderMonitor(main) {
    const t = this._t;
    main.innerHTML = `
      <div class="row"><label><input type="checkbox" class="pause" ${this._paused ? 'checked' : ''}> ${t.pause}</label>
      <label><input type="checkbox" class="mon-is" ${this._monIs ? 'checked' : ''}> ${t.showIs}</label>
      <button class="btn secondary clear">${t.clear}</button></div>
      <pre class="mon"></pre>`;
    const pre = main.querySelector('.mon');
    const lines = this._monIs ? this._state.monitor : (this._state.monitor_rf || this._state.monitor.filter((l) => !isIsLine(l)));
    pre.textContent = lines.join('\n') + '\n';
    pre.scrollTop = pre.scrollHeight;
    main.querySelector('.pause').addEventListener('change', (e) => { this._paused = e.target.checked; if (!this._paused) this._renderMonitor(main); });
    main.querySelector('.mon-is').addEventListener('change', (e) => {
      this._monIs = e.target.checked;
      try { localStorage.setItem('aprs-kiss-mon-is', this._monIs ? '1' : '0'); } catch { /* private mode */ }
      this._renderMonitor(main);
    });
    main.querySelector('.clear').addEventListener('click', () => { this._state.monitor = []; this._state.monitor_rf = []; this._renderMonitor(main); });
  }

  _appendMonitor(line) {
    const pre = this.shadowRoot.querySelector('.mon');
    if (!pre || (!this._monIs && isIsLine(line))) return;
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.appendChild(document.createTextNode(line + '\n'));
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }

  // ─── APRS ────────────────────────────────────────────────────────────

  // Radio or internet for a message: the last choice, else radio when transmitting is on.
  // the one switch "send over the internet too" (Settings) decides the default; each message can choose
  _via() {
    if (this._viaChoice) return this._viaChoice;
    if (!this._state?.tx_enabled) return 'internet';
    return this._extra?.beacon_is ? 'both' : 'radio';
  }

  _aprsData() {
    return {
      msgs: [...this._state.messages].reverse(),
      heard: [...this._state.heard].sort((a, b) => b.last_heard - a.last_heard),
    };
  }

  _aprsMsgsHtml(msgs) {
    const t = this._t;
    return msgs.length ? msgs.map((m) => `
      <div class="msg ${m.direction}">${esc(m.text)}
        <small>${m.direction === 'in' ? esc(m.from) : '→ ' + esc(m.to)}${m.via === 'radio' ? ' · 📻' : m.via === 'internet' ? ' · 🌐' : ''} · ${time(m.time)}${m.direction === 'out' && m.state ? ' · ' + esc(t.state[m.state] || m.state) : ''}</small></div>`).join('') : `<div class="hint">${t.noMessages}</div>`;
  }

  _aprsHeardHtml(heard) {
    const t = this._t;
    return `<table>
      <tr><th>Call</th><th>${t.lastHeard}</th><th class="pos">${t.position}</th><th>${t.comment}</th></tr>
      ${heard.map((h) => `<tr><td>${h.last_rf ? '' : `<span title="${t.viaIs}">🌐 </span>`}${esc(h.call)}${h.gated_by ? `<br><small>iGate ${esc(h.gated_by)}</small>` : ''}</td><td>${time(h.last_heard)}</td>
        <td class="pos">${h.latitude != null ? `${h.latitude.toFixed(4)}, ${h.longitude.toFixed(4)}` : ''}</td><td>${wxText(h.weather) ? `<span class="wx">🌡 ${esc(wxText(h.weather))}</span><br>` : ''}${esc(h.comment || h.status || '')}</td></tr>`).join('')}
    </table>${heard.some((h) => !h.last_rf) ? `<div class="hint">${t.isLegend}</div>` : ''}`;
  }

  _renderAprs(main) {
    const t = this._t;
    const { msgs, heard } = this._aprsData();
    main.classList.add('scroll', 'aprs');
    main.innerHTML = `
      <div class="row msgrow">
        <input class="call to" placeholder="${t.to}" value="${esc(this._msgTo || '')}">
        <div class="seg" role="group" title="${t.viaTitle}">
          <button type="button" data-via="radio" class="${this._via() === 'radio' ? 'on' : ''}">📻 ${t.viaRadio}</button><button type="button" data-via="both" class="${this._via() === 'both' ? 'on' : ''}">📻+🌐</button><button type="button" data-via="internet" class="${this._via() === 'internet' ? 'on' : ''}">🌐 ${t.viaNet}</button>
        </div>
        <input class="text" maxlength="67" placeholder="${t.message}">
        <button class="btn sendmsg">${t.send}</button>
      </div>
      <div class="row tools">
        <button class="btn secondary spotbtn" title="${esc(t.app.spot_title)}">⛰ ${esc(t.app.spot_button)}</button>
        <button class="btn secondary svcbtn" title="${esc(t.app.services_title)}">🛰 ${esc(t.app.services_button)}</button>
      </div>
      <div class="card tool" hidden></div>
      <div class="error">${esc(this._error)}</div>
      <div class="card"><h2>${t.map}</h2><div class="map"></div></div>
      <div class="cols">
        <div class="card msgs"><h2>${t.messages}</h2><div class="msgs-body">${this._aprsMsgsHtml(msgs)}</div></div>
        <div class="card"><h2>${t.heard}</h2><div class="heard-body">${this._aprsHeardHtml(heard)}</div></div>
      </div>`;
    const send = async () => {
      const to = main.querySelector('.to').value.trim().toUpperCase();
      const textEl = main.querySelector('.text');
      const text = textEl.value.trim();
      if (!to || !text) return;
      this._msgTo = to;
      const err = main.querySelector('.error');
      err.textContent = '';
      try {
        await this._hass.callWS({ type: 'aprs_kiss/send_message', to, text, via: this._via(), entry_id: this._state.entry_id });
        textEl.value = '';
        await this._loadStatus();
      } catch (e) {
        const m = e.message || String(e);
        err.textContent = /Transmitting is switched off/.test(m) ? t.errTxOff : /APRS-IS is not connected/.test(m) ? t.errIsOff : m;
      }
    };
    main.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
      this._viaChoice = b.dataset.via;
      main.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b));
    }));
    this._map = this._sm = null;
    this._renderMap(main.querySelector('.map'));
    main.querySelector('.sendmsg').addEventListener('click', send);
    main.querySelector('.text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
    main.querySelector('.spotbtn').addEventListener('click', () => this._toggleTool(main, 'spot'));
    main.querySelector('.svcbtn').addEventListener('click', () => this._toggleTool(main, 'services'));
    if (this._tool) this._toggleTool(main, this._tool, true);
  }

  // ─── Spot and Services (the same tables and checks as the app: core/spotting.py, core/services.py) ──

  async _toggleTool(main, which, keep = false) {
    const box = main.querySelector('.tool');
    if (!keep && this._tool === which && !box.hidden) {
      this._tool = null;
      box.hidden = true;
      return;
    }
    this._tool = which;
    box.hidden = false;
    if (!this._spotOpts) {
      try {
        this._spotOpts = await this._hass.callWS({ type: 'aprs_kiss/spot_options' });
      } catch (e) {
        box.innerHTML = `<div class="error">${esc(e.message || e)}</div>`;
        return;
      }
    }
    if (which === 'spot') this._renderSpot(main, box); else this._renderServices(main, box);
  }

  _renderServices(main, box) {
    const a = this._t.app;
    box.innerHTML = `<h2>${esc(a.services_title)}</h2><div class="hint">${esc(a.services_hint)}</div>
      ${this._spotOpts.services.map((s) => `<div class="svc"><b class="mono">${esc(s.call)}</b>
        <div class="hint">${esc(a[s.key] || '')}</div>
        <div class="row">${s.commands.map((c) => `<button class="btn secondary svccmd" data-call="${esc(s.call)}" data-cmd="${esc(c)}">${esc(c.trim() || a.svc_type)}</button>`).join('')}</div></div>`).join('')}`;
    box.querySelectorAll('.svccmd').forEach((b) => b.addEventListener('click', () => {
      main.querySelector('.to').value = b.dataset.call;
      this._msgTo = b.dataset.call;
      const text = main.querySelector('.text');
      text.value = b.dataset.cmd;
      text.focus();
      text.setSelectionRange(text.value.length, text.value.length);
    }));
  }

  _renderSpot(main, box) {
    const a = this._t.app;
    const o = this._spotOpts;
    let last = {};
    try { last = JSON.parse(localStorage.getItem('aprs_kiss_spot') || '{}'); } catch (e) { last = {}; }
    const opt = (value, text, sel) => `<option value="${esc(value)}"${value === sel ? ' selected' : ''}>${esc(text)}</option>`;
    box.innerHTML = `<h2>${esc(a.spot_title)}</h2>
      <div class="row">
        <label>${esc(a.spot_program)}<select class="sp-program">${o.programs.map((p) => opt(p, p === 'LH' ? a.spot_lighthouse : p, last.program || 'SOTA')).join('')}</select></label>
        <label>${esc(a.spot_gateway)}<select class="sp-gateway"></select></label>
      </div>
      <div class="row">
        <label>${esc(a.spot_ref)}<input class="sp-ref call" value="${esc(last.reference || '')}"></label>
        <label>${esc(a.spot_freq)}<input class="sp-freq" inputmode="decimal" value="${esc(last.frequency || '')}"></label>
        <label>${esc(a.spot_mode)}<select class="sp-mode"></select></label>
      </div>
      <div class="row"><label class="grow">${esc(a.spot_comment)}<input class="sp-comment"></label></div>
      <label class="check"><input type="checkbox" class="sp-test"> ${esc(a.spot_test)}</label>
      <div class="hint sp-hint"></div>
      <div class="mono sp-preview"></div>
      <div class="error sp-error"></div>
      <div class="row"><button class="btn sp-send">${esc(a.spot_send)}</button></div>`;
    const $ = (c) => box.querySelector(c);
    const hints = { APRS2SOTA: a.spot_hint_aprs2sota, APSPOT: a.spot_hint_apspot };
    hints[o.camilla] = a.spot_hint_camilla;
    let built = null;
    const spot = () => ({ program: $('.sp-program').value, gateway: $('.sp-gateway').value, reference: $('.sp-ref').value,
      frequency: $('.sp-freq').value, mode: $('.sp-mode').value, comment: $('.sp-comment').value, test: $('.sp-test').checked });
    const preview = async () => {
      built = null;
      const s = spot();
      try {
        const r = await this._hass.callWS({ type: 'aprs_kiss/spot_build', ...s, entry_id: this._state.entry_id });
        if (r.error) {
          $('.sp-preview').textContent = '';
          $('.sp-error').textContent = (s.reference || s.frequency) ? fill(a[r.error] || r.error, { example: r.example }) : '';
        } else {
          built = r;
          $('.sp-preview').textContent = `→ ${r.to}: ${r.text}`;
          $('.sp-error').textContent = '';
        }
      } catch (e) { $('.sp-error').textContent = e.message || String(e); }
    };
    const gatewayChanged = (keepMode) => {
      const g = $('.sp-gateway').value;
      const modes = o.modes[g] || [];
      const want = keepMode || $('.sp-mode').value;
      $('.sp-mode').innerHTML = modes.map((m) => opt(m, m, modes.includes(want) ? want : 'SSB')).join('');
      $('.sp-hint').textContent = hints[g] || '';
      preview();
    };
    const programChanged = (keepGateway, keepMode) => {
      const gws = o.gateways[$('.sp-program').value] || [];
      const sel = gws.includes(keepGateway) ? keepGateway : gws[0];
      $('.sp-gateway').innerHTML = gws.map((g) => opt(g, o.gateway_names[g] || g, sel)).join('');
      gatewayChanged(keepMode);
    };
    $('.sp-program').addEventListener('change', () => programChanged('', $('.sp-mode').value));
    $('.sp-gateway').addEventListener('change', () => gatewayChanged());
    $('.sp-mode').addEventListener('change', preview);
    $('.sp-test').addEventListener('change', preview);
    let timer;
    ['.sp-ref', '.sp-freq', '.sp-comment'].forEach((c) => $(c).addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(preview, 250);
    }));
    $('.sp-send').addEventListener('click', async () => {
      await preview();
      if (!built) {
        if (!$('.sp-error').textContent) $('.sp-error').textContent = fill(a.spot_bad_ref, { example: o.examples[$('.sp-program').value] || '' });
        return;
      }
      try {
        // by radio over APRS: an iGate in range takes it to the gateway (the message's own radio/internet choice)
        await this._hass.callWS({ type: 'aprs_kiss/send_message', to: built.to, text: built.text, via: this._via(),
          entry_id: this._state.entry_id });
        const s = spot();
        localStorage.setItem('aprs_kiss_spot', JSON.stringify({ program: s.program, gateway: s.gateway,
          reference: s.reference, frequency: s.frequency, mode: s.mode }));
        main.querySelector('.to').value = built.to;
        this._msgTo = built.to;
        this._tool = null;
        box.hidden = true;
        await this._loadStatus();
      } catch (e) {
        const m = e.message || String(e);
        $('.sp-error').textContent = /Transmitting is switched off/.test(m) ? this._t.errTxOff : /APRS-IS is not connected/.test(m) ? this._t.errIsOff : m;
      }
    });
    programChanged(last.gateway || '', last.mode || 'SSB');
  }

  // New data on the APRS tab: only the lists and the map markers change, so the map
  // keeps its zoom and position, the lists their scroll, the form what was typed.
  _updateAprs() {
    const main = this.shadowRoot.querySelector('main.aprs');
    if (!main || !this._map) { this._render(); return; }
    const { msgs, heard } = this._aprsData();
    main.querySelector('.msgs-body').innerHTML = this._aprsMsgsHtml(msgs);
    main.querySelector('.heard-body').innerHTML = this._aprsHeardHtml(heard);
    this._drawMarkers();
  }
}

AprsKissPanel.prototype._tileToken = async function tileToken() {
  const now = Date.now();
  if (this._tile && now - this._tile.at < TILE_TOKEN_REFRESH_MS) return this._tile.token;
  try {
    const r = await this._hass.callWS({ type: 'map_tiles/access_token' });
    this._tile = { token: r.token, at: now };
    return r.token;
  } catch {
    return null;
  }
};

AprsKissPanel.prototype._mapData = function mapData() {
  const x = this._extra || {};
  const pos = x.position || [this._hass.config.latitude, this._hass.config.longitude];
  return {
    heard: x.heard || this._state.heard || [],
    me: { call: this._state.callsign, lat: pos[0], lon: pos[1], symbol: x.symbol || '/-' },
    track: x.my_track || [],
    tracked: new Set(x.tracked || []),
  };
};

AprsKissPanel.prototype._stationPopup = function stationPopup(h) {
  const t = this._t;
  const cs = (this._hass.language || '').startsWith('cs');
  const [pic, name] = symbolInfo(h.symbol_table, h.symbol, cs);
  const rf = !!h.last_rf;
  const freq = repeaterLabel(h);
  return `<b>${pic} ${esc(h.call)}</b>${name ? ` <small>${esc(name)}</small>` : ''}${h.object_of ? `<br><small>${cs ? 'objekt od' : 'object of'} ${esc(h.object_of)}</small>` : ''}
    <br>${time(h.last_heard)}${rf ? '' : '<br>🌐 ' + t.viaIs}${h.gated_by ? '<br>iGate ' + esc(h.gated_by) : ''}${freq ? '<br>📻 ' + esc(freq) : ''}
    ${wxText(h.weather) ? '<br>🌡 ' + esc(wxText(h.weather)) : ''}${h.speed ? `<br>${Math.round(h.speed)} km/h${h.course != null ? ' ' + Math.round(h.course) + '°' : ''}` : ''}
    ${h.comment ? '<br>' + esc(h.comment) : ''}${h.path?.length ? '<br><small>' + esc(h.path.join(',')) + '</small>' : ''}`;
};

AprsKissPanel.prototype._maps = async function maps() {
  const now = Date.now();
  if (this._mapsList && now - this._mapsList.at < 60000) return this._mapsList.maps;
  try {
    const r = await this._hass.callWS({ type: 'aprs_kiss/maps' });
    this._mapsList = { maps: r.maps || [], at: now };
  } catch { this._mapsList = { maps: [], at: now }; }
  return this._mapsList.maps;
};

AprsKissPanel.prototype._renderMap = async function renderMap(el) {
  const mod = await import(LEAFLET_JS);
  const L = mod.default ?? mod;  // the ESM build has named exports only
  if (!el.isConnected) return;
  const cs = (this._hass.language || '').startsWith('cs');
  const sm = new StationMap(L, el, {
    t: this._t, cs, popup: (h) => this._stationPopup(h), tileToken: () => this._tileToken(), maps: () => this._maps(),
  });
  this._L = L;
  this._map = sm.map;
  this._sm = sm;
  await sm.setBase();
  // Once the user zooms or moves the map, that view stays (also after switching tabs).
  let touched = false;
  for (const ev of ['pointerdown', 'wheel', 'touchstart']) el.addEventListener(ev, () => { touched = true; }, { passive: true });
  sm.map.on('moveend', () => { if (touched) this._mapView = { center: sm.map.getCenter(), zoom: sm.map.getZoom() }; });
  sm.update(this._mapData());
  if (this._mapView) sm.map.setView(this._mapView.center, this._mapView.zoom);
  else sm.fit();
  setTimeout(() => sm.map.invalidateSize(), 100);
};

AprsKissPanel.prototype._drawMarkers = function drawMarkers() {
  if (this._sm) this._sm.update(this._mapData());
};

// ─── header: the USB GPS ──────────────────────────────────────────────────

AprsKissPanel.prototype._gpsChip = function gpsChip() {
  const g = this._extra?.status?.gps;
  if (!g) return '';
  const t = this._t;
  const cls = g.fix ? 'ok' : g.connected ? '' : 'bad';
  return `<span class="chip" title="${esc(g.error || '')}"><span class="dot ${cls}"></span>GPS ${g.fix ? (g.satellites ?? '') + ' ' + t.gpsSats : t.gpsNoFix}</span>`;
};

// ─── a small dialog of our own (the panel lives in a shadow root) ─────────

AprsKissPanel.prototype._dialog = function dialog(html, wire) {
  const back = document.createElement('div');
  back.className = 'dialog-back';
  back.innerHTML = `<div class="dialog">${html}</div>`;
  this.shadowRoot.appendChild(back);
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  wire(back.querySelector('.dialog'), close);
  return close;
};

// ─── BBS SERVER or TAK instead of APRS ────────────────────────────────────

AprsKissPanel.prototype._setMode = async function setMode(mode) {
  const t = this._t;
  const go = async (sentence = '') => {
    try {
      await this._hass.callWS({ type: 'aprs_kiss/set_mode', mode, sentence, entry_id: this._state.entry_id });
    } catch (e) {
      return /sentence_required/.test(e.message || '') ? 'sentence' : (e.message || String(e));
    }
    this._tab = mode || 'aprs';
    try { localStorage.setItem('aprs-kiss-tab', this._tab); } catch { /* private mode */ }
    setTimeout(() => this._load(), 3500);  // the integration reloads
    return null;
  };
  if (!mode) { await go(); return; }
  const first = await go();  // typed once before: no question
  if (first !== 'sentence') { if (first) alert(first); return; }
  const bbs = mode === 'bbs';
  this._dialog(`<h3>${bbs ? t.bbsConfirmTitle : t.takConfirmTitle}</h3>
      <div>${bbs ? t.bbsConfirmAsk : t.takConfirmAsk}</div>
      <b style="user-select:text">${bbs ? t.bbsSentence : t.takSentence}</b>
      <input class="sentence" autocomplete="off"><div class="error"></div>
      <div class="row" style="justify-content:flex-end"><button class="btn secondary no">${t.cancel}</button><button class="btn yes">${t.switchOn}</button></div>`,
  (d, close) => {
    const input = d.querySelector('.sentence');
    input.focus();
    const yes = async () => {
      const r = await go(input.value);
      if (r === 'sentence') { d.querySelector('.error').textContent = t.sentenceWrong; return; }
      if (r) { d.querySelector('.error').textContent = r; return; }
      close();
    };
    d.querySelector('.yes').addEventListener('click', yes);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') yes(); });
    d.querySelector('.no').addEventListener('click', close);
  });
};

AprsKissPanel.prototype._exclusiveBanner = function exclusiveBanner(mode) {
  const t = this._t;
  return `<div class="banner"><b>${mode === 'bbs' ? 'BBS SERVER' : 'TAK'}</b> ${t.exclusive}
    <button class="btn secondary off">${t.switchOff}</button></div>`;
};

// ─── offline maps (Settings) ──────────────────────────────────────────────

const mb = (n) => (n >= 1e9 ? (n / 1e9).toFixed(1) + ' GB' : n >= 1e6 ? (n / 1e6).toFixed(0) + ' MB' : Math.max(1, Math.round(n / 1e3)) + ' kB');

AprsKissPanel.prototype._renderMapsCard = async function renderMapsCard(box) {
  const t = this._t;
  let r;
  try { r = await this._hass.callWS({ type: 'aprs_kiss/maps' }); } catch (e) { box.textContent = e.message || String(e); return; }
  this._mapsList = { maps: r.maps || [], at: Date.now() };
  box.classList.remove('hint');
  box.innerHTML = `<div class="hint">${t.mapsHint} <code>${esc(r.folder)}</code></div>
    ${r.maps.length ? r.maps.map((m) => `<div class="list-row"><div class="grow">${esc(m.name)}<small>${esc(m.file)} · zoom ${m.min_zoom}–${m.max_zoom}${m.size ? ' · ' + mb(m.size) : ''}</small></div>
      <button class="btn secondary rm" data-file="${esc(m.file)}">${t.mapsRemove}</button></div>`).join('') : `<div class="hint">${t.mapsNone}</div>`}
    ${r.failed.map((f) => `<div class="list-row"><div class="grow">${esc(f.file)}<small class="error">${t.mapsFailed}: ${esc(t.mapErr[f.error] || f.error)}</small></div></div>`).join('')}
    <div class="row"><label class="btn up">${t.mapsUpload}<input type="file" hidden accept=".mbtiles,.pmtiles,.sqlitedb,.zip,.7z"></label>
      <button class="btn secondary rescan">${t.mapsRescan}</button><span class="up-state hint"></span></div>`;
  box.querySelectorAll('.rm').forEach((b) => b.addEventListener('click', async () => {
    await this._hass.callWS({ type: 'aprs_kiss/maps_remove', file: b.dataset.file });
    this._renderMapsCard(box);
  }));
  box.querySelector('.rescan').addEventListener('click', () => this._renderMapsCard(box));
  box.querySelector('input[type=file]').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const state = box.querySelector('.up-state');
    state.textContent = `${t.mapsUploading} ${file.name} (${mb(file.size)})`;
    try {
      const res = await this._hass.fetchWithAuth(`/api/aprs_kiss/maps/upload?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
      const body = await res.json();
      if (!res.ok) { state.innerHTML = `<span class="error">${esc(t.mapErr[body.error] || body.error)}</span>`; return; }
    } catch (err) { state.innerHTML = `<span class="error">${esc(err.message || err)}</span>`; return; }
    this._mapsList = null;
    this._renderMapsCard(box);
  });
};

// ─── #APRSThursday ────────────────────────────────────────────────────────

const thursdayNow = () => new Date().getUTCDay() === 4;
const left = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

AprsKissPanel.prototype._renderThursday = function renderThursday(main) {
  const t = this._t;
  main.classList.add('scroll');
  main.innerHTML = `
    <div class="card"><div class="th-state"></div><div class="hint">${t.thAbout}</div><div class="hint">${t.thRf}</div>
      <div class="hint"><a href="https://aprs.to" target="_blank" rel="noreferrer">${t.thMap}</a></div></div>
    <div class="row msgrow"><input class="text th-text" maxlength="55" placeholder="${t.thPh}">
      <div class="seg" role="group" title="${t.viaTitle}">
        <button type="button" data-via="radio" class="${this._via() === 'radio' ? 'on' : ''}">📻</button><button type="button" data-via="both" class="${this._via() === 'both' ? 'on' : ''}">📻+🌐</button><button type="button" data-via="internet" class="${this._via() === 'internet' ? 'on' : ''}">🌐</button></div>
      <button class="btn th-send">${t.thSend}</button><button class="btn secondary th-leave">${t.thLeave}</button></div>
    <div class="error">${esc(this._error)}</div>
    <div class="chatlog th-log"></div>`;
  main.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
    this._viaChoice = b.dataset.via;
    main.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b));
  }));
  const send = async () => {
    const input = main.querySelector('.th-text');
    if (!input.value.trim()) return;
    if (await this._ws({ type: 'aprs_kiss/thursday_send', text: input.value.trim(), via: this._via() })) {
      input.value = '';
      await this._loadExtra();
      this._refreshTab();
    }
  };
  main.querySelector('.th-send').addEventListener('click', send);
  main.querySelector('.th-text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  main.querySelector('.th-leave').addEventListener('click', async () => {
    if (await this._ws({ type: 'aprs_kiss/thursday_leave', via: this._via() })) { await this._loadExtra(); this._refreshTab(); }
  });
  this._refreshTab = () => {
    const x = this._extra || {};
    const st = main.querySelector('.th-state');
    if (!st) return;
    const parts = [thursdayNow() ? `<b class="ok">${t.thRunning}</b>` : t.thNext];
    parts.push(x.thursday_member_until ? `${t.thMember} ${new Date(x.thursday_member_until * 1000).toLocaleString()}` : t.thNotMember);
    if (x.thursday_wait) parts.push(`${t.thWait} ${left(x.thursday_wait)}`);
    st.innerHTML = parts.join(' · ');
    const log = main.querySelector('.th-log');
    const items = x.thursday || [];
    log.innerHTML = items.length ? items.map((e) => `<div class="chatline ${e.kind === 'out' || e.kind === 'leave' ? 'out' : ''}"><span class="t">${time(e.time)}</span>
      <span class="c">${esc(e.from)}:</span>${e.kind === 'server' ? '<i>' + esc(e.text) + '</i>' : esc(e.text)}${e.via === 'internet' ? ' 🌐' : ''}</div>`).join('') : `<div class="hint">${t.thEmpty}</div>`;
    log.scrollTop = log.scrollHeight;
  };
  this._refreshTab();
};

// ─── Bulletins ────────────────────────────────────────────────────────────

const BLN_REACH = [50, 150, 500, 0];

AprsKissPanel.prototype._renderBulletins = function renderBulletins(main) {
  const t = this._t;
  const fill = (s, v) => s.replace(/\{(\w+)\}/g, (_m, k) => v[k] ?? '');
  const reach = () => Number(localStorage.getItem('aprs-kiss-bln-km') ?? 150);
  main.classList.add('scroll');
  main.innerHTML = `
    <div class="card"><h2>${t.blnNew}</h2>
      <div class="row" style="flex-wrap:wrap;gap:8px">
        <select class="b-kind"><option value="b">${t.blnKindB}</option><option value="a">${t.blnKindA}</option></select>
        <label>${t.blnLine} <select class="b-line"></select></label>
        <input class="b-group" maxlength="5" placeholder="${t.blnGroup}" style="width:160px">
        <label>${t.blnHours} <select class="b-hours">${[1, 4, 12, 24, 48].map((h) => `<option value="${h}">${h} h</option>`).join('')}</select></label>
      </div>
      <div class="row msgrow"><input class="text b-text" maxlength="67" placeholder="${t.blnText}">
        <div class="seg" role="group" title="${t.viaTitle}">
          <button type="button" data-via="radio" class="${this._via() === 'radio' ? 'on' : ''}">📻</button><button type="button" data-via="both" class="${this._via() === 'both' ? 'on' : ''}">📻+🌐</button><button type="button" data-via="internet" class="${this._via() === 'internet' ? 'on' : ''}">🌐</button></div>
        <button class="btn b-send">📢 ${t.blnSend}</button></div>
      <div class="hint">${t.blnAbout}</div></div>
    <div class="error">${esc(this._error)}</div>
    <div class="card"><div class="row" style="justify-content:space-between;align-items:center"><h2>${t.bulletins}</h2>
      <label>${t.blnReach} <select class="b-reach">${BLN_REACH.map((k) => `<option value="${k}" ${reach() === k ? 'selected' : ''}>${k ? fill(t.blnWithin, { km: k }) : t.blnAll}</option>`).join('')}</select></label></div>
      <div class="b-list"></div></div>`;
  const q = (c) => main.querySelector(c);
  const lines = () => {
    const ann = q('.b-kind').value === 'a';
    const chars = ann ? 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' : '0123456789';
    const taken = new Set(((this._extra || {}).bulletins?.mine || []).map((m) => m.addressee));
    const first = [...chars].find((c) => !taken.has(`BLN${c}`)) || chars[0];
    q('.b-line').innerHTML = [...chars].map((c) => `<option ${c === first ? 'selected' : ''}>${c}</option>`).join('');
    q('.b-group').hidden = ann;
    q('.b-hours').value = ann ? '24' : '4';
  };
  q('.b-kind').addEventListener('change', lines);
  q('.b-group').addEventListener('input', (e) => { e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''); });
  lines();
  main.querySelectorAll('.seg button').forEach((b) => b.addEventListener('click', () => {
    this._viaChoice = b.dataset.via;
    main.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b));
  }));
  q('.b-reach').addEventListener('change', (e) => { localStorage.setItem('aprs-kiss-bln-km', e.target.value); this._refreshTab(); });
  const send = async () => {
    const text = q('.b-text').value.trim();
    if (!text) return;
    const ann = q('.b-kind').value === 'a';
    if (await this._ws({ type: 'aprs_kiss/bulletin_send', line: q('.b-line').value, group: ann ? '' : q('.b-group').value.trim().toUpperCase(),
                         text, hours: Number(q('.b-hours').value), via: this._via() })) {
      q('.b-text').value = '';
      await this._loadExtra();
      lines();
      this._refreshTab();
    }
  };
  q('.b-send').addEventListener('click', send);
  q('.b-text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  this._ws({ type: 'aprs_kiss/bulletin_read' });
  const fresh = new Set();
  this._refreshTab = () => {
    const box = q('.b-list');
    if (!box) return;
    const b = (this._extra || {}).bulletins || { heard: [], mine: [] };
    const now = Date.now() / 1000;
    const km = reach();
    b.heard.forEach((e) => { if (!e.read) fresh.add(`${e.from}|${e.addressee}`); });
    const shown = b.heard.filter((e) => !km || e.via === 'radio' || (e.km != null && e.km <= km));
    const chip = (e) => `<b style="font-size:12px;padding:1px 8px;border-radius:10px;background:var(--secondary-background-color)">${esc(e.addressee)}${e.kind === 'announcement' ? ' · ' + t.blnAnn : ''}</b>`;
    const mine = b.mine.map((m) => `<div class="list-row" style="background:var(--secondary-background-color);border-radius:10px;padding:6px 10px;margin-bottom:6px">
        <div class="grow">${chip(m)} ${esc(m.text)}<br><small>${fill(t.blnSent, { n: m.sent })}${m.next > now ? ' · ' + fill(t.blnNext, { m: Math.max(1, Math.round((m.next - now) / 60)) }) : ''} · ${fill(t.blnUntil, { t: time(m.until) })}</small></div>
        <button class="btn secondary b-stop" data-a="${esc(m.addressee)}">${t.blnStop}</button></div>`).join('');
    const heard = shown.map((e) => `<div class="list-row"><div class="grow">${chip(e)} <b>${esc(e.from)}</b>
        ${fresh.has(`${e.from}|${e.addressee}`) ? `<b class="ok" style="font-size:11px">${t.blnNewTag}</b>` : ''}<br>${esc(e.text)}
        <br><small>${time(e.time)}${e.km != null ? ` · ${Math.round(e.km * 10) / 10} km` : ''} · ${e.via === 'radio' ? t.blnRadio : t.blnNet}${(e.count || 1) > 1 ? ' · ' + fill(t.blnTimes, { n: e.count }) : ''}</small></div>
        <button class="btn secondary b-del" data-s="${esc(e.from)}" data-a="${esc(e.addressee)}">${t.blnDelete}</button></div>`).join('');
    const head = (x) => `<div class="hint" style="font-weight:600;margin:8px 0 4px">${x}</div>`;
    box.innerHTML = (mine ? `${head(t.blnMine)}${mine}${head(t.blnHeard)}` : '')
      + (heard || `<div class="hint">${b.heard.length ? fill(t.blnHidden, { n: b.heard.length }) : t.blnEmpty}</div>`);
    box.querySelectorAll('.b-stop').forEach((x) => x.addEventListener('click', async () => {
      await this._ws({ type: 'aprs_kiss/bulletin_stop', addressee: x.dataset.a }); await this._loadExtra(); lines(); this._refreshTab();
    }));
    box.querySelectorAll('.b-del').forEach((x) => x.addEventListener('click', async () => {
      await this._ws({ type: 'aprs_kiss/bulletin_delete', sender: x.dataset.s, addressee: x.dataset.a }); await this._loadExtra(); this._refreshTab();
    }));
  };
  this._refreshTab();
};

// ─── BBS SERVER ───────────────────────────────────────────────────────────

AprsKissPanel.prototype._renderBbs = async function renderBbs(main) {
  const t = this._t;
  main.classList.add('scroll');
  main.innerHTML = '<div class="hint">…</div>';
  const b = await this._ws({ type: 'aprs_kiss/bbs' });
  if (!b) { main.innerHTML = `<div class="error">${esc(this._error)}</div>`; return; }
  const st = b.settings || {};
  main.innerHTML = `${this._exclusiveBanner('bbs')}
    <div class="hint">${b.error ? `<span class="error">${esc(b.error)}</span>` : `<span class="ok">${t.bbsRunning} ${esc(b.call || '')}</span>`}
      ${this._state.tx_enabled ? '' : ` · <span class="warn">${t.bbsTxNeeded}</span>`}</div>
    <div class="cols">
      <div class="card"><h2>${t.bbsConnected}</h2>${b.conns.length ? b.conns.map((c) => `<div class="list-row">${esc(c.remote)} <small>(${c.minutes} min)</small></div>`).join('') : `<div class="hint">${t.bbsNobody}</div>`}
        <h2 style="margin-top:12px">${t.bbsLog}</h2><div class="mono">${b.log.map(([tm, line]) => `${time(tm)}  ${esc(line)}`).join('\n')}</div></div>
      <div class="card"><h2>${t.bbsMessages}</h2>${b.messages.length ? b.messages.map((m) => `<div class="list-row"><div class="grow open" data-n="${m.number}" style="cursor:pointer">
          <span style="${m.read ? '' : 'font-weight:700'}">#${m.number} ${esc(m.kind)} ${esc(m.subject)}</span><small>${esc(m.from)} → ${esc(m.to)} · ${time(m.date)} · ${m.size} B</small></div>
          <button class="btn secondary del" data-n="${m.number}">${t.bbsDelete}</button></div>`).join('') : `<div class="hint">${t.bbsNoMessages}</div>`}</div>
    </div>
    <div class="card"><h2>${t.bbsSettings}</h2>
      ${st.error ? `<div class="error">${esc(st.error)}</div>` : ''}
      <div class="form" style="overflow:visible">
        <label class="field">${t.bbsSessions}<input type="number" min="1" class="b-max_sessions" value="${st.max_sessions ?? 2}"></label>
        <label class="field">${t.bbsIdle}<input type="number" min="10" class="b-idle_timeout_sec" value="${st.idle_timeout_sec ?? 600}"></label>
        <label class="field">${t.bbsTx}<input type="number" min="0" class="b-max_tx_min" value="${st.max_tx_min ?? 10}"></label>
        <label class="field">${t.bbsMax}<input type="number" min="0" class="b-max_messages" value="${st.max_messages ?? 500}"></label>
      </div>
      <label class="field">${t.bbsWelcome}<textarea rows="7" class="b-welcome">${esc(b.welcome || '')}</textarea></label>
      <div class="hint">${t.bbsMore} <code>${esc(b.folder)}</code></div>
      <div class="row"><button class="btn b-save">${t.save}</button><button class="btn secondary b-reload">${t.bbsReload}</button><span class="b-msg"></span></div>
    </div>`;
  main.querySelector('.banner .off').addEventListener('click', () => this._setMode(''));
  main.querySelectorAll('.del').forEach((x) => x.addEventListener('click', async () => {
    await this._ws({ type: 'aprs_kiss/bbs_delete', number: Number(x.dataset.n) });
    this._renderBbs(main);
  }));
  main.querySelectorAll('.open').forEach((x) => x.addEventListener('click', () => {
    const m = b.messages.find((y) => y.number === Number(x.dataset.n));
    this._dialog(`<h3>#${m.number} ${esc(m.subject)}</h3><small class="hint">${esc(m.from)} → ${esc(m.to)}${m.at ? ' @ ' + esc(m.at) : ''} · ${time(m.date)}</small>
      <div class="mono" style="max-height:60vh;overflow:auto">${esc(m.body)}</div><div class="row" style="justify-content:flex-end"><button class="btn secondary close">OK</button></div>`,
    (d, close) => d.querySelector('.close').addEventListener('click', close));
  }));
  main.querySelector('.b-save').addEventListener('click', async () => {
    const settings = {};
    for (const k of ['max_sessions', 'idle_timeout_sec', 'max_tx_min', 'max_messages']) settings[k] = Number(main.querySelector(`.b-${k}`).value);
    const r = await this._ws({ type: 'aprs_kiss/bbs_settings', settings, welcome: main.querySelector('.b-welcome').value });
    main.querySelector('.b-msg').innerHTML = r ? `<span class="ok">${t.saved.split(';')[0]}</span>` : `<span class="error">${esc(this._error)}</span>`;
  });
  main.querySelector('.b-reload').addEventListener('click', async () => {
    const r = await this._ws({ type: 'aprs_kiss/bbs_reload' });
    if (r) this._renderBbs(main);
  });
  this._refreshTab = () => { if (!main.querySelector('input:focus, textarea:focus')) this._renderBbs(main); };
};

// ─── TAK ──────────────────────────────────────────────────────────────────

AprsKissPanel.prototype._renderTak = function renderTak(main) {
  const t = this._t;
  main.classList.add('scroll');
  main.innerHTML = `${this._exclusiveBanner('tak')}
    <div class="row"><span class="tak-state hint"></span><button class="btn tak-pos">${t.takSendPos}</button></div>
    <div class="error">${esc(this._error)}</div>
    <div class="cols">
      <div class="card"><h2>${t.takStations}</h2><div class="tak-st"></div></div>
      <div class="card"><h2>${t.takChat}</h2><div class="chatlog tak-log" style="min-height:160px"></div>
        <div class="row" style="margin-top:8px"><select class="tak-to"></select><input class="tak-text" style="flex:1" placeholder="${t.chatPh}">
        <button class="btn tak-send">${t.send}</button></div></div>
    </div>`;
  main.querySelector('.banner .off').addEventListener('click', () => this._setMode(''));
  main.querySelector('.tak-pos').addEventListener('click', () => this._ws({ type: 'aprs_kiss/tak_position' }));
  const send = async () => {
    const input = main.querySelector('.tak-text');
    const sel = main.querySelector('.tak-to');
    if (!input.value.trim()) return;
    const opt = sel.selectedOptions[0];
    if (await this._ws({ type: 'aprs_kiss/tak_chat', text: input.value.trim(), to_uid: sel.value, to_callsign: sel.value ? opt.textContent : '' })) {
      input.value = '';
      await this._loadExtra();
      this._refreshTab();
    }
  };
  main.querySelector('.tak-send').addEventListener('click', send);
  main.querySelector('.tak-text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  this._refreshTab = () => {
    const tak = this._extra?.tak || { stations: [], chat: [] };
    const now = Date.now() / 1000;
    main.querySelector('.tak-state').textContent = `${t.takRunning} ${tak.callsign || ''}`;
    main.querySelector('.tak-st').innerHTML = tak.stations.length ? tak.stations.map((s) => `<div class="list-row"><div class="grow"><b>${esc(s.callsign)}</b> <small>${esc(s.team || '')} · ${esc(s.role || '')} · ${Math.round((now - s.received) / 60)} min · ${s.lat.toFixed(4)}, ${s.lon.toFixed(4)}${s.battery ? ' · 🔋' + s.battery + ' %' : ''}</small></div></div>`).join('') : `<div class="hint">${t.takNoStations}</div>`;
    const sel = main.querySelector('.tak-to');
    const keep = sel.value;
    sel.innerHTML = `<option value="">${t.takEverybody}</option>` + tak.stations.map((s) => `<option value="${esc(s.uid)}" ${s.uid === keep ? 'selected' : ''}>${esc(s.callsign)}</option>`).join('');
    const log = main.querySelector('.tak-log');
    log.innerHTML = tak.chat.length ? tak.chat.map((c) => `<div class="chatline ${c.out ? 'out' : ''}"><span class="t">${time(c.time)}</span><span class="c">${esc(c.from)}:</span>${c.to && c.to !== 'All' && c.to !== 'All Chat Rooms' ? `<span class="to">→ ${esc(c.to_callsign || c.to)}</span>` : ''}${esc(c.text)}</div>`).join('') : `<div class="hint">${t.takNoChat}</div>`;
    log.scrollTop = log.scrollHeight;
  };
  this._refreshTab();
};

if (!customElements.get('aprs-kiss-panel')) customElements.define('aprs-kiss-panel', AprsKissPanel);
