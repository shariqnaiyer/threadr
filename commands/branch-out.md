---
description: Fork this conversation into a new herdr workspace or tmux window (same directory, no git branch)
argument-hint: [label]
allowed-tools: Bash(threadr fork:*)
---

Fork this conversation into a parallel session in the same working directory.
This creates no git branch and no worktree: the fork shares the working tree.

Label to use: `$ARGUMENTS`

If the label above is empty, choose one yourself: a 2-3 word kebab-case slug
describing what this conversation has been about (for example `auth-refresh` or
`try-sqlite`). Do not ask the user for a name - pick one and proceed.

Then run exactly this, substituting the label:

```bash
threadr fork "<label>"
```

threadr picks the multiplexer itself: a herdr workspace when this session runs
in herdr, otherwise a tmux window. Report the workspace or window it printed
and the label used. If it fails a precondition check, relay its error verbatim
rather than working around it.
