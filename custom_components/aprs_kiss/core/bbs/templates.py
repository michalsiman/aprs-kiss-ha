"""The files a new BBS folder starts with: settings and the texts users see.

They are written once, when the folder is empty, and are then the sysop's to edit.
Czech when the app runs in Czech, English otherwise. Placeholders in the texts:
{call} the user's callsign, {name} their name, {bbs} the BBS callsign, {bbsname} its name,
{sysop}, {new} messages new for the user, {mine} unread personal messages, {total} all messages.
"""

from __future__ import annotations

CONFIG_EN = """\
# APRS & Packet BBS server: settings.
# The BBS callsign is your callsign with the SSID chosen in the app's Settings.
# Edit, save, then press "Reload settings" in the BBS SERVER section (or restart the app).

[bbs]
name = "APRS & Packet BBS"
# Hierarchical address of this BBS (for "@" in addresses), e.g. "OK1SIM-1.#PLZ.CZE.EU".
# Empty: the BBS callsign.
address = ""
# Sysop callsign (without SSID). Empty: your own callsign. The sysop may read and kill all messages.
sysop = ""

[limits]
# Connections at the same time. The radio is one, so keep it small.
max_sessions = 2
# A user who sends nothing for this many seconds is disconnected.
idle_timeout_sec = 600
# Airtime the BBS may transmit to one connection, in minutes at 1200 Bd (0 = no limit).
max_tx_min = 10
# Messages kept at most; beyond this new messages are refused (0 = no limit).
max_messages = 500
# Longest message, in lines.
max_message_lines = 200
# Messages are deleted after this many days (0 = keep for ever).
keep_personal_days = 60
keep_bulletins_days = 30

[access]
# "all": anyone may connect. "list": only callsigns in users.toml.
mode = "all"
# Callsigns that may never connect (without SSID).
deny = []
# Ask a new user for their name on the first connection.
ask_name = true

[beacon]
# A UI frame to MAIL every N minutes (0 = off). Placeholders: {bbs} {bbsname} {total} {mailfor}
every_min = 0
text = "{bbs} {bbsname} - {total} msgs. Mail for: {mailfor}"

"""

CONFIG_CS = """\
# BBS server aplikace APRS & Packet: nastavení.
# Značka BBS je tvoje značka se SSID, které vybereš v Nastavení aplikace.
# Uprav, ulož a v sekci BBS SERVER stiskni "Načíst nastavení znovu" (nebo restartuj aplikaci).

[bbs]
name = "APRS & Packet BBS"
# Hierarchická adresa této BBS (pro "@" v adresách), např. "OK1SIM-1.#PLZ.CZE.EU".
# Prázdné: značka BBS.
address = ""
# Značka sysopa (bez SSID). Prázdné: tvoje značka. Sysop smí číst a mazat všechny zprávy.
sysop = ""

[limits]
# Kolik spojení najednou. Rádio je jedno, takže málo.
max_sessions = 2
# Kdo tolik sekund nic nepošle, toho BBS odpojí.
idle_timeout_sec = 600
# Kolik minut smí BBS vysílat jednomu spojení (počítáno při 1200 Bd, 0 = bez omezení).
max_tx_min = 10
# Nejvíc uložených zpráv; nad tento počet BBS nové zprávy odmítne (0 = bez omezení).
max_messages = 500
# Nejdelší zpráva v řádcích.
max_message_lines = 200
# Zprávy se mažou po tolika dnech (0 = nikdy).
keep_personal_days = 60
keep_bulletins_days = 30

[access]
# "all": připojit se smí kdokoliv. "list": jen značky v users.toml.
mode = "all"
# Značky, které se nesmí připojit (bez SSID).
deny = []
# Zeptat se nového uživatele při prvním připojení na jméno.
ask_name = true

[beacon]
# UI rámec na MAIL každých N minut (0 = vypnuto). Zástupné znaky: {bbs} {bbsname} {total} {mailfor}
every_min = 0
text = "{bbs} {bbsname} - {total} msgs. Mail for: {mailfor}"

"""

WELCOME_EN = """\
Welcome to {bbsname} ({bbs}), {name}!
Sysop: {sysop}. Messages: {total}, new for you: {new}, unread personal: {mine}.
Type H for help.
"""

WELCOME_CS = """\
Vítej na {bbsname} ({bbs}), {name}!
Sysop: {sysop}. Zpráv: {total}, nových pro tebe: {new}, nepřečtených osobních: {mine}.
Nápověda: H
"""

HELP_EN = """\
L          list new messages      LM  my messages      LB  bulletins
LL n       last n messages        L< call  from call   L> call  to call
R n [n..]  read message(s)        RM  read my unread messages
S call     send a personal message (also SP call @ BBS)
SB to      send a bulletin (e.g. SB ALL)
K n [n..]  kill message(s)        KM  kill my read messages
N name     your name              NQ qth   your QTH    NH bbs  your home BBS
I          about this BBS         J   last connections
V          version                B   bye (also Q)
"""

HELP_CS = """\
L          nové zprávy            LM  moje zprávy      LB  bulletiny
LL n       posledních n zpráv     L< značka  od        L> značka  pro
R n [n..]  přečíst zprávu         RM  přečíst moje nepřečtené
S značka   poslat osobní zprávu (také SP značka @ BBS)
SB pro     poslat bulletin (např. SB ALL)
K n [n..]  smazat zprávu          KM  smazat moje přečtené
N jméno    tvoje jméno            NQ qth   tvoje QTH   NH bbs  tvoje domovská BBS
I          o této BBS             J   poslední připojení
V          verze                  B   konec (také Q)
"""

INFO_EN = """\
{bbsname} ({bbs}) runs on APRS & Packet, https://github.com/michalsiman/aprs-kiss-app
Sysop: {sysop}. Messages stay on this BBS, there is no forwarding to other BBSes.
"""

INFO_CS = """\
{bbsname} ({bbs}) běží na aplikaci APRS & Packet, https://github.com/michalsiman/aprs-kiss-app
Sysop: {sysop}. Zprávy zůstávají na této BBS, předávání na jiné BBS (forwarding) zatím není.
"""

USERS_HEADER = """\
# Users of the BBS. The BBS adds and updates them itself; you may edit them while it is off.
# sysop = true gives the user the sysop's rights. With access mode "list" only these callsigns may connect.
"""


def files(language: str) -> dict[str, str]:
    cs = language == "cs"
    return {
        "bbs.toml": CONFIG_CS if cs else CONFIG_EN,
        "welcome.txt": WELCOME_CS if cs else WELCOME_EN,
        "help.txt": HELP_CS if cs else HELP_EN,
        "info.txt": INFO_CS if cs else INFO_EN,
    }
