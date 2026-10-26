---
name: org-update
description: Re-render an existing role-persona org after changing roles.yaml or pulling base-repo updates — refreshes generated files while preserving authored content and safely migrating legacy naming settings. Use for org changes or upstream updates, not first-time setup.
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

**Nothing is ever deleted.** Remove a role from `roles.yaml` and its old
`Team/` directory stays, reported as orphaned. It may contain authored Soul,
memory, or other work. Remove it only by explicit user choice.

## Changing the shape of the org

Edit **`org/roles.yaml`** — never the generated files. The lint fails on a
hand-edited generated file precisely because the next update would revert it,
and until then two files would describe the same person differently.

Role ids are the display and agent ids. Existing configurations may still
contain legacy display selectors; update removes those obsolete selectors
after a successful render, drops retired pack selections, and preserves every
other configuration value. Old generated directories and files are reported
and left intact, so authored content is not lost during migration.

Adding a pack adds persona seats with generated Soul files. The user should
write the Souls as part of onboarding.

## After it runs

1. **`install-org`** — new seats mean new agent files that need linking.
2. **`lint_vault.py`** — must be clean.
3. **New Claude session** named `<persona>-<TICKET>`, then ask a changed persona
   to state its role id and manager.

Report what changed, what was preserved, and anything orphaned. An update that
says only "done" hides exactly the information the user needs.
