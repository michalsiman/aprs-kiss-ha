"""Settings of one station and where the app keeps its files.

Replaces Home Assistant's config entry: a plain dataclass saved as JSON.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .aprsis import DEFAULT_PORT as DEFAULT_APRSIS_PORT
from .aprsis import DEFAULT_SERVER as DEFAULT_APRSIS_HOST
from . import aprs, mapfilter, profiles, roadalert
from .ax25 import Address

_LOGGER = logging.getLogger(__name__)

APP_NAME = "aprs-kiss"
VERSION = "1.10.0"
# A beta (a pre-release on GitHub, tag vX.Y.Z-beta): betas take the next patch numbers (1.0.1, 1.0.2 …),
# the next stable release a higher minor one (1.1.0), so updating always goes up.
BETA = False
VERSION_LABEL = f"{VERSION} beta" if BETA else VERSION
MIN_BEACON_MINUTES = 10


@dataclass
class Config:
    """Everything the user can set. Field names match the Home Assistant integration."""

    # TNC
    connection: str = "tcp"  # a transport registered in connection.py ("direwolf": the sound-card modem)
    direwolf_adevice: str = ""  # Direwolf's ADEVICE ("plughw:1,0"); "" = the system's default sound card
    direwolf_ptt: str = ""  # "" = VOX, "CM108" (the sound card's GPIO), "RTS:/dev/ttyUSB0", "DTR:COM3"
    direwolf_port: int = 8101  # the KISS port of the Direwolf the app starts
    direwolf_path: str = ""  # Direwolf's program; "" = found by itself
    host: str = "127.0.0.1"
    port: int = 8001
    device: str = ""
    baudrate: int = 9600
    txdelay_ms: int = 0  # 0 = leave the TNC's own
    # Station
    callsign: str = ""
    path: str = "WIDE1-1,WIDE2-1"
    symbol: str = "/-"
    profiles: str = ""  # up to three SSIDs with their own symbol, JSON (see profiles.py); empty = just the one above
    profile: int = 0  # the active one
    comment: str = ""
    latitude: float | None = None  # our position (Home Assistant's home in the integration)
    longitude: float | None = None
    beacon_minutes: int = 0
    beacon_is: bool = False
    tracker_on: bool = False  # the tracker runs: our GPS position goes out again and again
    tracker_mode: str = "fixed"  # "fixed" every tracker_minutes, or "smart" (SmartBeaconing)
    tracker_minutes: int = 2
    tracker_profile: str = "car"  # smart: walk, bike or car
    tracker_still_minutes: int = 60  # smart: standing still, once in this many minutes
    offer_tracker: bool = True  # phone: you seem to be driving with the tracker off - offer to switch it on
    offer_tracker_skip_day: str = ""  # …but not on this day ("2026-11-27"): "Not today" was tapped
    road_alerts: bool = False  # while the tracker runs: warn about road incidents ahead…
    meet_alerts: bool = False  # …and about other moving stations ahead…
    road_alert_km: int = 5  # …this far
    tracked_callsigns: str = ""
    accept_incoming: bool = False
    files_accept: bool = False  # Files: other stations may connect and send us a file (YAPP); each is asked about
    # APRS-IS
    aprsis_enabled: bool = False
    licence_confirmed: bool = False
    aprsis_host: str = DEFAULT_APRSIS_HOST
    aprsis_port: int = DEFAULT_APRSIS_PORT
    aprsis_passcode: str = ""
    aprsis_radius_km: int = 50
    igate_rx: bool = False
    igate_tx: bool = False
    digi_mode: str = "off"  # APRS digipeater: "off", "fillin" (WIDE1-1) or "wide" (WIDEn-N up to digi_max_hops)
    digi_max_hops: int = 2  # the most hops a WIDEn-N path may ask for to be repeated
    digi_aliases: str = ""  # also repeat frames addressed to these (e.g. RELAY), besides our callsign
    # station telemetry (digipeater and iGate numbers, aprs.fi graphs): "" off, "internet", "radio", "both"
    telemetry_via: str = ""
    telemetry_minutes: int = 20
    # App
    language: str = ""  # "", "cs" or "en"; empty = from the system
    show_internet: bool = True  # map and station list also show stations seen only on APRS-IS
    monitor_internet: bool = True  # the frame monitor also shows APRS-IS lines ([IS])
    map_muted: bool = False  # map tiles faded, so the station labels stand out
    map_trails: bool = False  # the map draws where each moving station went in the last half hour
    map_files: str = ""  # imported offline maps (MBTiles, PMTiles, …), one path per line
    map_imported: bool = True  # offline: the imported map (when there is one) over the bundled one
    spot_last: str = ""  # Messages › Spot: the last spot (JSON: program, reference, frequency, mode, gateway)
    map_rf_km: int = 0  # the map shows stations heard on the radio this far (0 = no limit)
    units_distance: str = ""  # "km", "mi"; "" = as the phone / computer is set (miles in the US and the UK)
    units_temperature: str = ""  # "C", "F"; "" = as the phone / computer is set (Fahrenheit in the US)
    units_pressure: str = ""  # "hPa", "inHg"; "" = as the phone / computer is set (inHg in the US)
    mic_e: bool = False  # our position as Mic-E (shorter on air, with a status)
    mic_e_status: str = "en_route"  # the Mic-E status: off_duty … priority, "emergency" (always sent as Mic-E)
    position_ambiguity: int = 0  # privacy: our position less exact (0 exact; 1 ≈ 200 m, 2 ≈ 2 km, 3 ≈ 20 km, 4 ≈ 110 km)
    send_motion: bool = True  # privacy: speed and course go out with the position
    send_altitude: bool = True  # privacy: the altitude goes out with the position
    bulletin_km: int = 150  # the Bulletins screen: bulletins from stations this far (0 = all); heard by radio always
    winlink_password: str = ""  # Winlink (APRSLink, WLNK-1): only characters of it go on air, never the password
    stations_sort: str = "time"  # the Stations list: "time" (last heard first), "distance" (nearest first), "call"
    map_count: bool = True  # under the map's buttons: how many stations are on the map
    map_weather: bool = True  # the map's corner shows the temperature from the weather stations around us
    map_filters: str = ""  # the map shows only these kinds of stations ("weather,moving,road"); empty = all
    map_tools_hidden: bool = False  # the map's button bar folded into one gear button
    map_online: str = "osm"  # the online map: "osm" (OpenStreetMap) or "otm" (OpenTopoMap: contours, hill shading)
    map_offline: bool = False  # the bundled offline map (borders, cities) instead of OpenStreetMap tiles
    gps_source: str = "manual"  # "manual" (latitude/longitude above), "usb" (an NMEA GPS module), "phone"
    gps_device: str = ""  # its serial port
    gps_baudrate: int = 0  # 0 = find it automatically
    tak_enabled: bool = False  # TAK mode: only TAK positions and GeoChat over the radio
    tak_callsign: str = ""  # TAK callsign shown to others; empty = the station callsign
    tak_team: str = "Cyan"
    tak_role: str = "Team Member"
    tak_interval_min: int = 2  # own position every N minutes (0 = only when asked)
    vara_host: str = ""  # VARA FM's address for the terminal (empty = no VARA)
    vara_port: int = 8300  # its command port; the data port is the next one
    bbs_enabled: bool = False  # run the BBS server (its own SSID, below)
    bbs_ssid: int = 1  # the BBS answers on your callsign with this SSID
    bbs_list: str = ""  # saved BBSes and nodes for the terminal: JSON [{"call": ..., "path": ...}]
    check_updates: bool = True
    update_beta: bool = False  # also offer beta versions (pre-releases on GitHub): for testers  # ask GitHub once a day whether a newer version is out
    seen_version: str = ""  # the version whose changes were last shown (after an update: what is new)
    disclaimer_accepted: bool = False  # the first-start warning (transmitting needs a licence) was accepted
    language_asked: bool = False
    bbs_sentence_ok: bool = False  # the BBS SERVER sentence was typed once: not asked again
    tak_sentence_ok: bool = False  # the same for TAK  # the first start asked which language to use
    run_background: bool = False  # Android: keep running when not on screen (a notification shows it)
    keep_screen_on: str = "never"  # "never", "tak" (while TAK runs) or "always": the screen does not go dark
    sound_tx: bool = False  # a short beep whenever the radio transmits
    sound_messages: bool = True  # a sound for a new APRS message
    thursday_via: str = ""
    bulletin_via: str = ""  # the same for our bulletins  # the same for APRS Thursday; "" = internet
    message_via: str = ""  # how messages go: "radio", "internet", "both"; "" = by the APRS-IS switch (beacon_is)
    sound_chat: bool = True  # … for a new packet chat line
    sound_tak: bool = True  # … for a new TAK GeoChat message
    sound_road: bool = True  # … for a road incident ahead (tracker)
    sound_meet: bool = True  # … for a moving station ahead (tracker)
    menu_hidden: bool = False  # a computer: the menu hidden behind ☰, sliding in from the side as on a phone
    theme: str = "auto"  # auto (as the desktop), light, dark

    @property
    def configured(self) -> bool:
        return bool(self.callsign)

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def aprsis_on(self) -> bool:
        return self.aprsis_enabled and self.licence_confirmed

    def paths(self) -> list[str]:
        return [p.strip().upper() for p in (self.path or "").replace(" ", ",").split(",") if p.strip()]

    def validate(self) -> Config:
        """Normalise and check; raises ValueError with a short reason."""
        if self.callsign:
            self.callsign = str(Address.parse(self.callsign.strip()))
        for p in self.paths():
            Address.parse(p)
        self.path = ",".join(self.paths())
        if len(self.symbol) != 2:
            raise ValueError("The symbol is two characters: table and code")
        if self.aprsis_passcode and not str(self.aprsis_passcode).lstrip("-").isdigit():
            raise ValueError("The passcode is a number")
        for name in ("latitude", "longitude"):
            value = getattr(self, name)
            if value in ("", None):
                setattr(self, name, None)
                continue
            value = float(value)
            if abs(value) > (90 if name == "latitude" else 180):
                raise ValueError(f"Invalid {name}")
            setattr(self, name, value)
        if self.beacon_minutes and self.beacon_minutes < MIN_BEACON_MINUTES:
            self.beacon_minutes = MIN_BEACON_MINUTES
        if self.tracker_mode not in ("fixed", "smart"):
            self.tracker_mode = "fixed"
        self.map_filters = mapfilter.join(mapfilter.parse(self.map_filters))
        self.map_rf_km = max(0, int(self.map_rf_km or 0))
        if self.map_online not in ("osm", "otm"):
            self.map_online = "osm"
        if self.mic_e_status not in aprs.MIC_E_STATUS:
            self.mic_e_status = "en_route"
        self.position_ambiguity = min(4, max(0, int(self.position_ambiguity or 0)))
        self.bulletin_km = max(0, int(self.bulletin_km or 0))
        if self.telemetry_via not in ("", "internet", "radio", "both"):
            self.telemetry_via = ""
        minutes = int(self.telemetry_minutes or 20)
        self.telemetry_minutes = minutes if minutes in (10, 20, 30, 60) else 20
        if self.stations_sort not in ("time", "distance", "call"):
            self.stations_sort = "time"
        if self.units_distance not in ("", "km", "mi"):
            self.units_distance = ""
        if self.units_temperature not in ("", "C", "F"):
            self.units_temperature = ""
        if self.units_pressure not in ("", "hPa", "inHg"):
            self.units_pressure = ""
        profiles.normalize(self)
        if self.tracker_profile not in ("walk", "bike", "car"):
            self.tracker_profile = "car"
        self.tracker_minutes = min(60, max(1, int(self.tracker_minutes or 2)))
        self.tracker_still_minutes = min(120, max(5, int(self.tracker_still_minutes or 60)))
        if self.road_alert_km not in roadalert.DISTANCES_KM:
            self.road_alert_km = 5
        self.direwolf_port = int(self.direwolf_port or 8101)
        if not 0 < self.direwolf_port < 65536:
            raise ValueError("Port out of range")
        if self.connection == "tcp" and not (0 < int(self.port) < 65536):
            raise ValueError("Invalid TCP port")
        return self  # licence_confirmed stays when APRS-IS is switched off: the sentence is typed once

    @property
    def map_paths(self) -> list[str]:
        return [line for line in self.map_files.splitlines() if line.strip()]

    def saved_bbs(self) -> list[dict[str, str]]:
        """The terminal's saved stations, each {"call", "path"}, in the order they were saved."""
        try:
            items = json.loads(self.bbs_list) if self.bbs_list else []
        except ValueError:
            return []
        out = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and str(item.get("call", "")).strip():
                out.append({"call": str(item["call"]).strip().upper(), "path": str(item.get("path", "")).strip().upper()})
        return out

    def save_bbs(self, call: str, path: str = "") -> None:
        """Add a station, or update its path when it is already saved."""
        call, path = call.strip().upper(), path.strip().upper()
        items = [i for i in self.saved_bbs() if i["call"] != call]
        items.append({"call": call, "path": path})
        self.bbs_list = json.dumps(items)

    def remove_bbs(self, call: str) -> None:
        self.bbs_list = json.dumps([i for i in self.saved_bbs() if i["call"] != call.strip().upper()])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Unknown keys are ignored, values are coerced to the field's type."""
        out = cls()
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            default = getattr(out, f.name)
            try:
                if value is None or value == "":
                    value = None if f.name in ("latitude", "longitude") else ("" if isinstance(default, str) else default)
                elif isinstance(default, bool):
                    value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
                elif isinstance(default, int):
                    value = int(value)
                elif f.name in ("latitude", "longitude"):
                    value = float(value)
                else:
                    value = str(value)
            except (TypeError, ValueError):
                value = default
            setattr(out, f.name, value)
        return out


def data_dir() -> Path:
    """A writable folder for settings and history.

    Apps built with `flet build` (also on Android/iOS) get FLET_APP_STORAGE_DATA;
    otherwise the usual per-user folder (~/.local/share/aprs-kiss on Linux,
    %LOCALAPPDATA%\\aprs-kiss on Windows). APRS_KISS_DATA overrides both.
    """
    for var in ("APRS_KISS_DATA", "FLET_APP_STORAGE_DATA"):
        if os.environ.get(var):
            path = Path(os.environ[var])
            break
    else:
        from platformdirs import user_data_dir  # noqa: PLC0415

        path = Path(user_data_dir(APP_NAME, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read %s: %s", path, err)
        return None


def load_config(folder: Path | None = None) -> Config:
    data = _read_json((folder or data_dir()) / "config.json")
    return Config.from_dict(data) if isinstance(data, dict) else Config()


def save_config(config: Config, folder: Path | None = None) -> None:
    _write_json((folder or data_dir()) / "config.json", config.to_dict())


def load_state(folder: Path | None = None) -> dict[str, Any]:
    data = _read_json((folder or data_dir()) / "state.json")
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, Any], folder: Path | None = None) -> None:
    _write_json((folder or data_dir()) / "state.json", state)
