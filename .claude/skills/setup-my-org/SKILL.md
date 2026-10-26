---
name: setup-my-org
description: Set up a role-persona org, vault and Claude links, then verify a generated persona can read its role. Use once per fork; use org-update for an existing org.
---

# Set up my org

Set up the user's org for the first time. The role id is the persona's display
and agent identity. Never ask for or assign a personal name to an agent. Live
sessions use `<persona>-<TICKET>`; pooled roles add a numeric seat suffix before
the ticket, such as `engineer-1-OPS-345`.

**Runs once per fork.** If `Team/Team-ORG.md` exists, stop and use `org-update`.

## Before asking anything

```bash
python3 tools/check_public.py
```

Check whether the user already has a vault before interviewing them.

## The interview

Ask conversationally and skip anything already answered.

1. **Principal display name.** This is the human owner, never an agent persona.
2. **Packs.** `core` is always included. Offer engineering, product, and
   operations based on the work the user does.
3. **Budget posture.** `frugal`, `balanced` (default), or `max` maps role tiers
   to models.
4. **Vault path.** Default `~/vault`; it should have its own git repository.
5. **Tracker.** `github-issues` (default), `jira`, or `none`; ask for the repo
   or project key when needed.
6. **Where tasks run.** Ask whether all tasks run on the user's own machines
   (`local`, the default) or in the cloud (`cloud`). Default to their own
   machines; the maintainer's preference is always their own machines. Pass
   the answer as `--execution`.

The SDLC personas are `product`, `engineer`, `ios-engineer`,
`android-engineer`, `devops`, `qa`, `sre`, and `lead`. Their responsibilities
are defined in `org/roles.yaml` and follow the stage table in the workforce
guidance.

## Run it

```bash
python3 tools/setup.py \
  --vault ~/vault --principal OWNER \
  --packs core,engineering --posture balanced \
  --tracker github-issues --tracker-project owner/repo \
  --execution local \
  --today YYYY-MM-DD
```

Then install and lint from the vault:

```bash
cd ~/vault
python3 .claude/skills/install-org/install.py
python3 lint_vault.py
```

The renderer validates before writing. If an org already exists, do not force
reseed; use `org-update`.

## Prove it

Start a new Claude session named `<persona>-<TICKET>`, ask for its role id and
manager, and compare the answer with `Team/Team-ORG.md`. Report what was checked
and what was not.

## Handoff

- Generated role files are changed in `org/roles.yaml` and refreshed with
  `tools/update.py`.
- Soul and memory files belong to the user and are preserved by updates.
- The vault is its own repository and can be installed on another machine.

If Claude cannot see generated personas, start a new session after linking them.
