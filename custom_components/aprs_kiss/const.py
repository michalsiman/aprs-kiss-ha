"""Constants for APRS & Packet (KISS TNC)."""

DOMAIN = "aprs_kiss"

CONF_CONNECTION = "connection"  # "tcp" or "serial"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_DEVICE = "device"
CONF_BAUDRATE = "baudrate"
CONF_CALLSIGN = "callsign"
CONF_PATH = "path"
CONF_SYMBOL = "symbol"
CONF_COMMENT = "comment"
CONF_BEACON_MINUTES = "beacon_minutes"
CONF_TRACKED = "tracked_callsigns"
CONF_ACCEPT_INCOMING = "accept_incoming"
CONF_TXDELAY = "txdelay_ms"
CONF_APRSIS = "aprsis_enabled"
CONF_APRSIS_HOST = "aprsis_host"
CONF_APRSIS_PORT = "aprsis_port"
CONF_APRSIS_PASSCODE = "aprsis_passcode"
CONF_APRSIS_RADIUS = "aprsis_radius_km"
CONF_IGATE_RX = "igate_rx"      # RF → APRS-IS
CONF_IGATE_TX = "igate_tx"      # APRS-IS → RF (messages to local stations)

DEFAULT_PORT = 8001
DEFAULT_PATH = "WIDE1-1,WIDE2-1"
DEFAULT_SYMBOL = "/-"
DEFAULT_APRSIS_HOST = "euro.aprs2.net"
DEFAULT_APRSIS_PORT = 14580
DEFAULT_APRSIS_RADIUS = 50
VERSION = "0.3.1"

EVENT_PACKET = f"{DOMAIN}_packet"      # every decoded APRS packet
EVENT_MESSAGE = f"{DOMAIN}_message"    # an APRS message addressed to us
EVENT_TERMINAL = f"{DOMAIN}_terminal"  # monitor lines, session text and states (for the panel)

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"  # .format(entry_id)

PANEL_STATIC = "/aprs_kiss_panel"
PANEL_URL = f"{PANEL_STATIC}/aprs-kiss-panel.js"
