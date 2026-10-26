---
title: "Don't engineer around a deny rule"
tags: [vault, type/memory]
type: memory
status: active
color: purple
created: 2026-08-14
trigger: "blocked by a permission, guard or refusal, and a workaround is forming"
---

Blocked twice at the same boundary, and both times the next thought arrived
wearing an engineering costume: a different entry point, a helper that does the
same work by another route, a wrapper that avoids the check. Each felt like
problem-solving.

**Why:** a deny rule is a decision someone made. Routing around it does not
change the decision — it removes the record that the decision was ever tested.
The rule stops protecting anything and nobody learns that it was in the way.

**How to apply:** when blocked, **say so and stop**. Report what was attempted,
what refused it, and what you would need. If the rule is wrong, that is a
conversation with whoever owns it, and it takes one message.

The tell is a solution that is more complicated than the direct approach *and*
happens to avoid a check. Complexity that buys nothing but permission is not
engineering.

Related: [[never-mutate-to-test-a-refusal]]
