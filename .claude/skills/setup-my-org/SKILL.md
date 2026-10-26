---
name: setup-my-org
description: Interview the user and stand up their agent org — vault, named team, symlinks into ~/.claude, verified end to end. Use once per fork, after cloning the base repo. For changing an existing org use org update instead.
---

# Set up my org

You are standing up someone's agent team for the first time. At the end they
have a vault, a named org with a reporting line, and Claude able to see all of
it — proven by asking an agent who it is, not by printing a success message.

**Runs once per fork.** One fork holds one org ([ADR-0002](../../../docs/decisions/0002-one-org-per-fork.md)).
If a vault already has `Team/Team-ORG.md`, this is an update: point at
`org update` and stop.

## Before asking anything

```bash
python3 tools/check_public.py    # you are in the right repo if this runs
```

If the user already has a vault, check for an existing org before the
interview. Discovering it afterwards wastes their time on questions whose
answers you cannot use.

## The interview

Ask these **conversationally, a few at a time** — not as a form. Offer the
default in each question so someone who does not care can say "defaults" and be
done. Do not ask about anything they have already told you.

**1. Their name, and what the org calls them.**
Used throughout the generated files. It also becomes a reserved word: no agent
may share it.

**2. Which packs.** Show the tree and let them prune. Defaults to `core` alone —
three roles. Do not talk anyone into fifteen.

| Pack | Adds | Good for |
|---|---|---|
| `core` *(always)* | chief of staff, engineering lead, operations lead | everyone |
| `engineering` | senior engineer, 2 engineers, QA | you are shipping code |
| `product` | product, design lead, UI, content | you have users |
| `operations` | systems engineer | you run infrastructure |
| `process` | scrum master | work goes invisible |
| `gtm` | growth | you are selling |
| `legal` | legal & compliance *(drafts only — never files or signs)* | terms, privacy, store policy |

**3. Naming.** `default` (Joe, Bill, John…), a theme (`friends`, `singers`,
`greek`, `scientists`, `norse`, `botanical`), `role_ids` for no names at all, or
their own list.

Say plainly what naming is and is not: **cosmetic**. Role ids are what skills
reference, so a theme changes labels and nothing else. Also say the cost — a
themed org trades some role legibility ("Chandler says the deploy is blocked"
tells you less than "the ops lead does"), which generated docs soften by always
rendering `Name (title)` on first mention.

**4. Budget posture.** `frugal` · `balanced` (default) · `max`. This maps role
tier to model once, rather than making them choose fifteen times. Be honest that
a fifteen-agent org is not cheap and `frugal` is a reasonable place to start.

**5. Vault path.** Default `~/vault`. **Its own git repository**, separate from
this one — their knowledge should not be a fork of anyone's tooling.

**6. Tracker.** `github-issues` (default), `jira`, or `none`. GitHub Issues
works for anyone with a repo and has no OAuth wall; Jira needs an authorised MCP
server, which cannot be set up from a non-interactive session. Ask for the repo
(`owner/name`) or the Jira project key.

## Run it

```bash
python3 tools/setup.py \
  --vault ~/vault --principal NAME \
  --packs core,engineering --theme greek --posture balanced \
  --tracker github-issues --tracker-project owner/repo \
  --today YYYY-MM-DD
```

Then, from the vault:

```bash
cd ~/vault
python3 .claude/skills/install-org/install.py
python3 lint_vault.py
```

`setup.py` validates before it writes, so a bad answer fails cleanly rather than
leaving half a team on disk. If it refuses because an org exists, do not pass
`--force-reseed` to get around it — that flag re-copies seed files, it does not
make a second org, and reaching for it means the answer was `org update`.

## Prove it — this is the step that matters

Everything so far is a script reporting on itself. Three things it cannot check:

1. **Start a new Claude session.** Agents load at session start.
2. **Ask one agent to state its name, role, and who it reports to.**
3. **Compare that against `Team/Team-ORG.md`.**

If they disagree, the setup is wrong even though every command exited zero. That
round-trip is the only evidence the whole chain works — vault → symlink → Claude
→ the agent reading its own Soul and Role.

Say what you checked and what you did not.

## Then hand over

Tell them, briefly:

- **Souls are theirs now.** Generated as a starting point; they should be
  rewritten. The lint nags once real work has happened and they are untouched.
- **`Team-ORG.md` and `*-Role.md` are generated** — edit `roles.yaml` and run
  `org update`. Hand-edits are reverted, and the lint fails on drift.
- **Journals carry PRs and tokens**; the chief of staff rolls them into a brief
  capped at 20 bullets. Ask for detail rather than expecting it up front.
- **The vault is its own git repo.** Commit it, keep the remote private, and
  they can clone onto another machine and run `install-org` there.

## When it goes wrong

**"An org already exists."** Working as designed. `org update` to change it, or
fork the base repo again for a genuinely different team.

**Render fails on names.** The message names the offending name and the rule —
reserved word, duplicate, pattern, or colliding with the principal. Re-ask for
that one name only; never substitute silently.

**A pack reports to a pack they dropped.** The error names both. Add the parent
pack or drop the child.

**Claude cannot see the agents.** The session predates the install. Start a new
one.
