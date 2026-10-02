---
name: find-session
description: Find a past coding-agent conversation by what it was about, then resume it or pull facts out of it. Use when the user says "find the chat where we...", "which session did I...", "what did we decide about X last week", "resume the session about Y", or asks for a session id, transcript, or working directory of earlier work.
---

# Finding past sessions

`threadr` indexes every agent transcript on this machine (Claude Code today) so
you never grep hundreds of megabytes of JSONL. If `threadr` is not on PATH, tell
the user to install it from https://github.com/shariqnaiyer/threadr.

## Search

```bash
threadr find --tsv auth token refresh
```

One row per session, tab separated:
`id  provider  cwd  branch  age  turns  title  state`.
`state` is `live` (resumable) or `gone` (transcript deleted, prompts recoverable).

- All terms must match, across title, git branch, directory, the user's prompts
  and the agent's replies. Newest first.
- Recall is layered, and each fallback announces itself on stderr: the cached
  digest (sub-second), then an exact scan of every full transcript (seconds),
  then best partial matches. An empty result means nothing matched - widen the
  query rather than assuming the tool gave up.
- No terms lists everything. `-n N` caps rows. `--cwd DIR` restricts to one
  project. `--live-only` hides deleted sessions. `--json` gives full records.
- `threadr show <id>` prints a digest: title, dir, branch, turns, first prompts.
- `threadr recover <id>` prints every prompt that survives a deleted transcript.
- `threadr tree` shows which sessions were forked from which.

## Reading a Claude Code transcript

Transcripts live at `~/.claude/projects/<slug>/<id>.jsonl` and run to tens of
thousands of lines - never `cat` one. Find the fullest copy, then read selectively:

```bash
ls -S ~/.claude/projects/*/<id>.jsonl | head -1
```

```bash
python3 - "$TRANSCRIPT" <<'EOF'
import json, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    d = json.loads(line)
    if d.get("type") == "user":
        print(d["message"]["content"])
EOF
```

Assistant text is under `message.content[].text` on `type == "assistant"` lines.

## Resuming

Hand the user a command rather than a raw id. `threadr <terms>` resumes the
single match, or opens a picker, and leaves their shell in the session's
directory. To resume directly: `claude --resume <id>` (add `--fork-session` to
branch a copy and leave the original alone).

## Gotchas

- **The project folder name lies.** A session resumed elsewhere keeps its
  original folder, and one id can be mirrored into several. Trust the `cwd`
  threadr reports, which comes from inside the transcript.
- **Retention.** Claude Code deletes transcripts older than `cleanupPeriodDays`
  (in `~/.claude/settings.json`, default 30). Their prompts survive in
  `~/.claude/history.jsonl`, which is what `threadr recover` reads. Check the
  setting before telling a user an old conversation is unrecoverable.
- `claude --name <name>` labels a session at launch, which makes it far easier
  to find later. Suggest it when the user starts work they will come back to.
