---
name: stop-work
description: The coordinator loop this skill stopped was removed in OPS-333. The script fails closed and releases nothing. Use when someone asks to stop work, so the answer is that there is no lease to release.
---

# /stop-work

The coordinator loop (`/start-ready-work`, spec F6) was removed in OPS-333.
This skill stays so a request to stop work gets a clear refusal instead of a
missing command. It does not release a lease, because there is no lease.

Run: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/stop-work/stop.py --project P`

The script exits 2 and says the loop was removed. Report that. Do not claim
the loop stopped, and do not invent a lease release.

Recoverable from tag `pre-harness-rewrite` (`c114b2e`). The harness rewrite
is OPS-334.
