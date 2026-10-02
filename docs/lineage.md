# How `threadr tree` finds forks

Forking a Claude Code conversation (`claude --resume <id> --fork-session`,
which is what `/branch-out` runs) writes a brand-new transcript. It gets a new
session id, and `sessionId` is rewritten on every line it copied. **Nothing in
the new transcript points at its parent.** Claude Code has no record of the
tree, so `threadr tree` rebuilds it from two facts.

## 1. Shared message ids

A fork keeps the `uuid` of every message it inherited. The size of the overlap
between two sessions' uuid sets is how much history one took from the other.
uuids are random, so any overlap at all (threadr requires two) means real
shared ancestry. A coincidence isn't possible.

## 2. When each line's own messages start

Overlap says two sessions are related but not which is the parent. For that,
threadr looks at each session's *exclusive* messages, the ones the other never
had, and takes the earliest timestamp among them. The session whose own history
began first was already running when the other split off.

## The rule

> Parent of X = the session sharing the most history with X, among those whose
> own messages started before X's did.

That is a strict ordering in time, so the result can't contain a cycle. On a
tie in shared history the fork point sat in history both candidates hold, so X
attaches to the shallower one.

One correction is applied afterwards. A fork can't inherit *less* history than
the line it came off. If one appears to, the real split happened further up,
and the node is re-attached to its grandparent until that holds.

## Why sets and not a prefix

Compaction (`/compact`, or an automatic `compact_boundary`) rewrites a
transcript in place. The inherited messages survive but their order doesn't,
so a fork is not a prefix of its parent. Comparing sets is order-independent,
and "first exclusive message" is a minimum over all exclusive messages rather
than the first one in file order.

Sessions marked `compacted` can report an inherited count slightly below the
truth for the same reason.

## Other providers

The algorithm only needs message ids and timestamps. A provider supplies them
through `Provider.lineage()` (see [providers.md](providers.md)). Providers
without stable message ids return `None` and are left out of the tree, but
they still work for search and resume.
