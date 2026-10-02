"""herdr: a fork opens as a new workspace, labelled and focused."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess

name = "herdr"
APP_BINARY = "/Applications/Herdr.app/Contents/MacOS/herdr"


def binary() -> str | None:
    found = shutil.which("herdr")
    if found:
        return found
    return APP_BINARY if os.access(APP_BINARY, os.X_OK) else None


def found() -> bool:
    return binary() is not None


def inside() -> bool:
    return bool(os.environ.get("HERDR_ENV"))


def open(cwd: str, label: str, command: list[str]) -> list[str]:
    from . import MuxError

    herdr = binary()
    made = subprocess.run([herdr, "workspace", "create", "--cwd", cwd, "--label", label,
                           "--no-focus"], capture_output=True, text=True)
    if made.returncode != 0:
        raise MuxError("herdr workspace create failed: " + (made.stderr or made.stdout).strip())
    try:
        result = json.loads(made.stdout)["result"]
        workspace = result["workspace"]["workspace_id"]
        pane = result["root_pane"]["pane_id"]
    except (ValueError, KeyError, TypeError):
        raise MuxError("could not read workspace and pane ids from: "
                       + made.stdout.strip()) from None

    ran = subprocess.run([herdr, "pane", "run", pane, shlex.join(command)],
                         capture_output=True, text=True)
    if ran.returncode != 0:
        raise MuxError(f"herdr pane run failed; close the empty workspace with: "
                       f"herdr workspace close {workspace}")
    subprocess.run([herdr, "workspace", "focus", workspace], capture_output=True)
    return [f"herdr workspace {workspace}  pane {pane}",
            f"close it with: herdr workspace close {workspace}"]
