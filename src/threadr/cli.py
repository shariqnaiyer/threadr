"""threadr command line."""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import __version__, index, providers, tree
from .mux import MUXES, MuxError, choose
from .util import Style, age, clip, fail, normalise_path, note, utf8_streams, yolo

USAGE = """\
usage: threadr [find] [terms...]       search sessions, pick one, cd there and resume it
       threadr show <id>               a digest of one session
       threadr recover <id>            the prompts that survive a deleted transcript
       threadr tree [--html [FILE]]    which sessions were forked from which
       threadr fork [label]            fork the current agent session into a new pane
       threadr doctor                  check providers, multiplexers and the picker
       threadr init zsh|bash           print the shell hook that lets threadr cd your shell

Run `threadr <command> -h` for a command's options.
"""


# --- find -----------------------------------------------------------------------
def find_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="threadr find",
        description="Search past sessions, then resume one and cd to its directory. "
                    "All terms must match, across title, git branch, directory, prompts "
                    "and replies. With no terms, lists every session newest first.")
    ap.add_argument("terms", nargs="*")
    ap.add_argument("-l", "--list", action="store_true", help="print the table, do not resume")
    ap.add_argument("-C", "--no-cd", action="store_true", help="resume where you are")
    ap.add_argument("-r", "--refresh", action="store_true", help="rebuild the index")
    ap.add_argument("-n", "--limit", type=int, default=40, help="maximum rows (default 40)")
    ap.add_argument("--cwd", help="only sessions whose directory contains this")
    ap.add_argument("--provider", help="only these providers, comma separated")
    ap.add_argument("--live-only", action="store_true", help="hide sessions with no transcript")
    ap.add_argument("--tsv", action="store_true", help="tab-separated rows, for scripts")
    ap.add_argument("--json", action="store_true", help="full records as JSON")
    return ap


def gather(args) -> tuple:
    chosen = providers.enabled(args.provider)
    entries = index.load(chosen, refresh=args.refresh)
    if args.live_only:
        entries = [e for e in entries if e["state"] == "live"]
    if args.cwd:
        needle = normalise_path(args.cwd)
        entries = [e for e in entries if needle in normalise_path(e["cwd"])]
    return chosen, index.search(entries, args.terms, chosen)


def title_of(entry: dict) -> str:
    text = entry["title"] or (entry["prompts"][0] if entry["prompts"] else "") or entry["fallback"]
    return clip(text, 110) or "(untitled)"


def cmd_find(argv: list[str]) -> int:
    args = find_parser().parse_args(argv)
    chosen, entries = gather(args)
    entries = entries[: max(args.limit, 0)]

    if args.json:
        json.dump(entries, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if entries else 1
    if args.tsv:
        for e in entries:
            print("\t".join([e["id"], e["provider"], e["cwd"] or "?", e["branch"] or "-",
                             age(e["mtime"]), str(e["turns"]), title_of(e), e["state"]]))
        return 0 if entries else 1
    if not entries:
        note("No session matches: " + " ".join(args.terms) if args.terms else "No sessions found.")
        return 1
    if args.list:
        print_table(entries, len(chosen) > 1)
        return 0

    entry = entries[0] if len(entries) == 1 and args.terms else pick(entries)
    return resume(entry, args.no_cd) if entry else 0


def print_table(entries: list[dict], with_provider: bool) -> None:
    s = Style()
    head = f"{'AGE':<5} {'TURNS':>5} {'STATE':<5} " + (f"{'AGENT':<7} " if with_provider else "")
    print(f"{s.dim}{head}{'TITLE':<62} BRANCH{s.off}")
    for e in entries:
        agent = f"{e['provider']:<7} " if with_provider else ""
        print(f"{age(e['mtime']):<5} {e['turns']:>5} {e['state']:<5} {agent}"
              f"{clip(title_of(e), 62):<62} {s.dim}{e['branch']}{s.off}")


def pick(entries: list[dict]) -> dict | None:
    if shutil.which("fzf"):
        return pick_fzf(entries)
    return pick_menu(entries)


def pick_fzf(entries: list[dict]) -> dict | None:
    keyed = {f"{e['provider']}:{e['id']}": e for e in entries}
    rows = "\n".join("\t".join([key, title_of(e), e["state"], e["branch"] or "-",
                                age(e["mtime"]), e["cwd"] or "?"]) for key, e in keyed.items())
    src = str(Path(__file__).resolve().parent.parent)
    env = dict(os.environ, PYTHONPATH=src + os.pathsep + os.environ.get("PYTHONPATH", ""))
    preview = shlex.join([sys.executable, "-m", "threadr", "show"]) + " {1}"
    done = subprocess.run(
        ["fzf", "--delimiter=\t", "--with-nth=2,3,4,5,6", "--no-multi", "--height=85%",
         "--layout=reverse", "--prompt=session> ", "--header=enter=resume  esc=cancel",
         "--preview=" + preview, "--preview-window=right:55%:wrap"],
        input=rows, stdout=subprocess.PIPE, text=True, env=env)
    line = done.stdout.strip()
    return keyed.get(line.split("\t", 1)[0]) if done.returncode == 0 and line else None


def pick_menu(entries: list[dict]) -> dict | None:
    s = Style()
    for i, e in enumerate(entries, 1):
        print(f"{i:3d}) {age(e['mtime']):<5} {title_of(e)}")
        print(f"     {s.dim}{e['cwd']}  [{e['branch'] or '-'}]{s.off}")
    try:
        choice = input("Session number (blank to cancel): ").strip()
    except EOFError:
        return None
    if not choice:
        return None
    if not choice.isdigit() or not 1 <= int(choice) <= len(entries):
        fail("not a listed number: " + choice)
        return None
    return entries[int(choice) - 1]


def resume(entry: dict, no_cd: bool) -> int:
    s = Style(sys.stderr)
    provider = providers.get(entry["provider"])
    if entry["state"] == "gone":
        note("That session's transcript was deleted - it cannot be resumed.")
        note("These prompts survive:")
        print()
        for text in provider.recover(entry["id"]) or []:
            print("> " + text + "\n")
        return 1

    cwd = entry["cwd"]
    if not no_cd and cwd:
        if os.path.isdir(cwd):
            os.chdir(cwd)
            # The shell wrapper reads this to cd the calling shell afterwards.
            target = os.environ.get("THREADR_CD_FILE")
            if target:
                Path(target).write_text(cwd, encoding="utf-8")
        else:
            note(f"Directory is gone: {cwd} - resuming in place.")

    argv = provider.resume_argv(entry["id"], yolo())
    if not shutil.which(argv[0]):
        return fail(f"{argv[0]} not found on PATH")
    print(f"{s.green}Resuming {title_of(entry)}{s.off}", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    os.execvp(argv[0], argv)
    return 0


# --- show / recover ---------------------------------------------------------------
def lookup(key: str, refresh: bool = False) -> dict | None:
    name, _, sid = key.rpartition(":")
    for e in index.load(providers.enabled(name or None), refresh=refresh):
        if e["id"] == sid:
            return e
    return None


def cmd_show(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="threadr show", description="A digest of one session.")
    ap.add_argument("id", help="session id, optionally provider:id")
    args = ap.parse_args(argv)
    e = lookup(args.id)
    if e is None:
        return fail("no session " + args.id)
    print(e["title"] or "(untitled)")
    print("-" * 60)
    print("agent   " + e["provider"])
    print("dir     " + (e["cwd"] or "?"))
    print("branch  " + (e["branch"] or "-"))
    print(f"turns   {e['turns']}   last active {age(e['mtime'])} ago   ({e['state']})")
    print("id      " + e["id"])
    print()
    for text in e["prompts"][:14]:
        print("> " + text[:300] + "\n")
    return 0


def cmd_recover(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="threadr recover",
                                 description="Print the prompts that survive for a session, "
                                             "even one whose transcript was deleted.")
    ap.add_argument("id", help="session id, optionally provider:id")
    ap.add_argument("--provider", help="which provider to ask")
    args = ap.parse_args(argv)
    name, _, sid = args.id.rpartition(":")
    for provider in providers.enabled(args.provider or name or None):
        prompts = provider.recover(sid)
        if prompts:
            print(f"session   {sid}  ({provider.name})")
            print(f"prompts   {len(prompts)} (replies are not kept)\n")
            for text in prompts:
                print("> " + text + "\n")
            return 0
    return fail("nothing survives for " + args.id)


# --- tree -------------------------------------------------------------------------
def cmd_tree(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="threadr tree",
                                 description="Reconstruct which sessions were forked from "
                                             "which, newest families first.")
    ap.add_argument("--all", action="store_true", help="include sessions never forked")
    ap.add_argument("--cwd", help="only families in this directory")
    ap.add_argument("--provider", help="only these providers, comma separated")
    ap.add_argument("--mermaid", action="store_true", help="a mermaid flowchart")
    ap.add_argument("--json", action="store_true", help="the forest as JSON")
    ap.add_argument("--html", nargs="?", const="", metavar="FILE",
                    help="write a self-contained page (default: a temp file, opened)")
    ap.add_argument("--no-color", "--no-colour", action="store_true", help="plain ASCII")
    args = ap.parse_args(argv)

    started = time.time()
    roots = tree.forest(providers.enabled(args.provider), args.cwd, args.all)
    if not roots:
        note("No forked sessions found - every conversation is a single line.")
        note("Pass --all to list unforked sessions too.")
        return 1

    if args.json:
        json.dump(tree.payload(roots), sys.stdout, indent=1)
        sys.stdout.write("\n")
        return 0
    if args.mermaid:
        tree.draw_mermaid(roots, sys.stdout)
        return 0
    if args.html is not None:
        target = Path(args.html or Path(tempfile.gettempdir()) / "threadr-fork-map.html")
        tree.draw_html(roots, target.expanduser())
        print("wrote " + str(target))
        if not args.html:
            opener = shutil.which("open") or shutil.which("xdg-open")
            if opener:
                subprocess.run([opener, str(target)], capture_output=True)
        return 0

    s = Style(enabled=None if not args.no_color else False)
    for root in roots:
        tree.draw_ascii(root, sys.stdout, s)
    total = sum(len(tree.family_of(r)) for r in roots)
    forks = total - len(roots)
    print(f"{len(roots)} families, {total} sessions, {forks} fork{'' if forks == 1 else 's'} "
          f"({time.time() - started:.1f}s)")
    return 0


# --- fork -------------------------------------------------------------------------
def cmd_fork(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="threadr fork",
        description="Fork the agent session this runs inside into a new herdr workspace or "
                    "tmux window, in the same directory. No git branch, no worktree: the "
                    "fork shares the working tree. THREADR_MUX=herdr|tmux forces a mux.")
    ap.add_argument("label", nargs="?", help="a name for the fork (default fork-HHMMSS)")
    args = ap.parse_args(argv)

    found = providers.current()
    if not found:
        return fail("not inside a supported agent session (no CLAUDE_CODE_SESSION_ID)")
    provider, sid = found
    label = args.label or "fork-" + time.strftime("%H%M%S")
    command = provider.fork_argv(sid, label, yolo())
    if command is None:
        return fail(f"{provider.name} sessions cannot be forked")
    if not shutil.which(command[0]):
        return fail(f"{command[0]} not found on PATH")
    try:
        mux = choose()
    except MuxError as err:
        return fail(str(err))

    cwd = os.getcwd()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True,
                           text=True) if shutil.which("git") else None
    if dirty and dirty.returncode == 0 and dirty.stdout.strip():
        print("note: working tree is dirty (shared with the fork, not copied):")
        for line in dirty.stdout.splitlines()[:8]:
            print("    " + line)

    try:
        lines = mux.open(cwd, label, command)
    except MuxError as err:
        return fail(str(err))
    print(f"forked {sid} as '{label}'")
    for line in lines + [f"cwd {cwd} (shared working tree)"]:
        print("  " + line)
    return 0


# --- doctor -----------------------------------------------------------------------
def cmd_doctor(argv: list[str]) -> int:
    s = Style()
    ok, no = f"{s.green}ok{s.off}  ", f"{s.dim}--{s.off}  "
    print(f"threadr {__version__}   python {sys.version.split()[0]}")
    print("\nproviders")
    for name, cls in providers.PROVIDERS.items():
        p = cls()
        count = len(p.transcripts())
        print(f"  {name:<8} {ok if p.available() else no}{count} transcripts")
    print("\nmultiplexers")
    for name, mux in MUXES.items():
        where = "  (this shell is inside it)" if mux.inside() else ""
        print(f"  {name:<8} {ok if mux.found() else no}{where}")
    print("\npicker")
    print(f"  {'fzf':<8} {ok if shutil.which('fzf') else no}"
          f"{'' if shutil.which('fzf') else 'falls back to a numbered menu'}")
    print("\nshell")
    wrapped = bool(os.environ.get("THREADR_CD_FILE"))
    hint = "" if wrapped else 'add  eval "$(threadr init zsh)"  to your rc file'
    print(f"  {'wrapper':<8} {ok if wrapped else no}{hint}")
    print(f"  {'yolo':<8} {ok if yolo() else no}"
          f"{'permission prompts skipped' if yolo() else 'THREADR_YOLO unset'}")
    return 0


def cmd_init(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="threadr init",
                                 description='Print the shell hook. In your rc file: '
                                             'eval "$(threadr init zsh)"')
    ap.add_argument("shell", choices=["zsh", "bash"])
    ap.parse_args(argv)
    print((Path(__file__).parent / "threadr.sh").read_text(encoding="utf-8"), end="")
    return 0


COMMANDS = {"find": cmd_find, "show": cmd_show, "recover": cmd_recover,
            "tree": cmd_tree, "fork": cmd_fork, "doctor": cmd_doctor,
            "init": cmd_init}


def main(argv: list[str] | None = None) -> int:
    utf8_streams()
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if argv and argv[0] in ("-V", "--version"):
        print("threadr " + __version__)
        return 0
    if argv and argv[0] in COMMANDS:
        return COMMANDS[argv[0]](argv[1:])
    return cmd_find(argv)
