# Hooks

The hard-law hooks (spec F8). `hooks.json` registers each one with Claude
Code; every hook lives in its own folder here and carries its own tests.

| Hook | Event | Law |
|---|---|---|
| `boundary/` | `PreToolUse` on `Bash` | F8: the publication-boundary check gates commit and push |
| `production/` | `PreToolUse` on `Bash` | F8: a command matching the project file's production patterns is the owner's |

`hooks.json` is shared: add your entry, change no one else's.

The merge gate (the builder is not the reviewer, the verifier uses a different
model, CI is green on the head) was removed in OPS-333. The rules to port into
the Phase 1 qa-verdict check are in
[`docs/decisions/merge-gate-rules-for-phase1.md`](../../docs/decisions/merge-gate-rules-for-phase1.md).
Recoverable from tag `pre-harness-rewrite` (`c114b2e`).

Tests:

    python3 -m unittest discover -s plugin/hooks/boundary
    python3 -m unittest discover -s plugin/hooks/production
