# Your vault

This is where the org keeps everything it knows. It is a plain folder of
Markdown — open it with Obsidian, edit it with anything, and keep it in git.

**It is not one thing.** Six zones live here with genuinely different
lifecycles, and most of the rules below exist to stop one zone's rules being
applied to another.

## The zones

| Zone | Written by | On `org update` | Hand-edit? |
|---|---|---|---|
| `Team/Team-ORG.md` | generated | **overwritten** | no — edit `roles.yaml` |
| `Team/<Name>-<Role>/*-Role.md` | generated | **overwritten** | no — edit `roles.yaml` |
| `Team/<Name>-<Role>/*-Soul.md` | generated once, then yours | preserved | **yes, please** |
| `Team/<Name>-<Role>/*-Memory.md` | the agent | preserved | rarely |
| `Sessions/` | agents, append-only | preserved | no |
| `Clients/<slug>/` | agents — **the wiki** | preserved | yes |
| `.claude/memory/` | agents | preserved | rarely |
| `.claude/skills/` | agents and you | preserved | yes |

The generated/authored split is the one that bites. A Role file describes what
the org decided; a Soul describes who someone became. Regenerating the first is
correct, regenerating the second would erase a month of accumulated character —
so `org update` never touches a Soul after the first write.

`lint_vault.py` enforces this in both directions: it fails if a generated file
was hand-edited, and it fails if a Soul is still the untouched template after
real work has happened.

## The wiki

`Clients/<slug>/` grows as agents work. It is not a documentation project
someone is assigned; it is the residue of doing the job.

The rule: **when an agent learns something about a client that outlives the
ticket, it becomes or updates a page there**, and links to the memory atom that
carries the lesson. Tickets are episodic and disappear into a closed board. The
wiki is what remains.

Backlinks are the mechanism, and `lint_vault.py` checks them: an orphan page is
one nothing points at, which means retrieval will never reach it. A correct,
well-written page nothing links to is worse than a missing one, because you
believe the ground is covered.

## Memory has two scopes

```
.claude/memory/_shared/      lessons that travel — how work goes wrong in general
.claude/memory/<client>/     facts about one client's cluster, board, product
```

Getting this wrong is the common failure and it fails in both directions. A
client fact in `_shared` pollutes every other engagement. A general lesson filed
under one client means it gets learned again on the next. The lint has a
heuristic for the first case; the second is on you.

## Journals and the brief

Every agent writes a journal entry per working session in `Sessions/`, carrying
**PRs touched and tokens used** as structured frontmatter — measured, not
estimated. These are raw and there are a lot of them; nobody is expected to read
them all.

The chief of staff rolls them into `Sessions/Brief-YYYY-MM-DD.md`: **bulleted
highlights, not narrative.** Shipped · Blocked · Needs a decision · Worth
watching. Each bullet names who and points at the detail.

The brief is capped by the lint at 20 bullets. That cap is the feature — a brief
that grows to fill the available space stops being read, and an unread brief is
worse than none because it looks like reporting happened.

Ask for detail when a bullet warrants it. That is the whole protocol.

## Skills

Agents write skills. Every one lives in `.claude/skills/` **here**, in the
vault, and is symlinked into `~/.claude/skills/` — never created directly in
`~/.claude/`, where it would be untracked, unsynced, and invisible to the
vault's own history.

`install-org` creates those links and verifies them. Once this vault is
linked from the home directory, the lint fails on a skill in
`~/.claude/skills/` that is not a symlink pointing into this vault. A home
directory that does not link this vault is not this install, and the lint
does not judge it.

## Git

The vault is its own repository, separate from the Agentic-OS repo. Your
knowledge is not a fork of anyone's tooling.

Obsidian's Git plugin is the simplest way to sync on a timer; a cron calling
`git add -A && git commit && git push` works equally well and is what runs when
Obsidian is closed.

> [!warning] This repository will contain client material
> One team works every client and there is no wall between them — see ADR-0001.
> Anything an agent learns lands here, and `git push` sends it wherever the
> remote is. **Keep the remote private**, and check `.gitignore` before adding
> anything that handles credentials.

## The lint

```bash
python3 lint_vault.py          # non-zero exit on failure — usable as a gate
python3 lint_vault.py --fix    # only for things that are safe to fix
```

Run it after vault writes. Every agent is told to.
