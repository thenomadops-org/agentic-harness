---
title: "A guard is a snapshot, not a subscription"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-28
trigger: "citing a check that passed earlier in the session as evidence that it still passes"
---

An agent working a long task ran the file-contention guard, got a clean result,
kept editing for another hour, and reported the clean result as its verification.
By then it had modified a contended file another agent held a lock on. Re-running
the same command at the end failed immediately and named the file.

The tool was never broken. The pass was true when it was taken and stale when it
was quoted.

**Why:** a check answers a question about the world *at the moment it runs*. An
agent's own edits are exactly the thing most likely to invalidate it, so the
period between "guard passed" and "work finished" is the period in which the
answer is most likely to change — and nothing announces the change.

This is why the coordinator's first diagnosis was also wrong: told the guard had
passed while a violation existed, it concluded the guard's scope was too narrow.
Running the guard again — one command — showed the scope was fine and the
timestamp was not.

**How to apply:** re-run the guard immediately before the commit, every commit,
not once per session. When you quote a check as evidence, quote one you ran
after your last edit. And when a check and reality disagree, **re-run the check
before theorising about it** — a stale pass and a broken tool are indistinguishable
in a report and take one command to tell apart.

Related: [[verify-the-merge-dont-take-the-report]] · [[zero-rows-inspected-is-not-a-pass]]
