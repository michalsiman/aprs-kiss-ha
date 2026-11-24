"""A small packet BBS with the classic W0RLI / MBL / FBB commands.

Transport-free: the owner (the Engine) passes in the text each connected station sends and gets
back text to send and requests to disconnect, through the callbacks given to BbsServer.
"""

from __future__ import annotations

import datetime as dt
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .storage import (
    BbsSettings,
    Message,
    Store,
    User,
    Users,
    as_row,
    base_call,
    load_settings,
    prepare_folder,
    read_text,
)

CR = "\r"
END_OF_TEXT = ("/EX", "\x1a", "***END", "/END")
LIST_DEFAULT = 20
LOG_LINES = 300


@dataclass
class Conn:
    remote: str  # with SSID, as connected
    call: str  # without SSID: the user
    since: float
    last: float
    mode: str = "cmd"  # cmd | subject | body
    draft: dict[str, Any] = field(default_factory=dict)
    buffer: str = ""
    tx_bytes: int = 0  # text the BBS sent to this station

    @property
    def tx_seconds(self) -> float:
        """Airtime estimate: 1200 Bd AFSK, about 10 % on top for AX.25 headers and flags."""
        return self.tx_bytes * 8 / 1200 * 1.1


class BbsServer:
    def __init__(
        self,
        folder: Path,
        bbs_call: str,
        version: str,
        send: Callable[[str, str], None],
        disconnect: Callable[[str], None],
        on_change: Callable[[], None] | None = None,
        language: str = "en",
    ) -> None:
        self.folder = folder
        self.call = bbs_call.upper()
        self.version = version
        self._send, self._disconnect = send, disconnect
        self._on_change = on_change
        prepare_folder(folder, language)
        self.settings: BbsSettings = load_settings(folder)
        self.users = Users(folder)
        self.store = Store(folder)
        self.conns: dict[str, Conn] = {}
        self.log: deque[tuple[float, str]] = deque(maxlen=LOG_LINES)
        self.recent: deque[tuple[float, str]] = deque(maxlen=20)  # for J
        self._last_beacon = time.time()
        self._last_purge = 0.0

    # ─── settings ─────────────────────────────────────────────────────────

    @property
    def sysop(self) -> str:
        return self.settings.sysop or base_call(self.call)

    @property
    def address(self) -> str:
        return self.settings.address or self.call

    def reload(self) -> None:
        """Read bbs.toml again (raises BbsConfigError, keeping the old settings)."""
        self.settings = load_settings(self.folder)
        self._event("settings reloaded")

    # ─── connections ──────────────────────────────────────────────────────

    def can_accept(self, remote: str) -> bool:
        call = base_call(remote)
        if call in self.settings.deny:
            return False
        if self.settings.access_mode == "list" and self.users.get(call) is None and call != self.sysop:
            return False
        return len(self.conns) < self.settings.max_sessions or remote.upper() in self.conns

    def connected(self, remote: str, now: float | None = None) -> None:
        now = now or time.time()
        remote = remote.upper()
        user, new = self.users.touch(remote, now)
        if base_call(remote) == self.sysop:
            user.sysop = True
        self.users.save()
        conn = self.conns[remote] = Conn(remote, user.call, now, now)
        self.recent.appendleft((now, remote))
        self._event(f"{remote} connected")
        lines = [f"[APRSKISS-{self.version}-H$]", self._fill(read_text(self.folder, "welcome.txt"), user)]
        if new and self.settings.ask_name and not user.name:
            lines.append("New user: please send your name with  N <name>")
        self._out(conn, "\r".join(lines) + CR + self._prompt())

    def disconnected(self, remote: str) -> None:
        conn = self.conns.pop(remote.upper(), None)
        if conn:
            self._event(f"{conn.remote} disconnected")

    def receive(self, remote: str, text: str) -> None:
        conn = self.conns.get(remote.upper())
        if conn is None:
            return
        conn.last = time.time()
        conn.buffer += text.replace("\r\n", "\r").replace("\n", "\r")
        if conn.mode == "body" and "\x1a" in conn.buffer:
            conn.buffer = conn.buffer.replace("\x1a", "\x1a" + CR, 1)  # Ctrl-Z ends the text even without Enter
        while CR in conn.buffer:
            line, conn.buffer = conn.buffer.split(CR, 1)
            self._line(conn, line)
            if conn.remote not in self.conns:  # said bye
                return
            limit = self.settings.max_tx_min * 60
            if limit and conn.tx_seconds > limit:
                self._out(conn, f"TX time limit of {self.settings.max_tx_min} min reached, bye." + CR)
                self._bye(conn)
                return

    def tick(self, now: float | None = None) -> str | None:
        """Every so often: idle timeouts, old messages, and the beacon text when one is due."""
        now = now or time.time()
        for conn in list(self.conns.values()):
            if now - conn.last > self.settings.idle_timeout_sec:
                self._out(conn, "Timeout, bye." + CR)
                self._bye(conn)
        if now - self._last_purge > 3600:
            self._last_purge = now
            gone = self.store.purge(self.settings.keep_personal_days, self.settings.keep_bulletins_days, now)
            if gone:
                self._event(f"{len(gone)} old messages deleted")
        every = self.settings.beacon_every_min * 60
        if every and now - self._last_beacon >= every:
            self._last_beacon = now
            return self.beacon_text()
        return None

    def beacon_text(self) -> str:
        unread = sorted({base_call(m.to) for m in self.store.messages.values() if m.kind != "B" and not m.is_read()})
        return self.settings.beacon_text.format(bbs=self.call, bbsname=self.settings.name,
                                                total=len(self.store.messages),
                                                mailfor=" ".join(unread) if unread else "-")

    # ─── for the app ──────────────────────────────────────────────────────

    def rows(self) -> list[dict[str, Any]]:
        return [as_row(m) for m in self.store.sorted()]

    def sysop_delete(self, number: int) -> bool:
        ok = self.store.delete(number)
        if ok:
            self._event(f"sysop killed #{number}")
        return ok

    # ─── commands ─────────────────────────────────────────────────────────

    def _line(self, conn: Conn, line: str) -> None:
        if conn.mode == "subject":
            subject = line.strip()
            if subject.upper() == "/ABORT":
                conn.mode, conn.draft = "cmd", {}
                self._out(conn, "Aborted." + CR + self._prompt())
                return
            conn.draft["subject"] = subject[:80] or "(no subject)"
            conn.draft["lines"] = []
            conn.mode = "body"
            self._out(conn, "Enter the text. End with /EX (or Ctrl-Z) on its own line, /ABORT cancels." + CR)
            return
        if conn.mode == "body":
            mark = line.strip().upper()
            if mark == "/ABORT":
                conn.mode, conn.draft = "cmd", {}
                self._out(conn, "Aborted." + CR + self._prompt())
                return
            ended = mark in END_OF_TEXT or line.endswith("\x1a")
            if not ended:
                conn.draft["lines"].append(line)
            if ended or len(conn.draft["lines"]) >= self.settings.max_message_lines:
                if not ended:
                    self._out(conn, f"Message is at its limit of {self.settings.max_message_lines} lines." + CR)
                self._store_draft(conn)
            return
        words = line.strip().split()
        if not words:
            self._out(conn, self._prompt())
            return
        cmd, args = words[0].upper(), words[1:]
        handler = {
            "L": self._cmd_list, "LM": self._cmd_list, "LB": self._cmd_list, "LL": self._cmd_list,
            "L<": self._cmd_list, "L>": self._cmd_list,
            "R": self._cmd_read, "RM": self._cmd_read_mine,
            "S": self._cmd_send, "SP": self._cmd_send, "SB": self._cmd_send, "ST": self._cmd_send,
            "K": self._cmd_kill, "KM": self._cmd_kill_mine,
            "N": self._cmd_name, "NQ": self._cmd_name, "NH": self._cmd_name,
            "I": self._cmd_info, "H": self._cmd_help, "?": self._cmd_help, "HELP": self._cmd_help,
            "J": self._cmd_heard, "V": self._cmd_version,
            "B": self._cmd_bye, "Q": self._cmd_bye, "BYE": self._cmd_bye,
        }.get(cmd)
        if handler is None:
            self._out(conn, f"Unknown command {cmd}. H for help." + CR + self._prompt())
            return
        handler(conn, cmd, args)

    def _user(self, conn: Conn) -> User:
        return self.users.get(conn.call) or User(conn.call)

    def _visible(self, conn: Conn, msg: Message) -> bool:
        if msg.kind == "B" or self._user(conn).sysop or conn.call == self.sysop:
            return True
        return conn.call in (base_call(msg.to), base_call(msg.sender))

    def _cmd_list(self, conn: Conn, cmd: str, args: list[str]) -> None:
        user = self._user(conn)
        msgs = [m for m in self.store.sorted() if self._visible(conn, m)]
        if cmd == "L":
            new = [m for m in msgs if m.number > user.last_listed]
            msgs = new if user.last_listed else msgs[-LIST_DEFAULT:]
            if msgs:
                user.last_listed = max(user.last_listed, msgs[-1].number)
                self.users.save()
        elif cmd == "LM":
            msgs = [m for m in msgs if base_call(m.to) == conn.call]
        elif cmd == "LB":
            msgs = [m for m in msgs if m.kind == "B"][-LIST_DEFAULT:]
        elif cmd == "LL":
            n = int(args[0]) if args and args[0].isdigit() else LIST_DEFAULT
            msgs = msgs[-n:]
        elif cmd in ("L<", "L>"):
            if not args:
                self._out(conn, f"Usage: {cmd} callsign" + CR + self._prompt())
                return
            who = base_call(args[0])
            msgs = [m for m in msgs if base_call(m.sender if cmd == "L<" else m.to) == who]
        if not msgs:
            self._out(conn, "No messages." + CR + self._prompt())
            return
        rows = ["Msg#  TS   Size To      From    Date       Subject"]
        for m in msgs:
            status = "Y" if m.is_read() else "N"
            when = dt.datetime.fromtimestamp(m.date, dt.timezone.utc).strftime("%d%m/%H%M")
            rows.append(f"{m.number:<5} {m.kind}{status} {m.size:>6} {m.to[:7]:<7} {m.sender[:7]:<7} {when}  {m.subject[:30]}")
        self._out(conn, CR.join(rows) + CR + self._prompt())

    def _show(self, conn: Conn, msg: Message) -> str:
        when = dt.datetime.fromtimestamp(msg.date, dt.timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        if base_call(msg.to) == conn.call or msg.kind == "B":
            self.store.mark_read(msg, conn.call)
        head = [f"Msg #{msg.number} ({msg.kind})  From: {msg.sender}  To: {msg.to}" + (f" @ {msg.at}" if msg.at else ""),
                f"Date: {when}", f"Subject: {msg.subject}", ""]
        return CR.join(head) + CR + msg.body.rstrip("\n").replace("\n", CR) + CR + f"[End of message #{msg.number}]" + CR

    def _cmd_read(self, conn: Conn, cmd: str, args: list[str]) -> None:
        numbers = [int(a) for a in args if a.isdigit()]
        if not numbers:
            self._out(conn, "Usage: R number" + CR + self._prompt())
            return
        out = []
        for n in numbers:
            msg = self.store.messages.get(n)
            out.append(self._show(conn, msg) if msg and self._visible(conn, msg) else f"No message #{n}." + CR)
        self._out(conn, "".join(out) + self._prompt())

    def _cmd_read_mine(self, conn: Conn, cmd: str, args: list[str]) -> None:
        mine = [m for m in self.store.sorted() if base_call(m.to) == conn.call and conn.call not in m.read_by]
        text = "".join(self._show(conn, m) for m in mine) if mine else "No unread messages." + CR
        self._out(conn, text + self._prompt())

    def _cmd_send(self, conn: Conn, cmd: str, args: list[str]) -> None:
        if not args:
            self._out(conn, f"Usage: {cmd} callsign [@ bbs]" + CR + self._prompt())
            return
        text = " ".join(args).upper()
        to, _, at = text.partition("@")
        to = to.strip().split()[0] if to.strip() else ""
        if not to:
            self._out(conn, f"Usage: {cmd} callsign [@ bbs]" + CR + self._prompt())
            return
        if self._full():
            self._out(conn, f"Sorry, the BBS is full ({self.settings.max_messages} messages)." + CR + self._prompt())
            return
        kind = {"SB": "B", "ST": "T"}.get(cmd, "P")
        conn.draft = {"kind": kind, "to": to, "at": at.strip()}
        conn.mode = "subject"
        note = ""
        if at.strip() and base_call(at.strip().split(".")[0]) != base_call(self.call):
            note = f"Note: no forwarding here, the message stays on {self.call}." + CR
        self._out(conn, note + "Subject:" + CR)

    def _full(self) -> bool:
        return bool(self.settings.max_messages) and len(self.store.messages) >= self.settings.max_messages

    def _store_draft(self, conn: Conn) -> None:
        d = conn.draft
        if self._full():
            conn.mode, conn.draft = "cmd", {}
            self._out(conn, f"Sorry, the BBS is full ({self.settings.max_messages} messages)." + CR + self._prompt())
            return
        msg = self.store.add(d["kind"], conn.call, d["to"], d["at"] or self.address, d["subject"],
                             "\n".join(d["lines"]))
        conn.mode, conn.draft = "cmd", {}
        self._event(f"{conn.remote} wrote #{msg.number} to {msg.to}")
        self._out(conn, f"Message #{msg.number} saved." + CR + self._prompt())

    def _can_kill(self, conn: Conn, msg: Message) -> bool:
        if self._user(conn).sysop or conn.call == self.sysop or base_call(msg.sender) == conn.call:
            return True
        return msg.kind != "B" and base_call(msg.to) == conn.call

    def _cmd_kill(self, conn: Conn, cmd: str, args: list[str]) -> None:
        numbers = [int(a) for a in args if a.isdigit()]
        if not numbers:
            self._out(conn, "Usage: K number" + CR + self._prompt())
            return
        out = []
        for n in numbers:
            msg = self.store.messages.get(n)
            if msg is None or not self._visible(conn, msg):
                out.append(f"No message #{n}.")
            elif not self._can_kill(conn, msg):
                out.append(f"Message #{n} is not yours to kill.")
            else:
                self.store.delete(n)
                self._event(f"{conn.remote} killed #{n}")
                out.append(f"Message #{n} killed.")
        self._out(conn, CR.join(out) + CR + self._prompt())

    def _cmd_kill_mine(self, conn: Conn, cmd: str, args: list[str]) -> None:
        mine = [m for m in self.store.sorted() if m.kind != "B" and base_call(m.to) == conn.call
                and conn.call in m.read_by]
        for m in mine:
            self.store.delete(m.number)
        if mine:
            self._event(f"{conn.remote} killed {len(mine)} read messages")
        self._out(conn, f"{len(mine)} messages killed." + CR + self._prompt())

    def _cmd_name(self, conn: Conn, cmd: str, args: list[str]) -> None:
        user = self.users.get(conn.call)
        value = " ".join(args).strip()
        if user is None or not value:
            self._out(conn, f"Usage: {cmd} text" + CR + self._prompt())
            return
        attr = {"N": "name", "NQ": "qth", "NH": "home"}[cmd]
        setattr(user, attr, value.upper() if attr == "home" else value[:30])
        self.users.save()
        self._out(conn, f"OK, {attr}: {getattr(user, attr)}" + CR + self._prompt())

    def _cmd_info(self, conn: Conn, cmd: str, args: list[str]) -> None:
        self._out(conn, self._fill(read_text(self.folder, "info.txt"), self._user(conn)) + self._prompt())

    def _cmd_help(self, conn: Conn, cmd: str, args: list[str]) -> None:
        self._out(conn, self._fill(read_text(self.folder, "help.txt"), self._user(conn)) + self._prompt())

    def _cmd_heard(self, conn: Conn, cmd: str, args: list[str]) -> None:
        rows = [f"{dt.datetime.fromtimestamp(t, dt.timezone.utc):%d.%m. %H:%M}  {call}" for t, call in self.recent]
        self._out(conn, (CR.join(rows) or "Nobody yet.") + CR + self._prompt())

    def _cmd_version(self, conn: Conn, cmd: str, args: list[str]) -> None:
        self._out(conn, f"APRS & Packet BBS {self.version}" + CR + self._prompt())

    def _cmd_bye(self, conn: Conn, cmd: str, args: list[str]) -> None:
        self._out(conn, f"73 de {self.call}" + CR)
        self._bye(conn)

    def _bye(self, conn: Conn) -> None:
        self.conns.pop(conn.remote, None)
        self._event(f"{conn.remote} bye")
        self._disconnect(conn.remote)

    # ─── helpers ──────────────────────────────────────────────────────────

    def _prompt(self) -> str:
        return f"{self.call} BBS>" + CR

    def _fill(self, text: str, user: User) -> str:
        total = len(self.store.messages)
        new = sum(1 for m in self.store.messages.values()
                  if m.number > user.last_listed and (m.kind == "B" or base_call(m.to) == user.call))
        mine = sum(1 for m in self.store.messages.values() if base_call(m.to) == user.call and user.call not in m.read_by)
        values = {"call": user.call, "name": user.name or user.call, "bbs": self.call, "bbsname": self.settings.name,
                  "sysop": self.sysop, "new": new, "mine": mine, "total": total}
        try:
            text = text.format(**values)
        except (KeyError, IndexError, ValueError):
            pass  # a typo in a text file must not break the BBS: show it as it is
        return text.rstrip("\n").replace("\n", CR) + CR

    def _out(self, conn: Conn, text: str) -> None:
        conn.tx_bytes += len(text.encode("utf-8"))
        self._send(conn.remote, text)

    def _event(self, text: str) -> None:
        now = time.time()
        self.log.append((now, text))
        try:
            with (self.folder / "log.txt").open("a", encoding="utf-8") as f:
                f.write(f"{dt.datetime.fromtimestamp(now, dt.timezone.utc):%Y-%m-%d %H:%M:%S}Z {text}\n")
        except OSError:
            pass
        if self._on_change:
            self._on_change()
