"""A provider-neutral, incrementally cached index of sessions, and ranked search."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from .util import cache_dir, note

CACHE_VERSION = 1
# Field weights for ranking.
WEIGHTS = {"title": 12, "branch": 7, "cwd": 5, "prompts": 3, "replies": 1}


def cache_file() -> Path:
    return cache_dir() / "index.json"


def load(providers: list, refresh: bool = False) -> list[dict]:
    """Every session from every provider, one row per conversation, newest first."""
    path = cache_file()
    cache: dict = {}
    if path.exists() and not refresh:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            if blob.get("version") == CACHE_VERSION:
                cache = {e["file"]: e for e in blob.get("entries", [])}
        except (ValueError, OSError, KeyError):
            cache = {}

    entries, seen, dirty = [], set(), False
    for provider in providers:
        for transcript in provider.transcripts():
            key = str(transcript)
            seen.add(key)
            try:
                stat = transcript.stat()
            except OSError:
                continue
            cached = cache.get(key)
            if cached and cached["mtime"] == stat.st_mtime and cached["size"] == stat.st_size:
                entries.append(cached)
                continue
            dirty = True
            record = provider.scan(transcript)
            if record:
                record.update(provider=provider.name, file=key, state="live",
                              mtime=stat.st_mtime, size=stat.st_size)
                entries.append(record)

    if dirty or seen != set(cache):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": CACHE_VERSION, "entries": entries}),
                       encoding="utf-8")
        tmp.replace(path)

    # An agent may mirror one session into several folders; keep the fullest copy.
    best: dict = {}
    for entry in entries:
        key = (entry["provider"], entry["id"])
        rival = best.get(key)
        if rival is None or (entry["size"], entry["mtime"]) > (rival["size"], rival["mtime"]):
            best[key] = entry

    for provider in providers:
        for orphan in provider.orphans():
            key = (provider.name, orphan["id"])
            if key not in best:
                orphan.update(provider=provider.name, file="", state="gone", size=0)
                best[key] = orphan

    return sorted(best.values(), key=lambda e: e["mtime"], reverse=True)


def score(entry: dict, terms: list[str]) -> tuple:
    """(weight, how many of the terms landed in any field)."""
    fields = {
        "title": entry["title"].lower(),
        "branch": entry["branch"].lower(),
        "cwd": entry["cwd"].lower(),
        "prompts": " ".join(entry["prompts"]).lower(),
        "replies": " ".join(entry.get("replies", [])).lower(),
    }
    total = hits = 0
    for term in terms:
        best = 0
        for name, text in fields.items():
            if term in text:
                weight = WEIGHTS[name]
                if re.search(r"\b" + re.escape(term), text):
                    weight += 2
                best = max(best, weight)
        if best:
            hits += 1
            total += best
    return total, hits


def deep_scan(providers: list, terms: list[str]) -> set:
    """(provider, id) of every transcript containing all terms, read in full.

    The index keeps a bounded digest of each conversation, so anything said
    deep inside a long reply is invisible to it. This is the slow, exact path.
    """
    found = set()
    for provider in providers:
        for path in provider.transcripts():
            key = (provider.name, path.stem)
            if key in found:
                continue
            remaining = set(terms)
            try:
                fh = path.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if provider.skip_line(line):
                        continue
                    low = line.lower()
                    remaining = {t for t in remaining if t not in low}
                    if not remaining:
                        found.add(key)
                        break
    return found


def search(entries: list[dict], terms: list[str], providers: list,
           say: Callable[[str], None] = note) -> list[dict]:
    """Rank entries against terms. Recall is layered and each fallback says so."""
    terms = [t.lower() for t in terms if t.strip()]
    if not terms:
        return entries
    ranked = [(score(e, terms), e) for e in entries]
    full = [(w, e) for (w, hits), e in ranked if hits == len(terms)]
    if full:
        ranked = full
    else:
        say("Not in the index digest; scanning full transcripts...")
        deep = deep_scan(providers, terms)
        rows = [(w, e) for (w, _), e in ranked if (e["provider"], e["id"]) in deep]
        if rows:
            ranked = rows
        else:
            ranked = [(hits * 1000 + w, e) for (w, hits), e in ranked if hits]
            if ranked:
                say("No session matched every term; showing the best partial matches.")
    ranked.sort(key=lambda pair: (pair[1]["mtime"], pair[0]), reverse=True)
    return [e for _, e in ranked]
