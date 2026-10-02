"""A throwaway $HOME, stub binaries and synthetic transcripts for the tests.

Nothing here touches the real machine: HOME, XDG_CACHE_HOME and TMPDIR point
into a temp dir, and PATH holds only the stubs plus the system basics.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "bin" / "threadr"
sys.path.insert(0, str(REPO / "src"))

SCRUB = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CONFIG_DIR", "HERDR_ENV", "TMUX", "TMUX_PANE",
         "THREADR_MUX", "THREADR_YOLO", "THREADR_PROVIDERS", "THREADR_CD_FILE", "NO_COLOR")

# Echoes its argv and working directory, so a test can see what was exec'd where.
ECHO = '#!/bin/sh\necho "{name} $*"\necho "PWD $(pwd)"\n'


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="threadr-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.bin = self.tmp / "bin"
        self.projects = self.home / ".claude" / "projects" / "-proj"
        for d in (self.home, self.bin, self.projects):
            d.mkdir(parents=True)
        self.stub("claude", ECHO.format(name="CLAUDE"))
        self.env = {k: v for k, v in os.environ.items() if k not in SCRUB}
        self.env.update(HOME=str(self.home), XDG_CACHE_HOME=str(self.home / ".cache"),
                        TMPDIR=str(self.tmp), PATH=f"{self.bin}:/usr/bin:/bin")
        self._saved = {k: os.environ.get(k) for k in ("HOME", "XDG_CACHE_HOME", *SCRUB)}
        os.environ.update(HOME=str(self.home), XDG_CACHE_HOME=str(self.home / ".cache"))
        for key in SCRUB:
            os.environ.pop(key, None)
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def stub(self, name: str, body: str) -> Path:
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)
        return path

    def dir(self, *parts: str) -> Path:
        path = self.home.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_threadr(self, *args, env=None, cwd=None, stdin=""):
        result = subprocess.run([sys.executable, str(BIN), *args], cwd=cwd or self.home,
                                env={**self.env, **(env or {})}, input=stdin,
                                capture_output=True, text=True, timeout=60)
        result.out = result.stdout + result.stderr
        return result

    def session(self, sid, title, cwd, branch, prompt, reply, when="2026-09-01T10:00:00Z",
                folder=None):
        """A minimal Claude Code transcript."""
        lines = [
            {"type": "ai-title", "aiTitle": title},
            {"type": "user", "cwd": str(cwd), "gitBranch": branch, "timestamp": when,
             "message": {"content": prompt}},
            {"type": "assistant", "timestamp": when,
             "message": {"content": [{"type": "text", "text": reply}]}},
            {"type": "user", "cwd": str(cwd), "gitBranch": branch, "timestamp": when,
             "message": {"content": "<system-reminder>ignore me</system-reminder>"}},
        ]
        folder = folder or self.projects
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{sid}.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return path

    def history(self, sid, prompt, project):
        path = self.home / ".claude" / "history.jsonl"
        with path.open("a") as fh:
            fh.write(json.dumps({"sessionId": sid, "display": prompt, "project": str(project),
                                 "timestamp": 1756000000000}) + "\n")

    def assertHas(self, haystack, needle):
        self.assertIn(needle, haystack)

    def assertHasnt(self, haystack, needle):
        self.assertNotIn(needle, haystack)
