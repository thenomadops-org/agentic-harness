---
adapter: jira
requires: an authorised Atlassian MCP server
configured_by: org.config.json → tracker.project = "PROJECT KEY"
---

# Adapter — Jira

More capable than GitHub Issues and considerably more able to fail quietly.
Every trap below is one that has actually cost someone a day.

## Before anything

**Jira needs interactive authorisation.** The MCP server uses OAuth, which
cannot be completed from a non-interactive session. If the org is going to run
unattended, authorise it first from an interactive terminal and confirm a read
works. An unauthorised server does not announce itself usefully — see the first
trap.

Resolve and record once, at setup:

- **cloudId** — site-wide, not per-project
- **project key** — exact, uppercase
- **transition ids** — read live from a real issue, never assumed

## The seven operations

Expressed as intent; the MCP tool names vary by server version.

### `list_ready`

JQL: `project = KEY AND status = "<ready status>" ORDER BY Rank ASC`

> [!danger] A malformed JQL returns an empty result set, not an error
> `project = WRONGKEY` and `project = DOESNOTEXIST` both come back as `[]`,
> identical to a genuinely empty queue. **"Nothing matched" and "your query was
> wrong" are indistinguishable at the call site.**
>
> Before reporting an empty queue, confirm the project key and status name exist
> — list visible projects and read the statuses off a real issue. Do this once
> per session, not once per poll.

### `read`

Fetch the issue with description **and** comments. Acceptance criteria live in
the description; amendments live in comments. Reading one is how you build the
wrong thing correctly.

### `claim`

Transition to the in-progress status, **then read the issue back and compare**.

> [!danger] Transition ids differ per project and collide across them
> `61` may be one status on one board and something entirely different on
> another. Firing an id resolved against the wrong project moves the ticket to a
> real, wrong state and reports success.
>
> **Resolve transitions by NAME against the live issue, every time.** Never
> hardcode ids, and never reuse ids across projects.

### `comment`

Post the update. Comments are permanent and visible to whoever can see the
project — write them for that audience.

### `link_pr`

Put the PR URL in a comment with the head SHA. Jira's dev-panel integration is
unreliable when the remote is not connected, and a URL in a comment always works.

### `hand_off`

Transition to the review status, resolved by name, then read back. **Never
transition to Done.** Review with a PR open is the handoff.

### `verify_state`

Re-fetch the issue and read its status. A transition call that returns 200 has
not proven the issue moved.

## Traps

**Malformed JQL returns `[]`.** Repeated because it is the one that wastes days:
an empty queue and a broken query look identical.

**Transition ids are per-project.** Resolve by name, live, every time.

**Project keys can be renumbered by a project move.** If issues were migrated,
old keys may redirect to *different* numbers — `OLD-133` can resolve to
`NEW-16`, not `NEW-133`. Resolve the old key through the API and use the key it
returns. Never rewrite a prefix by string substitution; it lands on a real but
unrelated issue.

**Two similar statuses.** Some projects carry both `Review` and `In Review` as
distinct columns. Confirm which one the workflow actually uses rather than
assuming they are aliases.

**Status names are per-workflow, not global.** The status you want may not exist
on this issue type even though it exists in the project.

## Setup checklist

- [ ] MCP server authorised, interactively, and a read confirmed
- [ ] cloudId recorded
- [ ] project key confirmed against the visible-projects list — not typed from memory
- [ ] transition ids read from a live issue and recorded **with their names**
- [ ] ready / in-progress / review status names confirmed to exist
