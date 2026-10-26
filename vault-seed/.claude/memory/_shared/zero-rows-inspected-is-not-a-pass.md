---
title: "Zero rows inspected is not a pass"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-28
trigger: "reading a green check, or writing one"
---

A vault linter selected zero of nine hundred notes for its main rule and reported
clean for weeks. It was dead twice over: it filtered on a directory that had been
deleted, and on a status value the schema had never allowed. Either bug alone
would have emptied the set; each hid the other, and the green tick looked
identical to a real pass.

A separate check gated on `cmd | tail && next`. That reads `tail`'s exit status,
which is always `0`, so the gate could not fail whatever the command did.

**Why:** a check that inspects nothing and a check that finds nothing wrong
produce the same output. Failure is loud; vacuity is silent, and it survives
exactly as long as nobody asks how many rows were examined.

**How to apply:** make every check report its denominator — *n inspected* — and
fail when the denominator is zero. Never gate on a pipeline's exit status; test
the command's own status, or `set -o pipefail`.

Before trusting a new check, **break the thing it guards and watch it go red.**
A check nobody has tried to break has an unknown pass rate, and writing it does
not tell you which of the two greens you are looking at.

Related: [[a-guard-is-a-snapshot-not-a-subscription]] · [[parse-dont-pattern-match]]
