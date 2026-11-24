/* The APRS map of the panel: the same map as in the APRS & Packet app.
 *
 * - each station is its APRS symbol on a light disc with its callsign below (a repeater also with its
 *   frequency, band and mode);
 * - stations that would cover each other are moved apart, a thin grey line leads to where they really
 *   are (port of the app's declutter.py);
 * - trails: where moving stations went in the last half hour;
 * - filters: weather stations, moving stations, repeaters, road incidents (port of mapfilter.py and
 *   repeater.py);
 * - the base map: OpenStreetMap through Home Assistant, the user's own offline maps (MBTiles, PMTiles…)
 *   from Home Assistant, or the bundled basic map (borders, roads, cities; works with no internet).
 */

import { ALL, UNKNOWN } from './symbols.js';

const WORLD_URL = new URL('world.json', import.meta.url).href;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ─── symbols ──────────────────────────────────────────────────────────────

export function symbolInfo(table, code, cs) {
  if (!code) return [UNKNOWN, ''];
  table = table || '/';
  const found = ALL[table + code];
  if (!found && !'/\\'.includes(table)) {
    const base = ALL['\\' + code];
    if (base) return [base[0], `${cs ? base[2] : base[1]} (${cs ? 'překryv' : 'overlay'} ${table})`];
  }
  if (!found) return [UNKNOWN, `${table}${code}`];
  return [found[0], cs ? found[2] : found[1]];
}

// ─── what a station is (mapfilter.py, repeater.py) ────────────────────────

const MOVING_SECONDS = 600;
const MOVING_KMH = 3;
const ROAD_ALTERNATE = new Set("'!jw{*eB");
const alternate = (table) => !!table && table !== '/';

export function isWeather(e) {
  if (e.weather && Object.keys(e.weather).length) return true;
  return e.symbol === '_' || (e.symbol === 'W' && (e.symbol_table === '/' || alternate(e.symbol_table)));
}

export const isRoad = (e) => alternate(e.symbol_table) && ROAD_ALTERNATE.has(e.symbol || '');

export function isMoving(e, now) {
  const track = e.track || [];
  if (track.length >= 2 && now - track[track.length - 2][0] <= MOVING_SECONDS) return true;
  const recent = now - (e.last_heard || 0) <= MOVING_SECONDS;
  if (recent && (e.speed || 0) > MOVING_KMH && !e.weather) return true;
  return e.first_heard != null && now - e.first_heard < MOVING_SECONDS;  // too new to know: shown until it stays put
}

const FREQ_RE = /(?<![\d.])(\d{2,4}\.\d{2,5})\s?MHz/gi;
const NAME_FREQ_RE = /^(\d{2,4}\.\d{1,5})/;
const SHIFT_RE = /(?:^|\s)(?:[+-]\d{3}\b|[+-]\d{1,2}\.\d+\s?MHz|T\d{3}\b|C\d{3}\b|Toff\b|R\d{2}[km]\b|1750)/i;
const MOBILE = new Set("><[bkuvjRUsY'XO=*afP");
const BANDS = [[28, 29.7, '10 m'], [50, 54, '6 m'], [70, 71, '4 m'], [144, 148, '2 m'], [219, 225, '1.25 m'],
  [420, 450, '70 cm'], [902, 928, '33 cm'], [1240, 1300, '23 cm']];
const MODES = [['DMR', 'DMR'], ['D-STAR', 'D-Star'], ['DSTAR', 'D-Star'], ['C4FM', 'C4FM'], ['YSF', 'C4FM'],
  ['FUSION', 'C4FM'], ['NXDN', 'NXDN'], ['P25', 'P25'], ['TETRA', 'TETRA'], ['M17', 'M17']];
const band = (mhz) => (BANDS.find(([lo, hi]) => mhz >= lo && mhz <= hi) || [])[2] || null;

function frequency(e) {
  const plausible = (v) => { const f = parseFloat(v); return band(f) ? f : null; };
  if (e.object_of) {
    const m = NAME_FREQ_RE.exec(e.call || '');
    if (m && plausible(m[1])) return plausible(m[1]);
  }
  for (const text of [e.comment, e.status]) {
    if (typeof text !== 'string') continue;
    for (const m of text.matchAll(FREQ_RE)) { if (plausible(m[1])) return plausible(m[1]); }
  }
  return null;
}

export function isRepeater(e) {
  if (e.symbol === 'r') return true;
  if (MOBILE.has(e.symbol) && e.symbol_table === '/') return false;
  if (frequency(e) == null) return false;
  if (e.object_of) return true;
  return SHIFT_RE.test(e.comment || '');
}

/** "439.350 · 70 cm · DMR" for a repeater, null for anything else. */
export function repeaterLabel(e) {
  if (!isRepeater(e)) return null;
  const mhz = frequency(e);
  if (mhz == null) return null;
  let text = mhz.toFixed(4).replace(/0+$/, '');
  if (text.split('.')[1].length < 3) text = mhz.toFixed(3);
  const up = `${e.call || ''} ${e.comment || ''}`.toUpperCase();
  const mode = (MODES.find(([k]) => up.includes(k)) || [])[1];
  return [text, band(mhz), mode].filter(Boolean).join(' · ');
}

/** A weather station's temperature for the second line of its tag ("4.8 °C", "4,8 °C" in Czech). */
export function temperatureLabel(e, cs) {
  const temp = e.weather?.temperature;
  if (typeof temp !== 'number') return null;
  const text = temp.toFixed(1);
  return `${cs ? text.replace('.', ',') : text} °C`;
}

export const FILTERS = ['weather', 'moving', 'repeater', 'road'];

function shown(e, kinds, now) {
  if (!kinds.size) return true;
  return (kinds.has('weather') && isWeather(e)) || (kinds.has('road') && isRoad(e))
    || (kinds.has('repeater') && isRepeater(e)) || (kinds.has('moving') && isMoving(e, now));
}

// ─── markers that would cover each other move apart (declutter.py) ────────

const CLOSE_X = 66;
const CLOSE_Y = 48;
const RINGS = [54, 78, 104, 132, 160];
const DIRECTIONS = 12;
const SAME_PX = 10;
const MIN_SPREAD_ZOOM = 9;
const OFFSETS = (() => {
  const out = [[0, 0]];
  RINGS.forEach((r, ring) => {
    const turn = Math.PI / DIRECTIONS * (ring % 2);
    for (let k = 0; k < DIRECTIONS; k++) {
      const a = -Math.PI / 2 + 2 * Math.PI * k / DIRECTIONS + turn;
      out.push([r * Math.cos(a), r * Math.sin(a)]);
    }
  });
  return out;
})();

/** Screen positions (pixels) -> where to draw each; `fixed` (our own station) never moves. */
export function spread(px, zoom, fixed = null) {
  const shownAt = px.map((p) => [...p]);
  if (zoom < MIN_SPREAD_ZOOM) return shownAt;
  const grid = new Map();
  const cell = (x, y) => `${Math.floor(x / CLOSE_X)},${Math.floor(y / CLOSE_Y)}`;
  const free = (x, y) => {
    const cx = Math.floor(x / CLOSE_X), cy = Math.floor(y / CLOSE_Y);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const [px2, py2] of grid.get(`${cx + dx},${cy + dy}`) || []) {
        if (Math.abs(px2 - x) < CLOSE_X && Math.abs(py2 - y) < CLOSE_Y) return false;
      }
    }
    return true;
  };
  const take = (x, y) => { const k = cell(x, y); if (!grid.has(k)) grid.set(k, []); grid.get(k).push([x, y]); };
  // several stations at one place: none stays on it, the place is kept for its dot
  const shared = new Set();
  const cells = new Map();
  px.forEach(([x, y], i) => {
    const cx = Math.floor(x / SAME_PX), cy = Math.floor(y / SAME_PX);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const j of cells.get(`${cx + dx},${cy + dy}`) || []) {
        if (Math.abs(px[j][0] - x) < SAME_PX && Math.abs(px[j][1] - y) < SAME_PX) { shared.add(i); shared.add(j); }
      }
    }
    const k = `${cx},${cy}`;
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k).push(i);
  });
  shared.delete(fixed);
  for (const i of shared) take(...px[i]);
  const order = px.map((_, i) => i);
  if (fixed != null && fixed >= 0 && fixed < px.length) { order.splice(fixed, 1); order.unshift(fixed); }
  for (const i of order) {
    const [x, y] = px[i];
    if (i === fixed) { take(x, y); continue; }
    let placed = false;
    for (const [ox, oy] of shared.has(i) ? OFFSETS.slice(1) : OFFSETS) {
      if (free(x + ox, y + oy)) { shownAt[i] = [x + ox, y + oy]; take(x + ox, y + oy); placed = true; break; }
    }
    if (!placed) take(x, y);
  }
  return shownAt;
}

// ─── the bundled basic map (offline_map.py) ───────────────────────────────

let worldPromise = null;
const world = () => (worldPromise ||= fetch(WORLD_URL).then((r) => r.json()).then((d) => {
  for (const key of ['borders', 'coast', 'motorways', 'roads']) {
    d[key] = (d[key] || []).map((line) => {
      let s = 90, n = -90, w = 180, e = -180;
      for (const [lat, lon] of line) { s = Math.min(s, lat); n = Math.max(n, lat); w = Math.min(w, lon); e = Math.max(e, lon); }
      return { line, s, n, w, e };
    });
  }
  return d;
}).catch(() => ({ borders: [], coast: [], motorways: [], roads: [], cities: [], towns: [], peaks: [] })));

const CITY_TIERS = [[4, (pop, cap) => cap && pop >= 2e6], [6, (pop, cap) => cap || pop >= 1e6],
  [7.5, (pop, cap) => cap || pop >= 3e5], [99, () => true]];
const TOWN_TIERS = [[8.5, null], [9.5, 20000], [10.5, 10000], [11.5, 5000], [12.5, 2000], [99, 0]];
const PEAK_TIERS = [[7, null], [8.5, 1], [10, 5], [11, 15], [99, 99]];
const ROAD_TIERS = [[5, false, false], [7.5, true, false], [99, true, true]];
const limit = (tiers, zoom) => tiers.find((t) => zoom < t[0]);

class BasicMap {
  constructor(L, map) {
    this.L = L;
    this.map = map;
    this.renderer = L.canvas({ padding: 0.5 });
    this.lines = L.layerGroup();
    this.places = L.layerGroup();
    this.box = null;
  }

  addTo(map) { this.lines.addTo(map); this.places.addTo(map); this.refresh(true); return this; }

  remove() { this.lines.remove(); this.places.remove(); }

  async refresh(force = false) {
    const d = await world();
    const map = this.map;
    if (!map.hasLayer(this.lines)) return;
    const zoom = map.getZoom();
    const view = map.getBounds().pad(0.6);
    if (!force && this.box && this.box.zoom === zoom && this.box.bounds.contains(map.getBounds())) return;
    this.box = { zoom, bounds: view };
    const s = view.getSouth(), n = view.getNorth(), w = view.getWest(), e = view.getEast();
    const inBox = (it) => it.n >= s && it.s <= n && it.e >= w && it.w <= e;
    const L = this.L;
    this.lines.clearLayers();
    const draw = (items, color, weight) => {
      const lines = items.filter(inBox).map((it) => it.line);
      if (lines.length) L.polyline(lines, { color, weight, interactive: false, renderer: this.renderer, smoothFactor: 1.5 }).addTo(this.lines);
    };
    draw(d.coast, '#4A7FB0', 1);
    const [, motorways, mainRoads] = limit(ROAD_TIERS, zoom);
    if (mainRoads) draw(d.roads, '#FFB74D', 1.2);
    if (motorways) draw(d.motorways, '#E57373', 2);
    draw(d.borders, '#7B5EA7', 1.4);
    this.places.clearLayers();
    const here = map.getBounds().pad(0.2);
    const label = (lat, lon, html) => L.marker([lat, lon], { interactive: false, keyboard: false,
      icon: L.divIcon({ className: 'place', html, iconSize: [140, 30], iconAnchor: [70, 4] }) }).addTo(this.places);
    const peaks = limit(PEAK_TIERS, zoom)[1];
    if (peaks != null) for (const [name, lat, lon, m, rank] of d.peaks || []) {
      if (rank < peaks && here.contains([lat, lon])) label(lat, lon, `<span class="peak">▲<br>${esc(name)} ${m} m</span>`);
    }
    const towns = limit(TOWN_TIERS, zoom)[1];
    if (towns != null) {
      let n = 0;
      for (const [name, lat, lon, pop] of d.towns || []) {
        if (pop >= towns && here.contains([lat, lon]) && n++ < 400) label(lat, lon, `<span class="town">•<br>${esc(name)}</span>`);
      }
    }
    const keep = limit(CITY_TIERS, zoom)[1];
    for (const [name, lat, lon, pop, cap] of d.cities || []) {
      if (keep(pop, !!cap) && here.contains([lat, lon])) label(lat, lon, `<span class="city${cap ? ' cap' : ''}">●<br>${esc(name)}</span>`);
    }
  }
}

// ─── the map ──────────────────────────────────────────────────────────────

// Material Design Icons (Apache 2.0), as Home Assistant uses them
const ICON = {
  layers: 'M12,16L19.36,10.27L21,9L12,2L3,9L4.63,10.27M12,18.54L4.62,12.81L3,14.07L12,21.07L21,14.07L19.37,12.8L12,18.54Z',
  filter: 'M14,12V19.88C14.04,20.18 13.94,20.5 13.71,20.71C13.32,21.1 12.69,21.1 12.3,20.71L10.29,18.7C10.06,18.47 9.96,18.16 10,17.87V12H9.97L4.21,4.62C3.87,4.19 3.95,3.56 4.38,3.22C4.57,3.08 4.78,3 5,3V3H19V3C19.22,3 19.43,3.08 19.62,3.22C20.05,3.56 20.13,4.19 19.79,4.62L14.03,12H14Z',
  trails: 'M3.5,18.5L9.5,12.5L13.5,16.5L22,6.92L20.59,5.5L13.5,13.5L9.5,9.5L2,17L3.5,18.5Z',
  earth: 'M17.9,17.39C17.64,16.59 16.89,16 16,16H15V13A1,1 0 0,0 14,12H8V10H10A1,1 0 0,0 11,9V7H13A2,2 0 0,0 15,5V4.59C17.93,5.77 20,8.64 20,12C20,14.08 19.2,15.97 17.9,17.39M11,19.93C7.05,19.44 4,16.08 4,12C4,11.38 4.08,10.78 4.21,10.21L9,15V16A2,2 0 0,0 11,18M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z',
};
const svg = (d) => `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="${d}"/></svg>`;
const short = (text) => String(text).split(' (')[0];  // one line in the menu

const TRAIL_SECONDS = 1800;
const TRAIL_COLOR = '#E53935';
const LEADER_COLOR = '#8E8E8E';
const COLORS = { rf: 'c-rf', is: 'c-is', tracked: 'c-tr', me: 'c-me' };

export class StationMap {
  /**
   * opts: { t (texts), cs, popup(h) -> html, tileToken() -> token|null, maps() -> [{url, min_zoom, max_zoom,
   *         bounds, attribution}], onView(view) }
   */
  constructor(L, el, opts) {
    this.L = L;
    this.el = el;
    this.opts = opts;
    this.prefs = { source: 'auto', filters: [], trails: false, internet: true, ...readPrefs() };
    const map = this.map = L.map(el, { zoomControl: true, attributionControl: true, minZoom: 3 });
    this.base = L.layerGroup().addTo(map);
    this.basic = new BasicMap(L, map);
    this.trails = L.layerGroup().addTo(map);
    this.leaders = L.layerGroup().addTo(map);
    this.markers = L.layerGroup().addTo(map);
    this.data = { heard: [], me: null, track: [], tracked: new Set() };
    map.on('zoomend', () => this.draw());
    map.on('moveend', () => { if (this.basic.lines._map) this.basic.refresh(); });
    this._toolbar();
  }

  savePrefs() { try { localStorage.setItem('aprs-kiss-map', JSON.stringify(this.prefs)); } catch { /* private mode */ } }

  async setBase() {
    const L = this.L;
    const map = this.map;
    this.base.clearLayers();
    this.basic.remove();
    this.el.classList.remove('basic');
    let source = this.prefs.source;
    const token = source === 'online' || source === 'auto' ? await this.opts.tileToken() : null;
    const imported = await this.opts.maps();
    if (source === 'auto') source = token ? 'online' : imported.length ? 'imported' : 'basic';
    if (source === 'imported' && !imported.length) source = 'basic';
    if (source === 'online' && !token) source = 'basic';
    this.current = source;
    if (source === 'online') {
      const url = (tk) => `/api/map_tiles/raster/{z}/{x}/{y}.png?token=${encodeURIComponent(tk)}`;
      const layer = L.tileLayer(url(token), { maxZoom: 19, maxNativeZoom: 18, attribution: '© OpenStreetMap' }).addTo(this.base);
      clearInterval(this._tokenTimer);
      this._tokenTimer = setInterval(async () => {
        if (!this.el.isConnected) { clearInterval(this._tokenTimer); return; }
        const tk = await this.opts.tileToken();
        if (tk) layer.setUrl(url(tk), true);
      }, 20 * 60 * 1000);
    } else {
      this.el.classList.add('basic');
      this.basic.addTo(map);
      if (source === 'imported') {
        for (const m of imported) {
          const b = m.bounds;
          L.tileLayer(m.url, { minZoom: 3, maxZoom: 19, minNativeZoom: m.min_zoom, maxNativeZoom: m.max_zoom,
            bounds: b ? L.latLngBounds([b[1], b[0]], [b[3], b[2]]) : undefined, attribution: m.attribution || m.name }).addTo(this.base);
        }
      }
      map.attributionControl.addAttribution('Natural Earth, GeoNames');
    }
    this._toolbar();
  }

  /** heard: stations; me: {call, lat, lon, symbol}; track: our GPS track; tracked: callsigns followed */
  update(data) {
    Object.assign(this.data, data);
    this.draw();
  }

  draw() {
    const L = this.L;
    const map = this.map;
    if (map._popup && map.hasLayer(map._popup)) return;  // don't close a popup being read
    const now = Date.now() / 1000;
    const zoom = map.getZoom();
    const kinds = new Set(this.prefs.filters);
    const wanted = [];
    for (const h of this.data.heard) {
      if (h.latitude == null || h.longitude == null) continue;
      if (!h.last_rf && !this.prefs.internet) continue;
      if (!shown(h, kinds, now)) continue;
      const color = this.data.tracked.has((h.call || '').toUpperCase()) ? COLORS.tracked : h.last_rf ? COLORS.rf : COLORS.is;
      wanted.push({ h, lat: h.latitude, lon: h.longitude, color, label: h.call, freq: repeaterLabel(h) || temperatureLabel(h, this.opts.cs), symbol: [h.symbol_table, h.symbol] });
    }
    const me = this.data.me;
    if (me && me.lat != null) wanted.push({ me: true, lat: me.lat, lon: me.lon, color: COLORS.me, label: me.call, symbol: [me.symbol?.[0], me.symbol?.[1]] });
    const px = wanted.map((w) => { const p = map.project([w.lat, w.lon], zoom); return [p.x, p.y]; });
    const fixed = me && me.lat != null ? wanted.length - 1 : null;
    const at = spread(px, zoom, fixed);
    this.markers.clearLayers();
    this.leaders.clearLayers();
    this.trails.clearLayers();
    const dots = new Set();
    wanted.forEach((w, i) => {
      const moved = at[i][0] !== px[i][0] || at[i][1] !== px[i][1];
      const pos = moved ? map.unproject(L.point(at[i][0], at[i][1]), zoom) : L.latLng(w.lat, w.lon);
      const [pic] = symbolInfo(w.symbol[0], w.symbol[1], this.opts.cs);
      const bandClass = w.freq && w.freq.endsWith('°C') ? 'wx' : w.freq && w.freq.includes('70 cm') ? 'b70' : w.freq && w.freq.includes('2 m') ? 'b2' : 'bx';
      const html = `<div class="st"><div class="disc">${pic}</div><div class="tag ${w.color}">${esc(w.label)}${w.freq ? `<div class="fq ${bandClass}">${esc(w.freq)}</div>` : ''}</div></div>`;
      const marker = L.marker(pos, { icon: L.divIcon({ className: 'stm', html, iconSize: [130, 64], iconAnchor: [65, 15] }),
        zIndexOffset: w.me ? 1000 : 0, keyboard: false });
      if (w.h) marker.bindPopup(() => this.opts.popup(w.h), { className: 'aprs-pop', maxWidth: 230, maxHeight: 150, autoPanPaddingTopLeft: [52, 10] });
      marker.addTo(this.markers);
      if (moved) {
        L.polyline([pos, [w.lat, w.lon]], { color: LEADER_COLOR, weight: 1.5, interactive: false }).addTo(this.leaders);
        const key = `${w.lat},${w.lon}`;
        if (!dots.has(key)) {
          dots.add(key);
          L.circleMarker([w.lat, w.lon], { radius: 4, color: '#fff', weight: 1, fillColor: LEADER_COLOR, fillOpacity: 1, interactive: false }).addTo(this.leaders);
        }
      }
      if (this.prefs.trails) {
        const track = w.me ? this.data.track : w.h.track;
        const pts = (track || []).filter((p) => now - p[0] <= TRAIL_SECONDS).map((p) => [p[1], p[2]]);
        if (pts.length >= 2) L.polyline(pts, { color: TRAIL_COLOR, weight: 2.5, interactive: false }).addTo(this.trails);
      }
    });
    this.leaders.eachLayer((l) => l.bringToFront?.());
  }

  fit() {
    const pts = this.data.heard.filter((h) => h.latitude != null).map((h) => [h.latitude, h.longitude]);
    if (this.data.me?.lat != null) pts.push([this.data.me.lat, this.data.me.lon]);
    if (pts.length > 1) this.map.fitBounds(pts, { padding: [30, 30], maxZoom: 12 });
    else if (pts.length) this.map.setView(pts[0], 10);
  }

  // ─── the buttons over the map: base map, filters, trails, stations from the internet ───

  _toolbar() {
    const L = this.L;
    const t = this.opts.t;
    if (!this._bar) {
      const Bar = L.Control.extend({ onAdd: () => { const d = L.DomUtil.create('div', 'mapbar leaflet-bar'); L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); return d; } });
      this._bar = new Bar({ position: 'topright' }).addTo(this.map);
    }
    const bar = this._bar.getContainer();
    const kinds = new Set(this.prefs.filters);
    bar.innerHTML = `
      <button class="b-src ${this.current && this.current !== 'online' ? 'on' : ''}" title="${esc(t.mapSource)}">${svg(ICON.layers)}</button>
      <button class="b-flt ${kinds.size ? 'on' : ''}" title="${esc(kinds.size ? t.filterOn + ': ' + [...kinds].map((k) => t['filter_' + k + '_short']).join(', ') : t.filter)}">${svg(ICON.filter)}</button>
      <button class="b-trl ${this.prefs.trails ? 'on' : ''}" title="${esc(t.trails)}">${svg(ICON.trails)}</button>
      <button class="b-net ${this.prefs.internet ? 'on' : ''}" title="${esc(t.showIs)}">${svg(ICON.earth)}</button>
      <div class="mapmenu" hidden></div>`;
    const menu = bar.querySelector('.mapmenu');
    const open = (html, onPick) => {
      if (!menu.hidden && menu.dataset.kind === html) { menu.hidden = true; return; }
      menu.innerHTML = html;
      menu.hidden = false;
      menu.querySelectorAll('[data-k]').forEach((b) => b.addEventListener('click', () => onPick(b.dataset.k)));
    };
    bar.querySelector('.b-src').addEventListener('click', async () => {
      const imported = await this.opts.maps();
      const item = (k, label, disabled = false) => `<button data-k="${k}" ${disabled ? 'disabled' : ''} class="${this.prefs.source === k ? 'on' : ''}">${label}</button>`;
      open(`<div class="mhead">${esc(t.mapSource)}</div>` + item('auto', short(t.mapAuto)) + item('online', short(t.mapOnline)) + item('imported', short(imported.length ? t.mapImported : t.mapNoImported), !imported.length) + item('basic', short(t.mapBasic)),
        async (k) => { this.prefs.source = k; this.savePrefs(); menu.hidden = true; await this.setBase(); });
    });
    bar.querySelector('.b-flt').addEventListener('click', () => {
      const item = (k) => `<button data-k="${k}" class="${kinds.has(k) ? 'on' : ''}" title="${esc(t['filter_' + k])}">${kinds.has(k) ? '☑' : '☐'} ${esc(short(t['filter_' + k]))}</button>`;
      open(`<div class="mhead">${esc(t.filter)}</div>` + FILTERS.map(item).join('') + `<button data-k="" ${kinds.size ? '' : 'disabled'}>✕ ${esc(t.filterAll)}</button>`, (k) => {
        const set = new Set(this.prefs.filters);
        if (!k) set.clear(); else if (set.has(k)) set.delete(k); else set.add(k);
        this.prefs.filters = FILTERS.filter((f) => set.has(f));
        this.savePrefs();
        this._toolbar();
        this.draw();
      });
    });
    bar.querySelector('.b-trl').addEventListener('click', () => { this.prefs.trails = !this.prefs.trails; this.savePrefs(); this._toolbar(); this.draw(); });
    bar.querySelector('.b-net').addEventListener('click', () => { this.prefs.internet = !this.prefs.internet; this.savePrefs(); this._toolbar(); this.draw(); });
  }
}

function readPrefs() {
  try { return JSON.parse(localStorage.getItem('aprs-kiss-map') || '{}'); } catch { return {}; }
}

export const MAP_CSS = `
  .map.basic, .map.basic .leaflet-container { background: #eef2f5; }
  .leaflet-marker-icon.stm { background: none; border: none; pointer-events: none !important; }
  .stm .st { display: flex; flex-direction: column; align-items: center; width: 130px; pointer-events: none; }
  .stm .disc { width: 30px; height: 30px; border-radius: 50%; background: rgba(255,255,255,.9); border: .8px solid rgba(0,0,0,.18);
               box-shadow: 0 1px 3px rgba(0,0,0,.25); display: flex; align-items: center; justify-content: center; font-size: 18px; line-height: 1; pointer-events: auto; cursor: pointer; }
  .stm .tag { margin-top: 1px; padding: 1px 5px; border-radius: 6px; background: rgba(255,255,255,.92); border: .8px solid rgba(0,0,0,.18);
              box-shadow: 0 1px 3px rgba(0,0,0,.25); font: 600 11px/1.3 Roboto, sans-serif; white-space: nowrap; text-align: center; pointer-events: auto; cursor: pointer; }
  .stm .tag.c-rf { color: #1565C0; } .stm .tag.c-is { color: #546E7A; } .stm .tag.c-tr { color: #E65100; } .stm .tag.c-me { color: #C62828; font-weight: 700; }
  .stm .fq { font-size: 10px; font-weight: 700; } .stm .fq.b2 { color: #2E7D32; } .stm .fq.b70 { color: #C2185B; } .stm .fq.bx { color: #5D4037; } .stm .fq.wx { color: #0277BD; }
  .place { background: none; border: none; text-align: center; color: #455A64; font: 10px/1.1 Roboto, sans-serif; white-space: nowrap; pointer-events: none; }
  .place .city { font-size: 11px; color: #37474F; } .place .city.cap { font-weight: 700; } .place .peak { color: #8D6E63; font-weight: 700; font-size: 9px; }
  .place .town { font-size: 9px; }
  .mapbar { display: flex; flex-direction: column; background: var(--card-background-color, #fff); position: relative; }
  .mapbar > button { width: 34px; height: 34px; border: none; background: none; cursor: pointer; color: var(--primary-text-color); border-bottom: 1px solid var(--divider-color, #ccc); display: flex; align-items: center; justify-content: center; padding: 0; }
  .mhead { padding: 8px 12px 4px; font: 500 12px Roboto, sans-serif; color: var(--secondary-text-color); }
  .mapbar > button:last-of-type { border-bottom: none; }
  .mapbar > button.on { background: rgba(var(--rgb-primary-color, 3, 169, 244), .22); }
  .mapmenu { position: absolute; right: 38px; top: 0; min-width: 200px; max-width: min(280px, 70vw); white-space: nowrap; display: flex; flex-direction: column; background: var(--card-background-color, #fff);
             border: 1px solid var(--divider-color, #ccc); border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.3); overflow: hidden; }
  .mapmenu button { text-align: left; padding: 8px 12px; border: none; background: none; font: 13px Roboto, sans-serif; color: var(--primary-text-color); cursor: pointer; }
  .mapmenu button.on { font-weight: 700; color: var(--primary-color); } .mapmenu button:disabled { opacity: .45; cursor: default; }
  .mapmenu button:hover:not(:disabled) { background: var(--secondary-background-color); }
`;
