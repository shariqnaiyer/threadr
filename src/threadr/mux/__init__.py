"""Terminal multiplexers a fork can open in.

Each mux exposes `name`, `found()`, `inside()` and `open(cwd, label, command)`,
which returns the lines to report back. Adding one means a module here and a
line in MUXES; order is the auto-detection preference.
"""
from __future__ import annotations

import os

from . import herdr, tmux

MUXES = {"herdr": herdr, "tmux": tmux}


class MuxError(Exception):
    pass


def choose():
    """THREADR_MUX if set, else the mux we are inside, else whichever is installed."""
    forced = os.environ.get("THREADR_MUX", "").strip()
    if forced:
        if forced not in MUXES:
            raise MuxError(f"unknown THREADR_MUX: {forced} (expected {' or '.join(MUXES)})")
        mux = MUXES[forced]
        if not mux.found():
            raise MuxError(f"THREADR_MUX={forced} but {forced} is not installed")
        return mux
    for mux in MUXES.values():
        if mux.inside() and mux.found():
            return mux
    for mux in MUXES.values():
        if mux.found():
            return mux
    raise MuxError("no multiplexer available - install herdr or tmux")
