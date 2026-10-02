# threadr

[![ci](https://github.com/shariqnaiyer/threadr/actions/workflows/ci.yml/badge.svg)](https://github.com/shariqnaiyer/threadr/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Find, resume, fork and map your coding-agent conversations.

You've had hundreds of conversations with Claude Code. threadr finds the one
you mean, puts you back in its directory, forks it into a parallel pane in
[herdr](https://herdr.dev) or tmux, and shows which conversations branched off
which.

```
$ threadr tree
~/code/shop  3 sessions, 2 forks
* checkout-tax-split  [main line]
  5be5c590  80 turns  01 Sep 14:36 -> 03 Sep 16:49
|- + try-sqlite  [fork]
|    8825bdb9  9 turns  forked 01 Sep 15:39, inherited 383 msgs
'- + fresh-review  [fork]
     8b8ac15e  72 turns  forked 03 Sep 16:46, inherited 3203 msgs  compacted
```

## Install

**The CLI.** It's Python 3.9+ and standard library only.

```bash
git clone https://github.com/shariqnaiyer/threadr ~/.threadr
~/.threadr/install.sh        # links ~/.local/bin/threadr, adds the shell hook to your rc
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/shariqnaiyer/threadr
echo 'eval "$(threadr init zsh)"' >> ~/.zshrc      # or bash
```

**The Claude Code plugin** adds `/branch-out` and the `find-session` skill:

```bash
claude plugin marketplace add shariqnaiyer/threadr
claude plugin install threadr@threadr
```

Run `threadr doctor` to check what was found.

## Find and resume

```bash
threadr checkout tax split    # resume the one match, or pick from several
threadr -l ledger             # list, don't resume
threadr -C <terms>            # resume without changing directory
threadr                       # every session, newest first
```

Every term has to match, across title, git branch, directory, your prompts and
the agent's replies. If the fast index misses, threadr scans every full
transcript, then falls back to best partial matches, and it tells you which
step answered. So an empty result really means nothing matched.

With [fzf](https://github.com/junegunn/fzf) you get a picker with a preview
pane. Without it you get a numbered menu. A session whose transcript was
already deleted can't be resumed, so threadr prints the prompts that survive
instead (`threadr recover <id>`).

## Fork

Inside Claude Code:

```
/branch-out try-sqlite
```

The conversation continues in parallel, in the same directory, under the label
you gave it. Leave the label out and Claude picks one. There's no git branch
or worktree, so both copies share the working tree, and threadr names any
uncommitted files before it forks.

| Where you are | The fork opens as |
|---|---|
| a herdr pane | a new herdr workspace, focused |
| a tmux pane | a new tmux window |
| neither | whichever is installed (a detached tmux session gets an `attach` hint) |

`threadr fork [label]` does the same from a shell inside an agent session.

## Map

```bash
threadr tree                 # the families above, newest first
threadr tree --html          # an interactive page, opened in your browser
threadr tree --mermaid       # or --json, --all, --cwd <dir>
```

Agents don't record which session a fork came from. threadr reconstructs it
from shared message ids. [How that works](docs/lineage.md).

## Keybindings

[`extras/`](extras) has bindings for herdr and tmux: `prefix f` picks and
resumes a session in a new pane, and `prefix T` opens the fork map.

## Configuration

| Variable | Effect |
|---|---|
| `THREADR_MUX=herdr\|tmux` | force a multiplexer for forks |
| `THREADR_YOLO=1` | resume and fork with the agent's permission prompts skipped |
| `THREADR_PROVIDERS=claude` | limit which agents are searched |
| `CLAUDE_CONFIG_DIR` | read Claude Code data from somewhere other than `~/.claude` |

The index is cached in `~/.cache/threadr/` and updates incrementally.

## Agents

Claude Code today. Search, the picker and the tree all go through a small
provider interface, so adding another agent means writing one module.
[Adding a provider](docs/providers.md).

## License

[MIT](LICENSE)
