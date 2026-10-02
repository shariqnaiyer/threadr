"""Small helpers shared by the search, tree and fork code."""
from __future__ import annotations

import calendar
import os
import sys
import time
from pathlib import Path


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "threadr"


def truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def yolo() -> bool:
    """Whether to resume and fork with the agent's permission prompts off."""
    return truthy("THREADR_YOLO")


def clip(text: str, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def age(mtime: float) -> str:
    delta = time.time() - mtime
    for unit, secs in (("d", 86400), ("h", 3600), ("m", 60)):
        if delta >= secs:
            return f"{int(delta // secs)}{unit}"
    return "now"


def when(stamp: str) -> str:
    """An ISO-8601 UTC timestamp as local `02 Sep 14:36`."""
    if not stamp:
        return "?"
    try:
        parsed = time.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return stamp[:10]
    return time.strftime("%d %b %H:%M", time.localtime(calendar.timegm(parsed)))


def normalise_path(text: str) -> str:
    """Fold separators and case so --cwd matches whatever a transcript stored."""
    return (text or "").replace("\\", "/").lower()


def utf8_streams() -> None:
    # Transcripts carry emoji and powerline glyphs; a shell under LC_ALL=C
    # would otherwise crash on the first one.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


class Style:
    def __init__(self, stream=sys.stdout, enabled: bool | None = None):
        if enabled is None:
            enabled = stream.isatty() and not os.environ.get("NO_COLOR")
        on = (lambda code: code) if enabled else (lambda code: "")
        self.bold, self.dim = on("\033[1m"), on("\033[2m")
        self.red, self.green, self.yellow = on("\033[31m"), on("\033[32m"), on("\033[33m")
        self.off = on("\033[0m")


def note(message: str) -> None:
    s = Style(sys.stderr)
    print(f"{s.yellow}{message}{s.off}", file=sys.stderr)


def fail(message: str) -> int:
    s = Style(sys.stderr)
    print(f"{s.red}threadr: {message}{s.off}", file=sys.stderr)
    return 1
