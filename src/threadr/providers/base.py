"""The contract every agent provider implements.

A provider knows where one coding agent keeps its transcripts and how to drive
its CLI. Everything here has a safe default, so a new provider can start with
`transcripts`, `scan` and `resume_argv` and switch the rest on later: search
works for any provider, forking only where `fork_argv` exists, and the fork
tree only where `lineage` can report message ids.
"""
from __future__ import annotations

import shutil
from pathlib import Path


class Provider:
    name = ""
    binary = ""

    def available(self) -> bool:
        return bool(shutil.which(self.binary)) or bool(self.transcripts())

    # --- search ---------------------------------------------------------------
    def transcripts(self) -> list[Path]:
        """Every transcript file on disk."""
        return []

    def scan(self, path: Path) -> dict | None:
        """One index record for a transcript, or None to skip it.

        Keys: id, title, cwd, branch, prompts, replies, fallback, turns,
        first, last. The index adds provider, file, state, mtime and size.
        """
        return None

    def skip_line(self, line: str) -> bool:
        """True for raw lines the exhaustive scan should ignore (injected context)."""
        return False

    def orphans(self) -> list[dict]:
        """Records for sessions whose transcript is gone but some trace survives."""
        return []

    def recover(self, session_id: str) -> list[str] | None:
        """Whatever prompts survive for a session, transcript or not."""
        return None

    # --- resume and fork ------------------------------------------------------
    def resume_argv(self, session_id: str, yolo: bool = False) -> list[str]:
        raise NotImplementedError

    def current_session(self) -> str | None:
        """The session id when called from inside a running agent session."""
        return None

    def fork_argv(self, session_id: str, label: str, yolo: bool = False) -> list[str] | None:
        """A command that starts a copy of the session, or None if unsupported."""
        return None

    # --- fork tree ------------------------------------------------------------
    def lineage(self, path: Path) -> dict | None:
        """Message ids and their timestamps, for reconstructing forks.

        Keys: id, uuids, stamps, prompts [(stamp, text)], title, cwd, branch,
        compacted, first, last. None means this provider cannot be mapped.
        """
        return None
