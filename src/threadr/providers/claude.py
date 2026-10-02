"""Claude Code: transcripts under ~/.claude/projects/<slug>/<session-id>.jsonl."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .base import Provider

# How much conversation text to keep per session for content search.
PROMPT_BUDGET = 20000
REPLY_BUDGET = 12000

# Prompts the harness injects rather than the user typing them.
NOISE = (
    "<system-reminder", "<command-", "Caveat:", "<local-command",
    "[Request interrupted", "<user-prompt-submit-hook",
    "Base directory for this skill:", "Loading skill",
    "Continue from where you left off",
    "This session is being continued from a previous",
    "Fork this conversation into a parallel session",
)

UUID_RE = re.compile(r'"uuid":\s*"([0-9a-f-]{36})"')
TS_RE = re.compile(r'"timestamp":\s*"([^"]+)"')
AI_TITLE_RE = re.compile(r'"aiTitle":\s*"((?:[^"\\]|\\.)*)"')
CUSTOM_TITLE_RE = re.compile(r'"customTitle":\s*"((?:[^"\\]|\\.)*)"')
CWD_RE = re.compile(r'"cwd":\s*"((?:[^"\\]|\\.)*)"')
BRANCH_RE = re.compile(r'"gitBranch":\s*"((?:[^"\\]|\\.)*)"')


def flatten(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)
    return ""


def unwrap_command(text: str) -> str:
    """Turn a slash-command envelope into the readable `/name args` form."""
    name = re.search(r"<command-name>\s*([^<]+?)\s*</command-name>", text)
    if not name:
        return text
    args = re.search(r"<command-args>\s*([^<]*?)\s*</command-args>", text)
    return (name.group(1) + " " + (args.group(1) if args else "")).strip()


def is_noise(text: str) -> bool:
    return not text or text.lstrip().startswith(NOISE)


def unescape(text: str) -> str:
    try:
        return json.loads('"' + text + '"')
    except ValueError:
        return text


class Claude(Provider):
    name = "claude"
    binary = "claude"

    @property
    def root(self) -> Path:
        # Claude Code honours CLAUDE_CONFIG_DIR, so we do too.
        return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

    def transcripts(self) -> list[Path]:
        projects = self.root / "projects"
        if not projects.is_dir():
            return []
        found = []
        for project in projects.iterdir():
            if project.is_dir():
                found.extend(p for p in project.glob("*.jsonl") if p.is_file())
        return found

    def scan(self, path: Path) -> dict | None:
        title = cwd = branch = None
        prompts: list[str] = []
        replies: list[str] = []
        fallback = ""
        prompt_len = reply_len = turns = 0
        first_ts = last_ts = None

        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            return None
        with fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                kind = rec.get("type")
                if kind == "ai-title":
                    title = rec.get("aiTitle") or title
                    continue
                if kind == "custom-title":
                    title = rec.get("customTitle") or title
                    continue
                if rec.get("cwd"):
                    cwd = rec["cwd"]
                    if rec.get("gitBranch"):
                        branch = rec["gitBranch"]
                ts = rec.get("timestamp")
                if ts:
                    first_ts = first_ts or ts
                    last_ts = ts
                if kind == "assistant" and reply_len < REPLY_BUDGET:
                    text = " ".join(flatten((rec.get("message") or {}).get("content")).split())
                    if text:
                        text = text[:800]
                        replies.append(text)
                        reply_len += len(text)
                if kind == "user":
                    turns += 1
                    if prompt_len < PROMPT_BUDGET:
                        text = " ".join(flatten((rec.get("message") or {}).get("content")).split())
                        if not fallback:
                            fallback = unwrap_command(text)[:200]
                        if not is_noise(text):
                            text = text[:600]
                            prompts.append(text)
                            prompt_len += len(text)

        if turns == 0 and not title:
            return None
        return {
            "id": path.stem,
            "title": title or "",
            "cwd": cwd or "",
            "branch": branch or "",
            "prompts": prompts,
            "replies": replies,
            "fallback": fallback,
            "turns": turns,
            "first": first_ts or "",
            "last": last_ts or "",
        }

    def skip_line(self, line: str) -> bool:
        # A memory file quoting a phrase must not match every session that loaded it.
        return '"type":"attachment"' in line or "<system-reminder" in line

    def _history(self) -> dict:
        """Prompts grouped by session id from history.jsonl.

        That file is not touched by the cleanupPeriodDays sweep, so it is the
        only record of sessions whose transcript has already been deleted.
        """
        path = self.root / "history.jsonl"
        if not path.exists():
            return {}
        sessions: dict = {}
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                sid = rec.get("sessionId")
                text = " ".join((rec.get("display") or "").split())
                if not sid or not text:
                    continue
                slot = sessions.setdefault(sid, {"prompts": [], "project": "", "last": 0.0})
                slot["prompts"].append(unwrap_command(text)[:600])
                slot["project"] = rec.get("project") or slot["project"]
                stamp = rec.get("timestamp")
                if stamp:
                    slot["last"] = max(slot["last"], stamp / 1000.0)
        return sessions

    def orphans(self) -> list[dict]:
        out = []
        for sid, slot in self._history().items():
            out.append({
                "id": sid,
                "title": "",
                "cwd": slot["project"],
                "branch": "",
                "prompts": slot["prompts"][:60],
                "replies": [],
                "fallback": slot["prompts"][0] if slot["prompts"] else "",
                "turns": len(slot["prompts"]),
                "first": "",
                "last": "",
                "mtime": slot["last"],
            })
        return out

    def recover(self, session_id: str) -> list[str] | None:
        slot = self._history().get(session_id)
        return slot["prompts"] if slot else None

    def resume_argv(self, session_id: str, yolo: bool = False) -> list[str]:
        argv = ["claude", "--resume", session_id]
        return argv + ["--dangerously-skip-permissions"] if yolo else argv

    def current_session(self) -> str | None:
        return os.environ.get("CLAUDE_CODE_SESSION_ID") or None

    def fork_argv(self, session_id: str, label: str, yolo: bool = False) -> list[str] | None:
        argv = ["claude", "--resume", session_id, "--fork-session", "--name", label]
        return argv + ["--dangerously-skip-permissions"] if yolo else argv

    def lineage(self, path: Path) -> dict | None:
        """One regex pass per transcript: message uuids, their times, a label.

        Forking (`--fork-session`) mints a new session id but keeps the uuid of
        every inherited message, which is what makes the tree recoverable.
        """
        uuids: list[str] = []
        stamps: list[str] = []
        prompts: list[tuple] = []
        titles: list[str] = []
        ai_title = cwd = branch = ""
        compacted = False

        try:
            fh = path.open(encoding="utf-8", errors="replace")
        except OSError:
            return None
        with fh:
            for line in fh:
                match = UUID_RE.search(line)
                if match:
                    found = TS_RE.search(line)
                    stamp = found.group(1) if found else ""
                    uuids.append(match.group(1))
                    stamps.append(stamp)
                    if '"compact_boundary"' in line:
                        compacted = True
                    if '"type":"user"' in line:
                        text = self._user_text(line)
                        if text:
                            prompts.append((stamp, text))
                    if not cwd:
                        cwd, branch = self._where(line)
                    continue
                if not ai_title:
                    match = AI_TITLE_RE.search(line)
                    if match:
                        ai_title = unescape(match.group(1))
                        continue
                match = CUSTOM_TITLE_RE.search(line)
                if match:
                    titles.append(unescape(match.group(1)))
                    continue
                if not cwd:
                    cwd, branch = self._where(line)

        if not uuids:
            return None
        live = sorted(s for s in stamps if s)
        prompts.sort()
        return {
            "id": path.stem,
            "uuids": uuids,
            "stamps": stamps,
            "prompts": prompts,
            # A later rename wins; a fork is launched with --name, so this is its label.
            "title": (titles[-1] if titles else "") or ai_title
                     or (prompts[0][1] if prompts else ""),
            "cwd": cwd,
            "branch": branch,
            "compacted": compacted,
            "first": live[0] if live else "",
            "last": live[-1] if live else "",
        }

    @staticmethod
    def _where(line: str) -> tuple:
        found = CWD_RE.search(line)
        if not found:
            return "", ""
        branch = BRANCH_RE.search(line)
        return unescape(found.group(1)), unescape(branch.group(1)) if branch else ""

    @staticmethod
    def _user_text(line: str) -> str:
        try:
            rec = json.loads(line)
        except ValueError:
            return ""
        text = " ".join(flatten((rec.get("message") or {}).get("content")).split())
        return "" if is_noise(text) else text
