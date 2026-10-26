---
title: "Reach for a mandate before a wrapper"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "about to write a script that shells out to a CLI you already trust"
---

A merge gate was built as a script to enforce a checklist that a handful of
direct API calls already answered. The script then needed its own error
handling, its own tests, its own bug fixes — and it became a second thing that
could be wrong about whether the merge was safe.

**Why:** a wrapper does not remove the underlying tool, it adds a layer that can
disagree with it. When they disagree, you debug the wrapper while believing you
are debugging the process.

**How to apply:** before writing a wrapper, ask what it adds beyond invocation.
If the answer is "it remembers the right flags" or "it runs them in order", write
a **mandate** instead — a documented procedure with the exact commands, which an
agent can follow and a human can read.

Write the script when it does something the commands cannot: reconciling several
sources, enforcing an invariant across them, or making an unsafe operation atomic.

The test is whether the layer could ever be *wrong* while the underlying command
was right. If yes, it needs its own tests, and that cost belongs in the decision.

Related: [[never-mutate-to-test-a-refusal]]
