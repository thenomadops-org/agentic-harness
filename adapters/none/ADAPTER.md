---
adapter: none
requires: nothing
configured_by: org.config.json → tracker.kind = "none"
---

# Adapter — none

No tracker. Work arrives in conversation and the org keeps its own record.

This is a real choice, not a placeholder. For a solo user it removes an entire
system, and the org still produces journals, a brief and a growing wiki — which
is most of what a tracker was providing.

## The seven operations

| Operation | Here |
|---|---|
| `list_ready` | Ask. There is no queue to poll. |
| `read` | The request, as stated, plus anything in `Clients/<slug>/`. |
| `claim` | Say what is being started, in one line, before starting. |
| `comment` | Progress goes in the agent's journal, not a ticket. |
| `link_pr` | The PR body names the work; the journal records the PR number. |
| `hand_off` | Open the PR, report the URL, stop. |
| `verify_state` | The PR is the state. `gh pr view --json state,mergeStateStatus`. |

## What is lost, honestly

**No durable record of what was asked** beyond the journals. If a request is
made in conversation and the session ends, the only trace is what an agent wrote
down. That is a real gap and it is why journals are not optional.

**No queue means no dispatch.** Nobody can be handed work asynchronously; every
piece starts from a conversation. Fine for one person, poor past two or three.

**Acceptance criteria live nowhere canonical.** With a tracker they are in the
ticket, read at closing time. Here they are whatever was said, so **write them
into the PR body before starting** and check against that.

## When to move off this

When you find yourself asking "what was I doing?" or re-explaining the same
request. That is a queue asking to exist. `github-issues` costs one label
creation and works with the repo you already have.
