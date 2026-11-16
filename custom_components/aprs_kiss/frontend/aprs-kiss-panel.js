/* APRS & Packet panel: packet radio terminal, frame monitor and APRS messages. No build step. */

const TEXTS = {
  en: {
    terminal: 'Terminal', monitor: 'Monitor', aprs: 'APRS', tnc: 'TNC', online: 'connected', offline: 'not connected',
    tx: 'Transmit', on: 'on', off: 'off', connectTo: 'Connect to', via: 'via', connect: 'Connect', disconnect: 'Disconnect',
    unproto: 'Unproto', unprotoTo: 'Unproto to', send: 'Send', typeLine: 'Type and press Enter',
    notConnected: 'Not connected. Enter a callsign and press Connect, or switch to unproto.',
    pause: 'Pause', clear: 'Clear', to: 'To', message: 'Message', messages: 'Messages', heard: 'Stations heard',
    lastHeard: 'Last heard', position: 'Position', comment: 'Comment', noMessages: 'No messages yet.', map: 'Map', mapOffline: 'The map needs internet for its tiles (OpenStreetMap).', you: 'You',
    txOffHint: 'Transmitting is off. Switch it on to connect or send.', state: { pending: 'waiting for ack', acked: 'acknowledged', rejected: 'rejected', failed: 'no ack', sent: 'sent' },
  },
  cs: {
    terminal: 'Terminál', monitor: 'Monitor', aprs: 'APRS', tnc: 'TNC', online: 'připojeno', offline: 'nepřipojeno',
    tx: 'Vysílání', on: 'zapnuto', off: 'vypnuto', connectTo: 'Připojit k', via: 'přes', connect: 'Připojit', disconnect: 'Odpojit',
    unproto: 'Unproto', unprotoTo: 'Unproto na', send: 'Odeslat', typeLine: 'Napiš a stiskni Enter',
    notConnected: 'Nepřipojeno. Zadej značku a stiskni Připojit, nebo přepni na unproto.',
    pause: 'Pozastavit', clear: 'Vymazat', to: 'Komu', message: 'Zpráva', messages: 'Zprávy', heard: 'Slyšené stanice',
    lastHeard: 'Naposledy', position: 'Poloha', comment: 'Komentář', noMessages: 'Zatím žádné zprávy.', map: 'Mapa', mapOffline: 'Mapa potřebuje internet pro podklad (OpenStreetMap).', you: 'Ty',
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
    this._error = '';
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    this._t = TEXTS[(hass.language || 'en').startsWith('cs') ? 'cs' : 'en'];
    if (first) this._init();
  }

  set narrow(v) { this._narrow = v; }

  async _init() {
    this._renderShell();
    await this._load();
    this._unsub = await this._hass.connection.subscribeEvents((e) => this._onEvent(e.data), 'aprs_kiss_terminal');
    this._unsubState = await this._hass.connection.subscribeEvents(() => this._loadSoon(), 'state_changed');
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsubState?.();
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
      if (this._tab === 'aprs') this._render();
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
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css">
      <style>
        :host { display: block; height: 100%; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
        .page { display: flex; flex-direction: column; height: 100%; max-width: 1100px; margin: 0 auto; box-sizing: border-box; padding: 12px 16px; gap: 10px; }
        header { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
        h1 { font-size: 20px; margin: 0 8px 0 0; font-weight: 500; }
        .chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 14px; font-size: 13px; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
        .dot { width: 9px; height: 9px; border-radius: 50%; background: #9e9e9e; }
        .dot.ok { background: #43a047; } .dot.bad { background: #e53935; }
        button.chip { cursor: pointer; color: inherit; font: inherit; font-size: 13px; }
        button.chip.tx-on { background: rgba(229, 57, 53, 0.15); border-color: #e53935; }
        nav { display: flex; gap: 4px; border-bottom: 1px solid var(--divider-color); }
        nav button { background: none; border: none; padding: 8px 14px; font: inherit; color: var(--secondary-text-color); cursor: pointer; border-bottom: 2px solid transparent; }
        nav button.active { color: var(--primary-color); border-bottom-color: var(--primary-color); }
        main { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
        .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
        input, select { font: inherit; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
        input.call { width: 120px; text-transform: uppercase; } input.path { width: 160px; text-transform: uppercase; }
        button.btn { font: inherit; padding: 7px 14px; border-radius: 8px; border: none; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
        button.btn.secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
        button.btn:disabled { opacity: 0.5; cursor: default; }
        pre { flex: 1; min-height: 200px; margin: 0; overflow: auto; padding: 10px 12px; border-radius: 10px; background: #111; color: #d0d0d0; font: 13px/1.45 ui-monospace, 'DejaVu Sans Mono', Menlo, Consolas, monospace; white-space: pre-wrap; word-break: break-word; }
        pre .tx { color: #4fc3f7; } pre .st { color: #ffb74d; font-style: italic; } pre .out { color: #81c784; }
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
        .map { height: 380px; border-radius: 10px; overflow: hidden; }
        .leaflet-container { background: var(--secondary-background-color); font: inherit; }
        .leaflet-tooltip.call-label { background: rgba(0,0,0,.65); color: #fff; border: none; box-shadow: none; padding: 1px 5px; font-size: 11px; }
        .wx { display: inline-block; }
        td:nth-child(-n+2) { white-space: nowrap; }
        .call-label::before { display: none; }
      </style>

      <div class="page"><header></header><nav></nav><main></main></div>`;
  }

  _render() {
    if (!this.shadowRoot.querySelector('main')) this._renderShell();
    this._renderHeader();
    const t = this._t;
    const nav = this.shadowRoot.querySelector('nav');
    nav.innerHTML = ['terminal', 'monitor', 'aprs'].map((k) => `<button data-tab="${k}" class="${this._tab === k ? 'active' : ''}">${t[k]}</button>`).join('');
    nav.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      this._tab = b.dataset.tab;
      localStorage.setItem('aprs-kiss-tab', this._tab);
      this._render();
    }));
    const main = this.shadowRoot.querySelector('main');
    if (!this._state) {
      main.innerHTML = `<div class="error">${esc(this._error)}</div>`;
      return;
    }
    if (this._tab === 'terminal') this._renderTerminal(main);
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
      <h1>APRS & Packet · ${esc(s.callsign)}</h1>
      <span class="chip"><span class="dot ${s.tnc_connected ? 'ok' : 'bad'}"></span>${t.tnc} ${s.tnc_connected ? t.online : t.offline}</span>
      <button class="chip ${s.tx_enabled ? 'tx-on' : ''}" id="tx"><span class="dot ${s.tx_enabled ? 'bad' : ''}"></span>${t.tx}: ${s.tx_enabled ? t.on : t.off}</button>
      ${sessions ? `<span class="chip">${esc(sessions)}</span>` : ''}`;
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

  // ─── monitor ─────────────────────────────────────────────────────────

  _renderMonitor(main) {
    const t = this._t;
    main.innerHTML = `
      <div class="row"><label><input type="checkbox" class="pause" ${this._paused ? 'checked' : ''}> ${t.pause}</label>
      <button class="btn secondary clear">${t.clear}</button></div>
      <pre class="mon"></pre>`;
    const pre = main.querySelector('.mon');
    pre.textContent = this._state.monitor.join('\n') + '\n';
    pre.scrollTop = pre.scrollHeight;
    main.querySelector('.pause').addEventListener('change', (e) => { this._paused = e.target.checked; if (!this._paused) this._renderMonitor(main); });
    main.querySelector('.clear').addEventListener('click', () => { this._state.monitor = []; this._renderMonitor(main); });
  }

  _appendMonitor(line) {
    const pre = this.shadowRoot.querySelector('.mon');
    if (!pre) return;
    const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
    pre.appendChild(document.createTextNode(line + '\n'));
    if (atBottom) pre.scrollTop = pre.scrollHeight;
  }

  // ─── APRS ────────────────────────────────────────────────────────────

  _renderAprs(main) {
    const t = this._t;
    const msgs = [...this._state.messages].reverse();
    const heard = [...this._state.heard].sort((a, b) => b.last_heard - a.last_heard);
    main.innerHTML = `
      <div class="row">
        <input class="call to" placeholder="${t.to}" value="${esc(this._msgTo || '')}">
        <input class="text" style="flex:1;min-width:180px" maxlength="67" placeholder="${t.message}">
        <button class="btn sendmsg">${t.send}</button>
      </div>
      <div class="error">${esc(this._error)}</div>
      <div class="card"><h2>${t.map}</h2><div class="map"></div></div>
      <div class="cols">
        <div class="card"><h2>${t.messages}</h2>${msgs.length ? msgs.map((m) => `
          <div class="msg ${m.direction}">${esc(m.text)}
            <small>${m.direction === 'in' ? esc(m.from) : '→ ' + esc(m.to)} · ${time(m.time)}${m.direction === 'out' && m.state ? ' · ' + esc(t.state[m.state] || m.state) : ''}</small></div>`).join('') : `<div class="hint">${t.noMessages}</div>`}
        </div>
        <div class="card"><h2>${t.heard}</h2><table>
          <tr><th>Call</th><th>${t.lastHeard}</th><th>${t.position}</th><th>${t.comment}</th></tr>
          ${heard.map((h) => `<tr><td>${esc(h.call)}</td><td>${time(h.last_heard)}</td>
            <td>${h.latitude != null ? `${h.latitude.toFixed(4)}, ${h.longitude.toFixed(4)}` : ''}</td><td>${h.weather ? `<span class="wx">🌡 ${esc(wxText(h.weather))}</span><br>` : ''}${esc(h.comment || h.status || '')}</td></tr>`).join('')}
        </table></div>
      </div>`;
    const send = async () => {
      const to = main.querySelector('.to').value.trim().toUpperCase();
      const text = main.querySelector('.text').value.trim();
      if (!to || !text) return;
      this._msgTo = to;
      if (await this._ws({ type: 'aprs_kiss/send_message', to, text })) await this._loadStatus();
      this._render();
    };
    this._renderMap(main.querySelector('.map'), heard);
    main.querySelector('.sendmsg').addEventListener('click', send);
    main.querySelector('.text').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
  }
}

AprsKissPanel.prototype._renderMap = async function renderMap(el, heard) {
  let L;
  try {
    L = (await import('https://cdn.jsdelivr.net/npm/leaflet@1.9.4/+esm')).default;
  } catch {
    el.innerHTML = `<div class="hint" style="padding:12px">${this._t.mapOffline}</div>`;
    return;
  }
  const map = L.map(el, { zoomControl: true, attributionControl: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
  const points = [];
  const home = [this._hass.config.latitude, this._hass.config.longitude];
  L.circleMarker(home, { radius: 8, color: '#fff', weight: 2, fillColor: '#1e88e5', fillOpacity: 1 })
    .bindTooltip(`${esc(this._state.callsign)} (${this._t.you})`, { permanent: true, direction: 'right', className: 'call-label' }).addTo(map);
  points.push(home);
  for (const h of heard) {
    if (h.latitude == null || h.longitude == null) continue;
    const p = [h.latitude, h.longitude];
    points.push(p);
    L.circleMarker(p, { radius: 7, color: '#fff', weight: 2, fillColor: '#fb8c00', fillOpacity: 1 })
      .bindTooltip(esc(h.call), { permanent: true, direction: 'right', className: 'call-label' })
      .bindPopup(`<b>${esc(h.call)}</b><br>${time(h.last_heard)}${h.weather ? '<br>🌡 ' + esc(wxText(h.weather)) : ''}${h.comment ? '<br>' + esc(h.comment) : ''}${h.path?.length ? '<br><small>' + esc(h.path.join(',')) + '</small>' : ''}`)
      .addTo(map);
  }
  if (points.length > 1) map.fitBounds(points, { padding: [30, 30], maxZoom: 12 });
  else map.setView(home, 10);
  setTimeout(() => map.invalidateSize(), 100);
};

customElements.define('aprs-kiss-panel', AprsKissPanel);
