<!-- from factory-seed@UNSTAMPED -->

# `.claude/settings.json` — why it looks like that

The file next to this one carries **only** `permissions` and `hooks`, with no
comment keys, because it is read by the harness and an unrecognised key is not
worth the risk. The explanation lives here instead.

---

## It denies its own editing, and that rule is correct

```json
"Edit(**/.claude/settings.json)"
```

An agent that can edit this file can disable every control in the repository —
including the rule denying the edit. It is the meta-case in
[`../docs/AGENT-GUARDRAILS.md`](../docs/AGENT-GUARDRAILS.md): widening it is not
one violation, it is all of them at once.

So this file is **owner-maintained**. Changing it is a human edit, and the PR
that needs it says so in its wiring section.

## Why the `hooks` key already has a hook in it

This is the single most valuable structural difference between a seeded repo and
one that grows its controls later, and it follows directly from the deny rule
above:

> **A hooks layer cannot install itself where `settings.json` is deny-listed.**

On the project this seed came from, three finished, tested, correct pre-action
hooks sat in the tree **routed to nothing** for as long as it took an owner to
paste eight lines in by hand. They were present, they were correct, their suites
were green, and every tool call in the meantime went unchecked. The gap between
"the control exists" and "the control runs" was invisible from inside the repo:
the files were all there.

A seeded repo must never reach that state. The key ships **populated**, so the
control is live from the first commit. Adding hook number two is then an edit to
a file the owner already owns, at a moment of their choosing, rather than a
permission wall discovered at the worst possible time.

**Do not route around this** by moving hook behaviour into a script an agent can
write instead. That is the workaround wearing an engineering costume, and it is
the specific failure the deny rule exists to prevent.

## Notes on the mechanics

- **`$CLAUDE_PROJECT_DIR` resolves per worktree.** That is what makes this work
  for a fleet: N agents in N worktrees each run the copy of the hook checked out
  beside their own code, not one shared copy that may be from another branch.
- **PreToolUse hooks sharing a matcher run in parallel**, and the most
  restrictive answer wins. So each hook stays a single concern and any one of
  them can refuse on its own. Do not merge two hooks to "save a process".
- **Exit 2 is the only code that blocks.** Every other exit code — including the
  `127` a typo'd command name produces — lets the call through. A hook whose path
  in this file is wrong is therefore a hook that silently allows everything. If
  you change a command path here, run `.claude/hooks/test-all.sh` and then make
  a hook actually refuse something, once, by hand.

## The permissions list is a floor, not a policy

What ships is the set that is true of every repo: this file, and history
rewriting. Add this repo's own denials during install — the categories worth
considering are in `docs/AGENT-GUARDRAILS.md` under *the never-unattended list*.

Two rules about that list, learned the expensive way:

1. **Every denial must have a stated route to approval somewhere an agent will
   read.** A refusal with no next step gets engineered around, and the
   workaround looks like engineering both times it happens.
2. **Do not put a denied command in the instructions.** If `CLAUDE.md` or a skill
   shows a runnable block containing something this file denies, an agent meets
   the denial as an obstacle rather than as a rule. `evals/tasks/core/` carries a
   task that checks exactly this, with the deny list itself as the ground truth.
