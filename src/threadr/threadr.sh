# shellcheck shell=bash
# threadr shell integration for zsh and bash. Load it from your rc file with
#
#   eval "$(threadr init zsh)"     # or bash
#
# A program cannot change its parent shell's directory, so this wrapper lets
# `threadr` leave the shell in the resumed session's directory once the agent
# exits. Everything else is passed straight through to the threadr on PATH.

threadr() {
  local cdfile ret dir
  cdfile=$(mktemp "${TMPDIR:-/tmp}/threadr.XXXXXX") || return 1
  THREADR_CD_FILE=$cdfile command threadr "$@"
  ret=$?
  if [ -s "$cdfile" ]; then
    dir=$(cat "$cdfile")
    if [ -d "$dir" ]; then cd -- "$dir" || :; fi
  fi
  rm -f -- "$cdfile"
  return $ret
}
