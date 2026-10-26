---
title: "Parse, don't pattern-match — then pin what you didn't parse"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "fixing a check that missed a case, or adding another pattern to a matcher"
---

When a checker misses a case, the reflex is to add a pattern for the case it
missed. That leaves a narrower hole of exactly the same shape, and the next
miss looks like a new bug rather than the same one.

Across eight fixes to one family of checks, seven produced a smaller version of
the original hole. Each looked like progress and each was overtaken within
weeks.

**Why:** a pattern says what you thought of. The input is written by someone who
did not read your pattern. Every list of shapes is a list of the shapes you
happened to imagine.

**How to apply:** offer exactly two outcomes and refuse the middle. Either
**parse** the thing — understand its structure well enough to reason about any
input — or **pin the gap**: state plainly that this class is not covered and
fail closed on it. What is forbidden is the third option, where you handle more
cases than before and imply you handle all of them.

If parsing is too expensive, pinning is not a defeat. A documented gap is
survivable; a checker believed to be complete is not.

Related: [[claims-strengthen-as-they-propagate]]
