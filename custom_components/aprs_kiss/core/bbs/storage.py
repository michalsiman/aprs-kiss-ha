"""The BBS on disk: settings (bbs.toml), users (users.toml) and messages, one text file each.

A message file is a header of "Key: value" lines, an empty line, then the text:

    Number: 12
    Type: P
    From: OK1ABC
    To: OK1SIM
    At: OK1SIM-1
    Date: 2026-11-22T15:00:00Z
    Subject: Hello
    Read-By: OK1SIM

    The message text...
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

from . import templates

DAY = 86400


class BbsConfigError(ValueError):
    """bbs.toml could not be read; the message says where."""


def base_call(call: str) -> str:
    """OK1ABC-7 -> OK1ABC: users and addressees are callsigns without SSID."""
    return call.strip().upper().split("-")[0]


# ─── settings ────────────────────────────────────────────────────────────────


@dataclass
class BbsSettings:
    name: str = "APRS & Packet BBS"
    address: str = ""
    sysop: str = ""
    max_sessions: int = 2
    idle_timeout_sec: int = 600
    max_tx_min: int = 10  # airtime the BBS may spend on one connection (0 = no limit)
    max_messages: int = 500  # the BBS refuses new messages beyond this (0 = no limit)
    max_message_lines: int = 200
    keep_personal_days: int = 60
    keep_bulletins_days: int = 30
    access_mode: str = "all"
    deny: list[str] = field(default_factory=list)
    ask_name: bool = True
    beacon_every_min: int = 0
    beacon_text: str = "{bbs} {bbsname} - {total} msgs. Mail for: {mailfor}"


_FIELDS = {  # (section, key) -> attribute
    ("bbs", "name"): "name", ("bbs", "address"): "address", ("bbs", "sysop"): "sysop",
    ("limits", "max_sessions"): "max_sessions", ("limits", "idle_timeout_sec"): "idle_timeout_sec",
    ("limits", "max_tx_min"): "max_tx_min", ("limits", "max_messages"): "max_messages",
    ("limits", "max_message_lines"): "max_message_lines",
    ("limits", "keep_personal_days"): "keep_personal_days", ("limits", "keep_bulletins_days"): "keep_bulletins_days",
    ("access", "mode"): "access_mode", ("access", "deny"): "deny", ("access", "ask_name"): "ask_name",
    ("beacon", "every_min"): "beacon_every_min", ("beacon", "text"): "beacon_text",
}


def prepare_folder(folder: Path, language: str = "en") -> None:
    """Create the folder with the default files the first time; existing files are never touched."""
    (folder / "messages").mkdir(parents=True, exist_ok=True)
    for name, text in templates.files(language).items():
        path = folder / name
        if not path.exists():
            path.write_text(text, encoding="utf-8")


def load_settings(folder: Path) -> BbsSettings:
    path = folder / "bbs.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return BbsSettings()
    except tomllib.TOMLDecodeError as err:
        raise BbsConfigError(f"{path.name}: {err}") from None
    out = BbsSettings()
    for (section, key), attr in _FIELDS.items():
        if key not in data.get(section, {}):
            continue
        value, default = data[section][key], getattr(out, attr)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, int):
            ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        elif isinstance(default, list):
            ok = isinstance(value, list) and all(isinstance(v, str) for v in value)
            value = [base_call(v) for v in value] if ok else value
        else:
            ok = isinstance(value, str)
        if not ok:
            raise BbsConfigError(f"{path.name}: [{section}] {key} = {value!r} is not valid")
        setattr(out, attr, value)
    old_idle = data.get("limits", {}).get("idle_timeout_min")  # before 0.1.13 the timeout was in minutes
    if "idle_timeout_sec" not in data.get("limits", {}) and isinstance(old_idle, int) and old_idle > 0:
        out.idle_timeout_sec = old_idle * 60
    if out.access_mode not in ("all", "list"):
        raise BbsConfigError(f'{path.name}: [access] mode must be "all" or "list"')
    out.max_sessions = max(1, out.max_sessions)
    out.idle_timeout_sec = max(10, out.idle_timeout_sec)
    out.max_message_lines = max(1, out.max_message_lines)
    out.sysop = base_call(out.sysop) if out.sysop else ""
    return out


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def update_settings(folder: Path, values: dict[tuple[str, str], Any]) -> None:
    """Change single values in bbs.toml and keep everything else, comments included.

    A key that is not in its section yet is added at the end of the section (the section too, if needed).
    The result is read back first, so a broken file is never written.
    """
    path = folder / "bbs.toml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    for (section, key), value in values.items():
        line = f"{key} = {_toml_value(value)}"
        current, start, end, found = None, None, len(lines), False
        for i, text in enumerate(lines):
            head = re.match(r"\s*\[([^\]]+)\]\s*$", text)
            if head:
                if current == section:
                    end = i
                    break
                current = head.group(1).strip()
                if current == section:
                    start = i
                continue
            if current == section and re.match(rf"\s*{re.escape(key)}\s*=", text):
                lines[i] = line
                found = True
                break
        if found:
            continue
        if start is None:
            lines += ["", f"[{section}]", line]
        else:
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            lines.insert(end, line)
    text = "\n".join(lines) + "\n"
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise BbsConfigError(f"bbs.toml: {err}") from None
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def write_text(folder: Path, name: str, text: str) -> None:
    tmp = folder / (name + ".tmp")
    tmp.write_text(text.replace("\r\n", "\n").rstrip("\n") + "\n", encoding="utf-8")
    tmp.replace(folder / name)


def read_text(folder: Path, name: str) -> str:
    try:
        return (folder / name).read_text(encoding="utf-8")
    except OSError:
        return ""


# ─── users ───────────────────────────────────────────────────────────────────


@dataclass
class User:
    call: str
    name: str = ""
    qth: str = ""
    home: str = ""
    sysop: bool = False
    first: float = 0.0
    last: float = 0.0
    last_listed: int = 0  # the highest message number this user has had listed by "L"
    connections: int = 0


class Users:
    def __init__(self, folder: Path) -> None:
        self.path = folder / "users.toml"
        self.users: dict[str, User] = {}
        try:
            data = tomllib.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except tomllib.TOMLDecodeError as err:
            raise BbsConfigError(f"users.toml: {err}") from None
        for call, row in (data.get("users") or {}).items():
            user = User(base_call(call))
            for key, value in row.items():
                if hasattr(user, key) and key != "call":
                    default = getattr(user, key)
                    try:
                        setattr(user, key, type(default)(value))
                    except (TypeError, ValueError):
                        pass
            self.users[user.call] = user

    def get(self, call: str) -> User | None:
        return self.users.get(base_call(call))

    def touch(self, call: str, now: float) -> tuple[User, bool]:
        """The user, created on the first connection; True when new."""
        key = base_call(call)
        user = self.users.get(key)
        new = user is None
        if new:
            user = self.users[key] = User(key, first=now)
        user.last = now
        user.connections += 1
        return user, new

    def save(self) -> None:
        lines = [templates.USERS_HEADER]
        for call in sorted(self.users):
            u = self.users[call]
            lines.append(f"[users.{json.dumps(call)}]")
            for key in ("name", "qth", "home", "sysop", "first", "last", "last_listed", "connections"):
                value = getattr(u, key)
                if isinstance(value, bool):
                    lines.append(f"{key} = {'true' if value else 'false'}")
                elif isinstance(value, float):
                    lines.append(f"{key} = {int(value)}")
                elif isinstance(value, int):
                    lines.append(f"{key} = {value}")
                else:
                    lines.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
            lines.append("")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines), encoding="utf-8")
        tmp.replace(self.path)


# ─── messages ────────────────────────────────────────────────────────────────


@dataclass
class Message:
    number: int
    kind: str  # P personal, B bulletin, T traffic
    sender: str
    to: str
    at: str
    date: float
    subject: str
    body: str
    read_by: list[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.body.encode("utf-8"))

    def is_read(self) -> bool:
        return base_call(self.to) in self.read_by if self.kind != "B" else bool(self.read_by)

    def to_text(self) -> str:
        date = dt.datetime.fromtimestamp(self.date, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        head = [f"Number: {self.number}", f"Type: {self.kind}", f"From: {self.sender}", f"To: {self.to}",
                f"At: {self.at}", f"Date: {date}", f"Subject: {self.subject}", f"Read-By: {','.join(self.read_by)}"]
        return "\n".join(head) + "\n\n" + self.body.rstrip("\n") + "\n"

    @classmethod
    def from_text(cls, text: str) -> Message:
        head, _, body = text.partition("\n\n")
        h: dict[str, str] = {}
        for line in head.splitlines():
            key, _, value = line.partition(":")
            h[key.strip().lower()] = value.strip()
        try:
            date = dt.datetime.strptime(h.get("date", ""), "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            date = 0.0
        return cls(int(h["number"]), (h.get("type") or "P")[:1].upper(), h.get("from", ""), h.get("to", ""),
                   h.get("at", ""), date, h.get("subject", ""), body,
                   [c for c in h.get("read-by", "").split(",") if c])


_NAME = re.compile(r"^(\d+)\.txt$")


class Store:
    def __init__(self, folder: Path) -> None:
        self.folder = folder / "messages"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.messages: dict[int, Message] = {}
        for path in self.folder.glob("*.txt"):
            if _NAME.match(path.name):
                try:
                    msg = Message.from_text(path.read_text(encoding="utf-8"))
                except (OSError, KeyError, ValueError):
                    continue
                self.messages[msg.number] = msg
        counter = self.folder / ".next"
        try:
            stored = int(counter.read_text().strip())
        except (OSError, ValueError):
            stored = 1
        self._next = max([stored, *(n + 1 for n in self.messages)])

    def _path(self, number: int) -> Path:
        return self.folder / f"{number:06d}.txt"

    def save(self, msg: Message) -> None:
        tmp = self._path(msg.number).with_suffix(".tmp")
        tmp.write_text(msg.to_text(), encoding="utf-8")
        tmp.replace(self._path(msg.number))

    def add(self, kind: str, sender: str, to: str, at: str, subject: str, body: str,
            now: float | None = None) -> Message:
        msg = Message(self._next, kind, sender, to, at, now or time.time(), subject, body)
        self._next += 1
        (self.folder / ".next").write_text(str(self._next))
        self.messages[msg.number] = msg
        self.save(msg)
        return msg

    def delete(self, number: int) -> bool:
        msg = self.messages.pop(number, None)
        if msg is None:
            return False
        self._path(number).unlink(missing_ok=True)
        return True

    def mark_read(self, msg: Message, call: str) -> None:
        call = base_call(call)
        if call not in msg.read_by:
            msg.read_by.append(call)
            self.save(msg)

    def purge(self, keep_personal_days: int, keep_bulletins_days: int, now: float) -> list[int]:
        gone = []
        for msg in list(self.messages.values()):
            days = keep_bulletins_days if msg.kind == "B" else keep_personal_days
            if days and now - msg.date > days * DAY:
                self.delete(msg.number)
                gone.append(msg.number)
        return gone

    def sorted(self) -> list[Message]:
        return [self.messages[n] for n in sorted(self.messages)]


def as_row(msg: Message) -> dict[str, Any]:
    """For the app's sysop view."""
    return {"number": msg.number, "kind": msg.kind, "from": msg.sender, "to": msg.to, "at": msg.at,
            "date": msg.date, "subject": msg.subject, "size": msg.size, "read": msg.is_read(), "body": msg.body}
