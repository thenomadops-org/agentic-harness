---
name: session-reflection
description: Write a reflection note for the current session into the Obsidian vault — what shipped, what was learned, what is still open — with token and cost figures measured from the session transcript, never estimated. One note per session, since several run concurrently. Invoke at the end of a working session, or when the user asks to "write the session note", "reflect on this session", or "/session-reflection".
---

# Session reflection → vault

Several sessions run at once, so **one note per session**, keyed on session id. A
daily rollup aggregates them. Both live in `~/Code/Obsidian/Sessions/`, and
obsidian-git commits and pushes on its 5-minute interval.

## 1. Identify the session

The session id is the transcript filename:
`~/.claude/projects/<slug>/<session-id>.jsonl`. The newest transcript in the
project directory is almost always the current session — confirm by checking its
mtime is recent rather than assuming.

## 2. Get the numbers — measured, never estimated

```bash
cd ~/Code/Obsidian
python3 scripts/session_metrics.py --write     # refresh the ledger
python3 scripts/session_metrics.py --daily     # per-day, bucketed by message date
```

⚠️ **Two traps this script exists to avoid:**

**Never sum the token classes into one "tokens" figure.** `cache_read` dwarfs
everything — the first real sample was 3.2×10⁹ cache-read against 3.4×10⁴ input.
They bill at very different rates, so a single total looks precise and means
nothing. Report the four separately.

**Never attribute a session's usage to its start date.** Sessions outlive days —
the first sample had one running 2026-08-05 → 08-10. Per-day figures must come
from `--daily`, which buckets by each message's own timestamp.

If a figure cannot be read, write that it is unavailable. **Do not estimate a
token count.** A guessed number in a table is indistinguishable from a measured
one, and the whole point of this note is to be data worth trusting later.

## 3. Write the note

`Sessions/YYYY-MM-DD-<first8-of-session-id>-<project>.md`, with the vault's
8-field frontmatter (`type: meta`) or `lint_vault.py` fails:

```yaml
---
title: "2026-08-09 · my-project · c8eec600"
tags: [vault, type/meta, domain/<domain>, session]
type: meta
domain: <domain>
repo: <repo>
status: active
color: blue
created: YYYY-MM-DD
---
```

Body — keep it short and specific; this is a record, not a narrative:

- **Shipped** — PRs merged/opened, tickets moved, with numbers
- **Learned** — anything durable. If it is a *shape* that recurs across repos,
  promote it to `00-Index/Operational-Gotchas.md`; if it is a fact about one
  codebase, to `_Memory/<repo>-Memory.md`. The reflection records that you did.
- **Got wrong** — mistakes and corrections, plainly. This is the highest-value
  section and the one most easily skipped. A reflection that only lists wins is
  a status report, not a reflection.
- **Still open** — what the next session inherits, and what is owner-gated
- **Usage** — the four token classes, turns, tool calls, subagents

## 4. Link it, or lint fails

`lint_vault.py` enforces that every page has an inbound link. Add the note to
`Sessions/YYYY-MM.md` (create it from the same frontmatter shape if absent) and
make sure that month index is itself linked from `00-Index/Session-Dashboard.md`.
An unlinked note breaks the vault's own check.

## 5. Verify

```bash
cd ~/Code/Obsidian && python3 lint_vault.py | tail -3
```

Must read `LINT CLEAN`. If it does not, fix the note rather than leaving the
vault failing its own contract.

## On the dollar figure

The subscription is a flat **$100/month**, so tokens carry **no per-token cost**.
Two different questions, and they must not be conflated:

- **Effective rate** — `$100 ÷ tokens actually used this month`. What you paid.
- **Notional API cost** — what the same usage would have cost at list prices.
  A value estimate, not a bill.

`00-Index/Session-Dashboard.md` keeps the rate assumptions in one visible block
so the arithmetic is transparent and correctable. **Do not hardcode prices into
notes** — rates change, and a stale rate silently poisons every historical
figure. Read them from the dashboard's assumption block, and if you cannot
verify current rates, say the notional figure is unavailable rather than
publishing a wrong one.
