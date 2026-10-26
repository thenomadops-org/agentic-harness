# Spec — a portable agentic workforce

**Status:** DRAFT, 2026-10-07
**Intent:** [../intent/portable-workforce.md](../intent/portable-workforce.md)
(owner rulings 1–10)
**Decision:** [ADR-0003](../decisions/0003-agents-merge-owner-promotes.md),
agents merge behind a gate and the owner promotes to production
**Terms:** [../GLOSSARY.md](../GLOSSARY.md)

Each fact is checkable. Its story cites it by anchor. `Open:` marks what is not
yet decided.

## F1 — The workforce is a plugin in `plugin/`

`plugin/` holds the workforce. A marketplace manifest at the repository root
lets a node install it with `claude plugin install`. It contains:
- `.claude-plugin/plugin.json`;
- `agents/`, one definition per role: engineer, senior-engineer, qa,
  android-engineer, ios-engineer, firebase-engineer, and the planning roles;
- `skills/`, the lifecycle skills (F12);
- `hooks/`, the hard laws (F7, F8);
- `lessons/`, the org lessons (F11).

The role agents and skills that live in `.claude/` and in the platform config
today move there. Nothing in `plugin/` names a person, a private host or a
private project.

A release is a git tag. A node updates by installing that tag, and the node
client reports the installed version on its heartbeat.

## F2 — Workforce changes are merged by the owner

A pull request that changes any path under `plugin/` is refused by the merge
gate (F7) for every actor except the owner, or an agent the owner has told in
conversation to merge it. Every other path follows the merge gate.

## F3 — Every project has a project file

`.agentic-os.yaml` at a project's repository root names:
- `board_project`, the board project key;
- `roles`, the roles the project needs;
- `test`, the command that must pass before a hand-off;
- `build`, the command that builds the project;
- `staging`, how a merge to `main` deploys staging, the staging URL, and how
  to check that the deploy took;
- `production`, the deploy command or pattern that the production hook (F8)
  guards.

`/onboard-project` (F12) writes the file and the first `CLAUDE.md`, by
interviewing the owner and reading the repository. Open: the staging section
for each project, filled in when that project is onboarded.

## F4 — Project knowledge lives in the project's repository

- `CLAUDE.md` sits at the repository root. Agents add a folder-level
  `CLAUDE.md` wherever a folder needs more specific context.
- `docs/memory/` holds one Markdown file per lesson. Each file has frontmatter
  `{title, summary, role, links}`, and `docs/memory/README.md` indexes them.
- Changes to these files ride in the story's own pull request, under the merge
  gate (owner ruling 7).

## F5 — One coordinator per project: the project lease

The board gains `acquire_project_lease {project, node}`,
`renew_project_lease {project, node}` and `release_project_lease
{project, node}`:
- An acquire is refused while another node holds an unexpired lease on that
  project. The refusal names the holder.
- A lease expires when it has not been renewed within its TTL. The default TTL
  is 10 minutes, and the coordinator renews every 2.
- The Nodes page shows which node holds which project, and since when.
- Each lease change writes one audit row.

## F6 — The coordinator run loop

> **Removed in OPS-333.** `/start-ready-work` and its coordinator are gone from this tree. `/stop-work` remains and fails closed: there is no lease to release. Recoverable from tag `pre-harness-rewrite` (`c114b2e`). The harness rewrite is OPS-334.

`/start-ready-work`, run in a project's repository on a node:
1. reads `.agentic-os.yaml`;
2. acquires the project lease and renews it for as long as it runs;
3. loops:
   - takes the next approved story in its project;
   - starts a builder subagent in the story's role on Sonnet, in its own
     worktree;
   - waits for the builder's pull request and hand-off;
   - runs `review-council` and a QA verify subagent, on a model the
     coordinator picks that differs from the builder's (F13);
   - merges when the gate passes (F7);
   - confirms the staging deploy (F3);
   - moves the card to ready for human test (F9).

Every claim, hand-off, verdict, merge and block is posted to the relay. The loop
stops on `/stop-work`, which releases the lease, or when no approved story is
left. The coordinator writes nothing but board calls and git operations.

## F7 — The merge gate is a hook, not a judgement

> **Removed in OPS-333.** The hook at `plugin/hooks/merge-gate/` is gone. The rules to port into the Phase 1 qa-verdict check are in [`../decisions/merge-gate-rules-for-phase1.md`](../decisions/merge-gate-rules-for-phase1.md).

A hook runs before any merge of a pull request to `main` and before the board
records a story as `merged`. It refuses the merge unless all of these hold:
1. `review-council` recorded a passing verdict on the story;
2. a QA verification is recorded, by an actor that is not the builder, on a
   model that differs from the builder's;
3. every required CI check on the head commit is green;
4. the merging actor is not the builder;
5. the pull request touches nothing under `plugin/` (F2).

An owner override recorded on the story lets the merge through. An override
names the instruction, who gave it and when, and it is audited. Each condition
has a test that fails when the condition is removed.

## F8 — The other hard laws are hooks

- **Secrets and private names.** The publication-boundary check gates every
  commit and push in a publishable repository. A failed check blocks the
  commit, and the check never runs through a pipe.
- **The builder never verifies its own work.** This is already enforced by the
  board (`sign_off` and review refusals). It is kept, and extended to the F9
  verification record.
- **Production is the owner's.** A command matching the project file's
  `production` pattern, or a destructive production change named there, is
  blocked without an owner override.

Every other action is a right of the role and is not gated (owner ruling 6).

## F9 — Verification before the merge, human test after

The board records QA's verdict on an `in_review` story with
`record_verification {id, verdict, model, artifact}`. The verifier must be an
actor other than the builder. Then:
1. A merge recorded with a staging deployment row puts the card in a **Ready
   for human test** lane.
2. When the owner accepts, the card closes. A failure the owner reports becomes
   a fix story linked to the card, or a revert.
3. Promoting to production (`release_story`) stays principal-only.

The old flow, where a story was signed off after the merge, applies only to
stories already merged before this ships.

## F10 — The law text matches ADR-0003

The board's SDLC law 7 is rewritten through `set_lifecycle` to read: "Agents
merge to `main` behind the merge gate; merging deploys staging; the owner
promotes to production. A direct instruction from the owner overrides any gate
and is recorded." `/sdlc` shows the new text, and `get_sdlc` returns it.

## F11 — Board memory: migrate, curate, archive

1. **Migrate.** Each project tier is exported into its repository's
   `docs/memory/` in the F4 format, as one pull request per repository.
   Project tiers whose project has no repository are listed for the owner.
2. **Curate.** The org tier is curated into `plugin/lessons/`, keeping only
   lessons that still hold, as one promote pull request the owner merges.
3. **Archive.** After both, `write_memory` and `update_memory` on the board are
   refused with a pointer to the repository. Search stays read-only, and the
   memory map page is removed.

## F12 — Lifecycle skills

The plugin ships one skill per stage:

| Skill | What it does | Status |
|---|---|---|
| `/onboard-project` | Writes F3 and F4 | new |
| `/scope` | Turns a conversation into an intent card plus the intent document | new |
| `grill-plan` | Sharpens the intent | exists |
| `/spec` | Writes numbered facts and a spec card | new |
| `/split-stories` | Files approved work cards, each citing a fact | new |
| `/start-ready-work` and `/stop-work` | Run the loop (F6) | `/start-ready-work` removed in OPS-333; `/stop-work` fails closed |
| `review-council` | Reviews the pull request | exists |
| `testing` | Tests the build | exists |
| `delegated-task` | Runs a story handed to an agent | exists |
| `/retro` | Writes project lessons to `docs/memory/` | new |
| `/promote-lessons` | Proposes org lessons as a `plugin/` pull request | new |

## F13 — Models

- The coordinator runs on Opus.
- Builders run on Sonnet unless a story's model field says otherwise.
- The coordinator picks the verify model per story, and it must differ from
  the builder's.
- Each run records the model on the story's run and on the verification
  record.

## Parked, not part of this spec

- server-to-node dispatch and the headless runner;
- per-story usage attribution;
- node-to-node fan-out;
- per-job token minting for coordinator-run builders.

Those builders use the coordinator's own board credential, and the board
attributes each action to the run.
