"""
friday/notes.py
---------------
Append + read today's voice notes. One markdown file per calendar day at
{PROJECT}/{cfg.NOTES_DIR}/YYYY-MM-DD.md.

No edit / delete API. Single-process, single-thread writer (FridayCore
thread). No locking needed.
"""

import datetime
from pathlib import Path

from friday import config as cfg

# Project root is the parent of the friday/ package, i.e. parent of this file's parent.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _today_path(now: datetime.datetime | None = None) -> Path:
    """Return today's notes file path. Creates the parent dir if missing."""
    now = now or datetime.datetime.now()
    dirpath = _PROJECT_ROOT / cfg.NOTES_DIR
    dirpath.mkdir(parents=True, exist_ok=True)
    return dirpath / f"{now.strftime('%Y-%m-%d')}.md"


def append(text: str, now: datetime.datetime | None = None) -> int:
    """Append a note entry. Returns the new total count of entries for today.

    File format:

        # Notes -- 2026-06-02

        - 09:14  buy milk on the way home
        - 11:42  remind anu about the dentist appointment
    """
    text = text.strip()
    if not text:
        return _count_entries(now)

    now = now or datetime.datetime.now()
    path = _today_path(now)

    if not path.exists():
        path.write_text(f"# Notes -- {now.strftime('%Y-%m-%d')}\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as f:
        f.write(f"- {now.strftime('%H:%M')}  {text}\n")

    return _count_entries(now)


def read_today(now: datetime.datetime | None = None) -> list[tuple[str, str]]:
    """Return today's entries as [(HH:MM, text), ...] in file order."""
    path = _today_path(now)
    if not path.exists():
        return []

    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        # Format: "- HH:MM  text"
        body = line[2:]
        if len(body) < 8 or body[5] != " " or body[2] != ":":
            continue
        time_str = body[:5]
        text     = body[7:].strip()
        if text:
            entries.append((time_str, text))
    return entries


def _count_entries(now: datetime.datetime | None = None) -> int:
    return len(read_today(now))
