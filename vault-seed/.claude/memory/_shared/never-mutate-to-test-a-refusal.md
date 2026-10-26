---
title: "Never mutate to test a refusal"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "about to check whether an action would be blocked"
---

To find out whether a merge would be refused, the obvious move is to attempt the
merge and read the error. **The attempt is the action.** If the guard is absent,
misconfigured, or the state changed a second ago, you have performed the thing
you were checking.

**Why:** a refusal test that works by trying it has no safe failure mode. It is
correct only when the guard is correct — which is the thing in question.

**How to apply:** read the state instead. Merge safety is a field you can query;
permissions are a field you can query. Almost every "would this be allowed"
question has a read-only form, and where it does not, that is worth knowing
before you find out the expensive way.

Generalises past merges: do not test whether a delete is blocked by deleting, or
whether a deploy gate holds by deploying. **Ask what it would do; do not do it
and observe.**

Related: [[prefer-a-mandate-over-a-wrapper]] · [[dont-engineer-around-a-deny-rule]]
