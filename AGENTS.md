# Working on threadr

- Python 3.9+, standard library only. Don't add dependencies.
- `src/threadr/` is the CLI. Anything agent-specific goes in `providers/`, and
  anything multiplexer-specific goes in `mux/`.
- `commands/`, `skills/` and `.claude-plugin/` are the Claude Code plugin. They
  call the `threadr` CLI and never duplicate its logic.
- Tests: `python3 -m unittest discover -s tests`. They run in a throwaway
  `$HOME` with stub binaries, and must never touch the real `~/.claude`, the
  real tmux server or the network.
- Lint: `uvx ruff check src tests bin/threadr` and
  `shellcheck install.sh src/threadr/threadr.sh`.
- Bump the version in `src/threadr/__init__.py` and
  `.claude-plugin/plugin.json` together, and add a CHANGELOG entry.
