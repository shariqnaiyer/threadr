#!/usr/bin/env bash
# Put `threadr` on PATH and wire its shell wrapper into your rc file.
# Idempotent: safe to re-run after a git pull.
#
# usage: ./install.sh [--dry-run] [--uninstall]
#
#   THREADR_BIN_DIR   where to link the CLI    (default ~/.local/bin)
#   THREADR_RC        which rc file to edit    (default ~/.zshrc or ~/.bashrc, from $SHELL)

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${THREADR_BIN_DIR:-$HOME/.local/bin}"
case "$(basename "${SHELL:-zsh}")" in
  bash) RC_DEFAULT="$HOME/.bashrc" ;;
  *)    RC_DEFAULT="$HOME/.zshrc" ;;
esac
RC="${THREADR_RC:-$RC_DEFAULT}"
BEGIN="# >>> threadr >>>"
END="# <<< threadr <<<"

DRY_RUN=0
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help)   sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           echo "install.sh: unknown option $arg" >&2; exit 1 ;;
  esac
done

say() { printf '%s\n' "$*"; }
run() { if [ "$DRY_RUN" = 1 ]; then say "  would run: $*"; else "$@"; fi; }

if [ "$UNINSTALL" = 1 ]; then
  if [ -L "$BIN_DIR/threadr" ]; then
    run rm "$BIN_DIR/threadr"
    say "removed  $BIN_DIR/threadr"
  fi
  if [ -f "$RC" ] && grep -qF "$BEGIN" "$RC"; then
    run sed -i.threadr-bak "/$BEGIN/,/$END/d" "$RC"
    say "removed  the threadr block from $RC (backup: $RC.threadr-bak)"
  fi
  exit 0
fi

say "threadr: $REPO"

# --- the CLI -----------------------------------------------------------------
dest="$BIN_DIR/threadr"
if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$REPO/bin/threadr" ]; then
  say "  ok       $dest"
else
  if [ -e "$dest" ] && [ ! -L "$dest" ]; then
    say "  BACKUP   $dest -> $dest.bak"
    run mv "$dest" "$dest.bak"
  fi
  run mkdir -p "$BIN_DIR"
  run ln -sfn "$REPO/bin/threadr" "$dest"
  say "  linked   $dest"
fi
run chmod +x "$REPO/bin/threadr"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) say "  note     $BIN_DIR is not on PATH - add it in $RC" ;;
esac

# --- the shell wrapper -------------------------------------------------------
if [ -f "$RC" ] && grep -qF "$BEGIN" "$RC"; then
  say "  ok       $RC already loads the threadr shell hook"
elif [ "$DRY_RUN" = 1 ]; then
  say "  would append a source line to $RC"
else
  printf '\n%s\n%s\n%s\n' "$BEGIN" "source \"$REPO/src/threadr/threadr.sh\"" "$END" >> "$RC"
  say "  appended a source line to $RC"
fi

# --- dependencies ------------------------------------------------------------
if ! command -v python3 >/dev/null; then
  say "  MISSING  python3 (3.9 or newer)"
elif ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  say "  MISSING  python3 3.9 or newer (found $(python3 --version 2>&1))"
fi
for tool in fzf herdr tmux; do
  command -v "$tool" >/dev/null || say "  absent   $tool (optional)"
done

say ""
say "Open a new shell, then try:  threadr doctor"
say "For /branch-out and the find-session skill in Claude Code:"
say "  claude plugin marketplace add shariqnaiyer/threadr"
say "  claude plugin install threadr@threadr"
