"""tmux: a fork opens as a new window, or a detached session outside tmux."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess

name = "tmux"


def found() -> bool:
    return shutil.which("tmux") is not None


def inside() -> bool:
    return bool(os.environ.get("TMUX"))


def open(cwd: str, label: str, command: list[str]) -> list[str]:
    from . import MuxError

    # tmux reads . and : in a target name as session/window separators.
    safe = label.replace(".", "-").replace(":", "-")
    line = shlex.join(command)
    if inside():
        made = subprocess.run(["tmux", "new-window", "-P", "-F", "#{session_name}:#{window_index}",
                               "-c", cwd, "-n", safe, line], capture_output=True, text=True)
        if made.returncode != 0:
            raise MuxError("tmux new-window failed: " + made.stderr.strip())
        window = made.stdout.strip() or safe
        return [f"tmux window {window}", f"close it with: tmux kill-window -t {window}"]

    made = subprocess.run(["tmux", "new-session", "-d", "-s", safe, "-c", cwd, line],
                          capture_output=True, text=True)
    if made.returncode != 0:
        raise MuxError(f"tmux new-session failed (is a session named '{safe}' already "
                       f"open?): " + made.stderr.strip())
    return [f"detached tmux session '{safe}'",
            f"attach with:   tmux attach -t {safe}",
            f"close it with: tmux kill-session -t {safe}"]
