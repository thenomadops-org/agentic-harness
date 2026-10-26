---
name: org-update
description: Re-render an existing org after changing roles.yaml or pulling base-repo updates — regenerates Team-ORG, Role files and agents while preserving Souls and memory. Use to add a pack, rename someone, change the reporting line, or take upstream skill improvements. Not for creating an org; that is setup-my-org.
---

# Update the org

Setup runs once. This runs every time after.

```bash
python3 tools/update.py --vault ~/vault --dry-run   # see what moves
python3 tools/update.py --vault ~/vault
cd ~/vault && python3 .claude/skills/install-org/install.py && python3 lint_vault.py
```

## What it will and will not touch

| Regenerated | Preserved |
|---|---|
| `Team/Team-ORG.md` | every `*-Soul.md` |
| every `Team/*/*-Role.md` | every `*-Memory.md` |
| `.claude/agents/*.md` | `Team-Operating-Agreement.md` |
| skills, adapter, lint tooling | everything in `Sessions/`, `Clients/`, `.claude/memory/` |

A Role file describes what the org decided. A Soul describes who someone became.
Regenerating the first is correct; regenerating the second erases the only thing
that made it worth having.

**Nothing is ever deleted.** Remove a role from `roles.yaml` and its `Team/`
directory stays, reported as orphaned. That person has a Soul someone wrote and
a memory they built — deleting it is a decision, not a cleanup step. Do it by
hand when you mean it.

## Changing the shape of the org

Edit **`org/roles.yaml`** — never the generated files. The lint fails on a
hand-edited generated file precisely because the next update would revert it,
and until then two files would describe the same person differently.

To change the theme, packs or posture, edit `<vault>/.claude/org.config.json`
deliberately, then update. That indirection is intentional: an update should not
be able to quietly rename the whole team.

Adding a pack adds seats with generated Souls. Say so — the new people need
their Souls written like everyone else's.

## After it runs

1. **`install-org`** — new seats mean new agent files that need linking.
2. **`lint_vault.py`** — must be clean.
3. **New Claude session**, then ask a *changed* agent to state its role and
   manager. If someone's reporting line moved, that is the one to ask.

Report what changed, what was preserved, and anything orphaned. An update that
says only "done" hides exactly the information the user needs.
