# Changelog

## 0.1.0 - 2026-10-02

First public release.

- `threadr [terms]` searches every Claude Code session by title, branch,
  directory, prompts and replies, then resumes the one you pick and leaves your
  shell in its directory. The fzf picker has a preview pane, with a numbered
  menu as the fallback.
- `threadr fork` and the `/branch-out` command fork the current conversation
  into a new herdr workspace or tmux window.
- `threadr tree` reconstructs which sessions were forked from which, as ASCII,
  mermaid, JSON or a self-contained HTML page.
- `threadr recover` reads the prompts that survive a deleted transcript.
- A provider interface, so other agents can be added without touching search
  or the tree.
- A Claude Code plugin (`/branch-out`, the `find-session` skill) and an
  `install.sh` for the shell side.
