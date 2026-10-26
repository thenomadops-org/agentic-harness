---
adapter: github-issues
requires: gh, authenticated
configured_by: org.config.json → tracker.project = "owner/repo"
---

# Adapter — GitHub Issues

The default. Everything is `gh`, which is already installed and authenticated
wherever code gets reviewed, and there is no OAuth flow to complete before the
org can read its queue.

Set `REPO` from `tracker.project` in `org.config.json`.

```bash
REPO=owner/repo
```

## State model

GitHub has no workflow states, only labels — so the adapter defines them, and
`setup` creates them. Three, deliberately:

| Label | Means |
|---|---|
| `ready` | available to start |
| `in-progress` | claimed |
| `in-review` | handed off — a human decides from here |

```bash
gh label create ready       -R "$REPO" --color 0E8A16 --description "Available for an agent to start" 2>/dev/null || true
gh label create in-progress -R "$REPO" --color FBCA04 --description "Claimed by an agent" 2>/dev/null || true
gh label create in-review   -R "$REPO" --color 1D76DB --description "Handed off for human review" 2>/dev/null || true
```

## The seven operations

### `list_ready`

```bash
gh issue list -R "$REPO" --label ready --state open \
  --json number,title,labels,assignees,updatedAt --limit 50
```

An empty array means nothing is ready. Unlike some trackers, a malformed query
here **errors** rather than returning empty — `gh` exits non-zero on a bad
label. Trust the exit code.

### `read`

```bash
gh issue view "$N" -R "$REPO" --json number,title,body,comments,labels,assignees
```

Read `body` **and** `comments`. Acceptance criteria are frequently amended in a
comment rather than edited into the body, and reading only the body is how you
build the wrong thing correctly.

### `claim`

```bash
gh issue edit "$N" -R "$REPO" --add-label in-progress --remove-label ready
gh issue comment "$N" -R "$REPO" --body "Started by <agent> (<role_id>)."
```

Then `verify_state`. Adding a label that is already present succeeds silently,
which means "the command worked" does not establish that you were the one who
claimed it.

### `comment`

```bash
gh issue comment "$N" -R "$REPO" --body "$(cat <<'EOF'
...
EOF
)"
```

### `link_pr`

GitHub links these itself when the PR body contains a closing keyword — but
**do not use `Closes #N`**. That closes the issue on merge, and this org never
closes. Reference it without the keyword:

```bash
gh pr create -R "$REPO" --title "..." --body "Implements #$N" --draft
```

`Implements`, `Part of` and `Refs` all link without closing. `Closes`, `Fixes`
and `Resolves` close on merge and take the acceptance-criteria check with them.

### `hand_off`

```bash
gh issue edit "$N" -R "$REPO" --add-label in-review --remove-label in-progress
gh issue comment "$N" -R "$REPO" --body "Handed off. PR: <url>. Not verified: <gaps>."
```

Then `verify_state`. **Never `gh issue close`.**

### `verify_state`

```bash
gh issue view "$N" -R "$REPO" --json number,state,labels \
  --jq '{number, state, labels: [.labels[].name]}'
```

Compare against what you set. This is a separate call on purpose: reusing the
response from the edit tells you what you asked for, not what is true.

## Traps

**`Closes #N` in a PR body closes the issue on merge.** The single most likely
way this org accidentally closes work. Use `Implements #N`.

**Label operations are idempotent and silent.** Adding `in-progress` to an issue
that already has it succeeds. If two agents claim the same issue, both commands
succeed and both agents believe they own it. The queue must be read and claimed
in one place — that is the dispatcher's job, not the adapter's.

**`--limit` defaults to 30.** A queue longer than that silently truncates and
looks like the end of the list. Set it explicitly.

**Issue numbers are shared with PRs.** `#42` may be either. `gh issue view 42`
on a PR number returns the PR, so check the type before acting on it.

**A closed issue can be reopened but loses its labels.** If something is closed
by mistake, reopening does not restore `in-review` — set it again explicitly.

## Setup

```bash
gh auth status                          # must be authenticated
gh repo view "$REPO" --json name        # must be reachable
```

Both before the first run. An unauthenticated `gh` fails per-command in ways
that read like an empty queue.
