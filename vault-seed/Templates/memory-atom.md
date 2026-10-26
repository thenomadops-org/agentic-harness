---
title: "{{SHORT TITLE}}"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: {{DATE}}
trigger: "{{when this should come to mind — one distinct phrase}}"
---

{{The fact, in two or three sentences. What is true, stated plainly.}}

**Why:** {{what it cost to learn — the incident, the wrong answer, the outage.
A memory with no cost attached tends to be a preference wearing a fact's clothes.}}

**How to apply:** {{what to do differently next time. Concrete enough to act on
without re-reading the incident.}}

Related: [[{{another-atom}}]]

<!--
SCOPE. Put this in .claude/memory/_shared/ only if it is true regardless of
client. Anything naming a cluster, board, repo or product goes in
.claude/memory/<client>/ instead. lint_vault.py flags shared atoms that read
like client facts, but it cannot catch the reverse.

TRIGGER. Make it distinct. Two atoms with near-identical triggers means the
"is it ONE thing?" test failed and neither will match cleanly — the lint
checks for that.

Link this from your <Name>-Memory.md index or it is an orphan: correct,
findable by nobody, and never retrieved.
-->
