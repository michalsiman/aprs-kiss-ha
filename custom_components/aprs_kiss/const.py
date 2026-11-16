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

DEFAULT_PORT = 8001
DEFAULT_PATH = "WIDE1-1,WIDE2-1"
DEFAULT_SYMBOL = "/-"

EVENT_PACKET = f"{DOMAIN}_packet"      # every decoded APRS packet
EVENT_MESSAGE = f"{DOMAIN}_message"    # an APRS message addressed to us
EVENT_TERMINAL = f"{DOMAIN}_terminal"  # monitor lines, session text and states (for the panel)

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"  # .format(entry_id)

PANEL_URL = "/aprs_kiss_panel/aprs-kiss-panel.js"
