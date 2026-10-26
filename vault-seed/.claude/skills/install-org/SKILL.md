---
name: install-org
description: Wire this vault's agents, skills and commands into ~/.claude and prove they work. Use after cloning the vault onto a new machine, after rendering or updating the org, when Claude cannot see the team, or when the vault lint reports skills outside the vault.
---

# Install the org

Everything the org is lives in the vault. `~/.claude` holds nothing but symlinks
pointing here. This skill creates those links and then **proves** they took —
because "the installer printed success" and "Claude can see your team" are
different claims, and only the second one matters.

## Bootstrap — the part that looks circular but is not

On a new machine you have a cloned vault and no installed org. This skill is in
the vault, so:

```bash
cd /path/to/your-vault
claude
```

Claude reads `.claude/skills/` from the working directory, so `install-org` is
available before anything is installed. That is the whole bootstrap.

## Run it

```bash
python3 .claude/skills/install-org/install.py --dry-run   # see the plan
python3 .claude/skills/install-org/install.py             # do it
```

Then **read the output rather than the exit code alone**. It lists every link
with what was already at the target.

### What the markers mean

| | Meaning | What to do |
|---|---|---|
| `+` | linked | nothing |
| ` ` | already correct | nothing — the script is idempotent |
| `!` | points at another vault | `--force` repoints it |
| `!` | **REFUSED — a real file** | move it into the vault, then re-run |

**A real file or directory is never replaced, not even with `--force`.** If
something in `~/.claude/skills/` is a real directory rather than a link,
somebody wrote a skill directly there — it is untracked and unsynced, and it is
the thing the vault lint complains about. Move it into
`<vault>/.claude/skills/`, then run this again. Deleting it on the user's behalf
is not recoverable.

## Verify — do not skip this

The script already re-reads from disk: every link resolves, every target is
inside this vault, and every agent file has parseable frontmatter with a `name:`.
An agent Claude cannot parse is installed and useless, and nothing else would
have caught that.

Then do the part the script cannot:

1. **Start a new Claude session.** Agents are read at session start; an existing
   session will not see them.
2. **Ask one agent to identify itself** — name, role, and who it reports to.
3. **Check the answer against `Team/Team-ORG.md`.**

If step 3 disagrees, the install is wrong even though every link resolved. That
is the round-trip, and it is the only evidence that the whole chain works:
vault → symlink → Claude → the agent's own Soul and Role files.

## Then run the vault lint

```bash
python3 lint_vault.py
```

Its "skills in the vault" check is the standing guard on this. It fails on any
skill in `~/.claude/skills/` that is not a symlink pointing here — which is how
you find out that a skill was created in the wrong place, weeks later, before it
is lost with the machine.

## Moving to a new machine

```bash
git clone <your-vault-remote> ~/vault
cd ~/vault
claude
```
Then invoke this skill. Nothing else carries over — no config to copy, no paths
to edit. That is the reason the vault holds everything and `~/.claude` holds
only links.

## Uninstalling

```bash
python3 .claude/skills/install-org/install.py --uninstall
```

Removes **only** symlinks pointing into this vault. Anything else in
`~/.claude` is left exactly where it is, including links to a different vault.

## When this goes wrong

**Claude still cannot see the agents.** The session was already open. Start a
new one — agents are read at startup.

**Windows: `OSError` on symlink.** Symlinks need Developer Mode or an elevated
shell. The script says so when it hits it.

**The lint still reports skills outside the vault.** You have two vaults and the
other one is installed. That check compares against the vault the lint lives in,
so it is telling you the truth: only one org can be installed at a time.

**An agent answers with the wrong manager.** The links are fine and the content
is stale — `Team/` was rendered before a `roles.yaml` change. Re-render, then
re-run this.
