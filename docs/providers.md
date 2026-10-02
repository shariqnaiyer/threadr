# Adding a provider

A provider teaches threadr one coding agent: where its transcripts live and how
to drive its CLI. Claude Code is the only one today. Adding another takes one
module and one line, and doesn't touch search, the picker or the tree.

## 1. Write `src/threadr/providers/<agent>.py`

Subclass `Provider` (in `base.py`) and override what the agent supports. Every
method has a safe default that turns its feature off.

| Method | Needed for | Default |
|---|---|---|
| `transcripts()` | search | no sessions |
| `scan(path)` | search: one record per transcript | skipped |
| `resume_argv(id, yolo)` | resuming | required |
| `skip_line(line)` | exhaustive scan ignores injected context | nothing skipped |
| `orphans()` / `recover(id)` | sessions whose transcript was deleted | none |
| `current_session()` | `threadr fork` from inside a session | not inside one |
| `fork_argv(id, label, yolo)` | `threadr fork` | can't fork |
| `lineage(path)` | `threadr tree` | left out of the tree |

`scan` returns a dict with `id, title, cwd, branch, prompts, replies,
fallback, turns, first, last`. The index adds `provider, file, state, mtime,
size` itself and caches the record until the file's size or mtime changes.

`yolo` is true when the user set `THREADR_YOLO=1`. Map it to the agent's own
"skip permission prompts" flag, or ignore it.

## 2. Register it

```python
# src/threadr/providers/__init__.py
PROVIDERS = {"claude": Claude, "myagent": MyAgent}
```

## 3. Test it

`tests/test_providers.py` has a toy `Notes` provider that shows the minimum.
Add a test module with a synthetic transcript in your agent's real format, and
cover search, resume, and fork and tree if you implemented them.

## Agent-side packaging

`/branch-out` and the `find-session` skill are Claude Code packaging around
the CLI. Another agent's equivalents (a custom prompt, a skill, a command)
belong in their own folder at the repo root and should call `threadr`, not
reimplement it.
