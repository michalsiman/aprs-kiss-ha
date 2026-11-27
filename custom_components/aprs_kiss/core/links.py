"""Web links in a message text: found, so the app can make them clickable (after a warning)."""

from __future__ import annotations

import re

_URL = re.compile(r"(?i)\b((?:https?://|www\.)[^\s<>\"']+)")
_TRAILING = ".,;:!?)]}'\""


def split_links(text: str) -> list[tuple[str, str | None]]:
    """The text in pieces: (piece, None) plain, (piece, url) a link; "www.…" gets https://. Punctuation
    right after a link ("see https://x.cz.") is not part of it; nor a closing bracket without its opening."""
    parts: list[tuple[str, str | None]] = []
    pos = 0
    for m in _URL.finditer(text or ""):
        link = m.group(1)
        while link and link[-1] in _TRAILING and not (link[-1] == ")" and link.count("(") >= link.count(")")):
            link = link[:-1]
        if len(link) < 8 or "." not in link.split("//")[-1]:
            continue
        start = m.start(1)
        if start > pos:
            parts.append((text[pos:start], None))
        url = link if link.lower().startswith(("http://", "https://")) else "https://" + link
        parts.append((link, url))
        pos = start + len(link)
    if pos < len(text or ""):
        parts.append((text[pos:], None))
    return parts
