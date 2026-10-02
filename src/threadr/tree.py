"""Reconstruct which sessions were forked from which, and draw it.

No agent records a fork's parent, so the lineage is rebuilt from two facts
(see docs/lineage.md):

  * how many message ids two sessions hold in common - the size of the
    history one inherited from the other, and
  * when each session's *own* messages start - the line that was already
    running before the other's first exclusive message is the parent.

Message ids are compared as sets, not as a prefix: compaction rewrites a
transcript, so inherited messages survive but their order does not.
"""
from __future__ import annotations

import itertools
import json
import shlex
from collections import Counter
from pathlib import Path

from .util import clip, normalise_path, when

# uuids are random, so even a couple in common means real shared history.
MIN_OVERLAP = 2


def collect(providers: list) -> list[dict]:
    """Lineage records for the fullest copy of every session, per provider."""
    sessions = []
    for provider in providers:
        best: dict = {}
        for path in provider.transcripts():
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if path.stem not in best or size > best[path.stem][0]:
                best[path.stem] = (size, path)
        for _, path in best.values():
            record = provider.lineage(path)
            if record:
                record["provider"] = provider.name
                record["set"] = set(record["uuids"])
                record["turns"] = len(record["prompts"])
                record["messages"] = len(record["uuids"])
                record["resume"] = shlex.join(provider.resume_argv(record["id"]))
                sessions.append(record)
    return sessions


def overlaps(sessions: list[dict]) -> Counter:
    """Shared-id counts for every pair that shares any history at all."""
    owners: dict = {}
    for index, session in enumerate(sessions):
        for uuid in session["set"]:
            owners.setdefault(uuid, []).append(index)
    counts: Counter = Counter()
    for holders in owners.values():
        for pair in itertools.combinations(sorted(holders), 2):
            counts[pair] += 1
    return Counter({p: n for p, n in counts.items() if n >= MIN_OVERLAP})


def first_exclusive(session: dict, other: dict) -> str:
    """When this session's own history - the part `other` never had - begins.

    A minimum over every exclusive message, not the first in file order,
    because compaction can reorder a transcript.
    """
    theirs = other["set"]
    best = ""
    for uuid, stamp in zip(session["uuids"], session["stamps"]):
        if stamp and uuid not in theirs and (not best or stamp < best):
            best = stamp
    return best


class Node:
    """A session, plus the forks taken off it."""

    def __init__(self, session: dict):
        self.session = session
        self.children: list = []
        self.parent = None
        self.inherited = 0      # messages carried over from the parent
        self.forked_at = ""     # when this fork's own history starts


def build_forest(sessions: list[dict]) -> list[Node]:
    """Give every session a parent where one can be justified.

    Parent of X = the session sharing the most history with X, among those
    whose own messages started before X's did. That is a strict ordering in
    time, so the result cannot contain a cycle.
    """
    pairs = overlaps(sessions)
    nodes = [Node(s) for s in sessions]
    if not pairs:
        return nodes

    diverge = {(i, j): (first_exclusive(sessions[i], sessions[j]),
                        first_exclusive(sessions[j], sessions[i]))
               for (i, j) in pairs}

    for index, node in enumerate(nodes):
        best = None
        for (i, j), shared in pairs.items():
            if index not in (i, j):
                continue
            other = j if i == index else i
            mine, theirs = diverge[(i, j)] if i == index else diverge[(i, j)][::-1]
            # The other line must already have been running on its own.
            if not theirs or (mine and theirs >= mine):
                continue
            # Most shared history wins. On a tie the fork point sat in history
            # both candidates hold, so attach to the shallower one.
            key = (shared, -sessions[other]["messages"])
            if best is None or key > best[0]:
                best = (key, other, shared, mine)
        if best is not None:
            _, parent, shared, mine = best
            node.inherited, node.forked_at, node.parent = shared, mine, nodes[parent]

    # A fork cannot inherit less history than the line it came off: if it
    # looks that way, the real split happened further up. Walk it up.
    for node in nodes:
        while node.parent is not None and node.parent.inherited > node.inherited:
            node.parent = node.parent.parent

    for node in nodes:
        if node.parent is not None:
            node.parent.children.append(node)
    for node in nodes:
        node.children.sort(key=lambda c: (c.inherited, c.forked_at))
    return [n for n in nodes if n.parent is None]


def family_of(root: Node) -> list[Node]:
    out = [root]
    for child in root.children:
        out.extend(family_of(child))
    return out


def opening_prompt(node: Node) -> str:
    """The first thing said on this line after it split from its parent."""
    prompts = node.session["prompts"]
    if not prompts:
        return ""
    if not node.forked_at:
        return prompts[0][1]
    for stamp, text in prompts:
        if stamp >= node.forked_at:
            return text
    return prompts[-1][1]


def forest(providers: list, cwd: str | None = None, everything: bool = False) -> list[Node]:
    roots = build_forest(collect(providers))
    if not everything:
        roots = [r for r in roots if r.children]
    if cwd:
        needle = normalise_path(cwd)
        roots = [r for r in roots if needle in normalise_path(r.session["cwd"])]
    roots.sort(key=lambda r: max(m.session["last"] for m in family_of(r)), reverse=True)
    return roots


# --- ASCII --------------------------------------------------------------------
def draw_ascii(root: Node, out, s) -> None:
    members = family_of(root)
    forks = len(members) - 1
    out.write(f"{s.bold}{root.session['cwd'] or '?'}{s.off}  {s.dim}{len(members)} sessions, "
              f"{forks} fork{'' if forks == 1 else 's'}{s.off}\n")

    def walk(node: Node, prefix: str, is_last: bool, top: bool) -> None:
        x = node.session
        elbow = "" if top else ("'- " if is_last else "|- ")
        pad = prefix if top else prefix + ("   " if is_last else "|  ")
        if top:
            mark, tag = f"{s.green}*{s.off}", f"{s.green}main line{s.off}"
            edge = f"{when(x['first'])} -> {when(x['last'])}"
        else:
            mark, tag = f"{s.yellow}+{s.off}", f"{s.yellow}fork{s.off}"
            edge = f"forked {when(node.forked_at)}, inherited {node.inherited} msgs"
        out.write(f"{prefix}{elbow}{mark} {s.bold}{clip(x['title'], 58)}{s.off}"
                  f"  {s.dim}[{s.off}{tag}{s.dim}]{s.off}\n")
        out.write(f"{pad}  {s.dim}{x['id'][:8]}  {x['turns']} turns  {edge}"
                  f"{'  compacted' if x['compacted'] else ''}{s.off}\n")
        if x["branch"]:
            out.write(f"{pad}  {s.dim}git: {x['branch']}{s.off}\n")
        quote = opening_prompt(node)
        if quote:
            out.write(f"{pad}  {s.dim}\"{clip(quote, 60)}\"{s.off}\n")
        for i, child in enumerate(node.children):
            walk(child, pad, i == len(node.children) - 1, False)

    walk(root, "", True, True)
    out.write("\n")


# --- mermaid ------------------------------------------------------------------
def draw_mermaid(roots: list[Node], out) -> None:
    out.write("flowchart LR\n")
    counter = [0]

    def esc(text: str) -> str:
        return clip(text, 46).replace('"', "'").replace("[", "(").replace("]", ")")

    def walk(node: Node, parent_id) -> None:
        counter[0] += 1
        nid = f"n{counter[0]}"
        x = node.session
        out.write(f'    {nid}["{esc(x["title"])}<br/>{x["turns"]} turns"]\n')
        if parent_id is None:
            out.write(f"    style {nid} stroke-width:2px\n")
        else:
            out.write(f'    {parent_id} -->|"+{node.inherited} msgs"| {nid}\n')
        for child in node.children:
            walk(child, nid)

    for root in roots:
        counter[0] += 1
        out.write(f'  subgraph f{counter[0]}["{esc(root.session["cwd"] or "?")}"]\n')
        walk(root, None)
        out.write("  end\n")


# --- JSON and HTML ------------------------------------------------------------
def node_to_dict(node: Node, top: bool) -> dict:
    x = node.session
    return {
        "id": x["id"],
        "provider": x["provider"],
        "title": x["title"] or "(untitled)",
        "turns": x["turns"],
        "messages": x["messages"],
        "branch": x["branch"],
        "cwd": x["cwd"],
        "first": x["first"],
        "last": x["last"],
        "compacted": x["compacted"],
        "isFork": not top,
        "inherited": node.inherited,
        "forkedAt": node.forked_at,
        "prompt": clip(opening_prompt(node), 320),
        "resume": x["resume"],
        "children": [node_to_dict(c, False) for c in node.children],
    }


def payload(roots: list[Node]) -> list[dict]:
    data = []
    for root in roots:
        members = family_of(root)
        data.append({
            "cwd": root.session["cwd"] or "?",
            "sessions": len(members),
            "forks": len(members) - 1,
            "last": max((m.session["last"] for m in members), default=""),
            "tree": node_to_dict(root, True),
        })
    data.sort(key=lambda f: f["last"], reverse=True)
    return data


def draw_html(roots: list[Node], path: Path) -> None:
    template = (Path(__file__).parent / "tree.html").read_text(encoding="utf-8")
    # Keep a stray "</script>" in a prompt from closing the data block early.
    data = json.dumps(payload(roots), indent=1).replace("</", "<\\/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.replace("__DATA__", data), encoding="utf-8")
