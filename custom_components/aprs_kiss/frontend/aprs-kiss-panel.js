/* APRS & Packet panel: packet radio terminal, frame monitor and APRS messages. No build step. */

// Everything the panel needs comes from Home Assistant: Leaflet is bundled with
// the integration, and map tiles come through Home Assistant's tile proxy.
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
    settings: 'Settings', callsign: 'Callsign', ssid: 'SSID', symbol: 'Icon (APRS symbol)', comment: 'Position comment', path: 'Digipeater path', beacon: 'Send position every (minutes, 0 = off, at least 10)', beaconIs: 'Send it regularly over the internet too (APRS-IS)', beaconHint: 'By radio while Transmit is on; over the internet only with this box ticked and APRS-IS connected. The position is Home Assistant\'s home, visible to everyone on aprs.fi.', tracked: 'Callsigns to track on the map', incoming: 'Accept incoming packet connections', txdelay: 'TX delay sent to the TNC (ms, 0 = leave)', station: 'Station', aprsis: 'APRS-IS (internet)', aprsisOn: 'Connect to APRS-IS', server: 'Server', port: 'Port', passcode: 'APRS-IS password (passcode)', licenceAsk: 'APRS-IS is for licensed radio amateurs only. To switch it on, type:', licenceText: 'I hold a valid amateur radio licence', licenceRequired: 'To switch APRS-IS on, type the sentence about your licence exactly as shown.', show: 'Show', hide: 'Hide', passHint: 'Empty: computed from your callsign (the standard APRS-IS passcode). Enter your own if you were given a different one.', passOwn: 'Your own passcode is saved. Clear the field to compute it from the callsign.', radius: 'Receive packets within (km of home, 0 = none)', igateRx: 'iGate: send packets heard on the radio to APRS-IS', igateTx: 'iGate: send internet messages to local stations by radio', unsaved: 'Changes are not saved yet: press Save.', save: 'Save', saved: 'Saved; the integration restarts with the new settings.', isState: 'APRS-IS', verified: 'logged in', unverified: 'connected, not verified (check the passcode)', disconnectedIs: 'not connected', passAuto: 'computed automatically', igateHint: 'Sending to APRS-IS needs no transmitter; gating to the radio needs Transmit on and a licence.', ssidHint: 'Usual meanings of the SSID:',
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
    settings: 'Nastavení', callsign: 'Značka', ssid: 'SSID', symbol: 'Ikona (APRS symbol)', comment: 'Komentář k poloze', path: 'Cesta přes digipeatery', beacon: 'Posílat polohu každých (minut, 0 = ne, nejméně 10)', beaconIs: 'Posílat pravidelně i přes internet (APRS-IS)', beaconHint: 'Rádiem, když je zapnuté vysílání; přes internet jen se zaškrtnutím a připojeným APRS-IS. Poloha je domov z Home Assistantu, na aprs.fi ji uvidí každý.', tracked: 'Značky sledované na mapě', incoming: 'Přijímat příchozí packet spojení', txdelay: 'TX delay pro TNC (ms, 0 = neměnit)', station: 'Stanice', aprsis: 'APRS-IS (internet)', aprsisOn: 'Připojit se k APRS-IS', server: 'Server', port: 'Port', passcode: 'Heslo pro APRS-IS (passcode)', licenceAsk: 'APRS-IS je jen pro radioamatéry s licencí. Pro zapnutí napiš:', licenceText: 'mám platnou radioamatérskou licenci', licenceRequired: 'Pro zapnutí APRS-IS napiš větu o licenci přesně tak, jak je uvedená.', show: 'Zobrazit', hide: 'Skrýt', passHint: 'Prázdné: spočítá se z tvé značky (standardní passcode APRS-IS). Zadej vlastní, pokud ti bylo přiděleno jiné.', passOwn: 'Je uložené tvoje vlastní heslo. Smazáním pole se bude počítat ze značky.', radius: 'Přijímat pakety do (km od domova, 0 = žádné)', igateRx: 'iGate: posílat pakety slyšené rádiem do APRS-IS', igateTx: 'iGate: zprávy z internetu pro místní stanice vysílat rádiem', unsaved: 'Změny ještě nejsou uložené: klikni na Uložit.', save: 'Uložit', saved: 'Uloženo; integrace se restartuje s novým nastavením.', isState: 'APRS-IS', verified: 'přihlášeno', unverified: 'připojeno, neověřeno (zkontroluj passcode)', disconnectedIs: 'nepřipojeno', passAuto: 'spočítá se automaticky', igateHint: 'Posílání do APRS-IS nepotřebuje vysílač; brána do rádia potřebuje zapnuté vysílání a licenci.', ssidHint: 'Obvyklé významy SSID:',
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

/** APRS weather (aprslib units: °C, m/s, mm, hPa, %) as a short line. */
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
    } catch (err) {
      this._error = err.message || String(err);
    }
    this._render();
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
      this._renderHeader();
      if (this._tab === 'aprs') this._updateAprs();
    } catch { /* keep the last state */ }
  }

  _onEvent(d) {
    if (!this._state || d.entry_id !== this._state.entry_id) return;
    if (d.kind === 'monitor') {
      this._state.monitor.push(d.line);
      if (this._state.monitor.length > 500) this._state.monitor.shift();
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
        .form { align-content: start; } .callrow input.f-pass { text-transform: none; }
        .field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
        .field input, .field select { color: var(--primary-text-color); }
        .field.check { flex-direction: row; align-items: center; gap: 8px; color: var(--primary-text-color); font-size: 14px; }
        .callrow { display: flex; gap: 8px; } .callrow input { flex: 1; text-transform: uppercase; } .callrow select { width: 90px; }
        .ok { color: var(--success-color, #43a047); font-size: 13px; }
        pre .tx { color: var(--primary-color); } pre .st { color: var(--warning-color, #ef6c00); font-style: italic; } pre .out { color: var(--success-color, #2e7d32); }
        .line { display: flex; gap: 8px; } .line input { flex: 1; font-family: ui-monospace, monospace; }
        .hint { font-size: 13px; color: var(--secondary-text-color); }
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
      </style>

      <div class="page"><div class="top"><div class="update" hidden></div><header></header><nav></nav></div><main></main></div>`;
  }

  _render() {
    if (!this.shadowRoot.querySelector('main')) this._renderShell();
    this._renderHeader();
    const t = this._t;
    const nav = this.shadowRoot.querySelector('nav');
    nav.innerHTML = ['chat', 'terminal', 'monitor', 'aprs', 'settings'].map((k) => k === 'settings'
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
    if (this._tab === 'settings') this._renderSettings(main);
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
          <label class="field check"><input type="checkbox" class="f-beacon-is" ${st.beacon_is ? 'checked' : ''}> ${t.beaconIs}</label>
          <div class="hint">${t.beaconHint}</div>
          <label class="field">${t.tracked}<input class="f-tracked" value="${esc(st.tracked_callsigns || '')}" placeholder="OK1SIM-9, OK1ABC-7"></label>
          <label class="field check"><input type="checkbox" class="f-incoming" ${st.accept_incoming ? 'checked' : ''}> ${t.incoming}</label>
          <label class="field">${t.txdelay}<input class="f-txdelay" type="number" min="0" max="1000" step="10" value="${st.txdelay_ms || 0}"></label>
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
          <label class="field">${t.radius}<input class="f-radius" type="number" min="0" max="500" value="${st.aprsis_radius_km ?? 50}"></label>
          <label class="field check"><input type="checkbox" class="f-irx" ${st.igate_rx ? 'checked' : ''}> ${t.igateRx}</label>
          <label class="field check"><input type="checkbox" class="f-itx" ${st.igate_tx ? 'checked' : ''}> ${t.igateTx}</label>
          <div class="hint">${t.igateHint}</div>
        </div>
      </div>
      <div class="row"><button class="btn save">${t.save}</button><span class="msg-saved"></span><span class="error">${esc(this._error)}</span></div>`;
    const q = (c) => main.querySelector(c);
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
        licence_text: q('.f-licence').value,
      };
      // Errors stay next to the button; re-rendering would lose what was typed.
      const err = main.querySelector('.row .error');
      err.textContent = '';
      let r = null;
      try {
        r = await this._hass.callWS({ type: 'aprs_kiss/set_settings', settings, entry_id: this._state?.entry_id });
      } catch (e) {
        const text = e.message || String(e);
        err.textContent = /licence_required/.test(text) ? t.licenceRequired : text;
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
    pre.textContent = this._state.monitor.filter((l) => this._monIs || !isIsLine(l)).join('\n') + '\n';
    pre.scrollTop = pre.scrollHeight;
    main.querySelector('.pause').addEventListener('change', (e) => { this._paused = e.target.checked; if (!this._paused) this._renderMonitor(main); });
    main.querySelector('.mon-is').addEventListener('change', (e) => {
      this._monIs = e.target.checked;
      try { localStorage.setItem('aprs-kiss-mon-is', this._monIs ? '1' : '0'); } catch { /* private mode */ }
      this._renderMonitor(main);
    });
    main.querySelector('.clear').addEventListener('click', () => { this._state.monitor = []; this._renderMonitor(main); });
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
  _via() {
    if (!this._viaChoice) {
      try { this._viaChoice = localStorage.getItem('aprs-kiss-via'); } catch { /* private mode */ }
    }
    return this._viaChoice || (this._state?.tx_enabled ? 'radio' : 'internet');
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
      ${heard.map((h) => `<tr><td>${h.last_rf ? '' : `<span title="${t.viaIs}">🌐 </span>`}${esc(h.call)}</td><td>${time(h.last_heard)}</td>
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
          <button type="button" data-via="radio" class="${this._via() === 'radio' ? 'on' : ''}">📻 ${t.viaRadio}</button><button type="button" data-via="internet" class="${this._via() === 'internet' ? 'on' : ''}">🌐 ${t.viaNet}</button>
        </div>
        <input class="text" maxlength="67" placeholder="${t.message}">
        <button class="btn sendmsg">${t.send}</button>
      </div>
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
      try { localStorage.setItem('aprs-kiss-via', this._viaChoice); } catch { /* private mode */ }
      main.querySelectorAll('.seg button').forEach((x) => x.classList.toggle('on', x === b));
    }));
    this._map = null;
    this._renderMap(main.querySelector('.map'), heard);
    main.querySelector('.sendmsg').addEventListener('click', send);
    main.querySelector('.text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  }

  // New data on the APRS tab: only the lists and the map markers change, so the map
  // keeps its zoom and position, the lists their scroll, the form what was typed.
  _updateAprs() {
    const main = this.shadowRoot.querySelector('main.aprs');
    if (!main || !this._map) { this._render(); return; }
    const { msgs, heard } = this._aprsData();
    main.querySelector('.msgs-body').innerHTML = this._aprsMsgsHtml(msgs);
    main.querySelector('.heard-body').innerHTML = this._aprsHeardHtml(heard);
    this._drawMarkers(heard);
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

AprsKissPanel.prototype._renderMap = async function renderMap(el, heard) {
  const mod = await import(LEAFLET_JS);
  const L = mod.default ?? mod;  // the ESM build has named exports only
  if (!el.isConnected) return;
  const map = L.map(el, { zoomControl: true, attributionControl: true });
  const tileUrl = (token) => `/api/map_tiles/raster/{z}/{x}/{y}.png?token=${encodeURIComponent(token)}`;
  const token = await this._tileToken();
  if (token) {
    const layer = L.tileLayer(tileUrl(token), { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
    // The token rotates; keep the layer working while the panel stays open.
    clearInterval(this._tileTimer);
    this._tileTimer = setInterval(async () => {
      if (!el.isConnected) { clearInterval(this._tileTimer); return; }
      const t = await this._tileToken();
      if (t) layer.setUrl(tileUrl(t), true);
    }, TILE_TOKEN_REFRESH_MS);
  } else {
    const note = L.control({ position: 'bottomleft' });
    note.onAdd = () => Object.assign(document.createElement('div'), { className: 'hint', textContent: this._t.mapOffline, style: 'background:var(--card-background-color);padding:4px 8px;border-radius:6px' });
    note.addTo(map);
  }
  this._L = L;
  this._map = map;
  this._markers = L.layerGroup().addTo(map);
  // Once the user zooms or moves the map, that view stays (also after switching tabs).
  let touched = false;
  for (const ev of ['pointerdown', 'wheel', 'touchstart']) el.addEventListener(ev, () => { touched = true; }, { passive: true });
  map.on('moveend', () => { if (touched) this._mapView = { center: map.getCenter(), zoom: map.getZoom() }; });
  if (this._mapView) map.setView(this._mapView.center, this._mapView.zoom);
  this._drawMarkers(heard);
  setTimeout(() => map.invalidateSize(), 100);
};

// A small popup that fits a phone's map: it scrolls inside when long, and the map
// moves so the popup stays clear of the zoom buttons (top left).
const POPUP = { className: 'aprs-pop', maxWidth: 230, maxHeight: 150, autoPanPaddingTopLeft: [52, 10], autoPanPaddingBottomRight: [10, 30] };

AprsKissPanel.prototype._drawMarkers = function drawMarkers(heard) {
  const L = this._L;
  const map = this._map;
  if (!L || !map) return;
  if (map._popup && map.hasLayer(map._popup)) return;  // don't close a popup being read
  this._markers.clearLayers();
  const points = [];
  const home = [this._hass.config.latitude, this._hass.config.longitude];
  L.circleMarker(home, { radius: 8, color: '#fff', weight: 2, fillColor: '#1e88e5', fillOpacity: 1 })
    .bindTooltip(`${esc(this._state.callsign)} (${this._t.you})`, { permanent: true, direction: 'right', className: 'call-label' }).addTo(this._markers);
  points.push(home);
  for (const h of heard) {
    if (h.latitude == null || h.longitude == null) continue;
    const p = [h.latitude, h.longitude];
    points.push(p);
    // Orange: heard by the radio; purple: seen only on APRS-IS.
    const rf = !!h.last_rf;
    L.circleMarker(p, { radius: rf ? 7 : 6, color: '#fff', weight: 2, fillColor: rf ? '#fb8c00' : '#8e24aa', fillOpacity: rf ? 1 : 0.85 })
      .bindTooltip(`${rf ? '' : '🌐 '}${esc(h.call)}`, { permanent: true, direction: 'right', className: 'call-label' })
      .bindPopup(`<b>${esc(h.call)}</b><br>${time(h.last_heard)}${rf ? '' : '<br>🌐 ' + this._t.viaIs}${wxText(h.weather) ? '<br>🌡 ' + esc(wxText(h.weather)) : ''}${h.comment ? '<br>' + esc(h.comment) : ''}${h.path?.length ? '<br><small>' + esc(h.path.join(',')) + '</small>' : ''}`, POPUP)
      .addTo(this._markers);
  }
  if (this._mapView) return;  // the user's view wins
  if (points.length > 1) map.fitBounds(points, { padding: [30, 30], maxZoom: 12 });
  else map.setView(home, 10);
};

if (!customElements.get('aprs-kiss-panel')) customElements.define('aprs-kiss-panel', AprsKissPanel);
