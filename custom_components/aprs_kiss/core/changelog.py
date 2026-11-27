"""What changed since the version last run: the sections of CHANGELOG.md between the two.

Sections start with "## 1.5.0 – 2026-11-26" (a beta: "## 1.2.4 beta – …"); "## Unreleased" is left out.
"""

from __future__ import annotations

import re

_HEAD = re.compile(r"^## (\d+(?:\.\d+)+)\b[^\n]*$", re.M)


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version.split(" ")[0])[:3])


def sections(text: str) -> list[tuple[str, str]]:
    """[(version, the section's text with its heading)], newest first as in the file."""
    out = []
    heads = list(_HEAD.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        nxt = text.find("\n## ", m.end())  # an "## Unreleased" or other heading ends a section too
        if 0 <= nxt < end:
            end = nxt + 1
        out.append((m.group(1), text[m.start():end].strip()))
    return out


def since(text: str, seen: str, current: str) -> str:
    """The sections newer than `seen` up to `current` (seen empty: only the current one's)."""
    now = version_key(current)
    low = version_key(seen) if seen else None
    parts = [body for version, body in sections(text)
             if version_key(version) <= now and (version_key(version) > low if low is not None
                                                  else version_key(version) == now)]
    return "\n\n".join(parts)
